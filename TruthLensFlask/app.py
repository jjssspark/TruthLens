import os
import uuid

from flask import Flask, g, redirect, request, session, url_for
from flask_compress import Compress
from dotenv import load_dotenv
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from backend.api.response import fail
from backend.logging_config import configure_logging
from backend.models.database import db

# /health·/ready는 외부 모니터링이 찌르는 곳이라 로그인 뒤에 두면 안 된다.
# 로그인으로 리다이렉트되면 모니터링이 302/200을 받아 장애를 놓친다.
_PUBLIC_PREFIXES = ('/login', '/auth/', '/static/', '/health', '/ready')


def create_app(config_overrides=None):
    load_dotenv()
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    configure_logging(app)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # cloudtype 등 리버스 프록시 뒤에서 https:// URL이 올바르게 생성되도록
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # 배포 환경이 gzip을 걸어주지 않아 CSS·HTML이 원본 크기 그대로 나간다. 앱에서 직접 압축한다.
    Compress(app)

    db.init_app(app)

    @app.before_request
    def assign_trace_id():
        g.trace_id = request.headers.get('X-Request-Id') or uuid.uuid4().hex

    @app.before_request
    def require_login():
        if any(request.path.startswith(p) for p in _PUBLIC_PREFIXES):
            return
        if not session.get('user_id'):
            return redirect(url_for('main.login'))

    register_blueprints(app)

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        # 404·405 등은 Flask 기본 처리를 그대로 쓴다
        if isinstance(e, HTTPException):
            return e

        app.logger.exception("처리되지 않은 예외", extra={"event": "request.failed"})

        if request.path.startswith('/api/'):
            return fail("INTERNAL_ERROR", "서버 오류가 발생했습니다.", 500)
        return "서버 오류가 발생했습니다.", 500

    # 로컬 개발용 SQLite를 쓸 때는 schema.sql을 수동 실행할 필요 없이 테이블을 자동 생성한다
    # (블루프린트 등록 이후에 실행해야 모든 모델이 SQLAlchemy 메타데이터에 등록된 상태가 된다)
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        with app.app_context():
            db.create_all()

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
