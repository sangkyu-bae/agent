"""판단 에이전트 답변 → BuyVerdict / SellVerdict (DD8).

Design Ref: stock-analysis-agents §7 JSON 파싱 — 마지막 ```json 블록 → pydantic 검증
→ 실패 시 보조 LLM 재구조화 1회 → 그래도 실패하면 None (호출자가 매수 skip ·
매도 hold 로 내린다, U9). 숫자는 검증만
하고 고치지 않는다 — 진입 여부는 게이트가 정한다.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from src.application.market_analysis.ports import StructuredExtractor
from src.domain.market_analysis.account import BuyVerdict, SellVerdict

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_PERIODS = ("단기", "중기", "장기")


def _price(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        price = Decimal(str(value).replace(",", "").replace("원", "").strip())
    except InvalidOperation:
        raise ValueError("price must be a number") from None
    if price <= 0:
        raise ValueError("price must be positive")
    return price


class BuyVerdictModel(BaseModel):
    score: int = Field(ge=1, le=10)
    decision: Literal["enter", "skip"]
    target_price: Decimal | None = None
    stop_loss: Decimal | None = None
    investment_period: str | None = None
    sector: str | None = Field(default=None, max_length=100)
    rationale: str = Field(default="", max_length=4000)
    skip_reason: str | None = Field(default=None, max_length=1000)

    @field_validator("decision", mode="before")
    @classmethod
    def _lower(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("target_price", "stop_loss", mode="before")
    @classmethod
    def _prices(cls, v: Any) -> Decimal | None:
        return _price(v)

    @field_validator("investment_period", mode="before")
    @classmethod
    def _period(cls, v: Any) -> str | None:
        return v if v in _PERIODS else None

    def to_verdict(self) -> BuyVerdict:
        return BuyVerdict(
            score=self.score,
            decision=self.decision,
            target_price=self.target_price,
            stop_loss=self.stop_loss,
            investment_period=self.investment_period,
            sector=self.sector or None,
            rationale=self.rationale,
            skip_reason=self.skip_reason or None,
        )


class SellVerdictModel(BaseModel):
    action: Literal["hold", "sell", "adjust"]
    new_target_price: Decimal | None = None
    new_stop_loss: Decimal | None = None
    confidence: int = Field(ge=1, le=10)
    reason: str = Field(default="", max_length=4000)

    @field_validator("action", mode="before")
    @classmethod
    def _lower(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("new_target_price", "new_stop_loss", mode="before")
    @classmethod
    def _prices(cls, v: Any) -> Decimal | None:
        return _price(v)

    def to_verdict(self) -> SellVerdict:
        return SellVerdict(
            action=self.action,
            new_target_price=self.new_target_price,
            new_stop_loss=self.new_stop_loss,
            confidence=self.confidence,
            reason=self.reason,
        )


def last_json_object(text: str) -> dict[str, Any] | None:
    """마지막 코드블록의 JSON 객체. 코드블록이
    없으면 답변 전체를 JSON 으로 읽어 본다."""
    blocks = _FENCE.findall(text or "")
    candidates = [blocks[-1]] if blocks else [(text or "").strip()]
    for raw in candidates:
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
        return value if isinstance(value, dict) else None
    return None


async def parse_model(
    answer: str,
    model: type[BaseModel],
    extractor: StructuredExtractor | None,
    request_id: str,
) -> tuple[Any, str]:
    raw = last_json_object(answer)
    if raw is not None:
        try:
            return model.model_validate(raw), "json"
        except ValidationError:
            pass
    if extractor is not None and answer.strip():
        extracted = await extractor.extract(
            text=answer, schema=model, request_id=request_id
        )
        if extracted is not None:
            return extracted, "extracted"
    return None, "failed"


async def parse_buy(
    answer: str, extractor: StructuredExtractor | None, *, request_id: str
) -> tuple[BuyVerdict | None, str]:
    """(판단, 파싱 경로 json|extracted|failed)."""
    model, mode = await parse_model(answer, BuyVerdictModel, extractor, request_id)
    return (model.to_verdict() if model is not None else None), mode


async def parse_sell(
    answer: str, extractor: StructuredExtractor | None, *, request_id: str
) -> tuple[SellVerdict | None, str]:
    model, mode = await parse_model(answer, SellVerdictModel, extractor, request_id)
    return (model.to_verdict() if model is not None else None), mode
