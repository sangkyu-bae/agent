"""deep-search-pipeline Design §8.3 L2 — 노드 단위 (정상 + 실패 폴백).

모든 케이스는 Fake LLM / Fake Tool 주입으로 구동한다.
"""
from __future__ import annotations

import pytest

from src.application.deep_search.llm_schemas import (
    CoverageVerdictOut,
    EvidenceExtractOut,
    EvidenceOut,
    KeyValueOut,
    QueryOut,
    RequirementOut,
    RequirementVerdictOut,
    SearchPlanOut,
)
from src.application.deep_search.nodes import (
    NodeDeps,
    make_evaluate_node,
    make_execute_node,
    make_extract_node,
    make_finalize_node,
    make_plan_node,
    route_after_evaluate,
)
from src.application.deep_search.rendering import MISSING_MARK
from src.domain.deep_search.policies import DeepSearchBudgetPolicy
from src.domain.deep_search.schemas import Evidence, Requirement, SearchQuery, StopReason
from tests.application.deep_search._fakes import FakeLLM, FakeLogger, FakeTool


def _deps(llm=None, tool=None, budget=None, user_context="") -> NodeDeps:
    return NodeDeps(
        tool=tool or FakeTool(),
        llm=llm or FakeLLM(),
        budget=budget or DeepSearchBudgetPolicy(),
        logger=FakeLogger(),
        user_context=user_context,
    )


def _state(**overrides) -> dict:
    base = {
        "question": "상상인플러스저축은행과 신한저축은행 BIS 비율 알려줘",
        "context": "",
        "user_context": "",
        "strategy": "",
        "requirements": [],
        "pending_queries": [],
        "query_history": [],
        "raw_results": [],
        "evidence": [],
        "iteration": 0,
        "new_evidence_count": 0,
        "can_retry": True,
        "stop_reason": "",
        "search_ok": False,
        "extract_degraded": False,
        "plan_fallback": False,
        "llm_chars": 0,
    }
    base.update(overrides)
    return base


def _plan_out(strategy="parallel") -> SearchPlanOut:
    return SearchPlanOut(
        strategy=strategy,
        requirements=[
            RequirementOut(id="r1", description="상상인플러스저축은행 BIS 비율",
                           constraints=[KeyValueOut(key="period", value="latest")]),
            RequirementOut(id="r2", description="신한저축은행 BIS 비율",
                           constraints=[KeyValueOut(key="period", value="latest")]),
        ],
        queries=[
            QueryOut(requirement_id="r1", query="상상인플러스저축은행 BIS 비율 최신"),
            QueryOut(requirement_id="r2", query="신한저축은행 BIS 비율 최신"),
        ],
    )


# ── L2-1 ~ L2-4: plan_node ──────────────────────────────────────


async def test_l2_1_decomposes_comparison_question():
    """L2-1: 'A와 B의 X' → requirement 2개, 독립 쿼리 2개."""
    deps = _deps(llm=FakeLLM(plan=[_plan_out()]))
    out = await make_plan_node(deps)(_state())

    assert out["strategy"] == "parallel"
    assert [r.id for r in out["requirements"]] == ["r1", "r2"]
    assert len(out["pending_queries"]) == 2
    assert out["pending_queries"][0].requirement_id == "r1"
    assert out["plan_fallback"] is False


async def test_l2_2_simple_question_yields_single_requirement():
    """L2-2: 단순 질문 → strategy=single, requirement 1개."""
    plan = SearchPlanOut(
        strategy="single",
        requirements=[RequirementOut(id="r1", description="쿠버네티스 Service의 정의")],
        queries=[QueryOut(requirement_id="r1", query="쿠버네티스 Service 정의")],
    )
    deps = _deps(llm=FakeLLM(plan=[plan]))
    out = await make_plan_node(deps)(_state(question="쿠버네티스 Service가 뭐야?"))

    assert out["strategy"] == "single"
    assert len(out["requirements"]) == 1
    assert len(out["pending_queries"]) == 1


async def test_l2_3_plan_failure_falls_back_to_single_query():
    """L2-3 (E1): plan LLM 예외 → 원 질문 1개 쿼리로 폴백, 예외 미전파."""
    deps = _deps(llm=FakeLLM(plan=[RuntimeError("boom")]))
    question = "상상인플러스저축은행 BIS"
    out = await make_plan_node(deps)(_state(question=question))

    assert out["strategy"] == "single"
    assert out["plan_fallback"] is True
    assert len(out["requirements"]) == 1
    assert out["requirements"][0].description == question
    assert out["pending_queries"][0].query == question
    assert deps.logger.has("warning", "plan")


async def test_plan_empty_output_falls_back():
    """빈 계획도 폴백 대상."""
    empty = SearchPlanOut(strategy="single", requirements=[], queries=[])
    deps = _deps(llm=FakeLLM(plan=[empty]))
    out = await make_plan_node(deps)(_state())
    assert out["plan_fallback"] is True
    assert len(out["pending_queries"]) == 1


async def test_plan_synthesizes_query_when_missing():
    """requirement는 있는데 쿼리가 없으면 description으로 쿼리를 만든다."""
    plan = SearchPlanOut(
        strategy="parallel",
        requirements=[
            RequirementOut(id="r1", description="A의 BIS"),
            RequirementOut(id="r2", description="B의 BIS"),
        ],
        queries=[],
    )
    deps = _deps(llm=FakeLLM(plan=[plan]))
    out = await make_plan_node(deps)(_state())
    assert [q.query for q in out["pending_queries"]] == ["A의 BIS", "B의 BIS"]
    assert out["plan_fallback"] is False


async def test_plan_drops_query_for_unknown_requirement():
    """존재하지 않는 requirement_id를 가리키는 쿼리는 버린다."""
    plan = SearchPlanOut(
        strategy="parallel",
        requirements=[RequirementOut(id="r1", description="A의 BIS")],
        queries=[
            QueryOut(requirement_id="r1", query="A BIS"),
            QueryOut(requirement_id="r9", query="유령 쿼리"),
        ],
    )
    deps = _deps(llm=FakeLLM(plan=[plan]))
    out = await make_plan_node(deps)(_state())
    assert [q.query for q in out["pending_queries"]] == ["A BIS"]


async def test_single_strategy_is_capped_to_one_requirement():
    """G-01/FR-02: strategy=single이면 코드가 요구를 1개로 강제한다.

    프롬프트 준수에만 의존하면 'single인데 3쿼리 팬아웃'이 가능해 R1(비용 폭증)의
    조기 탈출 장치가 무력화된다.
    """
    plan = SearchPlanOut(
        strategy="single",
        requirements=[
            RequirementOut(id="r1", description="A의 정의"),
            RequirementOut(id="r2", description="B의 정의"),
            RequirementOut(id="r3", description="C의 정의"),
        ],
        queries=[
            QueryOut(requirement_id="r1", query="qA"),
            QueryOut(requirement_id="r2", query="qB"),
            QueryOut(requirement_id="r3", query="qC"),
        ],
    )
    deps = _deps(llm=FakeLLM(plan=[plan]))
    out = await make_plan_node(deps)(_state())

    assert len(out["requirements"]) == 1
    assert len(out["pending_queries"]) == 1
    assert out["pending_queries"][0].requirement_id == out["requirements"][0].id
    assert deps.logger.has("warning", "single")


async def test_single_strategy_synthesizes_query_when_head_has_none():
    """single 절삭 후 남은 요구에 쿼리가 없으면 description으로 만든다."""
    plan = SearchPlanOut(
        strategy="single",
        requirements=[
            RequirementOut(id="r1", description="A의 정의"),
            RequirementOut(id="r2", description="B의 정의"),
        ],
        queries=[QueryOut(requirement_id="r2", query="qB")],
    )
    deps = _deps(llm=FakeLLM(plan=[plan]))
    out = await make_plan_node(deps)(_state())

    assert [r.id for r in out["requirements"]] == ["r1"]
    assert [q.query for q in out["pending_queries"]] == ["A의 정의"]


async def test_single_strategy_with_one_requirement_is_untouched():
    """정상적인 single은 경고 없이 통과한다."""
    plan = SearchPlanOut(
        strategy="single",
        requirements=[RequirementOut(id="r1", description="A의 정의")],
        queries=[QueryOut(requirement_id="r1", query="qA")],
    )
    deps = _deps(llm=FakeLLM(plan=[plan]))
    out = await make_plan_node(deps)(_state())

    assert len(out["pending_queries"]) == 1
    assert not deps.logger.has("warning", "single")


@pytest.mark.parametrize("strategy", ["parallel", "iterative"])
async def test_non_single_strategy_keeps_all_requirements(strategy):
    """분해가 목적인 전략은 절삭하지 않는다."""
    deps = _deps(llm=FakeLLM(plan=[_plan_out(strategy)]))
    out = await make_plan_node(deps)(_state())
    assert len(out["requirements"]) == 2
    assert len(out["pending_queries"]) == 2


async def test_l2_4_truncates_queries_over_budget_with_warning():
    """L2-4 (E2): 예산 초과 쿼리는 절삭하고 경고를 남긴다."""
    plan = SearchPlanOut(
        strategy="iterative",
        requirements=[RequirementOut(id=f"r{i}", description=f"요구{i}") for i in range(8)],
        queries=[QueryOut(requirement_id=f"r{i}", query=f"q{i}") for i in range(8)],
    )
    deps = _deps(llm=FakeLLM(plan=[plan]))
    out = await make_plan_node(deps)(_state())

    budget = deps.budget
    assert len(out["pending_queries"]) == budget.max_query_per_iteration
    assert deps.logger.has("warning", "truncated")


async def test_plan_prompt_includes_user_context():
    """user_context 블록은 system prompt 앞에 prepend 된다."""
    deps = _deps(llm=FakeLLM(plan=[_plan_out()]), user_context="[현재 사용자 정보] 이름: 배상규\n")
    await make_plan_node(deps)(_state())
    assert "배상규" in deps.llm.prompt_text("plan")


# ── L2-5 ~ L2-6: execute_node ───────────────────────────────────


async def test_l2_5_isolates_single_query_failure():
    """L2-5 (E3): 쿼리 하나가 실패해도 나머지 결과는 보존된다."""
    tool = FakeTool(responses={"q1": "결과1", "q3": "결과3"}, fail={"q2"})
    deps = _deps(tool=tool)
    state = _state(pending_queries=[
        SearchQuery("r1", "q1"), SearchQuery("r2", "q2"), SearchQuery("r3", "q3"),
    ])
    out = await make_execute_node(deps)(state)

    assert out["search_ok"] is True
    ok_flags = [ok for _, ok, _ in out["raw_results"]]
    assert ok_flags == [True, False, True]
    assert deps.logger.has("error", "search")


async def test_l2_6_all_queries_failed_sets_search_not_ok():
    """L2-6 (E4): 모든 쿼리 실패 → search_ok=False."""
    deps = _deps(tool=FakeTool(fail_all=True))
    state = _state(pending_queries=[SearchQuery("r1", "q1")])
    out = await make_execute_node(deps)(state)
    assert out["search_ok"] is False


async def test_execute_appends_query_history():
    """실행한 쿼리는 이력에 누적된다 (R3 재계획 입력)."""
    deps = _deps(tool=FakeTool())
    state = _state(query_history=["예전 쿼리"], pending_queries=[SearchQuery("r1", "새 쿼리")])
    out = await make_execute_node(deps)(state)
    assert out["query_history"] == ["예전 쿼리", "새 쿼리"]
    assert out["pending_queries"] == []


async def test_execute_passes_max_results_budget():
    """D8: 도구가 받아주면 max_results로 결과 수를 제한한다."""
    tool = FakeTool()
    deps = _deps(tool=tool)
    await make_execute_node(deps)(_state(pending_queries=[SearchQuery("r1", "q1")]))
    assert tool.payloads[0]["max_results"] == deps.budget.max_result_per_query


async def test_execute_retries_without_max_results_on_type_error():
    """D8: max_results를 받지 않는 도구는 query만으로 재시도한다."""
    tool = FakeTool(accepts_max_results=False)
    deps = _deps(tool=tool)
    out = await make_execute_node(deps)(_state(pending_queries=[SearchQuery("r1", "q1")]))
    assert out["search_ok"] is True
    assert tool.payloads[-1] == {"query": "q1"}


async def test_execute_runs_queries_concurrently():
    """병렬 실행 — 모든 쿼리가 한 번씩 호출된다."""
    tool = FakeTool()
    deps = _deps(tool=tool)
    queries = [SearchQuery(f"r{i}", f"q{i}") for i in range(4)]
    await make_execute_node(deps)(_state(pending_queries=queries))
    assert sorted(tool.queries) == ["q0", "q1", "q2", "q3"]


# ── L2-7 ~ L2-9: extract_node ───────────────────────────────────


def _extract_out(*items: tuple[str, str, str, float]) -> EvidenceExtractOut:
    return EvidenceExtractOut(
        evidence=[
            EvidenceOut(requirement_id=r, content=c, source=s, confidence=conf)
            for r, c, s, conf in items
        ]
    )


async def test_l2_7_extracts_tagged_evidence():
    """L2-7: 검색 결과 → requirement_id 태깅된 Evidence."""
    deps = _deps(llm=FakeLLM(extract=[_extract_out(("r1", "BIS 14.8%", "http://a", 0.9))]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        raw_results=[("q1", True, "본문")],
    )
    out = await make_extract_node(deps)(state)

    assert len(out["evidence"]) == 1
    assert out["evidence"][0].requirement_id == "r1"
    assert out["new_evidence_count"] == 1
    assert out["extract_degraded"] is False


async def test_l2_8_discards_evidence_without_source():
    """L2-8 (E7): 출처 없는 근거는 폐기한다."""
    deps = _deps(llm=FakeLLM(extract=[_extract_out(
        ("r1", "BIS 14.8%", "", 0.9),
        ("r1", "BIS 15.1%", "http://b", 0.9),
    )]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        raw_results=[("q1", True, "본문")],
    )
    out = await make_extract_node(deps)(state)

    assert [e.content for e in out["evidence"]] == ["BIS 15.1%"]
    assert deps.logger.has("warning", "evidence")


async def test_extract_discards_low_confidence():
    """E7: 신뢰도 미달 근거도 폐기."""
    deps = _deps(llm=FakeLLM(extract=[_extract_out(("r1", "추정치", "http://a", 0.1))]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        raw_results=[("q1", True, "본문")],
    )
    out = await make_extract_node(deps)(state)
    assert out["evidence"] == []


async def test_extract_discards_unknown_requirement_id():
    deps = _deps(llm=FakeLLM(extract=[_extract_out(("r9", "엉뚱", "http://a", 0.9))]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        raw_results=[("q1", True, "본문")],
    )
    out = await make_extract_node(deps)(state)
    assert out["evidence"] == []


async def test_l2_9_all_extract_failures_degrade_to_raw():
    """L2-9 (E6): 전 쿼리 extract 실패 → raw 본문 채택 (legacy 퇴행 방지)."""
    deps = _deps(llm=FakeLLM(extract=[RuntimeError("extract down")]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        raw_results=[("q1", True, "원문 검색 결과")],
    )
    out = await make_extract_node(deps)(state)

    assert out["extract_degraded"] is True
    assert out["evidence"] == []
    assert deps.logger.has("warning", "extract")


async def test_extract_skips_failed_search_results():
    """검색이 실패한 항목은 추출 대상이 아니다 — LLM 호출도 없다."""
    deps = _deps(llm=FakeLLM(extract=[_extract_out(("r1", "A", "http://a", 0.9))]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        raw_results=[("q1", False, "검색 실패: x"), ("q2", True, "본문")],
    )
    await make_extract_node(deps)(state)
    assert deps.llm.count("extract") == 1


async def test_extract_counts_only_new_evidence():
    """NO_GAIN 판정 입력 — 이미 보유한 근거는 새 근거로 세지 않는다."""
    known = Evidence(requirement_id="r1", content="BIS 14.8%", source="http://a", confidence=0.9)
    deps = _deps(llm=FakeLLM(extract=[_extract_out(("r1", "BIS 14.8%", "http://a", 0.9))]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        raw_results=[("q1", True, "본문")],
        evidence=[known],
    )
    out = await make_extract_node(deps)(state)
    assert out["new_evidence_count"] == 0


async def test_extract_truncates_long_result():
    """프롬프트 비대 방지 — 결과는 예산 길이로 절단된다."""
    budget = DeepSearchBudgetPolicy(extract_result_head=50)
    deps = _deps(
        llm=FakeLLM(extract=[_extract_out(("r1", "A", "http://a", 0.9))]), budget=budget,
    )
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        raw_results=[("q1", True, "Z" * 500)],
    )
    await make_extract_node(deps)(state)
    # 'Z'는 프롬프트 본문에 등장하지 않으므로 절단 길이를 정확히 잰다.
    assert deps.llm.prompt_text("extract").count("Z") == 50


# ── L2-10 ~ L2-12: evaluate_node ────────────────────────────────


def _verdict(complete: bool, statuses: dict[str, bool], next_q: list[tuple[str, str]] = None,
             can_retry: bool = True) -> CoverageVerdictOut:
    return CoverageVerdictOut(
        requirements=[
            RequirementVerdictOut(id=rid, satisfied=ok) for rid, ok in statuses.items()
        ],
        complete=complete,
        can_retry=can_retry,
        next_queries=[QueryOut(requirement_id=r, query=q) for r, q in (next_q or [])],
    )


async def test_l2_10_replans_only_missing_requirements():
    """L2-10: 충족된 requirement의 쿼리는 다시 만들지 않는다 (핵심)."""
    verdict = _verdict(
        complete=False,
        statuses={"r1": True, "r2": False},
        next_q=[("r2", "신한저축은행 경영공시 BIS")],
    )
    deps = _deps(llm=FakeLLM(evaluate=[verdict]))
    state = _state(
        requirements=[
            Requirement(id="r1", description="A의 BIS"),
            Requirement(id="r2", description="B의 BIS"),
        ],
        query_history=["A BIS", "B BIS"],
        search_ok=True,
        new_evidence_count=1,
    )
    out = await make_evaluate_node(deps)(state)

    statuses = {r.id: r.status for r in out["requirements"]}
    assert statuses == {"r1": "satisfied", "r2": "missing"}
    assert [q.requirement_id for q in out["pending_queries"]] == ["r2"]
    assert out["iteration"] == 1
    assert out["stop_reason"] == ""


async def test_evaluate_drops_next_query_for_satisfied_requirement():
    """충족된 requirement를 겨냥한 재쿼리는 버린다."""
    verdict = _verdict(
        complete=False,
        statuses={"r1": True, "r2": False},
        next_q=[("r1", "A BIS 재검색"), ("r2", "B BIS 재검색")],
    )
    deps = _deps(llm=FakeLLM(evaluate=[verdict]))
    state = _state(
        requirements=[
            Requirement(id="r1", description="A의 BIS"),
            Requirement(id="r2", description="B의 BIS"),
        ],
        search_ok=True,
        new_evidence_count=1,
    )
    out = await make_evaluate_node(deps)(state)
    assert [q.query for q in out["pending_queries"]] == ["B BIS 재검색"]


async def test_l2_11_repeated_queries_exhaust_retry():
    """L2-11 (E9/R3): 재쿼리가 이력과 전부 중복이면 can_retry=False."""
    verdict = _verdict(
        complete=False, statuses={"r1": False}, next_q=[("r1", "A BIS")],
    )
    deps = _deps(llm=FakeLLM(evaluate=[verdict]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        query_history=["A BIS"],
        search_ok=True,
        new_evidence_count=1,
    )
    out = await make_evaluate_node(deps)(state)

    assert out["can_retry"] is False
    assert out["stop_reason"] == StopReason.EXHAUSTED.value
    assert deps.logger.has("warning", "duplicate")


async def test_evaluate_no_next_queries_exhausts_retry():
    """대안 쿼리를 못 내놓으면 소진 처리."""
    verdict = _verdict(complete=False, statuses={"r1": False}, next_q=[])
    deps = _deps(llm=FakeLLM(evaluate=[verdict]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        search_ok=True, new_evidence_count=1,
    )
    out = await make_evaluate_node(deps)(state)
    assert out["can_retry"] is False


async def test_evaluate_respects_llm_can_retry_false():
    verdict = _verdict(
        complete=False, statuses={"r1": False}, next_q=[("r1", "새 쿼리")], can_retry=False,
    )
    deps = _deps(llm=FakeLLM(evaluate=[verdict]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        search_ok=True, new_evidence_count=1,
    )
    out = await make_evaluate_node(deps)(state)
    assert out["can_retry"] is False


async def test_l2_12_evaluate_failure_is_fail_open():
    """L2-12 (E8/D7): evaluate LLM 예외 → 즉시 종료, 예외 미전파."""
    deps = _deps(llm=FakeLLM(evaluate=[RuntimeError("judge down")]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        search_ok=True, new_evidence_count=1,
    )
    out = await make_evaluate_node(deps)(state)

    assert out["stop_reason"] == StopReason.EVAL_FAILED.value
    assert deps.logger.has("warning", "evaluate")


async def test_evaluate_skips_llm_when_search_failed():
    """E4: 검색이 전부 실패했으면 evaluate LLM을 호출하지 않는다."""
    deps = _deps(llm=FakeLLM(evaluate=[]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        search_ok=False,
    )
    out = await make_evaluate_node(deps)(state)

    assert deps.llm.count("evaluate") == 0
    assert out["stop_reason"] == StopReason.EXHAUSTED.value


async def test_evaluate_all_satisfied_completes():
    verdict = _verdict(complete=True, statuses={"r1": True, "r2": True})
    deps = _deps(llm=FakeLLM(evaluate=[verdict]))
    state = _state(
        requirements=[
            Requirement(id="r1", description="A"), Requirement(id="r2", description="B"),
        ],
        search_ok=True, new_evidence_count=2,
    )
    out = await make_evaluate_node(deps)(state)
    assert out["stop_reason"] == StopReason.COMPLETE.value


async def test_evaluate_prompt_carries_query_history():
    """D11/R3: 이전 쿼리 이력을 전량 주입해 동어반복을 차단한다."""
    verdict = _verdict(complete=False, statuses={"r1": False}, next_q=[("r1", "완전히 다른 쿼리")])
    deps = _deps(llm=FakeLLM(evaluate=[verdict]))
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        query_history=["첫 번째 쿼리", "두 번째 쿼리"],
        search_ok=True, new_evidence_count=1,
    )
    await make_evaluate_node(deps)(state)

    prompt = deps.llm.prompt_text("evaluate")
    assert "첫 번째 쿼리" in prompt
    assert "두 번째 쿼리" in prompt


async def test_evaluate_prompt_carries_constraints():
    """constraints는 직렬화되어 판정 LLM에 전달된다 (AD-5)."""
    verdict = _verdict(complete=True, statuses={"r1": True})
    deps = _deps(llm=FakeLLM(evaluate=[verdict]))
    state = _state(
        requirements=[
            Requirement(id="r1", description="A의 BIS",
                        constraints={"align": "same_period", "period": "latest"}),
        ],
        search_ok=True, new_evidence_count=1,
    )
    await make_evaluate_node(deps)(state)
    assert "same_period" in deps.llm.prompt_text("evaluate")


# ── 라우팅 ──────────────────────────────────────────────────────


def test_route_continues_when_no_stop_reason():
    assert route_after_evaluate(_state(stop_reason="")) == "execute"


@pytest.mark.parametrize("reason", [r.value for r in StopReason])
def test_route_finalizes_on_any_stop_reason(reason):
    assert route_after_evaluate(_state(stop_reason=reason)) == "finalize"


# ── L2-13: finalize_node ────────────────────────────────────────


async def test_l2_13_marks_missing_requirements():
    """L2-13 (FR-16): 미충족 requirement는 본문에 명시된다."""
    deps = _deps()
    state = _state(
        requirements=[
            Requirement(id="r1", description="A의 BIS", status="satisfied"),
            Requirement(id="r2", description="B의 BIS", status="missing"),
        ],
        evidence=[Evidence("r1", "BIS 14.8%", "http://a", 0.9)],
        stop_reason=StopReason.MAX_ITERATION.value,
        iteration=2,
        search_ok=True,
    )
    out = await make_finalize_node(deps)(state)

    assert MISSING_MARK in out["body"]
    assert "B의 BIS" in out["body"]
    assert "BIS 14.8%" in out["body"]
    assert "http://a" in out["body"]


async def test_finalize_summary_reports_coverage_and_stop():
    """FR-14: 요약에 전략·반복·커버리지·종료 사유가 담긴다."""
    deps = _deps()
    state = _state(
        strategy="parallel",
        requirements=[
            Requirement(id="r1", description="A", status="satisfied"),
            Requirement(id="r2", description="B", status="missing"),
        ],
        evidence=[Evidence("r1", "값", "http://a", 0.9)],
        stop_reason=StopReason.NO_GAIN.value,
        iteration=2,
        query_history=["q1", "q2"],
        search_ok=True,
    )
    out = await make_finalize_node(deps)(state)

    summary = out["summary"]
    assert "strategy=parallel" in summary
    assert "coverage=1/2" in summary
    assert "stop=no_gain" in summary
    assert "iteration=2" in summary
    assert len(summary) <= 512


async def test_finalize_uses_raw_results_when_degraded():
    """E6: 추출이 무너지면 원문 검색 결과를 본문으로 쓴다."""
    deps = _deps()
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        raw_results=[("q1", True, "원문 검색 결과 본문")],
        evidence=[],
        extract_degraded=True,
        stop_reason=StopReason.COMPLETE.value,
        search_ok=True,
        iteration=1,
    )
    out = await make_finalize_node(deps)(state)
    assert "원문 검색 결과 본문" in out["body"]


async def test_finalize_reports_search_failure():
    """E4: 검색이 전부 실패하면 본문에 사유가 남는다."""
    deps = _deps()
    state = _state(
        requirements=[Requirement(id="r1", description="A의 BIS")],
        raw_results=[("q1", False, "검색 실패: timeout")],
        stop_reason=StopReason.EXHAUSTED.value,
        search_ok=False,
        iteration=1,
    )
    out = await make_finalize_node(deps)(state)
    assert "검색 실패" in out["body"]
