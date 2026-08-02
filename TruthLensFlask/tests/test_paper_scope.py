"""논문 분석 범위 표시 테스트.

긴 논문은 앞부분만 분석되는데, 그 사실이 결과에 남지 않으면
전체를 판정한 것처럼 보인다. 점수 자체보다 이 표시가 더 중요하다.
"""
from unittest.mock import MagicMock, patch

import pytest

from ai_models.paper_detector import MAX_ANALYZED_CHARS, PaperDetector


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
    """상한보다 짧은 논문은 전문을 분석하고 그렇게 표시한다"""
    text = '가' * 1000

    with patch.object(detector.client.chat.completions, 'create', return_value=_fake_response()):
        result = detector.analyze_with_gpt(text)

    assert result["truncated"] is False
    assert result["analyzed_chars"] == 1000
    assert result["total_chars"] == 1000
    assert '전문' in PaperDetector._scope_note(result)


def test_long_paper_reports_truncation(detector):
    """상한을 넘으면 잘린 사실과 비율을 밝힌다"""
    text = '가' * (MAX_ANALYZED_CHARS * 2)

    with patch.object(detector.client.chat.completions, 'create', return_value=_fake_response()):
        result = detector.analyze_with_gpt(text)

    assert result["truncated"] is True
    assert result["analyzed_chars"] == MAX_ANALYZED_CHARS
    assert result["total_chars"] == MAX_ANALYZED_CHARS * 2

    note = PaperDetector._scope_note(result)
    assert '앞' in note and '50%' in note
    assert '반영되지 않았습니다' in note


def test_only_the_analyzed_prefix_is_sent(detector):
    """상한을 넘는 부분은 실제로 전송되지 않는다"""
    text = '가' * MAX_ANALYZED_CHARS + '뒷부분표식' * 100

    with patch.object(detector.client.chat.completions, 'create',
                      return_value=_fake_response()) as mock_create:
        detector.analyze_with_gpt(text)

    sent_prompt = mock_create.call_args.kwargs['messages'][0]['content']
    assert '뒷부분표식' not in sent_prompt


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
