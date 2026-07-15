from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.department.entity import UserDepartment
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.policy import KnowledgeBasePolicy


def _user(user_id: int = 1, role: UserRole = UserRole.USER) -> User:
    return User(
        email="test@test.com",
        password_hash="hash",
        role=role,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _kb(
    kb_id: str = "kb-1",
    owner_id: int = 1,
    scope: CollectionScope = CollectionScope.PERSONAL,
    department_id: str | None = None,
) -> KnowledgeBase:
    return KnowledgeBase(
        id=kb_id,
        name="여신 규정집",
        owner_id=owner_id,
        scope=scope,
        department_id=department_id,
        collection_name="shared-col",
    )


@pytest.fixture
def mock_kb_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.exists_active_name.return_value = False
    repo.save.side_effect = lambda kb, request_id: kb
    return repo


@pytest.fixture
def mock_assigner() -> AsyncMock:
    assigner = AsyncMock()
    assigner.assign.return_value = "shared-col"
    return assigner


@pytest.fixture
def mock_dept_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_departments_by_user.return_value = []
    return repo


@pytest.fixture
def use_case(
    mock_kb_repo: AsyncMock,
    mock_assigner: AsyncMock,
    mock_dept_repo: AsyncMock,
) -> KnowledgeBaseUseCase:
    return KnowledgeBaseUseCase(
        kb_repo=mock_kb_repo,
        policy=KnowledgeBasePolicy(),
        assigner=mock_assigner,
        dept_repo=mock_dept_repo,
        logger=MagicMock(),
    )


class TestCreate:
    async def test_creates_with_uuid_kb_id(
        self, use_case, mock_kb_repo, mock_assigner
    ):
        kb = await use_case.create(
            user=_user(),
            name="여신 규정집",
            collection_name="shared-col",
            scope=CollectionScope.PERSONAL,
            department_id=None,
            description="설명",
            request_id="req-1",
        )
        assert kb.id is not None and len(kb.id) == 36
        assert kb.name == "여신 규정집"
        assert kb.owner_id == 1
        assert kb.collection_name == "shared-col"
        mock_assigner.assign.assert_awaited_once()
        mock_kb_repo.save.assert_awaited_once()

    async def test_duplicate_active_name_raises(self, use_case, mock_kb_repo):
        mock_kb_repo.exists_active_name.return_value = True
        with pytest.raises(ValueError, match="already exists"):
            await use_case.create(
                user=_user(),
                name="여신 규정집",
                collection_name="shared-col",
                scope=CollectionScope.PERSONAL,
                department_id=None,
                description=None,
                request_id="req-1",
            )

    async def test_invalid_name_raises(self, use_case):
        with pytest.raises(ValueError):
            await use_case.create(
                user=_user(),
                name="   ",
                collection_name="shared-col",
                scope=CollectionScope.PERSONAL,
                department_id=None,
                description=None,
                request_id="req-1",
            )

    async def test_department_scope_requires_membership(
        self, use_case, mock_dept_repo
    ):
        mock_dept_repo.find_departments_by_user.return_value = [
            UserDepartment(
                user_id=1, department_id="d1", is_primary=True,
                created_at=datetime.now(),
            )
        ]
        with pytest.raises(ValueError):
            await use_case.create(
                user=_user(),
                name="부서 지식",
                collection_name="shared-col",
                scope=CollectionScope.DEPARTMENT,
                department_id="d9",
                description=None,
                request_id="req-1",
            )

    async def test_assigner_error_propagates(self, use_case, mock_assigner):
        mock_assigner.assign.side_effect = ValueError("Collection 'x' not found")
        with pytest.raises(ValueError, match="not found"):
            await use_case.create(
                user=_user(),
                name="이름",
                collection_name="x",
                scope=CollectionScope.PERSONAL,
                department_id=None,
                description=None,
                request_id="req-1",
            )


class TestList:
    async def test_regular_user_gets_accessible_only(
        self, use_case, mock_kb_repo
    ):
        mock_kb_repo.find_accessible.return_value = [_kb()]
        result = await use_case.list(_user(), "req-1")
        assert len(result) == 1
        mock_kb_repo.find_accessible.assert_awaited_once()
        mock_kb_repo.find_all_active.assert_not_awaited()

    async def test_admin_gets_all_active(self, use_case, mock_kb_repo):
        mock_kb_repo.find_all_active.return_value = [_kb(), _kb(kb_id="kb-2")]
        result = await use_case.list(_user(role=UserRole.ADMIN), "req-1")
        assert len(result) == 2
        mock_kb_repo.find_all_active.assert_awaited_once()
        mock_kb_repo.find_accessible.assert_not_awaited()


class TestGet:
    async def test_not_found_raises(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await use_case.get("ghost", _user(), "req-1")

    async def test_personal_other_user_raises_permission_error(
        self, use_case, mock_kb_repo
    ):
        mock_kb_repo.find_by_id.return_value = _kb(owner_id=99)
        with pytest.raises(PermissionError):
            await use_case.get("kb-1", _user(user_id=1), "req-1")

    async def test_owner_gets_kb(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = _kb(owner_id=1)
        kb = await use_case.get("kb-1", _user(user_id=1), "req-1")
        assert kb.id == "kb-1"


class TestDelete:
    async def test_not_found_raises(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await use_case.delete("ghost", _user(), "req-1")

    async def test_non_owner_raises_permission_error(
        self, use_case, mock_kb_repo
    ):
        mock_kb_repo.find_by_id.return_value = _kb(owner_id=99)
        with pytest.raises(PermissionError):
            await use_case.delete("kb-1", _user(user_id=1), "req-1")

    async def test_owner_soft_deletes(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = _kb(owner_id=1)
        await use_case.delete("kb-1", _user(user_id=1), "req-1")
        mock_kb_repo.soft_delete.assert_awaited_once_with("kb-1", "req-1")

    async def test_admin_can_delete_others(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = _kb(owner_id=99)
        await use_case.delete("kb-1", _user(role=UserRole.ADMIN), "req-1")
        mock_kb_repo.soft_delete.assert_awaited_once()


_CUSTOM_CONFIG = {
    "version": 1,
    "strategy": "full_token",
    "chunk_size": 1200,
    "chunk_overlap": 120,
}

_CHUNKING_OFF = dict(
    use_clause_chunking=False,
    chunking_profile_id=None,
    chunk_size=None,
    chunk_overlap=None,
    use_custom_chunking=False,
    custom_chunking_config=None,
)


class TestCreateCustomChunking:
    """kb-custom-chunking — create 시 커스텀 설정 검증/전달 (V-06, V-07)."""

    async def test_custom_config_saved_on_entity(
        self, use_case, mock_kb_repo
    ):
        kb = await use_case.create(
            user=_user(),
            name="커스텀 KB",
            collection_name="shared-col",
            scope=CollectionScope.PERSONAL,
            department_id=None,
            description=None,
            request_id="req-1",
            use_custom_chunking=True,
            custom_chunking_config=_CUSTOM_CONFIG,
        )
        assert kb.use_custom_chunking is True
        assert kb.custom_chunking_config == _CUSTOM_CONFIG

    async def test_both_toggles_rejected(self, use_case):
        with pytest.raises(ValueError, match="cannot both"):
            await use_case.create(
                user=_user(),
                name="충돌 KB",
                collection_name="shared-col",
                scope=CollectionScope.PERSONAL,
                department_id=None,
                description=None,
                request_id="req-1",
                use_clause_chunking=True,
                use_custom_chunking=True,
                custom_chunking_config=_CUSTOM_CONFIG,
            )

    async def test_config_without_toggle_rejected(self, use_case):
        with pytest.raises(ValueError, match="use_custom_chunking"):
            await use_case.create(
                user=_user(),
                name="KB",
                collection_name="shared-col",
                scope=CollectionScope.PERSONAL,
                department_id=None,
                description=None,
                request_id="req-1",
                use_custom_chunking=False,
                custom_chunking_config=_CUSTOM_CONFIG,
            )

    async def test_invalid_config_rejected(self, use_case):
        with pytest.raises(ValueError, match="chunk_size"):
            await use_case.create(
                user=_user(),
                name="KB",
                collection_name="shared-col",
                scope=CollectionScope.PERSONAL,
                department_id=None,
                description=None,
                request_id="req-1",
                use_custom_chunking=True,
                custom_chunking_config={
                    "strategy": "full_token", "chunk_size": 10,
                },
            )


class TestUpdateChunking:
    """kb-custom-chunking D7/D8/D9 — 청킹 설정 전체 교체."""

    async def test_owner_updates_settings(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = _kb(owner_id=1)
        await use_case.update_chunking(
            "kb-1", _user(user_id=1), request_id="req-1",
            **{**_CHUNKING_OFF,
               "use_custom_chunking": True,
               "custom_chunking_config": _CUSTOM_CONFIG},
        )
        mock_kb_repo.update_chunking.assert_awaited_once_with(
            "kb-1",
            use_clause_chunking=False,
            chunking_profile_id=None,
            chunk_size=None,
            chunk_overlap=None,
            use_custom_chunking=True,
            custom_chunking_config=_CUSTOM_CONFIG,
            request_id="req-1",
        )

    async def test_returns_refetched_kb(self, use_case, mock_kb_repo):
        updated = _kb(owner_id=1)
        updated.use_custom_chunking = True
        updated.custom_chunking_config = _CUSTOM_CONFIG
        mock_kb_repo.find_by_id.side_effect = [_kb(owner_id=1), updated]
        kb = await use_case.update_chunking(
            "kb-1", _user(user_id=1), request_id="req-1",
            **{**_CHUNKING_OFF,
               "use_custom_chunking": True,
               "custom_chunking_config": _CUSTOM_CONFIG},
        )
        assert kb.use_custom_chunking is True

    async def test_non_owner_rejected(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = _kb(owner_id=99)
        with pytest.raises(PermissionError):
            await use_case.update_chunking(
                "kb-1", _user(user_id=1), request_id="req-1",
                **_CHUNKING_OFF,
            )
        mock_kb_repo.update_chunking.assert_not_awaited()

    async def test_admin_updates_others(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = _kb(owner_id=99)
        await use_case.update_chunking(
            "kb-1", _user(role=UserRole.ADMIN), request_id="req-1",
            **_CHUNKING_OFF,
        )
        mock_kb_repo.update_chunking.assert_awaited_once()

    async def test_not_found_raises(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await use_case.update_chunking(
                "ghost", _user(), request_id="req-1", **_CHUNKING_OFF,
            )

    async def test_invalid_settings_rejected(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = _kb(owner_id=1)
        with pytest.raises(ValueError, match="cannot both"):
            await use_case.update_chunking(
                "kb-1", _user(user_id=1), request_id="req-1",
                **{**_CHUNKING_OFF,
                   "use_clause_chunking": True,
                   "use_custom_chunking": True,
                   "custom_chunking_config": _CUSTOM_CONFIG},
            )
        mock_kb_repo.update_chunking.assert_not_awaited()

    async def test_clause_settings_still_validated(
        self, use_case, mock_kb_repo
    ):
        """기존 조항 검증(비활성 시 오버라이드 금지)이 update에도 적용."""
        mock_kb_repo.find_by_id.return_value = _kb(owner_id=1)
        with pytest.raises(ValueError, match="use_clause_chunking"):
            await use_case.update_chunking(
                "kb-1", _user(user_id=1), request_id="req-1",
                **{**_CHUNKING_OFF, "chunk_size": 800},
            )
