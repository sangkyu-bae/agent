"""RunAgentUseCase 이미지 첨부 — chat-image-attachment Design §4.3 / §8.2 #11, #13, #14.

- precheck_attachments: 이미지 없음 → 즉시 반환, 장수 초과 → TooManyImagesError,
  supports_vision=false / provider 미지원 → VisionNotSupportedError
- _prepare_graph: 이번 턴 user content = [text, image×N], 이미지 없으면 str 그대로
- stream: DB 저장 content 는 query + 마커, base64 없음
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest
from src.domain.agent_attachment.exceptions import (
    TooManyImagesError,
    VisionNotSupportedError,
)
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.llm_model.entity import LlmModel

MODEL_ID = "model-vision"
_BLOCK = {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUFB", "detail": "high"}}


def _llm_model(*, supports_vision: bool = True, provider: str = "openai") -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id=MODEL_ID, provider=provider, model_name="gpt-x", display_name="GPT-X",
        description=None, api_key_env="OPENAI_API_KEY", max_tokens=1000,
        is_active=True, is_default=False, created_at=now, updated_at=now,
        supports_vision=supports_vision,
    )


def _agent() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()), user_id="user-1", name="a", description="d",
        system_prompt="s", flow_hint="h",
        workers=[WorkerDefinition("tavily_search", "search_worker", "검색", 0)],
        llm_model_id=MODEL_ID, status="active", temperature=0.5,
        created_at=now, updated_at=now,
    )


def _builder(supports: bool = True) -> MagicMock:
    b = MagicMock()
    b.supports.return_value = supports
    b.build_from_path.return_value = _BLOCK
    return b


def _image(name: str = "a.png") -> dict:
    return {"type": "image", "file_path": f"/tmp/{name}", "user_id": "user-1",
            "mime": "image/png", "file_name": name, "width": 10, "height": 10}


def _use_case(*, llm_model: LlmModel | None = None, builder=None, max_count: int = 5):
    repository = MagicMock()
    repository.find_by_id = AsyncMock(return_value=_agent())
    llm_repo = MagicMock()
    llm_repo.find_by_id = AsyncMock(return_value=llm_model or _llm_model())
    compiler = MagicMock()
    graph = MagicMock()
    compiler.compile = AsyncMock(return_value=graph)
    message_repo = MagicMock()
    message_repo.find_by_session = AsyncMock(return_value=[])
    saved = MagicMock(); saved.id.value = 1
    message_repo.save = AsyncMock(return_value=saved)
    summary_repo = MagicMock()
    summary_repo.find_latest_by_session = AsyncMock(return_value=None)
    uc = RunAgentUseCase(
        repository=repository, llm_model_repository=llm_repo, compiler=compiler,
        logger=MagicMock(), message_repo=message_repo, summary_repo=summary_repo,
        summarizer=MagicMock(), policy=SummarizationPolicy(), tracker=None,
        image_block_builder=builder, image_max_count=max_count, image_detail="high",
    )
    return uc, {"repo": repository, "llm_repo": llm_repo, "compiler": compiler,
                "message_repo": message_repo}


class TestPrecheck:
    @pytest.mark.asyncio
    async def test_no_images_returns_without_loading_agent(self) -> None:
        uc, deps = _use_case(builder=_builder())
        await uc.precheck_attachments(
            agent_id="a", attachments=[{"type": "excel", "file_path": "/x"}],
            request_id="r", viewer_user_id="user-1", viewer_department_ids=[],
        )
        deps["repo"].find_by_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_too_many_images_raises_before_agent_load(self) -> None:
        uc, deps = _use_case(builder=_builder(), max_count=2)
        with pytest.raises(TooManyImagesError):
            await uc.precheck_attachments(
                agent_id="a", attachments=[_image("1.png"), _image("2.png"), _image("3.png")],
                request_id="r", viewer_user_id="user-1", viewer_department_ids=[],
            )
        deps["repo"].find_by_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_model_without_vision_raises(self) -> None:
        uc, _ = _use_case(llm_model=_llm_model(supports_vision=False), builder=_builder())
        with pytest.raises(VisionNotSupportedError) as ei:
            await uc.precheck_attachments(
                agent_id="a", attachments=[_image()], request_id="r",
                viewer_user_id="user-1", viewer_department_ids=[],
            )
        assert "GPT-X" in str(ei.value)

    @pytest.mark.asyncio
    async def test_unsupported_provider_raises(self) -> None:
        uc, _ = _use_case(llm_model=_llm_model(provider="gemini"), builder=_builder(supports=False))
        with pytest.raises(VisionNotSupportedError):
            await uc.precheck_attachments(
                agent_id="a", attachments=[_image()], request_id="r",
                viewer_user_id="user-1", viewer_department_ids=[],
            )

    @pytest.mark.asyncio
    async def test_no_builder_configured_raises(self) -> None:
        uc, _ = _use_case(builder=None)
        with pytest.raises(VisionNotSupportedError):
            await uc.precheck_attachments(
                agent_id="a", attachments=[_image()], request_id="r",
                viewer_user_id="user-1", viewer_department_ids=[],
            )

    @pytest.mark.asyncio
    async def test_vision_model_passes(self) -> None:
        uc, _ = _use_case(builder=_builder())
        await uc.precheck_attachments(
            agent_id="a", attachments=[_image()], request_id="r",
            viewer_user_id="user-1", viewer_department_ids=[],
        )


class TestPrepareGraphUserContent:
    @pytest.mark.asyncio
    async def test_images_make_last_user_content_a_block_list(self) -> None:
        builder = _builder()
        uc, deps = _use_case(builder=builder)
        request = RunAgentRequest(
            query="표에서 3분기 값은?", user_id="user-1", session_id=None,
            attachments=[_image("a.png"), _image("b.png")],
        )
        _, initial_state, _ = await uc._prepare_graph(
            agent=_agent(), request=request, session_id="s", callback=None,
            run_id=None, request_id="r",
        )
        last = initial_state["messages"][-1]
        assert last["role"] == "user"
        assert last["content"] == [{"type": "text", "text": "표에서 3분기 값은?"}, _BLOCK, _BLOCK]
        # provider·mime·detail 이 빌더에 전달된다
        kwargs = builder.build_from_path.call_args.kwargs
        assert kwargs["mime"] == "image/png" and kwargs["detail"] == "high"
        assert builder.build_from_path.call_args.args[0] == "openai"
        # state.attachments 에는 바이트가 없다
        assert all("data" not in a for a in initial_state["attachments"])

    @pytest.mark.asyncio
    async def test_no_images_keeps_str_content(self) -> None:
        uc, _ = _use_case(builder=_builder())
        request = RunAgentRequest(
            query="안녕", user_id="user-1", session_id=None,
            attachments=[{"type": "excel", "file_path": "/x.xlsx", "user_id": "user-1"}],
        )
        _, initial_state, _ = await uc._prepare_graph(
            agent=_agent(), request=request, session_id="s", callback=None,
            run_id=None, request_id="r",
        )
        assert initial_state["messages"][-1]["content"] == "안녕"

    @pytest.mark.asyncio
    async def test_history_turns_stay_str(self) -> None:
        uc, deps = _use_case(builder=_builder())
        prev = MagicMock()
        prev.role.value = "user"; prev.content = "이전 질문"; prev.turn_index.value = 1
        prev.is_blocked = False
        deps["message_repo"].find_by_session = AsyncMock(return_value=[prev])
        request = RunAgentRequest(
            query="지금 질문", user_id="user-1", session_id="s", attachments=[_image()],
        )
        _, initial_state, _ = await uc._prepare_graph(
            agent=_agent(), request=request, session_id="s", callback=None,
            run_id=None, request_id="r",
        )
        msgs = initial_state["messages"]
        assert msgs[0]["content"] == "이전 질문"
        assert isinstance(msgs[-1]["content"], list)


class TestPersistedUserMessage:
    @pytest.mark.asyncio
    async def test_saved_content_is_query_plus_marker(self) -> None:
        uc, deps = _use_case(builder=_builder())
        request = RunAgentRequest(
            query="이 표 값은?", user_id="user-1", session_id="s",
            attachments=[_image("a.png"), _image("b.png")],
        )
        # stream 의 저장 단계까지만 — graph 는 빈 이벤트로 끝낸다
        graph = deps["compiler"].compile.return_value

        def _astream(*a, **k):
            async def _gen():
                if False:
                    yield
            return _gen()

        graph.astream_events = MagicMock(side_effect=_astream)
        events = [ev async for ev in uc.stream(agent_id="a", request=request, request_id="r")]
        assert events  # RUN_STARTED 등
        saved_msg = deps["message_repo"].save.await_args_list[0].args[0]
        assert saved_msg.content == "이 표 값은?\n[이미지 첨부: a.png, b.png]"
        assert "base64" not in saved_msg.content

    @pytest.mark.asyncio
    async def test_saved_content_unchanged_without_images(self) -> None:
        uc, deps = _use_case(builder=_builder())
        request = RunAgentRequest(query="그냥 질문", user_id="user-1", session_id="s")
        graph = deps["compiler"].compile.return_value

        def _astream(*a, **k):
            async def _gen():
                if False:
                    yield
            return _gen()

        graph.astream_events = MagicMock(side_effect=_astream)
        [ev async for ev in uc.stream(agent_id="a", request=request, request_id="r")]
        saved_msg = deps["message_repo"].save.await_args_list[0].args[0]
        assert saved_msg.content == "그냥 질문"


class TestApprovalSnapshotRedaction:
    """Analysis G-C1 / Plan FR-09: approval_request 스냅샷에 base64 가 없어야 한다."""

    def test_snapshot_payload_has_no_image_bytes(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        from src.application.agent_builder.run_agent_use_case import _redact_state_images
        from src.infrastructure.approval.snapshot import SnapshotSerializer

        big = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "Q" * 5000}}
        state = {
            "messages": [
                HumanMessage(content=[{"type": "text", "text": "표 값은?"}, big]),
                AIMessage(content="승인 대기"),
            ],
            "approval_pending": {"worker_id": "w"},
            "iteration_count": 1,
        }
        payload, _ = SnapshotSerializer.dumps_with_limit(_redact_state_images(state))
        assert "data:image" not in payload and "QQQQ" not in payload
        assert "[image:image/png]" in payload
        assert "표 값은?" in payload
        # 원본 state 는 변경되지 않는다 (실행 중 그래프 상태 보존)
        assert state["messages"][0].content[1] == big

    def test_persist_path_calls_redaction(self) -> None:
        import inspect

        from src.application.agent_builder import run_agent_use_case as mod

        src = inspect.getsource(mod.RunAgentUseCase._persist_approval_if_pending)
        assert "_redact_state_images(" in src


class TestPrecheckOverride:
    @pytest.mark.asyncio
    async def test_override_model_is_used_for_vision_check(self) -> None:
        # Analysis G-I3: 실행과 같은 실효 모델로 판정
        uc, deps = _use_case(builder=_builder())
        deps["llm_repo"].find_by_id = AsyncMock(
            side_effect=lambda mid, rid: _llm_model(supports_vision=(mid == "vision-override"))
        )
        await uc.precheck_attachments(
            agent_id="a", attachments=[_image()], request_id="r",
            viewer_user_id="user-1", viewer_department_ids=[],
            llm_model_id_override="vision-override",
        )
        with pytest.raises(VisionNotSupportedError):
            await uc.precheck_attachments(
                agent_id="a", attachments=[_image()], request_id="r",
                viewer_user_id="user-1", viewer_department_ids=[],
            )
