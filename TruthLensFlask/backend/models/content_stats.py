from backend.models.database import db, utcnow


class ContentStats(db.Model):
    """content_stats 테이블: 콘텐츠별 요청 통계 (FR-05, 5.3)"""
    __tablename__ = 'content_stats'

    content_hash = db.Column(db.String(64), primary_key=True)
    request_count = db.Column(db.Integer, default=0)
    last_requested_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
