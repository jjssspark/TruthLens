from datetime import datetime

from backend.models.database import db


class DetectionRequest(db.Model):
    """detection_requests 테이블: 판별 요청 이력 (5.3)"""
    __tablename__ = 'detection_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    content_hash = db.Column(db.String(64), nullable=False, index=True)
    type = db.Column(db.String(20), nullable=False)  # video, image, news, paper
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, processing, done, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
