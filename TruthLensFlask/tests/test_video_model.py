"""영상 딥페이크 모델 연동 테스트.

실제 Hugging Face 토큰 없이 돌아야 하므로 HTTP 계층만 목으로 대체하고,
프레임 샘플링·집계·폴백 로직은 진짜 코드를 통과시킨다.
"""
import statistics
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from ai_models.hf_deepfake_client import (
    IMAGE_ENSEMBLE_MODELS,
    HFDeepfakeClient,
    HFInferenceError,
)
from ai_models.video_detector import (
    MAX_MODEL_FRAMES,
    METHOD_ENSEMBLE,
    METHOD_HEURISTIC,
    METHOD_MODEL,
    VideoDetector,
)


# --- 클라이언트 ---

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
    assert "휴리스틱" in details["summary"]


def test_uses_model_when_token_is_present(video_path, monkeypatch):
    """토큰이 있으면 모델 판정을 주 신호로 쓴다"""
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    monkeypatch.delenv('HF_DEEPFAKE_MODEL', raising=False)

    with patch.object(HFDeepfakeClient, 'fake_percent', return_value=90.0):
        result = VideoDetector().detect(video_path)

    details = result["details"]
    assert details["method"] == METHOD_ENSEMBLE
    assert details["model"] == ", ".join(IMAGE_ENSEMBLE_MODELS)
    # 휴리스틱만 썼다면 이 값이 나올 수 없다.
    assert result["score"] == 90.0
    assert details["is_deepfake"] is True
    # 요약문도 방식을 정확히 말해야 한다. details.method만 맞고 문구가 어긋나면
    # 요약만 읽는 사용자는 여전히 잘못된 정보를 받는다.
    assert IMAGE_ENSEMBLE_MODELS[0] in details["summary"]
    assert "휴리스틱" not in details["summary"]


def test_falls_back_when_model_call_fails(video_path, monkeypatch):
    """모델 호출이 실패하면 휴리스틱으로 돌아가되 모델을 쓴 척하지 않는다"""
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')

    with patch.object(HFDeepfakeClient, 'fake_percent',
                      side_effect=HFInferenceError("429 rate limit")):
        details = VideoDetector().detect(video_path)["details"]

    assert details["method"] == METHOD_HEURISTIC
    assert details["model"] is None


def test_limits_model_calls_per_video(video_path, monkeypatch):
    """프레임 × 모델마다 왕복하므로 호출 수에 상한을 둔다"""
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    monkeypatch.delenv('HF_DEEPFAKE_MODEL', raising=False)

    with patch.object(HFDeepfakeClient, 'fake_percent', return_value=10.0) as mock_call:
        VideoDetector().detect(video_path)

    assert 0 < mock_call.call_count <= MAX_MODEL_FRAMES * len(IMAGE_ENSEMBLE_MODELS)


# --- 앙상블 판정 ---

def _ensemble_stub(score_by_model):
    """모델 이름별로 정해진 점수를 돌려주는 fake_percent 대역.

    autospec=True로 패치해야 self가 넘어와 어느 모델의 호출인지 구분할 수 있다.
    """
    def _call(self, image_bytes):
        value = score_by_model[self.model]
        if isinstance(value, Exception):
            raise value
        return value
    return _call


def test_frame_score_is_median_of_ensemble_models(video_path, monkeypatch):
    """프레임 한 장의 점수는 3개 모델의 중앙값이다.

    얼굴 조작 탐지기 하나에만 의존하면 진본 프레임에도 36~89%가 나온다(실측 6장).
    이미지 판별에서 검증된 3모델 중앙값(정확도 85.7%→94.3%)을 프레임에도 쓴다.
    """
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    monkeypatch.delenv('HF_DEEPFAKE_MODEL', raising=False)
    a, b, c = IMAGE_ENSEMBLE_MODELS

    with patch.object(HFDeepfakeClient, 'fake_percent', autospec=True,
                      side_effect=_ensemble_stub({a: 0.0, b: 100.0, c: 4.0})):
        result = VideoDetector().detect(video_path)

    assert result["score"] == 4.0
    assert result["details"]["method"] == METHOD_ENSEMBLE


def test_video_score_is_median_across_frames(monkeypatch):
    """영상 점수는 프레임 점수들의 중앙값이다.

    평균을 쓰면 프레임 하나가 튈 때 전체가 끌려간다.
    """
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    monkeypatch.delenv('HF_DEEPFAKE_MODEL', raising=False)

    # 프레임·모델을 동시에 쏘므로 호출 순서로는 프레임을 구분할 수 없다.
    # 프레임마다 밝기를 다르게 주고, 스텁이 받은 이미지를 보고 점수를 정한다.
    frames = [(float(i), np.full((64, 64, 3), i * 50, dtype=np.uint8)) for i in range(5)]

    def _by_brightness(payload):
        decoded = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
        # 마지막 프레임(밝기 200)만 튀는 점수를 준다
        return 99.0 if decoded[0][0][0] > 175 else 10.0

    with patch.object(HFDeepfakeClient, 'fake_percent', side_effect=_by_brightness):
        results, method, model = VideoDetector()._classify_with_model(frames)

    assert [r["ai_percent"] for r in results] == [10.0, 10.0, 10.0, 10.0, 99.0]
    assert statistics.median(r["ai_percent"] for r in results) == 10.0


def test_partial_model_failure_still_judges_with_remaining(video_path, monkeypatch):
    """앙상블 중 하나가 죽어도 나머지로 판정한다.

    3개 중 1개 실패는 남은 2개로 판단할 수 있다. 통째로 휴리스틱으로
    되돌리면 멀쩡한 모델 2개를 버리게 된다.
    """
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    monkeypatch.delenv('HF_DEEPFAKE_MODEL', raising=False)
    a, b, c = IMAGE_ENSEMBLE_MODELS

    with patch.object(HFDeepfakeClient, 'fake_percent', autospec=True,
                      side_effect=_ensemble_stub(
                          {a: 20.0, b: HFInferenceError("503"), c: 30.0})):
        details = VideoDetector().detect(video_path)["details"]

    assert details["method"] == METHOD_ENSEMBLE
    assert a in details["model"] and c in details["model"]
    assert b not in details["model"]


def test_single_model_override_skips_ensemble(video_path, monkeypatch):
    """모델을 지정하면 그것만 쓴다. 앙상블을 우회할 탈출구를 남긴다."""
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    monkeypatch.setenv('HF_DEEPFAKE_MODEL', 'someone/custom-model')

    with patch.object(HFDeepfakeClient, 'fake_percent', return_value=77.0) as call:
        details = VideoDetector().detect(video_path)["details"]

    assert details["method"] == METHOD_MODEL
    assert details["model"] == 'someone/custom-model'
    assert call.call_count <= MAX_MODEL_FRAMES
