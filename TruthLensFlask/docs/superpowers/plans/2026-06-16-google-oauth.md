# Google OAuth 로그인 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Google OAuth 2.0로 로그인하고 `session['user_id']`에 저장, 미인증 시 모든 라우트가 /login으로 리디렉션

**Architecture:** Authlib로 Google OAuth 흐름 처리, Flask `before_request`로 인증 게이트 구현, 팀원의 `session['user_id']` 방식 유지. Flask-Login 미사용.

**Tech Stack:** Authlib, Flask session, backend/models/mypage.py의 User 모델

---

## 파일 구조

| 작업 | 파일 |
|---|---|
| 신규 생성 | `backend/auth/__init__.py` |
| 신규 생성 | `backend/auth/routes.py` |
| 신규 생성 | `tests/test_auth.py` |
| 수정 | `requirements.txt` |
| 수정 | `config.py` |
| 수정 | `backend/models/mypage.py` (google_sub 추가, password_hash nullable) |
| 수정 | `schema.sql` |
| 수정 | `app.py` (OAuth 초기화, before_request, auth/mypage 블루프린트 등록) |
| 수정 | `templates/login.html` (버튼 href) |
| 수정 | `tests/conftest.py` (인증 fixture 추가) |
| 수정 | `tests/test_image.py`, `test_news.py`, `test_paper.py`, `test_video.py` (logged_in_client 사용) |

---

### Task 1: 의존성 및 설정 추가

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py`

- [ ] **Step 1: requirements.txt에 Authlib 추가**

```
flask
flask-sqlalchemy
pymysql
python-dotenv
gunicorn
celery
redis
opencv-python-headless
numpy
piexif
Pillow
Authlib
```

- [ ] **Step 2: config.py에 Google OAuth 설정 추가**

`DEBUG = ...` 줄 아래에 추가:

```python
# Google OAuth 설정
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
```

- [ ] **Step 3: 패키지 설치 확인**

```bash
pip install Authlib
python -c "import authlib; print(authlib.__version__)"
```

Expected: 버전 번호 출력 (예: 1.3.x)

---

### Task 2: User 모델 수정 (google_sub 추가, password_hash nullable)

**Files:**
- Modify: `backend/models/mypage.py`
- Modify: `schema.sql`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_auth.py` 신규 생성:

```python
from backend.models.mypage import User


def test_user_can_be_created_without_password(app):
    """Google OAuth 유저는 password_hash 없이 생성 가능해야 한다"""
    with app.app_context():
        user = User(email='google@example.com', name='Google User', google_sub='google_sub_123')
        from backend.models.database import db
        db.session.add(user)
        db.session.commit()

        saved = User.query.filter_by(email='google@example.com').first()
        assert saved is not None
        assert saved.google_sub == 'google_sub_123'
        assert saved.password_hash is None
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_auth.py::test_user_can_be_created_without_password -v
```

Expected: FAIL (`password_hash` NOT NULL 제약 또는 `google_sub` 컬럼 없음)

- [ ] **Step 3: User 모델 수정**

`backend/models/mypage.py`의 `password_hash`와 `google_sub` 줄을 수정:

```python
password_hash = db.Column(db.String(255), nullable=True)   # Google OAuth는 비밀번호 없음
google_sub    = db.Column(db.String(100), nullable=True)   # Google 고유 유저 ID
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_auth.py::test_user_can_be_created_without_password -v
```

Expected: PASS

- [ ] **Step 5: schema.sql 동기화**

`schema.sql`의 users 테이블에서 `password_hash`를 nullable로, `google_sub` 컬럼 추가:

```sql
password_hash       VARCHAR(255)    NULL,
google_sub          VARCHAR(100)    NULL                       COMMENT 'Google OAuth 고유 ID',
```

- [ ] **Step 6: 커밋**

```bash
git add backend/models/mypage.py schema.sql tests/test_auth.py requirements.txt config.py
git commit -m "feat: add google_sub to User model, make password_hash nullable"
```

---

### Task 3: Google OAuth 블루프린트 구현

**Files:**
- Create: `backend/auth/__init__.py`
- Create: `backend/auth/routes.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_auth.py`에 추가:

```python
from unittest.mock import patch


def test_google_callback_creates_new_user(app, client):
    """Google 콜백 시 신규 유저가 DB에 저장되어야 한다"""
    fake_userinfo = {
        'sub': 'google_sub_new',
        'email': 'newuser@gmail.com',
        'name': 'New User',
    }
    with patch('backend.auth.routes.oauth.google.authorize_access_token',
               return_value={'userinfo': fake_userinfo}):
        response = client.get('/auth/google/callback')

    with app.app_context():
        from backend.models.mypage import User
        user = User.query.filter_by(email='newuser@gmail.com').first()
        assert user is not None
        assert user.google_sub == 'google_sub_new'
        assert user.name == 'New User'


def test_google_callback_updates_last_login_for_existing_user(app, client):
    """이미 가입된 유저는 last_login_at이 갱신되어야 한다"""
    from backend.models.mypage import User
    from backend.models.database import db
    from datetime import datetime

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


def test_logout_clears_session(app, client):
    """로그아웃 시 세션의 user_id가 삭제되어야 한다"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1

    client.get('/auth/logout')

    with client.session_transaction() as sess:
        assert 'user_id' not in sess
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_auth.py -v -k "callback or logout"
```

Expected: FAIL (라우트 없음)

- [ ] **Step 3: backend/auth/__init__.py 생성**

```python
from authlib.integrations.flask_client import OAuth

oauth = OAuth()
```

- [ ] **Step 4: backend/auth/routes.py 생성**

```python
from datetime import datetime

from flask import Blueprint, redirect, session, url_for
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


@auth_bp.route('/auth/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('main.login'))
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

(Task 4의 app.py 등록 후 실행 가능하므로 Task 4 완료 후 재실행)

---

### Task 4: app.py에 OAuth 초기화 및 블루프린트 등록

**Files:**
- Modify: `app.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_auth.py`에 추가:

```python
def test_unauthenticated_request_redirects_to_login(client):
    """미인증 상태로 / 접근 시 /login으로 리디렉션되어야 한다"""
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_auth.py::test_unauthenticated_request_redirects_to_login -v
```

Expected: FAIL (현재 200 반환)

- [ ] **Step 3: app.py 수정**

```python
import os
from flask import Flask, redirect, request, session, url_for
from config import Config
from backend.models.database import db
from backend.auth import oauth
from dotenv import load_dotenv

# 인증 없이 접근 가능한 경로
_PUBLIC_PREFIXES = ('/login', '/auth/', '/static/')


def create_app(config_overrides=None):
    load_dotenv()
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)

    # Authlib OAuth 초기화
    oauth.init_app(app)
    oauth.register(
        name='google',
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )

    # 인증 게이트: 비공개 경로에 미인증 접근 시 /login 리디렉션
    @app.before_request
    def require_login():
        if any(request.path.startswith(p) for p in _PUBLIC_PREFIXES):
            return
        if not session.get('user_id'):
            return redirect(url_for('main.login'))

    register_blueprints(app)
    return app


def register_blueprints(app):
    from backend.routes.main_routes import main_bp
    from backend.routes.video_routes import video_bp
    from backend.routes.image_routes import image_bp
    from backend.routes.news_routes import news_bp
    from backend.routes.paper_routes import paper_bp
    from backend.routes.result_routes import result_bp
    from backend.routes.mypage_routes import mypage_bp
    from backend.auth.routes import auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(image_bp)
    app.register_blueprint(news_bp)
    app.register_blueprint(paper_bp)
    app.register_blueprint(result_bp)
    app.register_blueprint(mypage_bp)
    app.register_blueprint(auth_bp)


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=app.config['DEBUG'])
```

- [ ] **Step 4: 테스트 실행 — Task 3 + Task 4 통합 확인**

```bash
python -m pytest tests/test_auth.py -v
```

Expected: 모든 test_auth.py 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/auth/__init__.py backend/auth/routes.py app.py
git commit -m "feat: add Google OAuth blueprint and before_request auth gate"
```

---

### Task 5: 기존 테스트 픽스처 업데이트

기존 라우트 테스트들이 `before_request` 인증 게이트로 인해 302를 반환하므로 수정 필요.

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_image.py`, `tests/test_news.py`, `tests/test_paper.py`, `tests/test_video.py`

- [ ] **Step 1: 기존 테스트 실패 확인**

```bash
python -m pytest tests/ -v --ignore=tests/test_auth.py 2>&1 | grep FAILED
```

Expected: 여러 테스트가 302 리디렉션으로 FAIL

- [ ] **Step 2: conftest.py에 logged_in_client 픽스처 추가**

```python
import pytest
from app import create_app
from backend.models.database import db


@pytest.fixture
def app():
    flask_app = create_app(config_overrides={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "GOOGLE_CLIENT_ID": "test-client-id",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        "WTF_CSRF_ENABLED": False,
    })

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in_client(app, client):
    """인증된 테스트 클라이언트 — 세션에 user_id=1을 주입"""
    with app.app_context():
        from backend.models.mypage import User
        user = User(id=1, email='test@example.com', name='Test User', google_sub='test_sub')
        db.session.add(user)
        db.session.commit()

    with client.session_transaction() as sess:
        sess['user_id'] = 1

    return client
```

- [ ] **Step 3: test_image.py — client를 logged_in_client로 교체**

```python
def test_detect_image_page(logged_in_client):
    response = logged_in_client.get('/detect/image')
    assert response.status_code == 200


def test_detect_image_api_requires_file(logged_in_client):
    response = logged_in_client.post('/api/v1/detect/image', data={})
    assert response.status_code == 400
```

- [ ] **Step 4: test_news.py — client를 logged_in_client로 교체**

```python
def test_detect_news_page(logged_in_client):
    response = logged_in_client.get('/detect/news')
    assert response.status_code == 200


def test_detect_news_api_requires_url_or_text(logged_in_client):
    response = logged_in_client.post('/api/v1/detect/news', data={})
    assert response.status_code == 400


def test_detect_news_api_rejects_too_long_text(logged_in_client):
    response = logged_in_client.post('/api/v1/detect/news', data={'text': 'a' * 10001})
    assert response.status_code == 400


def test_detect_news_api_accepts_text(logged_in_client):
    response = logged_in_client.post('/api/v1/detect/news', data={'text': '뉴스 내용'})
    assert response.status_code == 200
```

- [ ] **Step 5: test_paper.py — client를 logged_in_client로 교체**

파일 내 `client` 파라미터를 모두 `logged_in_client`로 변경.

- [ ] **Step 6: test_video.py — client를 logged_in_client로 교체**

파일 내 `client` 파라미터를 모두 `logged_in_client`로 변경.

- [ ] **Step 7: 전체 테스트 통과 확인**

```bash
python -m pytest tests/ -v
```

Expected: 전체 PASS (test_cache.py의 앱 픽스처는 app_context 내에서만 동작하므로 영향 없음)

- [ ] **Step 8: 커밋**

```bash
git add tests/conftest.py tests/test_image.py tests/test_news.py tests/test_paper.py tests/test_video.py
git commit -m "test: update fixtures with logged_in_client for auth gate"
```

---

### Task 6: 로그인 페이지 버튼 연결

**Files:**
- Modify: `templates/login.html`

- [ ] **Step 1: 로그인 버튼 href 변경**

`login.html`에서 `onclick="handleLogin()"` 버튼 두 곳을 `/auth/google`로 변경:

```html
<!-- 기존 -->
<button onclick="handleLogin()" ...>

<!-- 변경 후 -->
<a href="/auth/google" ...>
```

정확히 수정할 두 곳 (174번째 줄 근처):

```html
<a href="/auth/google"
   class="w-full h-14 bg-white border border-outline-variant flex items-center justify-center gap-3 rounded-xl shadow-sm active:scale-[0.98] transition-all hover:bg-surface-container-low">
    <!-- ... 내부 내용 동일 ... -->
</a>
```

그리고 188번째 줄 근처 두 번째 버튼도 동일하게 `<a href="/auth/google">` 태그로 변경.

- [ ] **Step 2: handleLogin() JavaScript 함수 제거**

`login.html` 하단 `<script>` 태그 내 `handleLogin()` 함수 및 관련 alert 코드 삭제.

- [ ] **Step 3: 전체 테스트 최종 확인**

```bash
python -m pytest tests/ -v
```

Expected: 전체 PASS

- [ ] **Step 4: 최종 커밋**

```bash
git add templates/login.html
git commit -m "feat: wire login button to /auth/google"
```
