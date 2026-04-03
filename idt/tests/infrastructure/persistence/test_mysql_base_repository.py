"""MySQLBaseRepository 단위 테스트 (AsyncSession mock 사용)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, call

from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.domain.mysql.schemas import MySQLPaginationParams, MySQLQueryCondition
from src.infrastructure.persistence.mysql_base_repository import MySQLBaseRepository


# ─────────────────────────────────────────────
# 테스트 전용 ORM 모델 (실제 DB 연결 없음)
# ─────────────────────────────────────────────

class _TestBase(DeclarativeBase):
    pass


class _ItemModel(_TestBase):
    __tablename__ = "test_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="active")


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def _make_repo(session=None, logger=None):
    session = session or AsyncMock()
    logger = logger or MagicMock()
    return MySQLBaseRepository(
        session=session,
        model_class=_ItemModel,
        logger=logger,
    ), session, logger


def _mock_execute_scalar_one_or_none(session, value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    session.execute = AsyncMock(return_value=result)


def _mock_execute_scalars_all(session, values: list):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    session.execute = AsyncMock(return_value=result)


def _mock_execute_scalar_one(session, value):
    result = MagicMock()
    result.scalar_one.return_value = value
    session.execute = AsyncMock(return_value=result)


def _mock_execute_rowcount(session, rowcount: int):
    result = MagicMock()
    result.rowcount = rowcount
    session.execute = AsyncMock(return_value=result)


# ─────────────────────────────────────────────
# save
# ─────────────────────────────────────────────

class TestSave:
    @pytest.mark.asyncio
    async def test_save_adds_and_returns_entity(self):
        entity = _ItemModel(id=1, name="test", status="active")
        repo, session, _ = _make_repo()
        returned = await repo.save(entity, "req-1")
        session.add.assert_called_once_with(entity)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(entity)
        assert returned is entity

    @pytest.mark.asyncio
    async def test_save_logs_start_and_completion(self):
        entity = _ItemModel(id=1, name="x")
        repo, _, logger = _make_repo()
        await repo.save(entity, "req-1")
        assert logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_save_logs_error_and_reraises(self):
        entity = _ItemModel(id=1, name="x")
        repo, session, logger = _make_repo()
        session.flush.side_effect = RuntimeError("DB 오류")
        with pytest.raises(RuntimeError):
            await repo.save(entity, "req-1")
        logger.error.assert_called_once()


# ─────────────────────────────────────────────
# find_by_id
# ─────────────────────────────────────────────

class TestFindById:
    @pytest.mark.asyncio
    async def test_returns_entity_when_found(self):
        entity = _ItemModel(id=1, name="found")
        repo, session, _ = _make_repo()
        _mock_execute_scalar_one_or_none(session, entity)
        result = await repo.find_by_id(1, "req-1")
        assert result is entity

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        repo, session, _ = _make_repo()
        _mock_execute_scalar_one_or_none(session, None)
        result = await repo.find_by_id(999, "req-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_logs_start_and_completion(self):
        repo, session, logger = _make_repo()
        _mock_execute_scalar_one_or_none(session, None)
        await repo.find_by_id(1, "req-1")
        assert logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_logs_error_and_reraises(self):
        repo, session, logger = _make_repo()
        session.execute = AsyncMock(side_effect=RuntimeError("DB 오류"))
        with pytest.raises(RuntimeError):
            await repo.find_by_id(1, "req-1")
        logger.error.assert_called_once()


# ─────────────────────────────────────────────
# find_all
# ─────────────────────────────────────────────

class TestFindAll:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        items = [_ItemModel(id=i, name=f"item{i}") for i in range(3)]
        repo, session, _ = _make_repo()
        _mock_execute_scalars_all(session, items)
        result = await repo.find_all("req-1")
        assert result == items

    @pytest.mark.asyncio
    async def test_uses_default_pagination(self):
        repo, session, _ = _make_repo()
        _mock_execute_scalars_all(session, [])
        await repo.find_all("req-1")
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_respects_custom_pagination(self):
        repo, session, _ = _make_repo()
        _mock_execute_scalars_all(session, [])
        await repo.find_all("req-1", pagination=MySQLPaginationParams(limit=5, offset=10))
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logs_error_and_reraises(self):
        repo, session, logger = _make_repo()
        session.execute = AsyncMock(side_effect=RuntimeError("DB 오류"))
        with pytest.raises(RuntimeError):
            await repo.find_all("req-1")
        logger.error.assert_called_once()


# ─────────────────────────────────────────────
# find_by_conditions
# ─────────────────────────────────────────────

class TestFindByConditions:
    @pytest.mark.asyncio
    async def test_returns_filtered_list(self):
        items = [_ItemModel(id=1, name="matched", status="active")]
        repo, session, _ = _make_repo()
        _mock_execute_scalars_all(session, items)
        cond = MySQLQueryCondition(field="status", operator="eq", value="active")
        result = await repo.find_by_conditions([cond], "req-1")
        assert result == items

    @pytest.mark.asyncio
    async def test_raises_on_unsupported_operator(self):
        repo, session, _ = _make_repo()
        cond = MySQLQueryCondition(field="name", operator="unsupported", value="x")
        with pytest.raises(ValueError, match="Unsupported operator"):
            await repo.find_by_conditions([cond], "req-1")

    @pytest.mark.asyncio
    async def test_like_operator(self):
        repo, session, _ = _make_repo()
        _mock_execute_scalars_all(session, [])
        cond = MySQLQueryCondition(field="name", operator="like", value="%test%")
        await repo.find_by_conditions([cond], "req-1")
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_in_operator(self):
        repo, session, _ = _make_repo()
        _mock_execute_scalars_all(session, [])
        cond = MySQLQueryCondition(field="status", operator="in", value=["a", "b"])
        await repo.find_by_conditions([cond], "req-1")
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logs_error_and_reraises(self):
        repo, session, logger = _make_repo()
        session.execute = AsyncMock(side_effect=RuntimeError("DB 오류"))
        cond = MySQLQueryCondition(field="status", operator="eq", value="x")
        with pytest.raises(RuntimeError):
            await repo.find_by_conditions([cond], "req-1")
        logger.error.assert_called_once()


# ─────────────────────────────────────────────
# delete
# ─────────────────────────────────────────────

class TestDelete:
    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self):
        repo, session, _ = _make_repo()
        _mock_execute_rowcount(session, 1)
        result = await repo.delete(1, "req-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        repo, session, _ = _make_repo()
        _mock_execute_rowcount(session, 0)
        result = await repo.delete(999, "req-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_flushes_after_delete(self):
        repo, session, _ = _make_repo()
        _mock_execute_rowcount(session, 1)
        await repo.delete(1, "req-1")
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logs_error_and_reraises(self):
        repo, session, logger = _make_repo()
        session.execute = AsyncMock(side_effect=RuntimeError("DB 오류"))
        with pytest.raises(RuntimeError):
            await repo.delete(1, "req-1")
        logger.error.assert_called_once()


# ─────────────────────────────────────────────
# count
# ─────────────────────────────────────────────

class TestCount:
    @pytest.mark.asyncio
    async def test_returns_count(self):
        repo, session, _ = _make_repo()
        _mock_execute_scalar_one(session, 7)
        result = await repo.count("req-1")
        assert result == 7

    @pytest.mark.asyncio
    async def test_logs_error_and_reraises(self):
        repo, session, logger = _make_repo()
        session.execute = AsyncMock(side_effect=RuntimeError("DB 오류"))
        with pytest.raises(RuntimeError):
            await repo.count("req-1")
        logger.error.assert_called_once()


# ─────────────────────────────────────────────
# exists
# ─────────────────────────────────────────────

class TestExists:
    @pytest.mark.asyncio
    async def test_returns_true_when_exists(self):
        repo, session, _ = _make_repo()
        _mock_execute_scalar_one(session, 1)
        result = await repo.exists(1, "req-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        repo, session, _ = _make_repo()
        _mock_execute_scalar_one(session, 0)
        result = await repo.exists(999, "req-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_logs_error_and_reraises(self):
        repo, session, logger = _make_repo()
        session.execute = AsyncMock(side_effect=RuntimeError("DB 오류"))
        with pytest.raises(RuntimeError):
            await repo.exists(1, "req-1")
        logger.error.assert_called_once()
