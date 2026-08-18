"""배포본 상태를 밖에서 확인할 수 있어야 한다.

이 엔드포인트가 없어서 두 번 헤맸다. 한 번은 새 코드가 배포된 줄 알고 엉뚱한
곳을 범인으로 지목했고(TS-24), 한 번은 토큰이 죽어 판별 품질이 내려간 것을
로직 문제로 봤다(TS-25).
"""
from unittest.mock import patch

import pytest

import ai_models.video_detector as vd
from ai_models.hf_deepfake_client import IMAGE_ENSEMBLE_MODELS


def test_diagnostics_is_reachable_without_login(client):
    """로그인을 요구하면 정작 뭔가 잘못됐을 때 못 본다."""
    response = client.get('/diagnostics')

    assert response.status_code == 200
    assert response.get_json()['success'] is True


def test_diagnostics_reports_running_code_settings(client):
    """재빌드가 새 코드를 가져왔는지 이 값들로 가린다."""
    data = client.get('/diagnostics').get_json()['data']

    assert data['code']['fingerprint']
    video = data['code']['video']
    assert video['sampled_frames'] == vd.MAX_SAMPLED_FRAMES
    assert video['model_frames'] == vd.MAX_MODEL_FRAMES
    assert video['call_timeout_sec'] == vd.MODEL_CALL_TIMEOUT_SEC
    assert video['experimental'] is True
    assert video['ensemble_models'] == list(IMAGE_ENSEMBLE_MODELS)


def test_fingerprint_changes_when_detection_code_changes(client, monkeypatch, tmp_path):
    """지문이 코드 변경을 실제로 반영해야 의미가 있다."""
    before = client.get('/diagnostics').get_json()['data']['code']['fingerprint']

    import backend.routes.main_routes as routes
    monkeypatch.setattr(routes, '_FINGERPRINT_SOURCES', ('ai_models/base_detector.py',))
    after = client.get('/diagnostics').get_json()['data']['code']['fingerprint']

    assert before != after


def test_diagnostics_never_leaks_secret_values(client, monkeypatch):
    """설정 여부만 준다. 값은 절대 담지 않는다."""
    monkeypatch.setenv('HF_TOKEN', 'hf_super-secret-value')

    body = client.get('/diagnostics').get_data(as_text=True)

    assert 'hf_super-secret-value' not in body
    assert body.count('true') >= 1


def test_probe_is_skipped_unless_requested(client):
    """크레딧을 쓰는 호출이라 명시했을 때만 부른다."""
    hf = client.get('/diagnostics').get_json()['data']['hf']

    assert hf['checked'] is False
    assert 'probe=1' in hf['hint']


def test_probe_reports_each_model_separately(client, monkeypatch):
    """크레딧 소진은 제공자별로 일어난다. 하나가 죽어도 나머지로 판정이 돈다."""
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')
    dead = IMAGE_ENSEMBLE_MODELS[-1]

    class _Response:
        def __init__(self, status):
            self.status_code = status

    def _post(url, **kwargs):
        return _Response(402 if dead in url else 200)

    with patch('backend.routes.main_routes.requests.post', side_effect=_post):
        hf = client.get('/diagnostics?probe=1').get_json()['data']['hf']

    assert hf['usable'] == len(IMAGE_ENSEMBLE_MODELS) - 1
    assert hf['models'][dead]['state'] == 'credit_exhausted'
    assert '2개로 동작' in hf['summary']


def test_probe_says_heuristic_when_nothing_works(client, monkeypatch):
    """모델이 다 죽으면 휴리스틱으로 떨어진다는 사실을 명시한다."""
    monkeypatch.setenv('HF_TOKEN', 'hf_test-token')

    class _Response:
        status_code = 402

    with patch('backend.routes.main_routes.requests.post', return_value=_Response()):
        hf = client.get('/diagnostics?probe=1').get_json()['data']['hf']

    assert hf['usable'] == 0
    assert '휴리스틱' in hf['summary']


def test_probe_without_token_says_so(client, monkeypatch):
    """토큰이 없는 것과 크레딧이 없는 것은 다른 문제다."""
    monkeypatch.delenv('HF_TOKEN', raising=False)

    hf = client.get('/diagnostics?probe=1').get_json()['data']['hf']

    assert hf['state'] == 'no_token'
