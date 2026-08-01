from flask import g, jsonify


def ok(data=None, meta=None):
    """성공 응답 봉투. data와 error는 항상 존재하고 한쪽은 반드시 null이다."""
    body = {"success": True, "data": data, "error": None}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body)


def fail(code, message, http_status):
    """실패 응답 봉투.

    내부 예외 메시지·스택은 절대 담지 않는다. 원인 추적은 서버 로그에서
    traceId로 한다.
    """
    return jsonify({
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "traceId": g.get('trace_id'),
        },
    }), http_status
