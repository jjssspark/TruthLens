from datetime import datetime

from flask import Blueprint, flash, redirect, request, session, url_for

from backend.auth import oauth
from backend.models.database import db
from backend.models.mypage import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/auth/google')
def google_login():
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/auth/google/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get('userinfo')

        user = User.query.filter_by(email=userinfo['email']).first()
        if user is None:
            user = User(
                email=userinfo['email'],
                name=userinfo['name'],
                google_sub=userinfo['sub'],
            )
            db.session.add(user)

        user.last_login_at = datetime.utcnow()
        db.session.commit()

        session['user_id'] = user.id
        return redirect(url_for('main.index'))

    except Exception:
        return redirect(url_for('main.login'))


@auth_bp.route('/auth/email/login', methods=['POST'])
def email_login():
    try:
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user is None or user.password_hash != password:
            flash('이메일 또는 비밀번호가 올바르지 않습니다.')
            return redirect(url_for('main.login'))

        user.last_login_at = datetime.utcnow()
        db.session.commit()

        session['user_id'] = user.id
        return redirect(url_for('main.index'))

    except Exception as e:
        import logging
        logging.exception('email_login 오류')
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
            password_hash=password,
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
