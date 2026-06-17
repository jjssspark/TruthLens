from flask import Blueprint, jsonify, session
from datetime import datetime
from backend.models.database import db

mypage_bp = Blueprint('mypage', __name__)

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=True)
    google_sub    = db.Column(db.String(100), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(30), nullable=False, default='free')          # 'pro', 'enterprise' 등
    trust_score = db.Column(db.Float, nullable=False, default=0)            # 신뢰 수준 데이터
    scan_count = db.Column(db.Integer, nullable=False, default=0)           # 분석 통계 scans 수
    accuracy = db.Column(db.Float, nullable=False, default=0)               # 탐지 정확도 %
    next_payment_date = db.Column(db.Date, nullable=True)                   # 결제 예정일
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)