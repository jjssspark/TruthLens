import json
from unittest.mock import patch, MagicMock

from ai_models.paper_detector import PaperDetector
from backend.models.detection_result import DetectionResult
from backend.services.paper_service import PaperService


def test_detect_paper_page(logged_in_client):
    """논문 판별 화면(/detect/paper)이 정상적으로 렌더링되는지 확인한다 (FR-04)"""
    response = logged_in_client.get('/detect/paper')
    assert response.status_code == 200


def test_detect_paper_api_requires_file(logged_in_client):
    """file(PDF)이 없으면 400을 반환해야 한다 (FR-04)"""
    response = logged_in_client.post('/api/v1/detect/paper', data={})
    assert response.status_code == 400


def test_get_citations_for_unknown_request_returns_empty_list(logged_in_client):
    """존재하지 않는 request_id에 대해서도 빈 목록을 반환한다 (FR-04)"""
    response = logged_in_client.get('/api/v1/paper/999/citations')
    assert response.status_code == 200
    assert response.get_json()["data"]["citations"] == []


def test_analyze_paper_caches_result_on_cache_miss(app, tmp_path):
    """캐시 미스 시 분석 및 인용 분석을 수행하고 결과를 캐시에 저장한다 (FR-05)"""
    file_path = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"fake-pdf-bytes")
    detect_result = {"score": 65.0, "details": {"summary": "paper test", "citations": []}}

    with app.app_context():
        with patch('backend.services.paper_service.get_cached_result', return_value=None), \
             patch('backend.services.paper_service.set_cached_result') as mock_set, \
             patch.object(PaperDetector, 'detect', return_value=detect_result) as mock_detect, \
             patch('backend.services.paper_service.CitationService.analyze_citations') as mock_cite:
            detection_request = PaperService().analyze(file_path)

        mock_detect.assert_called_once_with(file_path)
        mock_set.assert_called_once()
        mock_cite.assert_called_once()

        result = DetectionResult.query.filter_by(request_id=detection_request.id).first()
        assert result.cached is False
        assert result.score == 65.0


def test_analyze_paper_uses_cached_result_on_cache_hit(app, tmp_path):
    """캐시 히트 시 분석과 인용 분석을 모두 건너뛴다 (FR-05)"""
    file_path = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"fake-pdf-bytes")
    cached_result = {"score": 91.0, "details": {"summary": "cached paper", "citations": []}}

    with app.app_context():
        with patch('backend.services.paper_service.get_cached_result',
                   return_value=json.dumps(cached_result)), \
             patch('backend.services.paper_service.set_cached_result') as mock_set, \
             patch.object(PaperDetector, 'detect') as mock_detect, \
             patch('backend.services.paper_service.CitationService.analyze_citations') as mock_cite:
            detection_request = PaperService().analyze(file_path)

        mock_detect.assert_not_called()
        mock_set.assert_not_called()
        mock_cite.assert_not_called()

        result = DetectionResult.query.filter_by(request_id=detection_request.id).first()
        assert result.cached is True
        assert result.score == 91.0
