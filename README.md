<div align="center">

# TruthLens

**AI가 만든 콘텐츠인지, 점수와 근거로 보여주는 웹 서비스**

이미지 · 뉴스 · 논문 · 영상을 올리면 AI 생성 여부를 판별하고, 왜 그렇게 나왔는지를 히트맵 · EXIF · 의심 문장으로 같이 보여줍니다.

[![tests](https://github.com/jjssspark/TruthLens/actions/workflows/tests.yml/badge.svg)](https://github.com/jjssspark/TruthLens/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![coverage](https://img.shields.io/badge/coverage-82%25-2ea44f)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

[**라이브 데모**](https://port-0-truthlens-mscko82687e05bd3.sel3.cloudtype.app) · [포트폴리오](docs/PORTFOLIO.md) · [설계 결정](docs/ADR.md) · [트러블슈팅](docs/TROUBLESHOOTING.md) · [회고](docs/RETROSPECTIVE.md)

![TruthLens 데모 — 이미지 업로드부터 AI 생성 판별 결과까지](docs/assets/truthlens-demo.gif)

**시연용 계정** · 아이디 `1234@lens.com` / 비밀번호 `12345678`
가입 없이 바로 눌러보시라고 열어둔 계정입니다. 직접 가입하셔도 됩니다.

</div>

---

## 이 저장소에서 봐주셨으면 하는 것

팀 프로젝트로 시작한 코드를 이어받아, 기능을 늘리기보다 **이미 있는 기능이 제대로 동작하고 설명할 수 있는 상태**로 만드는 데 두 달을 썼습니다. 그래서 자랑거리보다 이 세 가지를 봐주시면 좋겠습니다.

**1. 만든 기능의 정확도를 직접 쟀습니다**
영상 판별을 만들고 나서 공개 데이터셋 27개로 재봤더니 37%였습니다. 무조건 "진본"이라고 답할 때(55.6%)보다 낮습니다. 기능을 지우는 대신 그 숫자를 업로드 화면과 결과 화면에 그대로 띄우고 실험적 기능으로 표시했습니다. → [알려진 한계](#알려진-한계)

**2. 모델은 비교해보고 골랐습니다**
이미지 판별 후보 5개를 같은 표본에 돌렸더니 상위 셋의 정확도가 85.7%로 똑같았습니다. 그런데 실패 방향이 반대였습니다. 하나는 진짜 사진을 한 번도 의심하지 않는 대신 AI를 5장 놓쳤고, 나머지 둘은 AI를 다 잡는 대신 진짜 사진 5장을 의심했습니다. 오답이 겹치지 않아 중앙값(다수결)으로 묶었더니 94.3%가 됐습니다. → [ADR-7](docs/ADR.md)

**3. 원인을 잘못 짚은 것도 지우지 않았습니다**
배포본을 서버 로그만 보고 진단하다 두 번 틀렸습니다. 한 번은 제가 넣은 코드를 범인으로 지목했는데 그 코드는 배포된 적조차 없었습니다. 그래서 배포된 코드와 모델 상태를 밖에서 확인하는 `/diagnostics`를 만들었습니다. → [ADR-10](docs/ADR.md)

### 숫자로 보면

| 항목 | 전 | 후 |
| --- | --- | --- |
| 테스트 | 31개 | 178개 |
| 커버리지 (backend + ai_models) | 54% | 82% |
| 이미지 판별 정확도 (같은 표본 35장) | 85.7% | 94.3% |
| 뉴스 판별 응답 | 약 16초 | 1.3초 |
| 영상 판정 시간 / 메모리 | 13.3초 / 300MB | 6.1초 / 10MB |
| 로그인 페이지 전송량 | 787KB | 34KB |
| 기록한 버그·장애 | — | 28건 |

---

## 목차

- [빠른 실행](#빠른-실행)
- [기능](#기능)
- [기술 스택](#기술-스택)
- [판별 방식](#판별-방식)
- [알려진 한계](#알려진-한계)
- [배포](#배포)
- [문서](#문서)

---

## 빠른 실행

MariaDB · Redis를 설치하지 않고 SQLite로 바로 뜹니다. **clone 후 3분**이면 됩니다.

```bash
cd TruthLensFlask
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env              # 기본값(SQLite)만으로 실행 가능
python app.py                     # http://localhost:3000
```

`/auth/email/signup`으로 가입 후 로그인하면 전체 기능을 쓸 수 있습니다. 인증은 이메일 · 비밀번호 방식만 지원합니다. 라이브 데모는 시연용 계정(`1234@lens.com` / `12345678`)으로 바로 들어가실 수 있습니다.

**Docker로 실행**

```bash
docker compose up                              # SQLite 기반, http://localhost:3000
DATABASE_URL= docker compose --profile full up # MariaDB + Redis 조합
```

**테스트**

```bash
python -m pytest -q
python -m pytest --cov=backend --cov-report=term-missing
```

<details>
<summary><b>API 키가 필요한 기능</b></summary>

| 기능 | 키 | 없으면 |
| --- | --- | --- |
| 뉴스 · 논문 판별 | `GEMINI_API_KEY` | 앱은 정상 구동, 해당 기능만 에러 반환 |
| 이미지 · 영상 판별 | `HF_TOKEN` (선택) | 에러 대신 OpenCV 픽셀 휴리스틱으로 폴백 |

휴리스틱 모드는 정확도가 크게 떨어집니다. 어느 방식으로 판정했는지는 결과의 `details.method`(`hf-ensemble` / `local-heuristic`)에 항상 찍힙니다. 이미지 판별은 키 없이도 눌러볼 수 있습니다.

</details>

---

## 기능

PRD 설계와 실제 구현이 다른 부분을 그대로 적었습니다.

| 기능 | 상태 | 실제 구현 |
| --- | --- | --- |
| FR-01 영상 | 🧪 실험적 | 직접 링크 · 파일(MP4/AVI/MOV/WEBM). 프레임 6장을 이미지 앙상블로 판정하고 실측 정확도 경고를 함께 반환. 배포본은 앞단 프록시 제한으로 96MB까지 |
| FR-02 이미지 | ✅ 동작 | 1장씩. 모델 3개 중앙값 + 픽셀 휴리스틱 + EXIF + 히트맵 |
| FR-03 뉴스 | ✅ 동작 | 가짜뉴스 점수 · 출처 신뢰도 · 논리성 · 과장 표현 · 의심 문장. 팩트체크 기사 링크는 미구현 |
| FR-04 논문 | ⚠️ 부분 | AI 생성 비율 · 자동 요약 · 인용 목록 추출 · 리포트 PDF. **인용 교차 검증과 누락 인용 탐지는 미구현** |
| FR-05 캐싱 · 집계 | ✅ 동작 | 콘텐츠 해시 기준 캐시, 분석 요청자 수 표시 |

**목표 대비 결과**

| 목표 | 결과 |
| --- | --- |
| AI 생성 판별 정확도 85% 이상 | 이미지 94.3% (자체 표본 35장) · **영상 37%로 미달** |
| 판별 근거 시각화 | 히트맵 · EXIF · 의심 문장 · 판정 방식 표기 |
| 반복 요청 캐싱 | Redis(24h) · DB(7일) 두 방식으로 구현 |
| 논문 요약 자동 생성 | 구현 |
| 논문 누락 인용 탐지 | **미구현** |

<details>
<summary><b>화면 구조</b></summary>

| 화면 | 경로 | 주요 기능 |
| --- | --- | --- |
| 메인 | `/` | 서비스 소개, 판별 유형 선택 |
| 영상 판별 | `/detect/video` | URL · 파일 입력, 분석 진행 표시 |
| 이미지 판별 | `/detect/image` | 이미지 업로드 (현재 1장씩) |
| 뉴스 판별 | `/detect/news` | URL · 텍스트 입력 |
| 논문 판별 | `/detect/paper` | PDF 업로드, 요약 · 인용 분석 |
| 판별 결과 | `/result/:id` | 신뢰 점수 게이지, 판별 근거, 분석 요청자 수, 캐시 배지 |
| 판별 이력 | `/history` | 과거 요청 목록 및 재조회 |

모바일(320px+) · 태블릿(768px+) · 데스크탑(1280px+) 반응형이고, 모바일에서는 카메라 · 갤러리 업로드를 지원합니다.

</details>

---

## 기술 스택

코드에서 실제로 쓰고 있는 것만 적었습니다.

| 레이어 | 기술 |
| --- | --- |
| Frontend | Jinja2 · Tailwind CSS(CLI 빌드) · Vanilla JS |
| Backend | Python 3.11 · Flask 3 · Blueprint 8개 · Flask-SQLAlchemy |
| 이미지 · 영상 | OpenCV(headless) · NumPy · Pillow · piexif |
| AI 판별 | Hugging Face 추론 API(이미지 · 영상 앙상블 3모델) · Google Gemini(뉴스 · 논문) |
| 본문 추출 · PDF | BeautifulSoup4 · lxml · requests · pypdf · reportlab |
| Database | PostgreSQL(배포) · MariaDB(compose) · SQLite(로컬 기본) |
| Cache | Redis |
| WSGI · 배포 | Gunicorn · ProxyFix · Docker · 클라우드타입 |
| 테스트 | pytest · pytest-cov · GitHub Actions |

저장소에 있지만 요청 경로에서 쓰지 않는 것이 하나 있습니다. Celery 태스크(`tasks/video_tasks.py`)를 정의해뒀지만 `video_service.py`는 아직 동기로 처리합니다. 영상 판정이 gunicorn 타임아웃을 넘기지 않도록 프레임 수와 동시 호출로 먼저 맞춰둔 상태입니다.

Flask 구현은 [`TruthLensFlask/`](TruthLensFlask)에 있습니다.

---

## 판별 방식

**계층** — 라우트는 HTTP만, 서비스는 트랜잭션 · 캐시 · 집계만, 판별기는 분석만 맡습니다. 판별기는 Flask를 import 하지 않아서 웹 없이 단독으로 돌려볼 수 있습니다.

```
Route  →  Service  →  Detector
             ↓
      Content Hash → Cache → DB 기록
```

**캐시를 두 가지로 씁니다**

| 도메인 | 저장소 | TTL | 이유 |
| --- | --- | --- | --- |
| 영상 · 이미지 · 논문 | Redis (`cache/redis_client.py`) | 24시간 | 분석 비용이 커서 캐시 히트 시 1초 안에 돌려줘야 함. Redis가 없으면 캐시 미스로 처리되고 기능은 그대로 동작 |
| 뉴스 | DB (`DetectionRequest` 조회) | 7일 | 판별 이력 · 통계(FR-05)와 캐시 판단을 테이블 한 번 조회로 같이 처리할 수 있어 기존 레코드를 재사용 |

두 방식이 갈라져 있는 건 알려진 기술 부채입니다. 뉴스도 Redis로 옮기면 TTL · 무효화 규칙을 한 곳에서 볼 수 있습니다.

<details>
<summary><b>판별 기법 상세</b></summary>

**이미지** — 노이즈(채널별 Laplacian 분산) · 엣지(Canny 밀도) · 색상 분포 3축 휴리스틱에 EXIF 분석을 더하고, `HF_TOKEN`이 있으면 학습 모델 3개를 동시 호출해 중앙값으로 판정합니다. 의심 영역 히트맵을 base64로 만들어 응답에 같이 실어 보냅니다.

**영상** — OpenCV로 6프레임을 뽑아 즉시 640px로 줄이고, 프레임마다 이미지 앙상블 3모델을 동시에 부릅니다(프레임 × 모델 18콜을 한 번에). 영상 점수는 프레임 점수들의 중앙값입니다. 시간적 일관성은 계산은 하되 점수에 넣지 않습니다 — 근거 없는 임계값이 멀쩡한 영상을 흔들었습니다.

**뉴스** — Gemini에 AI 작성 여부 · 가짜뉴스 가능성 · 출처 신뢰도 · 논리성 · 과장 표현 · 의심 문장을 한 번에 물어봅니다. URL이면 BeautifulSoup4로 본문만 긁어 넘깁니다.

**논문** — pypdf로 텍스트를 뽑아 Gemini에 판정을 맡기고 reportlab으로 리포트 PDF를 만듭니다. 한글 폰트는 캐시 → 시스템 → 다운로드 순으로 찾고, 셋 다 실패하면 `KoreanFontUnavailable`을 던지고 멈춥니다. 한글이 네모로 깨진 PDF를 조용히 내보내느니 실패시키는 게 낫다고 봤습니다.

</details>

---

## 알려진 한계

- **영상 판별 정확도가 기준선보다 낮습니다.** 공개 데이터셋(deepaction_v1) AI 12개 / 진본 15개로 재서 **37.0%**입니다. 무조건 "진본"이라고 답할 때(55.6%)나 동전 던지기(50%)보다 못합니다. 지우는 대신 실측값을 화면에 그대로 띄우고 실험적 기능으로 표시했습니다. → [TROUBLESHOOTING 26~27번](docs/TROUBLESHOOTING.md)
- **이미지 판별 정확도는 자체 표본 35장 기준입니다.** 해상도 · 촬영 기기가 편중돼 있어 일반적인 정확도로 읽으면 안 됩니다.
- **이미지는 1장씩만 분석합니다.** 여러 장을 한 요청에서 순차 분석하면 gunicorn 기본 타임아웃(30초)을 넘겨 워커가 끊깁니다. 초과분은 조용히 자르지 않고 `IMAGE_COUNT_EXCEEDED`로 거절합니다.
- **논문 인용 교차 검증 · 누락 인용 탐지는 미구현입니다.** `citation_service.py`에 자리만 잡아뒀습니다.
- **업로드 파일은 배포 컨테이너 재시작마다 사라집니다.** DB는 외부 PostgreSQL로 옮겼지만 `uploads/`는 아직 컨테이너 디스크에 있습니다.
- **프론트엔드 테스트 러너가 없습니다.** 서버 응답 형식을 통일해놓고 프론트가 그걸 잘못 읽던 버그를, 백엔드 테스트 156건이 통과하는 동안 못 잡았습니다. → [TROUBLESHOOTING 20번](docs/TROUBLESHOOTING.md)
- **스키마 마이그레이션 도구가 없습니다.** `db.create_all()`은 없는 테이블만 만들고 컬럼 변경은 반영하지 못합니다.

---

## 배포

[클라우드타입](https://cloudtype.io)에 Flask App(Gunicorn)을 올리고, `main` 푸시 시 빌드 · 배포합니다. 키와 DB 접속 정보는 코드에 두지 않고 플랫폼 환경 변수로 관리합니다.

**DB만 밖으로 뺐습니다.** 관리형 DB도 같은 무료 플랜이라 앱과 함께 멈춰서 깨울 대상이 둘로 늘어납니다. 그래서 DB는 컨테이너 밖 상시 가동 PostgreSQL을 `DATABASE_URL`로 붙여 씁니다. → [TROUBLESHOOTING 17번](docs/TROUBLESHOOTING.md)

배포 반영 여부는 `/diagnostics`로 확인합니다. 판별 코드 3개 파일의 내용 해시, 실제 설정값(샘플 프레임 수 등), 외부 모델이 지금 몇 개나 응답하는지를 로그인 없이 볼 수 있습니다. 비밀값은 담지 않고 설정 여부만 참 · 거짓으로 줍니다.

> 라이브 데모는 무료 플랜이라 하루 한 번 멈춥니다. 첫 접속은 깨어날 때까지 잠깐 걸릴 수 있습니다.
> 가입 계정은 외부 DB에 있어 남지만, 업로드한 파일은 재시작마다 초기화됩니다.

<details>
<summary><b>PRD 설계와 실제 배포 구성 차이</b></summary>

| | PRD 설계 | 실제 배포 |
| --- | --- | --- |
| 웹 | Flask App (Gunicorn) | 동일 |
| 비동기 처리 | Celery Worker | **미사용** — 영상 판정을 동기로 처리하고 프레임 수 · 동시 호출로 시간을 맞춤 |
| DB | 클라우드타입 MariaDB | **컨테이너 밖 PostgreSQL** |
| 캐시 | 클라우드타입 Redis | 동일 |

환경은 `dev`(개발) · `qa`(통합 테스트) · `main`(운영) 세 단계로 나눠 뒀습니다.

</details>

---

## 문서

| 문서 | 내용 |
| --- | --- |
| [`docs/PORTFOLIO.md`](docs/PORTFOLIO.md) | 무엇을 왜 그렇게 만들었는지 |
| [`docs/ADR.md`](docs/ADR.md) | 설계 결정 10건 — 고려한 대안, 근거, 나중에 뒤집힌 것 |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | 버그 · 장애 28건 — 증상, 재현 조건, 시도했지만 안 된 것, 검증 |
| [`docs/RETROSPECTIVE.md`](docs/RETROSPECTIVE.md) | 회고 — 잘한 것, 아쉬운 것, 다음에 할 것 |
| [`docs/DEMO.md`](docs/DEMO.md) | 시연 시나리오 |
| [`docs/slides/TruthLens_Portfolio.html`](docs/slides/TruthLens_Portfolio.html) | 발표 슬라이드 11장 (브라우저로 열면 됩니다) |

---

## 라이선스

[MIT](LICENSE)
