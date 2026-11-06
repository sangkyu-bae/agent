"""PiiToolArgumentPolicy 단위 테스트 (mock 금지) — Design §4.6, D-08."""

from src.domain.pii_masking.policies import (
    PII_ORPHAN_TOOL_ARG_NOTICE,
    PiiToolArgumentPolicy,
)
from src.domain.pii_masking.schemas import PLACEHOLDER_PATTERN

find_orphan = PiiToolArgumentPolicy.find_orphan


def test_find_orphan_top_level_placeholder():
    assert find_orphan({"to": "[EMAIL_9]"}) == "[EMAIL_9]"


def test_find_orphan_nested_and_json_string():
    args = {"payload": [{"memo": "회신 {'to': '[phone_2]'}"}]}
    assert find_orphan(args) == "[phone_2]"


def test_find_orphan_plain_values_returns_none():
    assert find_orphan({"to": "a@b.com", "n": 3, "flag": True}) is None


def test_find_orphan_redacted_marker_is_not_placeholder():
    assert find_orphan({"to": "[REDACTED_EMAIL]"}) is None


def test_notice_contains_no_placeholder_shaped_text():
    # 안내문에 예시 placeholder가 있으면 다음 호출에서 입력 문자열로 예약된다.
    assert PLACEHOLDER_PATTERN.search(PII_ORPHAN_TOOL_ARG_NOTICE) is None
