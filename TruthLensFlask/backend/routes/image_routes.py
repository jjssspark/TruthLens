from flask import Blueprint, current_app, render_template, request

from backend.api.response import fail, ok
from backend.services.image_service import ImageService
from backend.services.upload_service import UnsupportedFileType, save_upload

image_bp = Blueprint('image', __name__)

# 임시 제한. 여러 장을 한 요청에서 순차로 분석하면 gunicorn 기본 타임아웃(30초)을
# 넘겨 워커가 중단되고, 응답이 JSON이 아니게 되어 프론트가 파싱에 실패한다.
# 판별을 동시 실행으로 고치면 PRD 설계값인 10으로 되돌린다.
MAX_IMAGES = 1
ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'webp', 'gif'}


@image_bp.route('/detect/image', methods=['GET'])
def detect_image_page():
    """이미지 판별 화면 (FR-02)"""
    return render_template('detect_image.html')


@image_bp.route('/api/v1/detect/image', methods=['POST'])
def detect_image_api():
    """이미지 AI 판별 요청 (FR-02). 현재는 한 번에 1장만 받는다 — MAX_IMAGES 주석 참고."""
    files = request.files.getlist('file')
    if not files:
        return fail("FILE_REQUIRED", "file이 필요합니다.", 400)

    # 초과분을 조용히 잘라내면 사용자는 전부 분석된 줄 안다. 명시적으로 거절한다.
    if len(files) > MAX_IMAGES:
        return fail(
            "IMAGE_COUNT_EXCEEDED",
            f"한 번에 {MAX_IMAGES}장까지만 분석할 수 있습니다.",
            400,
        )

    try:
        save_paths = [
            save_upload(file, ALLOWED_IMAGE_EXT, current_app.config['UPLOAD_FOLDER'])
            for file in files
        ]
    except UnsupportedFileType as e:
        return fail("FILE_TYPE_UNSUPPORTED", str(e), 400)

    results = ImageService().analyze_multiple(save_paths)

    return ok({"request_ids": [r.id for r in results]})
