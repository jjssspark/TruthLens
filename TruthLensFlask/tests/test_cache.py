import cache.redis_client as redis_client_module
from cache.redis_client import get_cached_result, set_cached_result


def test_get_cached_result_returns_none_when_redis_unreachable(app):
    """Redis에 연결할 수 없으면 캐시 미스(None)로 처리한다 (FR-05)"""
    redis_client_module._redis_client = None
    with app.app_context():
        app.config['REDIS_HOST'] = 'localhost'
        app.config['REDIS_PORT'] = 1  # 아무 것도 listen하지 않는 포트

        assert get_cached_result('content-hash') is None


def test_set_cached_result_does_not_raise_when_redis_unreachable(app):
    """Redis에 연결할 수 없으면 캐싱을 조용히 건너뛴다 (FR-05)"""
    redis_client_module._redis_client = None
    with app.app_context():
        app.config['REDIS_HOST'] = 'localhost'
        app.config['REDIS_PORT'] = 1  # 아무 것도 listen하지 않는 포트

        set_cached_result('content-hash', '{"score": 1}')


def test_result_key_includes_schema_version():
    """판별 로직이 바뀌면 키가 달라져야 옛 결과가 재사용되지 않는다.

    버전이 빠지면 같은 파일을 다시 올렸을 때 옛 판별 방식의 점수가 나온다.
    """
    key = redis_client_module._result_key('abc123')

    assert key == f'result:v{redis_client_module.CACHE_SCHEMA_VERSION}:abc123'
    assert key != 'result:abc123'
