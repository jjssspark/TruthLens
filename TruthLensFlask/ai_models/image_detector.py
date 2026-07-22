import base64
import cv2
import numpy as np
import piexif
from PIL import Image
from ai_models.base_detector import BaseDetector
from ai_models.pixel_heuristics import analyze_pixel_patterns


class ImageDetector(BaseDetector):
    """이미지 AI 생성 판별 모델 (FR-02)"""

    def detect(self, content):
        image = Image.open(content).convert('RGB')

        exif_data = self._analyze_exif(content)
        analysis = self._analyze_pixels(image)
        heatmap_b64 = self._generate_heatmap(image)

        ai_percent = analysis["ai_percent"]
        human_percent = 100.0 - ai_percent
        confidence = analysis["confidence"]

        return {
            "score": ai_percent,
            "details": {
                "heatmap": heatmap_b64,
                "exif": exif_data,
                "ai_percent": ai_percent,
                "human_percent": human_percent,
                "confidence": confidence,
                "summary": self._make_summary(ai_percent, human_percent, confidence, exif_data),
            }
        }

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

    def _make_summary(self, ai_percent, human_percent, confidence, exif_data):
        """결과 요약 문구 생성"""
        if ai_percent >= 70:
            verdict = "AI 제작 가능성이 높습니다"
        elif ai_percent >= 40:
            verdict = "AI와 사람이 혼합된 이미지로 보입니다"
        else:
            verdict = "사람이 제작한 이미지일 가능성이 높습니다"

        exif_note = "EXIF 정보가 없어 촬영 장비·편집 이력 확인은 제한됩니다." if exif_data.get("suspicious") else "EXIF 정상"

        return (
            f"{verdict} | "
            f"AI 개입 {ai_percent}% / 사람 개입 {human_percent}% | "
            f"신뢰도 {confidence}% | "
            f"{exif_note}"
        )