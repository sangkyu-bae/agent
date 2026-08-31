"""Evidence → 본문/요약 렌더 (Design §10.4, FR-15/FR-16).

LLM을 호출하지 않는다. finalize 노드의 순수 변환부.
"""
from __future__ import annotations

from src.domain.deep_search.policies import CoveragePolicy
from src.domain.deep_search.schemas import Evidence, Requirement

# FR-16: 미충족 요구를 본문에 명시해 final_answer의 환각을 막는다.
MISSING_MARK = "[미확보]"

SUMMARY_MAX_CHARS = 512
_RAW_HEAD = 4000


def _render_group(requirement: Requirement, items: list[Evidence]) -> list[str]:
    if not items:
        return [f"{MISSING_MARK} {requirement.description} — 검색으로 확인되지 않음"]

    lines = [f"■ {requirement.description}"]
    lines.extend(f"- {ev.content} (출처: {ev.source})" for ev in items)
    return lines


def render_evidence_body(
    requirements: list[Requirement], evidence: list[Evidence],
) -> str:
    """requirement별로 근거를 묶어 본문을 만든다 (FR-15)."""
    by_requirement: dict[str, list[Evidence]] = {r.id: [] for r in requirements}
    for ev in evidence:
        by_requirement.setdefault(ev.requirement_id, []).append(ev)

    lines: list[str] = []
    for requirement in requirements:
        lines.extend(_render_group(requirement, by_requirement.get(requirement.id, [])))
        lines.append("")
    return "\n".join(lines).strip()


def render_raw_body(raw_results: list[tuple[str, bool, str]]) -> str:
    """추출이 무너졌거나 검색이 실패했을 때의 본문 (E4/E6)."""
    blocks: list[str] = []
    for query, ok, text in raw_results:
        header = f"■ 검색: {query}" if ok else f"■ 검색: {query} — 실패"
        blocks.append(f"{header}\n{text[:_RAW_HEAD]}")
    return "\n\n".join(blocks) if blocks else "검색 결과가 없습니다."


def render_summary(state: dict) -> str:
    """step output 요약 (FR-14) — 512자 상한."""
    requirements = state.get("requirements") or []
    parts = [
        f"strategy={state.get('strategy') or 'unknown'}",
        f"iteration={state.get('iteration', 0)}",
        f"coverage={CoveragePolicy.satisfied_count(requirements)}/{len(requirements)}",
        f"stop={state.get('stop_reason') or 'unknown'}",
        f"queries={len(state.get('query_history') or [])}",
        f"evidence={len(state.get('evidence') or [])}",
    ]
    if state.get("plan_fallback"):
        parts.append("fallback=True")
    if state.get("extract_degraded"):
        parts.append("degraded=True")
    return " ".join(parts)[:SUMMARY_MAX_CHARS]
