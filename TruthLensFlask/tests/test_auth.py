from unittest.mock import patch

from backend.models.database import db
from backend.models.mypage import User


def test_user_can_be_created_without_password(app):
    """Google OAuth 유저는 password_hash 없이 생성 가능해야 한다"""
    with app.app_context():
        user = User(email='google@example.com', name='Google User', google_sub='google_sub_123')
        db.session.add(user)
        db.session.commit()

        saved = User.query.filter_by(email='google@example.com').first()
        assert saved is not None
        assert saved.google_sub == 'google_sub_123'
        assert saved.password_hash is None


def test_unauthenticated_request_redirects_to_login(client):
    """미인증 상태로 / 접근 시 /login으로 리디렉션되어야 한다"""
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_login_page_accessible_without_auth(client):
    """/login은 인증 없이 접근 가능해야 한다"""
    response = client.get('/login')
    assert response.status_code == 200


def test_google_callback_creates_new_user(app, client):
    """Google 콜백 시 신규 유저가 DB에 저장되어야 한다"""
    fake_userinfo = {
        'sub': 'google_sub_new',
        'email': 'newuser@gmail.com',
        'name': 'New User',
    }
    with patch('backend.auth.routes.oauth.google.authorize_access_token',
               return_value={'userinfo': fake_userinfo}):
        client.get('/auth/google/callback')

    with app.app_context():
        user = User.query.filter_by(email='newuser@gmail.com').first()
        assert user is not None
        assert user.google_sub == 'google_sub_new'
        assert user.name == 'New User'


def test_google_callback_updates_last_login_for_existing_user(app, client):
    """이미 가입된 유저는 last_login_at이 갱신되어야 한다"""
    with app.app_context():
        user = User(email='existing@gmail.com', name='Existing', google_sub='sub_existing')
        db.session.add(user)
        db.session.commit()

    fake_userinfo = {'sub': 'sub_existing', 'email': 'existing@gmail.com', 'name': 'Existing'}
    with patch('backend.auth.routes.oauth.google.authorize_access_token',
               return_value={'userinfo': fake_userinfo}):
        client.get('/auth/google/callback')

    with app.app_context():
        user = User.query.filter_by(email='existing@gmail.com').first()
        assert user.last_login_at is not None


def test_logout_clears_session(client):
    """로그아웃 시 세션의 user_id가 삭제되어야 한다"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1

    client.get('/auth/logout')

    with client.session_transaction() as sess:
        assert 'user_id' not in sess


def test_email_signup_creates_user_and_redirects(app, client):
    """이메일 회원가입 시 DB에 유저가 생성되고 메인으로 리디렉션된다"""
    response = client.post('/auth/email/signup', data={
        'email': 'newuser@test.com',
        'password': 'securepass123',
        'name': '테스트유저',
    })
    assert response.status_code == 302
    assert '/' in response.headers['Location']

    with app.app_context():
        user = User.query.filter_by(email='newuser@test.com').first()
        assert user is not None
        assert user.name == '테스트유저'
        assert user.password_hash is not None


def test_email_signup_rejects_duplicate_email(app, client):
    """이미 가입된 이메일로 회원가입 시 오류 메시지와 함께 /login으로 돌아온다"""
    
    with app.app_context():
        existing = User(email='dup@test.com', name='기존유저',
                        password_hash='pass')
        db.session.add(existing)
        db.session.commit()

    response = client.post('/auth/email/signup', data={
        'email': 'dup@test.com',
        'password': 'newpass',
        'name': '중복유저',
    })
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_email_login_success_sets_session_and_redirects(app, client):
    """올바른 이메일/비밀번호로 로그인 시 세션에 user_id가 설정되고 메인으로 이동한다"""
    
    with app.app_context():
        user = User(email='login@test.com', name='로그인유저',
                    password_hash='mypassword')
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    response = client.post('/auth/email/login', data={
        'email': 'login@test.com',
        'password': 'mypassword',
    })
    assert response.status_code == 302
    assert '/' in response.headers['Location']

    with client.session_transaction() as sess:
        assert sess.get('user_id') == user_id


def test_email_login_wrong_password_redirects_to_login(app, client):
    """잘못된 비밀번호로 로그인 시 /login으로 돌아온다"""
    
    with app.app_context():
        user = User(email='wrongpw@test.com', name='유저',
                    password_hash='correct')
        db.session.add(user)
        db.session.commit()

    response = client.post('/auth/email/login', data={
        'email': 'wrongpw@test.com',
        'password': 'wrong',
    })
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
