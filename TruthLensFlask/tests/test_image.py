def test_detect_image_page(logged_in_client):
    """이미지 판별 화면(/detect/image)이 정상적으로 렌더링되는지 확인한다 (FR-02)"""
    response = logged_in_client.get('/detect/image')
    assert response.status_code == 200


def test_detect_image_api_requires_file(logged_in_client):
    """file이 없으면 400을 반환해야 한다 (FR-02)"""
    response = logged_in_client.post('/api/v1/detect/image', data={})
    assert response.status_code == 400


def _write_image_file(tmp_path, content=b"fake-image-bytes"):
    file_path = tmp_path / "test.jpg"
    file_path.write_bytes(content)
    return str(file_path)


def test_analyze_multiple_detects_images_concurrently(app, tmp_path):
    """다중 업로드의 판별은 동시에 돌아야 한다.

    1장이 HF 모델 응답을 최대 20초 기다린다(hf_deepfake_client.py의 timeout=20).
    순차로 돌리면 4장에 최대 80초가 걸려 gunicorn 기본 타임아웃 30초를 넘긴다.
    워커가 중단되면 응답이 JSON이 아니게 되고, 프론트(main.js:21의 JSON.parse)가
    "서버 응답을 해석할 수 없습니다"를 띄운다.
    """
    import threading
    import time
    from unittest.mock import patch

    from ai_models.image_detector import ImageDetector
    from backend.services.image_service import ImageService

    paths = []
    for i in range(4):
        path = tmp_path / f"img{i}.jpg"
        path.write_bytes(f"fake-image-{i}".encode())
        paths.append(str(path))

    lock = threading.Lock()
    active = 0
    peak = 0

    def slow_detect(self, file_path):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.2)
        with lock:
            active -= 1
        return {"score": 0.0, "details": {}}

    with app.test_request_context():
        with patch('backend.services.image_service.get_cached_result', return_value=None), \
                patch('backend.services.image_service.set_cached_result'), \
                patch.object(ImageDetector, 'detect', slow_detect):
            requests = ImageService().analyze_multiple(paths)

    assert len(requests) == 4
    assert peak > 1, f"판별이 순차로 돌았다(최대 동시 실행 {peak}장). 장수만큼 시간이 곱해진다"


def test_analyze_caches_result_on_cache_miss(app, tmp_path):
    """캐시 미스 시 분석을 수행하고 결과를 캐시에 저장한다 (FR-05)"""
    import json
    from unittest.mock import patch

    from ai_models.image_detector import ImageDetector
    from backend.models.detection_result import DetectionResult
    from backend.services.image_service import ImageService

    file_path = _write_image_file(tmp_path)
    detect_result = {"score": 42.0, "details": {"summary": "test"}}

    with app.test_request_context():
        with patch('backend.services.image_service.get_cached_result', return_value=None), \
                patch('backend.services.image_service.set_cached_result') as mock_set, \
                patch.object(ImageDetector, 'detect', return_value=detect_result) as mock_detect:
            detection_request = ImageService().analyze(file_path)

        mock_detect.assert_called_once_with(file_path)
        mock_set.assert_called_once_with(detection_request.content_hash, json.dumps(detect_result))

        result = DetectionResult.query.filter_by(request_id=detection_request.id).first()
        assert result.cached is False
        assert result.score == 42.0
        assert result.detail_json["summary"] == "test"
        assert "analyzed_at" in result.detail_json
        assert "elapsed_time" in result.detail_json


def test_analyze_uses_cached_result_on_cache_hit(app, tmp_path):
    """캐시 히트 시 분석을 건너뛰고 캐시된 결과를 사용한다 (FR-05)"""
    import json
    from unittest.mock import patch

    from ai_models.image_detector import ImageDetector
    from backend.models.detection_result import DetectionResult
    from backend.services.image_service import ImageService

    file_path = _write_image_file(tmp_path)
    cached_result = {"score": 99.0, "details": {"summary": "cached"}}

    with app.test_request_context():
        with patch('backend.services.image_service.get_cached_result', return_value=json.dumps(cached_result)), \
                patch('backend.services.image_service.set_cached_result') as mock_set, \
                patch.object(ImageDetector, 'detect') as mock_detect:
            detection_request = ImageService().analyze(file_path)

        mock_detect.assert_not_called()
        mock_set.assert_not_called()

        result = DetectionResult.query.filter_by(request_id=detection_request.id).first()
        assert result.cached is True
        assert result.score == 99.0
        assert result.detail_json["summary"] == "cached"
        assert "analyzed_at" in result.detail_json
        assert "elapsed_time" in result.detail_json
