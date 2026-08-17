import json
from datetime import timedelta
from flask import session

from ai_models.news_detector import NewsDetector
from backend.models.database import db, utcnow
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult
from backend.services.content_hash_service import hash_text_or_url
from backend.services.article_extractor import ArticleExtractor


class NewsService:
    """뉴스 분석 서비스 (단순화 버전)"""

    CACHE_TTL_DAYS = 7

    def __init__(self):
        self.detector = NewsDetector()

    def analyze(self, url=None, text=None):
        user_id = session.get('user_id')
        
        # 1. 본문 확보
        if url:
            try:
                article_text = ArticleExtractor.extract(url)
            except Exception as e:
                raise ValueError(f"기사 추출 실패: {e}")
        else:
            article_text = text

        if not article_text:
            raise ValueError("분석할 내용이 없습니다.")

        # 2. 해시 생성
        content_hash = hash_text_or_url(article_text)

        # 3. DB에서 최근 동일 요청 확인 (7일)
        cached_request = (
            DetectionRequest.query
            .filter(
                DetectionRequest.content_hash == content_hash,
                DetectionRequest.status == "done",
                DetectionRequest.created_at >= utcnow() - timedelta(days=self.CACHE_TTL_DAYS)
            )
            .order_by(DetectionRequest.created_at.desc())
            .first()
        )

        # 4. 캐시 존재하면 재사용
        if cached_request:
            cached_result = DetectionResult.query.filter_by(
                request_id=cached_request.id
            ).first()

            if cached_result:
                return cached_request

        # 5. 새 요청 생성
        detection_request = DetectionRequest(
            user_id=user_id,
            content_hash=content_hash,
            type="news",
            status="pending"
        )
        db.session.add(detection_request)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        # 6. Gemini 분석 (핵심 로직)
        #
        # 실패하면 요청 행이 pending으로 남아 무엇이 어디서 끊겼는지 알 수 없다.
        # failed로 표시하고 예외는 그대로 올려 라우트가 502로 응답하게 한다.
        # (3번의 캐시 조회는 status='done'만 보므로 실패는 재사용되지 않는다)
        try:
            result = self.detector.detect(article_text)
        except Exception:
            detection_request.status = "failed"
            db.session.commit()
            raise

        # 7. 결과 저장
        detection_result = DetectionResult(
            request_id=detection_request.id,
            score=result["score"],
            detail_json=result["details"],
            cached=False
        )

        db.session.add(detection_result)

        detection_request.status = "done"
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return detection_request
