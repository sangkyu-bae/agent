"""prompt-composer 도메인 정책 유닛 테스트.

외부 의존 0. LLM·DB·langchain 없이 순수 함수만 검증한다.

prompt-depth Design Ref: §5 (조립·폴백 규칙) · §8.1 (T-P1~P6)
  - 조립 형식이 대괄호 블록에서 **마크다운 헤딩**으로 바뀌었다 (§4.3).
    구 형식을 단언하던 케이스는 새 계약으로 갱신했다 — Plan §6.2 "Breaking(의도)".
  - 신규 3필드(identity/context·workflows/style)가 부분 교체 헬퍼를 통과해도
    보존되는지가 이 사이클의 회귀 급소다 (T-P6).

선행 사이클 유지분: SC-03(조립 결정성) · SC-04(환각 폐기) · SC-05(레이어).
"""
from pathlib import Path

from src.domain.prompt_composer import policies as pol
from src.domain.prompt_composer.policies import PromptAssemblyPolicy as P
from src.domain.prompt_composer.schemas import (
    ComposedPrompt,
    ContextSection,
    PromptSections,
    RoleSection,
    ToolGuide,
    ToolMeta,
    WorkflowSection,
)


def _meta(tool_id: str, name: str = "도구", description: str = "설명") -> ToolMeta:
    return ToolMeta(
        tool_id=tool_id, name=name, description=description, source="internal"
    )


def _guide(tool_id: str, name: str = "도구", when: str = "언제", how: str = "어떻게",
           caution: str = "") -> ToolGuide:
    return ToolGuide(tool_id=tool_id, name=name, when=when, how=how, caution=caution)


def _sections(**kw) -> PromptSections:
    """기존 4섹션만 채운 최소 입력 — 신규 필드는 기본값(빈 값)이다."""
    base = {
        "purpose": "문서를 검색해 답하는 에이전트입니다.",
        "roles": (RoleSection(title="검색", detail="규정 원문을 찾는다"),),
        "tool_guides": (_guide("internal:excel_export", "엑셀 내보내기"),),
        "principles": ("한국어로 답한다",),
    }
    base.update(kw)
    return PromptSections(**base)


def _full_sections(**kw) -> PromptSections:
    """7섹션을 전부 채운 입력 (T-P1)."""
    base = {
        "identity": "여신 심사 실무자를 돕는 규정 전문가입니다.",
        "context": ContextSection(
            constraints=("추측하지 않는다",), background=("사내 여신 규정 2026판",)
        ),
        "workflows": (
            WorkflowSection(
                situation="일반 요청",
                steps=("규정을 찾는다", "근거와 함께 답한다"),
            ),
        ),
        "style": "격식체로 간결하게 답한다.",
    }
    base.update(kw)
    return _sections(**base)


# ── 신규 VO 기본값 (§3.1) ────────────────────────────────────────────────────


def test_prompt_sections_new_fields_have_defaults():
    """기존 4필드만으로 생성 가능해야 한다 — 생성자 호출부가 깨지지 않는 근거."""
    sections = PromptSections(purpose="목적")
    assert sections.identity == ""
    assert sections.context is None
    assert sections.workflows == ()
    assert sections.style == ""


def test_context_section_defaults_are_empty_tuples():
    assert ContextSection() == ContextSection(constraints=(), background=())


def test_workflow_section_requires_situation_and_defaults_steps():
    assert WorkflowSection(situation="일반 요청").steps == ()


# ── assemble: 결정성 (Plan SC-03 / FR-08) ───────────────────────────────────


def test_assemble_is_deterministic_across_repeated_calls():
    outputs = {P.assemble(_full_sections()) for _ in range(20)}
    assert len(outputs) == 1


def test_assemble_preserves_input_order_of_items():
    out = P.assemble(_sections(principles=("첫째", "둘째", "셋째")))
    assert out.index("첫째") < out.index("둘째") < out.index("셋째")


def test_assemble_does_not_end_with_newline():
    assert P.assemble(_full_sections()) == P.assemble(_full_sections()).rstrip()


# ── assemble: 마크다운 7섹션 (T-P1 / FR-07 / §4.3) ──────────────────────────


def test_assemble_renders_all_seven_sections_in_fixed_order():
    out = P.assemble(_full_sections())
    order = [
        "## Role and Identity",
        "## Context",
        "## Core Responsibilities",
        "## Tool Guidelines",
        "## Workflow",
        "## Communication Style",
        "## Important Notes",
    ]
    positions = [out.index(header) for header in order]
    assert positions == sorted(positions)


def test_assemble_starts_with_purpose_as_headerless_lead():
    """purpose 는 기존과 같은 위치에 헤더 없이 남는다 (§4.3)."""
    out = P.assemble(_full_sections())
    assert out.startswith("문서를 검색해 답하는 에이전트입니다.")
    assert not out.startswith("#")


def test_assemble_uses_no_section_numbers():
    """A-3 판정 — 번호를 붙이지 않는다. 빈 섹션 생략 시 번호가 튀는 문제 회피."""
    out = P.assemble(_full_sections())
    assert "## 1." not in out
    assert "## 2." not in out


def test_assemble_does_not_emit_agent_name_title():
    """A-4 판정 — 생성 시점에 이름이 확정되지 않으므로 `# 제목`을 쓰지 않는다."""
    out = P.assemble(_full_sections())
    assert "\n# " not in "\n" + out


def test_assemble_renders_identity_body():
    out = P.assemble(_full_sections())
    assert "## Role and Identity\n여신 심사 실무자를 돕는 규정 전문가입니다." in out


def test_assemble_renders_constraints_as_bullets():
    sections = _full_sections(
        context=ContextSection(constraints=("추측 금지", "출처 명시"), background=())
    )
    out = P.assemble(sections)
    assert "## Context\n- 추측 금지\n- 출처 명시" in out


def test_assemble_renders_background_under_label():
    sections = _full_sections(
        context=ContextSection(constraints=(), background=("2026 개정판 기준",))
    )
    out = P.assemble(sections)
    assert "## Context\n배경:\n- 2026 개정판 기준" in out


def test_assemble_renders_roles_under_core_responsibilities():
    out = P.assemble(_full_sections())
    assert "## Core Responsibilities\n- 검색: 규정 원문을 찾는다" in out


def test_assemble_renders_workflow_situation_and_numbered_steps():
    out = P.assemble(_full_sections())
    assert "## Workflow\n### 일반 요청\n1. 규정을 찾는다\n2. 근거와 함께 답한다" in out


def test_assemble_renders_multiple_workflows_in_order():
    sections = _full_sections(
        workflows=(
            WorkflowSection(situation="일반", steps=("a",)),
            WorkflowSection(situation="모호", steps=("b",)),
        )
    )
    out = P.assemble(sections)
    assert out.index("### 일반") < out.index("### 모호")


def test_assemble_renders_style_body():
    out = P.assemble(_full_sections())
    assert "## Communication Style\n격식체로 간결하게 답한다." in out


def test_assemble_renders_principles_under_important_notes():
    out = P.assemble(_full_sections())
    assert "## Important Notes\n- 한국어로 답한다" in out


def test_assemble_separates_blocks_with_blank_line():
    out = P.assemble(_full_sections())
    assert "\n\n## Role and Identity" in out


# ── assemble: 빈 섹션 헤더째 생략 (T-P2 / FR-07 / SC-5) ─────────────────────


def test_assemble_omits_identity_header_when_blank():
    out = P.assemble(_full_sections(identity="   "))
    assert "## Role and Identity" not in out
    assert "## Context" in out


def test_assemble_omits_context_header_when_section_is_none():
    out = P.assemble(_full_sections(context=None))
    assert "## Context" not in out


def test_assemble_omits_context_header_when_both_lists_empty():
    out = P.assemble(_full_sections(context=ContextSection()))
    assert "## Context" not in out


def test_assemble_omits_background_label_when_background_empty():
    sections = _full_sections(
        context=ContextSection(constraints=("추측 금지",), background=())
    )
    out = P.assemble(sections)
    assert "배경:" not in out


def test_assemble_omits_roles_header_when_empty():
    out = P.assemble(_full_sections(roles=()))
    assert "## Core Responsibilities" not in out
    assert "## Tool Guidelines" in out


def test_assemble_omits_tool_header_when_no_tools():
    """A-5 판정 — 도구 0개는 실패가 아니므로 헤더째 조용히 빠진다."""
    out = P.assemble(_full_sections(tool_guides=()))
    assert "## Tool Guidelines" not in out


def test_assemble_omits_workflow_header_when_empty():
    out = P.assemble(_full_sections(workflows=()))
    assert "## Workflow" not in out


def test_assemble_omits_workflow_entry_without_steps():
    sections = _full_sections(
        workflows=(
            WorkflowSection(situation="빈 절차", steps=()),
            WorkflowSection(situation="실제 절차", steps=("a",)),
        )
    )
    out = P.assemble(sections)
    assert "빈 절차" not in out
    assert "### 실제 절차" in out


def test_assemble_omits_workflow_heading_when_situation_blank():
    sections = _full_sections(
        workflows=(WorkflowSection(situation="  ", steps=("단계 하나",)),)
    )
    out = P.assemble(sections)
    assert "## Workflow\n1. 단계 하나" in out
    assert "###" not in out


def test_assemble_omits_style_header_when_blank():
    out = P.assemble(_full_sections(style=""))
    assert "## Communication Style" not in out


def test_assemble_omits_principles_header_when_empty():
    out = P.assemble(_full_sections(principles=()))
    assert "## Important Notes" not in out


def test_assemble_returns_only_purpose_when_all_sections_empty():
    out = P.assemble(PromptSections(purpose="목적만 있습니다."))
    assert out == "목적만 있습니다."


# ── assemble: 도구 지침 표기 (선행 사이클 계약 승계) ────────────────────────


def test_assemble_omits_caution_line_when_caution_is_blank():
    out = P.assemble(_sections(tool_guides=(_guide("t1", caution=""),)))
    assert "주의:" not in out


def test_assemble_renders_caution_line_when_present():
    guide = _guide("t1", caution="수치를 지어내지 않는다")
    out = P.assemble(_sections(tool_guides=(guide,)))
    assert "주의: 수치를 지어내지 않는다" in out


def test_assemble_omits_how_separator_when_how_is_blank():
    """폴백 경로는 how가 비어 있다 — 'when / ' 같은 매달린 구분자를 남기지 않는다."""
    guide = _guide("t1", "엑셀", when="설명", how="")
    out = P.assemble(_sections(tool_guides=(guide,)))
    assert "- 엑셀 (t1): 설명" in out
    assert "설명 /" not in out


# ── drop_hallucinated: 환각 폐기 (Plan SC-04 / FR-11) ───────────────────────


def test_drop_hallucinated_removes_guides_not_in_candidates():
    known = {"t1": _meta("t1")}
    sections = _sections(tool_guides=(_guide("t1"), _guide("ghost")))
    cleaned, dropped = P.drop_hallucinated(sections, known)
    assert tuple(g.tool_id for g in cleaned.tool_guides) == ("t1",)
    assert dropped == ("ghost",)


def test_drop_hallucinated_keeps_everything_when_all_known():
    known = {"t1": _meta("t1"), "t2": _meta("t2")}
    sections = _sections(tool_guides=(_guide("t1"), _guide("t2")))
    cleaned, dropped = P.drop_hallucinated(sections, known)
    assert len(cleaned.tool_guides) == 2
    assert dropped == ()


def test_drop_hallucinated_backfills_name_from_catalog():
    """LLM이 도구 이름을 바꿔 부르면 카탈로그 이름으로 되돌린다."""
    known = {"t1": _meta("t1", name="엑셀 내보내기")}
    sections = _sections(tool_guides=(_guide("t1", name="엉뚱한 이름"),))
    cleaned, _ = P.drop_hallucinated(sections, known)
    assert cleaned.tool_guides[0].name == "엑셀 내보내기"


def test_drop_hallucinated_leaves_other_sections_untouched():
    known = {"t1": _meta("t1")}
    sections = _sections(tool_guides=(_guide("t1"),))
    cleaned, _ = P.drop_hallucinated(sections, known)
    assert cleaned.purpose == sections.purpose
    assert cleaned.roles == sections.roles
    assert cleaned.principles == sections.principles


def test_drop_hallucinated_preserves_new_sections(  # T-P6
):
    """이 사이클의 회귀 급소 — 부분 교체 헬퍼가 신규 3필드를 떨어뜨리면 안 된다."""
    known = {"t1": _meta("t1")}
    sections = _full_sections(tool_guides=(_guide("t1"), _guide("ghost")))
    cleaned, dropped = P.drop_hallucinated(sections, known)
    assert dropped == ("ghost",)
    assert cleaned.identity == sections.identity
    assert cleaned.context == sections.context
    assert cleaned.workflows == sections.workflows
    assert cleaned.style == sections.style


def test_drop_hallucinated_with_empty_candidates_drops_all():
    sections = _sections(tool_guides=(_guide("t1"), _guide("t2")))
    cleaned, dropped = P.drop_hallucinated(sections, {})
    assert cleaned.tool_guides == ()
    assert dropped == ("t1", "t2")


def test_drop_hallucinated_deduplicates_repeated_guides():
    known = {"t1": _meta("t1")}
    sections = _sections(tool_guides=(_guide("t1"), _guide("t1")))
    cleaned, _ = P.drop_hallucinated(sections, known)
    assert len(cleaned.tool_guides) == 1


# ── clamp_sections: 상한 절단 (T-P5 / FR-09 / §5.2) ─────────────────────────


def test_clamp_sections_caps_roles_at_max():
    roles = tuple(RoleSection(title=f"r{i}", detail="d") for i in range(20))
    assert len(P.clamp_sections(_sections(roles=roles)).roles) == P.MAX_ROLES


def test_clamp_sections_caps_principles_at_max():
    principles = tuple(f"p{i}" for i in range(50))
    clamped = P.clamp_sections(_sections(principles=principles))
    assert len(clamped.principles) == P.MAX_PRINCIPLES


def test_clamp_sections_caps_tool_guides_at_max():
    guides = tuple(_guide(f"t{i}") for i in range(80))
    clamped = P.clamp_sections(_sections(tool_guides=guides))
    assert len(clamped.tool_guides) == P.MAX_TOOL_GUIDES


def test_clamp_sections_caps_constraints_at_max():
    context = ContextSection(constraints=tuple(f"c{i}" for i in range(30)))
    clamped = P.clamp_sections(_full_sections(context=context))
    assert len(clamped.context.constraints) == P.MAX_CONSTRAINTS


def test_clamp_sections_caps_background_at_max():
    context = ContextSection(background=tuple(f"b{i}" for i in range(30)))
    clamped = P.clamp_sections(_full_sections(context=context))
    assert len(clamped.context.background) == P.MAX_BACKGROUND


def test_clamp_sections_caps_workflows_at_max():
    workflows = tuple(
        WorkflowSection(situation=f"s{i}", steps=("a",)) for i in range(20)
    )
    clamped = P.clamp_sections(_full_sections(workflows=workflows))
    assert len(clamped.workflows) == P.MAX_WORKFLOWS


def test_clamp_sections_caps_workflow_steps_at_max():
    workflows = (
        WorkflowSection(situation="s", steps=tuple(f"step{i}" for i in range(30))),
    )
    clamped = P.clamp_sections(_full_sections(workflows=workflows))
    assert len(clamped.workflows[0].steps) == P.MAX_WORKFLOW_STEPS


def test_clamp_sections_caps_identity_chars():
    clamped = P.clamp_sections(_full_sections(identity="가" * 2000))
    assert len(clamped.identity) == P.MAX_IDENTITY_CHARS


def test_clamp_sections_caps_style_chars():
    clamped = P.clamp_sections(_full_sections(style="가" * 2000))
    assert len(clamped.style) == P.MAX_STYLE_CHARS


def test_clamp_sections_keeps_leading_items():
    roles = tuple(RoleSection(title=f"r{i}", detail="d") for i in range(20))
    assert P.clamp_sections(_sections(roles=roles)).roles[0].title == "r0"


def test_clamp_sections_keeps_none_context_as_none():
    assert P.clamp_sections(_full_sections(context=None)).context is None


def test_clamp_sections_is_noop_when_within_limits():
    sections = _full_sections()
    assert P.clamp_sections(sections) == sections


def test_clamp_sections_preserves_new_sections():
    """clamp 도 부분 재구성이다 — 신규 필드를 흘리면 안 된다."""
    sections = _full_sections()
    clamped = P.clamp_sections(sections)
    assert clamped.identity == sections.identity
    assert clamped.context == sections.context
    assert clamped.workflows == sections.workflows
    assert clamped.style == sections.style


# ── clamp_history: 이력 절단 (선행 사이클 Q3 — 자체 구현) ───────────────────


class _Turn:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


def test_clamp_history_keeps_only_recent_turns():
    turns = [_Turn("user", f"m{i}") for i in range(25)]
    out = P.clamp_history(turns)
    assert len(out) == P.MAX_HISTORY_TURNS
    assert out[-1]["content"] == "m24"


def test_clamp_history_truncates_long_content():
    out = P.clamp_history([_Turn("user", "가" * 1500)])
    assert len(out[0]["content"]) == P.MAX_HISTORY_TURN_CHARS


def test_clamp_history_returns_llm_message_dicts():
    assert P.clamp_history([_Turn("assistant", "안녕")]) == [
        {"role": "assistant", "content": "안녕"}
    ]


def test_clamp_history_handles_empty_and_none():
    assert P.clamp_history([]) == []
    assert P.clamp_history(None) == []


def test_clamp_history_accepts_dict_turns():
    """요청 스키마가 dict로 넘겨도 동작한다 (duck-typing 대신 명시 지원)."""
    assert P.clamp_history([{"role": "user", "content": "안녕"}]) == [
        {"role": "user", "content": "안녕"}
    ]


# ── fallback_sections: 규칙기반 폴백 (T-P4 / FR-10 / SC-7 / §5.1) ───────────


def test_fallback_sections_builds_one_guide_per_tool():
    metas = (_meta("t1", "엑셀", "표를 내보낸다"), _meta("t2", "검색", "문서를 찾는다"))
    out = P.fallback_sections(metas, "사내 규정 봇")
    assert tuple(g.tool_id for g in out.tool_guides) == ("t1", "t2")
    assert out.tool_guides[0].when == "표를 내보낸다"
    assert out.tool_guides[0].how == ""


def test_fallback_sections_purpose_is_never_blank():
    assert P.fallback_sections((), "").purpose.strip() != ""


def test_fallback_sections_includes_user_request_excerpt():
    out = P.fallback_sections((), "사내 규정 문서를 찾아 답하는 봇")
    assert "사내 규정 문서를 찾아 답하는 봇" in out.purpose


def test_fallback_sections_truncates_long_user_request():
    assert len(P.fallback_sections((), "가" * 500).purpose) < 400


def test_fallback_sections_fills_all_new_sections_with_constants():
    """A-6 판정 — 신규 4섹션을 고정 문구로 채운다."""
    out = P.fallback_sections((), "요청")
    assert out.identity == pol._FALLBACK_IDENTITY
    assert out.context == pol._FALLBACK_CONTEXT
    assert out.workflows == pol._FALLBACK_WORKFLOWS
    assert out.style == pol._FALLBACK_STYLE
    assert out.roles == pol._FALLBACK_ROLES


def test_fallback_sections_are_constant_across_requests():
    """폴백 관측성 — 값이 요청과 무관해야 출력만 보고 폴백임을 안다."""
    a = P.fallback_sections((), "요청 A")
    b = P.fallback_sections((), "요청 B")
    assert (a.identity, a.context, a.workflows, a.style, a.principles) == (
        b.identity, b.context, b.workflows, b.style, b.principles
    )


def test_fallback_sections_has_fixed_principles():
    a = P.fallback_sections((), "요청 A").principles
    assert a == P.fallback_sections((), "요청 B").principles
    assert len(a) == 3


def test_fallback_assembles_into_seven_section_markdown():
    """SC-7 — 폴백도 7섹션 구조로 나온다 (도구가 있을 때)."""
    out = P.assemble(P.fallback_sections((_meta("t1", "엑셀", "표 내보내기"),), "요청"))
    for header in (
        "## Role and Identity",
        "## Context",
        "## Core Responsibilities",
        "## Tool Guidelines",
        "## Workflow",
        "## Communication Style",
        "## Important Notes",
    ):
        assert header in out
    assert "엑셀" in out


def test_fallback_without_tools_omits_only_tool_section():
    out = P.assemble(P.fallback_sections((), "요청"))
    assert "## Tool Guidelines" not in out
    assert "## Workflow" in out


# ── ComposedPrompt VO 기본값 ────────────────────────────────────────────────


def test_composed_prompt_defaults_are_system_owned_and_empty():
    prompt = ComposedPrompt(sections=_sections(), assembled="x")
    assert prompt.degraded is False
    assert prompt.reason is None
    assert prompt.dropped_tool_ids == ()
    assert prompt.unknown_tool_ids == ()
    assert prompt.elapsed_ms == 0


# ── 레이어 규칙 (Plan SC-05 / D1) ───────────────────────────────────────────


_DOMAIN_DIR = (
    Path(__file__).resolve().parents[3]
    / "src" / "domain" / "prompt_composer"
)
_FORBIDDEN = ("langchain", "sqlalchemy", "fastapi", "pydantic", "agent_composer")


def test_domain_layer_has_no_forbidden_imports():
    offenders = []
    for path in _DOMAIN_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for banned in _FORBIDDEN:
                if banned in stripped:
                    offenders.append(f"{path.name}: {stripped}")
    assert offenders == [], offenders


# ── wiki-guided-routing D5: Tool Guidelines 섹션 한정 교체 ──────────────


_PROMPT_WITH_TOOLS = (
    "리드 문단입니다.\n\n"
    "## Role and Identity\n범용 에이전트\n\n"
    "## Tool Guidelines\n"
    "- 옛도구 (internal:old_tool): 예전 설명\n"
    "  주의: 옛 주의\n\n"
    "## Important Notes\n- 사용자가 직접 편집한 줄\n- 한국어로 답한다"
)


class TestReplaceToolSection:
    def test_replaces_only_tool_block_and_preserves_others(self):
        out = P.replace_tool_section(
            _PROMPT_WITH_TOOLS,
            (_guide("internal:new_tool", "새도구", when="새 설명", how=""),),
        )
        assert "옛도구" not in out and "옛 주의" not in out
        assert "- 새도구 (internal:new_tool): 새 설명" in out
        head, tail = out.split("## Tool Guidelines")
        assert head == "리드 문단입니다.\n\n## Role and Identity\n범용 에이전트\n\n"
        assert tail.endswith(
            "\n\n## Important Notes\n- 사용자가 직접 편집한 줄\n- 한국어로 답한다"
        )

    def test_no_heading_returns_prompt_unchanged(self):
        prompt = "## Role and Identity\n범용\n\n## Important Notes\n- 편집"
        assert P.replace_tool_section(prompt, (_guide("internal:x"),)) == prompt

    def test_empty_guides_removes_block(self):
        out = P.replace_tool_section(_PROMPT_WITH_TOOLS, ())
        assert "## Tool Guidelines" not in out
        assert out == (
            "리드 문단입니다.\n\n## Role and Identity\n범용 에이전트\n\n"
            "## Important Notes\n- 사용자가 직접 편집한 줄\n- 한국어로 답한다"
        )

    def test_tool_block_at_end_is_replaced_without_trailing_newline(self):
        prompt = "리드\n\n## Tool Guidelines\n- a (internal:a): 설명"
        out = P.replace_tool_section(prompt, (_guide("internal:b", "b", when="설명b", how=""),))
        assert out == "리드\n\n## Tool Guidelines\n- b (internal:b): 설명b"

    def test_only_first_heading_is_replaced(self):
        prompt = (
            "## Tool Guidelines\n- a (internal:a): 1\n\n"
            "## Workflow\n1. x\n\n"
            "## Tool Guidelines\n- 사용자가 붙인 중복 섹션"
        )
        out = P.replace_tool_section(prompt, (_guide("internal:b", "b", when="2", how=""),))
        assert out.count("## Tool Guidelines") == 2
        assert "- b (internal:b): 2" in out
        assert "사용자가 붙인 중복 섹션" in out
        assert "- a (internal:a): 1" not in out

    def test_deterministic(self):
        guides = (_guide("internal:b", "b", when="2", how=""),)
        assert (
            P.replace_tool_section(_PROMPT_WITH_TOOLS, guides)
            == P.replace_tool_section(_PROMPT_WITH_TOOLS, guides)
        )
