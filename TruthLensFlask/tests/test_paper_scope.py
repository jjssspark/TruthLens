"""논문 분석 범위 표시 테스트.

긴 논문은 앞부분만 분석되는데, 그 사실이 결과에 남지 않으면
전체를 판정한 것처럼 보인다. 점수 자체보다 이 표시가 더 중요하다.
"""
from unittest.mock import MagicMock, patch

import pytest

from ai_models.paper_detector import (
    MAX_ANALYZED_CHARS,
    PaperDetector,
    build_representative_excerpt,
    strip_references,
    strip_repeated_lines,
)


# --- 참고문헌 제거 ---

def test_strips_reference_section():
    """문서 후반부의 참고문헌 제목 이후를 잘라낸다"""
    body = '\n'.join(f'본문 {i}번째 문장입니다.' for i in range(200))
    refs = 'References\n' + '\n'.join(f'[{i}] Kim, 2020.' for i in range(100))

    result = strip_references(body + '\n' + refs)

    assert 'Kim, 2020' not in result
    assert '본문 199번째' in result


def test_keeps_early_mention_of_references():
    """본문 앞부분의 'References' 언급으로는 자르지 않는다

    서론에서 선행연구를 언급하며 나온 단어까지 자르면 논문 대부분이 사라진다.
    """
    text = 'References\n' + '\n'.join(f'본문 {i}번째 문장입니다.' for i in range(500))

    assert strip_references(text) == text


# --- 반복 줄 제거 ---

def test_strips_repeated_headers_and_page_numbers():
    """페이지마다 반복되는 머리말과 쪽번호를 지운다"""
    pages = []
    for p in range(20):
        pages.append('TruthLens 학술지 제12권')
        pages += [f'{p}쪽 {i}번째 고유 문장입니다.' for i in range(10)]
        pages.append(str(p))

    result = strip_repeated_lines('\n'.join(pages))

    assert 'TruthLens 학술지' not in result
    assert '0쪽 0번째 고유 문장입니다.' in result


def test_skips_stripping_when_it_would_destroy_the_document():
    """반복 줄 제거가 본문 대부분을 지우면 포기하고 원문을 쓴다

    표 행이나 짧은 항목 나열이 많은 논문에서 본문이 통째로 날아가는 것을 막는다.
    """
    text = '\n'.join(['같은 줄입니다.'] * 500)

    assert strip_repeated_lines(text) == text


# --- 균등 발췌 ---

def test_short_text_is_returned_whole():
    """상한보다 짧으면 그대로 쓴다"""
    text = '짧은 논문입니다.'

    assert build_representative_excerpt(text, limit=1000) == (text, 1)


def test_excerpt_covers_beginning_middle_and_end():
    """앞에서만 자르지 않고 서론·본론·결론을 고루 담는다"""
    head = '\n'.join(['서론 문장'] * 2000)
    middle = '\n'.join(['본론 문장'] * 8000)
    tail = '\n'.join(['결론 문장'] * 2000)

    excerpt, segments = build_representative_excerpt(head + middle + tail, limit=5000)

    assert '서론' in excerpt and '본론' in excerpt and '결론' in excerpt
    assert segments > 1
    assert len(excerpt) <= 5000 + 100   # 구분자 여유


def test_excerpt_marks_omitted_gaps():
    """발췌 구간 사이가 이어지지 않음을 표시한다

    표시가 없으면 모델이 끊긴 문장을 비문으로 오인해 점수가 왜곡된다.
    """
    text = '가' * 200000

    excerpt, _ = build_representative_excerpt(text, limit=5000)

    assert '중략' in excerpt


def _fake_response(payload='{"ai_score": 42, "summary": "요약"}'):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = payload
    return response


@pytest.fixture
def detector(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-test-key')
    return PaperDetector()


def test_short_paper_is_analyzed_in_full(detector):
    """상한보다 짧은 논문은 본문 전체를 분석하고 그렇게 표시한다"""
    text = '\n'.join(f'{i}번째 고유 문장입니다.' for i in range(50))

    with patch.object(detector.client.chat.completions, 'create', return_value=_fake_response()):
        result = detector.analyze_with_gpt(text)

    assert result["truncated"] is False
    assert result["analyzed_chars"] == len(text)
    assert '본문 전체' in PaperDetector._scope_note(result)


def test_long_paper_reports_sampling(detector):
    """상한을 넘으면 발췌 사실과 비율을 밝힌다"""
    text = '\n'.join(f'{i}번째 고유 문장으로 서로 다른 내용입니다.' for i in range(20000))

    with patch.object(detector.client.chat.completions, 'create', return_value=_fake_response()):
        result = detector.analyze_with_gpt(text)

    assert result["truncated"] is True
    assert result["segments"] > 1
    assert result["total_chars"] == len(text)
    assert result["analyzed_chars"] < result["body_chars"]

    note = PaperDetector._scope_note(result)
    assert '고르게 뽑아' in note
    assert '반영되지 않았습니다' in note


def test_document_tail_reaches_the_model(detector):
    """문서 끝부분도 실제로 전송된다

    앞에서만 자르던 이전 동작에서는 결론·고찰이 통째로 빠졌다.
    이 테스트가 그 회귀를 막는다.
    """
    filler = '\n'.join(f'{i}번째 본문 문장입니다.' for i in range(20000))
    text = filler + '\n' + '\n'.join(['결론부표식 문장입니다.'] * 3)

    with patch.object(detector.client.chat.completions, 'create',
                      return_value=_fake_response()) as mock_create:
        detector.analyze_with_gpt(text)

    sent_prompt = mock_create.call_args.kwargs['messages'][0]['content']
    assert '결론부표식' in sent_prompt


def test_failed_analysis_is_not_stored_as_a_zero_score(app, logged_in_client):
    """분석 실패를 'AI 생성 0%'라는 판정으로 저장하지 않는다

    판별기는 실패를 예외 대신 details.error + score 0으로 돌려준다.
    그대로 두면 사용자에게는 정상 판정처럼 보이고, 캐시에까지 들어가
    재시도해도 같은 0%가 나온다.
    """
    import io

    from backend.models.detection_request import DetectionRequest
    from backend.models.detection_result import DetectionResult

    failure = {"score": 0, "details": {"error": "DeepSeek API 잔액이 부족합니다.",
                                       "section_scores": {}, "suspicious_paragraphs": [],
                                       "summary": "", "key_claims": []}}

    with patch.object(PaperDetector, 'detect', return_value=failure), \
            patch('backend.services.paper_service.set_cached_result') as mock_cache:
        response = logged_in_client.post(
            '/api/v1/detect/paper',
            data={'file': (io.BytesIO(b'%PDF-1.4 fake'), 'paper.pdf')},
            content_type='multipart/form-data',
        )

    body = response.get_json()
    assert response.status_code == 502
    assert body["error"]["code"] == "ANALYSIS_FAILED"
    assert '잔액' in body["error"]["message"]

    mock_cache.assert_not_called()

    with app.app_context():
        assert DetectionResult.query.count() == 0
        assert DetectionRequest.query.first().status == 'failed'


def test_detect_surfaces_scope_in_details():
    """detect() 결과의 details에 분석 범위가 실린다"""
    analysis = {
        "ai_score": 42, "summary": "요약",
        "analyzed_chars": MAX_ANALYZED_CHARS, "total_chars": MAX_ANALYZED_CHARS * 3,
        "truncated": True,
    }

    with patch.object(PaperDetector, 'extract_text_from_pdf', return_value='가' * 100), \
            patch.object(PaperDetector, 'analyze_with_gpt', return_value=analysis), \
            patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'sk-test-key'}):
        details = PaperDetector().detect('dummy.pdf')["details"]

    assert details["truncated"] is True
    assert details["analyzed_chars"] == MAX_ANALYZED_CHARS
    assert '반영되지 않았습니다' in details["scope_note"]
