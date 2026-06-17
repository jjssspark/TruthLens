from ai_models.base_detector import BaseDetector


class VideoDetector(BaseDetector):
    """영상 AI 생성 판별 모델 (FR-01)"""

    def detect(self, content):
        # TODO: Transformers/OpenCV/PyTorch 기반 딥페이크 탐지 모델 연동
        return {
            "score": 0.0,
            "details": {
                "is_deepfake": False,
                "frame_highlights": [],  # 의심 구간 타임스탬프 목록
                "summary": "분석 모델이 아직 연동되지 않았습니다.",
            },
        }
