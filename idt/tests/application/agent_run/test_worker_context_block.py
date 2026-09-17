"""render_worker_context_block 테스트.

Design Ref: worker-context-injection §4.1 / §8.2 L1 #8~10 —
워커 react agent가 자신이 속한 에이전트와 역할을 알도록 하는 블록.
"""
import pytest


class TestRenderWorkerContextBlock:

    def test_includes_all_sections_when_fully_wired(self):
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block(
            agent_prompt="당신은 금융 리서치 에이전트입니다.",
            worker_description="웹 페이지를 스크래핑해 원문을 수집한다",
            tool_names=["scrape_fetch", "scrape_search"],
        )
        assert "[에이전트 지침]" in block
        assert "당신은 금융 리서치 에이전트입니다." in block
        assert "[당신의 역할]" in block
        assert "웹 페이지를 스크래핑해 원문을 수집한다" in block
        assert "[사용 가능한 도구]" in block
        assert "scrape_fetch" in block
        assert "scrape_search" in block
        assert "[도구 사용 규범]" in block

    def test_ends_with_separator(self):
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block("프롬프트", "역할", ["t1"])
        assert block.endswith("\n---\n\n")

    def test_truncates_long_agent_prompt(self):
        from src.application.agent_run.prompt_rendering import (
            MAX_AGENT_PROMPT_CHARS,
            render_worker_context_block,
        )
        long_prompt = "가" * (MAX_AGENT_PROMPT_CHARS + 500)
        block = render_worker_context_block(long_prompt, "역할", ["t1"])
        assert "생략" in block
        # 전문이 그대로 들어가지 않았고, 상한만큼만 실렸다.
        assert long_prompt not in block
        assert "가" * MAX_AGENT_PROMPT_CHARS in block
        assert "가" * (MAX_AGENT_PROMPT_CHARS + 1) not in block

    def test_does_not_truncate_prompt_within_limit(self):
        from src.application.agent_run.prompt_rendering import (
            MAX_AGENT_PROMPT_CHARS,
            render_worker_context_block,
        )
        prompt = "나" * (MAX_AGENT_PROMPT_CHARS - 1)
        block = render_worker_context_block(prompt, "역할", ["t1"])
        assert "생략" not in block

    def test_omits_agent_section_when_prompt_empty(self):
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block("", "역할", ["t1"])
        assert "[에이전트 지침]" not in block
        assert "[당신의 역할]" in block

    def test_omits_role_section_when_description_empty(self):
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block("프롬프트", "", ["t1"])
        assert "[당신의 역할]" not in block
        assert "[에이전트 지침]" in block

    def test_omits_tool_section_when_no_tools(self):
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block("프롬프트", "역할", [])
        assert "[사용 가능한 도구]" not in block

    def test_always_includes_tool_usage_norm(self):
        """§4.1 — 소프트 가드는 다른 입력이 비어도 항상 포함된다."""
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block("", "", [])
        assert "[도구 사용 규범]" in block
        assert "추측" in block

    @pytest.mark.parametrize("prompt,desc", [
        ("   ", "  "),
        (None, None),
    ])
    def test_handles_blank_and_none_inputs(self, prompt, desc):
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block(prompt, desc, None)
        assert "[도구 사용 규범]" in block
        assert "[에이전트 지침]" not in block


class TestToolNormToggle:
    """GAP-01 — 도구가 없는 노드(analysis 등)는 도구 규범이 불필요하다."""

    def test_omits_tool_norm_when_disabled(self):
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block(
            "프롬프트", "역할", [], include_tool_norm=False,
        )
        assert "[도구 사용 규범]" not in block
        assert "[에이전트 지침]" in block
        assert "[당신의 역할]" in block

    def test_includes_tool_norm_by_default(self):
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block("프롬프트", "역할", [])
        assert "[도구 사용 규범]" in block

    def test_returns_empty_when_norm_disabled_and_inputs_blank(self):
        """규범도 없고 내용도 없으면 빈 문자열 — 기존 동작 보존."""
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        assert render_worker_context_block("", "", [], include_tool_norm=False) == ""


class TestCapabilityDenialNorm:
    """Design Ref: supervisor-early-finish-fix §1.2 D-08 / Plan SC: FR-01.

    워커는 자기 도구 하나만 바인딩된다(1 tool = 1 worker). 그 범위를 에이전트
    전체 능력으로 착각해 '그 기능은 제공되지 않습니다'라고 단언하면, 그 문장이
    supervisor 결정 컨텍스트에 남아 조기 FINISH를 유발한다 (트레이스 01a0a82b).
    """

    def test_norm_forbids_denying_agent_wide_capability(self):
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block("", "", [])
        assert "범위 밖" in block
        assert "다른 워커" in block

    def test_denial_norm_is_part_of_tool_usage_norm(self):
        """규범 토글을 끄면 함께 빠진다 — 도구 없는 노드는 대상이 아니다."""
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block(
            "프롬프트", "역할", [], include_tool_norm=False,
        )
        assert "범위 밖" not in block

    def test_norm_mandates_passing_tool_results_through(self):
        """회귀(트레이스 01a0ae68): 워커가 도구 결과를 전달하지 않고
        '이 워커의 범위 밖입니다'만 반환해 supervisor가 도구 실패로 오인했다.
        전달 의무가 범위 밖 표기보다 먼저 와야 한다.
        """
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block("", "", [])
        assert "빠짐없이 답변에 그대로 실으세요" in block
        # 전달 지시가 '범위 밖' 표기 지시보다 앞에 온다.
        assert (
            block.index("빠짐없이 답변에 그대로 실으세요")
            < block.index("'이 워커의 범위 밖'이라고 덧붙이세요")
        )

    def test_norm_avoids_absolute_only_framing(self):
        """'A라고만 하라'는 절대 프레이밍이 전달 의무를 덮어쓴다 — 금지."""
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block("", "", [])
        assert "범위 밖'이라고만" not in block

    def test_norm_does_not_enumerate_capabilities(self):
        """그래프 계약 ② — 목록 프레이밍 금지. 할 수 있는 것을 나열하지 않는다."""
        from src.application.agent_run.prompt_rendering import (
            render_worker_context_block,
        )
        block = render_worker_context_block("", "", [])
        for forbidden in ("browser_click", "browser_open", "scrape_url"):
            assert forbidden not in block
