from flask import Blueprint, current_app, jsonify, render_template, request

from backend.services.image_service import ImageService
from backend.services.upload_service import UnsupportedFileType, save_upload

image_bp = Blueprint('image', __name__)

MAX_IMAGES = 10
ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'webp', 'gif'}


@image_bp.route('/detect/image', methods=['GET'])
def detect_image_page():
    """이미지 판별 화면 (FR-02)"""
    return render_template('detect_image.html')


@image_bp.route('/api/v1/detect/image', methods=['POST'])
def detect_image_api():
    """이미지 AI 판별 요청: 다중 업로드 지원 (최대 10장, FR-02)"""
    files = request.files.getlist('file')
    if not files:
        return jsonify({"status": "error", "data": {"message": "file이 필요합니다."}}), 400

    try:
        save_paths = [
            save_upload(file, ALLOWED_IMAGE_EXT, current_app.config['UPLOAD_FOLDER'])
            for file in files[:MAX_IMAGES]
        ]
    except UnsupportedFileType as e:
        return jsonify({"status": "error", "data": {"message": str(e)}}), 400

    results = ImageService().analyze_multiple(save_paths)

    return jsonify({
        "status": "success",
        "data": {"request_ids": [r.id for r in results]},
        "meta": {},
    })
