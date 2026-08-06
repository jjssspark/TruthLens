import os

import pytest

from backend.services import pdf_service
from backend.services.pdf_service import KoreanFontUnavailable, PDFService


@pytest.fixture(autouse=True)
def _clear_font_cache(app):
    """PDFService가 앱 루트의 cache/에 받아두는 폰트 파일을 매 테스트 전에 지운다.

    캐시가 남아 있으면 _locate_fonts()가 1순위로 그 캐시를 재사용해, 이후
    테스트가 시스템 폰트/다운로드 monkeypatch를 타지 않고 이전 테스트가
    받아둔 파일을 그대로 쓰게 되어 실행 순서에 따라 결과가 달라졌다.
    """
    cache_dir = os.path.join(app.root_path, "cache")
    for name in ("NanumGothic-Regular.ttf", "NanumGothic-Bold.ttf"):
        path = os.path.join(cache_dir, name)
        if os.path.exists(path):
            os.remove(path)
    yield


def test_resolves_a_font_file_that_exists(app):
    """폰트 확보에 성공하면 실제 존재하는 파일 경로를 갖는다"""
    with app.test_request_context():
        service = PDFService()

    assert os.path.exists(service.font_path)


def test_prefers_system_font_over_download(app, monkeypatch):
    """시스템 폰트가 있으면 네트워크를 타지 않는다

    다운로드는 SSL·네트워크·저장소 가용성에 모두 의존해 실패하기 쉽다.
    실제로 이 경로가 조용히 실패해 한글이 전부 네모로 나온 적이 있다.

    CI(ubuntu-latest)에는 나눔고딕 등 한글 폰트가 설치돼 있지 않아
    SYSTEM_FONT_CANDIDATES가 실제로는 항상 비어있는 것처럼 동작한다.
    "시스템 폰트가 있을 때"를 검증하려면 실제 존재를 보장할 수 있는
    폰트가 필요해, reportlab이 자체 내장한 Vera.ttf를 후보로 주입한다
    (한글 글리프는 없지만 이 테스트는 파일 탐색 우선순위만 검증한다).
    """
    import reportlab
    vera_path = os.path.join(os.path.dirname(reportlab.__file__), "fonts", "Vera.ttf")
    monkeypatch.setattr(pdf_service, 'SYSTEM_FONT_CANDIDATES', [(vera_path, None, None)])

    def _fail(self):
        raise AssertionError("시스템 폰트가 있는데 다운로드를 시도했다")

    monkeypatch.setattr(PDFService, '_download_fonts', _fail)

    with app.test_request_context():
        service = PDFService()

    assert service.font_path == vera_path


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

    assert raw.startswith(b'%PDF')
    # 어떤 한글 폰트가 잡히는지는 OS마다 다르다(macOS는 AppleGothic, CI는 NanumGothic).
    # 폰트 패밀리 이름으로 검사하면 환경에 따라 실패하므로 불변식으로 검사한다:
    # 표준 14종(Helvetica 등)은 절대 임베드되지 않으므로, /FontFile2가 있다는 것은
    # TrueType 폰트가 실제로 PDF에 박혔다는 뜻이다. 이게 없으면 한글이 네모로 나온다.
    assert b'/FontFile2' in raw
