import os

import pytest

from backend.services import pdf_service
from backend.services.pdf_service import KoreanFontUnavailable, PDFService


def test_resolves_a_font_file_that_exists(app):
    """폰트 확보에 성공하면 실제 존재하는 파일 경로를 갖는다"""
    with app.test_request_context():
        service = PDFService()

    assert os.path.exists(service.font_path)


def test_prefers_system_font_over_download(app, monkeypatch):
    """시스템 폰트가 있으면 네트워크를 타지 않는다

    다운로드는 SSL·네트워크·저장소 가용성에 모두 의존해 실패하기 쉽다.
    실제로 이 경로가 조용히 실패해 한글이 전부 네모로 나온 적이 있다.
    """
    def _fail(self):
        raise AssertionError("시스템 폰트가 있는데 다운로드를 시도했다")

    monkeypatch.setattr(PDFService, '_download_fonts', _fail)

    with app.test_request_context():
        service = PDFService()

    assert os.path.exists(service.font_path)


def test_raises_when_no_korean_font_is_available(app, monkeypatch):
    """폰트를 못 찾으면 깨진 PDF를 만들지 않고 명확히 실패한다"""
    monkeypatch.setattr(pdf_service, 'SYSTEM_FONT_CANDIDATES', [])
    monkeypatch.setattr(PDFService, '_download_fonts', lambda self: False)

    with app.test_request_context():
        with pytest.raises(KoreanFontUnavailable):
            PDFService()


def test_report_embeds_the_korean_font(app):
    """생성된 PDF에 한글 폰트가 임베드된다 (Helvetica만 남으면 네모가 된다)"""
    from backend.models.database import db
    from backend.models.detection_request import DetectionRequest
    from backend.models.detection_result import DetectionResult

    with app.test_request_context():
        request = DetectionRequest(user_id=1, content_hash='hash-pdf', type='image', status='done')
        db.session.add(request)
        db.session.commit()

        result = DetectionResult(
            request_id=request.id,
            score=39.0,
            detail_json={'summary': 'AI와 사람이 혼합된 이미지로 보입니다',
                         'exif': {'has_exif': False, 'suspicious': True}},
            cached=False,
        )
        db.session.add(result)
        db.session.commit()

        service = PDFService()
        pdf = service.generate_report_pdf(request, result)

    raw = pdf if isinstance(pdf, bytes) else pdf.read()
    font_name = os.path.splitext(os.path.basename(service.font_path))[0].encode()

    assert raw.startswith(b'%PDF')
    assert font_name in raw
