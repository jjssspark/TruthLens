from backend.models.database import db
from backend.models.detection_request import DetectionRequest


def test_index_renders_for_logged_in_user(logged_in_client):
    """로그인 상태에서 메인 화면(/)이 정상 렌더링되어야 한다"""
    response = logged_in_client.get('/')
    assert response.status_code == 200


def test_history_requires_login(client):
    """미인증 상태로 /history 접근 시 /login으로 리디렉션되어야 한다"""
    response = client.get('/history')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_history_shows_only_current_user_requests(app, logged_in_client):
    """/history는 본인의 판별 요청만 최신순으로 보여준다"""
    with app.app_context():
        own = DetectionRequest(user_id=1, content_hash='own-hash', type='image', status='done')
        other = DetectionRequest(user_id=2, content_hash='other-hash', type='image', status='done')
        db.session.add_all([own, other])
        db.session.commit()
        own_id, other_id = own.id, other.id

    response = logged_in_client.get('/history')
    assert response.status_code == 200
    assert f'요청 #{own_id}'.encode() in response.data
    assert f'요청 #{other_id}'.encode() not in response.data
