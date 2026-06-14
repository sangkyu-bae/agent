"""AuthContext ValueObject 단위 테스트 (mock 금지).

agent-user-context Design §3.1 검증:
- frozen (immutable)
- public_anonymous() 안전 디폴트
- has() 권한 체크 단일 진입점
- LLM 노출 시 사용할 whitelist 필드만 보유
"""
import pytest

from src.domain.agent_run.auth_context import AuthContext


def _make_ctx(**overrides) -> AuthContext:
    """테스트용 헬퍼 — 명시되지 않은 필드는 안전한 기본값으로."""
    defaults = dict(
        user_id=1,
        display_name="배상규",
        role="user",
        primary_department_id="dept-001",
        primary_department_name="DX팀",
        department_ids=("dept-001",),
        department_names=("DX팀",),
        permissions=frozenset({"USE_RAG_SEARCH"}),
    )
    defaults.update(overrides)
    return AuthContext(**defaults)


class TestAuthContextConstruction:
    def test_create_with_all_fields(self):
        ctx = _make_ctx()
        assert ctx.user_id == 1
        assert ctx.display_name == "배상규"
        assert ctx.role == "user"
        assert ctx.primary_department_id == "dept-001"
        assert ctx.primary_department_name == "DX팀"
        assert ctx.department_ids == ("dept-001",)
        assert ctx.department_names == ("DX팀",)
        assert ctx.permissions == frozenset({"USE_RAG_SEARCH"})
        assert ctx.tenant_id is None  # 향후 확장 슬롯

    def test_supports_no_department(self):
        ctx = _make_ctx(
            primary_department_id=None,
            primary_department_name=None,
            department_ids=(),
            department_names=(),
        )
        assert ctx.primary_department_id is None
        assert ctx.department_ids == ()


class TestAuthContextImmutability:
    def test_frozen_dataclass(self):
        ctx = _make_ctx()
        with pytest.raises(Exception):  # FrozenInstanceError
            ctx.user_id = 999  # type: ignore[misc]

    def test_department_ids_is_tuple(self):
        """tuple → hashable + immutable. list 사용 금지."""
        ctx = _make_ctx()
        assert isinstance(ctx.department_ids, tuple)

    def test_permissions_is_frozenset(self):
        ctx = _make_ctx()
        assert isinstance(ctx.permissions, frozenset)


class TestPublicAnonymous:
    """미인증/누락 시 안전 디폴트 — Fail-Closed."""

    def test_returns_auth_context(self):
        ctx = AuthContext.public_anonymous()
        assert isinstance(ctx, AuthContext)

    def test_no_permissions(self):
        """anonymous는 어떤 권한도 없어야 함."""
        ctx = AuthContext.public_anonymous()
        assert ctx.permissions == frozenset()

    def test_role_is_anonymous(self):
        ctx = AuthContext.public_anonymous()
        assert ctx.role == "anonymous"

    def test_user_id_zero(self):
        ctx = AuthContext.public_anonymous()
        assert ctx.user_id == 0

    def test_empty_departments(self):
        ctx = AuthContext.public_anonymous()
        assert ctx.department_ids == ()
        assert ctx.department_names == ()
        assert ctx.primary_department_id is None
        assert ctx.primary_department_name is None


class TestHasPermission:
    """ctx.has(code) — 권한 체크의 단일 진입점."""

    def test_has_existing_permission(self):
        ctx = _make_ctx(permissions=frozenset({"USE_RAG_SEARCH", "READ_PUBLIC_DOCS"}))
        assert ctx.has("USE_RAG_SEARCH") is True
        assert ctx.has("READ_PUBLIC_DOCS") is True

    def test_does_not_have_missing_permission(self):
        ctx = _make_ctx(permissions=frozenset({"USE_RAG_SEARCH"}))
        assert ctx.has("MANAGE_USERS") is False

    def test_anonymous_has_none(self):
        ctx = AuthContext.public_anonymous()
        assert ctx.has("READ_PUBLIC_DOCS") is False
        assert ctx.has("USE_RAG_SEARCH") is False
