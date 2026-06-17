import json
from unittest.mock import patch

from ai_models.video_detector import VideoDetector
from backend.models.detection_result import DetectionResult
from backend.services.video_service import VideoService


def test_detect_video_page(logged_in_client):
    """영상 판별 화면(/detect/video)이 정상적으로 렌더링되는지 확인한다 (FR-01)"""
    response = logged_in_client.get('/detect/video')
    assert response.status_code == 200


def test_detect_video_api_requires_file_or_url(logged_in_client):
    """file/url이 없으면 400을 반환해야 한다 (FR-01)"""
    response = logged_in_client.post('/api/v1/detect/video', data={})
    assert response.status_code == 400


def test_analyze_video_caches_result_on_cache_miss(app, tmp_path):
    """캐시 미스 시 분석을 수행하고 결과를 캐시에 저장한다 (FR-05)"""
    file_path = str(tmp_path / "test.mp4")
    (tmp_path / "test.mp4").write_bytes(b"fake-video-bytes")
    detect_result = {"score": 55.0, "details": {"summary": "video test"}}

    with app.app_context():
        with patch('backend.services.video_service.get_cached_result', return_value=None), \
             patch('backend.services.video_service.set_cached_result') as mock_set, \
             patch.object(VideoDetector, 'detect', return_value=detect_result) as mock_detect:
            detection_request = VideoService().analyze(file_path=file_path)

        mock_detect.assert_called_once_with(file_path)
        mock_set.assert_called_once()

        result = DetectionResult.query.filter_by(request_id=detection_request.id).first()
        assert result.cached is False
        assert result.score == 55.0


def test_analyze_video_uses_cached_result_on_cache_hit(app, tmp_path):
    """캐시 히트 시 분석을 건너뛰고 캐시된 결과를 사용한다 (FR-05)"""
    file_path = str(tmp_path / "test.mp4")
    (tmp_path / "test.mp4").write_bytes(b"fake-video-bytes")
    cached_result = {"score": 77.0, "details": {"summary": "cached video"}}

    with app.app_context():
        with patch('backend.services.video_service.get_cached_result',
                   return_value=json.dumps(cached_result)), \
             patch('backend.services.video_service.set_cached_result') as mock_set, \
             patch.object(VideoDetector, 'detect') as mock_detect:
            detection_request = VideoService().analyze(file_path=file_path)

        mock_detect.assert_not_called()
        mock_set.assert_not_called()

        result = DetectionResult.query.filter_by(request_id=detection_request.id).first()
        assert result.cached is True
        assert result.score == 77.0
