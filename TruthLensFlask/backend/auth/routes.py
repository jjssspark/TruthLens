from flask import Blueprint, flash, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from backend.models.database import db, utcnow
from backend.models.mypage import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/auth/email/login', methods=['POST'])
def email_login():
    try:
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user is None or not user.password_hash or not check_password_hash(user.password_hash, password):
            flash('이메일 또는 비밀번호가 올바르지 않습니다.')
            return redirect(url_for('main.login'))

        user.last_login_at = utcnow()
        db.session.commit()

        session['user_id'] = user.id
        return redirect(url_for('main.index'))

    except Exception as e:
        import logging
        logging.exception('email_login 오류')
        # 롤백하지 않으면 세션이 더러운 채로 남아, 같은 워커가 처리하는
        # 다음 요청까지 연쇄로 실패한다(email_signup과 동일 처리).
        db.session.rollback()
        flash('로그인 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.')
        return redirect(url_for('main.login'))


@auth_bp.route('/auth/email/signup', methods=['POST'])
def email_signup():
    try:
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        name = request.form.get('name', '').strip()

        if not email or not password or not name:
            flash('모든 항목을 입력해주세요.')
            return redirect(url_for('main.login'))

        if User.query.filter_by(email=email).first():
            flash('이미 사용 중인 이메일입니다.')
            return redirect(url_for('main.login'))

        user = User(
            email=email,
            name=name,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()

        session['user_id'] = user.id
        return redirect(url_for('main.index'))

    except Exception as e:
        import logging
        logging.exception('email_signup 오류')
        db.session.rollback()
        flash('회원가입 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.')
        return redirect(url_for('main.login'))


@auth_bp.route('/auth/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('main.login'))
