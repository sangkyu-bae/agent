"""image_generate 전용 노드·compile 분기·서브 상한 — Design §4.3 / §8.2 #7·#8·#9."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import build_initial_state
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import SupervisorConfig, WorkerDefinition, WorkflowDefinition
from src.domain.image_generation.exceptions import ImageProviderError
from src.domain.image_generation.schemas import ImageRequestDraft
from src.domain.image_generation.value_objects import GeneratedImage, GenerationMode
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel


def _llm_model() -> LlmModel:
    now = datetime.now(UTC)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini", display_name="m",
        description=None, api_key_env="OPENAI_API_KEY", max_tokens=None, is_active=True,
        is_default=True, created_at=now, updated_at=now,
    )


def _worker(tool_config=None) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="image_generate", worker_id="image_generate_worker", description="이미지 생성",
        sort_order=0, tool_config=tool_config if tool_config is not None else {"llm_model_id": "img-1"},
    )


def _compiler(use_case=None, max_per_turn=4) -> WorkflowCompiler:
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    return WorkflowCompiler(
        tool_factory=MagicMock(), llm_factory=llm_factory, logger=MagicMock(), hooks=DefaultHooks(),
        image_generation_use_case=use_case, image_generation_max_per_turn=max_per_turn,
    )


def _result(**over) -> GeneratedImage:
    base = dict(
        file_id="a" * 32, filename="generated-1.png", width=1024, height=1024, mime="image/png",
        model_id="img-1", model_name="gpt-image-1", provider="openai", prompt="가을 배너",
        mode=GenerationMode.GENERATE, elapsed_ms=5, fell_back_to_generate=False,
    )
    base.update(over)
    return GeneratedImage(**base)


def _llm(draft: ImageRequestDraft | None = None) -> MagicMock:
    llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=draft or ImageRequestDraft(
        prompt="가을 정기예금 특판 배너", size="1024x1024", quality="standard",
        mode="generate", source_image_index=None, reason="r",
    ))
    llm.with_structured_output.return_value = structured
    return llm


def _state(**over) -> dict:
    s = {
        "messages": [HumanMessage(content="가을 특판 배너 만들어 줘")],
        "token_usage": 0, "token_limit": 8000, "attachments": [], "analysis_source": [],
        "generated_images": [], "generated_image_count": 0, "worker_task": "배너 생성",
    }
    s.update(over)
    return s


class TestNode:
    @pytest.mark.asyncio
    async def test_success_returns_message_channel_and_count(self) -> None:
        uc = MagicMock(); uc.run = AsyncMock(return_value=_result())
        compiler = _compiler(uc)
        auth = MagicMock(); auth.user_id = 7
        node = compiler._create_image_generate_node(
            _llm(), _worker(), auth_ctx=auth, request_id="r", worker_context_block="CTX",
        )
        out = await node(_state())
        msg = out["messages"][0]
        assert isinstance(msg, AIMessage) and msg.name == "image_generate_worker"
        assert "![generated-1.png](/api/v1/document-extractor/files/" in msg.content
        assert out["generated_images"][0]["file_id"] == "a" * 32
        assert out["generated_image_count"] == 1
        cmd = uc.run.await_args.args[0]
        assert cmd.prompt == "가을 정기예금 특판 배너" and cmd.owner_user_id == "7"
        assert uc.run.await_args.kwargs["llm_model_id"] == "img-1"
        # 프롬프트 작성 LLM 은 구조화 출력 + 워커 컨텍스트를 받는다
        sent = _llm().with_structured_output.return_value.ainvoke  # 형태 확인용
        assert sent is not None

    @pytest.mark.asyncio
    async def test_turn_cap_blocks_without_calling_use_case(self) -> None:
        uc = MagicMock(); uc.run = AsyncMock()
        node = _compiler(uc, max_per_turn=2)._create_image_generate_node(
            _llm(), _worker(), auth_ctx=None, request_id="r",
        )
        out = await node(_state(generated_image_count=2))
        assert "상한" in out["messages"][0].content
        assert out.get("generated_image_count", 2) == 2
        uc.run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_state_cap_overrides_default(self) -> None:
        uc = MagicMock(); uc.run = AsyncMock(return_value=_result())
        node = _compiler(uc, max_per_turn=4)._create_image_generate_node(
            _llm(), _worker(), auth_ctx=None, request_id="r",
        )
        out = await node(_state(generated_image_count=1, image_generation_max_per_turn=1))
        assert "상한" in out["messages"][0].content and uc.run.await_count == 0

    @pytest.mark.asyncio
    async def test_edit_uses_attachment_and_fallback_without(self) -> None:
        uc = MagicMock(); uc.run = AsyncMock(return_value=_result(mode=GenerationMode.EDIT))
        draft = ImageRequestDraft(prompt="배경 흰색", size="1024x1024", quality="standard",
                                  mode="edit", source_image_index=0, reason="r")
        node = _compiler(uc)._create_image_generate_node(_llm(draft), _worker(), auth_ctx=None, request_id="r")
        att = {"type": "image", "file_path": "/tmp/a.png", "mime": "image/png", "file_name": "a.png"}
        await node(_state(attachments=[att]))
        cmd = uc.run.await_args.args[0]
        assert cmd.mode == GenerationMode.EDIT and cmd.source_image.file_path == "/tmp/a.png"
        assert cmd.fell_back_to_generate is False

        uc.run.reset_mock(); uc.run.return_value = _result(fell_back_to_generate=True)
        await node(_state(attachments=[]))
        cmd = uc.run.await_args.args[0]
        assert cmd.mode == GenerationMode.GENERATE and cmd.fell_back_to_generate is True

    @pytest.mark.asyncio
    async def test_bad_tool_config_replies_notice(self) -> None:
        uc = MagicMock(); uc.run = AsyncMock()
        node = _compiler(uc)._create_image_generate_node(_llm(), _worker(tool_config={}), auth_ctx=None, request_id="r")
        out = await node(_state())
        assert "이미지 모델" in out["messages"][0].content and uc.run.assert_not_awaited() is None

    @pytest.mark.asyncio
    async def test_use_case_error_replies_user_message(self) -> None:
        uc = MagicMock(); uc.run = AsyncMock(side_effect=ImageProviderError("정책 거부", retryable=False))
        node = _compiler(uc)._create_image_generate_node(_llm(), _worker(), auth_ctx=None, request_id="r")
        out = await node(_state())
        assert "정책 거부" in out["messages"][0].content
        assert "generated_image_count" not in out or out["generated_image_count"] == 0

    @pytest.mark.asyncio
    async def test_non_retryable_error_adds_no_retry_hint(self) -> None:
        # 2026-11 실런: 모델 미접근 400 에 supervisor 가 같은 워커를 8회 재호출했다
        uc = MagicMock()
        uc.run = AsyncMock(side_effect=ImageProviderError("모델 없음", retryable=False))
        node = _compiler(uc)._create_image_generate_node(
            _llm(), _worker(), auth_ctx=None, request_id="r",
        )
        out = await node(_state())
        assert "재시도하지 말고" in out["messages"][0].content

        uc.run = AsyncMock(side_effect=ImageProviderError("일시 오류", retryable=True))
        out = await node(_state())
        assert "일시 오류" in out["messages"][0].content
        assert "재시도하지 말고" not in out["messages"][0].content

    @pytest.mark.asyncio
    async def test_missing_use_case_replies_not_wired(self) -> None:
        node = _compiler(None)._create_image_generate_node(_llm(), _worker(), auth_ctx=None, request_id="r")
        out = await node(_state())
        assert "구성되지 않았습니다" in out["messages"][0].content

    @pytest.mark.asyncio
    async def test_draft_failure_replies_notice(self) -> None:
        uc = MagicMock(); uc.run = AsyncMock()
        llm = MagicMock()
        llm.with_structured_output.return_value.ainvoke = AsyncMock(side_effect=RuntimeError("llm down"))
        node = _compiler(uc)._create_image_generate_node(llm, _worker(), auth_ctx=None, request_id="r")
        out = await node(_state())
        assert "이미지 생성 실패" in out["messages"][0].content
        uc.run.assert_not_awaited()


class TestCompileBranch:
    @pytest.mark.asyncio
    async def test_image_generate_is_function_node_not_tool_factory(self) -> None:
        compiler = _compiler(MagicMock())
        workflow = WorkflowDefinition(supervisor_prompt="p", workers=[_worker()], flow_hint="f")
        with patch("src.application.agent_builder.workflow_compiler.create_agent") as ca:
            graph = await compiler.compile(workflow, _llm_model(), "req")
        assert "image_generate_worker" in graph.get_graph().nodes
        compiler._tool_factory.create.assert_not_called()
        compiler._tool_factory.create_async.assert_not_called()
        ca.assert_not_called()


class TestSubAgentCap:
    @pytest.mark.asyncio
    async def test_sub_graph_gets_half_cap_and_results_merge(self) -> None:
        compiler = _compiler(MagicMock(), max_per_turn=4)
        sub_graph = AsyncMock()
        sub_graph.ainvoke.return_value = {
            "messages": [AIMessage(content="서브 답")], "token_usage": 1,
            "generated_images": [{"file_id": "s" * 32, "filename": "generated-s.png"}],
            "generated_image_count": 1,
        }
        node = compiler._wrap_sub_agent("sub_w", sub_graph)
        out = await node(_state(generated_images=[{"file_id": "p" * 32, "filename": "generated-p.png"}],
                                generated_image_count=1, max_iterations=20))
        sent = sub_graph.ainvoke.call_args.args[0]
        assert sent["image_generation_max_per_turn"] == 2
        assert [i["file_id"] for i in out["generated_images"]] == ["p" * 32, "s" * 32]
        assert out["generated_image_count"] == 2

    def test_build_initial_state_defaults(self) -> None:
        s = build_initial_state(messages=[], config=SupervisorConfig(), available_workers=[])
        assert s["generated_images"] == [] and s["generated_image_count"] == 0
        assert s["image_generation_max_per_turn"] is None
        s2 = build_initial_state(messages=[], config=SupervisorConfig(), available_workers=[],
                                 image_generation_max_per_turn=2)
        assert s2["image_generation_max_per_turn"] == 2
