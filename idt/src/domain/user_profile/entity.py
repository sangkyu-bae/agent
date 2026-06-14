"""UserProfile 도메인 엔티티.

agent-user-context Design §3.4:
- users 테이블(인증)과 분리된 사내 메타데이터 (이름/직급/사번/입사일)
- frozen — 요청 처리 중 변경 금지
- 변경은 UpdateUserProfileUseCase를 통해서만
"""
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class UserProfile:
    user_id: int
    display_name: str          # LLM 노출용 이름 (예: "배상규")
    position: str | None       # 직급 (예: "대리", "과장")
    employee_no: str | None    # 사번 — 절대 LLM 노출 금지
    joined_at: date | None     # 입사일
    created_at: datetime
    updated_at: datetime
