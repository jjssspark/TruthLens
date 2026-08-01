# TruthLens 포트폴리오 완성도 개선 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 업로드 경로의 path traversal을 제거하고, API 응답을 프로젝트 자체 규약(`{success, data, error}`)으로 통일하며, 구조화 로깅과 핵심 판별 로직 테스트를 추가해 문서의 주장과 코드를 일치시킨다.

**Architecture:** 기존 3계층(`routes → services → ai_models`)을 유지한다. 횡단 관심사 두 개를 새 모듈로 뽑는다 — `backend/api/response.py`(응답 봉투)와 `backend/logging_config.py`(구조화 로깅). 업로드 저장은 `backend/services/upload_service.py`의 순수 함수로 분리해 Flask 없이 테스트 가능하게 만든다. 라우트는 이 세 모듈을 호출하기만 한다.

**Tech Stack:** Python 3.11+, Flask 3.x, SQLAlchemy, pytest, werkzeug(`secure_filename`), stdlib `logging`/`json`, GitHub Actions

## Global Constraints

- 새 런타임 의존성을 추가하지 않는다. 로깅은 stdlib `logging` + `json`만 쓴다.
- 500 응답에 스택 트레이스·내부 경로·예외 문자열을 절대 담지 않는다. 응답에는 `traceId`만 내려보낸다. (`.claude/standards/api-contract.md`)
- 로그에 비밀번호·토큰·API 키·요청 본문 전체를 남기지 않는다. (`.claude/standards/observability.md`)
- 모든 테스트는 외부 API 키 없이 통과해야 한다. 현재 48개 테스트가 그렇게 설계되어 있고 이를 깨지 않는다.
- 각 Task는 독립 커밋으로 만든다. 커밋 메시지는 `<type>: <설명>` 형식.
- **커밋 전 사용자에게 확인을 받는다.** (`~/.claude/CLAUDE.md`)
- 모든 명령은 `TruthLensFlask/` 안에서 실행한다.

## 설계 문서와 달라진 점

구현 계획을 쓰면서 실제 코드를 다시 확인한 결과, 설계 문서(`docs/design/specs/2026-08-01-portfolio-hardening-design.md`)의 사실관계 오류 2건을 발견했다.

| 설계 문서 서술 | 실제 | 계획에서의 처리 |
|---|---|---|
| "`config.py`에 `MAX_CONTENT_LENGTH`를 추가해 용량 초과를 413으로 처리하게 한다" | `config.py:37`에 이미 존재 (기본 500MB) | 추가 작업 없음 |
| "응답 형식 3종 — 판별 API `{status,data,meta}` / 로그인 API `{success,message}` / 규약 문서 `{success,data,error}`" | 로그인 API는 `templates/login.html:347-364`의 **주석 처리된 죽은 코드**다. 살아있는 JSON 응답은 `{status,data,meta}` 한 종류뿐 | 실제 마이그레이션 대상은 1종. Task 9에서 죽은 주석 블록을 제거한다 |

두 번째 항목은 Day 2 작업량을 줄인다. `backend/auth/routes.py`는 전부 `redirect` 반환이라 봉투 통일 대상이 아니다.

`save_upload`의 시그니처도 설계안(`save_upload(file, allowed_ext) -> str`)에서 바꿨다. `upload_folder`를 인자로 받아 모듈에서 Flask를 아예 import 하지 않게 한다 — 앱 컨텍스트 없이 테스트할 수 있다.

## File Structure

**신규**

| 파일 | 책임 |
|---|---|
| `backend/services/upload_service.py` | 업로드 파일 검증·저장. Flask 의존 없음 |
| `backend/api/__init__.py` | 패키지 마커 |
| `backend/api/response.py` | 응답 봉투 생성 (`ok`/`fail`) |
| `backend/logging_config.py` | `JsonFormatter`, `RequestIdFilter`, `configure_logging` |
| `tests/test_upload_service.py` | 업로드 검증·저장 테스트 |
| `tests/test_upload_routes.py` | 업로드 라우트 통합 테스트 |
| `tests/test_response_envelope.py` | 봉투 형식·전역 에러 핸들러 테스트 |
| `tests/test_logging_config.py` | JSON 로그 출력·traceId 전파 테스트 |
| `tests/test_image_detector.py` | 이미지 판별 로직 테스트 |
| `.github/workflows/tests.yml` | CI |

**수정**

| 파일 | 변경 |
|---|---|
| `backend/routes/image_routes.py` | `save_upload` 사용, 봉투 적용 |
| `backend/routes/video_routes.py` | 동일 |
| `backend/routes/paper_routes.py` | 동일 + 예외 노출 제거 |
| `backend/routes/news_routes.py` | 봉투 적용 + 예외 노출 제거 |
| `backend/routes/result_routes.py` | 봉투 적용 |
| `app.py` | `configure_logging`, `traceId` 주입, 전역 `errorhandler` |
| `tests/conftest.py` | `UPLOAD_FOLDER`를 tmp로 격리, `PROPAGATE_EXCEPTIONS=False` |
| `templates/detect_{image,news,paper,video}.html` | `json.status === 'success'` → `json.success` |
| `templates/login.html` | 죽은 주석 블록 제거 |
| `tests/test_news.py`, `tests/test_paper.py`, `tests/test_result.py` | 어서션 갱신 |
| `docs/PORTFOLIO.md`, `README.md` | 정정 + CI 뱃지 |

---

## Task 1: 업로드 저장 헬퍼

경로 조작을 막고 파일명 충돌을 없애는 순수 함수를 만든다. Flask를 import 하지 않으므로 앱 컨텍스트 없이 테스트된다.

**Files:**
- Create: `TruthLensFlask/backend/services/upload_service.py`
- Test: `TruthLensFlask/tests/test_upload_service.py`

**Interfaces:**
- Consumes: 없음 (첫 Task)
- Produces:
  - `UnsupportedFileType(ValueError)` — 확장자 allowlist 위반 시 발생
  - `save_upload(file, allowed_ext: set[str], upload_folder: str) -> str` — 저장된 경로 반환. `file`은 `werkzeug.datastructures.FileStorage`

- [ ] **Step 1: 실패하는 테스트 작성**

`TruthLensFlask/tests/test_upload_service.py`:

```python
import io
import os

import pytest
from werkzeug.datastructures import FileStorage

from backend.services.upload_service import UnsupportedFileType, save_upload

IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}


def _file(filename, content=b"data"):
    return FileStorage(stream=io.BytesIO(content), filename=filename)


def test_saves_inside_upload_folder(tmp_path):
    """정상 업로드는 지정한 폴더 안에 저장된다"""
    path = save_upload(_file("photo.jpg"), IMAGE_EXT, str(tmp_path))

    assert os.path.dirname(os.path.abspath(path)) == str(tmp_path)
    assert os.path.exists(path)


def test_traversal_filename_cannot_escape_upload_folder(tmp_path):
    """../ 가 포함된 파일명도 업로드 폴더를 벗어나지 못한다"""
    path = save_upload(_file("../../evil.jpg"), IMAGE_EXT, str(tmp_path))

    assert os.path.dirname(os.path.abspath(path)) == str(tmp_path)
    assert ".." not in os.path.basename(path)


def test_rejects_extension_outside_allowlist(tmp_path):
    """allowlist에 없는 확장자는 UnsupportedFileType을 던진다"""
    with pytest.raises(UnsupportedFileType):
        save_upload(_file("payload.php"), IMAGE_EXT, str(tmp_path))


def test_rejects_file_without_extension(tmp_path):
    """확장자가 없는 파일도 거부한다"""
    with pytest.raises(UnsupportedFileType):
        save_upload(_file("noext"), IMAGE_EXT, str(tmp_path))


def test_extension_check_is_case_insensitive(tmp_path):
    """대문자 확장자도 허용하고 소문자로 저장한다"""
    path = save_upload(_file("photo.JPG"), IMAGE_EXT, str(tmp_path))

    assert path.endswith(".jpg")


def test_same_filename_twice_does_not_overwrite(tmp_path):
    """같은 이름을 두 번 올려도 서로 덮어쓰지 않는다"""
    first = save_upload(_file("photo.jpg", b"first"), IMAGE_EXT, str(tmp_path))
    second = save_upload(_file("photo.jpg", b"second"), IMAGE_EXT, str(tmp_path))

    assert first != second
    assert os.path.exists(first) and os.path.exists(second)


def test_non_ascii_filename_keeps_extension(tmp_path):
    """한글 파일명이어도 확장자가 보존된다"""
    path = save_upload(_file("사진.png"), {"png"}, str(tmp_path))

    assert path.endswith(".png")
    assert os.path.exists(path)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_upload_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.upload_service'`

- [ ] **Step 3: 구현**

`TruthLensFlask/backend/services/upload_service.py`:

```python
import os
import uuid

from werkzeug.utils import secure_filename


class UnsupportedFileType(ValueError):
    """확장자 allowlist에 없는 파일이 업로드된 경우"""


def save_upload(file, allowed_ext, upload_folder):
    """업로드 파일을 안전한 경로에 저장하고 저장 경로를 반환한다.

    확장자를 allowlist로 먼저 검증하므로 경로에 들어가는 확장자는
    allowlist에 있는 문자열로만 한정된다. 이름 부분은 secure_filename으로
    경로 구분자와 상위 참조를 제거하고, uuid 접두어로 동시 업로드 충돌을 막는다.
    """
    original = file.filename or ''
    stem, dot_ext = os.path.splitext(original)
    ext = dot_ext.lower().lstrip('.')

    if ext not in allowed_ext:
        raise UnsupportedFileType(
            f"지원하지 않는 파일 형식입니다: {dot_ext or '(확장자 없음)'}"
        )

    # 한글 등 비ASCII 이름은 secure_filename이 전부 제거할 수 있어 대체 이름을 둔다
    safe_stem = secure_filename(stem) or 'upload'
    save_path = os.path.join(upload_folder, f"{uuid.uuid4().hex}_{safe_stem}.{ext}")

    file.save(save_path)
    return save_path
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_upload_service.py -v`
Expected: 7 passed

- [ ] **Step 5: 전체 회귀 확인**

Run: `cd TruthLensFlask && python -m pytest -q`
Expected: 55 passed (기존 48 + 신규 7)

- [ ] **Step 6: 커밋** (사용자 확인 후)

```bash
git add TruthLensFlask/backend/services/upload_service.py TruthLensFlask/tests/test_upload_service.py
git commit -m "feat: 업로드 파일명 검증·저장 헬퍼 추가

secure_filename + 확장자 allowlist + uuid 접두어로
path traversal과 파일명 충돌을 함께 막는다."
```

---

## Task 2: 업로드 라우트 3곳을 헬퍼로 교체

`file.filename`을 그대로 `os.path.join`에 넘기는 취약점 3곳을 제거한다. 테스트가 실제 `uploads/`를 오염시키지 않도록 conftest도 함께 격리한다.

**Files:**
- Modify: `TruthLensFlask/backend/routes/image_routes.py:1-37`
- Modify: `TruthLensFlask/backend/routes/video_routes.py:1-36`
- Modify: `TruthLensFlask/backend/routes/paper_routes.py:1-37`
- Modify: `TruthLensFlask/tests/conftest.py:8-20`
- Test: `TruthLensFlask/tests/test_upload_routes.py`

**Interfaces:**
- Consumes: `save_upload(file, allowed_ext, upload_folder)`, `UnsupportedFileType` (Task 1)
- Produces: 라우트 모듈의 확장자 상수 — `image_routes.ALLOWED_IMAGE_EXT`, `video_routes.ALLOWED_VIDEO_EXT`, `paper_routes.ALLOWED_PAPER_EXT`

- [ ] **Step 1: conftest에 업로드 폴더 격리 추가**

`TruthLensFlask/tests/conftest.py`의 `app` fixture를 교체한다. 기존:

```python
@pytest.fixture
def app():
    flask_app = create_app(config_overrides={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "GOOGLE_CLIENT_ID": "test-client-id",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
    })
```

변경 후:

```python
@pytest.fixture
def app(tmp_path_factory):
    flask_app = create_app(config_overrides={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "GOOGLE_CLIENT_ID": "test-client-id",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        # 테스트가 실제 uploads/를 오염시키지 않도록 격리
        "UPLOAD_FOLDER": str(tmp_path_factory.mktemp("uploads")),
    })
```

- [ ] **Step 2: 실패하는 테스트 작성**

`TruthLensFlask/tests/test_upload_routes.py`:

```python
import io
import os
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
    parent = os.path.dirname(os.path.abspath(upload_folder))
    before = set(os.listdir(parent))

    with patch.object(ImageService, 'analyze_multiple', return_value=[]):
        _upload(logged_in_client, '/api/v1/detect/image', '../../evil.jpg')

    assert set(os.listdir(parent)) == before
    assert all('..' not in name for name in os.listdir(upload_folder))
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_upload_routes.py -v`
Expected: FAIL — 확장자 검증이 없어 400 대신 200 또는 500이 반환된다

- [ ] **Step 4: `image_routes.py` 교체**

`TruthLensFlask/backend/routes/image_routes.py` 전체를 다음으로 바꾼다:

```python
from flask import Blueprint, current_app, jsonify, render_template, request

from backend.services.image_service import ImageService
from backend.services.upload_service import UnsupportedFileType, save_upload

image_bp = Blueprint('image', __name__)

MAX_IMAGES = 10
ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'webp', 'gif'}


@image_bp.route('/detect/image', methods=['GET'])
def detect_image_page():
    """이미지 판별 화면 (FR-02)"""
    return render_template('detect_image.html')


@image_bp.route('/api/v1/detect/image', methods=['POST'])
def detect_image_api():
    """이미지 AI 판별 요청: 다중 업로드 지원 (최대 10장, FR-02)"""
    files = request.files.getlist('file')
    if not files:
        return jsonify({"status": "error", "data": {"message": "file이 필요합니다."}}), 400

    try:
        save_paths = [
            save_upload(file, ALLOWED_IMAGE_EXT, current_app.config['UPLOAD_FOLDER'])
            for file in files[:MAX_IMAGES]
        ]
    except UnsupportedFileType as e:
        return jsonify({"status": "error", "data": {"message": str(e)}}), 400

    results = ImageService().analyze_multiple(save_paths)

    return jsonify({
        "status": "success",
        "data": {"request_ids": [r.id for r in results]},
        "meta": {},
    })
```

응답 형식은 Task 4에서 봉투로 바꾼다. 여기서는 보안 수정만 한다.

- [ ] **Step 5: `video_routes.py` 교체**

`TruthLensFlask/backend/routes/video_routes.py` 전체:

```python
from flask import Blueprint, current_app, jsonify, render_template, request

from backend.services.upload_service import UnsupportedFileType, save_upload
from backend.services.video_service import VideoService

video_bp = Blueprint('video', __name__)

ALLOWED_VIDEO_EXT = {'mp4', 'avi', 'mov', 'webm'}


@video_bp.route('/detect/video', methods=['GET'])
def detect_video_page():
    """영상 판별 화면 (FR-01)"""
    return render_template('detect_video.html')


@video_bp.route('/api/v1/detect/video', methods=['POST'])
def detect_video_api():
    """영상 AI 판별 요청: 파일(MP4/AVI/MOV/WEBM, 최대 500MB) 또는 URL (FR-01)"""
    url = request.form.get('url')

    if url:
        detection_request = VideoService().analyze(url=url)
    else:
        file = request.files.get('file')
        if not file:
            return jsonify({"status": "error", "data": {"message": "file 또는 url이 필요합니다."}}), 400

        try:
            save_path = save_upload(file, ALLOWED_VIDEO_EXT, current_app.config['UPLOAD_FOLDER'])
        except UnsupportedFileType as e:
            return jsonify({"status": "error", "data": {"message": str(e)}}), 400

        detection_request = VideoService().analyze(file_path=save_path)

    return jsonify({
        "status": "success",
        "data": {"request_id": detection_request.id},
        "meta": {},
    })
```

- [ ] **Step 6: `paper_routes.py`의 업로드 부분 교체**

`TruthLensFlask/backend/routes/paper_routes.py:1-9`의 import와 상수를 다음으로 바꾼다:

```python
from flask import Blueprint, current_app, jsonify, render_template, request

from backend.models.paper_citation import PaperCitation
from backend.services.citation_service import CitationService
from backend.services.paper_service import PaperService
from backend.services.upload_service import UnsupportedFileType, save_upload

paper_bp = Blueprint('paper', __name__)

ALLOWED_PAPER_EXT = {'pdf'}
```

`detect_paper_api`의 저장 부분(`:25-26`)을 교체:

```python
    try:
        save_path = save_upload(file, ALLOWED_PAPER_EXT, current_app.config['UPLOAD_FOLDER'])
    except UnsupportedFileType as e:
        return jsonify({"status": "error", "data": {"message": str(e)}}), 400
```

`import os`는 더 이상 쓰이지 않으므로 제거한다.

- [ ] **Step 7: 테스트 통과 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_upload_routes.py -v`
Expected: 4 passed

- [ ] **Step 8: 전체 회귀 확인**

Run: `cd TruthLensFlask && python -m pytest -q`
Expected: 59 passed

- [ ] **Step 9: 취약 패턴과 미사용 import 잔여 확인**

Run:

```bash
cd TruthLensFlask
grep -n "^import os" backend/routes/image_routes.py backend/routes/video_routes.py backend/routes/paper_routes.py
grep -rn "UPLOAD_FOLDER'\], file.filename" backend/
```

Expected: 두 명령 모두 출력 없음 (다른 라우트 파일의 `import os`는 이 작업 범위가 아니므로 건드리지 않는다)

- [ ] **Step 10: 커밋** (사용자 확인 후)

```bash
git add TruthLensFlask/backend/routes/image_routes.py \
        TruthLensFlask/backend/routes/video_routes.py \
        TruthLensFlask/backend/routes/paper_routes.py \
        TruthLensFlask/tests/conftest.py \
        TruthLensFlask/tests/test_upload_routes.py
git commit -m "fix: 업로드 경로 path traversal 취약점 제거

이미지·영상·논문 라우트가 file.filename을 그대로 os.path.join에
넘기던 것을 save_upload 헬퍼로 교체한다. 확장자 allowlist도 함께 적용.
테스트 업로드 폴더를 tmp로 격리한다."
```

---

## Task 3: 응답 봉투와 전역 에러 핸들러

응답 형식을 프로젝트 규약(`{success, data, error}`)에 맞추는 기반을 만든다. 이 Task는 헬퍼와 핸들러만 만들고, 개별 엔드포인트 전환은 Task 4~7에서 한다.

**Files:**
- Create: `TruthLensFlask/backend/api/__init__.py`
- Create: `TruthLensFlask/backend/api/response.py`
- Modify: `TruthLensFlask/app.py:1-57`
- Modify: `TruthLensFlask/tests/conftest.py`
- Test: `TruthLensFlask/tests/test_response_envelope.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `ok(data=None, meta=None) -> flask.Response` — `{"success": True, "data": data, "error": None}` (+ `meta`가 `None`이 아닐 때만 `"meta"` 키 포함)
  - `fail(code: str, message: str, http_status: int) -> tuple[flask.Response, int]` — `{"success": False, "data": None, "error": {"code", "message", "traceId"}}`
  - `g.trace_id: str` — Task 8(로깅)에서 사용

- [ ] **Step 1: 실패하는 테스트 작성**

`TruthLensFlask/tests/test_response_envelope.py`:

```python
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
```

- [ ] **Step 2: conftest에 `PROPAGATE_EXCEPTIONS=False` 추가**

`TESTING=True`이면 Flask의 `PROPAGATE_EXCEPTIONS`가 켜져서 예외를 그대로 다시 던진다. 그러면 `errorhandler(Exception)`이 동작하지 않아 위 테스트가 실패한다. `conftest.py`의 `config_overrides`에 추가:

```python
        # TESTING=True면 예외가 재발생해 errorhandler가 동작하지 않는다
        "PROPAGATE_EXCEPTIONS": False,
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_response_envelope.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.api'`

- [ ] **Step 4: 응답 헬퍼 구현**

`TruthLensFlask/backend/api/__init__.py` — 빈 파일로 생성.

`TruthLensFlask/backend/api/response.py`:

```python
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
```

- [ ] **Step 5: `app.py`에 traceId 주입과 전역 핸들러 등록**

import 블록(`:1-10`)을 다음으로 바꾼다. `import logging`은 Task 8에서 제거하므로 지금은 남겨둔다:

```python
import logging
import os
import uuid

from flask import Flask, g, redirect, request, session, url_for
from dotenv import load_dotenv
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from backend.api.response import fail
from backend.models.database import db
from backend.auth import oauth
```

`require_login` 정의(`:42`) **바로 위**에 traceId 주입을 추가한다. 등록 순서상 `require_login`보다 먼저 실행되어야 인증 실패 응답에도 traceId가 붙는다:

```python
    @app.before_request
    def assign_trace_id():
        g.trace_id = request.headers.get('X-Request-Id') or uuid.uuid4().hex
```

`register_blueprints(app)` 호출(`:49`) 뒤에 전역 핸들러를 등록:

```python
    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        # 404·405 등은 Flask 기본 처리를 그대로 쓴다
        if isinstance(e, HTTPException):
            return e

        app.logger.exception("처리되지 않은 예외", extra={"event": "request.failed"})

        if request.path.startswith('/api/'):
            return fail("INTERNAL_ERROR", "서버 오류가 발생했습니다.", 500)
        return "서버 오류가 발생했습니다.", 500
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_response_envelope.py -v`
Expected: 7 passed

- [ ] **Step 7: 전체 회귀 확인**

Run: `cd TruthLensFlask && python -m pytest -q`
Expected: 66 passed

- [ ] **Step 8: 커밋** (사용자 확인 후)

```bash
git add TruthLensFlask/backend/api/ TruthLensFlask/app.py \
        TruthLensFlask/tests/conftest.py TruthLensFlask/tests/test_response_envelope.py
git commit -m "feat: API 응답 봉투와 전역 에러 핸들러 추가

api-contract.md 규약대로 {success, data, error} 형식을 만들고,
미처리 예외가 내부 메시지를 노출하지 않도록 traceId만 내려보낸다."
```

---

## Task 4: 이미지 엔드포인트를 봉투로 전환

엔드포인트를 하나씩 옮긴다. 한 번에 전부 바꾸면 실패 원인을 특정할 수 없다.

**Files:**
- Modify: `TruthLensFlask/backend/routes/image_routes.py:18-37`
- Modify: `TruthLensFlask/templates/detect_image.html:223-226`
- Modify: `TruthLensFlask/tests/test_upload_routes.py`

**Interfaces:**
- Consumes: `ok`, `fail` (Task 3), `save_upload`, `UnsupportedFileType` (Task 1)
- Produces: `POST /api/v1/detect/image` → `{"success": true, "data": {"request_ids": [int]}, "error": null}`

- [ ] **Step 1: 실패하는 테스트 추가**

`TruthLensFlask/tests/test_upload_routes.py` 끝에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_upload_routes.py -v -k "envelope or code"`
Expected: FAIL — 응답에 `success` 키가 없음

- [ ] **Step 3: 라우트 전환**

`TruthLensFlask/backend/routes/image_routes.py` 전체:

```python
from flask import Blueprint, current_app, render_template, request

from backend.api.response import fail, ok
from backend.services.image_service import ImageService
from backend.services.upload_service import UnsupportedFileType, save_upload

image_bp = Blueprint('image', __name__)

MAX_IMAGES = 10
ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'webp', 'gif'}


@image_bp.route('/detect/image', methods=['GET'])
def detect_image_page():
    """이미지 판별 화면 (FR-02)"""
    return render_template('detect_image.html')


@image_bp.route('/api/v1/detect/image', methods=['POST'])
def detect_image_api():
    """이미지 AI 판별 요청: 다중 업로드 지원 (최대 10장, FR-02)"""
    files = request.files.getlist('file')
    if not files:
        return fail("FILE_REQUIRED", "file이 필요합니다.", 400)

    try:
        save_paths = [
            save_upload(file, ALLOWED_IMAGE_EXT, current_app.config['UPLOAD_FOLDER'])
            for file in files[:MAX_IMAGES]
        ]
    except UnsupportedFileType as e:
        return fail("FILE_TYPE_UNSUPPORTED", str(e), 400)

    results = ImageService().analyze_multiple(save_paths)

    return ok({"request_ids": [r.id for r in results]})
```

- [ ] **Step 4: 프론트엔드 파싱 수정**

`TruthLensFlask/templates/detect_image.html:223-226`. 기존:

```javascript
                if (json.status === 'success' && json.data.request_ids && json.data.request_ids.length) {
                    window.location.href = resultUrlTemplate.replace('/0', '/' + json.data.request_ids[0]);
                } else {
                    alert((json.data && json.data.message) || '분석 요청에 실패했습니다.');
```

변경 후:

```javascript
                if (json.success && json.data.request_ids && json.data.request_ids.length) {
                    window.location.href = resultUrlTemplate.replace('/0', '/' + json.data.request_ids[0]);
                } else {
                    alert((json.error && json.error.message) || '분석 요청에 실패했습니다.');
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_upload_routes.py -v`
Expected: 7 passed

- [ ] **Step 6: 전체 회귀 확인**

Run: `cd TruthLensFlask && python -m pytest -q`
Expected: 69 passed

- [ ] **Step 7: 커밋** (사용자 확인 후)

```bash
git add TruthLensFlask/backend/routes/image_routes.py \
        TruthLensFlask/templates/detect_image.html \
        TruthLensFlask/tests/test_upload_routes.py
git commit -m "refactor: 이미지 판별 API를 응답 봉투 형식으로 전환"
```

---

## Task 5: 뉴스 엔드포인트를 봉투로 전환

예외 문자열을 응답에 넣던 부분(`news_routes.py:35`)을 함께 제거한다.

**Files:**
- Modify: `TruthLensFlask/backend/routes/news_routes.py:1-43`
- Modify: `TruthLensFlask/templates/detect_news.html:191-194`
- Modify: `TruthLensFlask/tests/test_news.py:30`

**Interfaces:**
- Consumes: `ok`, `fail` (Task 3)
- Produces: `POST /api/v1/detect/news` → `{"success": true, "data": {"request_id": int}, "error": null}`

- [ ] **Step 1: 기존 어서션 갱신 + 실패 테스트 추가**

`TruthLensFlask/tests/test_news.py:30`의 기존 줄:

```python
    assert response.get_json()["status"] == "success"
```

변경 후:

```python
    assert response.get_json()["success"] is True
```

같은 파일 끝에 추가:

```python
def test_news_requires_url_or_text(logged_in_client):
    """url·text 둘 다 없으면 INPUT_REQUIRED로 400을 반환한다"""
    body = logged_in_client.post('/api/v1/detect/news', data={}).get_json()

    assert body["success"] is False
    assert body["error"]["code"] == "INPUT_REQUIRED"


def test_news_rejects_text_over_limit(logged_in_client):
    """10,000자를 넘는 text는 TEXT_TOO_LONG으로 거부한다"""
    body = logged_in_client.post(
        '/api/v1/detect/news', data={'text': 'ㄱ' * 10001}
    ).get_json()

    assert body["error"]["code"] == "TEXT_TOO_LONG"


def test_news_upstream_failure_does_not_leak_exception(logged_in_client):
    """외부 분석 실패 시 예외 메시지를 응답에 노출하지 않는다"""
    from unittest.mock import patch

    from backend.services.news_service import NewsService

    with patch.object(NewsService, 'analyze', side_effect=RuntimeError("api-key=SECRET123")):
        response = logged_in_client.post('/api/v1/detect/news', data={'text': '본문'})

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "ANALYSIS_FAILED"
    assert "SECRET123" not in response.get_data(as_text=True)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_news.py -v`
Expected: FAIL — `KeyError: 'success'`, 마지막 테스트는 500 + 예외 문자열 노출로 실패

- [ ] **Step 3: 라우트 전환**

`TruthLensFlask/backend/routes/news_routes.py` 전체:

```python
from flask import Blueprint, current_app, render_template, request

from backend.api.response import fail, ok
from backend.services.news_service import NewsService

news_bp = Blueprint('news', __name__)

MAX_TEXT_LENGTH = 10000


@news_bp.route('/detect/news', methods=['GET'])
def detect_news_page():
    """뉴스 판별 화면 (FR-03)"""
    return render_template('detect_news.html')


@news_bp.route('/api/v1/detect/news', methods=['POST'])
def detect_news_api():
    """뉴스 AI 생성/가짜뉴스 판별 요청: URL 또는 텍스트 (최대 10,000자, FR-03)"""
    url = request.form.get('url')
    text = request.form.get('text')

    if not url and not text:
        return fail("INPUT_REQUIRED", "url 또는 text가 필요합니다.", 400)

    if text and len(text) > MAX_TEXT_LENGTH:
        return fail("TEXT_TOO_LONG", f"text는 {MAX_TEXT_LENGTH}자를 초과할 수 없습니다.", 400)

    try:
        detection_request = NewsService().analyze(url=url, text=text)
    except ValueError as e:
        # 기사 추출 실패, 본문 없음 등 사용자 입력에서 비롯된 오류
        return fail("INPUT_REQUIRED", str(e), 400)
    except Exception:
        # 외부 API 장애는 우리 서버 버그가 아니므로 502로 구분한다.
        # 예외 내용은 응답이 아니라 서버 로그에만 남긴다.
        current_app.logger.exception("뉴스 분석 실패", extra={"event": "news.analyze.failed"})
        return fail("ANALYSIS_FAILED", "뉴스 분석에 실패했습니다. 잠시 후 다시 시도해주세요.", 502)

    return ok({"request_id": detection_request.id})
```

- [ ] **Step 4: 프론트엔드 파싱 수정**

`TruthLensFlask/templates/detect_news.html:191-194`. 기존:

```javascript
            if (res.ok && json.status === 'success' && json.data.request_id) {
                window.location.href = resultUrlTemplate.replace('/0', '/' + json.data.request_id);
            } else {
                alert((json.data && json.data.message) || '분석 요청에 실패했습니다.');
```

변경 후:

```javascript
            if (res.ok && json.success && json.data.request_id) {
                window.location.href = resultUrlTemplate.replace('/0', '/' + json.data.request_id);
            } else {
                alert((json.error && json.error.message) || '분석 요청에 실패했습니다.');
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_news.py -v`
Expected: 전부 passed

- [ ] **Step 6: 전체 회귀 확인**

Run: `cd TruthLensFlask && python -m pytest -q`
Expected: 72 passed

- [ ] **Step 7: 커밋** (사용자 확인 후)

```bash
git add TruthLensFlask/backend/routes/news_routes.py \
        TruthLensFlask/templates/detect_news.html \
        TruthLensFlask/tests/test_news.py
git commit -m "refactor: 뉴스 판별 API 봉투 전환 및 예외 노출 제거

외부 API 실패를 502 ANALYSIS_FAILED로 구분하고,
예외 문자열은 응답이 아닌 서버 로그에만 남긴다."
```

---

## Task 6: 논문·영상 엔드포인트를 봉투로 전환

두 엔드포인트는 변경 패턴이 동일하고 서로 의존하지 않아 한 Task로 묶는다.

**Files:**
- Modify: `TruthLensFlask/backend/routes/paper_routes.py`
- Modify: `TruthLensFlask/backend/routes/video_routes.py`
- Modify: `TruthLensFlask/templates/detect_paper.html:177-180`
- Modify: `TruthLensFlask/templates/detect_video.html:241-244`
- Modify: `TruthLensFlask/tests/test_paper.py:25`
- Modify: `TruthLensFlask/tests/test_upload_routes.py`

**Interfaces:**
- Consumes: `ok`, `fail` (Task 3), `save_upload`, `UnsupportedFileType` (Task 1)
- Produces:
  - `POST /api/v1/detect/paper` → `{"success", "data": {"request_id"}, "error"}`
  - `GET /api/v1/paper/<id>/citations` → `{"success", "data": {"citations": [...]}, "error"}`
  - `POST /api/v1/paper/<id>/citations/add` → `{"success", "data": {}, "error"}`
  - `POST /api/v1/detect/video` → `{"success", "data": {"request_id"}, "error"}`

- [ ] **Step 1: 기존 어서션 보강**

`TruthLensFlask/tests/test_paper.py:25`의 기존 줄은 `data` 키가 유지되므로 그대로 통과한다:

```python
    assert response.get_json()["data"]["citations"] == []
```

바로 아래에 봉투 확인을 추가한다:

```python
    assert response.get_json()["success"] is True
```

- [ ] **Step 2: 실패 테스트 추가**

`TruthLensFlask/tests/test_upload_routes.py` 끝에 추가:

```python
def test_paper_analysis_failure_returns_analysis_failed(logged_in_client):
    """논문 분석 실패는 502 ANALYSIS_FAILED이며 예외를 노출하지 않는다"""
    from backend.services.paper_service import PaperService

    with patch.object(PaperService, 'analyze', side_effect=RuntimeError("deepseek-key=SECRET456")):
        response = _upload(logged_in_client, '/api/v1/detect/paper', 'thesis.pdf')

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "ANALYSIS_FAILED"
    assert "SECRET456" not in response.get_data(as_text=True)


def test_video_requires_file_or_url(logged_in_client):
    """영상은 file·url 둘 다 없으면 INPUT_REQUIRED를 반환한다"""
    body = logged_in_client.post('/api/v1/detect/video', data={}).get_json()

    assert body["error"]["code"] == "INPUT_REQUIRED"
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_upload_routes.py tests/test_paper.py -v`
Expected: FAIL — 논문은 500 + 예외 노출, 영상은 `KeyError: 'error'`

- [ ] **Step 4: `paper_routes.py` 전환**

`TruthLensFlask/backend/routes/paper_routes.py` 전체:

```python
from flask import Blueprint, current_app, render_template, request

from backend.api.response import fail, ok
from backend.models.paper_citation import PaperCitation
from backend.services.citation_service import CitationService
from backend.services.paper_service import PaperService
from backend.services.upload_service import UnsupportedFileType, save_upload

paper_bp = Blueprint('paper', __name__)

ALLOWED_PAPER_EXT = {'pdf'}


@paper_bp.route('/detect/paper', methods=['GET'])
def detect_paper_page():
    """논문 판별 화면 (FR-04)"""
    return render_template('detect_paper.html')


@paper_bp.route('/api/v1/detect/paper', methods=['POST'])
def detect_paper_api():
    """논문 AI 판별 요청: PDF 업로드 (최대 50MB, 200페이지, FR-04)"""
    file = request.files.get('file')
    if not file:
        return fail("FILE_REQUIRED", "file(PDF)이 필요합니다.", 400)

    try:
        save_path = save_upload(file, ALLOWED_PAPER_EXT, current_app.config['UPLOAD_FOLDER'])
    except UnsupportedFileType as e:
        return fail("FILE_TYPE_UNSUPPORTED", str(e), 400)

    try:
        detection_request = PaperService().analyze(save_path)
    except Exception:
        current_app.logger.exception("논문 분석 실패", extra={"event": "paper.analyze.failed"})
        return fail("ANALYSIS_FAILED", "논문 분석에 실패했습니다. 잠시 후 다시 시도해주세요.", 502)

    return ok({"request_id": detection_request.id})


@paper_bp.route('/api/v1/paper/<int:request_id>/citations', methods=['GET'])
def get_citations(request_id):
    """논문 인용 분석 결과 조회 (FR-04)"""
    citations = PaperCitation.query.filter_by(request_id=request_id).all()

    return ok({
        "citations": [
            {"ref": c.citation_ref, "status": c.status, "doi": c.doi, "title": c.title}
            for c in citations
        ]
    })


@paper_bp.route('/api/v1/paper/<int:request_id>/citations/add', methods=['POST'])
def add_citations(request_id):
    """사용자가 확인한 누락 인용을 추가하고 PDF를 재생성한다 (FR-04)"""
    citation_ids = (request.get_json(silent=True) or {}).get('citation_ids', [])

    CitationService().add_citations(request_id, citation_ids)

    return ok({})
```

- [ ] **Step 5: `video_routes.py` 전환**

`TruthLensFlask/backend/routes/video_routes.py` 전체:

```python
from flask import Blueprint, current_app, render_template, request

from backend.api.response import fail, ok
from backend.services.upload_service import UnsupportedFileType, save_upload
from backend.services.video_service import VideoService

video_bp = Blueprint('video', __name__)

ALLOWED_VIDEO_EXT = {'mp4', 'avi', 'mov', 'webm'}


@video_bp.route('/detect/video', methods=['GET'])
def detect_video_page():
    """영상 판별 화면 (FR-01)"""
    return render_template('detect_video.html')


@video_bp.route('/api/v1/detect/video', methods=['POST'])
def detect_video_api():
    """영상 AI 판별 요청: 파일(MP4/AVI/MOV/WEBM, 최대 500MB) 또는 URL (FR-01)"""
    url = request.form.get('url')

    if url:
        detection_request = VideoService().analyze(url=url)
    else:
        file = request.files.get('file')
        if not file:
            return fail("INPUT_REQUIRED", "file 또는 url이 필요합니다.", 400)

        try:
            save_path = save_upload(file, ALLOWED_VIDEO_EXT, current_app.config['UPLOAD_FOLDER'])
        except UnsupportedFileType as e:
            return fail("FILE_TYPE_UNSUPPORTED", str(e), 400)

        detection_request = VideoService().analyze(file_path=save_path)

    return ok({"request_id": detection_request.id})
```

- [ ] **Step 6: 프론트엔드 파싱 수정**

`TruthLensFlask/templates/detect_paper.html:177-180`. 기존:

```javascript
                if (json.status === 'success' && json.data.request_id) {
                    window.location.href = resultUrlTemplate.replace('/0', '/' + json.data.request_id);
                } else {
                    alert((json.data && json.data.message) || '분석 요청에 실패했습니다.');
```

변경 후:

```javascript
                if (json.success && json.data.request_id) {
                    window.location.href = resultUrlTemplate.replace('/0', '/' + json.data.request_id);
                } else {
                    alert((json.error && json.error.message) || '분석 요청에 실패했습니다.');
```

`TruthLensFlask/templates/detect_video.html:241-244`도 동일하게 바꾼다. 기존:

```javascript
                if (json.status === 'success' && json.data.request_id) {
                    window.location.href = resultUrlTemplate.replace('/0', '/' + json.data.request_id);
                } else {
                    alert((json.data && json.data.message) || '분석 요청에 실패했습니다.');
```

변경 후:

```javascript
                if (json.success && json.data.request_id) {
                    window.location.href = resultUrlTemplate.replace('/0', '/' + json.data.request_id);
                } else {
                    alert((json.error && json.error.message) || '분석 요청에 실패했습니다.');
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_upload_routes.py tests/test_paper.py tests/test_video.py -v`
Expected: 전부 passed

- [ ] **Step 8: 전체 회귀 확인**

Run: `cd TruthLensFlask && python -m pytest -q`
Expected: 74 passed

- [ ] **Step 9: 커밋** (사용자 확인 후)

```bash
git add TruthLensFlask/backend/routes/paper_routes.py \
        TruthLensFlask/backend/routes/video_routes.py \
        TruthLensFlask/templates/detect_paper.html \
        TruthLensFlask/templates/detect_video.html \
        TruthLensFlask/tests/test_paper.py \
        TruthLensFlask/tests/test_upload_routes.py
git commit -m "refactor: 논문·영상 판별 API 봉투 전환 및 예외 노출 제거"
```

---

## Task 7: 결과 조회 엔드포인트를 봉투로 전환

마지막 남은 `{status, data, meta}` 응답 2곳을 옮긴다. 이 Task가 끝나면 살아있는 API 응답 형식이 1종이 된다.

**Files:**
- Modify: `TruthLensFlask/backend/routes/result_routes.py:1-45`
- Modify: `TruthLensFlask/tests/test_result.py`

**Interfaces:**
- Consumes: `ok` (Task 3)
- Produces:
  - `GET /api/v1/result/<id>` → `{"success", "data": {"score", "details", "cached"}, "error"}`
  - `GET /api/v1/stats/<hash>` → `{"success", "data": {"request_count"}, "error"}`

- [ ] **Step 1: 기존 어서션 확인**

Run: `cd TruthLensFlask && sed -n '30,65p' tests/test_result.py`

`body['data'][...]`를 읽는 구조는 `data` 키가 유지되므로 그대로 통과한다. `body['status']`를 읽는 줄이 있으면 `body['success'] is True`로 바꾼다.

- [ ] **Step 2: 봉투 확인 테스트 추가**

`TruthLensFlask/tests/test_result.py` 끝에 추가:

```python
def test_stats_api_uses_envelope(logged_in_client):
    """통계 API가 봉투 형식으로 응답한다 (FR-05)"""
    body = logged_in_client.get('/api/v1/stats/nonexistent-hash').get_json()

    assert body == {"success": True, "data": {"request_count": 0}, "error": None}
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_result.py -v`
Expected: FAIL — `{"status": "success", ...}`가 반환되어 비교 불일치

- [ ] **Step 4: 라우트 전환**

`TruthLensFlask/backend/routes/result_routes.py:1-2`의 import를 교체:

```python
import io
from flask import Blueprint, render_template, send_file

from backend.api.response import ok
```

`result_api`의 반환(`:25-33`)을 교체:

```python
    return ok({
        "score": detection_result.score,
        "details": detection_result.detail_json,
        "cached": detection_result.cached,
    })
```

`stats_api`의 반환(`:41-45`)을 교체:

```python
    return ok({"request_count": stats.request_count if stats else 0})
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_result.py -v`
Expected: 전부 passed

- [ ] **Step 6: 남은 구형 응답 형식 확인**

Run: `cd TruthLensFlask && grep -rn '"status": "success"\|"status": "error"' backend/ templates/`
Expected: 출력 없음

- [ ] **Step 7: 전체 회귀 확인**

Run: `cd TruthLensFlask && python -m pytest -q`
Expected: 75 passed

- [ ] **Step 8: 커밋** (사용자 확인 후)

```bash
git add TruthLensFlask/backend/routes/result_routes.py TruthLensFlask/tests/test_result.py
git commit -m "refactor: 결과·통계 조회 API 봉투 전환

이로써 살아있는 API 응답 형식이 {success, data, error} 1종으로 통일된다."
```

---

## Task 8: 구조화 JSON 로깅

`observability.md`가 요구하는 JSON 로그와 traceId 전파를 붙인다. 외부 의존성을 추가하지 않는다.

**Files:**
- Create: `TruthLensFlask/backend/logging_config.py`
- Modify: `TruthLensFlask/app.py:1-26`
- Modify: `TruthLensFlask/backend/services/image_service.py`
- Test: `TruthLensFlask/tests/test_logging_config.py`

**Interfaces:**
- Consumes: `g.trace_id` (Task 3)
- Produces:
  - `JsonFormatter(logging.Formatter)` — `format(record) -> str` (JSON 한 줄)
  - `RequestIdFilter(logging.Filter)` — 레코드에 `trace_id` 속성 주입
  - `configure_logging(app) -> None` — 루트 로거를 JSON 핸들러로 교체

- [ ] **Step 1: 실패하는 테스트 작성**

`TruthLensFlask/tests/test_logging_config.py`:

```python
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


def test_app_logs_are_json(app, capfd):
    """앱 로거가 실제로 JSON 한 줄을 출력한다"""
    app.logger.info("기동 확인", extra={"event": "app.started"})

    captured = capfd.readouterr()
    lines = [l for l in (captured.err + captured.out).splitlines() if l.startswith("{")]

    assert json.loads(lines[-1])["event"] == "app.started"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_logging_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.logging_config'`

- [ ] **Step 3: 구현**

`TruthLensFlask/backend/logging_config.py`:

```python
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
```

- [ ] **Step 4: `app.py`에서 `basicConfig` 교체**

`TruthLensFlask/app.py:17-20`의 기존 블록을 **삭제**한다:

```python
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
```

`config_overrides` 적용 이후, `os.makedirs(...)` 바로 위에 삽입한다 (`DEBUG` 설정을 읽어야 하므로 순서가 중요하다):

```python
    configure_logging(app)
```

import에서 `import logging`을 제거하고 다음을 추가:

```python
from backend.logging_config import configure_logging
```

- [ ] **Step 5: 판별 요청에 로그 지점 추가**

먼저 실제 코드를 읽는다:

Run: `cd TruthLensFlask && cat backend/services/image_service.py`

파일 상단에 추가:

```python
import logging

logger = logging.getLogger(__name__)
```

캐시 히트 분기에:

```python
            logger.info("이미지 캐시 히트", extra={"event": "image.cache.hit"})
```

캐시 미스 분기에:

```python
            logger.info("이미지 캐시 미스", extra={"event": "image.cache.miss"})
```

경과 시간이 계산된 뒤, `DetectionResult` 저장 직전에:

```python
        logger.info(
            "이미지 판별 완료",
            extra={"event": "image.analyze.completed", "durationMs": round(elapsed * 1000)},
        )
```

> `elapsed`는 기존 코드가 `detail_json`의 `elapsed_time`에 넣는 값과 같은 변수를 재사용한다. 실제 변수명은 Step 5 첫 명령으로 확인한 이름을 쓴다.

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd TruthLensFlask && python -m pytest tests/test_logging_config.py -v`
Expected: 7 passed

- [ ] **Step 7: 전체 회귀 확인**

Run: `cd TruthLensFlask && python -m pytest -q`
Expected: 82 passed

- [ ] **Step 8: 실제 로그가 JSON인지 눈으로 확인**

Run:

```bash
cd TruthLensFlask && python -c "
from app import create_app
app = create_app(config_overrides={'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
app.logger.info('기동 확인', extra={'event': 'app.started'})
c = app.test_client()
c.get('/login', headers={'X-Request-Id': 'demo-trace'})
" 2>&1 | tail -5
```

Expected: `{"timestamp": "...Z", "level": "INFO", "message": "기동 확인", "traceId": null, "service": "truthlens", "event": "app.started"}` 형태의 JSON 라인

- [ ] **Step 9: 커밋** (사용자 확인 후)

```bash
git add TruthLensFlask/backend/logging_config.py TruthLensFlask/app.py \
        TruthLensFlask/backend/services/image_service.py \
        TruthLensFlask/tests/test_logging_config.py
git commit -m "feat: 구조화 JSON 로깅과 traceId 전파 추가

observability.md 규약대로 필수 필드를 갖춘 JSON 로그를 출력하고,
X-Request-Id를 받아 전 계층에 전파한다. 비밀값은 로거에서 마스킹한다."
```

---

## Task 9: 이미지 판별 로직 테스트

커버리지가 가장 낮으면서(23%) 포트폴리오에서 가장 중요한 층을 덮는다. 외부 API 없이 순수하게 검증 가능하다.

**Files:**
- Create: `TruthLensFlask/tests/test_image_detector.py`
- Modify: `TruthLensFlask/templates/login.html:346-364`

**Interfaces:**
- Consumes: `ImageDetector.detect/_make_summary/_analyze_exif/_generate_heatmap`, `analyze_pixel_patterns` (기존 코드)
- Produces: 없음 (테스트 전용)

- [ ] **Step 1: 테스트 작성**

`TruthLensFlask/tests/test_image_detector.py`:

```python
import base64

import numpy as np
import pytest
from PIL import Image

from ai_models.image_detector import ImageDetector
from ai_models.pixel_heuristics import analyze_pixel_patterns


@pytest.fixture
def detector():
    return ImageDetector()


def _solid_image_path(tmp_path, color=(128, 128, 128), name="solid.jpg"):
    path = tmp_path / name
    Image.new("RGB", (256, 256), color).save(path)
    return str(path)


def _noise_image_path(tmp_path, name="noise.jpg"):
    rng = np.random.default_rng(42)
    array = rng.integers(0, 256, size=(256, 256, 3), dtype=np.uint8)
    path = tmp_path / name
    Image.fromarray(array).save(path)
    return str(path)


# --- _make_summary: 판정 문구 임계값 ---

@pytest.mark.parametrize("ai_percent, expected", [
    (100.0, "AI 제작 가능성이 높습니다"),
    (70.0, "AI 제작 가능성이 높습니다"),
    (69.9, "AI와 사람이 혼합된 이미지로 보입니다"),
    (40.0, "AI와 사람이 혼합된 이미지로 보입니다"),
    (39.9, "사람이 제작한 이미지일 가능성이 높습니다"),
    (0.0, "사람이 제작한 이미지일 가능성이 높습니다"),
])
def test_make_summary_verdict_at_thresholds(detector, ai_percent, expected):
    """70/40 경계에서 판정 문구가 정확히 분기한다"""
    summary = detector._make_summary(ai_percent, 100.0 - ai_percent, 90, {"suspicious": False})

    assert expected in summary


def test_make_summary_warns_when_exif_missing(detector):
    """EXIF가 없으면 그 사실을 요약에 명시한다"""
    summary = detector._make_summary(10.0, 90.0, 90, {"suspicious": True})

    assert "EXIF 정보가 없어" in summary


def test_make_summary_reports_normal_exif(detector):
    """EXIF가 정상이면 정상으로 표기한다"""
    summary = detector._make_summary(10.0, 90.0, 90, {"suspicious": False})

    assert "EXIF 정상" in summary


# --- _analyze_exif: 메타데이터 추출과 폴백 ---

def test_analyze_exif_flags_image_without_metadata(detector, tmp_path):
    """EXIF 없는 이미지는 suspicious로 표시된다"""
    result = detector._analyze_exif(_solid_image_path(tmp_path))

    assert result["has_exif"] is False
    assert result["suspicious"] is True


def test_analyze_exif_reads_camera_make_and_model(detector, tmp_path):
    """EXIF가 있으면 카메라 제조사·모델을 추출한다"""
    import piexif

    path = _solid_image_path(tmp_path, name="withexif.jpg")
    exif_bytes = piexif.dump({
        "0th": {
            piexif.ImageIFD.Make: b"Canon",
            piexif.ImageIFD.Model: b"EOS R5",
        },
        "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None,
    })
    piexif.insert(exif_bytes, path)

    result = detector._analyze_exif(path)

    assert result["camera_make"] == "Canon"
    assert result["camera_model"] == "EOS R5"
    assert result["has_exif"] is True
    assert result["suspicious"] is False


def test_analyze_exif_falls_back_on_corrupt_file(detector, tmp_path):
    """손상된 파일이어도 예외를 던지지 않고 폴백한다"""
    path = tmp_path / "corrupt.jpg"
    path.write_bytes(b"not-an-image")

    assert detector._analyze_exif(str(path)) == {"has_exif": False, "suspicious": True}


# --- _generate_heatmap ---

def test_generate_heatmap_returns_decodable_png_data_uri(detector, tmp_path):
    """히트맵은 디코딩 가능한 PNG data URI로 반환된다"""
    image = Image.open(_solid_image_path(tmp_path)).convert("RGB")

    heatmap = detector._generate_heatmap(image)

    assert heatmap.startswith("data:image/png;base64,")
    decoded = base64.b64decode(heatmap.split(",", 1)[1], validate=True)
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


# --- detect: 통합 ---

def test_detect_returns_complete_result_shape(detector, tmp_path):
    """detect()는 score와 6개 상세 필드를 모두 채워 반환한다"""
    result = detector.detect(_noise_image_path(tmp_path))

    assert 0 <= result["score"] <= 100
    assert set(result["details"]) == {
        "heatmap", "exif", "ai_percent", "human_percent", "confidence", "summary",
    }


def test_detect_ai_and_human_percent_sum_to_100(detector, tmp_path):
    """AI 개입과 사람 개입 비율의 합은 100이다"""
    details = detector.detect(_solid_image_path(tmp_path))["details"]

    assert details["ai_percent"] + details["human_percent"] == pytest.approx(100.0)


# --- pixel_heuristics: 점수 방향성 ---

def test_solid_image_scores_higher_than_noise_image():
    """노이즈가 없는 단색 이미지가 랜덤 노이즈보다 AI 점수가 높다"""
    solid = np.full((224, 224, 3), 128, dtype=np.uint8)
    noise = np.random.default_rng(0).integers(0, 256, (224, 224, 3), dtype=np.uint8)

    assert analyze_pixel_patterns(solid)["ai_percent"] > analyze_pixel_patterns(noise)["ai_percent"]


def test_solid_image_produces_expected_weighted_score():
    """단색 이미지는 노이즈 90·엣지 80·색상 75의 가중 평균 84.0을 낸다"""
    solid = np.full((224, 224, 3), 128, dtype=np.uint8)

    assert analyze_pixel_patterns(solid)["ai_percent"] == 84.0


def test_agreeing_analyses_yield_high_confidence():
    """세 분석 결과가 일치할수록 신뢰도가 높다"""
    solid = np.full((224, 224, 3), 128, dtype=np.uint8)

    assert analyze_pixel_patterns(solid)["confidence"] == 90
```

- [ ] **Step 2: 테스트 실행**

Run: `cd TruthLensFlask && python -m pytest tests/test_image_detector.py -v`
Expected: 전부 passed

> `test_solid_image_produces_expected_weighted_score`가 실패하면 임계값 계산을 검산한다. 단색 이미지는 노이즈 분산 0(→90), 엣지 밀도 0(→80), 색상 표준편차 0(→75)이므로 `90*0.5 + 80*0.3 + 75*0.2 = 84.0`이다. 계산이 맞는데도 실패하면 **테스트가 아니라 기대값**을 실제 동작에 맞춰 고친다.

- [ ] **Step 3: 커버리지 확인**

Run: `cd TruthLensFlask && python -m pytest --cov=ai_models --cov-report=term-missing tests/test_image_detector.py`
Expected: `ai_models/image_detector.py` 70% 이상, `ai_models/pixel_heuristics.py` 90% 이상

목표에 못 미치면 term-missing이 가리키는 미커버 줄을 보고 테스트를 추가한다.

- [ ] **Step 4: `login.html`의 죽은 주석 블록 제거**

`TruthLensFlask/templates/login.html:346-364`의 주석 처리된 `fetch('/login/google/callback', ...)` 블록 전체를 삭제한다. 호출되지 않는 코드이며, 존재하지 않는 응답 형식(`data.success`/`data.message`)을 참조해 오해를 부른다.

삭제 후 `handleCredentialResponse`는 다음만 남는다:

```javascript
        // Google 인증 완료 후 콜백 함수 (프론트엔드 SDK 방식)
        function handleCredentialResponse(response) {
            console.log("Google Credential Token:", response.credential);
            alert('구글 소셜 로그인 성공! (개발자 콘솔 연동 시 DB에 사용자 정보가 자동 저장됩니다)');
            window.location.href = "{{ url_for('main.index') }}";
        }
```

- [ ] **Step 5: 전체 회귀 확인**

Run: `cd TruthLensFlask && python -m pytest -q`
Expected: 96 passed

- [ ] **Step 6: 커밋** (사용자 확인 후)

```bash
git add TruthLensFlask/tests/test_image_detector.py TruthLensFlask/templates/login.html
git commit -m "test: 이미지 판별 로직 테스트 추가

임계값 경계·EXIF 폴백·히트맵 형식을 덮어 image_detector 커버리지를
23%에서 끌어올린다. login.html의 죽은 주석 블록도 함께 제거."
```

---

## Task 10: 문서 정정과 CI

코드가 사실이 된 뒤에 문서를 코드에 맞춘다. 순서가 반대면 또 거짓말이 된다.

**Files:**
- Create: `.github/workflows/tests.yml`
- Modify: `docs/PORTFOLIO.md`
- Modify: `README.md:1`

**Interfaces:**
- Consumes: Task 1~9의 결과
- Produces: 없음

- [ ] **Step 1: CI 워크플로 작성**

`/Users/tina/Project/TruthLens/.github/workflows/tests.yml`:

```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: TruthLensFlask

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip
          cache-dependency-path: TruthLensFlask/requirements-dev.txt

      # opencv-python은 libGL을 링크한다. headless 러너에는 없어서 import가 실패한다.
      - name: Install OpenCV system deps
        run: sudo apt-get update && sudo apt-get install -y libgl1 libglib2.0-0

      - name: Install dependencies
        run: pip install -r requirements-dev.txt

      - name: Run tests
        run: python -m pytest -q
        env:
          DATABASE_URL: sqlite:///:memory:
```

- [ ] **Step 2: 의존성 파일 존재 확인**

Run: `ls TruthLensFlask/requirements-dev.txt`
Expected: 파일 존재. 없으면 워크플로의 경로를 `requirements.txt`로 바꾼다.

- [ ] **Step 3: 로컬 전체 통과 재확인**

Run: `cd TruthLensFlask && python -m pytest -q`
Expected: 96 passed

- [ ] **Step 4: `README.md`에 CI 뱃지 추가**

`README.md:1`의 `# TruthLens` 바로 아래에 삽입:

```markdown
[![tests](https://github.com/jjssspark/TruthLens/actions/workflows/tests.yml/badge.svg)](https://github.com/jjssspark/TruthLens/actions/workflows/tests.yml)
```

- [ ] **Step 5: `docs/PORTFOLIO.md` 정정**

Run: `grep -n "방어\|전 구간\|예외 처리\|보안\|커버리지" docs/PORTFOLIO.md`

검증되지 않는 주장을 실제로 한 것으로 교체한다:

| 기존 주장 | 대체할 사실 |
|---|---|
| "라우트→서비스→모델 전 구간 방어 로직" | "전역 `errorhandler`로 미처리 예외를 `INTERNAL_ERROR` + `traceId`로 변환하고, 외부 API 실패는 502 `ANALYSIS_FAILED`로 구분한다 (`app.py`)" |
| 보안 관련 일반론 | "업로드 파일명을 `secure_filename` + 확장자 allowlist + uuid 접두어로 처리해 path traversal과 파일명 충돌을 막는다 (`backend/services/upload_service.py`)" |
| 응답 형식 언급 | "모든 API가 `{success, data, error}` 단일 봉투를 쓴다 (`backend/api/response.py`)" |

각 주장에 파일 경로를 붙인다. 근거가 없는 문장은 지운다.

- [ ] **Step 6: 문서의 수치 검증**

Run: `cd TruthLensFlask && python -m pytest --cov=backend --cov=ai_models --cov-report=term | tail -20`

`docs/PORTFOLIO.md`·`README.md`에 적힌 테스트 개수와 커버리지 수치를 이 출력과 대조해 실제 값으로 고친다.

- [ ] **Step 7: 커밋 및 푸시** (사용자 확인 후)

```bash
git add .github/workflows/tests.yml README.md docs/PORTFOLIO.md
git commit -m "docs: 문서를 코드 실제 동작에 맞춰 정정하고 CI 추가"
git pull --rebase
git push
```

> 푸시 후 GitHub Actions 탭에서 워크플로가 초록인지 확인한다. 실패하면 로그를 보고 고친 뒤 다시 푸시한다.

---

## Task 11: Tailwind 프로덕션 빌드 (선택)

**시간이 부족하면 이 Task를 버리고 Step 5의 "알려진 한계" 문단만 추가한다.** 어설픈 빌드 설정보다 한계를 명시하는 쪽이 낫다.

**Files:**
- Create: `TruthLensFlask/static/css/tailwind.src.css`
- Create: `TruthLensFlask/static/css/tailwind.css` (빌드 산출물)
- Create: `TruthLensFlask/tailwind.config.js`
- Modify: `TruthLensFlask/templates/base.html:7`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Consumes: 없음
- Produces: 없음

- [ ] **Step 1: Tailwind CLI 독립 실행 바이너리 내려받기**

```bash
cd /Users/tina/Project/TruthLens/TruthLensFlask
curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64
chmod +x tailwindcss-macos-arm64
```

`.gitignore`에 추가한다 (바이너리는 커밋하지 않는다):

```gitignore
# Tailwind CLI 바이너리 (로컬 빌드 도구)
tailwindcss-*
```

- [ ] **Step 2: 설정 파일과 소스 CSS 작성**

`TruthLensFlask/tailwind.config.js`:

```javascript
module.exports = {
  content: ['./templates/**/*.html', './static/js/**/*.js'],
  theme: { extend: {} },
  plugins: [],
};
```

`TruthLensFlask/static/css/tailwind.src.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 3: CSS 빌드**

```bash
cd /Users/tina/Project/TruthLens/TruthLensFlask
./tailwindcss-macos-arm64 -i static/css/tailwind.src.css -o static/css/tailwind.css --minify
```

Expected: `static/css/tailwind.css` 생성

- [ ] **Step 4: `base.html`에서 CDN 교체**

`TruthLensFlask/templates/base.html:7`의 기존:

```html
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
```

변경 후:

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.css') }}">
```

- [ ] **Step 5: 화면 회귀 확인**

```bash
cd /Users/tina/Project/TruthLens/TruthLensFlask && python app.py
```

브라우저에서 `/login`, `/detect/image`, `/history`를 열어 레이아웃이 깨지지 않는지 확인한다.

**깨지면 되돌린다.** CDN 스크립트로 `base.html`을 복원하고, `README.md`에 다음을 추가한 뒤 이 Task를 종료한다:

```markdown
### 알려진 한계

- Tailwind를 CDN(`cdn.tailwindcss.com`)으로 로드하고 있습니다. 공식 문서가 프로덕션 사용을 권장하지 않는 개발용 스크립트로, CLI 빌드 전환은 로드맵입니다. (`forms`/`container-queries` 플러그인 의존이 있어 CLI 전환 시 별도 설정이 필요합니다.)
```

- [ ] **Step 6: 커밋** (사용자 확인 후)

```bash
git add TruthLensFlask/static/css/ TruthLensFlask/tailwind.config.js \
        TruthLensFlask/templates/base.html .gitignore README.md
git commit -m "build: Tailwind CDN을 CLI 빌드 산출물로 교체"
```

---

## 완료 기준

설계 문서의 성공 기준과 대응한다. 전부 명령으로 검증 가능하다.

| 기준 | 검증 명령 | 통과 조건 |
|---|---|---|
| `secure_filename` 미적용 업로드 3 → 0 | `grep -rn "UPLOAD_FOLDER'\], file.filename" TruthLensFlask/backend/` | 출력 없음 |
| 확장자 allowlist 존재 | `grep -rn "ALLOWED_.*_EXT" TruthLensFlask/backend/routes/` | 3개 파일 |
| 응답 형식 1종 | `grep -rn '"status": "success"' TruthLensFlask/backend/ TruthLensFlask/templates/` | 출력 없음 |
| 에러 응답에 예외 문자열 0건 | `cd TruthLensFlask && python -m pytest -k "leak" -v` | passed |
| `image_detector` 커버리지 70%+ | `cd TruthLensFlask && python -m pytest --cov=ai_models --cov-report=term-missing` | 70% 이상 |
| 로그가 JSON | Task 8 Step 8 | JSON 라인 출력 |
| CI 초록 | GitHub Actions 탭 | 초록 체크 |

### 각 Task 종료 시 스모크 체크

`pytest`만으로는 앱이 실제로 기동하는지 알 수 없다. Task 2·4·7·8을 마칠 때마다 다음을 실행한다.

```bash
cd TruthLensFlask && python app.py
```

다른 터미널에서:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/login
```

Expected: `200`

그다음 브라우저로 회원가입 → `/detect/image`에서 이미지 1건 업로드 → 결과 페이지가 에러 없이 렌더링되는지 확인한다. 봉투 전환(Task 4~7) 이후에는 **프론트엔드가 응답을 파싱하지 못해 결과 페이지로 넘어가지 못하는 것이 가장 흔한 실패**이므로 이 확인을 건너뛰지 않는다.

## 리스크

| 리스크 | 대응 |
|---|---|
| `test_solid_image_produces_expected_weighted_score`의 기대값 84.0이 실제와 다름 | Task 9 Step 2 주석 참고. 계산을 검산하고 실제 동작에 맞춘다 |
| CI에서 opencv `libGL` 오류 | 워크플로에 apt 설치 단계를 포함했다. 그래도 실패하면 `opencv-python`을 `opencv-python-headless`로 교체 |
| `PROPAGATE_EXCEPTIONS` 누락으로 전역 핸들러 테스트 실패 | Task 3 Step 2에서 처리 |
| Task 8의 `image_service.py` 변수명이 예상과 다름 | Step 5 첫 명령으로 실제 파일을 읽고 그 이름을 쓴다 |
| Tailwind CDN의 `forms`/`container-queries` 플러그인이 CLI 빌드에서 빠져 화면이 깨짐 | Task 11 Step 5에서 확인하고, 깨지면 되돌린 뒤 한계로 명시 |
| 시간 부족 | Task 9(테스트)를 Task 10·11보다 우선한다. 절반만 마이그레이션된 API보다 낫다 |

## 롤백

각 Task가 독립 커밋이다. 문제가 생기면 해당 커밋만 `git revert <sha>` 한다.
Task 4~7은 엔드포인트별로 쪼개져 있어 한 엔드포인트만 되돌릴 수 있다.
