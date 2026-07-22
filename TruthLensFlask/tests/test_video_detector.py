import json

import cv2
import numpy as np
import pytest

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
