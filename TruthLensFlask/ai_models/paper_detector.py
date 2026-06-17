# 제목 : 논문 AI 생성 판별 및 분석
# 담당자 : 허영주

import os
import json
import re
from pypdf import PdfReader
from openai import OpenAI

# 상위 클래스가 정상적으로 구현되어 있다고 가정합니다.
# from ai_models.base_detector import BaseDetector
class BaseDetector: pass 

class PaperDetector(BaseDetector):
    """논문 AI 생성 판별 및 자동 요약 모델"""

    def __init__(self):
        # 환경변수에서 API KEY 로드
        api_key = os.getenv("DEEPSEEK_API_KEY")
        
        print("API KEY 로드 확인:", "성공" if api_key else "실패")

        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY가 설정되지 않았습니다. 환경변수를 확인하세요.")

        # [수정] base_url 끝에 /v1을 명시해 주는 것이 더 안정적입니다.
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")

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

    def analyze_with_gpt(self, text):
        # [수정] 입력 텍스트를 최소 15,000자 이상으로 늘려 논문 전체가 들어갈 수 있도록 합니다.
        # DeepSeek는 비용이 저렴하므로 더 늘려도 무방합니다.
        truncated_text = text[:20000]

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
            print("딥시크 메세지 전송")
            response = self.client.chat.completions.create(
                model="deepseek-chat", 
                messages=[
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2 # 구조화된 데이터를 받아야 하므로 일관성을 위해 낮은 온도로 설정
            )
            
        except Exception as e:
            print("DeepSeek API 통신 에러 발생:", e)
            raise
        
        result_text = response.choices[0].message.content
        print("===== DEEPSEEK RESPONSE =====")
        print(result_text)
        print("=============================")

        return self.parse_json_response(result_text)

    def detect(self, file_path):
        text = self.extract_text_from_pdf(file_path)
        
        print("FILE PATH:", file_path)
        print("TEXT LENGTH:", len(text))

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
                },
            }

        except Exception as e:
            return {
                "score": 0,
                "details": {
                    "error": str(e),
                    "section_scores": {},
                    "suspicious_paragraphs": [],
                    "summary": "",
                    "key_claims": [],
                },
            }