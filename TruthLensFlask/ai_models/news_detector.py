import json
import os
import re

import google.generativeai as genai

from ai_models.base_detector import BaseDetector
from config import Config


GEMINI_TIMEOUT_SEC = int(os.getenv("GEMINI_TIMEOUT_SEC", 30))


class NewsAnalysisError(RuntimeError):
    """뉴스 분석에 실패한 경우.

    ValueError를 쓰면 안 된다. 라우트가 ValueError를 사용자 입력 오류로 보고
    400 INPUT_REQUIRED를 반환하는데, 외부 API 장애는 사용자 잘못이 아니다.
    """


class NewsDetector(BaseDetector):
    """
    뉴스 AI 생성 및 가짜뉴스 판별 모델 (FR-03)

    Gemini를 이용하여

    - AI 생성 여부
    - 가짜뉴스 가능성
    - 출처 신뢰도
    - 논리성
    - 과장 표현
    - 의심 문장

    을 함께 분석한다.
    """

    def __init__(self):
        """
        Gemini 모델 초기화
        """

        genai.configure(api_key=Config.GEMINI_API_KEY)

        # gemini-2.5-flash는 내부 추론(thinking)을 수행해 같은 프롬프트에서
        # 약 16초가 걸린다. lite는 1.3초로 12배 빠르다. 구 SDK
        # (google-generativeai)는 thinking_config를 지원하지 않아 추론만
        # 끌 방법이 없으므로 모델 선택으로 해결한다.
        # 정확도를 우선하려면 GEMINI_MODEL=gemini-2.5-flash로 되돌린다.
        self.model = genai.GenerativeModel(
            model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        )

    def detect(self, content):
        """
        뉴스 분석

        Parameters
        ----------
        content : str
            URL 또는 기사 본문

        Returns
        -------
        dict
        """

        prompt = self._make_prompt(content)

        try:

            #############################################
            # Gemini 호출
            #############################################

            # 타임아웃이 없으면 응답이 늦을 때 요청 스레드가 무한정 묶인다
            response = self.model.generate_content(
                prompt, request_options={"timeout": GEMINI_TIMEOUT_SEC}
            )

            #############################################
            # 응답 문자열
            #############################################

            response_text = response.text.strip()

            #############################################
            # Markdown 제거
            #
            # Gemini는 종종
            #
            # ```json
            # {...}
            # ```
            #
            # 형태로 반환하므로 제거한다.
            #############################################

            response_text = re.sub(
                r"```json|```",
                "",
                response_text
            ).strip()

            #############################################
            # JSON 파싱
            #############################################

            result = json.loads(response_text)

            #############################################
            # 점수 보정
            #############################################

            ai_score = max(
                0,
                min(
                    100,
                    float(result.get("ai_score", 0))
                )
            )

            fake_score = max(
                0,
                min(
                    100,
                    float(result.get("fake_news_score", 0))
                )
            )

            #############################################
            # 반환
            #############################################

            return {

                "score": ai_score,

                "details": {

                    "fake_news_score": fake_score,

                    "source_trust":
                        result.get(
                            "source_trust",
                            "알 수 없음"
                        ),

                    "logic":
                        result.get(
                            "logic",
                            "분석 실패"
                        ),

                    "exaggeration":
                        result.get(
                            "exaggeration",
                            "없음"
                        ),

                    "suspicious_sentences":
                        result.get(
                            "suspicious_sentences",
                            []
                        )

                }

            }

        #############################################
        # 실패는 실패로 올린다
        #
        # 예전에는 여기서 score 0짜리 dict를 지어내 반환했다. 그러면
        # (1) 라우트의 502 분기가 영영 실행되지 않아 HTTP 200이 나가고,
        # (2) 실패가 status='done'으로 저장돼 7일간 캐시되며,
        # (3) 구글 에러 원문이 '논리성' 칸에 그대로 표시됐다.
        # 원문은 로그에만 남기고(news_routes), 호출부가 502로 응답하게 한다.
        #############################################

        except json.JSONDecodeError as e:

            raise NewsAnalysisError(
                f"Gemini 응답을 JSON으로 변환하지 못했습니다: {e}"
            ) from e

        except Exception as e:

            raise NewsAnalysisError(f"Gemini 호출 실패: {e}") from e

    #######################################################
    # Prompt 생성
    #######################################################

    def _make_prompt(self, content):

        return f"""
당신은 뉴스 팩트체크 전문 AI입니다.

아래 기사 본문만 분석하세요.

다른 내용을 추론하지 마세요.

관련 기사,
광고,
댓글,
기자 정보는
모두 무시하세요.

본문:

=========================
{content}
=========================

다음 항목을 반드시 분석하세요.

1.
AI가 작성했을 가능성
(0~100)

2.
가짜뉴스일 가능성
(0~100)

3.
출처 신뢰도
(높음 / 보통 / 낮음)

4.
논리성 평가

5.
과장 표현 여부

6.
의심되는 문장
최대 3개

주의사항

- JSON만 출력
- 설명 금지
- 코드블럭 금지
- 마크다운 금지

반드시 아래 형식만 출력

{{
    "ai_score": 72,
    "fake_news_score": 40,
    "source_trust": "보통",
    "logic": "주장의 근거가 일부 부족합니다.",
    "exaggeration": "다소 과장된 표현이 존재합니다.",
    "suspicious_sentences": [
        "...",
        "...",
        "..."
    ]
}}
"""