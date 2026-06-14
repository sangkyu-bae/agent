"""supervisor 시각화 의도 결정적 라우팅 테스트 (supervisor-viz-routing).

설계: docs/02-design/features/supervisor-viz-routing.design.md
- TC-1~7: AttachmentRoutingHooks — viz 의도 + 검색결과 기반 분석 워커 강제
- TC-8: supervisor_node 통합 (LLM이 FINISH 해도 강제 라우팅)
- TC-9~11: [시각화 안내] prompt 블록 삽입 조건
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from src.application.agent_builder.search_pipeline import format_search_result
from src.application.agent_builder.supervisor_hooks import AttachmentRoutingHooks
from src.application.agent_builder.supervisor_nodes import (
    _render_viz_guidance_block,
    create_supervisor_node,
)
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.visualization.policies import VisualizationRoutingPolicy

VIZ_QUESTION = "2026년 평균기온 그래프 그려줘"
PLAIN_QUESTION = "2026년 평균기온 알려줘"


def _search_msg(worker_id: str = "search_w") -> AIMessage:
    return AIMessage(
        name=worker_id,
        content=format_search_result(worker_id, "2026년 기온 데이터: 1월 -2도 ..."),
    )


def _make_state(**overrides) -> dict:
    base = {
        "messages": [{"role": "user", "content": VIZ_QUESTION}],
        "iteration_count": 0,
        "max_iterations": 10,
        "token_usage": 0,
        "token_limit": 8000,
        "next_worker": "",
        "last_worker_id": "",
        "available_workers": ["search_w", "data_analysis"],
        "quality_gate_enabled": False,
        "retry_counts": {},
        "max_retries_per_worker": 2,
        "forced_worker": "",
        "skipped_workers": [],
        "quality_gate_result": "",
        "attachments": [],
        "viz_decision": "",
        "charts": [],
        "visualization_done": False,
    }
    base.update(overrides)
    return base


def _hooks() -> AttachmentRoutingHooks:
    return AttachmentRoutingHooks(
        ["data_analysis"], viz_policy=VisualizationRoutingPolicy()
    )


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


def _workers() -> list[WorkerDefinition]:
    return [
        WorkerDefinition("search_w", "web_search", "웹 검색", 0),
        WorkerDefinition("data_analysis", "data_analysis", "데이터 분석", 1),
    ]


# ── TC-1~7: AttachmentRoutingHooks viz 강제 조건 ─────────────────────────


class TestVizIntentForceWorker:
    def test_tc1_forces_analysis_on_viz_intent_with_search_results(self):
        state = _make_state(
            messages=[
                {"role": "user", "content": VIZ_QUESTION},
                _search_msg(),
            ],
        )
        assert _hooks().force_worker(state) == "data_analysis"

    def test_tc2_no_force_without_viz_intent(self):
        state = _make_state(
            messages=[
                {"role": "user", "content": PLAIN_QUESTION},
                _search_msg(),
            ],
        )
        assert _hooks().force_worker(state) is None

    def test_tc3_no_force_without_search_results(self):
        """D3: 검색 결과가 없으면 Hook 침묵 (prompt 유도만)."""
        state = _make_state(
            messages=[{"role": "user", "content": VIZ_QUESTION}],
        )
        assert _hooks().force_worker(state) is None

    def test_tc4_no_force_after_analysis_ran(self):
        state = _make_state(
            messages=[
                {"role": "user", "content": VIZ_QUESTION},
                _search_msg(),
            ],
            last_worker_id="data_analysis",
        )
        assert _hooks().force_worker(state) is None

    def test_tc5_no_force_when_visualization_done(self):
        state = _make_state(
            messages=[
                {"role": "user", "content": VIZ_QUESTION},
                _search_msg(),
            ],
            last_worker_id="search_w",
            visualization_done=True,
        )
        assert _hooks().force_worker(state) is None

    def test_tc6_no_force_without_viz_policy(self):
        """viz_policy 미주입(하위호환) 시 기존 동작 — 엑셀 첨부만 강제."""
        hooks = AttachmentRoutingHooks(["data_analysis"])
        state = _make_state(
            messages=[
                {"role": "user", "content": VIZ_QUESTION},
                _search_msg(),
            ],
        )
        assert hooks.force_worker(state) is None

    def test_tc7_no_excel_force_when_visualization_done(self):
        """공통 가드: 시각화 완료 후엔 엑셀 첨부 강제도 발동하지 않는다."""
        state = _make_state(
            attachments=[{"type": "excel"}],
            last_worker_id="search_w",
            visualization_done=True,
        )
        assert _hooks().force_worker(state) is None

    def test_excel_force_preserved(self):
        """회귀: 엑셀 첨부 강제(기존 동작)는 viz_policy 주입 후에도 유지."""
        state = _make_state(attachments=[{"type": "excel"}])
        assert _hooks().force_worker(state) == "data_analysis"


# ── TC-8: supervisor_node 통합 — LLM FINISH 무시하고 강제 ────────────────


class TestSupervisorVizForceRouting:
    @pytest.mark.asyncio
    async def test_tc8_force_skips_llm_and_routes_to_analysis(self):
        mock_llm = _llm_returning("FINISH", answer="검색 결과를 알려드렸습니다")
        fn = create_supervisor_node(
            llm=mock_llm,
            workers=_workers(),
            supervisor_prompt="P",
            hooks=_hooks(),
            logger=MagicMock(),
            analysis_worker_ids=["data_analysis"],
            viz_policy=VisualizationRoutingPolicy(),
        )
        state = _make_state(
            messages=[
                {"role": "user", "content": VIZ_QUESTION},
                _search_msg(),
            ],
            last_worker_id="search_w",
        )
        result = await fn(state)
        assert result["next_worker"] == "data_analysis"
        assert result["forced_worker"] == "data_analysis"
        mock_llm.with_structured_output.assert_not_called()


# ── TC-9~11: [시각화 안내] prompt 블록 ───────────────────────────────────


class TestVizGuidanceBlock:
    def test_block_rendered_on_viz_intent(self):
        block = _render_viz_guidance_block(
            [{"role": "user", "content": VIZ_QUESTION}],
            ["data_analysis"],
            VisualizationRoutingPolicy(),
        )
        assert "[시각화 안내]" in block
        assert "data_analysis" in block
        assert "FINISH 하지 마세요" in block

    def test_blank_without_viz_intent(self):
        block = _render_viz_guidance_block(
            [{"role": "user", "content": PLAIN_QUESTION}],
            ["data_analysis"],
            VisualizationRoutingPolicy(),
        )
        assert block == ""

    def test_blank_without_analysis_workers_or_policy(self):
        msgs = [{"role": "user", "content": VIZ_QUESTION}]
        assert _render_viz_guidance_block(msgs, [], VisualizationRoutingPolicy()) == ""
        assert _render_viz_guidance_block(msgs, ["data_analysis"], None) == ""

    @pytest.mark.asyncio
    async def test_tc9_prompt_includes_block_on_viz_intent(self):
        mock_llm = _llm_returning("search_w")
        fn = create_supervisor_node(
            llm=mock_llm,
            workers=_workers(),
            supervisor_prompt="P",
            hooks=_hooks(),
            logger=MagicMock(),
            analysis_worker_ids=["data_analysis"],
            viz_policy=VisualizationRoutingPolicy(),
        )
        # 검색결과 없음 → Hook 침묵 → LLM 경로에서 블록 확인 (D3 시나리오)
        state = _make_state(
            messages=[{"role": "user", "content": VIZ_QUESTION}],
        )
        await fn(state)

        ainvoke = mock_llm.with_structured_output.return_value.ainvoke
        sent_messages = ainvoke.call_args.args[0]
        joined = " ".join(
            m["content"] for m in sent_messages if m.get("role") == "system"
        )
        assert "[시각화 안내]" in joined
        assert "분석 워커" in joined

    @pytest.mark.asyncio
    async def test_tc10_no_block_without_viz_intent(self):
        mock_llm = _llm_returning("FINISH", answer="안녕하세요")
        fn = create_supervisor_node(
            llm=mock_llm,
            workers=_workers(),
            supervisor_prompt="P",
            hooks=_hooks(),
            logger=MagicMock(),
            analysis_worker_ids=["data_analysis"],
            viz_policy=VisualizationRoutingPolicy(),
        )
        state = _make_state(
            messages=[{"role": "user", "content": PLAIN_QUESTION}],
        )
        result = await fn(state)

        assert result["next_worker"] == "__end__"  # 정상 FINISH 보존
        ainvoke = mock_llm.with_structured_output.return_value.ainvoke
        sent_messages = ainvoke.call_args.args[0]
        joined = " ".join(
            m["content"] for m in sent_messages if m.get("role") == "system"
        )
        assert "[시각화 안내]" not in joined

    @pytest.mark.asyncio
    async def test_tc11_legacy_call_without_new_params(self):
        """기존 호출 형태(신규 파라미터 미전달)는 블록 미삽입 + 동작 불변."""
        mock_llm = _llm_returning("FINISH", answer="답변")
        fn = create_supervisor_node(
            llm=mock_llm,
            workers=_workers(),
            supervisor_prompt="P",
            hooks=_hooks(),
            logger=MagicMock(),
        )
        state = _make_state(
            messages=[{"role": "user", "content": VIZ_QUESTION}],
        )
        result = await fn(state)

        assert result["next_worker"] == "__end__"
        ainvoke = mock_llm.with_structured_output.return_value.ainvoke
        sent_messages = ainvoke.call_args.args[0]
        joined = " ".join(
            m["content"] for m in sent_messages if m.get("role") == "system"
        )
        assert "[시각화 안내]" not in joined
