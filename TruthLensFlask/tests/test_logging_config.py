import json
import logging
import sys

import pytest


@pytest.fixture
def record_factory():
    def _make(msg="테스트 메시지", level=logging.INFO, **extra):
        record = logging.LogRecord(
            name="test", level=level, pathname=__file__, lineno=1,
            msg=msg, args=(), exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return record
    return _make


def test_formatter_emits_required_fields(record_factory):
    """필수 필드 timestamp/level/message/traceId/service를 모두 포함한다"""
    from backend.logging_config import JsonFormatter

    payload = json.loads(JsonFormatter().format(record_factory()))

    assert set(payload) >= {"timestamp", "level", "message", "traceId", "service"}
    assert payload["level"] == "INFO"
    assert payload["message"] == "테스트 메시지"
    assert payload["service"] == "truthlens"


def test_formatter_timestamp_is_iso_utc(record_factory):
    """timestamp는 ISO 8601 UTC 형식이다"""
    from datetime import datetime

    from backend.logging_config import JsonFormatter

    payload = json.loads(JsonFormatter().format(record_factory()))

    assert payload["timestamp"].endswith("Z")
    datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))


def test_formatter_passes_through_optional_fields(record_factory):
    """event·durationMs 같은 선택 필드를 extra로 넘기면 그대로 실린다"""
    from backend.logging_config import JsonFormatter

    payload = json.loads(JsonFormatter().format(
        record_factory(event="image.analyze.completed", durationMs=120)
    ))

    assert payload["event"] == "image.analyze.completed"
    assert payload["durationMs"] == 120


def test_formatter_includes_stack_for_exceptions():
    """예외 로그는 서버 로그에만 스택을 남긴다"""
    from backend.logging_config import JsonFormatter

    try:
        raise ValueError("터짐")
    except ValueError:
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="실패", args=(), exc_info=sys.exc_info(),
        )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["error"]["type"] == "ValueError"
    assert "Traceback" in payload["stack"]


def test_filter_injects_trace_id_inside_request(app):
    """요청 컨텍스트 안에서는 g.trace_id가 레코드에 주입된다"""
    from flask import g

    from backend.logging_config import RequestIdFilter

    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="m", args=(), exc_info=None,
    )

    with app.test_request_context():
        g.trace_id = "trace-xyz"
        RequestIdFilter().filter(record)

    assert record.trace_id == "trace-xyz"


def test_filter_is_safe_outside_request_context():
    """요청 컨텍스트 밖(Celery 워커 등)에서도 예외 없이 동작한다"""
    from backend.logging_config import RequestIdFilter

    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="m", args=(), exc_info=None,
    )

    assert RequestIdFilter().filter(record) is True
    assert record.trace_id is None


def test_third_party_libraries_never_log_request_bodies(app):
    """DEBUG를 켜도 서드파티 라이브러리는 본문을 찍지 않는다

    openai SDK는 DEBUG에서 프롬프트 전체(= 논문 전문)를 로그에 남긴다.
    observability.md가 금지한 '요청 본문 전체'가 그대로 쌓인다.
    """
    from backend.logging_config import NOISY_LIBRARY_LOGGERS

    for name in NOISY_LIBRARY_LOGGERS:
        assert logging.getLogger(name).level >= logging.WARNING, name


def test_application_logger_still_reaches_info(app):
    """서드파티를 낮춰도 우리 코드의 로그는 막히지 않는다"""
    assert logging.getLogger().level <= logging.INFO
    assert logging.getLogger('backend.services.image_service').getEffectiveLevel() <= logging.INFO


def test_app_logs_are_json(app):
    """create_app이 붙인 루트 핸들러가 실제로 JSON 한 줄을 내보낸다

    핸들러 스트림을 직접 갈아끼워 확인한다. pytest의 출력 캡처는 핸들러가
    생성 시점에 붙든 sys.stderr를 잡지 못해 capfd로는 검증할 수 없다.
    """
    import io

    handler = logging.getLogger().handlers[0]
    buffer = io.StringIO()
    original_stream, handler.stream = handler.stream, buffer
    try:
        app.logger.info("기동 확인", extra={"event": "app.started"})
    finally:
        handler.stream = original_stream

    payload = json.loads(buffer.getvalue().strip())

    assert payload["event"] == "app.started"
    assert payload["message"] == "기동 확인"
    assert payload["service"] == "truthlens"
    assert "traceId" in payload


def test_request_log_carries_trace_id(app, logged_in_client):
    """요청 중 남긴 로그에 X-Request-Id가 traceId로 실린다"""
    import io

    @app.route('/api/v1/__log_probe')
    def log_probe():
        from flask import current_app
        current_app.logger.info("탐침", extra={"event": "probe.logged"})
        return {"ok": True}

    handler = logging.getLogger().handlers[0]
    buffer = io.StringIO()
    original_stream, handler.stream = handler.stream, buffer
    try:
        logged_in_client.get('/api/v1/__log_probe', headers={'X-Request-Id': 'trace-req-1'})
    finally:
        handler.stream = original_stream

    logged = [json.loads(l) for l in buffer.getvalue().splitlines() if l.startswith("{")]
    probe = [entry for entry in logged if entry.get("event") == "probe.logged"][0]

    assert probe["traceId"] == "trace-req-1"
