"""HF 추론 API 대신 모델을 이 컴퓨터에서 직접 돌린다.

측정 전용이다. 앱(`ai_models/`)은 건드리지 않는다. torch는 컨테이너에 넣기엔
너무 무거워서 `requirements.txt`에 넣지 않는다. 측정할 때만 로컬에 설치한다.

    pip install torch transformers

왜 필요한가: 추론 API는 월간 크레딧이 있다. 정확도를 재려면 영상 하나당
프레임 6장 × 모델 3개 = 18회를 쏘는데, 영상 40개면 720회다. 벤치마킹 한 번에
크레딧이 말라서 서비스가 휴리스틱으로 떨어진다(2026-08-18 실제로 겪음).
로컬 추론은 느리지만 횟수 제한이 없고 서비스에 영향을 주지 않는다.
"""
import io
import logging

from PIL import Image

from ai_models.hf_deepfake_client import FAKE_LABELS, IMAGE_ENSEMBLE_MODELS

logger = logging.getLogger(__name__)


class LocalEnsemble:
    """앙상블 모델을 한 번 올려두고 계속 재사용한다.

    모델 로딩이 호출보다 훨씬 비싸므로 프레임마다 다시 만들면 안 된다.
    """

    def __init__(self, models=IMAGE_ENSEMBLE_MODELS, device=None):
        from transformers import pipeline  # torch가 있을 때만 import 한다

        self.models = tuple(models)
        self.device = device if device is not None else self._pick_device()
        self.pipes = {}
        for name in self.models:
            logger.info("모델 로딩: %s", name)
            self.pipes[name] = pipeline("image-classification", model=name,
                                        device=self.device)

    @staticmethod
    def _pick_device():
        import torch

        # 애플 실리콘은 MPS가 CPU보다 몇 배 빠르다
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return 0
        return -1

    def fake_percents(self, image_bytes):
        """{모델명: 가짜일 확률 0~100}. 라벨을 못 찾은 모델은 빼고 돌려준다."""
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        scores = {}
        for name, pipe in self.pipes.items():
            # top_k=None이어야 모든 라벨의 확률이 온다. 기본값은 상위 몇 개만 준다.
            predictions = pipe(image, top_k=None)
            for item in predictions:
                if str(item["label"]).strip().lower() in FAKE_LABELS:
                    scores[name] = round(float(item["score"]) * 100, 1)
                    break
            else:
                logger.warning("'가짜' 라벨을 못 찾음(%s): %s", name,
                               [p["label"] for p in predictions])
        return scores
