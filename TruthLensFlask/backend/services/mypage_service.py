from types import SimpleNamespace

from backend.models.database import db
from sqlalchemy import func
from flask import session

from backend.models.mypage import User
from backend.models.detection_request import DetectionRequest
from backend.models.detection_result import DetectionResult

class MypageService:
    def __init__(self):
        """
        마이페이지 서비스가 생성될 때 현재 로그인한 '본인'의 ID를 주입받아 
        인스턴스 변수에 안전하게 저장합니다.
        """
        self.user_id = session.get('user_id')
        
    def get_user_stats(self):
        """
        ERD 관계도에 따라 self.user_id를 가진 사용자의 
        1) 총 요청 건수(detection_requests)와 
        2) 이에 매핑된 결과(detection_results)의 score 평균을 계산하여 반환합니다.
        """
        # 1. 로그인 상태 확인
        if not self.user_id:
            return None

        # 2. DB에서 본인의 기본 회원 정보 조회 (users 테이블)
        user = User.query.get(self.user_id)
        if not user:
            return None

        # 3. 분석 통계: detection_requests 테이블에서 user_id가 본인인 데이터의 총 개수 세기
        total_scans = db.session.query(func.count(DetectionRequest.id))\
            .filter(DetectionRequest.user_id == self.user_id).scalar() or 0

        # 4. 탐지 정확도: ERD의 관계(detection_requests.id = detection_results.request_id)를 기반으로
        # 두 테이블을 JOIN 한 뒤, 본인이 요청한 결과의 score 평균값 구하기
        avg_score = db.session.query(func.avg(DetectionResult.score))\
            .join(DetectionRequest, DetectionResult.request_id == DetectionRequest.id)\
            .filter(DetectionRequest.user_id == self.user_id).scalar() or 0.0

        # 5. UI 가독성을 위해 score 값 정제 및 반올림 (예: 0.854 -> 85.4% 또는 85.4 -> 85.4)
        # AI 모델의 출력 스코어가 0~1 범위면 100을 곱해주고, 0~100 범위면 그대로 사용합니다.
        accuracy_rate = round(float(avg_score) * 100, 1) if avg_score <= 1.0 else round(float(avg_score), 1)

        # 6. 화면 표시용 값은 ORM user 객체를 변형하지 않고 별도 객체로 묶어서 반환
        # (user에 직접 대입하면 이후 flush/commit 시 계산값이 DB에 그대로 저장되어 데이터가 오염됨)
        return SimpleNamespace(
            name=user.name,
            email=user.email,
            role_badge=user.role.upper(),
            trust_score=int(user.trust_score) if user.trust_score else 0,
            scan_count=total_scans,
            accuracy=accuracy_rate,
            plan_name="Pro Plan" if user.role.lower() == 'pro' else "Enterprise Plan",
            next_payment_date=user.next_payment_date.strftime('%y.%m.%d') if user.next_payment_date else "N/A",
        )