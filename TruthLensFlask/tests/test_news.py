import json
from unittest.mock import patch

from ai_models.news_detector import NewsDetector
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
    """정상 텍스트 입력 시 분석 요청이 생성되어야 한다 (FR-03)"""
    response = logged_in_client.post('/api/v1/detect/news', data={"text": "샘플 뉴스 본문"})
    assert response.status_code == 200
    assert response.get_json()["status"] == "success"


def test_analyze_news_caches_result_on_cache_miss(app):
    """캐시 미스 시 분석을 수행하고 결과를 캐시에 저장한다 (FR-05)"""
    detect_result = {"score": 30.0, "details": {"summary": "news test"}}

    with app.app_context():
        with patch('backend.services.news_service.get_cached_result', return_value=None), \
             patch('backend.services.news_service.set_cached_result') as mock_set, \
             patch.object(NewsDetector, 'detect', return_value=detect_result) as mock_detect:
            detection_request = NewsService().analyze(text="테스트 뉴스 본문")

        mock_detect.assert_called_once_with("테스트 뉴스 본문")
        mock_set.assert_called_once()

        result = DetectionResult.query.filter_by(request_id=detection_request.id).first()
        assert result.cached is False
        assert result.score == 30.0


def test_analyze_news_uses_cached_result_on_cache_hit(app):
    """캐시 히트 시 분석을 건너뛰고 캐시된 결과를 사용한다 (FR-05)"""
    cached_result = {"score": 88.0, "details": {"summary": "cached news"}}

    with app.app_context():
        with patch('backend.services.news_service.get_cached_result',
                   return_value=json.dumps(cached_result)), \
             patch('backend.services.news_service.set_cached_result') as mock_set, \
             patch.object(NewsDetector, 'detect') as mock_detect:
            detection_request = NewsService().analyze(text="테스트 뉴스 본문")

        mock_detect.assert_not_called()
        mock_set.assert_not_called()

        result = DetectionResult.query.filter_by(request_id=detection_request.id).first()
        assert result.cached is True
        assert result.score == 88.0
