"""파이프라인 kb_id — agent-kb-quick-setup Design §4.2 / FR-12.

kb_id 가 있으면 CREATE 단계가 RAG 도구와 tool_configs 를 주입하고, 없으면 기존
논스톱 실행과 바이트 단위로 동일하다 (additive).
"""
from src.domain.agent_create_pipeline.policies import KNOWLEDGE_TOOL_ID
from src.domain.agent_create_pipeline.stages import PipelineStop

from tests.application.agent_create_pipeline.test_use_case import (
    _drain,
    _outcome,
    _pipeline,
)


async def test_kb_id_injects_knowledge_tool_into_create_request() -> None:
    use_case, fakes = _pipeline()
    events = await _drain(use_case, kb_id="kb-1")
    request = fakes["create"].calls[0]
    assert request.tool_ids == ["internal:a", KNOWLEDGE_TOOL_ID]
    assert request.tool_configs is not None
    assert request.tool_configs[KNOWLEDGE_TOOL_ID].kb_id == "kb-1"
    assert _outcome(events).kb_id == "kb-1"


async def test_without_kb_id_create_request_is_unchanged() -> None:
    use_case, fakes = _pipeline()
    events = await _drain(use_case)
    request = fakes["create"].calls[0]
    assert request.tool_ids == ["internal:a"]
    assert request.tool_configs is None
    assert _outcome(events).kb_id is None


async def test_kb_id_is_echoed_on_stopped_outcome() -> None:
    use_case, _ = _pipeline()
    events = await _drain(
        use_case,
        kb_id="kb-1",
        stop_after=PipelineStop.PROMPT,
        tools_confirmed=True,
        tool_ids=("internal:a",),
    )
    outcome = _outcome(events)
    assert outcome.status == "prompt_ready"
    assert outcome.kb_id == "kb-1"


async def test_kb_id_is_echoed_on_need_input_outcome() -> None:
    from src.domain.intent.schemas import IntentResult, SlotQuestion

    from tests.application.agent_create_pipeline.test_use_case import FakeIntentUC

    intent = FakeIntentUC(
        IntentResult(
            complete=False,
            questions=[SlotQuestion(slot_key="purpose", question="용도는?")],
        )
    )
    use_case, _ = _pipeline(intent=intent)
    outcome = _outcome(await _drain(use_case, kb_id="kb-1"))
    assert outcome.status == "need_input"
    assert outcome.kb_id == "kb-1"
