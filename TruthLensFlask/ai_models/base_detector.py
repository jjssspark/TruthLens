from abc import ABC, abstractmethod


class BaseDetector(ABC):
    """모든 AI 판별 모델이 따라야 하는 공통 인터페이스 (4.3 모델 인터페이스 추상화)"""

    @abstractmethod
    def detect(self, content):
        """
        콘텐츠를 분석하여 판별 결과를 반환한다.

        :param content: 분석 대상 (파일 경로, URL, 텍스트 등 도메인별로 다름)
        :return: {
            "score": float,   # AI 생성 가능성 신뢰 점수 (0~100)
            "details": dict,  # 도메인별 세부 분석 결과
        }
        """
        raise NotImplementedError
