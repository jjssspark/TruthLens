import redis
from flask import current_app

_redis_client = None


def get_redis_client():
    """Flask 앱 설정을 기반으로 Redis 클라이언트를 생성/반환한다 (싱글톤)"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=current_app.config['REDIS_HOST'],
            port=current_app.config['REDIS_PORT'],
            db=current_app.config['REDIS_DB'],
            decode_responses=True,
        )
    return _redis_client


def get_cached_result(content_hash):
    """콘텐츠 해시에 대한 캐시된 판별 결과를 조회한다 (FR-05).

    Redis에 연결할 수 없으면 캐시 미스(None)로 처리한다.
    """
    try:
        return get_redis_client().get(f"result:{content_hash}")
    except redis.RedisError:
        return None


def set_cached_result(content_hash, result_json, ttl=86400):
    """판별 결과를 캐시에 저장한다. 기본 TTL은 24시간(FR-05).

    Redis에 연결할 수 없으면 캐싱을 조용히 건너뛴다.
    """
    try:
        get_redis_client().set(f"result:{content_hash}", result_json, ex=ttl)
    except redis.RedisError:
        pass


def increment_request_count(content_hash):
    """동일 콘텐츠에 대한 요청 수를 증가시키고 현재 값을 반환한다 (FR-05).

    1회 이상 누적되면 캐시 활성화 트리거로 사용된다.
    """
    return get_redis_client().incr(f"count:{content_hash}")
