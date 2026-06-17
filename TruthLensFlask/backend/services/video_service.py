import json

from ai_models.video_detector import VideoDetector
from flask import session
from backend.models.database import db
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult
from backend.services.content_hash_service import hash_file, hash_text_or_url
from cache.redis_client import get_cached_result, set_cached_result
from backend.services.cache_record_service import record_cache_hit, record_cache_miss, record_request


class VideoService:
    """영상 AI 생성 판별 비즈니스 로직 (FR-01)"""

    def __init__(self):
        self.detector = VideoDetector()

    def analyze(self, file_path=None, url=None):
        """
        영상을 분석하고 결과를 DB에 저장한다.

        :param file_path: 업로드된 영상 파일 경로
        :param url: 영상 URL (YouTube, Vimeo, 직접 링크 등)
        :return: 생성된 DetectionRequest 인스턴스
        """
        content_hash = hash_file(file_path) if file_path else hash_text_or_url(url)
        user_id = session.get('user_id')
        
        detection_request = DetectionRequest(user_id=user_id, content_hash=content_hash, type='video', status='pending')
        db.session.add(detection_request)
        db.session.commit()

        record_request(content_hash)

        # TODO: 실제로는 tasks.video_tasks.analyze_video_task로 비동기 처리 (NFR: 2분 이내)
        cached_json = get_cached_result(content_hash)
        if cached_json is not None:
            result = json.loads(cached_json)
            is_cached = True
            record_cache_hit(content_hash)
        else:
            result = self.detector.detect(file_path or url)
            set_cached_result(content_hash, json.dumps(result))
            is_cached = False
            record_cache_miss(content_hash)

        db.session.add(DetectionResult(
            request_id=detection_request.id,
            score=result['score'],
            detail_json=result['details'],
            cached=is_cached,
        ))
        detection_request.status = 'done'
        db.session.commit()

        return detection_request
