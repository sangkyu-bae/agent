"""general 전환 근거 규칙 — RAGAS 그래프 끔/켬 실행 2건 (Design §4.2 stage, module-7).

같은 에이전트·같은 테스트셋을 그래프 끔(baseline)과 켬(graph)으로 각각 평가해 둘 다
완료돼야 근거로 인정한다. 켬/끔은 실행 설정의 allow_supplemental 로 구분한다
(관리자만 켤 수 있다). 설정에 값이 없는 예전 실행은 끔으로 본다.
"""

from __future__ import annotations

from dataclasses import dataclass

_COMPLETED = "completed"
_AGENT = "agent"


@dataclass(frozen=True)
class EvalRunFacts:
    id: str
    status: str
    target_type: str
    target_id: str | None
    testset_id: str | None
    allow_supplemental: bool


class EvalEvidencePolicy:
    @staticmethod
    def problem(
        baseline: EvalRunFacts | None, graph: EvalRunFacts | None
    ) -> str | None:
        """근거로 쓸 수 없는 이유(없으면 None)."""
        if baseline is None or graph is None:
            return "not_found"
        if baseline.id == graph.id:
            return "same_run"
        if baseline.status != _COMPLETED or graph.status != _COMPLETED:
            return "not_completed"
        if baseline.target_type != _AGENT or graph.target_type != _AGENT:
            return "not_agent"
        if baseline.target_id != graph.target_id:
            return "different_agent"
        if baseline.testset_id != graph.testset_id:
            return "different_testset"
        if baseline.allow_supplemental:
            return "baseline_not_off"
        if not graph.allow_supplemental:
            return "graph_not_on"
        return None
