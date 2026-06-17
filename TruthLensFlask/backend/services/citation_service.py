# 제목 : 논문 AI 생성 판별 및 분석
# 담당자 : 허영주 

from backend.models.database import db
from backend.models.paper_citation import PaperCitation

import re
from pypdf import PdfReader

class CitationService:

    def extract_citations(self, text):
        citations = re.findall(r"\[\d+\]|\([A-Z][A-Za-z]+,\s?\d{4}\)", text)
        return list(set(citations))
        
    """논문 인용 분석: 본문 인용 ↔ 참고문헌 교차 검증, 누락 인용 탐지 (FR-04)"""
    def analyze_citations(self, request_id, file_path):
        """
        본문 내 인용 표시([1], (Smith, 2020) 등)와 참고문헌 목록을 교차 검증하여
        누락된 인용을 PaperCitation 테이블에 저장한다.
        """
        # TODO: PDF에서 본문 인용 표시 추출 및 참고문헌 목록 파싱, 누락 인용 메타데이터 검색(DOI/저자/제목)
        citations = []  # [{"ref": "[1]", "status": "matched"|"missing", "doi": ..., "title": ...}]

        # for citation in citations:
        #     db.session.add(PaperCitation(
        #         request_id=request_id,
        #         citation_ref=citation['ref'],
        #         status=citation['status'],
        #         doi=citation.get('doi'),
        #         title=citation.get('title'),
        #     ))
        
        for citation in citations:
            db.session.add(PaperCitation(
                request_id=request_id,
                citation_ref=citation,
                status="detected",
                doi=None,
                title=None,
            ))
            
        db.session.commit()

        return citations

    def add_citations(self, request_id, citation_ids):
        """사용자가 확인한 누락 인용을 추가하고 수정된 PDF를 재생성한다"""
        # TODO: 선택된 citation_ids에 대한 메타데이터를 참고문헌에 추가하고 PDF 재생성
        raise NotImplementedError
