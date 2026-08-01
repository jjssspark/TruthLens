import io
import os
import uuid
from unittest.mock import patch


def _upload(client, endpoint, filename, field='file'):
    return client.post(
        endpoint,
        data={field: (io.BytesIO(b"fake-bytes"), filename)},
        content_type='multipart/form-data',
    )


def test_image_upload_rejects_disallowed_extension(logged_in_client):
    """이미지 엔드포인트는 allowlist 밖 확장자를 400으로 거부한다"""
    response = _upload(logged_in_client, '/api/v1/detect/image', 'payload.php')
    assert response.status_code == 400


def test_paper_upload_rejects_non_pdf(logged_in_client):
    """논문 엔드포인트는 PDF가 아니면 400으로 거부한다"""
    response = _upload(logged_in_client, '/api/v1/detect/paper', 'notes.txt')
    assert response.status_code == 400


def test_video_upload_rejects_disallowed_extension(logged_in_client):
    """영상 엔드포인트는 allowlist 밖 확장자를 400으로 거부한다"""
    response = _upload(logged_in_client, '/api/v1/detect/video', 'clip.exe')
    assert response.status_code == 400


def test_traversal_filename_does_not_write_outside_upload_folder(app, logged_in_client):
    """../ 파일명 업로드가 UPLOAD_FOLDER 밖에 파일을 만들지 않는다"""
    from backend.services.image_service import ImageService

    upload_folder = app.config['UPLOAD_FOLDER']
    # pytest 임시 루트는 실행 간 유지되므로, 이전 실행이 남긴 파일과
    # 섞이지 않도록 매번 다른 이름을 쓴다
    attack_name = f'../../evil-{uuid.uuid4().hex}.jpg'
    escaped = os.path.abspath(os.path.join(upload_folder, attack_name))

    with patch.object(ImageService, 'analyze_multiple', return_value=[]):
        _upload(logged_in_client, '/api/v1/detect/image', attack_name)

    assert not os.path.exists(escaped)
    assert os.listdir(upload_folder) != []
    assert all('..' not in name for name in os.listdir(upload_folder))


def test_image_error_response_uses_envelope(logged_in_client):
    """이미지 엔드포인트 에러는 봉투 형식과 에러 코드를 따른다"""
    response = logged_in_client.post('/api/v1/detect/image', data={})
    body = response.get_json()

    assert response.status_code == 400
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "FILE_REQUIRED"


def test_image_unsupported_extension_uses_error_code(logged_in_client):
    """확장자 위반은 FILE_TYPE_UNSUPPORTED 코드를 쓴다"""
    body = _upload(logged_in_client, '/api/v1/detect/image', 'payload.php').get_json()

    assert body["error"]["code"] == "FILE_TYPE_UNSUPPORTED"


def test_image_success_response_uses_envelope(logged_in_client):
    """이미지 판별 성공 응답은 success/data/error 봉투를 쓴다"""
    from backend.services.image_service import ImageService

    class _Stub:
        id = 42

    with patch.object(ImageService, 'analyze_multiple', return_value=[_Stub()]):
        body = _upload(logged_in_client, '/api/v1/detect/image', 'photo.jpg').get_json()

    assert body == {"success": True, "data": {"request_ids": [42]}, "error": None}
