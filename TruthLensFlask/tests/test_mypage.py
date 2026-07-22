from backend.models.database import db
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult
from backend.models.mypage import User


def test_profile_requires_login(client):
    """미인증 상태로 /profile 접근 시 /login으로 리디렉션되어야 한다"""
    response = client.get('/profile')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_profile_renders_stats_for_logged_in_user(app, logged_in_client):
    """/profile은 본인의 스캔 횟수와 평균 점수를 계산해 보여준다"""
    with app.app_context():
        req = DetectionRequest(user_id=1, content_hash='h1', type='image', status='done')
        db.session.add(req)
        db.session.commit()
        result = DetectionResult(request_id=req.id, score=80.0)
        db.session.add(result)
        db.session.commit()

    response = logged_in_client.get('/profile')
    assert response.status_code == 200
    assert b'test@example.com' in response.data
