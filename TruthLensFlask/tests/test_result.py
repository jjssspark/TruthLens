from unittest.mock import patch

from backend.models.database import db
from backend.models.content_stats import ContentStats
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult


def _create_request_with_result(app, score=75.0, detail=None):
    with app.app_context():
        req = DetectionRequest(user_id=1, content_hash='hash-1', type='image', status='done')
        db.session.add(req)
        db.session.commit()
        result = DetectionResult(request_id=req.id, score=score, detail_json=detail or {})
        db.session.add(result)
        db.session.commit()
        return req.id


def test_result_page_returns_404_for_unknown_id(logged_in_client):
    """존재하지 않는 request_id로 접근 시 404를 반환해야 한다"""
    response = logged_in_client.get('/result/999')
    assert response.status_code == 404


def test_result_page_renders_for_existing_request(app, logged_in_client):
    """결과가 있는 request_id는 결과 화면을 정상 렌더링해야 한다"""
    request_id = _create_request_with_result(app)
    response = logged_in_client.get(f'/result/{request_id}')
    assert response.status_code == 200


def test_result_api_returns_score_json(app, logged_in_client):
    """/api/v1/result/<id>는 score/details/cached를 JSON으로 반환해야 한다"""
    request_id = _create_request_with_result(app, score=42.0, detail={'summary': 'ok'})
    response = logged_in_client.get(f'/api/v1/result/{request_id}')
    assert response.status_code == 200
    body = response.get_json()
    assert body['data']['score'] == 42.0
    assert body['data']['details'] == {'summary': 'ok'}


def test_result_api_404_when_no_result(logged_in_client):
    """결과가 없는 request_id는 404를 반환해야 한다"""
    response = logged_in_client.get('/api/v1/result/999')
    assert response.status_code == 404


def test_stats_api_returns_zero_when_no_stats(logged_in_client):
    """통계가 없는 콘텐츠 해시는 request_count 0을 반환해야 한다"""
    response = logged_in_client.get('/api/v1/stats/unknown-hash')
    assert response.status_code == 200
    assert response.get_json()['data']['request_count'] == 0


def test_stats_api_returns_existing_count(app, logged_in_client):
    """콘텐츠 통계가 있으면 request_count 값을 그대로 반환해야 한다"""
    with app.app_context():
        db.session.add(ContentStats(content_hash='known-hash', request_count=5))
        db.session.commit()

    response = logged_in_client.get('/api/v1/stats/known-hash')
    assert response.get_json()['data']['request_count'] == 5


def test_stats_api_uses_envelope(logged_in_client):
    """통계 API가 봉투 형식으로 응답한다 (FR-05)"""
    body = logged_in_client.get('/api/v1/stats/nonexistent-hash').get_json()

    assert body == {"success": True, "data": {"request_count": 0}, "error": None}


def test_download_pdf_report_returns_pdf(app, logged_in_client):
    """PDF 다운로드는 폰트 다운로드(네트워크) 없이 PDFService만 모킹해 검증한다"""
    request_id = _create_request_with_result(app)
    with patch('backend.routes.result_routes.PDFService.generate_report_pdf', return_value=b'%PDF-1.4 fake'):
        response = logged_in_client.get(f'/result/{request_id}/pdf')

    assert response.status_code == 200
    assert response.mimetype == 'application/pdf'
