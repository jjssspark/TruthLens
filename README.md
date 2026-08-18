# TruthLens

[![tests](https://github.com/jjssspark/TruthLens/actions/workflows/tests.yml/badge.svg)](https://github.com/jjssspark/TruthLens/actions/workflows/tests.yml)

이미지·영상·뉴스·논문을 올리면 AI가 만든 것인지 점수와 근거로 보여주는 Flask 웹 서비스입니다.

![TruthLens 데모 — 이미지 업로드부터 AI 생성 판별 결과까지](docs/assets/truthlens-demo.gif)

**라이브 데모**: https://port-0-truthlens-mscko82687e05bd3.sel3.cloudtype.app

무료 티어 컨테이너입니다. 가입 계정은 컨테이너 밖 관리형 PostgreSQL에 저장되어 재시작해도 남지만,
업로드한 파일은 재시작마다 초기화되므로 과거 분석 결과의 이미지가 보이지 않을 수 있습니다.
이미지 판별은 로그인만 하면 키 없이 바로 눌러볼 수 있습니다.

## 문서

| 문서 | 내용 |
| --- | --- |
| [`docs/PORTFOLIO.md`](docs/PORTFOLIO.md) | 무엇을 왜 그렇게 만들었는지 |
| [`docs/ADR.md`](docs/ADR.md) | 설계 결정 10건 — 고려한 대안, 근거, 나중에 뒤집힌 것 |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | 버그·장애 28건 — 증상, 재현 조건, 시도했지만 안 된 것, 검증 |
| [`docs/RETROSPECTIVE.md`](docs/RETROSPECTIVE.md) | 회고 |
| [`docs/DEMO.md`](docs/DEMO.md) | 시연 시나리오 |
| [`docs/slides/TruthLens_Portfolio.html`](docs/slides/TruthLens_Portfolio.html) | 발표 슬라이드 11장 (브라우저로 열면 됩니다) |

## 이 프로젝트에서 한 것

팀 프로젝트로 시작한 코드를 이어받아, 기능을 늘리기보다 이미 있는 기능이 제대로 동작하고
설명할 수 있는 상태로 만드는 데 집중했습니다.

**만든 기능의 정확도를 직접 쟀습니다.**
영상 판별을 만들고 나서 공개 데이터셋 27개로 재봤더니 37%였습니다. 무조건 "진본"이라고
답할 때(55.6%)보다 낮습니다. 기능을 지우는 대신 그 숫자를 업로드 화면과 결과 화면에
그대로 띄우고 실험적 기능으로 표시했습니다. 자세한 내용은 [알려진 한계](#알려진-한계)에 있습니다.

**이미지 판별은 모델 5개를 같은 표본으로 비교해 3개를 골랐습니다.**
정확도는 셋 다 85.7%로 같은데 실패 방향이 반대였습니다. 하나는 진짜 사진을 한 번도
의심하지 않는 대신 AI를 5장 놓쳤고, 나머지 둘은 AI를 다 잡는 대신 진짜 사진 5장을
의심했습니다. 오답이 겹치지 않아서 중앙값(다수결)으로 묶었더니 94.3%가 됐습니다.

**원인을 잘못 짚은 것도 지우지 않고 남겼습니다.**
배포본을 서버 로그만 보고 진단하다 두 번 틀렸습니다. 한 번은 제가 넣은 코드를 범인으로
지목했는데 그 코드는 배포된 적조차 없었습니다. 그래서 배포된 코드와 모델 상태를 밖에서
확인할 수 있는 `/diagnostics`를 만들었습니다.

**숫자로 보면 이렇습니다.**

| 항목 | 값 |
| --- | --- |
| 테스트 | 31개 → 178개 |
| 커버리지 | 54% → 82% (backend + ai_models) |
| 기록한 버그·장애 | 28건 |
| 로그인 페이지 전송량 | 787KB → 34KB |
| 뉴스 판별 응답 | 약 16초 → 1.3초 |
| 영상 판정 시간 | 13.3초 → 6.1초 |

## 1. 프로젝트 개요

TruthLens는 생성형 AI 기술의 발전으로 빠르게 늘어나는 AI 생성 영상·이미지·텍스트(뉴스·논문)에 대해
AI 생성 여부를 판별하고 관련 분석 정보를 제공하는 웹 서비스입니다.

딥페이크 영상·이미지를 이용한 허위정보 유포, AI 생성 가짜뉴스·논문을 통한 여론 조작 및 학술 신뢰성 훼손,
AI 생성 콘텐츠의 저작권·진위 여부를 둘러싼 분쟁 증가, 일반 사용자의 진위 판별 도구 부재라는
문제를 해결하기 위해 시작되었습니다.

점수만 보여주면 믿기 어렵기 때문에, 왜 그렇게 나왔는지를 히트맵·EXIF·의심 문장으로 같이 보여주는 것을
기본으로 잡았습니다.

**목표와 달성 여부**

| 목표 | 결과 |
| --- | --- |
| AI 생성 판별 정확도 85% 이상 | 이미지 94.3%(자체 표본 35장) · **영상 37%로 미달** |
| 판별 근거 및 신뢰 지표 시각화 | 히트맵·EXIF·의심 문장·판정 방식 표기 |
| 반복 요청 캐싱으로 응답 지연 최소화 | Redis(24h) · DB(7일) 두 방식으로 구현 |
| 논문 요약 자동 생성 | 구현 |
| 논문 누락 인용 탐지 | **미구현** |
| 동일 콘텐츠 분석 요청 현황 공개 | 구현 |

## 2. 핵심 기능

PRD 설계와 실제 구현이 다른 부분은 따로 적었습니다.

| 기능 | PRD 설계 | 실제 구현 |
| --- | --- | --- |
| FR-01 영상 | URL(YouTube/Vimeo/직접 링크) 또는 파일 500MB·10분 → 딥페이크 탐지, 프레임 단위 의심 구간 | **실험적.** 직접 링크·파일(MP4/AVI/MOV/WEBM), 배포본은 앞단 프록시 제한으로 96MB까지. 프레임 6장을 이미지 앙상블로 판정하고 실측 정확도 경고를 함께 반환 |
| FR-02 이미지 | JPG/PNG/WebP/GIF 최대 20MB, 다중 업로드 10장 → 히트맵, 픽셀 패턴, EXIF | 1장씩. 모델 3개 중앙값 + 픽셀 휴리스틱 + EXIF + 히트맵 |
| FR-03 뉴스 | URL 또는 텍스트 최대 10,000자 → 가짜뉴스 점수, 출처 신뢰도, 편향 분석, 유사 팩트체크 링크 | 가짜뉴스 점수·출처 신뢰도·논리성·과장 표현·의심 문장. **팩트체크 기사 링크는 미구현** |
| FR-04 논문 | PDF 최대 50MB·200p → 섹션별 AI 비율, 요약, 인용 교차 검증, 누락 인용 탐지, 수정본 PDF | AI 생성 비율·요약·인용 목록 추출·리포트 PDF. **인용 교차 검증과 누락 인용 탐지는 미구현** |
| FR-05 캐싱·집계 | 콘텐츠 해시 기준 캐시, 분석 요청자 수 표시 | 구현 (7절 참고) |

## 3. 기술 스택

실제로 코드에서 쓰고 있는 것만 적었습니다.

| 레이어 | 기술 |
| --- | --- |
| Frontend | Jinja2 템플릿 · Tailwind CSS(CLI 빌드) · Vanilla JS |
| Backend | Python 3.11 · Flask 3 · Blueprint 8개 · Flask-SQLAlchemy |
| 이미지 · 영상 | OpenCV(headless) · NumPy · Pillow · piexif |
| AI 판별 | Hugging Face 추론 API(이미지·영상 앙상블 3모델) · Google Gemini(뉴스·논문) |
| 본문 추출 | BeautifulSoup4 · lxml · requests |
| PDF | pypdf · reportlab |
| Database | PostgreSQL(배포) · MariaDB(compose) · SQLite(로컬 기본) |
| Cache | Redis |
| WSGI · 배포 | Gunicorn · ProxyFix · Docker · 클라우드타입 |
| 테스트 | pytest · pytest-cov · GitHub Actions |

저장소에 들어 있지만 아직 요청 경로에서 쓰지 않는 것이 하나 있습니다. Celery 태스크(`tasks/video_tasks.py`)를
정의해뒀지만 `video_service.py`가 아직 동기로 처리합니다. 영상 판정이 gunicorn 타임아웃을 넘기지 않도록
프레임 수와 동시 호출로 먼저 맞춰둔 상태입니다.

Flask 백엔드 구현은 [`TruthLensFlask/`](TruthLensFlask) 디렉토리를 참고하세요.

## 4. 로컬 실행 (Quick Start)

MariaDB/Redis를 따로 설치하지 않고 SQLite로 바로 실행할 수 있습니다. **3분 안에 실행 가능**합니다.

```bash
cd TruthLensFlask
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env              # 기본값(SQLite)만으로 바로 실행 가능
python app.py                     # http://localhost:3000
```

- 최초 실행 시 SQLite(`dev.db`)에 테이블이 자동 생성됩니다.
- `/auth/email/signup`으로 이메일 회원가입 후 로그인하면 전체 기능을 체험할 수 있습니다. 인증은 이메일/비밀번호 방식만 지원합니다.
- 뉴스 판별(FR-03)은 `GEMINI_API_KEY`, 논문 판별(FR-04)은 `GEMINI_API_KEY`가 필요합니다(`.env.example` 참고). 키가 없으면 앱은 정상 구동되고 해당 기능만 에러를 반환합니다.
- 영상 판별(FR-01)과 이미지 판별(FR-02)의 `HF_TOKEN`은 **선택**입니다. 없으면 에러 대신 로컬 휴리스틱으로 동작합니다. 다만 휴리스틱은 정확도가 크게 떨어지므로, 판별 성능을 보려면 키를 넣는 편이 맞습니다.
- **이미지 판별(FR-02)은 `HF_TOKEN`이 있으면 학습 모델 3개를 동시에 호출해 중앙값으로 판정합니다**(`ai_models/image_detector.py`). 단일 모델은 특정 생성기의 이미지를 놓쳤습니다. 자체 표본 35장(AI 19 / 진본 16)에서 85.7% → 94.3%로 올랐습니다. **표본이 작고 편중돼 있어 일반적인 정확도로 읽으면 안 됩니다**(근거와 한계는 [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) 19번). 모델 하나가 실패해도 나머지로 판정합니다.
- **영상 판별(FR-01)은 실험적 기능입니다.** `HF_TOKEN`이 있으면 프레임 6장을 뽑아 이미지 판별과 같은 모델 3개에 물어보고 중앙값으로 판정하며, 없거나 전부 실패하면 OpenCV 픽셀 휴리스틱으로 폴백합니다. 어느 쪽을 썼는지는 결과의 `details.method`(`hf-ensemble` / `hf-model` / `local-heuristic`)에 항상 표시됩니다.
  원래는 얼굴 조작 탐지 모델 하나만 썼는데, 얼굴이 없는 화면 녹화가 62%로 나오는 오탐이 있어 교체했습니다(같은 영상이 15.5%가 됐습니다). 다만 교체 후에도 실측 정확도가 낮아 결과에 경고를 함께 내려보냅니다(`details.experimental`, `details.reliability_note`).

### 알려진 한계

- **영상 판별 정확도가 기준선보다 낮습니다.** 공개 데이터셋(deepaction_v1) AI 12개 / 진본 15개로 재서 **37.0%**입니다. 무조건 "진본"이라고 답할 때(55.6%)나 동전 던지기(50%)보다 못합니다. 지우는 대신 업로드 화면과 결과 화면에 실측값을 그대로 띄우고 실험적 기능으로 표시했습니다(측정 방법과 근거는 [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) 26~27번).
- **영상·이미지 판별은 `HF_TOKEN` 없이는 휴리스틱** — 위 항목 참고. 휴리스틱 모드의 정확도는 상용 탐지 수준이 아닙니다. 어느 방식으로 판정했는지는 결과의 `details.method`에 항상 표시됩니다.
- **이미지 판별 정확도는 자체 표본 35장 기준입니다.** 해상도·촬영 기기가 편중된 표본이라 일반화할 수 없습니다.
- **이미지는 현재 1장씩만 분석합니다.** PRD 설계는 10장 동시 업로드지만, 여러 장을 한 요청에서 순차로 분석하면 gunicorn 기본 타임아웃(30초)을 넘겨 워커가 중단되고 응답이 끊깁니다. 판별 동시 실행으로 고치는 중이며, 그때까지 UI·API 모두 1장으로 제한했습니다.
- **업로드 파일은 배포 컨테이너 재시작마다 사라집니다.** DB는 외부 PostgreSQL로 옮겼지만 `uploads/`는 아직 컨테이너 디스크에 있습니다.
- **프론트엔드 테스트 러너가 없습니다.** 서버 응답 형식을 통일해놓고 프론트가 그걸 잘못 읽던 버그를, 백엔드 테스트 156건이 전부 통과하는 동안 잡지 못했습니다([`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) 20번).
- **스키마 마이그레이션 도구가 없습니다.** `db.create_all()`은 없는 테이블만 만들고 컬럼 변경은 반영하지 못합니다.
- **뉴스만 DB 캐시, 나머지는 Redis 캐시** — 7절 "캐싱 전략" 참고.

**시연 시나리오와 진행상황 확인 방법**은 [`docs/DEMO.md`](docs/DEMO.md)를, 개발 중 발견한 버그와 해결 과정은 [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)를 참고하세요.

### Docker로 실행

MariaDB/Redis 설치 없이 SQLite 기반으로 바로 기동합니다.

```bash
cd TruthLensFlask
docker compose up            # http://localhost:3000
```

MariaDB + Redis 조합으로 운영 환경과 유사하게 실행하려면:

```bash
DATABASE_URL= docker compose --profile full up
```

**테스트 실행**

```bash
python -m pytest -q                                    # 전체 테스트
python -m pytest --cov=backend --cov-report=term-missing  # 커버리지 확인
```

## 5. 주요 화면 구조

| 화면 | 경로 | 주요 기능 |
| --- | --- | --- |
| 메인(홈) 화면 | `/` | 서비스 소개, 판별 유형 선택 |
| 영상 판별 | `/detect/video` | URL/파일 입력, 분석 진행 표시 |
| 이미지 판별 | `/detect/image` | 이미지 업로드 (현재 1장씩) |
| 뉴스 판별 | `/detect/news` | URL/텍스트 입력 |
| 논문 판별 | `/detect/paper` | PDF 업로드, 요약/인용 분석 |
| 판별 결과 | `/result/:id` | 신뢰 점수 게이지, 판별 근거 요약, 동일 콘텐츠 분석 요청자 수, 캐시 배지, 결과 공유/재요청 버튼 |
| 판별 이력 | `/history` | 과거 요청 목록 및 결과 재조회 |

반응형 디자인으로 모바일(320px+), 태블릿(768px+), 데스크탑(1280px+)을 지원하며,
모바일에서는 카메라/갤러리 접근을 통한 파일 업로드를 지원합니다.

## 6. 배포

배포 플랫폼으로 **클라우드타입(cloudtype.io)** 을 사용합니다. GitHub 연동 기반으로
복잡한 인프라 설정 없이 Flask 애플리케이션을 빠르게 배포·운영할 수 있습니다.

**배포 환경 구성**

| 환경 | 클라우드타입 Stage | 용도 |
| --- | --- | --- |
| 개발(Dev) | `dev` | 기능 개발 및 단위 테스트, 개발팀 내부 접근 전용 |
| 스테이징(QA) | `qa` | 통합 테스트 및 QA 검증, 운영 환경과 동일 구성으로 최종 검증 |
| 운영(Production) | `main` | 실사용자 대상 서비스, GitHub `main` 브랜치 병합 시 자동 배포 |

**배포 서비스 구성**

| | PRD 설계 | 실제 배포 |
| --- | --- | --- |
| 웹 | Flask App (Gunicorn) | 동일 |
| 비동기 처리 | Celery Worker | **미사용** — 영상 판정을 동기로 처리하고 프레임 수·동시 호출로 시간을 맞춤 |
| DB | 클라우드타입 MariaDB | **컨테이너 밖 PostgreSQL** |
| 캐시 | 클라우드타입 Redis | 동일 |

**DB를 밖으로 뺀 이유입니다.** 클라우드타입 관리형 DB도 같은 무료 플랜이라 앱과 함께 멈춰서 깨울
대상이 둘로 늘어납니다. 그래서 DB는 클라우드타입이 아니라 **컨테이너 밖 상시 가동 PostgreSQL**을
`DATABASE_URL` 환경변수로 붙여 씁니다. 이 결정의 경위는
[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) 17번에 있습니다.

**CI/CD**: GitHub 저장소를 OAuth로 연동해 `main` 푸시 시 빌드·배포합니다.
API 키와 DB 접속 정보는 코드에 두지 않고 클라우드타입 프로젝트 환경 변수로 관리합니다.

배포가 반영됐는지는 `/diagnostics`로 확인합니다. 판별 코드 3개 파일의 내용 해시와 실제 설정값(샘플 프레임 수 등),
외부 모델이 지금 몇 개나 응답하는지를 로그인 없이 볼 수 있습니다. 비밀값은 담지 않고 설정 여부만 참·거짓으로 줍니다.
이 엔드포인트를 만들게 된 경위는 [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) 28번에 있습니다.

**최소 요구사항**

| 항목 | 사양 | 비고 |
| --- | --- | --- |
| Python | 3.11 이상 | Flask 3.x 호환 버전 |
| DB | MariaDB 11.x (PRD) | 실제 배포는 외부 PostgreSQL, 로컬 기본은 SQLite |
| Redis | 7.x | 클라우드타입 기본 제공 버전 |
| 클러스터 리전 | Seoul | 국내 사용자 응답 속도 최소화 |
| Dockerfile | 제공(선택) | 커스텀 빌드 환경이 필요한 경우 사용 |

## 7. 캐싱 전략

동일 콘텐츠 재요청 시 재분석을 피하기 위해 도메인별로 두 가지 캐싱 방식을 사용합니다.

| 도메인 | 캐시 저장소 | TTL | 이유 |
| --- | --- | --- | --- |
| 영상 / 이미지 / 논문 | Redis (`cache/redis_client.py`) | 24시간(기본) | 대용량 파일 분석 비용이 커서 캐시 히트 시 응답을 최대한 빠르게(1초 이내) 반환해야 함. Redis가 없으면 캐시 미스로 처리되어 캐싱만 비활성화되고 기능은 정상 동작(`get_cached_result`/`set_cached_result`의 예외 처리 참고) |
| 뉴스 | DB (`DetectionRequest` 테이블 조회, `NewsService.CACHE_TTL_DAYS = 7`) | 7일 | 뉴스는 원문 URL/텍스트 해시 기준으로 재분석 이력을 DB에서 직접 조회하여 판별 이력·통계(FR-05)와 캐시 판단을 한 번에 처리하도록 구현되어 있음. 별도 Redis 키 없이도 기존 `DetectionRequest`/`DetectionResult` 레코드를 그대로 재사용 |

두 방식이 아직 통일되어 있지 않은 점은 알려진 기술 부채입니다. 추후 뉴스도 Redis 캐시로 통일하면
캐시 조회 비용을 낮추고 캐싱 정책(TTL, 무효화)을 한 곳에서 관리할 수 있습니다.

## 라이선스

[MIT](LICENSE)
