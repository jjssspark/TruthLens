import os
import uuid

from flask import Flask, g, redirect, request, session, url_for
from flask_compress import Compress
from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from backend.api.response import fail
from backend.logging_config import configure_logging
from backend.models.database import db

# /health·/ready는 외부 모니터링이 찌르는 곳이라 로그인 뒤에 두면 안 된다.
# /diagnostics도 마찬가지다 — 배포가 반영됐는지 확인하려고 여는 곳인데
# 로그인을 요구하면 정작 뭔가 잘못됐을 때 못 본다. 비밀값은 담지 않는다.
# 로그인으로 리다이렉트되면 모니터링이 302/200을 받아 장애를 놓친다.
_PUBLIC_PREFIXES = ('/login', '/auth/', '/static/', '/health', '/ready', '/diagnostics')


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
            # 예외 클래스 이름까지는 응답에 담는다. 이것만으로 어느 계층이
            # 터졌는지(DB·메모리·외부 API) 갈리는데, 클래스 이름에는 내부 값이나
            # 경로가 없다. 메시지와 스택은 계속 로그에만 남긴다.
            return fail(
                "INTERNAL_ERROR",
                f"서버 오류가 발생했습니다. ({type(e).__name__})",
                500,
            )
        return "서버 오류가 발생했습니다.", 500

    # 없는 테이블만 만든다. 예전에는 SQLite일 때만 돌렸는데, 배포 DB를 외부
    # 관리형 Postgres로 옮기면서 모든 백엔드에서 돌게 했다. 그쪽엔 schema.sql을
    # 손으로 실행해 줄 사람이 없다.
    # (블루프린트 등록 이후에 실행해야 모든 모델이 SQLAlchemy 메타데이터에 등록된 상태가 된다)
    with app.app_context():
        try:
            db.create_all()
        except SQLAlchemyError:
            # gunicorn 워커 2개가 동시에 부팅하면 양쪽 다 CREATE TABLE을 시도해
            # 한쪽이 "이미 존재함"으로 터진다. 여기서 죽으면 크래시 루프가 되므로
            # 기동은 계속한다. DB가 정말 안 붙는 경우는 /ready가 503으로 알린다.
            app.logger.warning(
                "테이블 자동 생성 실패 — /ready로 DB 상태를 확인할 것",
                exc_info=True,
                extra={"event": "db.create_all.failed"},
            )

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
