"""PlaceholderStreamPolicy 단위 테스트 (mock 금지) — Design §4.5."""

import pytest
from src.domain.pii_masking.policies import PlaceholderStreamPolicy

hold_start = PlaceholderStreamPolicy.hold_start


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("전송 [", 3),
        ("전송 [PH", 3),
        ("전송 [PHONE", 3),
        ("전송 [PHONE_", 3),
        ("전송 [PHONE_1", 3),
        ("전송 [phone_1", 3),
        ("[ACC", 0),
        ("[RRN_", 0),
    ],
)
def test_hold_start_placeholder_prefix_returns_bracket_index(text, expected):
    assert hold_start(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "전송했습니다",
        "완료 [PHONE_1]",
        "목록 [1]",
        "참고 [출처",
        "[PHONEX",
        "[PHONE_1a",
    ],
)
def test_hold_start_not_a_placeholder_prefix_returns_none(text):
    assert hold_start(text) is None


def test_hold_start_tail_longer_than_limit_returns_none():
    assert hold_start("[PHONE_" + "1" * 30) is None


def test_hold_start_uses_last_bracket():
    text = "[PHONE_1] 그리고 [EM"
    assert hold_start(text) == text.rindex("[")
