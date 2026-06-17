from datetime import datetime

from backend.models.database import db


class CacheMetadata(db.Model):
    """cache_metadata 테이블: 캐시 활성화 이력 (FR-05, 5.3)"""
    __tablename__ = 'cache_metadata'

    content_hash = db.Column(db.String(64), primary_key=True)
    ttl = db.Column(db.Integer, default=86400)  # 기본 24시간(초), 트렌딩 콘텐츠는 자동 연장
    hit_count = db.Column(db.Integer, default=0)
    activated_at = db.Column(db.DateTime, default=datetime.utcnow)
