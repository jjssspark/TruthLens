"""영상 딥페이크 모델 연동 테스트.

실제 Hugging Face 토큰 없이 돌아야 하므로 HTTP 계층만 목으로 대체하고,
프레임 샘플링·집계·폴백 로직은 진짜 코드를 통과시킨다.
"""
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from ai_models.hf_deepfake_client import (
    DEFAULT_MODEL,
    HFDeepfakeClient,
    HFInferenceError,
)
from ai_models.video_detector import METHOD_HEURISTIC, METHOD_MODEL, VideoDetector


# --- 클라이언트 ---

def test_from_env_returns_none_without_token(monkeypatch):
    """토큰이 없으면 클라이언트를 만들지 않는다 (휴리스틱 폴백 신호)"""
    monkeypatch.delenv('HF_TOKEN', raising=False)

    assert HFDeepfakeClient.from_env() is None


def test_from_env_uses_default_model(monkeypatch):
    """모델을 지정하지 않으면 기본 모델을 쓴다"""
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    monkeypatch.delenv('HF_DEEPFAKE_MODEL', raising=False)

    assert HFDeepfakeClient.from_env().model == DEFAULT_MODEL


def test_extract_fake_percent_reads_the_fake_label():
    """Fake 라벨의 확률을 0~100으로 환산한다"""
    payload = [{"label": "Fake", "score": 0.9312}, {"label": "Real", "score": 0.0688}]

    assert HFDeepfakeClient._extract_fake_percent(payload) == 93.1


def test_extract_fake_percent_is_case_insensitive():
    """모델마다 라벨 표기가 달라 대소문자를 가리지 않는다"""
    assert HFDeepfakeClient._extract_fake_percent([{"label": "DEEPFAKE", "score": 0.5}]) == 50.0


def test_extract_fake_percent_rejects_unknown_labels():
    """'가짜' 라벨이 없으면 조용히 0을 주지 않고 실패한다"""
    with pytest.raises(HFInferenceError):
        HFDeepfakeClient._extract_fake_percent([{"label": "cat", "score": 0.9}])


# --- 판별기 통합 ---

@pytest.fixture
def video_path(tmp_path):
    """랜덤 프레임 30장짜리 짧은 영상"""
    path = str(tmp_path / "clip.mp4")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'mp4v'), 10.0, (128, 128))
    rng = np.random.default_rng(3)
    for _ in range(30):
        writer.write(rng.integers(0, 256, (128, 128, 3), dtype=np.uint8))
    writer.release()
    return path


def test_falls_back_to_heuristic_without_token(video_path, monkeypatch):
    """토큰이 없으면 휴리스틱으로 판정하고 그 사실을 결과에 남긴다"""
    monkeypatch.delenv('HF_TOKEN', raising=False)

    details = VideoDetector().detect(video_path)["details"]

    assert details["method"] == METHOD_HEURISTIC
    assert details["model"] is None


def test_uses_model_when_token_is_present(video_path, monkeypatch):
    """토큰이 있으면 모델 판정을 주 신호로 쓴다"""
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    monkeypatch.delenv('HF_DEEPFAKE_MODEL', raising=False)

    with patch.object(HFDeepfakeClient, 'fake_percent', return_value=90.0):
        result = VideoDetector().detect(video_path)

    details = result["details"]
    assert details["method"] == METHOD_MODEL
    assert details["model"] == DEFAULT_MODEL
    # 모델 90 * 0.8 = 72 이상. 휴리스틱만 썼다면 이 값이 나올 수 없다.
    assert result["score"] >= 72.0
    assert details["is_deepfake"] is True


def test_falls_back_when_model_call_fails(video_path, monkeypatch):
    """모델 호출이 실패하면 휴리스틱으로 돌아가되 모델을 쓴 척하지 않는다"""
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')

    with patch.object(HFDeepfakeClient, 'fake_percent',
                      side_effect=HFInferenceError("429 rate limit")):
        details = VideoDetector().detect(video_path)["details"]

    assert details["method"] == METHOD_HEURISTIC
    assert details["model"] is None


def test_limits_model_calls_per_video(video_path, monkeypatch):
    """프레임마다 왕복하므로 호출 수에 상한을 둔다"""
    from ai_models.video_detector import MAX_MODEL_FRAMES

    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')

    with patch.object(HFDeepfakeClient, 'fake_percent', return_value=10.0) as mock_call:
        VideoDetector().detect(video_path)

    assert 0 < mock_call.call_count <= MAX_MODEL_FRAMES
