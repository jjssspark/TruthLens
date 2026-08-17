import json
import time

import cv2
import numpy as np
import pytest

import ai_models.video_detector as vd_module
from ai_models.video_detector import VideoDetector


def _write_video(path, frames, fps=10.0, size=(64, 64)):
    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    for frame in frames:
        writer.write(frame)
    writer.release()


def _random_frames(count, size=(64, 64)):
    """프레임마다 완전히 다른 랜덤 노이즈 — 자연스러운 변화가 있는 '진짜 영상'을 흉내낸다."""
    return [
        np.random.randint(0, 255, (size[1], size[0], 3), dtype=np.uint8)
        for _ in range(count)
    ]


def _static_frames(count, size=(64, 64)):
    """모든 프레임이 동일 — 보간/합성 의심 신호(시간적 일관성 이상)를 흉내낸다."""
    base = np.full((size[1], size[0], 3), 128, dtype=np.uint8)
    return [base.copy() for _ in range(count)]


def test_sampled_frames_are_downscaled(tmp_path):
    """큰 영상은 샘플링 즉시 축소한다.

    원본 해상도로 들고 있으면 4K 프레임 하나가 20MB라 15장이면 300MB를 넘어
    컨테이너에서 워커가 메모리로 죽는다. 소비자(픽셀 휴리스틱·시간적 일관성·
    딥페이크 모델)가 전부 224×224로 줄여 쓰므로 판정에는 영향이 없다.
    """
    video_path = tmp_path / "big.avi"
    _write_video(video_path, _random_frames(20, size=(1280, 720)), size=(1280, 720))

    capture = cv2.VideoCapture(str(video_path))
    frames = VideoDetector()._sample_frames(capture)
    capture.release()

    assert frames
    for _, frame in frames:
        assert max(frame.shape[:2]) <= vd_module.FRAME_MAX_SIDE


def test_small_frames_are_not_upscaled(tmp_path):
    """이미 작은 영상은 늘리지 않는다. 없는 정보를 만들어내지 않는다."""
    video_path = tmp_path / "small.avi"
    _write_video(video_path, _random_frames(10))

    capture = cv2.VideoCapture(str(video_path))
    frames = VideoDetector()._sample_frames(capture)
    capture.release()

    assert frames
    for _, frame in frames:
        assert frame.shape[:2] == (64, 64)


def test_model_frames_are_classified_concurrently_in_timestamp_order(monkeypatch):
    """프레임 판정을 동시에 실행하되 결과는 타임스탬프 순서를 지킨다.

    순차로 돌면 프레임 8개 × 최대 20초라 gunicorn 타임아웃(30초)을 넘겨 워커가
    중단된다(실측 19.6초). 동시 실행은 완료 순서가 뒤섞이므로 순서를 되돌려야
    frame_highlights의 시각이 맞는다.
    """
    import ai_models.video_detector as vd

    call_count = []

    class _StubClient:
        model = 'stub-model'

        def fake_percent(self, payload):
            call_count.append(payload)
            # 나중에 보낸 프레임이 먼저 끝나도록 지연을 뒤집는다
            time.sleep(0.05 * (4 - len(call_count)))
            return 10.0 * len(call_count)

    monkeypatch.setattr(vd.HFDeepfakeClient, 'from_env', staticmethod(lambda: _StubClient()))

    frames = [(float(i), np.full((64, 64, 3), i * 10, dtype=np.uint8)) for i in range(4)]

    started = time.time()
    results, method, model = VideoDetector()._classify_with_model(frames)
    elapsed = time.time() - started

    assert method == vd.METHOD_MODEL
    assert [r["timestamp_sec"] for r in results] == [0.0, 1.0, 2.0, 3.0]
    # 순차라면 0.15+0.10+0.05+0.0 = 0.30초. 동시 실행이면 가장 느린 하나에 수렴한다.
    assert elapsed < 0.28


def test_model_failure_on_any_frame_still_falls_back_to_heuristic(monkeypatch):
    """한 프레임이라도 실패하면 통째로 휴리스틱으로 돌아간다(기존 동작 유지).

    일부만 모델 판정인 혼합 결과는 해석할 수 없다.
    """
    import ai_models.video_detector as vd

    class _FlakyClient:
        model = 'stub-model'
        seen = 0

        def fake_percent(self, payload):
            _FlakyClient.seen += 1
            if _FlakyClient.seen == 2:
                raise vd.HFInferenceError("추론 API가 HTTP 503를 반환했습니다")
            return 42.0

    monkeypatch.setattr(vd.HFDeepfakeClient, 'from_env', staticmethod(lambda: _FlakyClient()))

    frames = [(float(i), np.full((64, 64, 3), 7, dtype=np.uint8)) for i in range(4)]

    results, method, model = VideoDetector()._classify_with_model(frames)

    assert results is None
    assert method == vd.METHOD_HEURISTIC
    assert model is None


def test_detect_returns_expected_schema_for_real_video(tmp_path):
    """정상 영상은 result.html이 기대하는 스키마(score/details.is_deepfake/frame_highlights)를 반환한다 (FR-01)"""
    video_path = tmp_path / "sample.avi"
    _write_video(video_path, _random_frames(30))

    result = VideoDetector().detect(str(video_path))

    assert "score" in result
    assert isinstance(result["score"], float)
    assert 0.0 <= result["score"] <= 100.0

    details = result["details"]
    assert "is_deepfake" in details
    assert isinstance(details["frame_highlights"], list)
    assert details["sampled_frames"] > 0
    assert "summary" in details

    # VideoService가 캐시에 저장하기 위해 json.dumps(result)를 호출하므로
    # numpy 스칼라(np.float64/np.bool_)가 섞여 있으면 여기서 TypeError가 발생해야 한다.
    json.dumps(result)


def test_detect_flags_static_frames_as_suspicious(tmp_path):
    """프레임 간 변화가 전혀 없는 영상은 시간적 일관성 이상으로 점수가 높아져야 한다 (FR-01)"""
    video_path = tmp_path / "static.avi"
    _write_video(video_path, _static_frames(30))

    result = VideoDetector().detect(str(video_path))

    assert result["details"]["temporal_consistency"] == "프레임 간 변화가 지나치게 적어 보간/합성이 의심됩니다."


def test_detect_samples_at_most_max_frames(tmp_path):
    """긴 영상이어도 처리 시간을 보장하기 위해 최대 샘플 프레임 수를 넘지 않는다 (NFR: 2분 이내)"""
    video_path = tmp_path / "long.avi"
    _write_video(video_path, _random_frames(200))

    result = VideoDetector().detect(str(video_path))

    assert result["details"]["sampled_frames"] <= 16


def test_detect_returns_error_result_for_missing_file(tmp_path):
    """존재하지 않는 파일/URL은 예외 없이 에러 메시지가 담긴 결과를 반환해야 한다 (FR-01)"""
    result = VideoDetector().detect(str(tmp_path / "does-not-exist.mp4"))

    assert result["score"] == 0.0
    assert result["details"]["is_deepfake"] is False
    assert "error" in result["details"]


def test_detect_returns_error_result_for_corrupted_file(tmp_path):
    """디코딩할 수 없는(손상된) 파일은 예외 없이 에러 메시지가 담긴 결과를 반환해야 한다 (FR-01)"""
    video_path = tmp_path / "corrupted.mp4"
    video_path.write_bytes(b"not-a-real-video-file")

    result = VideoDetector().detect(str(video_path))

    assert result["score"] == 0.0
    assert "error" in result["details"]
