from backend.models.cache_metadata import CacheMetadata
from backend.models.content_stats import ContentStats
from backend.models.database import db


def record_cache_miss(content_hash: str) -> None:
    """캐시 미스(최초 분석) 시 cache_metadata 행을 생성한다."""
    if not db.session.get(CacheMetadata, content_hash):
        db.session.add(CacheMetadata(content_hash=content_hash))


def record_cache_hit(content_hash: str) -> None:
    """캐시 히트 시 cache_metadata.hit_count를 1 증가시킨다."""
    meta = db.session.get(CacheMetadata, content_hash)
    if meta:
        meta.hit_count += 1


def record_request(content_hash: str) -> None:
    """요청마다 content_stats.request_count를 1 증가시킨다."""
    stats = db.session.get(ContentStats, content_hash)
    if stats:
        stats.request_count += 1
    else:
        db.session.add(ContentStats(content_hash=content_hash, request_count=1))
