"""PermissionCode enum + label_ko 단위 테스트 (mock 금지).

agent-user-context Design §3.2 검증:
- 8개 권한 코드 모두 존재
- 한국어 라벨 매핑 완비 (누락 시 KeyError 발생 검출)
"""
import pytest

from src.domain.permission.value_objects import PermissionCode


class TestPermissionCodeMembers:
    """8개 권한 코드 enum 멤버 존재 검증."""

    def test_read_public_docs_exists(self):
        assert PermissionCode.READ_PUBLIC_DOCS.value == "READ_PUBLIC_DOCS"

    def test_read_internal_notices_exists(self):
        assert PermissionCode.READ_INTERNAL_NOTICES.value == "READ_INTERNAL_NOTICES"

    def test_read_department_docs_exists(self):
        assert PermissionCode.READ_DEPARTMENT_DOCS.value == "READ_DEPARTMENT_DOCS"

    def test_use_rag_search_exists(self):
        assert PermissionCode.USE_RAG_SEARCH.value == "USE_RAG_SEARCH"

    def test_use_web_search_exists(self):
        assert PermissionCode.USE_WEB_SEARCH.value == "USE_WEB_SEARCH"

    def test_create_agent_exists(self):
        assert PermissionCode.CREATE_AGENT.value == "CREATE_AGENT"

    def test_manage_users_exists(self):
        assert PermissionCode.MANAGE_USERS.value == "MANAGE_USERS"

    def test_manage_permissions_exists(self):
        assert PermissionCode.MANAGE_PERMISSIONS.value == "MANAGE_PERMISSIONS"

    def test_enum_is_str(self):
        """PermissionCode는 str을 상속해야 ai_run_* 등 외부 모듈과 비교 가능."""
        assert PermissionCode.USE_RAG_SEARCH == "USE_RAG_SEARCH"


class TestPermissionCodeLabelKo:
    """한국어 라벨 매핑 검증 — render_user_context_block에서 사용."""

    def test_all_members_have_label(self):
        """모든 enum 멤버에 한국어 라벨이 매핑되어야 함."""
        for code in PermissionCode:
            label = code.label_ko
            assert isinstance(label, str)
            assert len(label) > 0

    def test_read_public_docs_label(self):
        assert PermissionCode.READ_PUBLIC_DOCS.label_ko == "사내 공개 문서 조회"

    def test_use_rag_search_label(self):
        assert PermissionCode.USE_RAG_SEARCH.label_ko == "RAG 문서 검색"

    def test_manage_users_label(self):
        assert PermissionCode.MANAGE_USERS.label_ko == "사용자 관리"


class TestPermissionCodeFromString:
    """문자열로부터 enum 생성 — DB row → enum 변환에 사용."""

    def test_from_value(self):
        assert PermissionCode("USE_RAG_SEARCH") is PermissionCode.USE_RAG_SEARCH

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            PermissionCode("UNKNOWN_CODE")
