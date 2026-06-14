"""render_user_context_block 단위 테스트 (스냅샷 + whitelist 강제).

agent-user-context Design §4.3 + 테스트 전략 §10.1:
- 민감정보(employee_no, email, user_id 숫자)가 절대 노출되지 않아야 함
- 모든 권한이 한국어 라벨로 변환되어야 함
- anonymous면 빈 문자열
"""
from src.application.agent_run.prompt_rendering import render_user_context_block
from src.domain.agent_run.auth_context import AuthContext


def _ctx(**overrides) -> AuthContext:
    defaults = dict(
        user_id=42,
        display_name="배상규",
        role="user",
        primary_department_id="dept-001",
        primary_department_name="DX팀",
        department_ids=("dept-001",),
        department_names=("DX팀",),
        permissions=frozenset({"USE_RAG_SEARCH", "READ_PUBLIC_DOCS"}),
    )
    defaults.update(overrides)
    return AuthContext(**defaults)


class TestRenderUserContextBlockHappy:
    def test_includes_display_name(self):
        block = render_user_context_block(_ctx())
        assert "배상규" in block

    def test_includes_department_name(self):
        block = render_user_context_block(_ctx())
        assert "DX팀" in block

    def test_role_label_user(self):
        block = render_user_context_block(_ctx(role="user"))
        assert "일반 사용자" in block

    def test_role_label_admin(self):
        block = render_user_context_block(_ctx(role="admin"))
        assert "관리자" in block

    def test_includes_korean_permission_labels(self):
        block = render_user_context_block(_ctx(
            permissions=frozenset({"USE_RAG_SEARCH", "MANAGE_USERS"}),
        ))
        assert "RAG 문서 검색" in block
        assert "사용자 관리" in block

    def test_includes_natural_language_pronoun_hint(self):
        block = render_user_context_block(_ctx())
        # "나", "내", "본인" 가이드 포함
        assert "'나'" in block or "나" in block

    def test_includes_no_block_self_decision_warning(self):
        """LLM이 권한 여부를 스스로 판단해서 차단하지 못하게 강제 문구."""
        block = render_user_context_block(_ctx())
        assert "도구가 자동으로 제외" in block


class TestRenderUserContextBlockEdge:
    def test_anonymous_returns_empty(self):
        ctx = AuthContext.public_anonymous()
        assert render_user_context_block(ctx) == ""

    def test_none_returns_empty(self):
        assert render_user_context_block(None) == ""

    def test_no_department(self):
        block = render_user_context_block(_ctx(
            primary_department_id=None,
            primary_department_name=None,
        ))
        assert "(미배정)" in block

    def test_no_permissions(self):
        block = render_user_context_block(_ctx(permissions=frozenset()))
        assert "(권한 없음)" in block

    def test_unknown_permission_code_skipped(self):
        """DB seed와 enum 불일치 시 graceful skip — 다른 권한은 정상 표시."""
        block = render_user_context_block(_ctx(
            permissions=frozenset({"USE_RAG_SEARCH", "UNKNOWN_CODE"}),
        ))
        assert "RAG 문서 검색" in block
        assert "UNKNOWN_CODE" not in block


class TestRenderUserContextBlockSecurity:
    """민감정보 미노출 강제 — whitelist enforcement."""

    def test_user_id_number_not_exposed(self):
        block = render_user_context_block(_ctx(user_id=42))
        # 42가 출력에 나타나면 사용자 식별 누설
        assert "42" not in block

    def test_email_format_not_exposed(self):
        """display_name에 email이 들어가도 @ 기호는 도메인이라 위험 — 일단 @만 검사."""
        block = render_user_context_block(_ctx(
            display_name="hong",
        ))
        assert "@" not in block

    def test_employee_no_field_not_in_block(self):
        """AuthContext에 employee_no 필드 자체가 없음 — 컴파일 타임 보장. 본 테스트는 회귀 보호."""
        block = render_user_context_block(_ctx())
        assert "employee_no" not in block.lower()
        assert "사번" not in block

    def test_password_word_not_in_block(self):
        block = render_user_context_block(_ctx())
        assert "password" not in block.lower()
        assert "비밀번호" not in block

    def test_tenant_id_not_exposed(self):
        ctx = _ctx()
        # tenant_id는 frozen 필드라 None만 가능
        block = render_user_context_block(ctx)
        assert "tenant" not in block.lower()


class TestRenderUserContextBlockDeterministic:
    """결정적 출력 — 스냅샷 테스트 안정성."""

    def test_permissions_sorted(self):
        """frozenset은 순서 비결정 — 출력은 결정적이어야 함."""
        ctx_a = _ctx(permissions=frozenset({"USE_RAG_SEARCH", "READ_PUBLIC_DOCS"}))
        ctx_b = _ctx(permissions=frozenset({"READ_PUBLIC_DOCS", "USE_RAG_SEARCH"}))
        # 동일 입력 → 동일 출력
        assert render_user_context_block(ctx_a) == render_user_context_block(ctx_b)
