"""RolloutPolicy·StageTransitionPolicy (Design §3.1, §4.2 stage, Plan FR-20·FR-23)."""
import pytest
from src.domain.graph_rag.exceptions import GraphStageEvalRequiredError
from src.domain.graph_rag.policies import RolloutPolicy, StageTransitionPolicy
from src.domain.graph_rag.value_objects import RolloutStage

OFF, ADMIN, GENERAL = RolloutStage.OFF, RolloutStage.ADMIN_ONLY, RolloutStage.GENERAL


@pytest.mark.parametrize("stage, is_admin, expected", [
    (OFF, True, False), (OFF, False, False),
    (ADMIN, True, True), (ADMIN, False, False),
    (GENERAL, True, True), (GENERAL, False, True),
])
def test_rollout_allows(stage, is_admin, expected):
    assert RolloutPolicy.allows(stage, caller_is_admin=is_admin) is expected


def test_skip_reason_names_why():
    assert RolloutPolicy.skip_reason(OFF, caller_is_admin=True) == "stage_off"
    assert RolloutPolicy.skip_reason(ADMIN, caller_is_admin=False) == "grant_not_admin"
    assert RolloutPolicy.skip_reason(ADMIN, caller_is_admin=True) is None


@pytest.mark.parametrize("current, target", [
    (OFF, ADMIN), (ADMIN, OFF), (GENERAL, OFF), (GENERAL, ADMIN),
])
def test_non_general_targets_need_nothing(current, target):
    StageTransitionPolicy.validate(
        current, target, eval_evidence_ok=False, force_reason=None
    )


def test_general_without_evidence_or_reason_is_blocked():
    with pytest.raises(GraphStageEvalRequiredError):
        StageTransitionPolicy.validate(
            ADMIN, GENERAL, eval_evidence_ok=False, force_reason=None
        )


def test_general_with_short_reason_is_blocked():
    with pytest.raises(GraphStageEvalRequiredError):
        StageTransitionPolicy.validate(
            ADMIN, GENERAL, eval_evidence_ok=False, force_reason="급해서"
        )


def test_general_with_evidence_or_long_reason_passes():
    StageTransitionPolicy.validate(
        ADMIN, GENERAL, eval_evidence_ok=True, force_reason=None
    )
    StageTransitionPolicy.validate(
        ADMIN, GENERAL, eval_evidence_ok=False,
        force_reason="시연 일정상 평가 없이 공개하고 다음 주에 평가 실행",
    )


def test_same_stage_is_noop():
    assert StageTransitionPolicy.is_noop(ADMIN, ADMIN) is True
    assert StageTransitionPolicy.is_noop(ADMIN, GENERAL) is False
