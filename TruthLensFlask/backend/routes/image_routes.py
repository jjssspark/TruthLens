import os

from flask import Blueprint, current_app, jsonify, render_template, request

from backend.services.image_service import ImageService

image_bp = Blueprint('image', __name__)

MAX_IMAGES = 10


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

    save_paths = []
    for file in files[:MAX_IMAGES]:
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename)
        file.save(save_path)
        save_paths.append(save_path)

    results = ImageService().analyze_multiple(save_paths)

    return jsonify({
        "status": "success",
        "data": {"request_ids": [r.id for r in results]},
        "meta": {},
    })
