"""셀 직렬화 Policy (Design §3.3, FR-05).

순수 함수 — openpyxl·pydantic 등 외부 의존 금지 (domain 규칙).
수식 셀은 리더가 data_only=True로 읽어 계산 결과값이 들어오므로 여기 규칙에 수렴한다.
"""
import datetime
import math


def serialize_cell(value: object) -> str:
    """셀 값을 프리뷰용 문자열로 통일한다 (Design §3.3 테이블).

    bool은 int의 하위 타입이므로 int보다 먼저 검사한다.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return _serialize_float(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    return str(value)


def _serialize_float(value: float) -> str:
    if math.isnan(value) or math.isinf(value):
        return ""
    if value.is_integer():
        return str(int(value))  # 1.0 → "1"
    return str(value)
