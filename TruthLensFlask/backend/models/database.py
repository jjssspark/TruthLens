from flask_sqlalchemy import SQLAlchemy

# 모든 모델이 공유하는 SQLAlchemy 인스턴스 (4.2 보안: ORM 사용으로 SQL Injection 방지)
db = SQLAlchemy()
