import os

from flask import Flask, redirect, request, session, url_for
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from backend.models.database import db
from backend.auth import oauth

_PUBLIC_PREFIXES = ('/login', '/auth/', '/static/')


def create_app(config_overrides=None):
    load_dotenv()
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # cloudtype 등 리버스 프록시 뒤에서 https:// URL이 올바르게 생성되도록
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    db.init_app(app)

    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )

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
