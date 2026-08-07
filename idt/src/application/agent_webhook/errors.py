"""agent-webhook 전용 예외 (M2 Design D19 — G5 교훈: 문자열 매칭 분기 대체)."""


class WebhookValidationError(Exception):
    """설정 값 검증 실패 (outbound URL 형식·선행 조건 위반) → 라우터 422."""
