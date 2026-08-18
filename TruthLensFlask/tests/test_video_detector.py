import json
import time
from unittest.mock import patch

import cv2
import numpy as np
import pytest

import ai_models.video_detector as vd_module
from ai_models.hf_deepfake_client import HFDeepfakeClient, HFInferenceError
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
    """프레임 × 모델 호출을 동시에 실행하되 결과는 타임스탬프 순서를 지킨다.

    순차로 돌면 왕복 대기가 호출 수만큼 곱해져 gunicorn 타임아웃에 걸린다
    (실측 8프레임 19.6초). 동시 실행은 완료 순서가 뒤섞이므로 순서를 되돌려야
    frame_highlights의 시각이 맞는다.
    """
    import ai_models.video_detector as vd

    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    monkeypatch.setenv('HF_DEEPFAKE_MODEL', 'stub-model')  # 단일 모델로 지연을 단순화

    calls = []

    def _slow(self, image_bytes):
        calls.append(image_bytes)
        # 나중에 보낸 프레임이 먼저 끝나도록 지연을 뒤집는다
        time.sleep(0.05 * (4 - len(calls)))
        return 10.0 * len(calls)

    frames = [(float(i), np.full((64, 64, 3), i * 10, dtype=np.uint8)) for i in range(4)]

    with patch.object(HFDeepfakeClient, 'fake_percent', autospec=True, side_effect=_slow):
        started = time.time()
        results, method, model = VideoDetector()._classify_with_model(frames)
        elapsed = time.time() - started

    assert method == vd.METHOD_MODEL
    assert [r["timestamp_sec"] for r in results] == [0.0, 1.0, 2.0, 3.0]
    # 순차라면 0.15+0.10+0.05+0.0 = 0.30초. 동시 실행이면 가장 느린 하나에 수렴한다.
    assert elapsed < 0.28


def test_falls_back_to_heuristic_when_every_model_call_fails(monkeypatch):
    """모든 호출이 실패해야 휴리스틱으로 돌아간다.

    일부 실패는 남은 모델로 판정한다 — test_video_model.py 참고.
    """
    import ai_models.video_detector as vd

    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    monkeypatch.delenv('HF_DEEPFAKE_MODEL', raising=False)

    frames = [(float(i), np.full((64, 64, 3), 7, dtype=np.uint8)) for i in range(4)]

    with patch.object(HFDeepfakeClient, 'fake_percent',
                      side_effect=HFInferenceError("추론 API가 HTTP 503를 반환했습니다")):
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


def test_temporal_consistency_does_not_change_score(tmp_path, monkeypatch):
    """시간적 일관성은 점수를 바꾸지 않고 참고 문구로만 남는다.

    임계값(std > mean*1.5 -> 55점)에 근거가 없어 지극히 정상인 12초 클립도
    "합성 경계 의심 55점"을 받았다. 근거 없는 상수가 판정을 흔들면 안 된다.
    """
    video_path = tmp_path / "static.avi"
    _write_video(video_path, _static_frames(30))

    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    monkeypatch.delenv('HF_DEEPFAKE_MODEL', raising=False)

    with patch.object(HFDeepfakeClient, 'fake_percent', return_value=10.0):
        result = VideoDetector().detect(str(video_path))

    # 프레임이 전부 동일해 "보간/합성 의심"이 뜬다(옛 가중치로는 +21점)
    assert "보간/합성이 의심" in result["details"]["temporal_consistency"]
    # 그래도 점수는 모델 판정 그대로다
    assert result["score"] == 10.0


def test_sample_frames_returns_the_requested_count(tmp_path):
    """요청한 만큼 샘플링한다.

    마지막 인덱스(total-1)로 seek하면 읽기가 실패해 한 장씩 모자랐다
    (16 요청 -> 15장, 8 요청 -> 7장).
    """
    video_path = tmp_path / "many.avi"
    _write_video(video_path, _random_frames(120))

    capture = cv2.VideoCapture(str(video_path))
    frames = VideoDetector()._sample_frames(capture)
    capture.release()

    assert len(frames) == vd_module.MAX_SAMPLED_FRAMES


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
