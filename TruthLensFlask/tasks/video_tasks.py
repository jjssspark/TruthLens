from ai_models.video_detector import VideoDetector
from tasks.celery_app import celery_app


@celery_app.task(name='tasks.analyze_video')
def analyze_video_task(request_id, video_path_or_url):
    """영상 AI 생성 판별을 비동기로 처리한다 (FR-01, NFR: 2분 이내)"""
    # TODO: 분석 완료 후 backend.models.detection_result.DetectionResult에 저장하고
    #       detection_requests.status를 'done'으로 갱신
    detector = VideoDetector()
    return detector.detect(video_path_or_url)
