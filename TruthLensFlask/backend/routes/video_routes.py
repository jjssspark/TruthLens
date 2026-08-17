from flask import Blueprint, current_app, render_template, request

from backend.api.response import fail, ok
from backend.services.upload_service import UnsupportedFileType, save_upload
from backend.services.video_service import VideoService

video_bp = Blueprint('video', __name__)

ALLOWED_VIDEO_EXT = {'mp4', 'avi', 'mov', 'webm'}


@video_bp.route('/detect/video', methods=['GET'])
def detect_video_page():
    """영상 판별 화면 (FR-01)"""
    return render_template('detect_video.html')


@video_bp.route('/api/v1/detect/video', methods=['POST'])
def detect_video_api():
    """영상 AI 판별 요청: 파일(MP4/AVI/MOV/WEBM) 또는 URL (FR-01)

    앱의 MAX_CONTENT_LENGTH는 500MB(PRD 설계값)지만, 배포 앞단 프록시가 100MB에서
    먼저 거부한다(실측: 96MB 통과, 100MB 413). 그 413은 앱을 거치지 않으므로 여기서
    잡을 수 없고, 화면에서는 templates/detect_video.html이 업로드 전에 막는다.
    """
    url = request.form.get('url')

    if url:
        detection_request = VideoService().analyze(url=url)
    else:
        file = request.files.get('file')
        if not file:
            return fail("INPUT_REQUIRED", "file 또는 url이 필요합니다.", 400)

        try:
            save_path = save_upload(file, ALLOWED_VIDEO_EXT, current_app.config['UPLOAD_FOLDER'])
        except UnsupportedFileType as e:
            return fail("FILE_TYPE_UNSUPPORTED", str(e), 400)

        detection_request = VideoService().analyze(file_path=save_path)

    return ok({"request_id": detection_request.id})
