"""prompt-composer Design §8.2 — L0 유닛 테스트 (도메인 정책).

외부 의존 0. LLM·DB·langchain 없이 순수 함수만 검증한다.
핵심은 SC-03(조립 결정성)과 SC-04(환각 폐기), SC-05(레이어)다.
"""
from pathlib import Path

from src.domain.prompt_composer.policies import PromptAssemblyPolicy as P
from src.domain.prompt_composer.schemas import (
    ComposedPrompt,
    PromptSections,
    RoleSection,
    ToolGuide,
    ToolMeta,
)


def _meta(tool_id: str, name: str = "도구", description: str = "설명") -> ToolMeta:
    return ToolMeta(
        tool_id=tool_id, name=name, description=description, source="internal"
    )


def _guide(tool_id: str, name: str = "도구", when: str = "언제", how: str = "어떻게",
           caution: str = "") -> ToolGuide:
    return ToolGuide(tool_id=tool_id, name=name, when=when, how=how, caution=caution)


def _sections(**kw) -> PromptSections:
    base = {
        "purpose": "문서를 검색해 답하는 에이전트입니다.",
        "roles": (RoleSection(title="검색", detail="규정 원문을 찾는다"),),
        "tool_guides": (_guide("internal:excel_export", "엑셀 내보내기"),),
        "principles": ("한국어로 답한다",),
    }
    base.update(kw)
    return PromptSections(**base)


# ── assemble: 결정성 (Design §8.2 #1 · Plan SC-03) ──────────────────────────


def test_assemble_is_deterministic_across_repeated_calls():
    sections = _sections()
    outputs = {P.assemble(sections) for _ in range(20)}
    assert len(outputs) == 1


def test_assemble_renders_all_four_sections_in_fixed_order():
    out = P.assemble(_sections())
    assert out.index("[역할]") < out.index("[도구 지침]") < out.index("[동작 원칙]")
    assert out.startswith("문서를 검색해 답하는 에이전트입니다.")


def test_assemble_preserves_input_order_of_items():
    sections = _sections(principles=("첫째", "둘째", "셋째"))
    out = P.assemble(sections)
    assert out.index("첫째") < out.index("둘째") < out.index("셋째")


# ── assemble: 빈 섹션 생략 (Design §8.2 #2, #3) ─────────────────────────────


def test_assemble_omits_header_when_section_is_empty():
    out = P.assemble(_sections(roles=()))
    assert "[역할]" not in out
    assert "[도구 지침]" in out


def test_assemble_returns_only_purpose_when_all_sections_empty():
    out = P.assemble(
        PromptSections(
            purpose="목적만 있습니다.", roles=(), tool_guides=(), principles=()
        )
    )
    assert out == "목적만 있습니다."


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


def test_assemble_does_not_end_with_newline():
    assert P.assemble(_sections()) == P.assemble(_sections()).rstrip()


# ── drop_hallucinated: 환각 폐기 (Design §8.2 #4 · Plan SC-04) ──────────────


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


# ── clamp_sections: 상한 절단 ────────────────────────────────────────────────


def test_clamp_sections_caps_roles_at_max():
    roles = tuple(RoleSection(title=f"r{i}", detail="d") for i in range(20))
    clamped = P.clamp_sections(_sections(roles=roles))
    assert len(clamped.roles) == P.MAX_ROLES


def test_clamp_sections_caps_principles_at_max():
    principles = tuple(f"p{i}" for i in range(50))
    clamped = P.clamp_sections(_sections(principles=principles))
    assert len(clamped.principles) == P.MAX_PRINCIPLES


def test_clamp_sections_caps_tool_guides_at_max():
    guides = tuple(_guide(f"t{i}") for i in range(80))
    clamped = P.clamp_sections(_sections(tool_guides=guides))
    assert len(clamped.tool_guides) == P.MAX_TOOL_GUIDES


def test_clamp_sections_keeps_leading_items():
    roles = tuple(RoleSection(title=f"r{i}", detail="d") for i in range(20))
    clamped = P.clamp_sections(_sections(roles=roles))
    assert clamped.roles[0].title == "r0"


def test_clamp_sections_is_noop_when_within_limits():
    sections = _sections()
    assert P.clamp_sections(sections) == sections


# ── clamp_history: 이력 절단 (Design §8.2 #6 · Q3 자체 구현) ─────────────────


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
    out = P.clamp_history([_Turn("assistant", "안녕")])
    assert out == [{"role": "assistant", "content": "안녕"}]


def test_clamp_history_handles_empty_and_none():
    assert P.clamp_history([]) == []
    assert P.clamp_history(None) == []


def test_clamp_history_accepts_dict_turns():
    """요청 스키마가 dict로 넘겨도 동작한다 (duck-typing 대신 명시 지원)."""
    assert P.clamp_history([{"role": "user", "content": "안녕"}]) == [
        {"role": "user", "content": "안녕"}
    ]


# ── fallback_sections: 규칙기반 폴백 (Design §8.2 #7 · Plan SC-02) ───────────


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
    out = P.fallback_sections((), "가" * 500)
    assert len(out.purpose) < 400


def test_fallback_sections_has_no_roles():
    assert P.fallback_sections((_meta("t1"),), "요청").roles == ()


def test_fallback_sections_has_fixed_principles():
    a = P.fallback_sections((), "요청 A").principles
    b = P.fallback_sections((), "요청 B").principles
    assert a == b
    assert len(a) == 3


def test_fallback_sections_assembles_without_error():
    out = P.assemble(P.fallback_sections((_meta("t1", "엑셀", "표 내보내기"),), "요청"))
    assert "엑셀" in out
    assert out.strip() != ""


# ── ComposedPrompt VO 기본값 ────────────────────────────────────────────────


def test_composed_prompt_defaults_are_system_owned_and_empty():
    prompt = ComposedPrompt(sections=_sections(), assembled="x")
    assert prompt.degraded is False
    assert prompt.reason is None
    assert prompt.dropped_tool_ids == ()
    assert prompt.unknown_tool_ids == ()
    assert prompt.elapsed_ms == 0


# ── 레이어 규칙 (Design §8.2 #5 · Plan SC-05 · D1) ──────────────────────────


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
