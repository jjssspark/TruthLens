import base64
import cv2
import numpy as np
import piexif
from PIL import Image
from ai_models.base_detector import BaseDetector


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
        """픽셀 패턴으로 AI/사람 개입 비율 계산
        
        분석 항목 3가지를 각각 점수 내서 종합해요.
        
        1. 노이즈 균일도: AI 이미지는 노이즈가 지나치게 균일
        2. 엣지 패턴: AI 이미지는 경계선이 너무 매끄러움
        3. 색상 분포: AI 이미지는 색상이 과도하게 균형잡혀 있음
        """
        img_array = np.array(image.resize((224, 224)))

        # --- 분석 1: 노이즈 균일도 ---
        noise_scores = []
        for ch in range(3):
            ch_data = img_array[:, :, ch].astype(float)
            lap = cv2.Laplacian(ch_data, cv2.CV_64F)
            noise_scores.append(np.var(lap))
        avg_noise = np.mean(noise_scores)

        # 노이즈 분산이 낮을수록 AI 가능성 높음
        if avg_noise < 100:
            noise_ai_score = 90
        elif avg_noise < 300:
            noise_ai_score = 70
        elif avg_noise < 600:
            noise_ai_score = 45
        elif avg_noise < 1000:
            noise_ai_score = 25
        else:
            noise_ai_score = 10

        # --- 분석 2: 엣지 매끄러움 ---
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size

        # 엣지가 너무 적거나 너무 균일하면 AI 의심
        if edge_density < 0.03:
            edge_ai_score = 80
        elif edge_density < 0.08:
            edge_ai_score = 55
        elif edge_density < 0.15:
            edge_ai_score = 35
        else:
            edge_ai_score = 15

        # --- 분석 3: 색상 분포 균일도 ---
        color_stds = [np.std(img_array[:, :, ch]) for ch in range(3)]
        avg_color_std = np.mean(color_stds)

        # 색상 표준편차가 지나치게 균일하면 AI 의심
        if avg_color_std < 30:
            color_ai_score = 75
        elif avg_color_std < 50:
            color_ai_score = 50
        elif avg_color_std < 70:
            color_ai_score = 30
        else:
            color_ai_score = 15

        # --- 종합 점수 (가중 평균) ---
        # 노이즈가 가장 신뢰도 높아서 비중 높게
        ai_percent = round(
            noise_ai_score * 0.5 +
            edge_ai_score * 0.3 +
            color_ai_score * 0.2,
            1
        )

        # 신뢰도: 3개 분석이 일치할수록 높음
        scores = [noise_ai_score, edge_ai_score, color_ai_score]
        score_std = np.std(scores)
        if score_std < 10:
            confidence = 90
        elif score_std < 20:
            confidence = 75
        elif score_std < 30:
            confidence = 55
        else:
            confidence = 35

        return {
            "ai_percent": ai_percent,
            "confidence": confidence,
        }

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