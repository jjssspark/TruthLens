from flask import Blueprint, current_app, render_template, request

from backend.api.response import fail, ok
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
        return fail("INPUT_REQUIRED", "url 또는 text가 필요합니다.", 400)

    if text and len(text) > MAX_TEXT_LENGTH:
        return fail("TEXT_TOO_LONG", f"text는 {MAX_TEXT_LENGTH}자를 초과할 수 없습니다.", 400)

    try:
        detection_request = NewsService().analyze(url=url, text=text)
    except ValueError as e:
        # 기사 추출 실패, 본문 없음 등 사용자 입력에서 비롯된 오류
        return fail("INPUT_REQUIRED", str(e), 400)
    except Exception:
        # 외부 API 장애는 우리 서버 버그가 아니므로 502로 구분한다.
        # 예외 내용은 응답이 아니라 서버 로그에만 남긴다.
        current_app.logger.exception("뉴스 분석 실패", extra={"event": "news.analyze.failed"})
        return fail("ANALYSIS_FAILED", "뉴스 분석에 실패했습니다. 잠시 후 다시 시도해주세요.", 502)

    return ok({"request_id": detection_request.id})
