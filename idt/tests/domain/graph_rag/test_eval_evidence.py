"""general 전환 근거 규칙 (Design §4.2 stage, module-7)."""

import pytest
from src.domain.graph_rag.eval_evidence import EvalEvidencePolicy, EvalRunFacts


def _run(id_="r1", **over):
    base = dict(
        id=id_,
        status="completed",
        target_type="agent",
        target_id="agent-1",
        testset_id="ts-1",
        allow_supplemental=False,
    )
    base.update(over)
    return EvalRunFacts(**base)


def test_valid_pair_off_then_on():
    assert (
        EvalEvidencePolicy.problem(_run("b"), _run("g", allow_supplemental=True))
        is None
    )


@pytest.mark.parametrize(
    "baseline,graph,reason",
    [
        (None, _run("g", allow_supplemental=True), "not_found"),
        (_run("b"), None, "not_found"),
        (_run("b"), _run("b", allow_supplemental=True), "same_run"),
        (
            _run("b", status="running"),
            _run("g", allow_supplemental=True),
            "not_completed",
        ),
        (
            _run("b"),
            _run("g", allow_supplemental=True, status="failed"),
            "not_completed",
        ),
        (_run("b", target_type="rag"), _run("g", allow_supplemental=True), "not_agent"),
        (
            _run("b"),
            _run("g", allow_supplemental=True, target_id="agent-2"),
            "different_agent",
        ),
        (
            _run("b"),
            _run("g", allow_supplemental=True, testset_id="ts-2"),
            "different_testset",
        ),
        (
            _run("b", allow_supplemental=True),
            _run("g", allow_supplemental=True),
            "baseline_not_off",
        ),
        (_run("b"), _run("g"), "graph_not_on"),
    ],
)
def test_invalid_pairs(baseline, graph, reason):
    assert EvalEvidencePolicy.problem(baseline, graph) == reason
