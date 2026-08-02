# 제목 : 논문 AI 생성 판별 및 분석
# 담당자 : 허영주

import os
import json
import logging
import re
from pypdf import PdfReader
from openai import OpenAI

# 상위 클래스가 정상적으로 구현되어 있다고 가정합니다.
# from ai_models.base_detector import BaseDetector
class BaseDetector: pass

logger = logging.getLogger(__name__)

# deepseek-chat 컨텍스트(64K 토큰) 안에서 안전한 상한.
# 이 길이를 넘는 논문은 앞부분만 분석되며, 그 사실을 결과에 표시한다.
MAX_ANALYZED_CHARS = int(os.getenv("PAPER_MAX_CHARS", 50000))


class PaperDetector(BaseDetector):
    """논문 AI 생성 판별 및 자동 요약 모델"""

    def __init__(self):
        # 환경변수에서 API KEY 로드 (없어도 여기서는 실패시키지 않고, 실제 호출 시점에 처리한다.
        # 그래야 API 키가 없어도 앱 자체는 정상 기동하고, 해당 기능 호출 시에만 에러를 반환한다)
        api_key = os.getenv("DEEPSEEK_API_KEY")

        # [수정] base_url 끝에 /v1을 명시해 주는 것이 더 안정적입니다.
        self.client = OpenAI(api_key=api_key or "missing", base_url="https://api.deepseek.com/v1")
        self._api_key_configured = bool(api_key)

    def extract_text_from_pdf(self, file_path):
        reader = PdfReader(file_path)
        text = ""

        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

        return text.strip()

    def parse_json_response(self, result_text):
        result_text = result_text.strip()
        # 마크다운 태그 제거 정규식 적용 (더 확실하게 방어)
        result_text = re.sub(r"^```json\s*|```$", "", result_text, flags=re.MULTILINE).strip()

        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            # 완벽한 JSON 형태가 아닐 경우 내부 중괄호 검색 추출
            match = re.search(r"\{.*\}", result_text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError("DeepSeek 응답을 JSON으로 변환하는 데 실패했습니다.")

    def _friendly_error_message(self, error):
        """DeepSeek API 예외를 사용자에게 노출 가능한 한국어 메시지로 변환한다."""
        message = str(error)

        if "DEEPSEEK_API_KEY" in message:
            return message

        if "402" in message or "Insufficient Balance" in message:
            return "DeepSeek API 잔액이 부족합니다. API 키 결제 상태를 확인하세요."

        if "429" in message:
            return "DeepSeek API 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요."

        if "401" in message or "authentication" in message.lower():
            return "DeepSeek API Key가 유효하지 않습니다. 키를 확인하세요."

        return "논문 분석 중 오류가 발생했습니다. 잠시 후 다시 시도하세요."

    def analyze_with_gpt(self, text):
        if not self._api_key_configured:
            raise ValueError("DEEPSEEK_API_KEY가 설정되지 않았습니다. 환경변수를 확인하세요.")

        # deepseek-chat의 컨텍스트는 64K 토큰이라 5만자까지는 안전하게 들어간다.
        # 그래도 200페이지 논문은 넘치므로 잘린 사실을 결과로 되돌려 표시한다.
        # 앞부분만 보고 전체를 판정한 것처럼 보이면 안 된다.
        truncated_text = text[:MAX_ANALYZED_CHARS]

        prompt = f"""
너는 학술 논문의 AI 작성 여부를 정밀 분석하고 요약하는 전문가야.
제공된 논문 텍스트를 바탕으로 지정된 JSON 형식으로 분석 보고서를 작성해줘.

반드시 다른 설명 없이 아래 JSON 포맷을 정확히 지켜서 JSON 데이터만 반환해.
citations 필드는 반드시 배열(List) 형태로 반환한다.

각 citation 객체는 아래 필드를 모두 포함해야 한다.

- citation_ref : 문자열
- status : matched 또는 missing
- doi : 문자열 또는 null
- title : 문자열 또는 null

본문에서 발견된 모든 인용을 citations 배열에 포함한다.

DOI를 찾을 수 없으면 null
제목을 찾을 수 없으면 null
참고문헌과 매칭되면 matched
매칭되지 않으면 missing

포맷 예시:
{{
  "ai_score": 0,
  "ai_reason": "AI 생성 의심 이유 설명",
  "suspicious_paragraphs": ["AI 작성이 의심되는 구체적인 문단 내용"],
  "summary": "논문 핵심 요약 500자 이내",
  "key_claims": ["핵심 주장1", "핵심 주장2", "핵심 주장3"],
  "section_scores": {{
    "introduction": 0,
    "methodology": 0,
    "conclusion": 0
  }},
  "citations": [
    {{
      "citation_ref": "[1]",
      "status": "matched",
      "doi": "10.xxxx/xxxxx",
      "title": "참고문헌 제목"
    }},
    {{
      "citation_ref": "[2]",
      "status": "missing",
      "doi": null,
      "title": null
    }}
  ]
}}

분석할 논문 텍스트:
{truncated_text}
"""
        try:
            # [수정] model명을 "deepseek-chat"으로 변경합니다.
            logger.info("딥시크 메세지 전송")
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2 # 구조화된 데이터를 받아야 하므로 일관성을 위해 낮은 온도로 설정
            )

        except Exception as e:
            logger.error("DeepSeek API 통신 에러 발생: %s", e)
            raise

        result_text = response.choices[0].message.content
        logger.info("DeepSeek 응답 수신 (길이: %d자)", len(result_text or ""))
        logger.debug("DeepSeek 응답 원문: %s", result_text)

        parsed = self.parse_json_response(result_text)

        # 분석 범위를 결과에 함께 실어 보낸다. 잘린 채로 전체 판정처럼
        # 보이면 점수를 신뢰할 수 없다.
        parsed["analyzed_chars"] = len(truncated_text)
        parsed["total_chars"] = len(text)
        parsed["truncated"] = len(text) > len(truncated_text)
        if parsed["truncated"]:
            logger.warning(
                "논문이 길어 앞 %d자만 분석했습니다 (전체 %d자)",
                len(truncated_text), len(text),
                extra={"event": "paper.text.truncated"},
            )

        return parsed

    @staticmethod
    def _scope_note(result):
        """분석 범위를 사람이 읽을 문장으로 만든다."""
        analyzed = result.get("analyzed_chars", 0)
        total = result.get("total_chars", 0)
        if not result.get("truncated"):
            return f"논문 전문({total:,}자)을 분석했습니다."
        percent = round(analyzed / total * 100) if total else 0
        return (
            f"논문이 길어 앞 {analyzed:,}자만 분석했습니다 "
            f"(전체 {total:,}자 중 약 {percent}%). 뒷부분은 판정에 반영되지 않았습니다."
        )

    def detect(self, file_path):
        try:
            text = self.extract_text_from_pdf(file_path)
        except Exception as e:
            logger.error("PDF 텍스트 추출 실패 (%s): %s", file_path, e)
            return {
                "score": 0,
                "details": {
                    "error": f"PDF를 읽는 중 오류가 발생했습니다: {e}",
                    "section_scores": {},
                    "suspicious_paragraphs": [],
                    "summary": "",
                    "key_claims": [],
                },
            }

        logger.info("FILE PATH: %s", file_path)
        logger.info("TEXT LENGTH: %d", len(text))

        if not text:
            return {
                "score": 0,
                "details": {
                    "error": "PDF에서 텍스트를 추출하지 못했습니다.",
                    "section_scores": {},
                    "suspicious_paragraphs": [],
                    "summary": "",
                    "key_claims": [],
                },
            }

        try:
            result = self.analyze_with_gpt(text)
            
            return {
                "score": result.get("ai_score", 0),
                "details": {
                    "ai_reason": result.get("ai_reason", ""),
                    "section_scores": result.get("section_scores", {}),
                    "suspicious_paragraphs": result.get("suspicious_paragraphs", []),
                    "summary": result.get("summary", ""),
                    "key_claims": result.get("key_claims", []),
                    "citations": result.get("citations", []),
                    # 어디까지 읽고 판정했는지 밝힌다
                    "analyzed_chars": result.get("analyzed_chars", 0),
                    "total_chars": result.get("total_chars", 0),
                    "truncated": result.get("truncated", False),
                    "scope_note": self._scope_note(result),
                },
            }

        except Exception as e:
            logger.error("논문 분석 실패: %s", e)
            return {
                "score": 0,
                "details": {
                    "error": self._friendly_error_message(e),
                    "section_scores": {},
                    "suspicious_paragraphs": [],
                    "summary": "",
                    "key_claims": [],
                },
            }