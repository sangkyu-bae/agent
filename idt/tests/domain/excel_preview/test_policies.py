"""셀 직렬화 Policy 테스트 (excel-preview Design §3.3 테이블).

FR-05: 셀 값 문자열 통일 규칙을 테이블 테스트로 고정한다.
"""
import datetime
import math

import pytest

from src.domain.excel_preview.policies import serialize_cell


class TestSerializeCell:
    @pytest.mark.parametrize(
        "value,expected",
        [
            # None → 빈 문자열
            (None, ""),
            # str → 그대로
            ("서울", "서울"),
            ("", ""),
            # bool → true/false (int보다 먼저 분기 — bool은 int 하위 타입)
            (True, "true"),
            (False, "false"),
            # int → str
            (42, "42"),
            (0, "0"),
            (-7, "-7"),
            # float 정수값 → 정수 표기 (1.0이 아니라 1)
            (1.0, "1"),
            (-3.0, "-3"),
            (0.0, "0"),
            # float 그 외 → str
            (3.14, "3.14"),
            # datetime → ISO 8601
            (datetime.datetime(2026, 10, 12, 9, 0, 0), "2026-10-12T09:00:00"),
            # date → ISO 날짜
            (datetime.date(2026, 10, 12), "2026-10-12"),
            # time → ISO 시각
            (datetime.time(9, 30, 0), "09:30:00"),
        ],
    )
    def test_table(self, value, expected):
        assert serialize_cell(value) == expected

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_nan_inf_to_empty(self, value):
        assert serialize_cell(value) == ""

    def test_fallback_str(self):
        class Weird:
            def __str__(self) -> str:
                return "weird"

        assert serialize_cell(Weird()) == "weird"

    def test_large_float_not_integer(self):
        assert serialize_cell(2.5) == "2.5"

    def test_math_nan_guard_does_not_break_int(self):
        # math.isnan은 float 전용 — int 경로가 영향받지 않아야 한다
        assert serialize_cell(10**20) == str(10**20)
        assert not math.isnan(float(1))
