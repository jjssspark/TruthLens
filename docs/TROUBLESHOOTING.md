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
