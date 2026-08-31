"""render_user_context_block 단위 테스트 (스냅샷 + whitelist 강제).

agent-user-context Design §4.3 + 테스트 전략 §10.1:
- 민감정보(employee_no, email, user_id 숫자)가 절대 노출되지 않아야 함
- anonymous면 빈 문자열

supervisor-overblock-fix D1/D2: 권한 목록('허용된 정보 영역') 미노출 +
권한 심사 위임 가드 문구 — LLM 자체 권한 심사로 인한 과차단 방지.
"""
from datetime import UTC, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from src.application.agent_run.prompt_rendering import (
    render_datetime_block,
    render_user_context_block,
)
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

    def test_includes_natural_language_pronoun_hint(self):
        block = render_user_context_block(_ctx())
        # "나", "내", "본인" 가이드 포함
        assert "'나'" in block or "나" in block

    def test_includes_no_block_self_decision_warning(self):
        """LLM이 권한 여부를 스스로 판단해서 차단하지 못하게 강제 문구."""
        block = render_user_context_block(_ctx())
        assert "도구가 자동으로 검증" in block

    def test_includes_delegation_guard(self):
        """supervisor-overblock-fix D2: 권한 심사 위임 가드 문구."""
        block = render_user_context_block(_ctx())
        assert "거부하거나 차단하지 마세요" in block
        assert "확인되지 않습니다" in block

    def test_permission_list_not_exposed(self):
        """supervisor-overblock-fix D1 (FR-01): 권한 목록이 '허용된 정보 영역'
        프레이밍으로 노출되지 않는다 — 목록이 있으면 LLM이 자체 권한 심사를 수행."""
        block = render_user_context_block(_ctx(
            permissions=frozenset({"USE_RAG_SEARCH", "MANAGE_USERS"}),
        ))
        assert "허용된 정보 영역" not in block
        assert "RAG 문서 검색" not in block
        assert "사용자 관리" not in block


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

    def test_no_permissions_renders_without_permission_section(self):
        """supervisor-overblock-fix D1: 권한 목록 소멸 — '(권한 없음)'도 미노출.
        빈 permissions에서도 기본 필드(이름·부서)는 정상 렌더링."""
        block = render_user_context_block(_ctx(permissions=frozenset()))
        assert "(권한 없음)" not in block
        assert "배상규" in block


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


# ── wiki-agentic-navigation FR-03/FR-04: 위키 목차 블록 ──────────────

from src.application.agent_run.prompt_rendering import render_wiki_toc_block
from src.application.wiki.schemas import WikiTreeItem

_NOW = datetime(2026, 7, 23, tzinfo=UTC)


def _toc_item(id="w1", title="한도 산정 기준", path="여신/한도") -> WikiTreeItem:
    return WikiTreeItem(
        id=id, title=title, status="approved", source_type="human",
        path=path, updated_at=_NOW,
    )


class TestRenderWikiTocBlockEmpty:
    def test_empty_items_returns_empty_string(self):
        """FR-04: 위키 0건이면 블록 자체 미주입(빈 블록 노이즈 금지)."""
        assert render_wiki_toc_block([], max_items=50, max_bytes=4000) == ""


class TestRenderWikiTocBlockContent:
    def test_includes_id_title_path_and_date(self):
        block = render_wiki_toc_block([_toc_item()], max_items=50, max_bytes=4000)
        assert "(id: w1)" in block
        assert "한도 산정 기준" in block
        assert "여신/한도" in block
        assert "2026-07-21" not in block and "2026-07-23" in block

    def test_header_and_usage_instruction_present(self):
        block = render_wiki_toc_block([_toc_item()], max_items=50, max_bytes=4000)
        assert "[에이전트 지식 위키 목차]" in block
        assert "wiki_read" in block

    def test_none_path_renders_title_only(self):
        block = render_wiki_toc_block(
            [_toc_item(path=None)], max_items=50, max_bytes=4000
        )
        assert "한도 산정 기준" in block
        assert "None" not in block

    def test_ends_with_separator(self):
        """user_context_block 관례: 말미 '---' 구분자."""
        block = render_wiki_toc_block([_toc_item()], max_items=50, max_bytes=4000)
        assert block.endswith("---\n\n")


class TestRenderWikiTocBlockLimits:
    def test_max_items_truncates_with_notice(self):
        items = [_toc_item(id=f"w{i}", title=f"문서{i}") for i in range(5)]
        block = render_wiki_toc_block(items, max_items=3, max_bytes=4000)
        assert "(id: w0)" in block and "(id: w2)" in block
        assert "(id: w3)" not in block and "(id: w4)" not in block
        assert "전체 5건 중 3건" in block

    def test_max_bytes_truncates_lines_from_tail(self):
        items = [_toc_item(id=f"w{i}", title=f"문서{i}" * 20) for i in range(20)]
        small = render_wiki_toc_block(items, max_items=50, max_bytes=500)
        # max_bytes는 목록부 상한 — 고정 헤더/생략 표시/구분자 오버헤드는 별도
        assert len(small.encode("utf-8")) <= 500 + 400
        assert "(id: w0)" in small
        assert "(id: w19)" not in small
        assert "생략" in small or "중" in small

    def test_no_truncation_no_notice(self):
        block = render_wiki_toc_block(
            [_toc_item()], max_items=50, max_bytes=4000
        )
        assert "생략" not in block


# ── runtime-datetime-context D1: render_datetime_block ──────────────


class TestRenderDatetimeBlock:
    """FR-01/02/03/11 + NFR(길이·캐시 안정·금지어)."""

    _NOW = datetime(2026, 8, 24, 15, 30, tzinfo=UTC)  # KST 2026-08-25 00:30

    def test_snapshot_2026_08_25_is_tuesday(self):
        """FR-01: 헤더 + 'YYYY-MM-DD (요일)' + 지침 + '---' 구분자."""
        block = render_datetime_block("Asia/Seoul", now_utc=self._NOW)
        # Design §4.2 고정 스냅샷 — 전체 문자열 동등 (지침 3줄 누락도 잡는다)
        assert block == (
            "[현재 날짜]\n"
            "- 2026-08-25 (화)\n\n"
            "'오늘', '최근', '최신', '이번 주/이번 달' 같은 표현은 "
            "위 날짜를 기준으로 해석하세요.\n"
            "웹 검색이 필요하면 검색어에 위 날짜(연-월-일)를 포함하세요.\n"
            "검색 결과나 문서의 날짜가 위 날짜와 다르면 "
            "그 날짜를 답변에 함께 밝히세요.\n"
            "\n---\n\n"
        )

    def test_utc_2330_renders_next_day_in_kst(self):
        """FR-02: 서버 로컬시간이 아닌 tz 기준 날짜."""
        block = render_datetime_block("Asia/Seoul", now_utc=self._NOW)
        assert "2026-08-25" in block and "2026-08-24" not in block
        assert "2026-08-24" in render_datetime_block("UTC", now_utc=self._NOW)

    def test_now_utc_default_uses_current_time(self):
        """FR-03: now_utc 미지정 시 현재 UTC — 오늘 날짜(양 tz 중 하나) 포함."""
        block = render_datetime_block("Asia/Seoul")
        today_kst = datetime.now(UTC).astimezone(
            ZoneInfo("Asia/Seoul")
        ).strftime("%Y-%m-%d")
        assert today_kst in block

    def test_none_tz_returns_empty_without_logging(self):
        """tz=None = 미배선 opt-out — 빈 문자열, 로그 없음."""
        logger = MagicMock()
        assert render_datetime_block(None, now_utc=self._NOW, logger=logger) == ""
        logger.warning.assert_not_called()

    def test_invalid_tz_returns_empty_and_warns_with_exception(self):
        """FR-11: degraded — 빈 문자열 + warning(exception=e)."""
        logger = MagicMock()
        block = render_datetime_block("Mars/Olympus", now_utc=self._NOW, logger=logger)
        assert block == ""
        logger.warning.assert_called_once()
        assert "exception" in logger.warning.call_args.kwargs

    def test_invalid_tz_without_logger_does_not_raise(self):
        assert render_datetime_block("Mars/Olympus", now_utc=self._NOW) == ""

    def test_block_length_under_200(self):
        """NFR: 워커 N개에 각각 prepend되므로 크기 상한."""
        assert len(render_datetime_block("Asia/Seoul", now_utc=self._NOW)) <= 200

    def test_same_day_two_times_render_identical(self):
        """NFR 캐시 안정: 시각 미포함 → 같은 날이면 동일 텍스트."""
        a = render_datetime_block("Asia/Seoul", now_utc=self._NOW)
        b = render_datetime_block(
            "Asia/Seoul", now_utc=datetime(2026, 8, 25, 10, 0, tzinfo=UTC)
        )
        assert a == b

    def test_block_has_no_gate_vocabulary(self):
        """supervisor-overblock-fix 교훈: 심사/게이트 프레이밍 어휘 금지."""
        block = render_datetime_block("Asia/Seoul", now_utc=self._NOW)
        for word in ("거부", "차단", "권한"):
            assert word not in block
