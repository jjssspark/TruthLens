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

### 13. PDF 한글 폰트 테스트가 macOS에서만 실패
- 증상: CI(Linux)와 GitHub Actions는 통과하는데 로컬 macOS에서만 `test_report_embeds_the_korean_font`가 실패. `assert b'NanumGothic' in raw`에서 어긋남.
- 원인(표면): 어설션이 `PDFService.FONT_NAME`('NanumGothic')이 PDF 바이트에 있는지를 검사함.
- 원인(근본): 어설션 위 주석은 "pdfmetrics에 등록한 폰트 이름으로 참조하므로 이걸로 검사해야 한다"고 적혀 있었으나, 실제로 PDF에 박히는 문자열은 **임베드된 폰트 파일의 내부 PostScript 이름**이다. `_locate_fonts()`는 시스템 폰트를 우선하므로 macOS에서는 `/System/Library/Fonts/Supplemental/AppleGothic.ttf`가 잡히고, 등록명은 'NanumGothic'이어도 PDF에는 'AppleGothic'이 남는다. CI에서는 나눔고딕이 잡혀 두 이름이 우연히 일치해 통과했던 것.
- 시도했지만 안 된 방향: 처음엔 폰트 캐시나 다운로드 폴백 문제로 의심했으나, 로그(`{"event": "pdf.font.system", "message": "시스템 한글 폰트 사용: .../AppleGothic.ttf"}`)에서 폰트 확보 자체는 정상임을 확인해 방향을 바꿈.
- 해결: 환경마다 달라지는 폰트 패밀리 이름 대신 불변식으로 검사하도록 변경. 표준 14종(Helvetica 등)은 절대 임베드되지 않으므로 `assert b'/FontFile2' in raw`로 "TrueType 폰트가 실제로 PDF에 박혔는지"를 확인한다. 이게 없으면 한글이 네모로 나오므로 원래 지키려던 의도와 동일하다.
- 검증: macOS 로컬 `pytest -q` 135건 전부 통과.

### 14. 배포본이 느린 원인이 서버가 아니라 브라우저에서 CSS를 컴파일하고 있었던 것
- 증상: 배포 사이트 접속 시 체감상 버벅임. 스타일이 입혀지기 전 화면이 잠깐 깨져 보임.
- 재현 조건: 배포본 아무 페이지나 접속. 로컬에서는 잘 안 느껴짐(회선이 빨라서).
- 원인(표면): 서버 응답은 정상이었음. `curl` 측정 결과 TTFB 45~230ms, HTML 21KB.
- 원인(근본): 모든 템플릿이 `<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries">`(Tailwind **Play CDN**)를 쓰고 있었음. 이건 CSS 파일이 아니라 **브라우저에서 DOM을 스캔해 CSS를 실시간 생성하는 419KB짜리 JIT 컴파일러**다. Tailwind 공식 문서가 프로덕션 사용을 금지한 물건. 여기에 `lh3.googleusercontent.com`의 외부 이미지 326KB가 더해져 로그인 페이지 한 장이 788KB였음.
- 시도했지만 안 된 방향: 처음엔 클라우드타입 프리티어의 5Mbps 대역폭 제한을 의심했음. 같은 21KB HTML이 어떤 요청에선 1.37초가 걸렸기 때문. 하지만 무거운 자원이 전부 외부 CDN(클라우드타입 대역폭을 안 씀)이라 이 가설로는 설명이 안 됐고, 자원별로 개별 측정하고 나서야 Play CDN이 범인임을 확인함.
- 해결:
  1. Tailwind v3.4 CLI로 사전 빌드해 정적 CSS로 교체(419KB JS → 31KB CSS). Play CDN이 v3이므로 **v4가 아닌 v3으로 고정**해야 기본값이 안 바뀜.
  2. 외부 이미지 3장을 `static/img/*.webp`로 내재화(1,034KB → 42KB). 원본이 `aida-public` 임시 URL이라 만료되면 이미지가 깨질 위험도 함께 제거.
  3. Google Fonts 요청 2회를 1회로 합치고 `preconnect` 추가.
- 이 과정에서 밟을 뻔한 함정 3가지:
  - **`login.html`은 `fontSize` 정의가 없는 별도 설정을 쓰고 있었다.** `text-body-sm` 등 25곳이 현재 아무 효과 없이 죽어 있는 상태. 두 설정을 하나로 합쳐 빌드했다면 이것들이 살아나 글자 크기가 바뀌었을 것. 그래서 CSS를 `tailwind.base.css` / `tailwind.login.css` 두 벌로 분리함.
  - **Play CDN은 스타일을 `<head>` 맨 끝에 주입한다.** 즉 `index.css`와 작성자 인라인 `<style>`보다 뒤에 온다. `<link>`를 원래 스크립트 자리에 넣었다면 우선순위가 뒤집혀 디자인이 바뀌었을 것. 실제 배포본 DOM을 열어 주입 위치를 확인한 뒤 `</head>` 직전에 배치.
  - **`--minify`가 색을 바꿨다.** cssnano의 `colormin`이 `rgba(200,197,204,.3)`을 `hsla(266,6%,79%,.3)`로 변환하는데, 이 왕복 변환에서 채널당 1씩 어긋남. `postcss.config.js`에서 `colormin: false`로 끄고 나머지 압축은 유지.
- 검증: 배포본 렌더링 HTML을 기준으로 CDN만 빌드 CSS로 바꾼 사본을 만들어, 브라우저에서 `getComputedStyle` 27개 속성 × 요소 75개와 `getBoundingClientRect`를 전수 비교 → **박스 0개, 스타일 0개 차이**. `pytest -q` 135건 통과. 로그인 페이지 전송량 788KB → 72KB(91% 감소).
- 추후 관리:
  - 템플릿에 클래스를 추가하면 `npm run css`를 다시 돌려야 한다. Play CDN과 달리 빌드 시점에 스캔한 클래스만 CSS에 들어간다.
  - 배포 이미지(`Dockerfile`)에 node가 없어서 빌드 산출물 `static/css/tailwind.*.css`를 커밋한다.
  - `bg-white/8`은 Tailwind 기본 opacity 스케일에 `8`이 없어 **이전부터 무효인 클래스**다(`index.html`, `login.html`). 의도한 효과를 내려면 `bg-white/[0.08]`로 고쳐야 한다.
- 이어서 처리한 것 — 응답 압축 부재:
  - 위 작업 중 배포 서버가 압축을 전혀 하지 않는 걸 발견했다(`Accept-Encoding: gzip`을 보내도 `content-encoding` 헤더 없음). 정적 자산이 원본 크기 그대로 나가고 있었다.
  - `Flask-Compress`를 `create_app()`에 추가해 해결. 로그인 HTML 16.9KB → 4.5KB, `tailwind.base.css` 31.8KB → 7.3KB, `index.css` 18.0KB → 5.8KB.
  - **주의**: `Accept-Encoding: gzip`만 보내면 정적 파일은 압축되지 않는다. Flask-Compress가 스트리밍 응답(=`send_from_directory`로 나가는 정적 파일)에 한해 `COMPRESS_ALGORITHM_STREAMING`을 쓰는데 여기에 gzip이 빠져 있기 때문(`['zstd','br','deflate']`). 처음 측정할 때 gzip만 보내서 "정적 파일은 압축이 안 된다"고 잘못 판단했다가, 실제 브라우저 헤더(`gzip, deflate, br, zstd`)로 다시 재고서야 정상 동작을 확인했다. 브라우저는 전부 br을 보내므로 실사용에는 문제없다.
  - 최종: 로그인 페이지 1회 로드 787KB → 34KB(96% 감소).

### 15. AI로 생성한 이미지를 "진본"으로 판정하던 문제 — 학습 모델을 아예 안 타고 있었다
- 증상: 생성형 AI로 만든 사진을 업로드했는데 "사람이 제작한 이미지일 가능성이 높습니다"로 나옴.
- 재현 조건: 이미지 판별에 AI 생성 이미지를 넣으면 항상. 특정 파일에 국한되지 않음.
- 원인(표면): `ImageDetector.detect()`가 `ai_percent`를 낮게 계산.
- 원인(근본): 세 가지가 겹쳐 있었다.
  1. **학습 모델을 아예 호출하지 않았다.** `HFDeepfakeClient`와 `HF_TOKEN`이 갖춰져 있는데 `video_detector.py`만 쓰고 `image_detector.py`는 로컬 픽셀 휴리스틱만 돌리고 있었다.
  2. **그 휴리스틱은 판별력이 없다.** `ai_percent = 노이즈×0.5 + 엣지×0.3 + 색상×0.2`인데 각 항이 계단 함수라 **이론상 최댓값이 84%**이고, `AI높음`(70% 이상)이 나오려면 거의 빈 화면 수준으로 매끈해야 한다. 실측하면 무엇을 넣어도 38~49%에만 몰렸고, 해상도를 320px로 줄이면 판정이 `사람제작`→`혼합`으로 뒤집혔다. 요즘 생성 이미지는 디테일이 풍부해서 이 조건에 걸리지 않는다.
  3. **모델 선택이 용도와 어긋났다.** 기본 모델 `prithivMLmods/deepfake-detector-model-v1`은 **딥페이크(얼굴 조작) 탐지기**다. "AI가 통째로 생성한 이미지인가"와는 다른 문제를 푼다.
- 시도했지만 안 된 방향: 처음엔 휴리스틱의 임계값만 조정하면 될 거라 봤다. 하지만 산식의 상한이 84%로 고정돼 있어 가중치를 바꿔도 구조적으로 해결되지 않는다는 걸 계산으로 확인하고 방향을 바꿨다.
- 근거 데이터 — AI 생성이 확실한 이미지 3장에 모델 4종을 돌린 결과:

  | 모델 | 3장 중 AI로 맞춘 수 |
  |---|---|
  | prithivMLmods/deepfake-detector-model-v1 (당시 사용) | 0 / 3 |
  | umm-maybe/AI-image-detector | 1 / 3 |
  | Organika/sdxl-detector | 2 / 3 |
  | haywoodsloan/ai-image-detector-deploy | 3 / 3 |

- 해결: 이미지 판별을 영상과 같은 모델 경로로 옮기되 **모델은 용도별로 분리**했다. `IMAGE_DEFAULT_MODEL = haywoodsloan/ai-image-detector-deploy`, 환경변수는 `HF_IMAGE_MODEL`. 영상은 기존 딥페이크 모델을 그대로 쓴다. 토큰이 없거나 호출이 실패하면 휴리스틱으로 폴백하되 `details.method`와 요약 문구에 **"로컬 휴리스틱(모델 호출 불가) — 정확도가 제한적입니다"**를 명시한다. 모델을 쓴 척하지 않는다.
- 검증: 같은 3장이 교체 후 88.4% / 100% / 100%로 전부 `AI높음` 판정(이전 38~49% 전부 오판). `pytest -q` 140건 통과(기존 135 + 신규 5).
- 라벨 데이터로 재검증 (교체 직후 3장은 표본이 너무 작아 별도 측정함):

  | 라벨 | 장수 | 점수 범위 | 결과 |
  |---|---|---|---|
  | AI 생성 (webp) | 5 | 94.5 ~ 100% | 전부 `AI높음` |
  | 직접 촬영 (스마트폰) | 16 | 0.0 ~ 16.2% | 전부 `사람제작` |

  임계값 40%·70% 어느 쪽으로 잡아도 **오탐 0건, 미탐 0건**. 두 그룹 사이가 78%포인트 비어 있어 경계에 걸릴 위험이 낮다. 교체 전 휴리스틱이 38~49%에만 몰렸던 것과 대비된다.

  **오탐(진짜 사진을 AI로 판정)이 미탐보다 치명적이라 그쪽을 먼저 확인했다.** 심사자가 자기 사진을 올렸는데 AI라고 나오면 서비스 신뢰가 통째로 무너진다.

- 추후 관리:
  - **표본 21장은 여전히 작다.** AI 5장이 전부 같은 생성기(해상도가 모두 340×456으로 동일), 진본 16장도 같은 기기다. 다른 생성기(Midjourney, DALL·E 등)나 다른 카메라에서도 같은 결과일지는 이 데이터로 말할 수 없다.
  - 단위 테스트가 `.env`의 실제 토큰을 주워 네트워크를 타지 않도록 `tests/test_image_detector.py`에 `HF_TOKEN`을 지우는 autouse 픽스처를 뒀다. 모델 경로는 `fake_percent`를 patch해 검증한다.
  - 판별 방식이 바뀌면 **기존 Redis 캐시의 옛 결과가 그대로 나오는** 문제가 있었다. 캐시 키를 `result:{해시}` → `result:v{버전}:{해시}`로 바꾸고 `CACHE_SCHEMA_VERSION`을 2로 올려 해결했다. 앞으로 판별 로직이나 결과 스키마를 바꾸면 이 상수를 같이 올려야 한다. 단 `HF_IMAGE_MODEL`로 모델만 교체하는 경우는 자동 무효화되지 않으므로 그때도 수동으로 올려야 한다.

### 16. 푸시해도 배포가 안 걸리던 원인 — 존재하지 않는 브랜치를 감시하고 있었음
- 증상: `main`에 커밋을 푸시해도 클라우드타입이 반응하지 않음. 수동으로 "시작"을 눌러 앱을 깨우면 **옛 코드가 그대로** 떠 있었다. 새로 추가한 `/health`는 302로 로그인 화면에 리다이렉트되고, 새 CSS 파일은 404였다.
- 처음 세운 가설(틀림): 무료 플랜이라 배포가 느리거나, 빌드 캐시가 남아 옛 이미지를 재사용한다고 봤다. 캐시를 의심해 재배포를 눌렀는데 그때 진짜 원인이 로그에 찍혔다.
- 원인: 빌드 설정의 Git ref가 `refs/heads/portfolio-hardening`을 가리키고 있었다. 그 브랜치는 이미 삭제돼 원격에 없다(`git ls-remote` 결과 `refs/heads/main` 하나뿐, reflog에 흔적만 2건).

  ```
  😐 Fetching repository.
    ├ Git URL is https://github.com/<REDACTED>/TruthLens
    ├ Git sub path is TruthLensFlask
    └ Git ref is refs/heads/portfolio-hardening
  🔴 Build job failed. git fetching error:
  warning: Could not find remote branch portfolio-hardening to clone.
  fatal: Remote branch portfolio-hardening not found in upstream origin
  ```

- 왜 눈치채기 어려웠나: **자동 배포가 조용히 실패한 게 아니라 아예 트리거되지 않았다.** 감시 대상 브랜치에 푸시가 없었으니 클라우드타입 입장에선 할 일이 없었고, 에러도 알림도 남지 않았다. 앱은 마지막으로 성공한 빌드 이미지로 계속 떠서 "배포는 됐는데 코드가 옛날 것"인 상태로 보였다.
- 해결: 콘솔에서 Git ref를 `main`으로 변경. (브랜치를 다시 만들어 맞추는 방법도 있지만, 브랜치 두 개를 영구히 동기화해야 해서 같은 사고가 재발한다.)
- 검증: 재배포 후 정적 파일 4개를 내려받아 로컬 HEAD와 SHA-256 대조 — 전부 일치.

  | 파일 | 로컬 | 배포 |
  |---|---|---|
  | `js/main.js` | `2cb2de7f4bf0` | `2cb2de7f4bf0` |
  | `css/index.css` | `23d8804fee1e` | `23d8804fee1e` |
  | `css/tailwind.base.css` | `3c1c72c4c66c` | `3c1c72c4c66c` |
  | `css/tailwind.login.css` | `d8860d9841bb` | `d8860d9841bb` |

  `/health` → 200 `{"status":"ok"}`, `/ready` → 200 `{"status":"ready"}`. Play CDN 스크립트는 HTML에서 0회. 로그인 페이지 실전 전송량 787,739 → **9,187 bytes**(zstd 적용, 98.8% 감소).
- 배운 점: "배포됐는데 코드가 옛날 것"이면 캐시부터 의심하기 전에 **빌드가 실제로 돌았는지, 어느 ref를 봤는지**를 먼저 확인해야 한다. 배포본과 로컬 HEAD의 해시를 대조하는 건 20초짜리 작업인데 추측을 즉시 끝낸다.

### 17. 회원가입한 계정으로 로그인이 안 되던 문제 — DB가 컨테이너와 함께 사라지고 있었음
- 증상: 회원가입에 성공했던 계정으로 며칠 뒤 로그인하니 "이메일 또는 비밀번호가 올바르지 않습니다"가 떴다.
- 처음 의심한 것들(전부 아님):
  - 비밀번호 해싱 로직 문제 → `tests/test_auth.py` 9건 전부 통과. 배포본에 없는 계정으로 로그인을 찔러보니 `302 → /login`으로 정상 실패 경로. 500이 아니라 코드는 멀쩡했다.
  - 소셜 로그인으로 가입해놓고 이메일로 로그인하는 상황(`password_hash`가 `None`이면 line 17에서 항상 실패) → 이 앱은 `/auth/email/*` 하나뿐이고 OAuth 코드가 없어 해당 없음.
- 원인(근본): DB가 앱 컨테이너의 로컬 디스크에 있었다. 세 가지가 겹친다.
  - `.gitignore`에 `instance/`가 있어 DB 파일이 저장소에 없다
  - `Dockerfile`이 `RUN mkdir -p uploads instance`로 **빈 폴더만** 만들고 시작한다
  - 클라우드타입 무료 플랜은 하루 한 번 강제 중지되고, 재기동·재배포 때 컨테이너 디스크가 초기화된다

  그래서 SQLite 파일이 통째로 날아가고, `app.py`가 빈 DB에 테이블을 새로 만들어 아무 일 없었다는 듯 떴다. **가입은 실제로 성공했고 그 뒤에 지워진 것이다.**
- 확인한 것과 추측한 것의 구분: 위 세 가지는 저장소에서 직접 확인했다. 다만 클라우드타입 환경변수의 `DATABASE_URL`이 실제로 `sqlite:///`인지는 콘솔 접근이 필요해 확인하지 못했다. `/ready`가 200이라 DB 연결 자체는 되고 있어, SQLite든 외부 DB든 양쪽 모두와 모순되지 않는다.
- 해결: DB를 컨테이너 밖 관리형 Postgres로 옮기기로 하고 코드 쪽 준비를 마쳤다.
  - `requirements.txt`에 `psycopg2-binary` 추가
  - `app.py`: `db.create_all()`이 **SQLite일 때만** 돌던 조건을 제거. 외부 DB에는 `schema.sql`을 손으로 실행해 줄 사람이 없다. 이 조건을 안 고치면 `DATABASE_URL`을 Postgres로 바꾸는 순간 테이블이 없는 채로 앱이 떠서 회원가입이 500으로 죽는다
  - gunicorn 워커 2개가 동시에 부팅하면 양쪽 다 `CREATE TABLE`을 시도해 한쪽이 "이미 존재함"으로 터진다. 여기서 죽으면 크래시 루프가 되므로 `SQLAlchemyError`를 잡아 기동은 계속하되 `event: db.create_all.failed`로 **WARN을 남긴다**(조용한 폴백 금지). DB가 정말 안 붙는 경우는 `/ready`가 503으로 알린다
- 검증: 도커로 일회용 Postgres 16을 띄워 실제로 확인했다. 단위 테스트만으로는 "재배포해도 계정이 남는가"를 증명할 수 없다.

  | 확인 항목 | 결과 |
  |---|---|
  | 빈 Postgres에 기동 → 테이블 자동 생성 | 6개 (`users`, `detection_requests`, `detection_results`, `cache_metadata`, `content_stats`, `paper_citations`) |
  | `/ready` | 200 `{"status":"ready"}` |
  | 회원가입 | 302 → `/` |
  | **앱 인스턴스를 새로 만든 뒤 로그인** (재배포 상황) | 302 → `/` — **유지됨** |
  | 틀린 비밀번호 | 302 → `/login` (여전히 막힘) |
  | 3회 더 재기동 후 사용자 수 | 1 (`create_all`이 기존 데이터를 지우지 않음) |

  `pytest -q` **146건 통과**(기존 143 + 신규 3).
- 추후 관리:
  - 배포 후 운영에서 최종 확인 완료. `/health` 200, `/ready` 200(Postgres 연결됨), 배포본 정적 파일 4개가 로컬 HEAD와 SHA-256 일치.
  - **테이블 존재 여부는 `/ready`로 증명되지 않는다.** `/ready`는 `SELECT 1`만 하므로 테이블이 없어도 200이다. 없는 계정으로 로그인을 찔러 화면 문구로 구분했다 — "이메일 또는 비밀번호가 올바르지 않습니다"면 조회가 성공하고 결과만 없는 정상 경로(테이블 있음), "로그인 중 오류가 발생했습니다"면 예외(테이블 없음). 전자가 나왔다.
  - 클라우드타입 관리형 DB를 쓰면 DB 서비스도 같은 무료 플랜이라 함께 멈춘다. 깨울 대상이 둘로 늘어나므로 외부 상시 가동 DB를 골랐다.
  - `uploads/`도 같은 이유로 매번 초기화된다. 과거 분석 결과의 이미지가 안 뜰 수 있다. 이번 작업 범위에는 넣지 않았다.
  - 스키마 변경 관리 도구(Alembic 등)가 없다. `create_all()`은 **없는 테이블만** 만들고 기존 테이블의 컬럼 변경은 반영하지 못한다. 컬럼을 추가·변경하는 시점에는 마이그레이션 도구가 필요하다.
- 배운 점: "로그인이 안 된다"는 증상에서 인증 코드를 먼저 파는 건 자연스럽지만, 이번엔 **인증 코드가 아니라 데이터가 사라진 문제**였다. 테스트가 전부 통과하는데 운영에서만 실패하면 코드가 아니라 코드 밖(환경·수명주기·영속성)을 봐야 한다는 신호다.

### 18. "재시작"은 옛 이미지를 다시 켤 뿐이었다 — 코드를 고쳐도 반영되지 않던 문제
- 증상: DB를 외부 Postgres로 옮기는 커밋(`psycopg2-binary` 추가 포함)을 푸시하고 배포했는데도 사이트가 계속 503. 12분 넘게 상태가 그대로였다.
- 로그에 찍힌 것:

  ```
  File "/app/app.py", line 37, in create_app
      db.init_app(app)
    ...
    File ".../sqlalchemy/dialects/postgresql/psycopg2.py", line 697, in import_dbapi
      import psycopg2
  ModuleNotFoundError: No module named 'psycopg2'
  [ERROR] Worker (pid:7) exited with code 3.
  [ERROR] Reason: Worker failed to boot.
  ```

  환경변수 `DATABASE_URL`은 Postgres로 바뀌어 반영됐다(그래서 psycopg2를 찾으러 갔다). 그런데 드라이버가 없어 워커 두 개가 모두 부팅에 실패하고 마스터까지 종료됐다.
- 원인을 확정한 방법 — **트레이스백의 줄 번호**:

  | | `db.init_app` | `app = create_app()` |
  |---|---|---|
  | 로그가 가리킨 위치 | 37 | 93 |
  | 옛 커밋 `af454fd` | 37 | 93 ← 일치 |
  | 새 커밋 `26490a1` | 38 | 105 |

  새 커밋은 import를 한 줄 추가해 위치가 밀렸는데, 로그는 밀리기 전 위치를 가리켰다. **실행 중인 코드가 푸시 이전 것**이라는 뜻이다.

  로그 앞부분도 같은 결론을 준다. 소스를 받아오거나 `pip install` 하는 단계가 하나도 없이 `Connecting to ...` 다음 바로 gunicorn이 뜬다. 새로 빌드한 게 아니라 마지막으로 성공했던 이미지를 그대로 다시 켠 것이다.

- 원인: 클라우드타입에서 "시작"(재시작)은 기존 이미지를 다시 실행할 뿐이다. `requirements.txt`를 고쳐도 그 이미지 안에는 새 패키지가 없다. 새 커밋을 반영하려면 **빌드를 다시 돌려야** 한다.
- 해결: 재시작이 아니라 재빌드를 트리거. 빌드 로그에 `Fetching repository` → `Git ref is refs/heads/main` → `pip install`이 찍히는지 확인하면 제대로 걸린 것이다.
- 검증: 기동 후 `/health` 200, `/ready` 200. 배포본 정적 파일 4개가 로컬 HEAD(`26490a1`)와 SHA-256 일치. 앱이 `postgresql://` URL로 뜬 것 자체가 psycopg2가 설치됐다는 증거다(없으면 부팅 단계에서 죽는다).
- 배운 점:
  - **트레이스백의 줄 번호는 어느 리비전이 돌고 있는지 알려주는 지문이다.** "배포했는데 왜 안 고쳐지지"에서 추측을 끝내는 가장 빠른 방법이었다.
  - 이번 배포는 원인이 세 겹이었다 — (1) 삭제된 브랜치를 감시(16번), (2) 드라이버 없이 `DATABASE_URL`만 교체, (3) 재빌드 대신 재시작. 하나를 풀면 다음 게 나왔다. **증상이 같아도(503) 원인이 바뀔 수 있으니 단계마다 증거를 다시 잡아야 한다.**
  - 부수적으로 로그에 `Control server error: [Errno 13] Permission denied: '/.gunicorn'`도 찍혔지만 크래시와 무관하다. non-root 컨테이너에서 gunicorn이 컨트롤 소켓을 못 만드는 것뿐이다. **로그에 있는 에러가 전부 원인은 아니다.**

### 19. 다른 생성기로 만든 AI 이미지를 놓치던 문제 — 단일 모델의 한계를 앙상블로 넘김
- 증상: 배포 후 사용자가 AI로 만든 이미지 5장을 올렸는데 2~3장만 맞혔다. 틀린 것들은 0.0%, 0.2%, 1.2%처럼 **확신 있게** 진본이라고 했다.
- 재현: 사용자가 준 AI 이미지 14장을 로컬에서 돌려 9/14(64%)로 재현했다. 15번에서 쓴 5장은 여전히 94.5~100%로 잘 맞혔다.
- 원인을 찾기 전에 지운 가설들 — 전부 아니었다:

  | 의심 | 확인 방법 | 결과 |
  |---|---|---|
  | `HF_IMAGE_MODEL`이 잘못 설정됨 | 클라우드타입 환경변수 목록 확인 | 변수 자체가 없음(= 올바른 기본 모델) |
  | 업로드 경로가 로컬 테스트와 다름 | `image_routes.py` 추적 | 배포도 파일 저장 후 경로를 넘김. 동일 |
  | 재압축·리사이즈로 생성 흔적이 지워짐 | q75 재압축, 50% 축소, 2배 확대로 재측정 | 전부 99%대 유지. 이 모델은 재압축에 강함 |

- 원인(근본): **모델의 진짜 한계였다.** 15번에 적어둔 우려가 현실이 됐다 — 그때 검증에 쓴 AI 5장이 전부 같은 생성기였고, "다른 생성기에서도 통할지는 이 데이터로 말할 수 없다"고 기록해뒀다. 새 이미지는 다른 생성기 것이었다.
- 후보 모델 5개를 같은 표본(AI 19장 / 진본 16장)으로 비교했다. **셋의 정확도가 똑같은데 실패 방향이 정반대였다.**

  | 모델 | 정확도 | AI 탐지 | 오탐 |
  |---|---|---|---|
  | haywoodsloan/ai-image-detector-deploy | 85.7% | 14/19 | **0/16** |
  | Organika/sdxl-detector | 85.7% | **19/19** | 5/16 |
  | Ateeqq/ai-vs-human-image-detector | 85.7% | **19/19** | 5/16 |
  | dima806/ai_vs_real_image_detection | 68.6% | 19/19 | 11/16 |
  | umm-maybe/AI-image-detector | 40.0% | 0/19 | 2/16 |

  기존 모델은 진짜 사진을 한 번도 의심하지 않는 대신 AI를 5장 놓쳤고, 나머지 둘은 AI를 다 잡는 대신 진짜 사진 5장을 의심했다. **오답이 겹치지 않는다는 게 핵심이었다.**

- 해결: 세 모델 점수의 **중앙값**을 쓴다. 3개 중 중앙값이 70 이상인 것은 "3개 중 2개 이상이 70 이상"과 수학적으로 같으므로 곧 다수결이다. 점수 하나만 바꾸면 되니 판정 문구·신뢰도 계산 등 하위 로직을 건드리지 않는다.
  - `IMAGE_ENSEMBLE_MODELS` 상수로 3개를 묶었다. 홀수여야 중앙값이 다수결이 된다.
  - 세 호출은 `ThreadPoolExecutor`로 동시에 쏜다. 순차로 하면 대기가 3배가 된다(실측 2.2초 → 0.8초).
  - 하나가 실패해도 남은 것들의 중앙값으로 판정한다. 전부 실패해야 휴리스틱으로 떨어진다.
  - `HF_IMAGE_MODEL`을 지정하면 그 모델 하나만 쓴다. 앙상블을 우회할 탈출구를 남겼다.
  - 조합을 4가지 다 계산해보고 골랐다. 전원일치(AND)는 85.7%로 개선이 없었고, 하나라도(OR)는 오탐이 8/16으로 늘어 77.1%로 나빠졌다.
- 시도했지만 안 된 것: 기존 모델이 오탐 0이라 "기존 모델이 낮게 보면 거부"하는 규칙을 만들려 했다. 하지만 놓치는 5장에서 기존 모델 점수가 0.0~4.8이고, 오탐 2건에서도 4.5·0.1이라 **구간이 겹쳐서 구분이 안 됐다.** 폐기했다.
- 검증: 실제 35장 재측정.

  | | 교체 전 | 교체 후 |
  |---|---|---|
  | 정확도 | 85.7% | **94.3%** |
  | AI 탐지 | 14/19 | **19/19** |
  | 오탐 | 0/16 | 2/16 |
  | 이미지당 소요 | 1.0초 | 1.2초 |

  놓치던 5장(`theater`, `opium`, `mansion`, `constable`, `photographer`)이 전부 99.9% 이상으로 잡혔다. `pytest -q` 152건 통과(기존 146 + 신규 6).
- 측정이 한 번 오염됐던 일: 첫 35장 측정에서 정확도가 82.9%로 나왔다. 새로 추가한 두 모델이 **콜드스타트로 대량 타임아웃**나서 모델 1~2개만 성공했고, 다수결이 성립하지 않은 채 집계된 것이다. 예열 후 재측정하니 3개 전부 성공(35장 중 실패 0)하며 94.3%가 나왔다. **외부 추론 API를 쓰는 측정은 첫 회차를 믿으면 안 된다.**
- 추후 관리:
  - 오탐이 0에서 2로 늘었다. 진짜 사진을 AI라고 하는 건 놓치는 것보다 사용자 신뢰에 더 해롭다. 그럼에도 AI를 4장 중 1장씩 놓치는 쪽이 서비스로서 더 문제라고 판단해 교체했다. **이 트레이드오프는 의도한 것이다.**
  - **표본 35장(AI 19 / 진본 16)으로 잰 94.3%를 일반적인 정확도로 말하면 안 된다.** AI 19장은 해상도가 760×1018과 1200×670 두 종류뿐이고, 진본 16장은 같은 기기로 찍은 것이다.
  - 판별 로직이 바뀌었으므로 `CACHE_SCHEMA_VERSION`을 3으로 올렸다. 안 올리면 24시간 동안 옛 점수가 캐시로 반환된다.
  - HF 무료 추론은 콜드스타트가 있다. 오래 안 쓴 모델의 첫 호출은 20초 타임아웃에 걸릴 수 있고, 그때는 남은 모델로 판정된다(정확도가 조용히 떨어진다). 이 상황은 `event: image.model.fallback` 로그로 남는다.
