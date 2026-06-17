import io
from flask import Blueprint, jsonify, render_template, send_file

from backend.models.content_stats import ContentStats
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult
from backend.services.pdf_service import PDFService

result_bp = Blueprint('result', __name__)


@result_bp.route('/result/<int:request_id>', methods=['GET'])
def result_page(request_id):
    """판별 결과 화면: 신뢰 점수, 상세 분석, 집계 표시"""
    detection_request = DetectionRequest.query.get_or_404(request_id)
    detection_result = DetectionResult.query.filter_by(request_id=request_id).first()
    return render_template('result.html', request=detection_request, result=detection_result)


@result_bp.route('/api/v1/result/<int:request_id>', methods=['GET'])
def result_api(request_id):
    """판별 결과 조회"""
    detection_result = DetectionResult.query.filter_by(request_id=request_id).first_or_404()

    return jsonify({
        "status": "success",
        "data": {
            "score": detection_result.score,
            "details": detection_result.detail_json,
            "cached": detection_result.cached,
        },
        "meta": {},
    })


@result_bp.route('/api/v1/stats/<string:content_hash>', methods=['GET'])
def stats_api(content_hash):
    """콘텐츠별 요청 통계 조회 (FR-05)"""
    stats = ContentStats.query.get(content_hash)

    return jsonify({
        "status": "success",
        "data": {"request_count": stats.request_count if stats else 0},
        "meta": {},
    })


@result_bp.route('/result/<int:request_id>/pdf', methods=['GET'])
def download_pdf_report(request_id):
    """분석 결과 PDF 보고서 다운로드 (한국어 대응)"""
    detection_request = DetectionRequest.query.get_or_404(request_id)
    detection_result = DetectionResult.query.filter_by(request_id=request_id).first_or_404()

    pdf_bytes = PDFService().generate_report_pdf(detection_request, detection_result)

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'TruthLens_Report_{request_id}.pdf'
    )
