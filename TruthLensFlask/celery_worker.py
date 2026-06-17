from app import create_app
from tasks.celery_app import celery_app

# Flask 설정을 Celery에 반영 (브로커/백엔드 등)
flask_app = create_app()
celery_app.conf.update(flask_app.config)

# tasks 모듈을 import 해야 Celery가 task를 인식한다
from tasks import video_tasks  # noqa: E402,F401

if __name__ == '__main__':
    celery_app.start()
