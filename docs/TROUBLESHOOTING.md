# 트러블슈팅

5일간 포트폴리오 고도화 과정에서 실제로 마주친 버그를 증상 → 원인 → 해결 형식으로 정리했습니다.
각 항목은 실제로 재현 후 수정한 것입니다.

### 1. 테스트 8개 실패 (신규 clone 직후)
- 증상: `pytest` 실행 시 31개 중 8개 실패.
- 원인: (1) request context 밖에서 `session`에 접근하는 코드 2건, (2) 리팩토링 이후 갱신되지 않은 stale assertion 4건, (3) 로컬 환경에 API 키가 없어서 실패하는 테스트 2건.
- 해결: 각 원인별로 개별 수정. API 키가 필요한 테스트는 목(mock) 처리로 전환.

### 2. `PaperDetector` 생성자 크래시로 앱 전체가 죽음
- 증상: `DEEPSEEK_API_KEY`가 없는 환경에서 앱을 실행하면 논문 판별 기능뿐 아니라 서버 자체가 부팅되지 않음.
- 원인: API 키 검증을 `PaperDetector.__init__()`(생성자)에서 수행하고 있어, 블루프린트 등록 시점에 즉시 예외가 발생.
- 해결: 키 검증을 실제 호출 시점(`detect()`)으로 이동. 키가 없으면 해당 기능만 에러를 반환하고 앱은 정상 구동(graceful degradation).

### 3. 평문 비밀번호 저장/비교
- 증상: 로그인 시 `password_hash != password`로 평문 비교.
- 원인: 비밀번호 해싱이 아예 적용되지 않은 초기 구현.
- 해결: `werkzeug.security`의 `generate_password_hash`/`check_password_hash`로 교체.

### 4. `db.create_all()` 순서 버그
- 증상: SQLite 로컬 실행 시 일부 테이블이 생성되지 않음.
- 원인: 블루프린트(모델) import 이전에 `db.create_all()`이 호출되어, 일부 모델이 SQLAlchemy 메타데이터에 아직 등록되지 않은 상태였음.
- 해결: `register_blueprints(app)` 이후로 `db.create_all()` 호출 순서를 재배치.

### 5. 뉴스/논문 라우트가 서비스 예외를 감싸지 않음
- 증상: 잘못된 URL 입력 등으로 `NewsService.analyze()`가 `ValueError`를 던지면, 사용자에게 JSON 에러 대신 Flask 기본 500 HTML 에러 페이지가 노출됨.
- 원인: 모델(detector) 레벨은 예외를 잘 감싸 `{"score":0,"details":{"error":...}}` 형태로 응답하지만, 그 앞단인 서비스/라우트 레이어(기사 추출 실패, PDF 파싱 실패, DB 커밋 실패 등)는 보호되지 않았음.
- 해결: 라우트에서 `ValueError`→400, 그 외 예외→500 JSON으로 응답하도록 try/except 추가. `PaperDetector.detect()`의 PDF 파싱도 동일하게 방어.

### 6. DeepSeek 402(잔액 부족) 원본 에러가 그대로 노출
- 증상: 실제 API 키로 논문 판별 테스트 중 DeepSeek 계정 잔액 부족(402)이 발생했는데, `details.error`에 DeepSeek 원본 JSON 문자열이 그대로 노출됨.
- 원인: 뉴스 판별(`news_detector.py`)에는 이미 있던 "친화적 에러 메시지 변환" 패턴이 논문 판별 쪽에는 없었음.
- 해결: `paper_detector.py`에 `_friendly_error_message()`를 추가해 402/429/401을 한국어 메시지로 변환. 원본 에러는 서버 로그(`logger.error`)에만 남김. Mock이 아닌 실 API로 테스트했기 때문에 발견할 수 있었던 케이스.

### 7. 커밋 실패 시 `db.session.rollback()` 누락
- 증상: 없음(잠재적 버그) — commit이 실패하면 세션이 dirty 상태로 남아 이후 쿼리까지 연쇄 실패할 수 있는 상황.
- 원인: `news_service.py`, `paper_service.py`, `citation_service.py`의 commit 지점에 rollback 처리가 없었음(`auth/routes.py`에는 이미 있었음).
- 해결: 모든 commit 지점에 `except: db.session.rollback(); raise` 패턴을 일관 적용.

### 8. 320px 모바일에서 결과 게이지가 카드 밖으로 넘칠 뻔함
- 증상: `result.html`의 `.gauge-container`가 `width: 280px` 고정인데, 이를 감싸는 `.glass-card`(`p-8`, 좌우 64px)와 페이지 패딩(좌우 32px)을 더하면 최소 지원폭 320px에서 `320 - 32 - 64 = 224px`만 남아 280px 게이지가 들어갈 수 없었음.
- 원인: 게이지를 데스크탑 기준 고정 픽셀로 설계하고 모바일 대응을 별도 검증하지 않음.
- 해결: `width: min(280px, 100%)` + `aspect-ratio: 2/1`로 변경, 카드 패딩도 모바일에서 `p-6`으로 축소. 페이지 패딩 + 카드 패딩 + 고정폭 요소를 직접 더해보는 산수 검증이 스크린샷보다 빠르고 확실했음.

### 9. 뉴스 판별 실 API(Gemini) 테스트 중 개발 샌드박스의 DNS 접근 제한
- 증상: `generativelanguage.googleapis.com`을 resolve하지 못해 600초 타임아웃 발생.
- 원인: 개발 샌드박스 환경의 아웃바운드 네트워크 제약(추정).
- 해결: 별도 수정 불필요 — 5번 항목에서 추가한 예외 처리 덕분에 서버가 죽지 않고 "분석 실패"로 200 응답을 정상 반환하는 것을 확인. 오히려 그 방어 로직이 예상 밖의 실패 모드(API 요금이 아닌 네트워크 장애)에서도 동작함을 재검증한 계기.

### 10. `uploads/`에 실제 파일이 커밋되어 있었음
- 증상: `.gitignore`에 `uploads/*` 규칙이 있는데도 이미지·PDF 파일 2개가 git 이력에 남아 있음.
- 원인: gitignore 규칙 추가 이전에 먼저 커밋된 파일이라 규칙이 소급 적용되지 않음(gitignore는 신규 추적 파일에만 적용).
- 해결: `git rm --cached`로 추적만 해제(로컬 파일은 유지). 이후 신규 업로드는 정상적으로 무시됨.

### 11. SQLAlchemy 컬럼 default에 `datetime.utcnow()`(호출)를 쓰면 안 되는 이유와 deprecation 정리
- 증상: `datetime.utcnow()` 사용 시 `DeprecationWarning` 다수 발생.
- 원인: Python 3.12+에서 `datetime.utcnow()`가 deprecated. 대체품인 `datetime.now(timezone.utc)`는 aware datetime이라 DB의 naive `DATETIME` 컬럼과 그대로 섞으면 저장/비교 시 타입 불일치가 날 수 있음.
- 해결: `backend/models/database.py`에 `datetime.now(timezone.utc).replace(tzinfo=None)`을 반환하는 `utcnow()` 헬퍼를 추가해 기존 naive UTC 동작을 그대로 유지하며 교체. SQLAlchemy 컬럼 default는 호출이 아닌 함수 참조를 받는다는 기존 패턴(`default=datetime.utcnow` → `default=utcnow`)도 그대로 보존.

### 12. `docker compose up`이 13일 전 이미지를 재사용해 최신 커밋이 반영되지 않음
- 증상: 전날 커밋한 UI 변경(로그인 방식 변경, 다크 테마 전환)이 로컬 실행 화면에 전혀 반영되지 않음.
- 원인: `docker-compose.yml`의 `app` 서비스가 소스를 볼륨 마운트하지 않고 `Dockerfile`의 `COPY . .`로 빌드 시점 코드를 이미지에 굽는 구조. `docker compose up`은 이미지가 로컬에 이미 존재하면 재빌드하지 않는데, 로컬 이미지가 13일 전 빌드본이었음(`docker images` 생성 시각과 `git log` 커밋 시각을 대조해 확인).
- 해결: `docker compose up --build`로 재빌드. `docs/DEMO.md`의 실행 안내를 `--build` 포함 명령으로 갱신해 재발을 막음.
