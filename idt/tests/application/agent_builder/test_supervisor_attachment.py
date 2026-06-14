"""supervisor 첨부 인지 + 결정적 라우팅 테스트 (SUP-ATTACH-001).

설계: docs/02-design/features/supervisor-attachment-routing.design.md
- C-1: _render_attachment_block + supervisor_node prompt 첨부 인지/거부 억제
- C-2: AttachmentRoutingHooks (엑셀 첨부 시 analysis 워커 강제 라우팅)
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.supervisor_hooks import (
    AttachmentRoutingHooks,
    DefaultHooks,
)
from src.application.agent_builder.supervisor_nodes import (
    _render_attachment_block,
    create_supervisor_node,
)
from src.domain.agent_builder.schemas import WorkerDefinition


def _make_state(**overrides) -> dict:
    base = {
        "messages": [{"role": "user", "content": "분석해줘"}],
        "iteration_count": 0,
        "max_iterations": 10,
        "token_usage": 0,
        "token_limit": 8000,
        "next_worker": "",
        "last_worker_id": "",
        "available_workers": ["data_analysis"],
        "quality_gate_enabled": False,
        "retry_counts": {},
        "max_retries_per_worker": 2,
        "forced_worker": "",
        "skipped_workers": [],
        "quality_gate_result": "",
        "attachments": [],
        "viz_decision": "",
    }
    base.update(overrides)
    return base


def _analysis_worker() -> WorkerDefinition:
    return WorkerDefinition("data_analysis", "data_analysis", "데이터 분석", 0)


def _llm_returning(next_: str, answer: str = "", reasoning: str = "r"):
    """with_structured_output().ainvoke가 지정 decision을 반환하는 MagicMock LLM."""
    mock_llm = MagicMock()
    decision = MagicMock()
    decision.next = next_
    decision.answer = answer
    decision.reasoning = reasoning
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=decision
    )
    return mock_llm


# ── TC-1: _render_attachment_block ──────────────────────────────────────


class TestRenderAttachmentBlock:
    def test_with_excel_filename(self):
        block = _render_attachment_block([{"type": "excel", "file_name": "vac.xlsx"}])
        assert "[첨부된 데이터]" in block
        assert "excel(vac.xlsx)" in block
        assert "거부하지 말고" in block

    def test_empty_returns_blank(self):
        assert _render_attachment_block([]) == ""
        assert _render_attachment_block(None) == ""

    def test_no_filename_hides_path(self):
        block = _render_attachment_block(
            [{"type": "excel", "file_path": "/tmp/secret.xlsx"}]
        )
        assert "/tmp/secret.xlsx" not in block  # 임시경로 비노출
        assert "excel" in block


# ── TC-2: AttachmentRoutingHooks ────────────────────────────────────────


class TestAttachmentRoutingHooks:
    def test_forces_analysis_on_excel(self):
        hooks = AttachmentRoutingHooks(["data_analysis"])
        state = _make_state(attachments=[{"type": "excel"}], last_worker_id="")
        assert hooks.force_worker(state) == "data_analysis"

    def test_no_force_after_analysis_ran(self):
        hooks = AttachmentRoutingHooks(["data_analysis"])
        state = _make_state(
            attachments=[{"type": "excel"}], last_worker_id="data_analysis"
        )
        assert hooks.force_worker(state) is None

    def test_no_force_without_routable_attachment(self):
        hooks = AttachmentRoutingHooks(["data_analysis"])
        assert hooks.force_worker(_make_state(attachments=[])) is None
        assert (
            hooks.force_worker(_make_state(attachments=[{"type": "image"}])) is None
        )

    def test_no_force_when_no_analysis_worker(self):
        hooks = AttachmentRoutingHooks([])
        state = _make_state(attachments=[{"type": "excel"}])
        assert hooks.force_worker(state) is None

    def test_skip_workers_empty(self):
        hooks = AttachmentRoutingHooks(["data_analysis"])
        assert hooks.skip_workers(_make_state()) == []

    def test_skip_workers_includes_analysis_when_visualization_done(self):
        # supervisor-chart-builder-node: 시각화 완료 후 분석워커 재라우팅 차단.
        hooks = AttachmentRoutingHooks(["data_analysis"])
        state = _make_state(visualization_done=True)
        assert hooks.skip_workers(state) == ["data_analysis"]

    def test_skip_workers_empty_when_not_visualization_done(self):
        hooks = AttachmentRoutingHooks(["data_analysis"])
        assert hooks.skip_workers(_make_state(visualization_done=False)) == []


# ── TC-3: supervisor_node force → LLM 우회 ──────────────────────────────


class TestSupervisorForceRouting:
    @pytest.mark.asyncio
    async def test_force_skips_llm_and_routes(self):
        """엑셀 첨부 시 LLM이 거부(FINISH)하려 해도 analysis 워커로 강제 라우팅."""
        mock_llm = _llm_returning("FINISH", answer="권한이 없습니다")
        fn = create_supervisor_node(
            llm=mock_llm,
            workers=[_analysis_worker()],
            supervisor_prompt="P",
            hooks=AttachmentRoutingHooks(["data_analysis"]),
            logger=MagicMock(),
        )
        state = _make_state(
            attachments=[{"type": "excel", "file_path": "/tmp/x.xlsx"}],
            last_worker_id="",
        )
        result = await fn(state)
        assert result["next_worker"] == "data_analysis"
        assert result["forced_worker"] == "data_analysis"
        mock_llm.with_structured_output.assert_not_called()


# ── TC-4: supervisor_node prompt 첨부 인지 ──────────────────────────────


class TestSupervisorAttachmentPrompt:
    @pytest.mark.asyncio
    async def test_includes_attachment_block_in_prompt(self):
        """DefaultHooks(강제 없음) 경로에서 prompt에 첨부 인지 블록이 들어간다."""
        mock_llm = _llm_returning("data_analysis")
        fn = create_supervisor_node(
            llm=mock_llm,
            workers=[_analysis_worker()],
            supervisor_prompt="P",
            hooks=DefaultHooks(),
            logger=MagicMock(),
        )
        state = _make_state(
            attachments=[{"type": "excel", "file_name": "v.xlsx"}],
        )
        await fn(state)

        ainvoke = mock_llm.with_structured_output.return_value.ainvoke
        sent_messages = ainvoke.call_args.args[0]
        joined = " ".join(
            m["content"] for m in sent_messages if m.get("role") == "system"
        )
        assert "[첨부된 데이터]" in joined
        assert "거부하지 말고" in joined


# ── TC-5: 첨부 없을 때 기존 동작 보존 ───────────────────────────────────


class TestNoAttachmentRegression:
    @pytest.mark.asyncio
    async def test_no_attachment_behaves_as_before(self):
        mock_llm = _llm_returning("FINISH", answer="안녕하세요")
        fn = create_supervisor_node(
            llm=mock_llm,
            workers=[_analysis_worker()],
            supervisor_prompt="P",
            hooks=AttachmentRoutingHooks(["data_analysis"]),
            logger=MagicMock(),
        )
        state = _make_state(attachments=None, messages=[{"role": "user", "content": "안녕"}])
        result = await fn(state)

        assert result["next_worker"] == "__end__"  # 정상 FINISH 보존
        ainvoke = mock_llm.with_structured_output.return_value.ainvoke
        sent_messages = ainvoke.call_args.args[0]
        joined = " ".join(
            m["content"] for m in sent_messages if m.get("role") == "system"
        )
        assert "[첨부된 데이터]" not in joined  # 블록 미삽입
