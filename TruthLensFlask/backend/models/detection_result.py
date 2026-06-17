from datetime import datetime

from backend.models.database import db


class DetectionResult(db.Model):
    """detection_results 테이블: 판별 결과 (5.3)"""
    __tablename__ = 'detection_results'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('detection_requests.id'), nullable=False)
    score = db.Column(db.Float, nullable=False)  # AI 생성 가능성 신뢰 점수 (0~100)
    detail_json = db.Column(db.JSON, nullable=True)  # 도메인별 세부 분석 결과
    cached = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
