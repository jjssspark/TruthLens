import base64
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from ai_models.hf_deepfake_client import (
    IMAGE_DEFAULT_MODEL,
    IMAGE_ENSEMBLE_MODELS,
    HFDeepfakeClient,
    HFInferenceError,
)
from ai_models.image_detector import (
    METHOD_ENSEMBLE,
    METHOD_HEURISTIC,
    METHOD_MODEL,
    ImageDetector,
)
from ai_models.pixel_heuristics import analyze_pixel_patterns


@pytest.fixture
def detector():
    return ImageDetector()


@pytest.fixture(autouse=True)
def no_hf_token(monkeypatch):
    """단위 테스트가 외부 추론 API를 호출하지 않도록 토큰을 지운다.

    .env에 실제 토큰이 있으면 detect()가 네트워크를 타서 느리고 불안정해진다.
    모델 경로는 아래에서 fake_percent를 patch해 따로 검증한다.
    """
    monkeypatch.delenv("HF_TOKEN", raising=False)


def _solid_image_path(tmp_path, color=(128, 128, 128), name="solid.jpg"):
    path = tmp_path / name
    Image.new("RGB", (256, 256), color).save(path)
    return str(path)


def _noise_image_path(tmp_path, name="noise.jpg"):
    rng = np.random.default_rng(42)
    array = rng.integers(0, 256, size=(256, 256, 3), dtype=np.uint8)
    path = tmp_path / name
    Image.fromarray(array).save(path)
    return str(path)


# --- _make_summary: 판정 문구 임계값 ---

@pytest.mark.parametrize("ai_percent, expected", [
    (100.0, "AI 제작 가능성이 높습니다"),
    (70.0, "AI 제작 가능성이 높습니다"),
    (69.9, "AI와 사람이 혼합된 이미지로 보입니다"),
    (40.0, "AI와 사람이 혼합된 이미지로 보입니다"),
    (39.9, "사람이 제작한 이미지일 가능성이 높습니다"),
    (0.0, "사람이 제작한 이미지일 가능성이 높습니다"),
])
def test_make_summary_verdict_at_thresholds(detector, ai_percent, expected):
    """70/40 경계에서 판정 문구가 정확히 분기한다"""
    summary = detector._make_summary(ai_percent, 100.0 - ai_percent, 90, {"suspicious": False})

    assert expected in summary


def test_make_summary_warns_when_exif_missing(detector):
    """EXIF가 없으면 그 사실을 요약에 명시한다"""
    summary = detector._make_summary(10.0, 90.0, 90, {"suspicious": True})

    assert "EXIF 정보가 없어" in summary


def test_make_summary_reports_normal_exif(detector):
    """EXIF가 정상이면 정상으로 표기한다"""
    summary = detector._make_summary(10.0, 90.0, 90, {"suspicious": False})

    assert "EXIF 정상" in summary


# --- _analyze_exif: 메타데이터 추출과 폴백 ---

def test_analyze_exif_flags_image_without_metadata(detector, tmp_path):
    """EXIF 없는 이미지는 suspicious로 표시된다"""
    result = detector._analyze_exif(_solid_image_path(tmp_path))

    assert result["has_exif"] is False
    assert result["suspicious"] is True


def test_analyze_exif_reads_camera_make_and_model(detector, tmp_path):
    """EXIF가 있으면 카메라 제조사·모델을 추출한다"""
    import piexif

    path = _solid_image_path(tmp_path, name="withexif.jpg")
    exif_bytes = piexif.dump({
        "0th": {
            piexif.ImageIFD.Make: b"Canon",
            piexif.ImageIFD.Model: b"EOS R5",
        },
        "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None,
    })
    piexif.insert(exif_bytes, path)

    result = detector._analyze_exif(path)

    assert result["camera_make"] == "Canon"
    assert result["camera_model"] == "EOS R5"
    assert result["has_exif"] is True
    assert result["suspicious"] is False


def test_analyze_exif_falls_back_on_corrupt_file(detector, tmp_path):
    """손상된 파일이어도 예외를 던지지 않고 폴백한다"""
    path = tmp_path / "corrupt.jpg"
    path.write_bytes(b"not-an-image")

    assert detector._analyze_exif(str(path)) == {"has_exif": False, "suspicious": True}


# --- _generate_heatmap ---

def test_generate_heatmap_returns_decodable_png_data_uri(detector, tmp_path):
    """히트맵은 디코딩 가능한 PNG data URI로 반환된다"""
    image = Image.open(_solid_image_path(tmp_path)).convert("RGB")

    heatmap = detector._generate_heatmap(image)

    assert heatmap.startswith("data:image/png;base64,")
    decoded = base64.b64decode(heatmap.split(",", 1)[1], validate=True)
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


# --- detect: 통합 ---

def test_detect_returns_complete_result_shape(detector, tmp_path):
    """detect()는 score와 8개 상세 필드를 모두 채워 반환한다"""
    result = detector.detect(_noise_image_path(tmp_path))

    assert 0 <= result["score"] <= 100
    assert set(result["details"]) == {
        "heatmap", "exif", "ai_percent", "human_percent", "confidence", "summary",
        "method", "model",
    }


def test_detect_ai_and_human_percent_sum_to_100(detector, tmp_path):
    """AI 개입과 사람 개입 비율의 합은 100이다"""
    details = detector.detect(_solid_image_path(tmp_path))["details"]

    assert details["ai_percent"] + details["human_percent"] == pytest.approx(100.0)


# --- pixel_heuristics: 점수 방향성 ---

def test_solid_image_scores_higher_than_noise_image():
    """노이즈가 없는 단색 이미지가 랜덤 노이즈보다 AI 점수가 높다"""
    solid = np.full((224, 224, 3), 128, dtype=np.uint8)
    noise = np.random.default_rng(0).integers(0, 256, (224, 224, 3), dtype=np.uint8)

    assert analyze_pixel_patterns(solid)["ai_percent"] > analyze_pixel_patterns(noise)["ai_percent"]


def test_solid_image_produces_expected_weighted_score():
    """단색 이미지는 노이즈 90·엣지 80·색상 75의 가중 평균 84.0을 낸다"""
    solid = np.full((224, 224, 3), 128, dtype=np.uint8)

    assert analyze_pixel_patterns(solid)["ai_percent"] == 84.0


def test_agreeing_analyses_yield_high_confidence():
    """세 분석 결과가 일치할수록 신뢰도가 높다"""
    solid = np.full((224, 224, 3), 128, dtype=np.uint8)

    assert analyze_pixel_patterns(solid)["confidence"] == 90


def _graded_noise_image(amplitude, seed=7):
    """중간 회색에 ±amplitude 노이즈를 얹은 이미지"""
    rng = np.random.default_rng(seed)
    base = np.full((224, 224, 3), 128, dtype=np.int16)
    noise = rng.integers(-amplitude, amplitude + 1, (224, 224, 3))
    return np.clip(base + noise, 0, 255).astype(np.uint8)


def test_ai_score_decreases_as_noise_increases():
    """노이즈가 많아질수록 AI 점수가 단조 감소한다

    판별기의 핵심 전제(AI 이미지는 노이즈가 지나치게 균일하다)를 고정한다.
    임계값 구간을 바꾸면 이 성질이 먼저 깨진다.
    """
    scores = [
        analyze_pixel_patterns(_graded_noise_image(amp))["ai_percent"]
        for amp in (0, 3, 8, 15, 30, 60, 127)
    ]

    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[-1]


def test_confidence_varies_with_analysis_agreement():
    """세 분석이 엇갈리는 구간에서는 신뢰도가 낮아진다"""
    confidences = {
        analyze_pixel_patterns(_graded_noise_image(amp))["confidence"]
        for amp in (0, 8, 15, 30)
    }

    # 전부 일치(90)만 나오면 신뢰도 계산이 무의미하다는 뜻
    assert len(confidences) > 1
    assert min(confidences) < 90


# --- 판정 방식: 학습 모델 vs 로컬 휴리스틱 ---

def test_falls_back_to_heuristic_without_token(detector, tmp_path):
    """토큰이 없으면 휴리스틱으로 판정하고 그 사실을 결과에 표시한다"""
    details = detector.detect(_noise_image_path(tmp_path))["details"]

    assert details["method"] == METHOD_HEURISTIC
    assert details["model"] is None
    assert "로컬 휴리스틱" in details["summary"]


def test_uses_model_when_token_is_present(detector, tmp_path, monkeypatch):
    """토큰이 있으면 학습 모델 판정값을 그대로 점수로 쓴다"""
    monkeypatch.setenv("HF_TOKEN", "hf_test-token")
    monkeypatch.delenv("HF_IMAGE_MODEL", raising=False)

    with patch.object(HFDeepfakeClient, "fake_percent", return_value=93.5):
        result = detector.detect(_noise_image_path(tmp_path))

    details = result["details"]
    assert details["method"] == METHOD_ENSEMBLE
    assert result["score"] == 93.5
    assert details["human_percent"] == 6.5
    # 어떤 모델을 썼는지 숨기지 않는다
    assert IMAGE_DEFAULT_MODEL in details["summary"]


def test_model_confidence_grows_with_distance_from_fifty(detector, tmp_path, monkeypatch):
    """모델은 신뢰도를 주지 않으므로 판정이 50%에서 먼 정도로 환산한다"""
    monkeypatch.setenv("HF_TOKEN", "hf_test-token")

    with patch.object(HFDeepfakeClient, "fake_percent", return_value=50.0):
        undecided = detector.detect(_noise_image_path(tmp_path))["details"]["confidence"]
    with patch.object(HFDeepfakeClient, "fake_percent", return_value=100.0):
        certain = detector.detect(_noise_image_path(tmp_path))["details"]["confidence"]

    assert undecided == 0.0
    assert certain == 100.0


def test_falls_back_when_model_call_fails(detector, tmp_path, monkeypatch):
    """모델 호출이 실패하면 휴리스틱으로 돌아가되 모델을 쓴 척하지 않는다"""
    monkeypatch.setenv("HF_TOKEN", "hf_test-token")

    with patch.object(HFDeepfakeClient, "fake_percent",
                      side_effect=HFInferenceError("추론 API가 HTTP 503을 반환했습니다")):
        details = detector.detect(_noise_image_path(tmp_path))["details"]

    assert details["method"] == METHOD_HEURISTIC
    assert details["model"] is None
    assert "로컬 휴리스틱" in details["summary"]


# --- 앙상블: 세 모델 다수결 ---

def _per_model(scores):
    """모델 이름 → 점수 매핑으로 fake_percent를 흉내낸다."""
    def fake(self, image_bytes):
        value = scores[self.model]
        if isinstance(value, Exception):
            raise value
        return value
    return fake


def test_ensemble_uses_median_of_three_models(detector, tmp_path, monkeypatch):
    """세 모델 점수의 중앙값을 쓴다.

    중앙값 >= 70은 '3개 중 2개 이상이 70 이상'과 같다. 즉 다수결이다.
    한 모델이 크게 어긋나도 나머지 둘이 가리키는 쪽으로 판정된다.
    """
    monkeypatch.setenv("HF_TOKEN", "hf_test-token")
    monkeypatch.delenv("HF_IMAGE_MODEL", raising=False)
    a, b, c = IMAGE_ENSEMBLE_MODELS

    with patch.object(HFDeepfakeClient, "fake_percent", autospec=True,
                      side_effect=_per_model({a: 4.5, b: 99.2, c: 100.0})):
        result = detector.detect(_noise_image_path(tmp_path))

    assert result["score"] == 99.2
    assert result["details"]["method"] == METHOD_ENSEMBLE


def test_ensemble_minority_cannot_flip_verdict(detector, tmp_path, monkeypatch):
    """한 모델만 AI라고 해도 나머지 둘이 아니라면 AI로 판정하지 않는다.

    모델 하나가 진짜 사진을 AI로 오판하는 경우를 막는 게 다수결의 목적이다.
    """
    monkeypatch.setenv("HF_TOKEN", "hf_test-token")
    monkeypatch.delenv("HF_IMAGE_MODEL", raising=False)
    a, b, c = IMAGE_ENSEMBLE_MODELS

    with patch.object(HFDeepfakeClient, "fake_percent", autospec=True,
                      side_effect=_per_model({a: 99.9, b: 2.0, c: 1.0})):
        result = detector.detect(_noise_image_path(tmp_path))

    assert result["score"] == 2.0
    assert "사람이 제작한 이미지" in result["details"]["summary"]


def test_ensemble_survives_single_model_failure(detector, tmp_path, monkeypatch):
    """한 모델이 죽어도 나머지로 판정한다. 전체를 휴리스틱으로 떨어뜨리지 않는다."""
    monkeypatch.setenv("HF_TOKEN", "hf_test-token")
    monkeypatch.delenv("HF_IMAGE_MODEL", raising=False)
    a, b, c = IMAGE_ENSEMBLE_MODELS

    with patch.object(HFDeepfakeClient, "fake_percent", autospec=True,
                      side_effect=_per_model({a: HFInferenceError("HTTP 503"), b: 90.0, c: 96.0})):
        details = detector.detect(_noise_image_path(tmp_path))["details"]

    assert details["method"] == METHOD_ENSEMBLE
    assert details["ai_percent"] == 93.0  # 남은 둘의 중앙값(= 평균)


def test_ensemble_falls_back_when_every_model_fails(detector, tmp_path, monkeypatch):
    """전부 실패하면 휴리스틱으로 돌아가되 모델을 쓴 척하지 않는다."""
    monkeypatch.setenv("HF_TOKEN", "hf_test-token")
    monkeypatch.delenv("HF_IMAGE_MODEL", raising=False)
    err = HFInferenceError("HTTP 503")
    a, b, c = IMAGE_ENSEMBLE_MODELS

    with patch.object(HFDeepfakeClient, "fake_percent", autospec=True,
                      side_effect=_per_model({a: err, b: err, c: err})):
        details = detector.detect(_noise_image_path(tmp_path))["details"]

    assert details["method"] == METHOD_HEURISTIC
    assert details["model"] is None
    assert "로컬 휴리스틱" in details["summary"]


def test_env_override_pins_a_single_model(detector, tmp_path, monkeypatch):
    """HF_IMAGE_MODEL을 지정하면 그 모델 하나만 쓴다(앙상블 우회용 탈출구)."""
    monkeypatch.setenv("HF_TOKEN", "hf_test-token")
    monkeypatch.setenv("HF_IMAGE_MODEL", "someone/custom-detector")

    with patch.object(HFDeepfakeClient, "fake_percent", return_value=88.0):
        details = detector.detect(_noise_image_path(tmp_path))["details"]

    assert details["method"] == METHOD_MODEL
    assert details["model"] == "someone/custom-detector"
    assert details["ai_percent"] == 88.0


def test_ensemble_has_three_distinct_models():
    """중앙값이 다수결이 되려면 홀수여야 하고, 서로 다른 모델이어야 의미가 있다."""
    assert len(IMAGE_ENSEMBLE_MODELS) == 3
    assert len(set(IMAGE_ENSEMBLE_MODELS)) == 3
