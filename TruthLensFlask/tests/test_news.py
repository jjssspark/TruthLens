from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ai_models.news_detector import NewsAnalysisError, NewsDetector
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult
from backend.services.news_service import NewsService


def test_detect_news_page(logged_in_client):
    """뉴스 판별 화면(/detect/news)이 정상적으로 렌더링되는지 확인한다 (FR-03)"""
    response = logged_in_client.get('/detect/news')
    assert response.status_code == 200


def test_detect_news_api_requires_url_or_text(logged_in_client):
    """url/text가 없으면 400을 반환해야 한다 (FR-03)"""
    response = logged_in_client.post('/api/v1/detect/news', data={})
    assert response.status_code == 400


def test_detect_news_api_rejects_too_long_text(logged_in_client):
    """텍스트가 10,000자를 초과하면 400을 반환해야 한다 (FR-03)"""
    response = logged_in_client.post('/api/v1/detect/news', data={"text": "a" * 10001})
    assert response.status_code == 400


def test_detect_news_api_accepts_text(logged_in_client):
    """정상 텍스트 입력 시 분석 요청이 생성되어야 한다 (FR-03)

    판별기를 목으로 막는다. 막지 않으면 테스트가 실제 Gemini를 호출해 네트워크와
    API 키에 의존하게 된다.
    """
    detect_result = {"score": 12.0, "details": {"logic": "근거가 충분합니다."}}

    with patch.object(NewsDetector, 'detect', return_value=detect_result):
        response = logged_in_client.post('/api/v1/detect/news', data={"text": "샘플 뉴스 본문"})

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_news_detector_raises_when_api_call_fails():
    """Gemini 호출이 실패하면 결과를 지어내지 않고 예외를 올린다.

    실패를 score 0짜리 정상 결과로 둔갑시키면 라우트의 502 분기가 영영 실행되지
    않고, 실패가 status='done'으로 저장돼 7일간 캐시된다.
    """
    detector = NewsDetector()
    upstream = RuntimeError("403 ACCESS_TOKEN_SCOPE_INSUFFICIENT generativelanguage.googleapis.com")

    with patch.object(detector.model, 'generate_content', side_effect=upstream):
        with pytest.raises(NewsAnalysisError):
            detector.detect("본문")


def test_news_detector_raises_when_response_is_not_json():
    """응답이 JSON이 아니면 ValueError가 아니라 분석 실패로 올린다.

    ValueError로 올리면 라우트가 사용자 입력 오류(400 INPUT_REQUIRED)로 오분류한다.
    """
    detector = NewsDetector()

    with patch.object(detector.model, 'generate_content',
                      return_value=SimpleNamespace(text="이건 JSON이 아닙니다")):
        with pytest.raises(NewsAnalysisError):
            detector.detect("본문")


def test_news_analysis_failure_returns_502_and_is_not_saved_as_done(app, logged_in_client):
    """분석 실패는 502로 응답하고, 성공 이력으로 저장하지 않는다."""
    upstream = NewsAnalysisError(
        "403 Request had insufficient authentication scopes. "
        "reason: ACCESS_TOKEN_SCOPE_INSUFFICIENT"
    )

    with patch.object(NewsDetector, 'detect', side_effect=upstream):
        response = logged_in_client.post('/api/v1/detect/news', data={'text': '본문'})

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "ANALYSIS_FAILED"
    # 구글 내부 사정을 사용자 화면에 흘리지 않는다
    assert "ACCESS_TOKEN_SCOPE_INSUFFICIENT" not in response.get_data(as_text=True)

    with app.app_context():
        assert DetectionRequest.query.filter_by(type='news', status='done').count() == 0


def test_news_requires_url_or_text(logged_in_client):
    """url·text 둘 다 없으면 INPUT_REQUIRED로 400을 반환한다"""
    body = logged_in_client.post('/api/v1/detect/news', data={}).get_json()

    assert body["success"] is False
    assert body["error"]["code"] == "INPUT_REQUIRED"


def test_news_rejects_text_over_limit(logged_in_client):
    """10,000자를 넘는 text는 TEXT_TOO_LONG으로 거부한다"""
    body = logged_in_client.post(
        '/api/v1/detect/news', data={'text': 'ㄱ' * 10001}
    ).get_json()

    assert body["error"]["code"] == "TEXT_TOO_LONG"


def test_news_upstream_failure_does_not_leak_exception(logged_in_client):
    """외부 분석 실패 시 예외 메시지를 응답에 노출하지 않는다"""
    with patch.object(NewsService, 'analyze', side_effect=RuntimeError("api-key=SECRET123")):
        response = logged_in_client.post('/api/v1/detect/news', data={'text': '본문'})

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "ANALYSIS_FAILED"
    assert "SECRET123" not in response.get_data(as_text=True)


def test_analyze_news_caches_result_on_cache_miss(app):
    """캐시 미스(최초 요청) 시 분석을 수행하고 결과를 DB에 저장한다 (FR-05)"""
    detect_result = {"score": 30.0, "details": {"summary": "news test"}}

    with app.test_request_context():
        with patch.object(NewsDetector, 'detect', return_value=detect_result) as mock_detect:
            detection_request = NewsService().analyze(text="테스트 뉴스 본문")

        mock_detect.assert_called_once_with("테스트 뉴스 본문")

        result = DetectionResult.query.filter_by(request_id=detection_request.id).first()
        assert result.cached is False
        assert result.score == 30.0


def test_analyze_news_uses_cached_result_on_cache_hit(app):
    """7일 이내 동일 콘텐츠 재요청 시 분석을 건너뛰고 기존 요청을 재사용한다 (FR-05)"""
    detect_result = {"score": 88.0, "details": {"summary": "news test"}}

    with app.test_request_context():
        with patch.object(NewsDetector, 'detect', return_value=detect_result) as mock_detect:
            first_request = NewsService().analyze(text="동일한 뉴스 본문")

        with patch.object(NewsDetector, 'detect') as mock_detect_second:
            second_request = NewsService().analyze(text="동일한 뉴스 본문")

        mock_detect_second.assert_not_called()
        assert second_request.id == first_request.id
