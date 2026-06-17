import os

from flask import Blueprint, current_app, jsonify, render_template, request

from backend.services.video_service import VideoService

video_bp = Blueprint('video', __name__)


@video_bp.route('/detect/video', methods=['GET'])
def detect_video_page():
    """영상 판별 화면 (FR-01)"""
    return render_template('detect_video.html')


@video_bp.route('/api/v1/detect/video', methods=['POST'])
def detect_video_api():
    """영상 AI 판별 요청: 파일(MP4/AVI/MOV/WEBM, 최대 500MB) 또는 URL (FR-01)"""
    url = request.form.get('url')

    if url:
        detection_request = VideoService().analyze(url=url)
    else:
        file = request.files.get('file')
        if not file:
            return jsonify({"status": "error", "data": {"message": "file 또는 url이 필요합니다."}}), 400

        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename)
        file.save(save_path)
        detection_request = VideoService().analyze(file_path=save_path)

    return jsonify({
        "status": "success",
        "data": {"request_id": detection_request.id},
        "meta": {},
    })
