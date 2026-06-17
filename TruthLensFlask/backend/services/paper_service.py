# 제목 : 논문 AI 생성 판별 및 분석
# 담당자 : 허영주

import json

from flask import session
from ai_models.paper_detector import PaperDetector
from backend.models.database import db
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult
from backend.services.citation_service import CitationService
from backend.services.content_hash_service import hash_file
from backend.models.paper_citation import PaperCitation
from cache.redis_client import get_cached_result, set_cached_result
from backend.services.cache_record_service import record_cache_hit, record_cache_miss, record_request


class PaperService:
    """논문 AI 생성 판별 및 분석 비즈니스 로직 (FR-04)"""

    def __init__(self):
        self.detector = PaperDetector()
        self.citation_service = CitationService()

    def analyze(self, file_path):
        """PDF 논문(최대 50MB, 200페이지)에 대해 AI 판별, 자동 요약, 인용 분석을 수행한다"""
        content_hash = hash_file(file_path)
        user_id = session.get('user_id')
        
        detection_request = DetectionRequest(user_id=user_id, content_hash=content_hash, type='paper', status='pending')
        db.session.add(detection_request)
        db.session.commit()

        record_request(content_hash)

        cached_json = get_cached_result(content_hash)
        if cached_json is not None:
            result = json.loads(cached_json)
            is_cached = True
            record_cache_hit(content_hash)
        else:
            result = self.detector.detect(file_path)
            set_cached_result(content_hash, json.dumps(result))
            is_cached = False
            record_cache_miss(content_hash)

            # 인용 분석은 캐시 미스(최초 분석) 시에만 수행
            citations = result["details"].get("citations", [])
            self.citation_service.analyze_citations(detection_request.id, file_path)

            for citation in citations:
                db.session.add(PaperCitation(
                    request_id=detection_request.id,
                    citation_ref=citation.get("citation_ref"),
                    status=citation.get("status", "detected"),
                    doi=citation.get("doi"),
                    title=citation.get("title"),
                ))

        db.session.add(DetectionResult(
            request_id=detection_request.id,
            score=result['score'],
            detail_json=result['details'],
            cached=is_cached,
        ))
        detection_request.status = 'done'
        db.session.commit()

        return detection_request
