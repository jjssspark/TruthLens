import logging
import os

import requests

logger = logging.getLogger(__name__)

# 구 엔드포인트(api-inference.huggingface.co)는 더 이상 응답하지 않는다.
HF_ROUTER_URL = "https://router.huggingface.co/hf-inference/models/{model}"

# 영상용. Siglip 기반 2클래스 분류기. id2label = {0: "Fake", 1: "Real"}
# 얼굴이 조작됐는지를 보는 딥페이크 탐지기라, "AI가 통째로 생성한 이미지인가"와는 다른 문제를 푼다.
DEFAULT_MODEL = "prithivMLmods/deepfake-detector-model-v1"

# 이미지용. AI 생성 이미지 탐지 전용 모델. id2label = {0: "artificial", 1: "real"}
# 위 딥페이크 모델을 정지 이미지에 쓰면 생성 이미지를 진본으로 판정한다(실측 3장 전부 오판).
IMAGE_DEFAULT_MODEL = "haywoodsloan/ai-image-detector-deploy"

# 모델마다 라벨 표기가 달라 소문자로 비교한다
FAKE_LABELS = {"fake", "deepfake", "ai", "ai_generated", "artificial", "spoof"}


class HFInferenceError(RuntimeError):
    """Hugging Face 추론 API 호출 또는 응답 해석에 실패한 경우."""


class HFDeepfakeClient:
    """프레임 한 장의 딥페이크 확률을 Hugging Face 추론 API로 얻는다."""

    def __init__(self, token, model=None, timeout=20):
        self.token = token
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout
        self.url = HF_ROUTER_URL.format(model=self.model)

    @classmethod
    def from_env(cls, model_env="HF_DEEPFAKE_MODEL", default_model=None):
        """HF_TOKEN이 없으면 None을 반환한다.

        호출부는 None일 때 로컬 휴리스틱으로 폴백하되, 어떤 방식을 썼는지
        결과에 반드시 표시해야 한다. 모델을 쓴 척하면 안 된다.

        영상과 이미지는 푸는 문제가 달라 서로 다른 모델을 쓴다.
        호출부가 자기 용도에 맞는 환경변수와 기본 모델을 지정한다.
        """
        token = os.getenv("HF_TOKEN")
        if not token or not token.strip():
            return None
        return cls(token.strip(), os.getenv(model_env) or default_model)

    def fake_percent(self, image_bytes):
        """이미지 한 장이 '가짜'일 확률을 0~100으로 반환한다."""
        try:
            response = requests.post(
                self.url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "image/jpeg",
                },
                data=image_bytes,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise HFInferenceError(f"추론 API 요청 실패: {e}") from e

        if response.status_code != 200:
            raise HFInferenceError(
                f"추론 API가 HTTP {response.status_code}를 반환했습니다: {response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as e:
            raise HFInferenceError(f"추론 API 응답이 JSON이 아닙니다: {response.text[:200]}") from e

        return self._extract_fake_percent(payload)

    @staticmethod
    def _extract_fake_percent(payload):
        if not isinstance(payload, list) or not payload:
            raise HFInferenceError(f"예상과 다른 응답 형식입니다: {str(payload)[:200]}")

        for item in payload:
            if not isinstance(item, dict):
                continue
            if str(item.get("label", "")).strip().lower() in FAKE_LABELS:
                return round(float(item["score"]) * 100, 1)

        labels = [item.get("label") for item in payload if isinstance(item, dict)]
        raise HFInferenceError(f"'가짜' 라벨을 찾지 못했습니다. 받은 라벨: {labels}")
