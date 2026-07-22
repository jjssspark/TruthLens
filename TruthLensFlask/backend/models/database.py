from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

# 모든 모델이 공유하는 SQLAlchemy 인스턴스 (4.2 보안: ORM 사용으로 SQL Injection 방지)
db = SQLAlchemy()


def utcnow():
    """DB의 DATETIME 컬럼(naive)과 호환되는 naive UTC 현재 시각을 반환한다.

    datetime.utcnow()는 deprecated이므로 timezone-aware로 구한 뒤 tzinfo를 제거한다.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
