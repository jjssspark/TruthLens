from werkzeug.security import generate_password_hash

from backend.models.database import db
from backend.models.mypage import User


def test_unauthenticated_request_redirects_to_login(client):
    """미인증 상태로 / 접근 시 /login으로 리디렉션되어야 한다"""
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_login_page_accessible_without_auth(client):
    """/login은 인증 없이 접근 가능해야 한다"""
    response = client.get('/login')
    assert response.status_code == 200


def test_email_login_updates_last_login_at(app, client):
    """로그인 성공 시 last_login_at이 갱신된다"""
    with app.app_context():
        user = User(email='lastlogin@test.com', name='유저',
                    password_hash=generate_password_hash('pw12345'))
        db.session.add(user)
        db.session.commit()
        assert user.last_login_at is None

    client.post('/auth/email/login', data={
        'email': 'lastlogin@test.com',
        'password': 'pw12345',
    })

    with app.app_context():
        assert User.query.filter_by(email='lastlogin@test.com').first().last_login_at is not None


def test_google_login_route_is_gone(client):
    """구글 OAuth 라우트가 완전히 제거되었다"""
    assert client.get('/auth/google').status_code == 404
    assert client.get('/auth/google/callback').status_code == 404


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
                    password_hash=generate_password_hash('mypassword'))
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
                    password_hash=generate_password_hash('correct'))
        db.session.add(user)
        db.session.commit()

    response = client.post('/auth/email/login', data={
        'email': 'wrongpw@test.com',
        'password': 'wrong',
    })
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
