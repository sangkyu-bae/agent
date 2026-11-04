"""RunAgentUseCase 도구 권한 배선 (tool-access-control FR-09·10·11, Design §8.3 R1~R6·R14).

판정 주체: auth_ctx 있으면 그것(채팅·웹훅·잡), 없으면 user_id(스케줄·RAGAS), 승인 재개는
원래 요청자. 조회 실패는 deny_all(도구 없이 실행).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.agent_run.auth_context import AuthContext
from src.domain.tool_access.value_objects import ToolAccessSet
from tests.application.agent_builder.test_identity_subject_wiring import (
    _agent,
    _bare_run_uc,
)

ACCESS = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:tavily_search"}))


def _ctx() -> AuthContext:
    return AuthContext(
        user_id=7, display_name="u", role="user", primary_department_id=None,
        primary_department_name=None, department_ids=("d1",), department_names=(),
        permissions=frozenset(),
    )


def _uc(resolver):
    uc = _bare_run_uc()
    uc._tool_access_resolver = resolver
    uc._build_messages = AsyncMock(return_value=[])
    uc._build_graph_config = MagicMock(return_value={})
    return uc


def _resolver(access=ACCESS, error=None):
    r = MagicMock()
    r.for_auth_ctx = AsyncMock(return_value=access, side_effect=error)
    r.for_user_id = AsyncMock(return_value=access, side_effect=error)
    return r


def _request(user_id="7"):
    return MagicMock(user_id=user_id, session_id=None, query="q", attachments=None,
                     llm_model_id=None, temperature=None)


async def _prepare(uc, auth_ctx=None, sink=None):
    with patch("src.application.agent_builder.run_agent_use_case.build_initial_state",
               return_value={}) as init:
        await uc._prepare_graph(
            agent=_agent(), request=_request(), session_id="s", callback=None,
            run_id=None, request_id="rid", auth_ctx=auth_ctx, excluded_sink=sink,
        )
    return uc._compiler.compile.call_args.kwargs, init


class TestPrepareGraph:
    async def test_auth_ctx_path_uses_for_auth_ctx(self):
        r = _resolver()
        kwargs, _ = await _prepare(_uc(r), auth_ctx=_ctx())
        assert kwargs["tool_access"] is ACCESS
        r.for_auth_ctx.assert_awaited_once()
        r.for_user_id.assert_not_awaited()

    async def test_no_auth_ctx_uses_request_user_id(self):
        # R4·R6: 스케줄·RAGAS 는 auth_ctx 없이 user_id 만 넘긴다
        r = _resolver()
        kwargs, _ = await _prepare(_uc(r))
        assert kwargs["tool_access"] is ACCESS
        r.for_user_id.assert_awaited_once_with("7", "rid")

    async def test_resolver_failure_is_deny_all(self):
        # R14
        kwargs, _ = await _prepare(_uc(_resolver(error=RuntimeError("db"))))
        assert kwargs["tool_access"] == ToolAccessSet.deny_all()

    async def test_without_resolver_no_filter(self):
        kwargs, _ = await _prepare(_uc(None))
        assert kwargs["tool_access"] is None

    async def test_sink_is_passed_and_available_workers_exclude_it(self):
        uc = _uc(_resolver())
        agent = _agent()
        w_ok = WorkerDefinition(tool_id="tavily_search", worker_id="web", description="")
        w_no = WorkerDefinition(tool_id="python_code_executor", worker_id="code", description="")
        agent.to_workflow_definition.return_value = MagicMock(workers=[w_ok, w_no])

        async def fake_compile(**kw):
            kw["excluded_sink"].append(w_no)
            return MagicMock()

        uc._compiler.compile = AsyncMock(side_effect=fake_compile)
        sink: list = []
        with patch("src.application.agent_builder.run_agent_use_case.build_initial_state",
                   return_value={}) as init:
            await uc._prepare_graph(
                agent=agent, request=_request(), session_id="s", callback=None,
                run_id=None, request_id="rid", excluded_sink=sink,
            )
        assert sink == [w_no]
        assert init.call_args.kwargs["available_workers"] == ["web"]


class TestResume:
    async def test_resume_uses_original_requester(self):
        # R5: 승인 재개는 승인자가 아니라 원래 요청자 기준
        r = _resolver()
        uc = _uc(r)
        uc._parse_result = MagicMock(return_value=("답", None))
        await uc._resume_graph({}, _agent(), "rid", subject_user_id="requester-9")
        assert uc._compiler.compile.call_args.kwargs["tool_access"] is ACCESS
        r.for_user_id.assert_awaited_once_with("requester-9", "rid")


class TestAnswerPayload:
    def test_excluded_tools_only_when_present(self):
        p = RunAgentUseCase._answer_payload("a", [], None, excluded_tools=[])
        assert "excluded_tools" not in p
        p = RunAgentUseCase._answer_payload(
            "a", [], None, excluded_tools=[{"tool_id": "x", "name": "x", "reason": "no_permission"}]
        )
        assert p["excluded_tools"][0]["tool_id"] == "x"


class TestExecuteMapsExcluded:
    async def test_response_carries_excluded_tools(self):
        from src.domain.agent_run.value_objects import AgentRunEventType

        uc = _bare_run_uc()

        async def fake_stream(*a, **k):
            yield MagicMock(event_type=AgentRunEventType.ANSWER_COMPLETED, payload={
                "answer": "a", "tools_used": [],
                "excluded_tools": [{"tool_id": "internal:x", "name": "X", "reason": "no_permission"}],
            })

        uc.stream = fake_stream
        res = await uc.execute("ag1", _request(), "rid")
        assert [e.tool_id for e in res.excluded_tools] == ["internal:x"]

    async def test_response_defaults_to_empty(self):
        from src.domain.agent_run.value_objects import AgentRunEventType

        uc = _bare_run_uc()

        async def fake_stream(*a, **k):
            yield MagicMock(event_type=AgentRunEventType.ANSWER_COMPLETED,
                            payload={"answer": "a", "tools_used": []})

        uc.stream = fake_stream
        res = await uc.execute("ag1", _request(), "rid")
        assert res.excluded_tools == []


class TestDegradedPayload:
    def test_excluded_payload_reads_stream_state(self):
        # Check G-03: 정상·강등 답변이 같은 상태(state.excluded_workers)를 쓴다
        from src.application.agent_builder.run_agent_use_case import _StreamState

        state = _StreamState()
        assert RunAgentUseCase._excluded_payload(state) == []
        state.excluded_workers.append(
            WorkerDefinition(tool_id="python_code_executor", worker_id="code", description="")
        )
        assert RunAgentUseCase._excluded_payload(state) == [
            {"tool_id": "internal:python_code_executor", "name": "Python 코드 실행", "reason": "no_permission"}
        ]

    def test_degraded_path_passes_excluded_tools(self):
        import inspect

        src = inspect.getsource(RunAgentUseCase._degraded_completion_events)
        assert "excluded_tools=self._excluded_payload(state)" in src
