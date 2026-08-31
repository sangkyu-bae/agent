"""deep-search-pipeline 노드 (Design §2.1).

plan → execute → extract → evaluate → (execute | finalize)

Design Ref §6.1: 모든 LLM 단계는 graceful fallback한다 — 어떤 실패도 그래프를
중단시키지 않는다.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any

from src.application.deep_search.llm_schemas import (
    CoverageVerdictOut,
    EvidenceExtractOut,
    SearchPlanOut,
    to_mapping,
)
from src.application.deep_search.prompts import (
    EVALUATE_SYSTEM_PROMPT,
    EXTRACT_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT,
)
from src.application.deep_search.rendering import (
    render_evidence_body,
    render_raw_body,
    render_summary,
)
from src.domain.deep_search.policies import CoveragePolicy, DeepSearchBudgetPolicy
from src.domain.deep_search.schemas import (
    Evidence,
    Requirement,
    SearchQuery,
    StopReason,
    count_new_evidence,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


@dataclass
class NodeDeps:
    """노드가 필요로 하는 주입 의존 (Design §9.2 — 내부 생성 금지)."""

    tool: Any
    llm: Any
    budget: DeepSearchBudgetPolicy
    logger: LoggerInterface
    user_context: str = ""


def _system(deps: NodeDeps, prompt: str) -> dict:
    """사용자 컨텍스트 블록을 system prompt 앞에 prepend (§7)."""
    return {"role": "system", "content": deps.user_context + prompt}


def _describe(requirements: list[Requirement]) -> str:
    return "\n".join(
        f"- {r.id}: {r.description} / 조건: {r.constraints or '없음'} / 상태: {r.status}"
        for r in requirements
    )


# ── plan (D1: 이해 + 분해 + 쿼리를 1콜로) ───────────────────────


async def _invoke_plan(deps: NodeDeps, state: dict) -> tuple[SearchPlanOut | None, int]:
    user_content = f"[대화 맥락]\n{state['context']}\n\n[질문]\n{state['question']}"
    try:
        out = await deps.llm.with_structured_output(SearchPlanOut).ainvoke([
            _system(deps, PLAN_SYSTEM_PROMPT),
            {"role": "user", "content": user_content},
        ])
    except Exception as e:
        deps.logger.warning("deep_search plan failed, using original question", error=str(e))
        return None, 0
    return out, len(out.reasoning or "")


def _cap_single_strategy(
    deps: NodeDeps,
    strategy: str,
    requirements: list[Requirement],
    queries: list[SearchQuery],
) -> tuple[list[Requirement], list[SearchQuery]]:
    """G-01/FR-02: `single`이면 요구를 1개로 강제한다.

    프롬프트 준수에만 맡기면 "single인데 N쿼리 팬아웃"이 가능해 R1(비용 폭증)의
    유일한 조기 탈출 장치가 무력해진다. 규칙은 코드가 보증한다.
    """
    if strategy != "single" or len(requirements) <= 1:
        return requirements, queries

    deps.logger.warning(
        "deep_search single strategy produced multiple requirements, capping to one",
        requirements=len(requirements), queries=len(queries),
    )
    head = requirements[0]
    kept = [q for q in queries if q.requirement_id == head.id][:1]
    return [head], kept or [SearchQuery(requirement_id=head.id, query=head.description)]


def _build_plan(
    deps: NodeDeps, out: SearchPlanOut,
) -> tuple[list[Requirement], list[SearchQuery]]:
    requirements = [
        Requirement(
            id=r.id,
            description=r.description,
            constraints=to_mapping(r.constraints),  # D19: key/value 목록 → dict
        )
        for r in out.requirements
        if r.id and r.description.strip()
    ]
    known = {r.id for r in requirements}
    queries = [
        SearchQuery(requirement_id=q.requirement_id, query=q.query.strip())
        for q in out.queries
        if q.requirement_id in known and q.query.strip()
    ]
    if requirements and not queries:
        queries = [SearchQuery(r.id, r.description) for r in requirements]

    requirements, queries = _cap_single_strategy(
        deps, out.strategy, requirements, queries,
    )
    kept, dropped = deps.budget.truncate_queries(queries)
    if dropped:
        deps.logger.warning(
            "deep_search plan queries truncated",
            dropped=dropped, limit=deps.budget.max_query_per_iteration,
        )
    return requirements, kept


def _fallback_plan(state: dict, chars: int) -> dict:
    """E1: 원 질문 하나를 단일 요구로 삼는다 — legacy 동등 경로."""
    question = state["question"]
    return {
        "strategy": "single",
        "requirements": [Requirement(id="r1", description=question)],
        "pending_queries": [SearchQuery(requirement_id="r1", query=question)],
        "plan_fallback": True,
        "llm_chars": state["llm_chars"] + chars,
    }


def make_plan_node(deps: NodeDeps):
    async def plan_node(state: dict) -> dict:
        deps.logger.info("deep_search plan_node", question_length=len(state["question"]))
        out, chars = await _invoke_plan(deps, state)
        if out is None:
            return _fallback_plan(state, chars)

        requirements, queries = _build_plan(deps, out)
        if not requirements or not queries:
            deps.logger.warning("deep_search plan produced empty plan, using fallback")
            return _fallback_plan(state, chars)

        return {
            "strategy": out.strategy,
            "requirements": requirements,
            "pending_queries": queries,
            "plan_fallback": False,
            "llm_chars": state["llm_chars"] + chars,
        }

    return plan_node


# ── execute (도구 병렬) ─────────────────────────────────────────


def _as_text(result: Any) -> str:
    return result if isinstance(result, str) else str(result)


async def safe_search(deps: NodeDeps, query: str) -> tuple[str, bool, str]:
    """검색 1회. 예외는 (query, False, 사유)로 흡수한다 (E3).

    D8: 도구가 max_results를 받지 않으면 query만으로 한 번 재시도한다.
    """
    budget_payload = {"query": query, "max_results": deps.budget.max_result_per_query}
    try:
        return query, True, _as_text(await deps.tool.ainvoke(budget_payload))
    except (TypeError, ValueError) as e:
        deps.logger.warning(
            "deep_search tool rejected max_results, retrying with query only",
            error=str(e),
        )
    except Exception as e:
        deps.logger.error("deep_search search failed", exception=e)
        return query, False, f"검색 실패: {e}"

    try:
        return query, True, _as_text(await deps.tool.ainvoke({"query": query}))
    except Exception as e:
        deps.logger.error("deep_search search failed", exception=e)
        return query, False, f"검색 실패: {e}"


def make_execute_node(deps: NodeDeps):
    async def execute_node(state: dict) -> dict:
        queries = state["pending_queries"]
        deps.logger.info(
            "deep_search execute_node", count=len(queries), iteration=state["iteration"],
        )
        results = list(await asyncio.gather(
            *[safe_search(deps, q.query) for q in queries]
        ))
        return {
            "raw_results": results,
            "search_ok": any(ok for _, ok, _ in results),
            "query_history": state["query_history"] + [q.query for q in queries],
            "pending_queries": [],
        }

    return execute_node


# ── extract (쿼리별 병렬 LLM) ───────────────────────────────────


async def _invoke_extract(
    deps: NodeDeps, state: dict, query: str, text: str,
) -> tuple[EvidenceExtractOut | None, int]:
    user_content = (
        f"[요구 목록]\n{_describe(state['requirements'])}\n\n"
        f"[사용한 검색 쿼리]\n{query}\n\n"
        f"[검색 결과]\n{text[:deps.budget.extract_result_head]}"
    )
    try:
        out = await deps.llm.with_structured_output(EvidenceExtractOut).ainvoke([
            _system(deps, EXTRACT_SYSTEM_PROMPT),
            {"role": "user", "content": user_content},
        ])
    except Exception as e:
        deps.logger.warning("deep_search extract failed for one query", error=str(e))
        return None, 0
    return out, sum(len(e.content) for e in out.evidence)


def _admissible(deps: NodeDeps, raw: list, known: set[str]) -> list[Evidence]:
    """E7: 출처 없음·저신뢰·미지의 요구를 겨냥한 근거는 폐기 (환각 방지, D6)."""
    accepted: list[Evidence] = []
    for item in raw:
        evidence = Evidence(
            requirement_id=item.requirement_id,
            content=item.content,
            source=item.source,
            confidence=item.confidence,
            attrs=to_mapping(item.attrs),  # D19: key/value 목록 → dict
        )
        if evidence.requirement_id not in known:
            continue
        if CoveragePolicy.is_admissible(evidence, deps.budget):
            accepted.append(evidence)

    dropped = len(raw) - len(accepted)
    if dropped:
        deps.logger.warning("deep_search discarded evidence", dropped=dropped)
    return accepted


def make_extract_node(deps: NodeDeps):
    async def extract_node(state: dict) -> dict:
        succeeded = [(q, t) for q, ok, t in state["raw_results"] if ok]
        if not succeeded:
            return {"new_evidence_count": 0, "extract_degraded": False}

        outs = list(await asyncio.gather(
            *[_invoke_extract(deps, state, q, t) for q, t in succeeded]
        ))
        raw = [item for out, _ in outs if out is not None for item in out.evidence]
        fresh = _admissible(deps, raw, {r.id for r in state["requirements"]})

        degraded = all(out is None for out, _ in outs)
        if degraded:
            deps.logger.warning("deep_search extract failed for all queries, using raw results")

        return {
            "evidence": fresh,
            "new_evidence_count": count_new_evidence(state["evidence"], fresh),
            "extract_degraded": degraded,
            "llm_chars": state["llm_chars"] + sum(c for _, c in outs),
        }

    return extract_node


# ── evaluate (D2: 판정 + 재계획을 1콜로) ────────────────────────


async def _invoke_evaluate(
    deps: NodeDeps, state: dict,
) -> tuple[CoverageVerdictOut | None, int]:
    history = "\n".join(f"- {q}" for q in state["query_history"]) or "없음"
    user_content = (
        f"[질문]\n{state['question']}\n\n"
        f"[요구 목록]\n{_describe(state['requirements'])}\n\n"
        f"[확보한 근거]\n{render_evidence_body(state['requirements'], state['evidence'])}\n\n"
        f"[이전 검색 쿼리]\n{history}"
    )
    try:
        out = await deps.llm.with_structured_output(CoverageVerdictOut).ainvoke([
            _system(deps, EVALUATE_SYSTEM_PROMPT),
            {"role": "user", "content": user_content},
        ])
    except Exception as e:
        deps.logger.warning("deep_search evaluate failed, stopping fail-open", error=str(e))
        return None, 0
    return out, len(out.retry_reason or "")


def _apply_verdict(
    requirements: list[Requirement], out: CoverageVerdictOut,
) -> list[Requirement]:
    satisfied = {v.id for v in out.requirements if v.satisfied}
    return [
        replace(r, status=CoveragePolicy.SATISFIED if r.id in satisfied else CoveragePolicy.MISSING)
        for r in requirements
    ]


def _plan_retry(
    deps: NodeDeps, state: dict, out: CoverageVerdictOut, requirements: list[Requirement],
) -> tuple[list[SearchQuery], bool]:
    """미충족 요구만을 겨냥한 재쿼리를 고른다 (FR-08 / E9)."""
    missing = set(CoveragePolicy.missing_ids(requirements))
    history = {q.strip() for q in state["query_history"]}
    candidates = [
        SearchQuery(requirement_id=q.requirement_id, query=q.query.strip())
        for q in out.next_queries
        if q.requirement_id in missing and q.query.strip()
    ]
    fresh = [q for q in candidates if q.query not in history]

    if candidates and not fresh:
        deps.logger.warning(
            "deep_search replan produced duplicate queries only", count=len(candidates),
        )
        return [], False

    kept, dropped = deps.budget.truncate_queries(fresh)
    if dropped:
        deps.logger.warning("deep_search replan queries truncated", dropped=dropped)
    if not kept or not out.can_retry:
        return [], False
    return kept, True


def _stopped(state: dict, iteration: int, reason: StopReason, chars: int = 0) -> dict:
    return {
        "pending_queries": [],
        "can_retry": False,
        "iteration": iteration,
        "stop_reason": reason.value,
        "llm_chars": state["llm_chars"] + chars,
    }


def make_evaluate_node(deps: NodeDeps):
    async def evaluate_node(state: dict) -> dict:
        iteration = state["iteration"] + 1
        if not state["search_ok"]:
            # E4: 검색이 전부 실패했으면 판정 LLM을 호출하지 않는다.
            deps.logger.warning("deep_search all searches failed, skipping evaluate")
            return _stopped(state, iteration, StopReason.EXHAUSTED)

        out, chars = await _invoke_evaluate(deps, state)
        if out is None:
            return _stopped(state, iteration, StopReason.EVAL_FAILED, chars)  # D7

        requirements = _apply_verdict(state["requirements"], out)
        queries, can_retry = _plan_retry(deps, state, out, requirements)
        stop = CoveragePolicy.should_stop(
            requirements=requirements,
            iteration=iteration,
            new_evidence_count=state["new_evidence_count"],
            can_retry=can_retry,
            budget=deps.budget,
        )
        return {
            "requirements": requirements,
            "pending_queries": queries,
            "can_retry": can_retry,
            "iteration": iteration,
            "stop_reason": stop.value if stop else "",
            "llm_chars": state["llm_chars"] + chars,
        }

    return evaluate_node


def route_after_evaluate(state: dict) -> str:
    """종료 사유가 정해졌으면 finalize, 아니면 다음 라운드 검색."""
    return "finalize" if state.get("stop_reason") else "execute"


# ── finalize (LLM 없음) ─────────────────────────────────────────


def _build_body(state: dict) -> str:
    if not state["search_ok"] or state["extract_degraded"]:
        return render_raw_body(state["raw_results"])
    return render_evidence_body(state["requirements"], state["evidence"])


def make_finalize_node(deps: NodeDeps):
    async def finalize_node(state: dict) -> dict:
        requirements = state["requirements"]
        deps.logger.info(
            "deep_search finished",
            stop_reason=state.get("stop_reason") or "unknown",
            satisfied=CoveragePolicy.satisfied_count(requirements),
            total=len(requirements),
            iteration=state["iteration"],
        )
        return {"body": _build_body(state), "summary": render_summary(state)}

    return finalize_node
