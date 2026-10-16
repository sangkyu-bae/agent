"""실호출 스모크 — Design §8.4 (`pytest -m llm`, 환경변수 없으면 skip).

Plan DoD: 작성만 하고 실행은 이월. 실행 가능해지면 양성 대조군 벤치로 임계값을 조정한다.
  TYPESAFE_API_KEY=… (또는 ANYJEV_BASE_URL=http://127.0.0.1:8100)
  uv run python -m pytest -m llm tests/infrastructure/judgment/
"""

import os

import pytest
from src.domain.judgment.value_objects import (
    ChoiceQuestion,
    JudgmentRequest,
    NoulQuestion,
)

pytestmark = pytest.mark.llm

_REQUEST = JudgmentRequest(
    state={"fact": "하늘은 맑고 파랗다. 구름 한 점 없다."},
    questions={
        "is_blue": NoulQuestion("state.fact 에 따르면 하늘이 파란가?"),
        "weather": ChoiceQuestion(
            "state.fact 가 묘사하는 날씨는?",
            (("sunny", "맑음"), ("rainy", "비"), ("cloudy", "흐림")),
        ),
    },
)


def _assert_answers(resp) -> None:
    assert resp.noul("is_blue").probability > 0.5
    assert resp.choice("weather").choice == "sunny"
    assert resp.latency_ms >= 0


async def test_jev_live():
    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        pytest.skip("TYPESAFE_API_KEY 미설정")
    pytest.importorskip("typesafe_sdk")
    from src.infrastructure.judgment.jev.adapter import JevJudgmentAdapter

    adapter = JevJudgmentAdapter(
        api_key=api_key,
        model=os.environ.get("TYPESAFE_MODEL", "jev-latest"),
        timeout_seconds=10.0,
        base_url=os.environ.get("TYPESAFE_BASE_URL") or None,
    )
    try:
        resp = await adapter.judge(_REQUEST)
    finally:
        await adapter.aclose()
    assert resp.model.startswith("jev-")
    _assert_answers(resp)


async def test_anyjev_live():
    base_url = os.environ.get("ANYJEV_BASE_URL")
    if not base_url:
        pytest.skip("ANYJEV_BASE_URL 미설정")
    from src.infrastructure.judgment.anyjev.adapter import AnyJevJudgmentAdapter

    adapter = AnyJevJudgmentAdapter(
        base_url=base_url,
        timeout_seconds=30.0,
        model_name=os.environ.get("ANYJEV_MODEL"),
    )
    try:
        resp = await adapter.judge(_REQUEST)
    finally:
        await adapter.aclose()
    assert len(resp.extra["decisions"]) == 2
    _assert_answers(resp)
