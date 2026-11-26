"""판단 답변 파싱 — 마지막 JSON 블록 → 검증 → 보조 LLM 1회 → 실패 (DD8, U9)."""

from __future__ import annotations

from decimal import Decimal

from src.application.market_analysis.verdict_parser import (
    BuyVerdictModel,
    last_json_object,
    parse_buy,
    parse_sell,
)

BUY = (
    '판단 메모\n```json\n{"score": 3, "decision": "skip"}\n```\n'
    "최종:\n```json\n"
    '{"score": 8, "decision": "Enter", "target_price": "12,000", "stop_loss": 9500,'
    ' "investment_period": "단기", "sector": "반도체", "rationale": "근거",'
    ' "skip_reason": null}\n```'
)


class FakeExtractor:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    async def extract(self, *, text, schema, request_id):
        self.calls.append(schema)
        return self.result


def test_last_json_object_takes_the_last_block():
    assert last_json_object(BUY)["score"] == 8
    assert last_json_object('{"a": 1}') == {"a": 1}
    assert last_json_object("그냥 글") is None
    assert last_json_object("```json\n[1, 2]\n```") is None


async def test_parse_buy_from_json_normalizes_values():
    ex = FakeExtractor()
    verdict, mode = await parse_buy(BUY, ex, request_id="r")
    assert mode == "json" and ex.calls == []
    assert verdict.decision == "enter" and verdict.score == 8
    assert verdict.target_price == Decimal("12000") and verdict.stop_loss == Decimal(
        "9500"
    )
    assert verdict.investment_period == "단기"


async def test_invalid_json_falls_back_to_extractor_once():
    model = BuyVerdictModel(
        score=5, decision="skip", rationale="r", skip_reason="데이터 없음"
    )
    ex = FakeExtractor(model)
    verdict, mode = await parse_buy('```json\n{"score": 99}\n```', ex, request_id="r")
    assert mode == "extracted" and len(ex.calls) == 1
    assert verdict.decision == "skip" and verdict.skip_reason == "데이터 없음"


async def test_u9_parse_and_extractor_both_fail():
    ex = FakeExtractor(None)
    verdict, mode = await parse_buy("점수는 8점입니다", ex, request_id="r")
    assert (verdict, mode) == (None, "failed") and len(ex.calls) == 1
    # 빈 답변은 보조 LLM 을 부르지 않는다
    ex2 = FakeExtractor(None)
    assert await parse_buy("", ex2, request_id="r") == (None, "failed")
    assert ex2.calls == []


async def test_bad_numbers_are_rejected_not_fixed():
    text = (
        '```json\n{"score": 8, "decision": "enter", '
        '"target_price": -1, "stop_loss": 9}\n```'
    )
    verdict, mode = await parse_buy(text, None, request_id="r")
    assert (verdict, mode) == (None, "failed")


async def test_non_finite_prices_are_rejected_not_raised():
    """G6 — "NaN" 은 Decimal 비교에서 InvalidOperation(ArithmeticError)을 내
    pydantic 이 바꾸지 못하고 새어 나갔고, "Infinity" 는 그대로 통과했다.
    JSON 의 맨 NaN·Infinity 리터럴(json.loads 가 받아들임)도 같다."""
    for target in ('"NaN"', '"Infinity"', '"-Infinity"', "NaN", "Infinity"):
        text = (
            '```json\n{"score": 8, "decision": "enter", '
            f'"target_price": {target}, "stop_loss": 9500}}\n```'
        )
        ex = FakeExtractor(None)
        verdict, mode = await parse_buy(text, ex, request_id="r")
        assert (verdict, mode) == (None, "failed"), target


async def test_non_finite_sell_prices_are_rejected():
    text = (
        '```json\n{"action": "adjust", "new_stop_loss": "NaN", '
        '"confidence": 7, "reason": "r"}\n```'
    )
    verdict, mode = await parse_sell(text, None, request_id="r")
    assert (verdict, mode) == (None, "failed")


async def test_unknown_period_becomes_none():
    text = (
        '```json\n{"score": 6, "decision": "skip", "investment_period": "초단기"}\n```'
    )
    verdict, _ = await parse_buy(text, None, request_id="r")
    assert verdict.investment_period is None


async def test_parse_sell():
    text = (
        '```json\n{"action": "ADJUST", "new_target_price": "13000", '
        '"new_stop_loss": "9800", "confidence": 6, "reason": "추세 유지"}\n```'
    )
    verdict, mode = await parse_sell(text, None, request_id="r")
    assert mode == "json" and verdict.action == "adjust"
    assert verdict.new_stop_loss == Decimal("9800")
    assert await parse_sell("모르겠다", None, request_id="r") == (None, "failed")
