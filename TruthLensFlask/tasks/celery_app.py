from celery import Celery

from config import Config

# Flask 앱과 별도로 동작하는 Celery 인스턴스 (영상 비동기 분석용, 5.1)
celery_app = Celery(
    'truthlens',
    broker=Config.CELERY_BROKER_URL,
    backend=Config.CELERY_RESULT_BACKEND,
)
