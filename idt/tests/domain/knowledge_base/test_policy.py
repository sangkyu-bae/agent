import pytest

from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
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
    owner_id: int = 1,
    scope: CollectionScope = CollectionScope.PERSONAL,
    department_id: str | None = None,
) -> KnowledgeBase:
    return KnowledgeBase(
        id="kb-1",
        name="테스트 지식베이스",
        owner_id=owner_id,
        scope=scope,
        department_id=department_id,
        collection_name="shared-col",
    )


class TestValidateName:
    def test_korean_name_allowed(self):
        assert KnowledgeBasePolicy.validate_name("여신 규정집") == "여신 규정집"

    def test_ascii_name_allowed(self):
        assert KnowledgeBasePolicy.validate_name("loan-docs") == "loan-docs"

    def test_strips_whitespace(self):
        assert KnowledgeBasePolicy.validate_name("  이름  ") == "이름"

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            KnowledgeBasePolicy.validate_name("")

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValueError):
            KnowledgeBasePolicy.validate_name("   ")

    def test_over_100_chars_rejected(self):
        with pytest.raises(ValueError):
            KnowledgeBasePolicy.validate_name("가" * 101)

    def test_100_chars_allowed(self):
        assert KnowledgeBasePolicy.validate_name("가" * 100) == "가" * 100

    def test_control_char_rejected(self):
        with pytest.raises(ValueError):
            KnowledgeBasePolicy.validate_name("이름\x00")


class TestCanRead:
    def test_admin_always_true(self):
        kb = _kb(owner_id=99)
        assert KnowledgeBasePolicy.can_read(_user(role=UserRole.ADMIN), kb, [])

    def test_public_true_for_anyone(self):
        kb = _kb(owner_id=99, scope=CollectionScope.PUBLIC)
        assert KnowledgeBasePolicy.can_read(_user(), kb, [])

    def test_personal_owner_true(self):
        kb = _kb(owner_id=1)
        assert KnowledgeBasePolicy.can_read(_user(user_id=1), kb, [])

    def test_personal_other_false(self):
        kb = _kb(owner_id=99)
        assert not KnowledgeBasePolicy.can_read(_user(user_id=1), kb, [])

    def test_department_member_true(self):
        kb = _kb(owner_id=99, scope=CollectionScope.DEPARTMENT, department_id="d1")
        assert KnowledgeBasePolicy.can_read(_user(), kb, ["d1"])

    def test_department_non_member_false(self):
        kb = _kb(owner_id=99, scope=CollectionScope.DEPARTMENT, department_id="d1")
        assert not KnowledgeBasePolicy.can_read(_user(), kb, ["d2"])


class TestCanReadRef:
    """kb-rag-filter Act-1: 원시값 기반 읽기권한 — can_read와 동일 규칙."""

    def test_admin_always_true(self):
        kb = _kb(owner_id=99)
        assert KnowledgeBasePolicy.can_read_ref(1, UserRole.ADMIN, kb, [])

    def test_public_true_for_anyone(self):
        kb = _kb(owner_id=99, scope=CollectionScope.PUBLIC)
        assert KnowledgeBasePolicy.can_read_ref(1, UserRole.USER, kb, [])

    def test_personal_owner_true(self):
        kb = _kb(owner_id=1)
        assert KnowledgeBasePolicy.can_read_ref(1, UserRole.USER, kb, [])

    def test_personal_other_false(self):
        kb = _kb(owner_id=99)
        assert not KnowledgeBasePolicy.can_read_ref(1, UserRole.USER, kb, [])

    def test_personal_none_user_id_false(self):
        kb = _kb(owner_id=1)
        assert not KnowledgeBasePolicy.can_read_ref(
            None, UserRole.USER, kb, []
        )

    def test_department_member_true(self):
        kb = _kb(
            owner_id=99, scope=CollectionScope.DEPARTMENT, department_id="d1"
        )
        assert KnowledgeBasePolicy.can_read_ref(1, UserRole.USER, kb, ["d1"])

    def test_department_non_member_false(self):
        kb = _kb(
            owner_id=99, scope=CollectionScope.DEPARTMENT, department_id="d1"
        )
        assert not KnowledgeBasePolicy.can_read_ref(
            1, UserRole.USER, kb, ["d2"]
        )


class TestCanWrite:
    def test_admin_always_true(self):
        kb = _kb(owner_id=99, scope=CollectionScope.PUBLIC)
        assert KnowledgeBasePolicy.can_write(_user(role=UserRole.ADMIN), kb, [])

    def test_personal_owner_true(self):
        kb = _kb(owner_id=1)
        assert KnowledgeBasePolicy.can_write(_user(user_id=1), kb, [])

    def test_personal_other_false(self):
        kb = _kb(owner_id=99)
        assert not KnowledgeBasePolicy.can_write(_user(user_id=1), kb, [])

    def test_department_member_true(self):
        kb = _kb(owner_id=99, scope=CollectionScope.DEPARTMENT, department_id="d1")
        assert KnowledgeBasePolicy.can_write(_user(), kb, ["d1"])

    def test_department_non_member_false(self):
        kb = _kb(owner_id=99, scope=CollectionScope.DEPARTMENT, department_id="d1")
        assert not KnowledgeBasePolicy.can_write(_user(), kb, [])

    def test_public_owner_true(self):
        kb = _kb(owner_id=1, scope=CollectionScope.PUBLIC)
        assert KnowledgeBasePolicy.can_write(_user(user_id=1), kb, [])

    def test_public_non_owner_false(self):
        kb = _kb(owner_id=99, scope=CollectionScope.PUBLIC)
        assert not KnowledgeBasePolicy.can_write(_user(user_id=1), kb, [])


class TestCanDelete:
    def test_admin_true(self):
        assert KnowledgeBasePolicy.can_delete(
            _user(role=UserRole.ADMIN), _kb(owner_id=99)
        )

    def test_owner_true(self):
        assert KnowledgeBasePolicy.can_delete(_user(user_id=1), _kb(owner_id=1))

    def test_other_false(self):
        assert not KnowledgeBasePolicy.can_delete(_user(user_id=1), _kb(owner_id=99))


class TestValidateScope:
    def test_personal_ok_without_department(self):
        KnowledgeBasePolicy.validate_scope(CollectionScope.PERSONAL, None, [])

    def test_public_ok_without_department(self):
        KnowledgeBasePolicy.validate_scope(CollectionScope.PUBLIC, None, [])

    def test_department_requires_department_id(self):
        with pytest.raises(ValueError, match="department_id"):
            KnowledgeBasePolicy.validate_scope(CollectionScope.DEPARTMENT, None, ["d1"])

    def test_department_must_belong(self):
        with pytest.raises(ValueError):
            KnowledgeBasePolicy.validate_scope(
                CollectionScope.DEPARTMENT, "d9", ["d1", "d2"]
            )

    def test_department_member_ok(self):
        KnowledgeBasePolicy.validate_scope(CollectionScope.DEPARTMENT, "d1", ["d1"])


class TestCanManageSettings:
    """kb-custom-chunking D9 — 청킹 설정 변경은 소유자/ADMIN만."""

    def test_owner_allowed(self):
        assert KnowledgeBasePolicy.can_manage_settings(
            _user(user_id=1), _kb(owner_id=1)
        )

    def test_admin_allowed(self):
        assert KnowledgeBasePolicy.can_manage_settings(
            _user(user_id=2, role=UserRole.ADMIN), _kb(owner_id=1)
        )

    def test_other_user_denied(self):
        assert not KnowledgeBasePolicy.can_manage_settings(
            _user(user_id=2), _kb(owner_id=1)
        )
