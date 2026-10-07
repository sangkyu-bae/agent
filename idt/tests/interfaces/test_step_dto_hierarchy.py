"""StepDto 계층 필드 직렬화 테스트.

Design Ref: subagent-step-observability §4.1 / §8.2 B13
Plan SC: SC-6 (하위호환 — 필드 추가만, 평면 목록 유지)
"""
from datetime import datetime, timezone

from src.application.agent_run.use_cases.get_run_detail_use_case import StepNode
from src.domain.agent_run.entities import AgentRunStep
from src.domain.agent_run.value_objects import NodeType, RunId, StepStatus
from src.interfaces.schemas.agent_run_response import StepDto, _step_node_to_dto


def _step(**overrides) -> AgentRunStep:
    base = dict(
        id="c-1", run_id=RunId("11111111-1111-1111-1111-111111111111"), step_index=3,
        node_name="supervisor", node_type=NodeType.SUPERVISOR, llm_model_id=None,
        status=StepStatus.SUCCESS, input_summary=None, output_summary=None,
        started_at=datetime(2026, 10, 6, tzinfo=timezone.utc), ended_at=None,
        latency_ms=12, error_text=None,
    )
    base.update(overrides)
    return AgentRunStep(**base)


def test_B13_자식_step의_계층_필드가_DTO에_실린다():
    dto = _step_node_to_dto(StepNode(step=_step(parent_step_id="w-1", depth=1)))
    assert dto.parent_step_id == "w-1"
    assert dto.depth == 1
    body = dto.model_dump()
    assert body["parent_step_id"] == "w-1" and body["depth"] == 1


def test_B13_최상위_step은_None과_0():
    dto = _step_node_to_dto(StepNode(step=_step()))
    assert dto.parent_step_id is None
    assert dto.depth == 0


def test_필드_기본값으로_기존_생성부_호환():
    dto = StepDto(id="s", step_index=1, node_name="n", node_type="WORKER",
                  status="SUCCESS", started_at=datetime(2026, 10, 6, tzinfo=timezone.utc))
    assert dto.parent_step_id is None
    assert dto.depth == 0
