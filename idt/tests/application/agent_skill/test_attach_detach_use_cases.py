"""Application 테스트: Attach / Detach / List 부착 UseCase."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_skill.attach_skill_use_case import AttachSkillUseCase
from src.application.agent_skill.detach_skill_use_case import DetachSkillUseCase
from src.application.agent_skill.list_attached_skills_use_case import (
    ListAttachedSkillsUseCase,
)
from src.domain.agent_skill.schemas import AgentSkillLink
from src.domain.skill_builder.schemas import (
    SkillDefinition,
    SkillScriptType,
    SkillVisibility,
)


def _agent(owner="1", status="active", visibility="private", dept=None):
    return SimpleNamespace(
        id="agent-1", user_id=owner, status=status,
        visibility=visibility, department_id=dept,
    )


def _skill(owner="1", status="active", visibility=SkillVisibility.PRIVATE,
           script_type=SkillScriptType.NONE, dept=None):
    return SkillDefinition(
        id="skill-1", user_id=owner, name="환율", description="d",
        instruction="주입 지시문", trigger=None, script_type=script_type,
        script_content=None, status=status, visibility=visibility,
        department_id=dept, forked_from=None, forked_at=None,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


def _deps(agent=None, skill=None, existing_links=None):
    links = MagicMock()
    links.list_links = AsyncMock(return_value=existing_links or [])
    links.attach = AsyncMock(side_effect=lambda link, rid: link)
    links.detach = AsyncMock()
    links.list_attached_skills = AsyncMock(return_value=[skill] if skill else [])
    agents = MagicMock()
    agents.find_by_id = AsyncMock(return_value=agent)
    skills = MagicMock()
    skills.find_by_id = AsyncMock(return_value=skill)
    dept = MagicMock()
    dept.find_departments_by_user = AsyncMock(return_value=[])
    return links, agents, skills, dept


class TestAttach:
    @pytest.mark.asyncio
    async def test_attach_success_owner(self):
        links, agents, skills, dept = _deps(_agent(), _skill())
        uc = AttachSkillUseCase(links, agents, skills, dept, MagicMock())
        res = await uc.execute("agent-1", "skill-1", "req",
                               viewer_user_id="1", viewer_role="user")
        assert res.skill_id == "skill-1"
        assert res.sort_order == 0
        assert res.has_script is False
        links.attach.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_attach_agent_not_found(self):
        links, agents, skills, dept = _deps(None, _skill())
        uc = AttachSkillUseCase(links, agents, skills, dept, MagicMock())
        with pytest.raises(ValueError, match="에이전트를 찾을 수 없"):
            await uc.execute("agent-x", "skill-1", "req",
                             viewer_user_id="1", viewer_role="user")

    @pytest.mark.asyncio
    async def test_attach_no_edit_permission(self):
        links, agents, skills, dept = _deps(_agent(owner="2"), _skill())
        uc = AttachSkillUseCase(links, agents, skills, dept, MagicMock())
        with pytest.raises(PermissionError):
            await uc.execute("agent-1", "skill-1", "req",
                             viewer_user_id="1", viewer_role="user")

    @pytest.mark.asyncio
    async def test_attach_skill_deleted(self):
        links, agents, skills, dept = _deps(_agent(), _skill(status="deleted"))
        uc = AttachSkillUseCase(links, agents, skills, dept, MagicMock())
        with pytest.raises(ValueError, match="스킬을 찾을 수 없"):
            await uc.execute("agent-1", "skill-1", "req",
                             viewer_user_id="1", viewer_role="user")

    @pytest.mark.asyncio
    async def test_attach_skill_not_accessible(self):
        # 타인 소유 private skill → 접근 불가
        links, agents, skills, dept = _deps(
            _agent(), _skill(owner="2", visibility=SkillVisibility.PRIVATE)
        )
        uc = AttachSkillUseCase(links, agents, skills, dept, MagicMock())
        with pytest.raises(PermissionError, match="스킬에 접근"):
            await uc.execute("agent-1", "skill-1", "req",
                             viewer_user_id="1", viewer_role="user")

    @pytest.mark.asyncio
    async def test_attach_duplicate(self):
        existing = [AgentSkillLink(agent_id="agent-1", skill_id="skill-1")]
        links, agents, skills, dept = _deps(_agent(), _skill(), existing)
        uc = AttachSkillUseCase(links, agents, skills, dept, MagicMock())
        with pytest.raises(ValueError, match="이미 부착"):
            await uc.execute("agent-1", "skill-1", "req",
                             viewer_user_id="1", viewer_role="user")

    @pytest.mark.asyncio
    async def test_attach_max_exceeded(self):
        existing = [
            AgentSkillLink(agent_id="agent-1", skill_id=f"s{i}") for i in range(3)
        ]
        links, agents, skills, dept = _deps(_agent(), _skill(), existing)
        uc = AttachSkillUseCase(links, agents, skills, dept, MagicMock())
        with pytest.raises(ValueError, match="최대"):
            await uc.execute("agent-1", "skill-1", "req",
                             viewer_user_id="1", viewer_role="user")


class TestDetach:
    @pytest.mark.asyncio
    async def test_detach_calls_repo(self):
        links, agents, skills, dept = _deps(_agent(), _skill())
        uc = DetachSkillUseCase(links, agents, MagicMock())
        await uc.execute("agent-1", "skill-1", "req",
                         viewer_user_id="1", viewer_role="user")
        links.detach.assert_awaited_once_with("agent-1", "skill-1", "req")

    @pytest.mark.asyncio
    async def test_detach_permission(self):
        links, agents, skills, dept = _deps(_agent(owner="2"), _skill())
        uc = DetachSkillUseCase(links, agents, MagicMock())
        with pytest.raises(PermissionError):
            await uc.execute("agent-1", "skill-1", "req",
                             viewer_user_id="1", viewer_role="user")

    @pytest.mark.asyncio
    async def test_detach_admin_allowed(self):
        links, agents, skills, dept = _deps(_agent(owner="2"), _skill())
        uc = DetachSkillUseCase(links, agents, MagicMock())
        await uc.execute("agent-1", "skill-1", "req",
                         viewer_user_id="9", viewer_role="admin")
        links.detach.assert_awaited_once()


class TestList:
    @pytest.mark.asyncio
    async def test_list_returns_items_with_max(self):
        links, agents, skills, dept = _deps(_agent(), _skill())
        uc = ListAttachedSkillsUseCase(links, agents, dept, MagicMock())
        res = await uc.execute("agent-1", "req",
                               viewer_user_id="1", viewer_role="user")
        assert res.total == 1
        assert res.max_attachable == 3
        assert res.skills[0].skill_id == "skill-1"
