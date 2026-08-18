import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)

# 구 엔드포인트(api-inference.huggingface.co)는 더 이상 응답하지 않는다.
HF_ROUTER_URL = "https://router.huggingface.co/hf-inference/models/{model}"

# AI 생성 이미지 탐지 전용 모델. id2label = {0: "artificial", 1: "real"}
IMAGE_DEFAULT_MODEL = "haywoodsloan/ai-image-detector-deploy"

# 이미지와 영상 프레임 모두 이 셋의 중앙값을 쓴다(= 2표 이상 다수결).
#
# 영상은 원래 얼굴 조작 탐지기(prithivMLmods/deepfake-detector-model-v1)를 썼는데,
# 그 모델은 "얼굴이 조작됐는가"를 푸는 물건이라 풍경·사물 프레임에는 쓸 수 없다.
# 진짜 사진 6장 실측에서 36.3 / 43.6 / 52.3 / 79.8 / 86.1 / 89.2%를 뱉었다.
# 같은 사진들에 아래 앙상블 중앙값은 0.3 / 0.4 / 0.4 / 0.8 / 7.1 / 99.8%였다.
#
# 실측 35장(AI 19 / 진본 16)에서 세 모델이 서로 반대로 틀렸다.
#   haywoodsloan  AI 14/19, 오탐 0/16   ← 놓치지만 진짜 사진을 의심하지 않음
#   Organika      AI 19/19, 오탐 5/16   ← 다 잡지만 진짜 사진을 의심함
#   Ateeqq        AI 19/19, 오탐 5/16
# 중앙값을 쓰면 AI 19/19, 오탐 2/16 (정확도 85.7% → 94.3%).
# 홀수여야 중앙값이 다수결이 된다. 모델을 추가할 거면 5개로 늘린다.
IMAGE_ENSEMBLE_MODELS = (
    IMAGE_DEFAULT_MODEL,
    "Organika/sdxl-detector",
    "Ateeqq/ai-vs-human-image-detector",
)

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


def collect_model_scores(token, models, payload, timeout=20):
    """모델들을 동시에 호출해 성공한 것만 {모델명: 점수}로 모은다.

    하나가 죽어도 나머지로 판정한다. 순차 호출하면 대기 시간이 모델 수만큼
    늘어나므로 동시에 쏜다.

    timeout은 호출 하나의 상한이다. 영상은 프레임 수만큼 곱해지므로 더 짧게 준다.
    """
    scores = {}
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {
            pool.submit(HFDeepfakeClient(token, model, timeout).fake_percent, payload): model
            for model in models
        }
        for future in as_completed(futures):
            model = futures[future]
            try:
                scores[model] = future.result()
            except HFInferenceError as e:
                logger.warning("판별 모델 호출 실패(%s): %s", model, e,
                               extra={"event": "hf.model.failed"})
    # dict는 삽입 순서를 유지하는데 완료 순서라 매번 달라진다. 요약 문구가
    # 호출마다 바뀌지 않도록 지정한 순서로 되돌린다.
    return {model: scores[model] for model in models if model in scores}
