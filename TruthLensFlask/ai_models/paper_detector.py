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

# 모델 컨텍스트 안에서 안전한 상한. 발췌 샘플링(build_representative_excerpt)이
# 이 값을 예산으로 쓴다.
MAX_ANALYZED_CHARS = int(os.getenv("PAPER_MAX_CHARS", 50000))

# 논문 판별은 OpenAI 호환 엔드포인트를 통해 호출한다.
#
# 원래 DeepSeek을 썼는데 잔액이 떨어지면 402 하나로 기능 전체가 멈춘다(TS-6에서
# 이미 겪었고 다시 발생했다). 뉴스가 이미 쓰는 Gemini 키를 재사용해 외부 결제
# 의존을 하나 줄인다. Gemini는 OpenAI 호환 엔드포인트를 제공하므로 base_url과
# 모델명만 바꾸면 프롬프트·JSON 파싱·발췌 샘플링·인용 분석은 그대로 돈다.
#
# 다른 제공자로 되돌리려면 이 두 환경변수와 PAPER_API_KEY만 지정하면 된다.
# getenv의 기본값 인자를 쓰면 안 된다. .env에 "PAPER_MODEL=" 처럼 키만 있고 값이
# 비면 빈 문자열이 반환돼 기본값이 무시되고 호출이 깨진다. or로 받는다.
PAPER_API_BASE_URL = (
    os.getenv("PAPER_API_BASE_URL")
    or "https://generativelanguage.googleapis.com/v1beta/openai/"
)
PAPER_MODEL = os.getenv("PAPER_MODEL") or "gemini-2.5-flash-lite"

# 참고문헌 시작을 알리는 제목. 줄 전체가 이것으로 시작할 때만 자른다
# (본문에 "references"라는 단어가 나오는 것과 구분하기 위해).
REFERENCE_HEADINGS = re.compile(
    r'^\s*(?:\d+\s*\.?\s*)?(references?|bibliography|works\s+cited|참고\s*문헌|참고자료|인용\s*문헌)\s*$',
    re.IGNORECASE | re.MULTILINE,
)

# 발췌 구간 사이에 넣어 텍스트가 이어지지 않음을 모델에 알린다
EXCERPT_SEPARATOR = "\n\n[... 중략 ...]\n\n"

# 예산 배분: 서론부 35% / 중간 45% / 결론부 20%
HEAD_RATIO, TAIL_RATIO = 0.35, 0.20
MIDDLE_WINDOWS = 3


def strip_references(text):
    """참고문헌 이후를 잘라낸다.

    서지 정보는 형식이 정형화돼 판별에 기여하지 않으면서 분량의 20~40%를
    차지한다. 남겨두면 정작 봐야 할 본문이 예산 밖으로 밀려난다.
    """
    matches = list(REFERENCE_HEADINGS.finditer(text))
    if not matches:
        return text
    # 본문 초반의 오탐을 피해 문서 후반부에 나온 마지막 제목을 기준으로 자른다
    last = matches[-1]
    if last.start() < len(text) * 0.4:
        return text
    return text[:last.start()]


def strip_repeated_lines(text, min_repeats=4, min_kept_ratio=0.6):
    """페이지마다 반복되는 머리말·꼬리말과 쪽번호를 제거한다.

    반복 줄이 항상 잡음인 것은 아니다. 표 행이나 짧은 항목 나열이 많은
    논문에서는 본문이 통째로 날아갈 수 있다. 결과가 원문의 min_kept_ratio
    미만으로 줄면 제거를 포기하고 원문을 그대로 돌려준다.
    """
    lines = text.split('\n')
    counts = {}
    for line in lines:
        stripped = line.strip()
        if 0 < len(stripped) <= 80:
            counts[stripped] = counts.get(stripped, 0) + 1

    noise = {s for s, n in counts.items() if n >= min_repeats}
    cleaned = '\n'.join(
        line for line in lines
        if line.strip() not in noise and not re.fullmatch(r'\s*\d{1,4}\s*', line)
    )

    if text and len(cleaned) < len(text) * min_kept_ratio:
        logger.warning(
            "반복 줄 제거가 본문의 %d%%를 지워 건너뜁니다 (%d자 → %d자)",
            round((1 - len(cleaned) / len(text)) * 100), len(text), len(cleaned),
            extra={"event": "paper.text.strip_skipped"},
        )
        return text

    return cleaned


def build_representative_excerpt(text, limit=MAX_ANALYZED_CHARS):
    """문서 전체에서 고르게 뽑은 발췌문을 만든다.

    앞에서부터 자르면 표지·목차·초록·서론만 읽게 되고, AI 생성 흔적이
    잘 드러나는 본론·고찰은 통째로 빠진다. 영상 판별이 프레임을 균등
    샘플링하는 것과 같은 이유다.
    """
    if len(text) <= limit:
        return text, 1

    budget = limit - len(EXCERPT_SEPARATOR) * MIDDLE_WINDOWS
    head_len = int(budget * HEAD_RATIO)
    tail_len = int(budget * TAIL_RATIO)
    window_len = (budget - head_len - tail_len) // MIDDLE_WINDOWS

    segments = [text[:head_len]]

    middle_start, middle_end = head_len, len(text) - tail_len
    span = middle_end - middle_start
    for i in range(MIDDLE_WINDOWS):
        # 각 구간의 중앙에서 창을 연다
        center = middle_start + int(span * (i + 0.5) / MIDDLE_WINDOWS)
        start = max(middle_start, center - window_len // 2)
        segments.append(text[start:start + window_len])

    segments.append(text[-tail_len:])

    return EXCERPT_SEPARATOR.join(segments), len(segments)


class PaperDetector(BaseDetector):
    """논문 AI 생성 판별 및 자동 요약 모델"""

    def __init__(self):
        # 환경변수에서 API KEY 로드 (없어도 여기서는 실패시키지 않고, 실제 호출 시점에 처리한다.
        # 그래야 API 키가 없어도 앱 자체는 정상 기동하고, 해당 기능 호출 시에만 에러를 반환한다)
        # PAPER_API_KEY를 주면 그쪽을 우선한다 — 제공자를 바꿀 때 코드를 안 고쳐도 된다.
        api_key = os.getenv("PAPER_API_KEY") or os.getenv("GEMINI_API_KEY")

        self.client = OpenAI(api_key=api_key or "missing", base_url=PAPER_API_BASE_URL)
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
            raise ValueError("분석 API 응답을 JSON으로 변환하는 데 실패했습니다.")

    def _friendly_error_message(self, error):
        """분석 API 예외를 사용자에게 노출 가능한 한국어 메시지로 변환한다.

        원문에는 엔드포인트 주소와 내부 코드가 섞여 있어 그대로 보여주면 안 된다.
        """
        message = str(error)

        if "API_KEY가 설정되지 않았습니다" in message:
            return message

        if "402" in message or "Insufficient Balance" in message:
            return "분석 API 잔액이 부족합니다. API 키 결제 상태를 확인하세요."

        if "429" in message or "RESOURCE_EXHAUSTED" in message:
            return "분석 API 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요."

        # 뉴스 판별에서 겪은 것과 같은 상황 — 키가 아니라 OAuth 토큰으로 인증되면
        # 스코프가 모자라 403이 난다. 키 미설정과 증상이 달라 따로 안내한다.
        if "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in message:
            return "분석 API 키가 전달되지 않았습니다. GEMINI_API_KEY 환경변수를 확인하세요."

        if "401" in message or "API_KEY_INVALID" in message or "authentication" in message.lower():
            return "분석 API Key가 유효하지 않습니다. 키를 확인하세요."

        return "논문 분석 중 오류가 발생했습니다. 잠시 후 다시 시도하세요."

    def analyze_with_gpt(self, text):
        if not self._api_key_configured:
            raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다. 환경변수를 확인하세요.")

        # 판별에 기여하지 않는 부분을 먼저 걷어내고, 남은 본문에서 고르게 뽑는다.
        # 어디를 읽었는지는 결과에 표시한다 — 앞부분만 보고 전체를 판정한 것처럼
        # 보이면 안 된다.
        body = strip_repeated_lines(strip_references(text))
        truncated_text, segment_count = build_representative_excerpt(body, MAX_ANALYZED_CHARS)

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
            logger.info("논문 분석 요청 전송", extra={"event": "paper.api.request"})
            response = self.client.chat.completions.create(
                model=PAPER_MODEL,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2 # 구조화된 데이터를 받아야 하므로 일관성을 위해 낮은 온도로 설정
            )

        except Exception as e:
            logger.error("분석 API 통신 에러 발생: %s", e)
            raise

        result_text = response.choices[0].message.content
        logger.info("분석 API 응답 수신 (길이: %d자)", len(result_text or ""))
        logger.debug("분석 API 응답 원문: %s", result_text)

        parsed = self.parse_json_response(result_text)

        # 분석 범위를 결과에 함께 실어 보낸다. 잘린 채로 전체 판정처럼
        # 보이면 점수를 신뢰할 수 없다.
        parsed["analyzed_chars"] = len(truncated_text)
        parsed["total_chars"] = len(text)
        parsed["body_chars"] = len(body)
        parsed["segments"] = segment_count
        parsed["truncated"] = len(body) > len(truncated_text)
        if parsed["truncated"]:
            logger.warning(
                "논문이 길어 본문 %d자 중 %d자를 %d개 구간으로 나눠 분석했습니다 (원문 %d자)",
                len(body), len(truncated_text), segment_count, len(text),
                extra={"event": "paper.text.sampled"},
            )

        return parsed

    @staticmethod
    def _scope_note(result):
        """분석 범위를 사람이 읽을 문장으로 만든다."""
        analyzed = result.get("analyzed_chars", 0)
        total = result.get("total_chars", 0)
        body = result.get("body_chars", total)

        trimmed = ""
        if total and body < total:
            trimmed = f" 참고문헌·반복 머리말 {total - body:,}자는 분석에서 제외했습니다."

        if not result.get("truncated"):
            return f"본문 전체({body:,}자)를 분석했습니다.{trimmed}"

        percent = round(analyzed / body * 100) if body else 0
        return (
            f"본문 {body:,}자 중 {analyzed:,}자(약 {percent}%)를 "
            f"서론·본론·결론에서 고르게 뽑아 분석했습니다.{trimmed} "
            f"발췌되지 않은 구간은 판정에 반영되지 않았습니다."
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
                    "body_chars": result.get("body_chars", 0),
                    "segments": result.get("segments", 1),
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