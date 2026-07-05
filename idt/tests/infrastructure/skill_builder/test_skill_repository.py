"""Infrastructure 테스트: SkillRepository (Mock AsyncSession)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.skill_builder.schemas import (
    SkillDefinition,
    SkillScriptType,
    SkillVisibility,
)
from src.infrastructure.persistence.models.skill_builder.models import (
    SkillDefinitionModel,
)
from src.infrastructure.skill_builder.skill_repository import (
    SkillRepository,
    _to_entity,
    _to_model,
)


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_logger():
    return MagicMock()


def _entity(**overrides) -> SkillDefinition:
    base = dict(
        id="skill-1",
        user_id="user-1",
        name="환율 계산기",
        description="설명",
        instruction="지시문",
        trigger="환율",
        script_type=SkillScriptType.PYTHON,
        script_content="print(1)",
        status="active",
        visibility=SkillVisibility.PRIVATE,
        department_id=None,
        forked_from=None,
        forked_at=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    base.update(overrides)
    return SkillDefinition(**base)


def _model_from(entity: SkillDefinition) -> SkillDefinitionModel:
    """매핑 검증을 위해 spec 모델을 구성."""
    m = MagicMock(spec=SkillDefinitionModel)
    m.id = entity.id
    m.user_id = entity.user_id
    m.name = entity.name
    m.description = entity.description
    m.trigger = entity.trigger
    m.instruction = entity.instruction
    m.script_type = entity.script_type.value
    m.script_content = entity.script_content
    m.status = entity.status
    m.visibility = entity.visibility.value
    m.department_id = entity.department_id
    m.forked_from = entity.forked_from
    m.forked_at = entity.forked_at
    m.created_at = entity.created_at
    m.updated_at = entity.updated_at
    return m


class TestMapping:
    def test_to_model_maps_trigger_and_enums(self):
        model = _to_model(_entity())
        assert model.trigger == "환율"
        assert model.script_type == "python"
        assert model.visibility == "private"

    def test_to_entity_roundtrip(self):
        entity = _entity()
        result = _to_entity(_model_from(entity))
        assert result.id == "skill-1"
        assert result.script_type == SkillScriptType.PYTHON
        assert result.visibility == SkillVisibility.PRIVATE


class TestSave:
    @pytest.mark.asyncio
    async def test_save_delegates_to_base(self, mock_session, mock_logger):
        repo = SkillRepository(session=mock_session, logger=mock_logger)
        with patch.object(repo, "_base_save", new_callable=AsyncMock) as base:
            base.return_value = _model_from(_entity())
            result = await repo.save(_entity(), "req-1")
        assert result.id == "skill-1"
        base.assert_called_once()


class TestFindById:
    @pytest.mark.asyncio
    async def test_find_by_id_returns_entity(self, mock_session, mock_logger):
        repo = SkillRepository(session=mock_session, logger=mock_logger)
        with patch.object(repo, "_base_find_by_id", new_callable=AsyncMock) as f:
            f.return_value = _model_from(_entity())
            result = await repo.find_by_id("skill-1", "req-1")
        assert result is not None
        assert result.name == "환율 계산기"

    @pytest.mark.asyncio
    async def test_find_by_id_returns_none(self, mock_session, mock_logger):
        repo = SkillRepository(session=mock_session, logger=mock_logger)
        with patch.object(repo, "_base_find_by_id", new_callable=AsyncMock) as f:
            f.return_value = None
            result = await repo.find_by_id("nope", "req-1")
        assert result is None


class TestSoftDelete:
    @pytest.mark.asyncio
    async def test_soft_delete_sets_status_and_saves(self, mock_session, mock_logger):
        repo = SkillRepository(session=mock_session, logger=mock_logger)
        model = _model_from(_entity())
        with patch.object(repo, "_base_find_by_id", new_callable=AsyncMock) as f, \
                patch.object(repo, "_base_save", new_callable=AsyncMock) as s:
            f.return_value = model
            await repo.soft_delete("skill-1", "req-1")
        assert model.status == "deleted"
        s.assert_called_once()

    @pytest.mark.asyncio
    async def test_soft_delete_noop_when_missing(self, mock_session, mock_logger):
        repo = SkillRepository(session=mock_session, logger=mock_logger)
        with patch.object(repo, "_base_find_by_id", new_callable=AsyncMock) as f, \
                patch.object(repo, "_base_save", new_callable=AsyncMock) as s:
            f.return_value = None
            await repo.soft_delete("nope", "req-1")
        s.assert_not_called()


class TestListByUser:
    @pytest.mark.asyncio
    async def test_list_by_user_maps_results(self, mock_session, mock_logger):
        repo = SkillRepository(session=mock_session, logger=mock_logger)
        scalars = MagicMock()
        scalars.all.return_value = [_model_from(_entity())]
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars
        mock_session.execute = AsyncMock(return_value=exec_result)

        result = await repo.list_by_user("user-1", "req-1")
        assert len(result) == 1
        assert result[0].user_id == "user-1"
