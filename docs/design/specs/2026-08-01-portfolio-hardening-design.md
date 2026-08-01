# TruthLens 포트폴리오 완성도 설계

작성일: 2026-08-01
목표 독자: 풀스택 신입 채용 담당자 · 기술면접관
기간: 3~5일

## 배경

TruthLens는 이미지·뉴스·논문의 AI 생성 여부를 판별하는 Flask 서비스다. 48개 테스트가 통과하고
계층(`routes → services → ai_models`)도 나뉘어 있어 구조 자체는 문제가 없다.

실사 결과 드러난 진짜 문제는 **문서가 주장하는 것과 코드가 실제로 하는 것의 간극**이다.

| # | 문제 | 근거 |
|---|---|---|
| 1 | Path traversal 취약점 3곳 | `image_routes.py:27`, `video_routes.py:28`, `paper_routes.py:25` — `file.filename`을 sanitize 없이 `os.path.join`에 전달. `secure_filename`이 코드베이스에 한 번도 없음 |
| 2 | 문서-코드 불일치 | `PORTFOLIO.md`는 "라우트→서비스→모델 전 구간 방어"를 주장하나 `image_routes.py`·`video_routes.py`에 `try/except` 없음, 전역 `errorhandler`도 없음 |
| 3 | 500 응답에 내부 예외 노출 | `paper_routes.py`, `news_routes.py`가 `f"...: {e}"`로 예외를 그대로 반환. 자체 규약 `api-contract.md`가 금지한 항목 |
| 4 | 응답 형식 3종 분기 | 판별 API `{status, data, meta}` / 로그인 API `{success, message}` / 규약 문서 `{success, data, error}` |
| 5 | 로깅 부재 | 평문 `basicConfig` 한 줄. `backend/services/` 11개 중 로깅하는 파일 1개 |
| 6 | 핵심 로직이 가장 안 덮임 | `image_detector` 23%, `paper_detector` 25%, `pdf_service` 29%, `article_extractor` 23%. 반면 `backend/models/`는 100% |
| 7 | Tailwind를 CDN으로 로드 | `templates/base.html:7` — 공식 문서가 프로덕션 사용을 금지한 개발용 스크립트 |

포트폴리오 관점에서 1·2·3이 가장 위험하다. 신입 평가에서 보안 기본기 결함과
"문서가 사실이 아님"은 다른 모든 장점을 상쇄한다.

## 성공 기준

숫자로 검증 가능한 것만 둔다.

- [ ] `secure_filename` 미적용 업로드 경로 3 → 0
- [ ] 업로드 확장자 allowlist·용량 상한 존재
- [ ] API 응답 형식 3종 → 1종 (`{success, data, error}`)
- [ ] 에러 응답에 내부 예외 문자열·스택 0건
- [ ] `image_detector.py` 커버리지 23% → 70% 이상, `pixel_heuristics.py` 75% → 90% 이상
- [ ] `PORTFOLIO.md`의 모든 주장이 코드에서 확인 가능
- [ ] GitHub Actions에서 `pytest` 초록

## 범위

**포함**: 보안 수정, 응답 봉투 통일, 구조화 로깅, detector 테스트 보강, 문서 정정, CI, Tailwind 빌드

**제외** (의도적):

- `CLAUDE.md`의 `src/domain` 계층 분리 마이그레이션 — 3,232줄 규모에 클린 아키텍처를 도입하면
  면접에서 "왜 이 규모에 이렇게까지?"라는 역질문을 부른다. 현재 3계층으로 이미 설명 가능하다.
- 영상 판별(FR-01) 모델 실연동 — 기존 판단(로드맵으로 명시) 유지
- 프론트엔드 재설계 — 템플릿 2,461줄이 이미 완성도가 있어 투자 대비 개선폭이 작다

---

## Day 1 — 보안

### `backend/services/upload_service.py` (신규)

```python
def save_upload(file, allowed_ext: set[str]) -> str:
    """업로드 파일을 안전한 경로에 저장하고 저장 경로를 반환한다.

    - secure_filename()으로 경로 구분자·상위 참조 제거
    - 확장자 allowlist 검증 (실패 시 UnsupportedFileType 예외)
    - uuid4 접두어로 파일명 충돌 방지
    """
```

호출부 3곳(`image_routes.py`, `video_routes.py`, `paper_routes.py`)을 이 헬퍼로 교체한다.

**부수 효과**: 현재 같은 이름의 파일을 두 사용자가 올리면 서로 덮어쓰는 버그가 uuid 접두어로 함께 해소된다.

`config.py`에 `MAX_CONTENT_LENGTH`를 추가해 용량 초과는 Flask가 413으로 처리하게 한다
(애플리케이션 코드에서 크기를 세지 않는다).

**검증**: 파일명이 `../../evil.jpg`인 업로드가 `UPLOAD_FOLDER` 밖에 쓰지 않는 테스트, 허용되지 않은
확장자가 400을 받는 테스트.

---

## Day 2 — 응답 봉투 통일

### `backend/api/response.py` (신규)

```python
def ok(data=None, meta=None): ...
    # -> {"success": True, "data": data, "error": None}  (+ meta 있을 때만 포함)

def fail(code: str, message: str, http_status: int): ...
    # -> ({"success": False, "data": None,
    #      "error": {"code": code, "message": message, "traceId": ...}}, http_status)
```

`data`와 `error`는 항상 존재하고 한쪽은 반드시 `null`이다. 실패 응답에 `data`를 채우지 않는다.

### 에러 코드

| 코드 | HTTP | 상황 |
|---|---|---|
| `FILE_REQUIRED` | 400 | 파일 파라미터 누락 |
| `FILE_TYPE_UNSUPPORTED` | 400 | 확장자 allowlist 위반 |
| `INPUT_REQUIRED` | 400 | url/text 둘 다 없음 |
| `TEXT_TOO_LONG` | 400 | 10,000자 초과 |
| `ANALYSIS_FAILED` | 502 | 외부 판별 API 실패 |
| `INTERNAL_ERROR` | 500 | 미처리 예외 |

`ANALYSIS_FAILED`를 502로 두는 이유: 외부 API(Gemini·DeepSeek) 장애는 우리 서버의 버그가 아니라
업스트림 실패이므로, 알림 기준에서 500과 구분되어야 한다.

### 전역 에러 핸들러

`app.py`에 `errorhandler(Exception)`을 등록한다. 스택 트레이스는 `logger.exception`으로
**서버 로그에만** 남기고, 응답에는 `INTERNAL_ERROR` 코드와 `traceId`만 내려보낸다.
현재 `paper_routes.py`·`news_routes.py`가 `{e}`를 노출하는 문제가 여기서 해결된다.

### 동반 수정

| 파일 | 변경 |
|---|---|
| `templates/detect_{image,news,paper,video}.html` | `json.status === 'success'` → `json.success` |
| `templates/login.html:358` | `data.success` 유지하되 `data.error.message`로 메시지 경로 통일 |
| `tests/test_{image,news,paper,video,auth}.py` | 어서션 갱신 |

### 진행 순서

엔드포인트를 **하나씩** 옮기고 매번 `pytest`를 돌린다: 이미지 → 뉴스 → 논문 → 영상 → 로그인.
한 번에 전부 바꾸면 실패 원인을 특정할 수 없다.

---

## Day 3 — 로깅과 테스트

### 구조화 로깅

외부 의존성을 추가하지 않고 stdlib만 쓴다.

```
backend/logging_config.py (신규)
  JsonFormatter(logging.Formatter)   — timestamp/level/message/traceId/service를 JSON으로 출력
  RequestIdFilter(logging.Filter)    — flask.g의 traceId를 모든 레코드에 자동 주입
```

`before_request`에서 `X-Request-Id` 헤더를 받거나 없으면 UUID를 생성해 `flask.g`에 저장한다.
**필터로 주입하는 이유**: 호출부마다 `traceId`를 넘기도록 기대하면 반드시 누락된다.

로그를 남길 지점은 판별 요청 시작·완료(`durationMs` 포함), 캐시 히트/미스, 외부 API 실패로 한정한다.
`DEBUG`는 운영에서 끈다.

### detector 테스트

`image_detector.py`가 표적으로 적합하다 — 외부 API 없이 순수하게 검증 가능하다.

| 대상 | 검증 내용 |
|---|---|
| `_make_summary` | 70/40 임계값 경계에서 문구 분기 (69/70/39/40) |
| `_analyze_exif` | EXIF 있는 파일 / 없는 파일 / 손상 파일의 폴백 |
| `_generate_heatmap` | `data:image/png;base64,` 형식 반환 |
| `pixel_heuristics.analyze_pixel_patterns` | 단색 이미지 / 노이즈 이미지의 점수 방향성 |

테스트 픽스처 이미지는 `PIL`로 코드에서 생성한다(바이너리 커밋 회피).

---

## Day 4 — 문서와 CI

### `PORTFOLIO.md` 정정

검증되지 않는 주장을 걷어내고 Day 1~3에서 **실제로 한 것**으로 교체한다.
특히 "전 구간 방어 로직" 문장은 전역 에러 핸들러 도입 이후에야 사실이 된다.

### GitHub Actions

`push`·`pull_request`마다 `pytest` 실행. `README.md`에 상태 뱃지를 단다.
외부 API 키 없이 통과해야 하므로(현재도 그렇게 설계됨) 시크릿 설정은 불필요하다.

---

## Day 5 — Tailwind와 버퍼

Tailwind CLI 독립 실행 바이너리로 CSS를 빌드해 산출물을 커밋한다.
`node_modules` 없이 정적 파일만 남으므로 Flask 프로젝트 구성을 흐리지 않는다.

**시간이 부족하면 이 항목을 버린다.** 어설픈 빌드 설정보다 `README.md`에
"알려진 한계 — Tailwind CDN 사용 중, 프로덕션 빌드는 로드맵"으로 명시하는 쪽이 낫다.

---

## 테스트 전략

각 Day는 다음을 만족해야 다음으로 넘어간다.

1. `pytest` 48개 + 신규 테스트 전부 통과
2. 앱이 실제로 기동하고 `/detect/image` 시연 플로우가 동작

Day 2는 엔드포인트 단위로 위 검증을 반복한다.

## 리스크와 완화

| 리스크 | 완화 |
|---|---|
| Day 2가 백엔드·프론트·테스트를 동시에 건드려 깨지기 쉬움 | 엔드포인트 하나씩 이동, 매번 `pytest` |
| 시간 부족 | Day 3 테스트 보강을 Day 2 잔여 엔드포인트보다 우선. 절반만 마이그레이션된 API보다 낫다 |
| detector 테스트가 예상보다 오래 걸림 | `image_detector` + `pixel_heuristics`만 목표. `paper_detector`·`pdf_service`는 범위 밖 |

## 롤백

각 Day를 독립 커밋으로 만든다. 문제가 생기면 해당 커밋만 `git revert` 한다.
Day 2만 여러 커밋(엔드포인트별)으로 쪼갠다.
