import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import session

from ai_models.image_detector import ImageDetector
from backend.models.database import db
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult
from backend.services.content_hash_service import hash_file
from backend.services.cache_record_service import (
    record_cache_hit,
    record_cache_miss,
    record_request,
)
from cache.redis_client import get_cached_result, set_cached_result


class ImageService:
    """이미지 AI 생성 판별 비즈니스 로직 (FR-02)"""
    
    def __init__(self):
        self.detector = ImageDetector()

    def analyze(self, file_path):
        """단일 이미지를 분석하고 결과를 DB에 저장한다 (FR-05: 결과 캐싱)"""
        start_time = time.time()

        content_hash = hash_file(file_path)

        # 2. 세션에서 현재 로그인한 유저의 ID를 꺼내옴
        # 로그인하지 않은 유저가 접근할 경우를 대비해 기본값(None 또는 시스템ID) 설정 가능
        user_id = session.get('user_id')
        
        # DB에 요청 기록
        detection_request = DetectionRequest(
            user_id=user_id, # 3. 세션에서 가져온 user_id 저장
            content_hash=content_hash,
            type='image',
            status='pending'
        )
        db.session.add(detection_request)
        db.session.commit()

        record_request(content_hash)

        # 캐시 확인
        cached_json = get_cached_result(content_hash)

        if cached_json is not None:
            # 캐시 히트
            result = json.loads(cached_json)
            is_cached = True
            record_cache_hit(content_hash)
        else:
            # 캐시 미스 → 실제 AI 분석 수행
            result = self.detector.detect(file_path)
            is_cached = False
            record_cache_miss(content_hash)

        # 분석 시간 기록
        elapsed_time = round(time.time() - start_time, 2)
        analyzed_at = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")

        result['details']['analyzed_at'] = analyzed_at
        result['details']['elapsed_time'] = elapsed_time

        # 캐시 미스인 경우에만 Redis에 저장
        if not is_cached:
            set_cached_result(content_hash, json.dumps(result))

        # 최종 결과 DB에 저장
        db.session.add(DetectionResult(
            request_id=detection_request.id,
            score=result['score'],
            detail_json=result['details'],
            cached=is_cached,
        ))
        detection_request.status = 'done'
        db.session.commit()

        return detection_request

    def analyze_multiple(self, file_paths):
        """다중 이미지(최대 10장)를 분석한다"""
        return [self.analyze(path) for path in file_paths]