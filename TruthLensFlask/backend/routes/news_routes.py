from flask import Blueprint, jsonify, render_template, request

from backend.services.news_service import NewsService

news_bp = Blueprint('news', __name__)

MAX_TEXT_LENGTH = 10000


@news_bp.route('/detect/news', methods=['GET'])
def detect_news_page():
    """뉴스 판별 화면 (FR-03)"""
    return render_template('detect_news.html')


@news_bp.route('/api/v1/detect/news', methods=['POST'])
def detect_news_api():
    """뉴스 AI 생성/가짜뉴스 판별 요청: URL 또는 텍스트 (최대 10,000자, FR-03)"""
    url = request.form.get('url')
    text = request.form.get('text')

    if not url and not text:
        return jsonify({"status": "error", "data": {"message": "url 또는 text가 필요합니다."}}), 400

    if text and len(text) > MAX_TEXT_LENGTH:
        return jsonify({"status": "error", "data": {"message": f"text는 {MAX_TEXT_LENGTH}자를 초과할 수 없습니다."}}), 400

    detection_request = NewsService().analyze(url=url, text=text)

    
    return jsonify({
        "status": "success",
        "data": {
            "request_id": detection_request.id
        },
        "meta":{}    
    })
