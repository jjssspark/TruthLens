from flask import Blueprint, current_app, jsonify, render_template, request

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
        return jsonify({"status": "error", "data": {"message": "file(PDF)이 필요합니다."}}), 400

    try:
        save_path = save_upload(file, ALLOWED_PAPER_EXT, current_app.config['UPLOAD_FOLDER'])
    except UnsupportedFileType as e:
        return jsonify({"status": "error", "data": {"message": str(e)}}), 400

    try:
        detection_request = PaperService().analyze(save_path)
    except Exception as e:
        return jsonify({"status": "error", "data": {"message": f"논문 분석 중 오류가 발생했습니다: {e}"}}), 500

    return jsonify({
        "status": "success",
        "data": {"request_id": detection_request.id},
        "meta": {},
    })


@paper_bp.route('/api/v1/paper/<int:request_id>/citations', methods=['GET'])
def get_citations(request_id):
    """논문 인용 분석 결과 조회 (FR-04)"""
    citations = PaperCitation.query.filter_by(request_id=request_id).all()

    return jsonify({
        "status": "success",
        "data": {
            "citations": [
                {"ref": c.citation_ref, "status": c.status, "doi": c.doi, "title": c.title}
                for c in citations
            ]
        },
        "meta": {},
    })


@paper_bp.route('/api/v1/paper/<int:request_id>/citations/add', methods=['POST'])
def add_citations(request_id):
    """사용자가 확인한 누락 인용을 추가하고 PDF를 재생성한다 (FR-04)"""
    citation_ids = (request.get_json(silent=True) or {}).get('citation_ids', [])

    CitationService().add_citations(request_id, citation_ids)

    return jsonify({"status": "success", "data": {}, "meta": {}})
