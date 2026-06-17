from flask import Blueprint, jsonify, session
from flask import Blueprint, redirect, render_template, url_for
from backend.services.mypage_service import MypageService

from backend.models.mypage import User

mypage_bp = Blueprint('mypage', __name__)

@mypage_bp.route('/profile', methods=['GET'])
def profile():
    """마이페이지 화면: 프로필 및 스캔 통계"""
    user_info = MypageService().get_user_stats()
    if user_info is None:
        return redirect(url_for('main.login'))

    return render_template('mypage.html', user=user_info)