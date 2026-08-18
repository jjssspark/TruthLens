import base64
import io
import logging
import os
import statistics

import cv2
import numpy as np
import piexif
from PIL import Image
from ai_models.base_detector import BaseDetector
from ai_models.hf_deepfake_client import IMAGE_ENSEMBLE_MODELS, collect_model_scores
from ai_models.pixel_heuristics import analyze_pixel_patterns

logger = logging.getLogger(__name__)

METHOD_MODEL = "hf-model"
METHOD_ENSEMBLE = "hf-ensemble"
METHOD_HEURISTIC = "local-heuristic"


class ImageDetector(BaseDetector):
    """이미지 AI 생성 판별 모델 (FR-02)"""

    def detect(self, content):
        image = Image.open(content).convert('RGB')

        exif_data = self._analyze_exif(content)
        heatmap_b64 = self._generate_heatmap(image)

        model_result, method, model_name = self._classify_with_model(image)
        if model_result is not None:
            ai_percent = model_result["ai_percent"]
            confidence = model_result["confidence"]
        else:
            analysis = self._analyze_pixels(image)
            ai_percent = analysis["ai_percent"]
            confidence = analysis["confidence"]

        human_percent = round(100.0 - ai_percent, 1)

        return {
            "score": ai_percent,
            "details": {
                "heatmap": heatmap_b64,
                "exif": exif_data,
                "ai_percent": ai_percent,
                "human_percent": human_percent,
                "confidence": confidence,
                # 휴리스틱 결과를 모델 결과처럼 보이게 하면 안 된다.
                "method": method,
                "model": model_name,
                "summary": self._make_summary(ai_percent, human_percent, confidence,
                                              exif_data, method, model_name),
            }
        }

    def _classify_with_model(self, image):
        """학습된 AI 생성 이미지 탐지 모델로 판정한다.

        반환: (결과 dict 또는 None, 사용한 방식, 모델 이름 또는 None)
        토큰이 없거나 호출이 실패하면 None을 돌려 호출부가 휴리스틱으로 폴백하게 한다.
        """
        token = os.getenv("HF_TOKEN")
        if not token or not token.strip():
            return None, METHOD_HEURISTIC, None
        token = token.strip()

        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=92)
        payload = buffer.getvalue()

        # 특정 모델을 지정하면 그것만 쓴다. 앙상블을 우회할 탈출구를 남겨둔다.
        override = os.getenv("HF_IMAGE_MODEL")
        models = (override,) if override else IMAGE_ENSEMBLE_MODELS

        scores = collect_model_scores(token, models, payload)
        if not scores:
            return None, METHOD_HEURISTIC, None

        ai_percent = round(statistics.median(scores.values()), 1)
        logger.info("이미지 판별 모델 판정 완료",
                    extra={"event": "image.model.completed"})
        return (
            {
                "ai_percent": ai_percent,
                # 모델은 신뢰도를 따로 주지 않는다. 판정이 50%에서 멀수록
                # 확신이 크다고 보고 0~100으로 환산한다(영상 판별기와 동일 규칙).
                "confidence": round(abs(ai_percent - 50) * 2, 1),
            },
            METHOD_MODEL if override else METHOD_ENSEMBLE,
            ", ".join(scores),
        )

    def _analyze_exif(self, file_path):
        """EXIF 메타데이터 추출
        
        왜 EXIF를 보냐면: AI 생성 이미지는 카메라 정보 자체가 없어요.
        실제 사진엔 촬영 기기, 날짜, GPS 등이 남아있어요.
        """
        try:
            exif_dict = piexif.load(file_path)
            result = {}

            zeroth = exif_dict.get("0th", {})
            if piexif.ImageIFD.Make in zeroth:
                result["camera_make"] = zeroth[piexif.ImageIFD.Make].decode(errors='ignore')
            if piexif.ImageIFD.Model in zeroth:
                result["camera_model"] = zeroth[piexif.ImageIFD.Model].decode(errors='ignore')
            if piexif.ImageIFD.Software in zeroth:
                result["software"] = zeroth[piexif.ImageIFD.Software].decode(errors='ignore')

            exif = exif_dict.get("Exif", {})
            if piexif.ExifIFD.DateTimeOriginal in exif:
                result["date_taken"] = exif[piexif.ExifIFD.DateTimeOriginal].decode(errors='ignore')

            result["has_exif"] = len(result) > 0
            result["suspicious"] = not result["has_exif"]
            return result

        except Exception:
            return {"has_exif": False, "suspicious": True}

    def _analyze_pixels(self, image):
        """픽셀 패턴으로 AI/사람 개입 비율 계산 (ai_models.pixel_heuristics 공용 로직)"""
        img_array = np.array(image.resize((224, 224)))
        return analyze_pixel_patterns(img_array)

    def _generate_heatmap(self, image):
        """조작 의심 영역 히트맵 생성 후 base64 반환"""
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        img_cv = cv2.resize(img_cv, (224, 224))

        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        laplacian = np.uint8(np.absolute(laplacian))
        heatmap = cv2.applyColorMap(laplacian, cv2.COLORMAP_JET)

        _, buffer = cv2.imencode('.png', heatmap)
        b64 = base64.b64encode(buffer).decode('utf-8')
        return f"data:image/png;base64,{b64}"

    def _make_summary(self, ai_percent, human_percent, confidence, exif_data,
                      method=METHOD_HEURISTIC, model_name=None):
        """결과 요약 문구 생성"""
        if ai_percent >= 70:
            verdict = "AI 제작 가능성이 높습니다"
        elif ai_percent >= 40:
            verdict = "AI와 사람이 혼합된 이미지로 보입니다"
        else:
            verdict = "사람이 제작한 이미지일 가능성이 높습니다"

        exif_note = "EXIF 정보가 없어 촬영 장비·편집 이력 확인은 제한됩니다." if exif_data.get("suspicious") else "EXIF 정상"

        # 어떤 방식으로 판정했는지 숨기지 않는다. 휴리스틱 폴백은 정확도가 크게 떨어진다.
        if method == METHOD_ENSEMBLE:
            count = len(model_name.split(", ")) if model_name else 0
            method_note = f"판정 방식: 학습 모델 {count}개 다수결({model_name})"
        elif method == METHOD_MODEL:
            method_note = f"판정 방식: 학습 모델({model_name})"
        else:
            method_note = "판정 방식: 로컬 휴리스틱(모델 호출 불가) — 정확도가 제한적입니다"

        return (
            f"{verdict} | "
            f"AI 개입 {ai_percent}% / 사람 개입 {human_percent}% | "
            f"신뢰도 {confidence}% | "
            f"{exif_note} | "
            f"{method_note}"
        )