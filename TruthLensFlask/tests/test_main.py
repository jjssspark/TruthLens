from backend.models.database import db
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult


def test_index_renders_for_logged_in_user(logged_in_client):
    """로그인 상태에서 메인 화면(/)이 정상 렌더링되어야 한다"""
    response = logged_in_client.get('/')
    assert response.status_code == 200


def test_index_shows_empty_state_without_history(logged_in_client):
    """이력이 없으면 가짜 데이터 대신 빈 상태를 보여준다"""
    response = logged_in_client.get('/')

    assert '아직 분석 이력이 없습니다'.encode() in response.data


def _add_request(user_id, type_, score=None, content_hash='hash-abcdefgh'):
    request = DetectionRequest(user_id=user_id, content_hash=content_hash,
                               type=type_, status='done' if score is not None else 'pending')
    db.session.add(request)
    db.session.commit()
    if score is not None:
        db.session.add(DetectionResult(request_id=request.id, score=score,
                                       detail_json={}, cached=False))
        db.session.commit()
    return request.id


def test_index_lists_only_current_user_requests(app, logged_in_client):
    """메인의 최근 분석은 본인 요청만 보여준다"""
    with app.app_context():
        own_id = _add_request(1, 'image', 88.0)
        other_id = _add_request(2, 'image', 91.0, content_hash='other-hash')

    response = logged_in_client.get('/')

    assert f'#{own_id}'.encode() in response.data
    assert f'/result/{other_id}'.encode() not in response.data


def test_index_badges_reflect_score_thresholds(app, logged_in_client):
    """점수 구간에 따라 판정 배지가 달라진다 (70 / 40 경계)"""
    with app.app_context():
        _add_request(1, 'image', 88.0, content_hash='h-ai')
        _add_request(1, 'news', 52.5, content_hash='h-mixed')
        _add_request(1, 'paper', 12.0, content_hash='h-human')

    body = logged_in_client.get('/').data

    assert 'AI 생성 의심'.encode() in body
    assert '혼합 추정'.encode() in body
    assert '사람 제작 추정'.encode() in body


def test_index_counts_ai_detections(app, logged_in_client):
    """AI 판정 집계는 70점 이상만 센다"""
    with app.app_context():
        _add_request(1, 'image', 88.0, content_hash='h1')
        _add_request(1, 'image', 70.0, content_hash='h2')
        _add_request(1, 'image', 69.9, content_hash='h3')

    body = logged_in_client.get('/').data.decode()

    assert 'data-count-to="3"' in body   # 전체 분석 3건
    assert 'data-count-to="2"' in body   # 그중 AI 판정 2건


def test_video_badge_reflects_configured_token(logged_in_client, monkeypatch):
    """HF_TOKEN이 있으면 영상 카드가 모델 연동 상태로 표시된다"""
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')

    body = logged_in_client.get('/').data.decode()

    assert '딥페이크 모델 연동됨' in body
    assert '휴리스틱 모드' not in body


def test_video_badge_reflects_missing_token(logged_in_client, monkeypatch):
    """HF_TOKEN이 없으면 휴리스틱 모드임을 그대로 밝힌다

    고정 문구를 쓰면 연동해두고 '예정'으로 남거나, 키가 없는데 연동된 것처럼
    보인다. 둘 다 사용자에게 거짓말이 된다.
    """
    monkeypatch.delenv('HF_TOKEN', raising=False)

    body = logged_in_client.get('/').data.decode()

    assert '휴리스틱 모드' in body
    assert '딥페이크 모델 연동됨' not in body


def test_index_handles_request_without_result(app, logged_in_client):
    """결과 레코드가 아직 없는 요청도 렌더링이 깨지지 않는다"""
    with app.app_context():
        _add_request(1, 'video', None)

    response = logged_in_client.get('/')

    assert response.status_code == 200
    assert 'pending'.encode() in response.data


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


# --- 헬스체크: 외부 모니터링이 찌르는 엔드포인트 ---

def test_health_is_reachable_without_login(client):
    """로그인 뒤에 있으면 모니터링이 302를 받아 장애를 놓친다"""
    response = client.get('/health')

    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok'}


def test_ready_reports_ready_when_database_is_reachable(client):
    """/ready는 DB까지 확인한다"""
    response = client.get('/ready')

    assert response.status_code == 200
    assert response.get_json() == {'status': 'ready'}
