import os

from flask import Blueprint, render_template
from flask import session, redirect, url_for

from backend.models.database import db
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult

main_bp = Blueprint('main', __name__)

# 점수가 이 값 이상이면 AI 생성으로 본다 (image_detector._make_summary와 같은 기준)
AI_SCORE_THRESHOLD = 70


@main_bp.route('/', methods=['GET'])
def index():
    """메인(홈) 화면: 서비스 소개, 판별 유형 선택, 내 최근 분석 이력"""
    user_id = session.get('user_id')

    recent = (
        db.session.query(DetectionRequest, DetectionResult)
        .outerjoin(DetectionResult, DetectionResult.request_id == DetectionRequest.id)
        .filter(DetectionRequest.user_id == user_id)
        .order_by(DetectionRequest.created_at.desc())
        .limit(4)
        .all()
    )

    ai_detected = (
        db.session.query(DetectionResult)
        .join(DetectionRequest, DetectionResult.request_id == DetectionRequest.id)
        .filter(
            DetectionRequest.user_id == user_id,
            DetectionResult.score >= AI_SCORE_THRESHOLD,
        )
        .count()
    )

    return render_template(
        'index.html',
        recent=recent,
        total_scans=DetectionRequest.query.filter_by(user_id=user_id).count(),
        ai_detected=ai_detected,
        # 카드 배지가 실제 설정 상태를 말하게 한다. 키가 없는데 "연동됨"으로
        # 보이거나, 연동해두고 "예정"으로 남아 있으면 둘 다 거짓말이 된다.
        configured_keys={
            'GEMINI_API_KEY': bool(os.getenv('GEMINI_API_KEY')),
            'DEEPSEEK_API_KEY': bool(os.getenv('DEEPSEEK_API_KEY')),
            'HF_TOKEN': bool(os.getenv('HF_TOKEN')),
        },
    )


@main_bp.route('/history', methods=['GET'])
def history():
    """판별 이력: 로그인한 유저의 요청 목록 (최근 20건)"""
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    requests = DetectionRequest.query.filter_by(user_id=session['user_id']).order_by(DetectionRequest.created_at.desc()).limit(20).all()
    return render_template('history.html', requests=requests)

@main_bp.route('/login', methods=['GET'])
def login():
    """로그인 / 회원가입 화면"""
    return render_template('login.html')




