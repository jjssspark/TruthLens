# 시연 가이드

이미지/뉴스/논문/영상 4개 핵심 기능을 시연하는 방법입니다.

## 0. 실행

```bash
cd TruthLensFlask
docker compose up          # 또는: source venv/bin/activate && python app.py
```

브라우저에서 http://localhost:3000 접속 → `/auth/email/signup`에서 이메일 회원가입(비밀번호만 있으면 됨) → 자동 로그인.

## 1. 이미지 판별 (외부 API 키 불필요 — 가장 먼저 보여주기 좋음)

1. 메인 화면 또는 `/detect/image`로 이동
2. 아무 이미지 파일 업로드(JPG/PNG/WebP/GIF)
3. 업로드 진행률 바(%) → "분석 중..." 전환 확인
4. 결과 화면(`/result/:id`)에서 신뢰 점수 게이지, 의심 영역 히트맵, EXIF 메타데이터 분석 확인
5. **진행상황 체크 포인트**: 게이지 퍼센트가 렌더링되고 "AI 생성 가능성 신뢰 점수"가 0이 아닌 값으로 표시되면 정상 동작

## 2. 뉴스 판별 (`GEMINI_API_KEY` 필요)

1. `/detect/news`로 이동
2. URL 또는 텍스트(최대 10,000자) 입력 — 예: 뉴스 기사 URL 하나
3. 결과 화면에서 AI 생성/가짜뉴스 가능성 점수, 출처 신뢰도, 의심 문장 하이라이트 확인
4. **API 키가 없는 경우**: 에러 없이 200 응답하며 "Gemini API Key를 확인하세요."가 상세 분석 영역에 표시됨 — 이 메시지가 뜨는 것 자체가 Day2에서 만든 예외 처리가 정상 동작 중이라는 증거

## 3. 논문 판별 (`DEEPSEEK_API_KEY` 필요)

1. `/detect/paper`로 이동
2. PDF 업로드(최대 50MB)
3. 결과 화면에서 섹션별 AI 생성 비율, 자동 요약, 인용 교차 검증 결과 확인
4. **API 키가 없는 경우**: "DEEPSEEK_API_KEY가 설정되지 않았습니다." 메시지로 정상 처리되는 것을 확인 (앱이 죽지 않음)

## 4. 영상 판별 (외부 API 키 불필요 — OpenCV 로컬 휴리스틱)

1. `/detect/video`로 이동
2. MP4/AVI/MOV/WEBM 파일 업로드 (또는 직접 링크된 영상 URL 입력 — YouTube/Vimeo 페이지 링크는 미지원)
3. 결과 화면에서 딥페이크 탐지 여부, 의심 구간 타임스탬프 확인
4. 프레임을 최대 16장 균등 샘플링해 이미지 판별과 동일한 노이즈/엣지/색상 휴리스틱 + 프레임 간 시간적 일관성을 분석하는 방식으로, 상용 딥러닝 딥페이크 탐지 모델과는 다름을 짧게 언급하면 됩니다.

## 진행 상황을 확인하는 방법 (개발 중 셀프 체크)

| 확인 항목 | 명령 | 통과 기준 |
| --- | --- | --- |
| 전체 테스트 | `python -m pytest -q` | 전부 `passed`, 회귀 없음 |
| 커버리지 | `python -m pytest --cov=backend --cov-report=term-missing` | `backend/routes/*`, `backend/services/*` 커버리지 확인 |
| Docker 기동 | `docker compose up` → `curl -I http://localhost:3000/login` | `HTTP/1.1 200 OK` |
| 회귀 없는지 | `git status` / `git diff` | 의도한 파일만 변경됐는지 확인 |
| 실제 플로우 | 브라우저로 회원가입 → 이미지/뉴스/논문 각 1건 분석 → 결과 페이지 진입 | 각 결과 페이지가 에러 없이 렌더링 |

## 백업 자료

네트워크가 막혀 있거나(API 키 쿼터 소진 등) 라이브 시연이 어려운 경우를 대비해
`docs/demo/` 폴더의 GIF를 백업 시연 자료로 사용하세요(이미지 판별 플로우 1건 기록).
