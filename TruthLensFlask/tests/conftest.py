import pytest

from app import create_app
from backend.models.database import db


@pytest.fixture
def app(tmp_path_factory):
    flask_app = create_app(config_overrides={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        # 테스트가 실제 uploads/를 오염시키지 않도록 격리
        "UPLOAD_FOLDER": str(tmp_path_factory.mktemp("uploads")),
        # TESTING=True면 예외가 재발생해 errorhandler가 동작하지 않는다
        "PROPAGATE_EXCEPTIONS": False,
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
    """인증된 테스트 클라이언트 — 세션에 user_id=1 주입"""
    from backend.models.mypage import User

    with app.app_context():
        user = User(id=1, email='test@example.com', name='Test User')
        db.session.add(user)
        db.session.commit()

    with client.session_transaction() as sess:
        sess['user_id'] = 1

    return client
