def test_ok_wraps_data_in_envelope(app):
    """ok()는 success/data/error 세 키를 모두 채운다"""
    from backend.api.response import ok

    with app.test_request_context():
        body = ok({"request_id": 7}).get_json()

    assert body == {"success": True, "data": {"request_id": 7}, "error": None}


def test_ok_includes_meta_only_when_given(app):
    """meta는 명시했을 때만 포함된다"""
    from backend.api.response import ok

    with app.test_request_context():
        assert "meta" not in ok({"a": 1}).get_json()
        assert ok({"a": 1}, meta={"total": 3}).get_json()["meta"] == {"total": 3}


def test_fail_returns_code_and_status(app):
    """fail()은 error.code와 HTTP 상태를 함께 반환한다"""
    from backend.api.response import fail

    with app.test_request_context():
        response, status = fail("FILE_REQUIRED", "file이 필요합니다.", 400)
        body = response.get_json()

    assert status == 400
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "FILE_REQUIRED"


def test_trace_id_is_taken_from_request_header(app, logged_in_client):
    """X-Request-Id 헤더가 있으면 그 값을 traceId로 쓴다"""
    from backend.api.response import fail

    @app.route('/api/v1/__trace_probe')
    def probe():
        return fail("INTERNAL_ERROR", "테스트", 500)

    response = logged_in_client.get(
        '/api/v1/__trace_probe', headers={'X-Request-Id': 'req-abc-123'}
    )

    assert response.get_json()["error"]["traceId"] == "req-abc-123"


def test_trace_id_is_generated_when_header_absent(app, logged_in_client):
    """헤더가 없으면 traceId를 생성한다"""
    from backend.api.response import fail

    @app.route('/api/v1/__trace_probe2')
    def probe2():
        return fail("INTERNAL_ERROR", "테스트", 500)

    trace_id = logged_in_client.get('/api/v1/__trace_probe2').get_json()["error"]["traceId"]

    assert trace_id


def test_unhandled_exception_returns_envelope_without_leaking_details(app, logged_in_client):
    """미처리 예외는 INTERNAL_ERROR 봉투로만 응답하고 예외 내용을 노출하지 않는다"""
    @app.route('/api/v1/__boom')
    def boom():
        raise RuntimeError("데이터베이스 비밀번호가 담긴 내부 메시지")

    response = logged_in_client.get('/api/v1/__boom')
    body = response.get_json()

    assert response.status_code == 500
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["traceId"]
    assert "데이터베이스 비밀번호" not in response.get_data(as_text=True)
    assert "Traceback" not in response.get_data(as_text=True)


def test_http_exceptions_keep_their_own_status(logged_in_client):
    """404 등 HTTPException은 전역 핸들러가 500으로 바꾸지 않는다"""
    assert logged_in_client.get('/api/v1/does-not-exist').status_code == 404
