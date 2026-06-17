from backend.models.database import db


class PaperCitation(db.Model):
    """paper_citations 테이블: 논문 인용 분석 결과 (FR-04, 5.3)"""
    __tablename__ = 'paper_citations'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('detection_requests.id'), nullable=False)
    citation_ref = db.Column(db.String(255), nullable=False)  # 예: [1], (Smith, 2020)
    status = db.Column(db.String(20), nullable=False, default='matched')  # matched, missing
    doi = db.Column(db.String(100), nullable=True)
    title = db.Column(db.String(500), nullable=True)
