"""Infrastructure 테스트: AgentSkillRepository (Mock AsyncSession)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.agent_skill.schemas import AgentSkillLink
from src.infrastructure.agent_skill.agent_skill_repository import (
    AgentSkillRepository,
    _to_link,
)
from src.infrastructure.persistence.models.agent_skill.models import AgentSkillModel


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_logger():
    return MagicMock()


def _link_model(skill_id="skill-1", order=0):
    m = MagicMock(spec=AgentSkillModel)
    m.id = "row-1"
    m.agent_id = "agent-1"
    m.skill_id = skill_id
    m.sort_order = order
    m.created_at = datetime(2026, 1, 1)
    return m


class TestToLink:
    def test_maps_model_to_link(self):
        link = _to_link(_link_model())
        assert link.agent_id == "agent-1"
        assert link.skill_id == "skill-1"
        assert link.sort_order == 0


class TestAttach:
    @pytest.mark.asyncio
    async def test_attach_saves_and_returns_link(self, mock_session, mock_logger):
        repo = AgentSkillRepository(session=mock_session, logger=mock_logger)
        with patch.object(repo, "_base_save", new_callable=AsyncMock) as base:
            base.return_value = _link_model()
            result = await repo.attach(
                AgentSkillLink(agent_id="agent-1", skill_id="skill-1",
                               sort_order=0, created_at=datetime(2026, 1, 1)),
                "req-1",
            )
        assert isinstance(result, AgentSkillLink)
        assert result.skill_id == "skill-1"
        base.assert_called_once()


class TestDetach:
    @pytest.mark.asyncio
    async def test_detach_executes_delete_and_flush(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock()
        mock_session.flush = AsyncMock()
        repo = AgentSkillRepository(session=mock_session, logger=mock_logger)
        await repo.detach("agent-1", "skill-1", "req-1")
        mock_session.execute.assert_awaited_once()
        mock_session.flush.assert_awaited_once()


class TestListLinks:
    @pytest.mark.asyncio
    async def test_list_links_maps_results(self, mock_session, mock_logger):
        scalars = MagicMock()
        scalars.all.return_value = [_link_model("skill-1", 0), _link_model("skill-2", 1)]
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars
        mock_session.execute = AsyncMock(return_value=exec_result)

        repo = AgentSkillRepository(session=mock_session, logger=mock_logger)
        links = await repo.list_links("agent-1", "req-1")
        assert [l.skill_id for l in links] == ["skill-1", "skill-2"]


class TestListAttachedSkills:
    @pytest.mark.asyncio
    async def test_returns_skill_entities_via_join(self, mock_session, mock_logger):
        from src.infrastructure.persistence.models.skill_builder.models import (
            SkillDefinitionModel,
        )
        sm = MagicMock(spec=SkillDefinitionModel)
        sm.id = "skill-1"
        sm.user_id = "user-1"
        sm.name = "환율"
        sm.description = "d"
        sm.instruction = "주입 지시문"
        sm.trigger = None
        sm.script_type = "none"
        sm.script_content = None
        sm.status = "active"
        sm.visibility = "private"
        sm.department_id = None
        sm.forked_from = None
        sm.forked_at = None
        sm.created_at = datetime(2026, 1, 1)
        sm.updated_at = datetime(2026, 1, 1)

        scalars = MagicMock()
        scalars.all.return_value = [sm]
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars
        mock_session.execute = AsyncMock(return_value=exec_result)

        repo = AgentSkillRepository(session=mock_session, logger=mock_logger)
        skills = await repo.list_attached_skills("agent-1", "req-1")
        assert len(skills) == 1
        assert skills[0].instruction == "주입 지시문"
