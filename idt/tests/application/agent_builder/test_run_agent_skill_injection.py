"""Application 테스트: RunAgentUseCase 부착 Skill instruction 주입 (Phase A)."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.domain.agent_builder.schemas import WorkflowDefinition
from src.domain.skill_builder.schemas import (
    SkillDefinition,
    SkillScriptType,
    SkillVisibility,
)


def _skill(name="환율", instruction="환율 변환 절차", script_type=SkillScriptType.PYTHON):
    return SkillDefinition(
        id="skill-1", user_id="1", name=name, description="d",
        instruction=instruction, trigger=None, script_type=script_type,
        script_content="print(1)" if script_type != SkillScriptType.NONE else None,
        status="active", visibility=SkillVisibility.PRIVATE, department_id=None,
        forked_from=None, forked_at=None,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


def _make_uc(agent_skill_repo=None) -> RunAgentUseCase:
    return RunAgentUseCase(
        repository=MagicMock(),
        llm_model_repository=MagicMock(),
        compiler=MagicMock(),
        logger=MagicMock(),
        message_repo=MagicMock(),
        summary_repo=MagicMock(),
        summarizer=MagicMock(),
        policy=MagicMock(),
        agent_skill_repo=agent_skill_repo,
    )


def _workflow():
    return WorkflowDefinition(
        supervisor_prompt="원본 시스템 프롬프트", workers=[], flow_hint="",
    )


_AGENT = SimpleNamespace(id="agent-1", name="A")


class TestInjectAttachedSkills:
    @pytest.mark.asyncio
    async def test_no_repo_returns_unchanged(self):
        uc = _make_uc(agent_skill_repo=None)
        wf = _workflow()
        result = await uc._inject_attached_skills(wf, _AGENT, "req")
        assert result is wf
        assert result.supervisor_prompt == "원본 시스템 프롬프트"

    @pytest.mark.asyncio
    async def test_empty_attached_returns_unchanged(self):
        repo = MagicMock()
        repo.list_attached_skills = AsyncMock(return_value=[])
        uc = _make_uc(agent_skill_repo=repo)
        wf = _workflow()
        result = await uc._inject_attached_skills(wf, _AGENT, "req")
        assert result.supervisor_prompt == "원본 시스템 프롬프트"

    @pytest.mark.asyncio
    async def test_injects_instruction_before_base_prompt(self):
        repo = MagicMock()
        repo.list_attached_skills = AsyncMock(return_value=[_skill()])
        uc = _make_uc(agent_skill_repo=repo)
        wf = _workflow()
        result = await uc._inject_attached_skills(wf, _AGENT, "req")
        # 새 객체 — 원본 불변
        assert wf.supervisor_prompt == "원본 시스템 프롬프트"
        # 주입된 instruction이 base prompt 앞에 위치
        assert "환율 변환 절차" in result.supervisor_prompt
        assert result.supervisor_prompt.endswith("원본 시스템 프롬프트")
        assert "[부착된 스킬: 환율]" in result.supervisor_prompt

    @pytest.mark.asyncio
    async def test_script_skill_injects_instruction_only(self):
        """script를 가진 Skill도 instruction만 주입 — script_content는 프롬프트에 없음."""
        repo = MagicMock()
        repo.list_attached_skills = AsyncMock(
            return_value=[_skill(script_type=SkillScriptType.PYTHON)]
        )
        uc = _make_uc(agent_skill_repo=repo)
        result = await uc._inject_attached_skills(_workflow(), _AGENT, "req")
        assert "환율 변환 절차" in result.supervisor_prompt
        assert "print(1)" not in result.supervisor_prompt
