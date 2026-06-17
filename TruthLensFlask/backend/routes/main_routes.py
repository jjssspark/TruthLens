from flask import Blueprint, render_template
from flask import session, redirect, url_for

from backend.models.detection_request import DetectionRequest

main_bp = Blueprint('main', __name__)


@main_bp.route('/', methods=['GET'])
def index():
    """메인(홈) 화면: 서비스 소개, 판별 유형 선택"""
    return render_template('index.html')


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




