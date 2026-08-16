import redis
from flask import current_app

_redis_client = None

# 판별 로직이나 결과 스키마가 바뀌면 이 값을 올린다. 키가 달라져 옛 캐시가
# 자동으로 무시되고, TTL(24시간)이 끝나면 알아서 사라진다. 이걸 안 올리면
# 같은 파일을 다시 올렸을 때 옛 판별 방식의 점수가 그대로 나온다.
#
# v2: 이미지 판별을 로컬 휴리스틱에서 학습 모델로 교체하고
#     details에 method·model 키를 추가함
#
# 주의: HF_IMAGE_MODEL 등으로 모델만 바꾸는 경우는 이 값이 그대로라 캐시가
# 유지된다. 모델을 교체했다면 이 값도 같이 올려야 한다.
CACHE_SCHEMA_VERSION = 2


def _result_key(content_hash):
    return f"result:v{CACHE_SCHEMA_VERSION}:{content_hash}"


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
        return get_redis_client().get(_result_key(content_hash))
    except redis.RedisError:
        return None


def set_cached_result(content_hash, result_json, ttl=86400):
    """판별 결과를 캐시에 저장한다. 기본 TTL은 24시간(FR-05).

    Redis에 연결할 수 없으면 캐싱을 조용히 건너뛴다.
    """
    try:
        get_redis_client().set(_result_key(content_hash), result_json, ex=ttl)
    except redis.RedisError:
        pass


def increment_request_count(content_hash):
    """동일 콘텐츠에 대한 요청 수를 증가시키고 현재 값을 반환한다 (FR-05).

    1회 이상 누적되면 캐시 활성화 트리거로 사용된다.
    """
    return get_redis_client().incr(f"count:{content_hash}")
