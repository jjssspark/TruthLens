import hashlib
import io
import os
from pathlib import Path

import requests
from flask import Blueprint, current_app, render_template, request
from flask import session, redirect, url_for
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.api.response import ok
from backend.models.database import db
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult
from ai_models import video_detector as vd
from ai_models.hf_deepfake_client import HF_ROUTER_URL, IMAGE_ENSEMBLE_MODELS

main_bp = Blueprint('main', __name__)

# 점수가 이 값 이상이면 AI 생성으로 본다 (image_detector._make_summary와 같은 기준)
AI_SCORE_THRESHOLD = 70


@main_bp.route('/health', methods=['GET'])
def health():
    """프로세스가 살아있는지만 본다. 의존성은 확인하지 않는다.

    외부 모니터링(UptimeRobot 등)이 찌르는 대상. DB 조회를 넣으면 DB가 잠깐
    느릴 때 앱이 죽은 것으로 오인된다. 그 판단은 /ready가 한다.
    """
    return {'status': 'ok'}, 200


@main_bp.route('/ready', methods=['GET'])
def ready():
    """DB까지 붙는지 확인한다. 실패하면 503."""
    try:
        db.session.execute(text('SELECT 1'))
    except SQLAlchemyError:
        current_app.logger.exception(
            "readiness 확인 실패", extra={"event": "health.ready.failed"}
        )
        return {'status': 'unavailable'}, 503
    return {'status': 'ready'}, 200


# 지문을 뜨는 대상. 판별 동작을 결정하는 파일만 넣는다.
_FINGERPRINT_SOURCES = (
    'ai_models/video_detector.py',
    'ai_models/image_detector.py',
    'ai_models/hf_deepfake_client.py',
)


def _source_fingerprint():
    """배포된 소스의 지문. 재빌드가 실제로 새 코드를 가져왔는지 가린다.

    커밋 해시를 쓰려면 빌드 인자를 넘겨야 하는데, 그건 배포 플랫폼 설정에
    의존한다. 파일 내용을 직접 해싱하면 아무 설정 없이도 코드가 바뀌면 바뀐다.
    """
    root = Path(current_app.root_path)
    digest = hashlib.sha256()
    for relative in _FINGERPRINT_SOURCES:
        path = root / relative
        digest.update(path.read_bytes() if path.exists() else b'missing')
    return digest.hexdigest()[:12]


def _probe_hf(token):
    """앙상블 모델을 하나씩 실제로 찔러 상태를 확인한다.

    모델마다 따로 본다. 크레딧 소진은 제공자별로 일어나서, 하나가 402여도
    나머지로 판정이 돌아간다(실측: 3개 중 1개만 402). "되냐 안 되냐"로
    뭉뚱그리면 지금 몇 개로 판정하고 있는지 알 수 없다.

    모델 수만큼 호출하므로 ?probe=1을 명시했을 때만 부른다.
    """
    from PIL import Image

    buffer = io.BytesIO()
    Image.new('RGB', (32, 32), (128, 128, 128)).save(buffer, format='JPEG')
    payload = buffer.getvalue()

    states = {
        200: ('ok', '정상'),
        401: ('invalid_token', 'HF_TOKEN이 잘못됐습니다'),
        402: ('credit_exhausted', '월간 추론 크레딧 소진'),
        429: ('rate_limited', '호출이 너무 잦습니다'),
    }

    results = {}
    for model in IMAGE_ENSEMBLE_MODELS:
        try:
            response = requests.post(
                HF_ROUTER_URL.format(model=model),
                headers={'Authorization': f'Bearer {token}',
                         'Content-Type': 'image/jpeg'},
                data=payload,
                timeout=15,
            )
        except requests.RequestException as e:
            results[model] = {'state': 'unreachable',
                              'message': f'닿지 못했습니다: {type(e).__name__}'}
            continue
        state, message = states.get(
            response.status_code,
            ('unknown', f'예상하지 못한 응답({response.status_code})'),
        )
        results[model] = {'http_status': response.status_code,
                          'state': state, 'message': message}

    usable = sum(1 for r in results.values() if r.get('state') == 'ok')
    total = len(IMAGE_ENSEMBLE_MODELS)
    if usable == total:
        summary = f'앙상블 {total}개 모두 정상입니다.'
    elif usable >= 2:
        summary = (f'{total}개 중 {usable}개로 동작 중입니다. '
                   '중앙값을 낼 수는 있지만 다수결이 약해집니다.')
    elif usable == 1:
        summary = (f'{total}개 중 1개만 살아 있습니다. '
                   '중앙값이 그 모델 하나의 판정과 같아집니다.')
    else:
        summary = '쓸 수 있는 모델이 없어 로컬 픽셀 휴리스틱으로 동작합니다.'

    return {'checked': True, 'usable': usable, 'total': total,
            'summary': summary, 'models': results}


@main_bp.route('/diagnostics', methods=['GET'])
def diagnostics():
    """배포본이 어떤 코드로 무엇을 할 수 있는 상태인지 한 화면에 보여준다.

    이게 없어서 두 번 헤맸다. 한 번은 새 코드가 배포된 줄 알고 엉뚱한 곳을
    범인으로 지목했고(TS-24), 한 번은 토큰이 죽어 판별 품질이 내려간 것을
    로직 문제로 봤다(TS-25). 둘 다 로그를 뒤져야만 알 수 있었다.

    비밀값은 담지 않는다. 설정 여부만 불리언으로 준다.
    """
    token = (os.getenv('HF_TOKEN') or '').strip()

    hf = {'checked': False,
          'hint': '?probe=1 을 붙이면 실제로 한 번 호출해 확인합니다(크레딧 1회 소모).'}
    if request.args.get('probe') == '1':
        hf = _probe_hf(token) if token else {
            'checked': True, 'state': 'no_token',
            'message': 'HF_TOKEN이 설정되지 않았습니다.',
        }

    return ok({
        'code': {
            'fingerprint': _source_fingerprint(),
            # 이 값들이 옛 배포본과 다르면 재빌드가 반영된 것이다
            'video': {
                'sampled_frames': vd.MAX_SAMPLED_FRAMES,
                'model_frames': vd.MAX_MODEL_FRAMES,
                'call_timeout_sec': vd.MODEL_CALL_TIMEOUT_SEC,
                'aggregation': 'median',
                'experimental': True,
                'measured_accuracy': vd.MEASURED_ACCURACY,
                'ensemble_models': list(IMAGE_ENSEMBLE_MODELS),
            },
        },
        'keys': {
            'HF_TOKEN': bool(token),
            'GEMINI_API_KEY': bool(os.getenv('PAPER_API_KEY') or os.getenv('GEMINI_API_KEY')),
        },
        'hf': hf,
    })


@main_bp.route('/', methods=['GET'])
def index():
    """메인(홈) 화면: 서비스 소개, 판별 유형 선택, 내 최근 분석 이력"""
    user_id = session.get('user_id')

    recent = (
        db.session.query(DetectionRequest, DetectionResult)
        .outerjoin(DetectionResult, DetectionResult.request_id == DetectionRequest.id)
        .filter(DetectionRequest.user_id == user_id)
        .order_by(DetectionRequest.created_at.desc())
        .limit(4)
        .all()
    )

    ai_detected = (
        db.session.query(DetectionResult)
        .join(DetectionRequest, DetectionResult.request_id == DetectionRequest.id)
        .filter(
            DetectionRequest.user_id == user_id,
            DetectionResult.score >= AI_SCORE_THRESHOLD,
        )
        .count()
    )

    return render_template(
        'index.html',
        recent=recent,
        total_scans=DetectionRequest.query.filter_by(user_id=user_id).count(),
        ai_detected=ai_detected,
        # 카드 배지가 실제 설정 상태를 말하게 한다. 키가 없는데 "연동됨"으로
        # 보이거나, 연동해두고 "예정"으로 남아 있으면 둘 다 거짓말이 된다.
        configured_keys={
            # 뉴스와 논문이 같은 키를 쓴다 — 논문 판별을 DeepSeek에서 Gemini로 옮겼다.
            'GEMINI_API_KEY': bool(os.getenv('PAPER_API_KEY') or os.getenv('GEMINI_API_KEY')),
            'HF_TOKEN': bool(os.getenv('HF_TOKEN')),
        },
    )


@main_bp.route('/history', methods=['GET'])
def history():
    """판별 이력: 로그인한 유저의 요청 목록 (최근 20건)"""
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    requests = DetectionRequest.query.filter_by(user_id=session['user_id']).order_by(DetectionRequest.created_at.desc()).limit(20).all()
    return render_template('history.html', requests=requests)

@main_bp.route('/login', methods=['GET'])
def login():
    """로그인 / 회원가입 화면"""
    return render_template('login.html')




