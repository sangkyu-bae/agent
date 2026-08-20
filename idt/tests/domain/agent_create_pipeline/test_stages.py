"""단계 VO 테스트 — Design §3.1.

steps가 "항상 5개 고정"(§4.3)이 되려면 STAGE_ORDER 자체가 계약이다.
화면이 단계 바를 고정 렌더하므로 순서·값 문자열이 바뀌면 프론트 계약이 깨진다.
"""
from src.domain.agent_create_pipeline.stages import (
    STAGE_ORDER,
    PipelineStage,
    StageRecord,
    StageStatus,
)


def test_stage_order_is_the_five_fixed_stages_in_order() -> None:
    assert STAGE_ORDER == (
        PipelineStage.INTENT,
        PipelineStage.TOOLS,
        PipelineStage.PROMPT,
        PipelineStage.CREATE,
        PipelineStage.BIND,
    )


def test_stage_values_are_wire_strings() -> None:
    """응답 JSON에 그대로 실리는 문자열 — 변경은 프론트 계약 파괴다."""
    assert [s.value for s in STAGE_ORDER] == [
        "intent", "tools", "prompt", "create", "bind",
    ]
    assert [s.value for s in StageStatus] == [
        "ok", "degraded", "failed", "skipped",
    ]


def test_stage_record_defaults() -> None:
    record = StageRecord(stage=PipelineStage.INTENT, status=StageStatus.OK)
    assert record.reason is None
    assert record.elapsed_ms == 0
