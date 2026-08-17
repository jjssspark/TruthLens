# TruthLens

[![tests](https://github.com/jjssspark/TruthLens/actions/workflows/tests.yml/badge.svg)](https://github.com/jjssspark/TruthLens/actions/workflows/tests.yml)

AI 생성 콘텐츠 판별 서비스 (Product Requirements Document 기반)

![TruthLens 데모 — 이미지 업로드부터 AI 생성 판별 결과까지](docs/assets/truthlens-demo.gif)

**라이브 데모**: https://port-0-truthlens-mscko82687e05bd3.sel3.cloudtype.app
(무료 티어 컨테이너입니다. 가입 계정은 컨테이너 밖 관리형 PostgreSQL에 저장되어 재시작해도 남지만,
업로드한 파일은 재시작마다 초기화되므로 과거 분석 결과의 이미지가 보이지 않을 수 있습니다.)

## 1. 프로젝트 개요

TruthLens는 생성형 AI 기술의 급속한 발전으로 인해 범람하는 AI 생성 영상·이미지·텍스트(뉴스·논문)에 대해
**AI 생성 여부를 판별**하고 관련 분석 정보를 제공하는 웹 서비스입니다.

딥페이크 영상·이미지를 이용한 허위정보 유포, AI 생성 가짜뉴스·논문을 통한 여론 조작 및 학술 신뢰성 훼손,
AI 생성 콘텐츠의 저작권·진위 여부를 둘러싼 법적·윤리적 분쟁 증가, 일반 사용자의 진위 판별 도구 부재라는
문제를 해결하기 위해 시작되었습니다.

**목표**
- 영상·이미지·텍스트(뉴스·논문)에 대한 AI 생성 여부 판별 정확도 85% 이상 달성
- 판별 결과에 대한 근거 정보 및 신뢰 지표 시각화 제공
- 반복 요청에 대한 캐싱으로 응답 지연 최소화 (캐시 히트 시 1초 이내)
- 논문 대상 요약 자동 생성 및 누락 인용 탐지·추가 기능 제공
- 동일 콘텐츠에 대한 집단 분석 요청 현황을 사용자에게 투명하게 공개

## 2. 핵심 기능

| 기능 | 도메인 | 설명 |
| --- | --- | --- |
| FR-01 영상 AI 생성 판별 | 영상 | URL(YouTube, Vimeo, 직접 링크) 또는 파일(MP4/AVI/MOV/WEBM, 최대 500MB·10분) 입력 → AI 생성 신뢰 점수, 딥페이크 탐지, 프레임 단위 의심 구간 하이라이트, 판별 근거 요약 제공 |
| FR-02 이미지 AI 생성 판별 | 이미지 | 이미지(JPG/PNG/WebP/GIF, 최대 20MB, 다중 업로드 최대 10장) → AI 생성 신뢰 점수, 의심 영역 히트맵, 픽셀 패턴 이상 탐지, EXIF 메타데이터 분석 |
| FR-03 뉴스 가짜 판별 | 뉴스 | URL 또는 텍스트(최대 10,000자) → AI 생성 텍스트/가짜뉴스 가능성 점수, 출처 신뢰도, 감성·편향 분석, 의심 문장 하이라이트, 유사 팩트체크 기사 링크 |
| FR-04 논문 AI 생성 판별 및 분석 | 논문 | PDF 업로드(최대 50MB, 200페이지) → 논문/섹션별 AI 생성 비율, 의심 문단 하이라이트, 자동 요약(500자 이내) 및 핵심 주장 추출, 본문-참고문헌 인용 교차 검증·누락 인용 탐지 및 메타데이터 자동 검색, 수정본 PDF 다운로드 |
| FR-05 캐싱 및 동일 콘텐츠 집계 표시 | 공통 | 동일 콘텐츠 해시에 대해 1시간 내 100회 이상 요청 시 Redis 캐시 활성화(TTL 기본 24시간), 결과 페이지에 "이 콘텐츠를 분석한 사용자 수" 및 캐시 결과 배지 표시 |

## 3. 기술 스택

| 레이어 | 기술 | 역할 |
| --- | --- | --- |
| Frontend | HTML5, CSS3, JavaScript (Vanilla / Alpine.js) | UI 렌더링, 파일 업로드, 결과 시각화 |
| Backend | Python 3.11+, Flask 3.x | API 라우팅, 비즈니스 로직, 파일 처리 |
| AI 분석 | Transformers, OpenCV, PyTorch | AI 생성 콘텐츠 탐지 모델 실행 |
| Database | MariaDB 11.x (PRD 설계) — 실제 구동은 SQLite(로컬)·PostgreSQL(배포) | 판별 결과, 요청 이력, 콘텐츠 메타데이터 저장 |
| Cache | Redis 7.x | 콘텐츠 판별 결과 캐싱, 요청 카운터 |
| File Storage | 로컬 파일시스템 / AWS S3 (확장) | 업로드 파일 임시 저장 |
| Task Queue | Celery + Redis | 영상 등 장시간 처리 비동기 작업 |
| Web Server | Gunicorn + Nginx | 운영 환경 서비스 배포 |

Flask 백엔드 구현은 [`TruthLensFlask/`](TruthLensFlask) 디렉토리를 참고하세요.

## 4. 주요 화면 구조

| 화면 | 경로 | 주요 기능 |
| --- | --- | --- |
| 메인(홈) 화면 | `/` | 서비스 소개, 판별 유형 선택 |
| 영상 판별 | `/detect/video` | URL/파일 입력, 분석 진행 표시 |
| 이미지 판별 | `/detect/image` | 이미지 업로드, 다중 업로드 |
| 뉴스 판별 | `/detect/news` | URL/텍스트 입력 |
| 논문 판별 | `/detect/paper` | PDF 업로드, 요약/인용 분석 |
| 판별 결과 | `/result/:id` | 신뢰 점수 게이지, 판별 근거 요약, 동일 콘텐츠 분석 요청자 수, 캐시 배지, 결과 공유/재요청 버튼 |
| 판별 이력 | `/history` | 과거 요청 목록 및 결과 재조회 |

반응형 디자인으로 모바일(320px+), 태블릿(768px+), 데스크탑(1280px+)을 지원하며,
모바일에서는 카메라/갤러리 접근을 통한 파일 업로드를 지원합니다.

## 5. 로컬 실행 (Quick Start)

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
- 뉴스 판별(FR-03)은 `GEMINI_API_KEY`, 논문 판별(FR-04)은 `DEEPSEEK_API_KEY`가 필요합니다(`.env.example` 참고). 키가 없으면 앱은 정상 구동되고 해당 기능만 에러를 반환합니다.
- 영상 판별(FR-01)과 이미지 판별(FR-02)의 `HF_TOKEN`은 **선택**입니다. 없으면 에러 대신 로컬 휴리스틱으로 동작합니다. 다만 휴리스틱은 정확도가 크게 떨어지므로, 판별 성능을 보려면 키를 넣는 편이 맞습니다.
- **이미지 판별(FR-02)은 `HF_TOKEN`이 있으면 학습 모델 3개를 동시에 호출해 중앙값으로 판정합니다**(`ai_models/image_detector.py`). 단일 모델은 특정 생성기의 이미지를 놓쳤습니다. 자체 표본 35장(AI 19 / 진본 16)에서 85.7% → 94.3%로 올랐습니다. **표본이 작고 편중돼 있어 일반적인 정확도로 읽으면 안 됩니다**(근거와 한계는 [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) 19번). 모델 하나가 실패해도 나머지로 판정합니다.
- **영상 판별(FR-01)은 두 가지 방식으로 동작합니다.** `HF_TOKEN`이 있으면 Hugging Face 추론 API의 딥페이크 분류 모델(기본 `prithivMLmods/deepfake-detector-model-v1`)로 프레임을 판정하고, 없으면 OpenCV 픽셀 휴리스틱으로 폴백합니다. 어느 쪽을 썼는지는 결과의 `details.method`(`hf-model` / `local-heuristic`)에 항상 표시되므로, 휴리스틱 결과를 모델 판정으로 오인할 일이 없습니다. 모델 호출이 실패해도 같은 방식으로 폴백하고 그 사실을 남깁니다.

### 알려진 한계

- **영상·이미지 판별은 `HF_TOKEN` 없이는 휴리스틱** — 위 항목 참고. 휴리스틱 모드의 정확도는 상용 탐지 수준이 아닙니다. 어느 방식으로 판정했는지는 결과의 `details.method`에 항상 표시됩니다.
- **이미지 판별 정확도는 자체 표본 35장 기준입니다.** 해상도·촬영 기기가 편중된 표본이라 일반화할 수 없습니다.
- **업로드 파일은 배포 컨테이너 재시작마다 사라집니다.** DB는 외부 PostgreSQL로 옮겼지만 `uploads/`는 아직 컨테이너 디스크에 있습니다.
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

## 6. 배포

배포 플랫폼으로 **클라우드타입(cloudtype.io)** 을 사용합니다. GitHub 연동 기반으로
복잡한 인프라 설정 없이 Flask 애플리케이션을 빠르게 배포·운영할 수 있습니다.

**배포 환경 구성**

| 환경 | 클라우드타입 Stage | 용도 |
| --- | --- | --- |
| 개발(Dev) | `dev` | 기능 개발 및 단위 테스트, 개발팀 내부 접근 전용 |
| 스테이징(QA) | `qa` | 통합 테스트 및 QA 검증, 운영 환경과 동일 구성으로 최종 검증 |
| 운영(Production) | `main` | 실사용자 대상 서비스, GitHub `main` 브랜치 병합 시 자동 배포 |

**배포 서비스 구성** (PRD 설계): 동일 프로젝트 내에서 서비스명을 hostname으로 상호 통신합니다.
- Flask App — Python 3.11 기반 웹 애플리케이션 서버 (Gunicorn)
- Celery Worker — 영상 등 장시간 비동기 분석 작업 처리
- MariaDB — 클라우드타입 제공 데이터베이스 서비스
- Redis — 클라우드타입 제공 캐시 서비스

**DB만 위 구성과 다릅니다.** 클라우드타입 관리형 DB도 같은 무료 플랜이라 앱과 함께 멈춰서 깨울
대상이 둘로 늘어납니다. 그래서 DB는 클라우드타입이 아니라 **컨테이너 밖 상시 가동 PostgreSQL**을
`DATABASE_URL` 환경변수로 붙여 씁니다. 이 결정의 경위는
[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) 17번에 있습니다.

**CI/CD**: GitHub 저장소를 OAuth로 연동하여 브랜치 푸시 시 자동 빌드·배포되며,
테스트 통과 후 배포되도록 GitHub Actions 워크플로우를 구성할 수 있습니다(선택).
API 키, DB 접속 정보 등 민감 정보는 코드에 포함하지 않고 클라우드타입 프로젝트 환경 변수로 관리합니다.

**최소 요구사항**

| 항목 | 사양 | 비고 |
| --- | --- | --- |
| Python | 3.11 이상 | Flask 3.x 호환 버전 |
| MariaDB | 11.x | PRD 설계 기준. 실제 배포는 외부 PostgreSQL, 로컬은 SQLite |
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

## Troubleshooting_요약
- PaperDetector 생성자 크래시로 API 키 없이는 서버 자체가 부팅되지 않던 버그, 평문 비밀번호 저장 — 둘 다 배포 전에 잡아야 했던 안정성·보안 결함이었습니다.
- docker compose up이 13일 전 이미지를 재사용해 최신 커밋이 반영되지 않던 인프라 문제를 이미지 생성 시각과 커밋 시각 대조로 추적했습니다.
- 전체 19건(재현 조건·시도했지만 안 된 것 포함)은 [노션 문서](https://app.notion.com/p/3b1f6f1e619a80ef90fce2a31236b1d7?source=copy_link)에 정리했습니다.

## ADR 요약
- 에러 처리를 라우트마다가 아니라 app.py 전역 계층에서 보장하도록 설계해, 외부 API 장애(502)와 서버 버그(500)를 구분했습니다.
- 업로드 파일명을 sanitize 없이 그대로 써서 발생하던 path traversal 취약점을 secure_filename + uuid 접두어로 제거했습니다.
- 전체 결정 과정(고려한 대안, 근거, 실제 결과)은 [노션 ADR 문서](https://app.notion.com/p/ADR-3b1f6f1e619a80a69c60eadc60db4df0?source=copy_link)에 정리했습니다.
