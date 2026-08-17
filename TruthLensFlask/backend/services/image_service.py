import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
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

logger = logging.getLogger(__name__)


class ImageService:
    """이미지 AI 생성 판별 비즈니스 로직 (FR-02)"""
    
    def __init__(self):
        self.detector = ImageDetector()

    def analyze(self, file_path, precomputed=None, detect_seconds=0.0):
        """단일 이미지를 분석하고 결과를 DB에 저장한다 (FR-05: 결과 캐싱)

        precomputed: 이미 끝난 detect() 결과. 다중 업로드에서 판별만 미리 동시에
        돌려두고 넘긴다. detect_seconds는 그때 걸린 시간이며, 화면에 표시되는
        소요 시간이 실제보다 짧게 나오지 않도록 더해준다.
        """
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
            logger.info("이미지 캐시 히트", extra={"event": "image.cache.hit"})
        else:
            # 캐시 미스 → 실제 AI 분석 수행
            result = precomputed if precomputed is not None else self.detector.detect(file_path)
            is_cached = False
            record_cache_miss(content_hash)
            logger.info("이미지 캐시 미스", extra={"event": "image.cache.miss"})

        # 분석 시간 기록
        elapsed_time = round(time.time() - start_time + detect_seconds, 2)
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

        logger.info(
            "이미지 판별 완료",
            extra={
                "event": "image.analyze.completed",
                "durationMs": round(elapsed_time * 1000),
            },
        )

        return detection_request

    def analyze_multiple(self, file_paths):
        """다중 이미지(최대 10장)를 분석한다.

        판별만 동시에 돌린다. 순차로 하면 장수만큼 시간이 곱해지는데, 1장이
        HF 모델 응답을 최대 20초 기다리므로 4장이면 gunicorn 타임아웃을 넘겨
        워커가 중단된다. 그러면 응답이 JSON이 아니게 되어 프론트가 파싱에 실패한다.

        analyze() 전체를 스레드로 넘기면 안 된다. flask.session은 요청 컨텍스트에,
        db.session은 스레드에 묶여 있어 워커 스레드에는 둘 다 없다. 그래서 외부
        의존이 없는 detect()만 떼어내 동시에 돌리고, DB 기록은 호출 스레드에서 한다.
        """
        if len(file_paths) < 2:
            return [self.analyze(path) for path in file_paths]

        # 캐시에 있는 것까지 판별을 돌리면 캐시를 둔 의미가 없다(FR-05: 히트 시 1초 이내).
        misses = [path for path in file_paths if get_cached_result(hash_file(path)) is None]

        detected = {}
        if misses:
            started = time.time()
            with ThreadPoolExecutor(max_workers=len(misses)) as pool:
                for path, result in zip(misses, pool.map(self.detector.detect, misses)):
                    detected[path] = result
            # 동시에 돌았으므로 각 장이 실제로 기다린 시간은 전체 소요와 같다고 본다.
            detect_seconds = time.time() - started
        else:
            detect_seconds = 0.0

        return [
            self.analyze(path, detected.get(path),
                         detect_seconds if path in detected else 0.0)
            for path in file_paths
        ]