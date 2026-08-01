# Google OAuth 로그인 설계

**날짜:** 2026-06-16  
**범위:** Google OAuth 2.0 로그인 + 전체 라우트 인증 게이트

## 목표

- 사이트 진입 시 로그인 화면이 가장 먼저 노출
- Google 계정으로 로그인, 최초 로그인 시 DB에 사용자 등록
- 재방문 시 `last_login_at` 갱신

## 라이브러리

- `Authlib` — Google OAuth 2.0 흐름 처리
- `Flask-Login` — 세션 관리 및 `@login_required` 데코레이터

## 신규 파일

| 파일 | 역할 |
|---|---|
| `backend/auth/__init__.py` | auth 블루프린트 패키지 |
| `backend/auth/routes.py` | `/auth/google`, `/auth/google/callback`, `/auth/logout` |
| `backend/models/user.py` | `User` ORM 모델 (Flask-Login `UserMixin` 상속) |

## 변경 파일

| 파일 | 변경 내용 |
|---|---|
| `requirements.txt` | `Authlib`, `Flask-Login` 추가 |
| `config.py` | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` 추가 |
| `app.py` | `LoginManager` 초기화, auth 블루프린트 등록 |
| `backend/routes/*.py` | 모든 라우트에 `@login_required` 추가 |

## User 모델 (users 테이블)

```
id, email (unique), name, google_sub (Google 고유 ID),
role, trust_score, scan_count, accuracy,
created_at, last_login_at
```

`password_hash`는 Google 전용이므로 사용하지 않음 (nullable 유지).

## OAuth 흐름

```
미인증 요청 → Flask-Login → /login 리디렉션
→ "Google로 계속하기" → /auth/google
→ Google 동의 화면
→ /auth/google/callback
→ DB: email로 조회
    - 없으면 INSERT (최초 가입)
    - 있으면 last_login_at UPDATE
→ Flask-Login 세션 등록
→ next 파라미터 또는 / 로 리디렉션
```

## 인증 제외 라우트

- `GET /login`
- `GET /auth/google`
- `GET /auth/google/callback`

나머지 모든 라우트는 `@login_required` 적용.

## 에러 처리

- Google OAuth 실패(사용자 취소, 토큰 오류) → /login 리디렉션 + flash 메시지
- DB 저장 실패 → 로그 기록 후 /login 리디렉션
