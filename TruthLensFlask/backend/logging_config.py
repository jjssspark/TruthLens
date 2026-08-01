import json
import logging
from datetime import datetime, timezone

from flask import g, has_request_context

# 로거 레벨에서 강제로 가린다. 각 호출부가 기억하길 기대하면 반드시 새어나간다.
_REDACT_KEYS = {'password', 'token', 'authorization', 'api_key', 'apikey', 'secret'}

# extra로 들어온 것 중 로그에 실어 보낼 선택 필드
_OPTIONAL_FIELDS = ('event', 'durationMs', 'userId')


class RequestIdFilter(logging.Filter):
    """flask.g의 trace_id를 모든 레코드에 주입한다.

    호출부마다 traceId를 넘기도록 기대하면 반드시 누락되므로 필터에서 처리한다.
    Celery 워커처럼 요청 컨텍스트가 없는 곳에서도 죽지 않아야 한다.
    """

    def filter(self, record):
        record.trace_id = g.get('trace_id') if has_request_context() else None
        return True


class JsonFormatter(logging.Formatter):
    """구조화 JSON 로그. 사람이 아니라 검색 엔진이 읽는 형식."""

    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
                                 .isoformat()
                                 .replace('+00:00', 'Z'),
            "level": record.levelname,
            "message": record.getMessage(),
            "traceId": getattr(record, 'trace_id', None),
            "service": "truthlens",
        }

        for field in _OPTIONAL_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)

        if record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            payload["error"] = {"type": exc_type.__name__, "message": str(exc_value)}
            # 스택은 서버 로그에만 남는다. 응답에는 절대 싣지 않는다.
            payload["stack"] = self.formatException(record.exc_info)

        return json.dumps(_redact(payload), ensure_ascii=False)


def _redact(payload):
    return {
        key: ('<REDACTED>' if key.lower() in _REDACT_KEYS else value)
        for key, value in payload.items()
    }


def configure_logging(app):
    """루트 로거를 JSON 핸들러 하나로 교체한다."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.DEBUG if app.config.get('DEBUG') else logging.INFO)
