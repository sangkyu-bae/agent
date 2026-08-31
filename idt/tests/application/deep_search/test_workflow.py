"""deep-search-pipeline Design §8.4 L3 — 서브그래프 전 구간 통합.

L3-1(선택적 재검색)이 이 기능의 존재 이유이자 회귀 방어의 핵심이다.
"""
from __future__ import annotations

import inspect

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.search_pipeline import (
    create_search_pipeline_node,
    is_search_result,
)
from src.application.agent_run.step_tracking import STEP_OUTPUT_SUMMARY_KEY
from src.application.deep_search import workflow as workflow_module
from src.application.deep_search.llm_schemas import (
    CoverageVerdictOut,
    EvidenceExtractOut,
    EvidenceOut,
    QueryOut,
    RequirementOut,
    RequirementVerdictOut,
    SearchPlanOut,
)
from src.application.deep_search.workflow import create_deep_search_node
from src.domain.deep_search.policies import DeepSearchBudgetPolicy
from tests.application.deep_search._fakes import FakeLLM, FakeLogger, FakeTool

WORKER_ID = "web_searcher"


def _supervisor_state(question: str) -> dict:
    return {
        "messages": [HumanMessage(content=question)],
        "token_usage": 100,
    }


def _plan(strategy: str, reqs: list[tuple[str, str]], queries: list[tuple[str, str]]):
    return SearchPlanOut(
        strategy=strategy,
        requirements=[RequirementOut(id=i, description=d) for i, d in reqs],
        queries=[QueryOut(requirement_id=r, query=q) for r, q in queries],
    )


def _extract(*items: tuple[str, str, str]):
    return EvidenceExtractOut(
        evidence=[
            EvidenceOut(requirement_id=r, content=c, source=s, confidence=0.9)
            for r, c, s in items
        ]
    )


def _verdict(statuses: dict[str, bool], next_q=None, can_retry=True):
    return CoverageVerdictOut(
        requirements=[RequirementVerdictOut(id=k, satisfied=v) for k, v in statuses.items()],
        complete=all(statuses.values()),
        can_retry=can_retry,
        next_queries=[QueryOut(requirement_id=r, query=q) for r, q in (next_q or [])],
    )


def _node(llm: FakeLLM, tool: FakeTool, budget=None, logger=None, **blocks):
    return create_deep_search_node(
        worker_id=WORKER_ID,
        tool=tool,
        pipeline_llm=llm,
        policy=budget or DeepSearchBudgetPolicy(),
        logger=logger or FakeLogger(),
        **blocks,
    )


# ── 팩토리 계약 (AD-1: legacy와 동일 시그니처) ──────────────────


def test_factory_signature_matches_legacy():
    """AD-1/FR-12: 컴파일러에서 한 줄로 교체 가능해야 한다."""
    legacy = inspect.signature(create_search_pipeline_node).parameters
    deep = inspect.signature(create_deep_search_node).parameters
    assert list(deep) == list(legacy)


async def test_datetime_block_precedes_user_context():
    """runtime-datetime-context D4: 순서는 날짜 → 사용자 → 본문."""
    llm = FakeLLM(
        plan=[_plan("single", [("r1", "A")], [("r1", "q1")])],
        extract=[_extract(("r1", "값", "http://a"))],
        evaluate=[_verdict({"r1": True})],
    )
    node = _node(
        llm, FakeTool(),
        user_context_block="[현재 사용자 정보] 이름: 배상규\n",
        datetime_block="[현재 날짜] 2026-08-25 (화)\n",
    )
    await node(_supervisor_state("오늘 기준 A"))

    prompt = llm.prompt_text("plan")
    assert prompt.index("2026-08-25") < prompt.index("배상규")


async def test_datetime_block_reaches_every_llm_stage():
    """날짜는 plan/extract/evaluate 세 단계 모두에 닿아야 한다."""
    llm = FakeLLM(
        plan=[_plan("single", [("r1", "A")], [("r1", "q1")])],
        extract=[_extract(("r1", "값", "http://a"))],
        evaluate=[_verdict({"r1": True})],
    )
    node = _node(llm, FakeTool(), datetime_block="[현재 날짜] 2026-08-25 (화)\n")
    await node(_supervisor_state("오늘 기준 A"))

    for slot in ("plan", "extract", "evaluate"):
        assert "2026-08-25" in llm.prompt_text(slot)


# ── L3-1: 선택적 재검색 (핵심 게이트) ───────────────────────────


async def test_l3_1_second_iteration_targets_only_missing_requirement():
    """L3-1: 1회차에 r1만 충족 → 2회차 쿼리는 r2만 대상.

    이 기능의 존재 이유. 실패하면 legacy 대비 이득이 없다.
    """
    llm = FakeLLM(
        plan=[_plan(
            "parallel",
            [("r1", "상상인플러스 BIS"), ("r2", "신한 BIS")],
            [("r1", "상상인플러스저축은행 BIS"), ("r2", "신한저축은행 BIS")],
        )],
        extract=[
            _extract(("r1", "BIS 14.8%", "http://a")),   # 1회차 q1
            _extract(),                                   # 1회차 q2 — 수확 없음
            _extract(("r2", "BIS 15.6%", "http://b")),   # 2회차
        ],
        evaluate=[
            _verdict({"r1": True, "r2": False}, next_q=[("r2", "신한저축은행 경영공시 BIS")]),
            _verdict({"r1": True, "r2": True}),
        ],
    )
    tool = FakeTool()
    result = await _node(llm, tool)(_supervisor_state("A와 B의 BIS 비율"))

    assert tool.queries == [
        "상상인플러스저축은행 BIS",
        "신한저축은행 BIS",
        "신한저축은행 경영공시 BIS",   # 2회차는 미충족 r2 하나만
    ]
    body = result["messages"][0].content
    assert "BIS 14.8%" in body
    assert "BIS 15.6%" in body
    assert "stop=complete" in result[STEP_OUTPUT_SUMMARY_KEY]


async def test_l3_1b_satisfied_requirement_is_never_requeried():
    """1회차에 충족된 requirement의 쿼리가 2회차 도구 호출에 없어야 한다."""
    llm = FakeLLM(
        plan=[_plan("parallel", [("r1", "A"), ("r2", "B")], [("r1", "qA"), ("r2", "qB")])],
        extract=[_extract(("r1", "A값", "http://a")), _extract(), _extract()],
        evaluate=[
            _verdict({"r1": True, "r2": False}, next_q=[("r2", "qB2")]),
            _verdict({"r1": True, "r2": False}, next_q=[("r2", "qB3")]),
        ],
    )
    tool = FakeTool()
    await _node(llm, tool)(_supervisor_state("A와 B"))

    assert "qA" in tool.queries
    assert tool.queries.count("qA") == 1


# ── L3-2 / L3-3: 비용 상한 (NFR-02) ─────────────────────────────


async def test_l3_2_single_strategy_costs_no_more_than_legacy():
    """L3-2: single 경로 LLM 호출 3회 ≤ legacy 상한 4회."""
    llm = FakeLLM(
        plan=[_plan("single", [("r1", "쿠버네티스 Service")], [("r1", "쿠버네티스 Service 정의")])],
        extract=[_extract(("r1", "Service는 …", "http://k8s"))],
        evaluate=[_verdict({"r1": True})],
    )
    tool = FakeTool()
    await _node(llm, tool)(_supervisor_state("쿠버네티스 Service가 뭐야?"))

    assert llm.total_calls == 3
    assert len(tool.queries) == 1


async def test_l3_3_iterative_worst_case_within_budget():
    """L3-3: iterative 최악 경로 LLM ≤ 12회, 검색 ≤ 10회 (NFR-02)."""
    reqs = [(f"r{i}", f"요구{i}") for i in range(3)]
    queries = [(f"r{i}", f"q{i}") for i in range(3)]
    llm = FakeLLM(
        plan=[_plan("iterative", reqs, queries)],
        extract=[_extract()],
        evaluate=[_verdict(
            {"r0": False, "r1": False, "r2": False},
            next_q=[("r0", "n0"), ("r1", "n1"), ("r2", "n2")],
        )],
    )
    tool = FakeTool()
    result = await _node(llm, tool)(_supervisor_state("복잡한 질문"))

    assert llm.total_calls <= 12
    assert len(tool.queries) <= 10
    assert "stop=max_iteration" in result[STEP_OUTPUT_SUMMARY_KEY]


async def test_no_gain_stops_before_budget_exhausted():
    """NO_GAIN: 2회차에 새 근거가 0건이면 예산을 남기고 종료한다."""
    budget = DeepSearchBudgetPolicy(max_iteration=5)
    llm = FakeLLM(
        plan=[_plan("iterative", [("r1", "A")], [("r1", "q1")])],
        extract=[_extract(("r1", "같은 근거", "http://a"))],   # 매번 동일 → 새 근거 0
        evaluate=[_verdict({"r1": False}, next_q=[("r1", "q2")]),
                  _verdict({"r1": False}, next_q=[("r1", "q3")])],
    )
    tool = FakeTool()
    result = await _node(llm, tool, budget=budget)(_supervisor_state("질문"))

    assert "stop=no_gain" in result[STEP_OUTPUT_SUMMARY_KEY]
    assert len(tool.queries) == 2


# ── L3-4: 반환 계약 (FR-12) ─────────────────────────────────────


async def test_l3_4_return_contract_matches_legacy():
    """L3-4: 기존 search 노드와 동일한 반환 계약."""
    llm = FakeLLM(
        plan=[_plan("single", [("r1", "A")], [("r1", "q1")])],
        extract=[_extract(("r1", "값", "http://a"))],
        evaluate=[_verdict({"r1": True})],
    )
    result = await _node(llm, FakeTool())(_supervisor_state("질문"))

    assert set(result) >= {
        "messages", "last_worker_id", "token_usage", STEP_OUTPUT_SUMMARY_KEY,
    }
    message = result["messages"][0]
    assert isinstance(message, AIMessage)
    assert message.name == WORKER_ID
    assert is_search_result(message) is True
    assert result["last_worker_id"] == WORKER_ID
    assert result["token_usage"] > 100
    assert len(result[STEP_OUTPUT_SUMMARY_KEY]) <= 512


# ── L3-5: E10 서브그래프 예외 흡수 ──────────────────────────────


async def test_l3_5_subgraph_exception_falls_back_to_single_search(monkeypatch):
    """L3-5 (E10): 서브그래프 예외 → legacy 단일 쿼리 1회 검색, 예외 미전파."""
    async def _boom(graph, state):
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(workflow_module, "_run_graph", _boom)

    tool = FakeTool(default="폴백 검색 결과")
    logger = FakeLogger()
    result = await _node(FakeLLM(), tool, logger=logger)(_supervisor_state("원 질문"))

    assert tool.queries == ["원 질문"]
    assert "폴백 검색 결과" in result["messages"][0].content
    assert "stop=fallback" in result[STEP_OUTPUT_SUMMARY_KEY]
    assert logger.has("error", "deep_search")


async def test_fallback_survives_tool_failure(monkeypatch):
    """E10 폴백 검색까지 실패해도 그래프는 중단되지 않는다."""
    async def _boom(graph, state):
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(workflow_module, "_run_graph", _boom)

    result = await _node(FakeLLM(), FakeTool(fail_all=True))(_supervisor_state("질문"))
    assert result["last_worker_id"] == WORKER_ID
    assert "검색 실패" in result["messages"][0].content


# ── 폴백·열화 경로 통합 ─────────────────────────────────────────


async def test_plan_failure_still_searches_once(monkeypatch):
    """E1: plan 실패해도 원 질문으로 한 번은 검색한다."""
    llm = FakeLLM(
        plan=[RuntimeError("plan down")],
        extract=[_extract(("r1", "값", "http://a"))],
        evaluate=[_verdict({"r1": True})],
    )
    tool = FakeTool()
    result = await _node(llm, tool)(_supervisor_state("원 질문 그대로"))

    assert tool.queries == ["원 질문 그대로"]
    assert "fallback=True" in result[STEP_OUTPUT_SUMMARY_KEY]


async def test_total_search_failure_skips_evaluate_llm():
    """E4: 검색 전부 실패 → evaluate LLM 호출 0회."""
    llm = FakeLLM(
        plan=[_plan("single", [("r1", "A")], [("r1", "q1")])],
        extract=[_extract()],
        evaluate=[],
    )
    tool = FakeTool(fail_all=True)
    result = await _node(llm, tool)(_supervisor_state("질문"))

    assert llm.count("evaluate") == 0
    assert "stop=exhausted" in result[STEP_OUTPUT_SUMMARY_KEY]


async def test_question_falls_back_to_last_message():
    """user 메시지가 없으면 마지막 메시지 본문을 질문으로 쓴다."""
    llm = FakeLLM(
        plan=[_plan("single", [("r1", "A")], [("r1", "q1")])],
        extract=[_extract(("r1", "값", "http://a"))],
        evaluate=[_verdict({"r1": True})],
    )
    state = {"messages": [AIMessage(content="에이전트 발화")], "token_usage": 0}
    result = await _node(llm, FakeTool())(state)
    assert result["last_worker_id"] == WORKER_ID


async def test_worker_outputs_excluded_from_context():
    """대화 맥락에서 이전 워커 산출물은 제외한다 (D5 관례 계승)."""
    llm = FakeLLM(
        plan=[_plan("single", [("r1", "A")], [("r1", "q1")])],
        extract=[_extract(("r1", "값", "http://a"))],
        evaluate=[_verdict({"r1": True})],
    )
    state = {
        "messages": [
            HumanMessage(content="사용자 질문"),
            AIMessage(content="[other 검색결과]\n이전 워커 산출물", name="other"),
        ],
        "token_usage": 0,
    }
    await _node(llm, FakeTool())(state)
    assert "이전 워커 산출물" not in llm.prompt_text("plan")


@pytest.mark.parametrize("strategy", ["single", "parallel", "iterative"])
async def test_all_strategies_produce_valid_contract(strategy):
    llm = FakeLLM(
        plan=[_plan(strategy, [("r1", "A")], [("r1", "q1")])],
        extract=[_extract(("r1", "값", "http://a"))],
        evaluate=[_verdict({"r1": True})],
    )
    result = await _node(llm, FakeTool())(_supervisor_state("질문"))
    assert is_search_result(result["messages"][0]) is True
