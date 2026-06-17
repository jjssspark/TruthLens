import os
import io
import urllib.request
from flask import current_app
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 나눔고딕 폰트 다운로드용 URL 설정 (정형화된 구글 폰트 주소)
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
FONT_BOLD_URL = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"

class PDFService:
    """분석 결과 리포트를 PDF 형식으로 생성하는 서비스 클래스 (한글 대응 포함)"""

    def __init__(self):
        # Flask 어플리케이션 루트 경로의 cache 폴더를 폰트 다운로드 저장소로 사용
        self.cache_dir = os.path.join(current_app.root_path, "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.font_path = os.path.join(self.cache_dir, "NanumGothic-Regular.ttf")
        self.font_bold_path = os.path.join(self.cache_dir, "NanumGothic-Bold.ttf")
        self._ensure_fonts()

    def _ensure_fonts(self):
        """한글 폰트가 로컬에 캐싱되어 있는지 확인하고 없으면 다운로드하거나 시스템 폰트로 폴백합니다."""
        # 일반(Regular) 폰트 파일 보장
        if not os.path.exists(self.font_path):
            try:
                print("구글 폰트 저장소에서 NanumGothic-Regular 다운로드 중...")
                urllib.request.urlretrieve(FONT_URL, self.font_path)
            except Exception as e:
                print(f"폰트 다운로드 중 오류 발생: {e}. Windows 시스템 폰트로 폴백 시도합니다.")
                # Windows 환경 맑은 고딕 폴백 경로 지정
                win_font = r"C:\Windows\Fonts\malgun.ttf"
                if os.path.exists(win_font):
                    self.font_path = win_font
                else:
                    print("Windows 시스템 폰트(malgun.ttf)를 찾을 수 없습니다. 기본 폰트를 사용합니다.")

        # 볼드(Bold) 폰트 파일 보장
        if not os.path.exists(self.font_bold_path):
            try:
                print("구글 폰트 저장소에서 NanumGothic-Bold 다운로드 중...")
                urllib.request.urlretrieve(FONT_BOLD_URL, self.font_bold_path)
            except Exception as e:
                print(f"볼드 폰트 다운로드 중 오류 발생: {e}. Windows 시스템 볼드 폰트로 폴백 시도합니다.")
                win_font_bold = r"C:\Windows\Fonts\malgunbd.ttf"
                if os.path.exists(win_font_bold):
                    self.font_bold_path = win_font_bold
                else:
                    self.font_bold_path = self.font_path  # 볼드 폰트가 없으면 일반 폰트로 대체 적용

        # ReportLab 엔진에 한글 폰트 등록
        try:
            if os.path.exists(self.font_path):
                pdfmetrics.registerFont(TTFont('NanumGothic', self.font_path))
            if os.path.exists(self.font_bold_path):
                pdfmetrics.registerFont(TTFont('NanumGothic-Bold', self.font_bold_path))
        except Exception as e:
            print(f"ReportLab 한글 폰트 등록에 실패하였습니다 (기본 Helvetica로 대체됩니다): {e}")

    def generate_report_pdf(self, request, result):
        """요청 및 결과 데이터를 조합하여 세련된 디자인의 PDF 보고서 바이너리를 생성합니다."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
        )

        styles = getSampleStyleSheet()
        
        # 폰트 활성화 여부에 따른 동적 폰트명 바인딩
        registered_fonts = pdfmetrics.getRegisteredFontNames()
        regular_font_name = 'NanumGothic' if 'NanumGothic' in registered_fonts else 'Helvetica'
        bold_font_name = 'NanumGothic-Bold' if 'NanumGothic-Bold' in registered_fonts else 'Helvetica-Bold'

        # 레이아웃 타이포그래피 스타일 정의
        title_style = ParagraphStyle(
            'PDFTitle',
            parent=styles['Normal'],
            fontName=bold_font_name,
            fontSize=24,
            leading=28,
            textColor=colors.HexColor('#0F172A'),  # Deep Navy 색상 적용
            alignment=1,  # 가운데 정렬
            spaceAfter=15
        )

        subtitle_style = ParagraphStyle(
            'PDFSubTitle',
            parent=styles['Normal'],
            fontName=regular_font_name,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#64748B'),  # Slate Gray
            alignment=1,
            spaceAfter=25
        )

        h1_style = ParagraphStyle(
            'PDFH1',
            parent=styles['Normal'],
            fontName=bold_font_name,
            fontSize=13,
            leading=17,
            textColor=colors.HexColor('#1E293B'),
            spaceBefore=15,
            spaceAfter=8,
            keepWithNext=True
        )

        body_style = ParagraphStyle(
            'PDFBody',
            parent=styles['Normal'],
            fontName=regular_font_name,
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor('#334155'),
            spaceAfter=6
        )

        bold_body_style = ParagraphStyle(
            'PDFBodyBold',
            parent=body_style,
            fontName=bold_font_name
        )

        table_header_style = ParagraphStyle(
            'PDFTableHeader',
            parent=styles['Normal'],
            fontName=bold_font_name,
            fontSize=9.5,
            leading=12,
            textColor=colors.white,
            alignment=1
        )

        story = []

        # 1. 보고서 제목 영역
        story.append(Paragraph("TruthLens AI 콘텐츠 분석 보고서", title_style))
        story.append(Paragraph("본 보고서는 TruthLens 인공지능 분석 검증 엔진이 자동으로 진단하여 생성한 기술 보고서입니다.", subtitle_style))
        story.append(Spacer(1, 10))

        # 2. 메타 정보 분석
        verdict = "낮은 위험 - 진본일 가능성이 높음"
        verdict_color = colors.HexColor('#10B981')  # Green
        if result.score >= 70:
            verdict = "매우 위험 - AI 생성 콘텐츠 의심 강함"
            verdict_color = colors.HexColor('#EF4444')  # Red
        elif result.score >= 40:
            verdict = "주의 및 의심 - 면밀한 추가 검토 권장"
            verdict_color = colors.HexColor('#F59E0B')  # Yellow

        type_labels = {'video': '영상', 'image': '이미지', 'news': '뉴스', 'paper': '논문'}
        
        info_data = [
            [Paragraph("보고서 번호", bold_body_style), Paragraph(f"#{request.id}", body_style)],
            [Paragraph("진단 미디어 유형", bold_body_style), Paragraph(f"{type_labels.get(request.type, request.type)}", body_style)],
            [Paragraph("요청 처리 상태", bold_body_style), Paragraph(f"{request.status.upper()}", body_style)],
            [Paragraph("디바이스/콘텐츠 해시", bold_body_style), Paragraph(f"{request.content_hash}", body_style)],
            [Paragraph("검증 완료 시각", bold_body_style), Paragraph(f"{result.created_at}", body_style)],
            [Paragraph("AI 판별 신뢰 점수", bold_body_style), Paragraph(f"<b>{result.score}점</b> (최대 100점)", bold_body_style)],
            [Paragraph("종합 포렌식 판정", bold_body_style), Paragraph(f"<font color='{verdict_color.hexval()}'><b>{verdict}</b></font>", body_style)]
        ]

        info_table = Table(info_data, colWidths=[140, 390])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 15))

        # 3. 종합 소견 및 요약문
        story.append(Paragraph("1. 종합 포렌식 스캔 소견", h1_style))
        details = result.detail_json or {}
        
        summary_text = details.get('summary', '제출된 콘텐츠에 대한 상세 요약 정보가 존재하지 않습니다.')
        story.append(Paragraph(summary_text, body_style))
        story.append(Spacer(1, 10))

        if 'ai_reason' in details and details['ai_reason']:
            story.append(Paragraph("<b>AI 판별 의심 및 추출 상세 근거:</b>", bold_body_style))
            story.append(Paragraph(details['ai_reason'], body_style))
            story.append(Spacer(1, 15))

        # 4. 미디어별 상세 분석 내용 동적 분기
        if request.type == 'paper':
            story.append(Paragraph("2. 논문 영역별 정밀 검사 보고", h1_style))
            
            # 섹션별 점수 목록 구성
            section_scores = details.get('section_scores', {})
            if section_scores:
                sec_data = [[Paragraph("진단 논문 영역 (Section)", table_header_style), Paragraph("AI 생성 위험 점수 (Score)", table_header_style)]]
                for sec, score in section_scores.items():
                    sec_data.append([
                        Paragraph(sec.upper(), body_style),
                        Paragraph(f"<b>{score}%</b> (AI 유사도 비율)", body_style)
                    ])
                
                sec_table = Table(sec_data, colWidths=[260, 270])
                sec_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                    ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))
                story.append(sec_table)
                story.append(Spacer(1, 15))

            # 핵심 주장 내용 리스팅
            key_claims = details.get('key_claims', [])
            if key_claims:
                story.append(Paragraph("<b>검출된 주요 핵심 주장 (Key Claims)</b>", bold_body_style))
                for claim in key_claims:
                    story.append(Paragraph(f"• {claim}", body_style))
                story.append(Spacer(1, 15))

            # 인용 교차 매칭 분석 (Citations)
            citations = details.get('citations', [])
            if citations:
                story.append(Paragraph("<b>학술 참고문헌 인용 매칭 검증 현황 (Citations Integrity)</b>", bold_body_style))
                cit_data = [
                    [
                        Paragraph("인용 번호", table_header_style),
                        Paragraph("매칭 결과", table_header_style),
                        Paragraph("등록 DOI", table_header_style),
                        Paragraph("참고문헌 학술지 제목", table_header_style)
                    ]
                ]
                for cit in citations:
                    ref = cit.get('citation_ref', '-')
                    status = cit.get('status', 'unknown')
                    doi = cit.get('doi') or 'N/A'
                    title = cit.get('title') or 'N/A'

                    # 매칭 상태 색상 입히기
                    status_str = f"<font color='#10B981'><b>MATCHED</b></font>" if status == 'matched' else f"<font color='#EF4444'><b>MISSING</b></font>"
                    
                    cit_data.append([
                        Paragraph(ref, body_style),
                        Paragraph(status_str, body_style),
                        Paragraph(doi, body_style),
                        Paragraph(title, body_style)
                    ])

                cit_table = Table(cit_data, colWidths=[70, 90, 150, 220])
                cit_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                    ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ]))
                story.append(cit_table)
                story.append(Spacer(1, 15))

        elif request.type == 'image':
            story.append(Paragraph("2. 이미지 메타데이터 및 픽셀 시그니처 분석", h1_style))
            if 'exif' in details and details['exif']:
                story.append(Paragraph("<b>추출된 EXIF 촬영 메타데이터:</b>", bold_body_style))
                for key, val in details['exif'].items():
                    story.append(Paragraph(f"• <b>{key}</b>: {val}", body_style))
            else:
                story.append(Paragraph("• 이미지 파일 내부의 특이 EXIF 서명 정보가 발견되지 않았습니다 (소셜 웹을 통해 지워졌을 가능성이 있습니다).", body_style))

        elif request.type == 'video':
            story.append(Paragraph("2. 딥페이크 인코딩 시그니처 정밀 스캔", h1_style))
            is_deepfake = details.get('is_deepfake', False)
            story.append(Paragraph(f"• <b>인공지능 합성(Deepfake) 여부:</b> {'<b>위험 감지 (탐지됨)</b>' if is_deepfake else '미탐지 (안전)'}", body_style))
            
            frame_highlights = details.get('frame_highlights', [])
            if frame_highlights:
                story.append(Paragraph("<b>프레임별 합성 의심 타임라인:</b>", bold_body_style))
                for frame in frame_highlights:
                    story.append(Paragraph(f"  - {frame}", body_style))

        elif request.type == 'news':
            story.append(Paragraph("2. 뉴스 텍스트 사실 왜곡 및 출처 신뢰도", h1_style))
            story.append(Paragraph(f"• <b>허위 사실 왜곡 가능성:</b> {details.get('fake_news_score', 0)}%", body_style))
            story.append(Paragraph(f"• <b>공식 도메인 출처 신뢰도 등급:</b> {details.get('source_trust', '분류 정보 없음')}", body_style))
            story.append(Paragraph(f"• <b>주관적 감성 및 편향성 노출도:</b> {details.get('sentiment_bias', '중립적 구성')}", body_style))
            
            suspicious_sentences = details.get('suspicious_sentences', [])
            if suspicious_sentences:
                story.append(Paragraph("<b>왜곡/과장 의심 문장 하이라이트:</b>", bold_body_style))
                for sentence in suspicious_sentences:
                    story.append(Paragraph(f"  - \"{sentence}\"", body_style))

        # 5. 법적 고지사항
        story.append(Spacer(1, 20))
        disclaimer_text = ("<b>[유의사항]</b> 본 기술 리포트는 인공지능 통계 모델 및 패턴 분석을 활용해 작성되었으며, "
                           "특정 문서 및 미디어의 법적 유효성이나 절대적 가치를 영속적으로 보장하지 않습니다. "
                           "학술 및 실무 검증의 최종 의사결정을 돕는 보조 지표로 사용해 주시기를 바랍니다.")
        story.append(Paragraph(disclaimer_text, subtitle_style))

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
