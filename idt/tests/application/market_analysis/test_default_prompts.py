"""기본 지침 — 길이 상한·필수 문구·판단 역할 JSON 형식·도구 (design §7)."""

import pytest
from src.application.market_analysis.default_prompts import (
    ROLE_NAMES,
    ROLE_PROMPTS,
    ROLE_TOKEN_LIMITS,
    ROLE_TOOLS,
)
from src.domain.market_analysis.runtime import ToolSource
from src.domain.market_analysis.tool_policy import ToolPolicy
from src.domain.market_analysis.value_objects import AgentRole

# AgentBuilderPolicy.MAX_SYSTEM_PROMPT_LENGTH
# (스키마 8000 과 어긋남 — Design O5, 보고만 함)
PROMPT_MAX = 4000


def test_every_role_has_prompt_name_tools_and_budget():
    for role in AgentRole:
        assert role in ROLE_PROMPTS and role in ROLE_NAMES and role in ROLE_TOOLS
        assert 8000 <= ROLE_TOKEN_LIMITS[role] <= 500_000


@pytest.mark.parametrize("role", list(AgentRole))
def test_prompt_rules(role):
    prompt = ROLE_PROMPTS[role]
    assert len(prompt) <= PROMPT_MAX, (role, len(prompt))
    assert "투자 권유" in prompt
    assert "데이터 없음" in prompt or role is AgentRole.JOURNAL
    assert "지시" in prompt  # 참고 자료 안의 지시는 따르지 않는다


@pytest.mark.parametrize(
    ("role", "fields"),
    [
        (
            AgentRole.BUY_JUDGE,
            [
                "score",
                "decision",
                "target_price",
                "stop_loss",
                "investment_period",
                "rationale",
                "skip_reason",
            ],
        ),
        (
            AgentRole.SELL_JUDGE,
            ["action", "new_target_price", "new_stop_loss", "confidence", "reason"],
        ),
        (
            AgentRole.JOURNAL,
            [
                "one_line",
                "situation",
                "evaluation",
                "lessons",
                "tags",
                "principle_candidates",
            ],
        ),
    ],
)
def test_judgement_roles_specify_json(role, fields):
    prompt = ROLE_PROMPTS[role]
    assert "```json" in prompt
    for field in fields:
        assert f'"{field}"' in prompt, field


def test_section_prompts_mention_provisional_bars():
    for role in AgentRole.section_roles():
        assert "미확정" in ROLE_PROMPTS[role]


def test_tools_are_inside_the_allowlist_and_never_order():
    for role, tools in ROLE_TOOLS.items():
        for source, tool in tools:
            assert tool not in {"place_order", "cancel_order"}
            if source is not ToolSource.TAVILY:
                ToolPolicy.check(source, tool)
