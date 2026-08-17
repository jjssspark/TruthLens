"""앱 팩토리가 어떤 DB 백엔드에서도 테이블을 준비하는지 검증한다.

배경: 클라우드타입 무료 플랜은 컨테이너 디스크를 재기동마다 초기화한다.
SQLite 파일이 앱과 같은 디스크에 있으면 가입한 계정이 통째로 사라진다.
외부 관리형 DB(Postgres 등)로 옮기는데, 기존 코드는 URI가 sqlite로 시작할
때만 create_all()을 돌려서 Postgres로 바꾸면 테이블이 아예 생기지 않았다.
"""
import json

import pytest
from sqlalchemy.exc import ProgrammingError

from app import create_app
from backend.models.database import db


@pytest.fixture
def overrides(tmp_path):
    return {
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "PROPAGATE_EXCEPTIONS": False,
    }


def test_creates_tables_on_non_sqlite_backend(monkeypatch, overrides):
    """sqlite가 아닌 백엔드에서도 테이블 생성을 시도해야 한다.

    이 검사가 없으면 DATABASE_URL을 Postgres로 바꾼 순간 테이블이 없는 채로
    앱이 떠서, 회원가입이 500으로 죽는다.
    """
    calls = []
    monkeypatch.setattr(db, "create_all", lambda *a, **kw: calls.append(True))

    create_app(config_overrides={
        **overrides,
        # 실제 접속은 하지 않는다. 엔진 생성은 지연 로딩이라 드라이버만 있으면 된다.
        "SQLALCHEMY_DATABASE_URI": "postgresql://user:pw@db.invalid:5432/truthlens",
    })

    assert calls, "sqlite가 아닌 백엔드에서 create_all()이 호출되지 않았다"


def test_boot_survives_when_table_creation_fails(monkeypatch, overrides, capsys):
    """테이블 생성이 실패해도 앱은 떠야 하고, 조용히 넘어가면 안 된다.

    gunicorn 워커 2개가 동시에 부팅하면 둘 다 CREATE TABLE을 시도해 한쪽이
    '이미 존재함'으로 터진다. 이때 프로세스가 죽으면 크래시 루프가 된다.
    외부 DB가 잠시 안 뜬 경우도 마찬가지로 기동은 되어야 /ready가 503을 알린다.

    caplog가 아니라 stderr를 읽는 이유: configure_logging()이 루트 핸들러를
    JSON 핸들러 하나로 교체해서 pytest의 캡처 핸들러가 떨어져 나간다.
    """
    def boom(*args, **kwargs):
        raise ProgrammingError("CREATE TABLE users (...)", {}, Exception("already exists"))

    monkeypatch.setattr(db, "create_all", boom)

    app = create_app(config_overrides={
        **overrides,
        "SQLALCHEMY_DATABASE_URI": "postgresql://user:pw@db.invalid:5432/truthlens",
    })

    assert app is not None, "테이블 생성 실패로 앱 기동이 막히면 크래시 루프가 된다"

    logged = [
        json.loads(line)
        for line in capsys.readouterr().err.splitlines()
        if line.startswith("{")
    ]
    warnings = [p for p in logged if p.get("event") == "db.create_all.failed"]
    assert warnings, "실패를 조용히 삼키면 안 된다 (observability: 폴백은 WARN을 남긴다)"
    assert warnings[0]["level"] == "WARNING"
    assert warnings[0]["error"]["type"] == "ProgrammingError"


def test_engine_checks_connection_before_handing_it_out(overrides):
    """풀에서 꺼낸 커넥션이 살아있는지 확인하도록 엔진이 설정돼야 한다.

    외부 관리형 Postgres는 유휴 커넥션을 서버 쪽에서 먼저 끊는다. 죽은
    커넥션을 그대로 쓰면 다음 요청이 연결 오류로 죽는다. config.py에만
    값을 적어두고 엔진까지 전달되지 않으면 소용없으므로 엔진에서 확인한다.
    """
    app = create_app(config_overrides={**overrides, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

    with app.app_context():
        assert db.engine.pool._pre_ping is True
        assert db.engine.pool._recycle > 0


def test_still_creates_tables_on_sqlite(monkeypatch, overrides):
    """기존 로컬 개발 흐름(SQLite 자동 생성)이 깨지지 않아야 한다."""
    calls = []
    monkeypatch.setattr(db, "create_all", lambda *a, **kw: calls.append(True))

    create_app(config_overrides={**overrides, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

    assert calls
