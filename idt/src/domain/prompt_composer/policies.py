"""프롬프트 조립·폐기·절단·폴백 규칙 — 순수 함수만.

Design Ref: §3.2 / §2.4 P4.

Plan SC-03 — `assemble()` 은 시간·UUID·랜덤을 쓰지 않는다. 인자만으로 결정되므로
동일 입력은 항상 바이트 동일 출력을 낸다. 이 성질이 섹션 단위 재생성·diff 의 전제다.

Design Q3 — `clamp_history` 는 `agent_composer.ComposePolicy.clamp_history` 를
재사용하지 않고 복제한다. 재사용하면 domain/prompt_composer → domain/agent_composer
의존이 생겨 "기존 경로 물리적 무변경"(D1)이 첫 지점에서 깨진다.
"""
from src.domain.prompt_composer.schemas import (
    PromptSections,
    RoleSection,
    ToolGuide,
    ToolMeta,
)

_ROLES_HEADER = "[역할]"
_TOOLS_HEADER = "[도구 지침]"
_PRINCIPLES_HEADER = "[동작 원칙]"

_FALLBACK_PURPOSE_BASE = "사용자의 요청을 처리하는 에이전트입니다."
_FALLBACK_REQUEST_PREFIX = " 요청 요약: "
_FALLBACK_REQUEST_CHARS = 200
_FALLBACK_PRINCIPLES = (
    "한국어로 답한다",
    "도구 결과에 없는 내용은 지어내지 않는다",
    "확인할 수 없으면 모른다고 답한다",
)


class PromptAssemblyPolicy:
    """시스템 프롬프트의 조립 규칙 모음. 상태를 갖지 않는다."""

    MAX_ROLES = 6
    MAX_TOOL_GUIDES = 50
    MAX_PRINCIPLES = 10
    MAX_HISTORY_TURNS = 20
    MAX_HISTORY_TURN_CHARS = 1000

    # ── 조립 ────────────────────────────────────────────────────────────

    @staticmethod
    def assemble(sections: PromptSections) -> str:
        """섹션 → 최종 시스템 프롬프트 문자열 (Design §3.2).

        Plan SC-03: 결정적. 빈 섹션은 헤더째 생략하며 끝 개행을 남기지 않는다.
        """
        blocks: list[str] = [sections.purpose.strip()]
        blocks.append(_role_block(sections.roles))
        blocks.append(_tool_block(sections.tool_guides))
        blocks.append(_principle_block(sections.principles))
        return "\n\n".join(b for b in blocks if b).rstrip()

    # ── 환각 폐기 ───────────────────────────────────────────────────────

    @staticmethod
    def drop_hallucinated(
        sections: PromptSections, known: dict[str, ToolMeta]
    ) -> tuple[PromptSections, tuple[str, ...]]:
        """후보에 없는 tool_id 의 지침을 폐기하고 이름을 카탈로그 값으로 되돌린다.

        Plan SC-04 / Design E5. 프롬프트의 "목록 밖 도구 금지" 지시는 신뢰하지
        않는다 — 실제 차단은 여기서 한다.

        Returns:
            (정제된 섹션, 폐기된 tool_id 튜플)
        """
        kept: list[ToolGuide] = []
        dropped: list[str] = []
        seen: set[str] = set()
        for guide in sections.tool_guides:
            meta = known.get(guide.tool_id)
            if meta is None:
                dropped.append(guide.tool_id)
                continue
            if guide.tool_id in seen:
                continue
            seen.add(guide.tool_id)
            kept.append(_with_catalog_name(guide, meta))
        return _replace_guides(sections, tuple(kept)), tuple(dropped)

    # ── 절단 ────────────────────────────────────────────────────────────

    @staticmethod
    def clamp_sections(sections: PromptSections) -> PromptSections:
        """섹션별 항목 수 상한 적용. 앞쪽 항목을 유지한다."""
        cls = PromptAssemblyPolicy
        return PromptSections(
            purpose=sections.purpose,
            roles=sections.roles[: cls.MAX_ROLES],
            tool_guides=sections.tool_guides[: cls.MAX_TOOL_GUIDES],
            principles=sections.principles[: cls.MAX_PRINCIPLES],
        )

    @staticmethod
    def clamp_history(turns) -> list[dict]:
        """최근 N턴만 유지하고 턴당 content 를 절단한다 (Design Q3 — 자체 구현).

        입력은 role/content 속성을 가진 객체 또는 dict 목록,
        출력은 LLM messages 호환 {role, content} dict 목록이다.
        """
        if not turns:
            return []
        cls = PromptAssemblyPolicy
        recent = list(turns)[-cls.MAX_HISTORY_TURNS :]
        return [
            {
                "role": _turn_field(turn, "role"),
                "content": _turn_field(turn, "content")[
                    : cls.MAX_HISTORY_TURN_CHARS
                ],
            }
            for turn in recent
        ]

    # ── 폴백 ────────────────────────────────────────────────────────────

    @staticmethod
    def fallback_sections(
        metas: tuple[ToolMeta, ...], user_request: str
    ) -> PromptSections:
        """LLM 실패 시 도구 메타만으로 조립하는 규칙기반 섹션 (Plan SC-02).

        역할은 생성 근거가 없으므로 비운다. 원칙은 고정 3개다 — 요청 내용과
        무관하게 같은 값이어야 폴백임이 관측으로 드러난다.
        """
        return PromptSections(
            purpose=_fallback_purpose(user_request),
            roles=(),
            tool_guides=tuple(
                ToolGuide(
                    tool_id=meta.tool_id,
                    name=meta.name,
                    when=meta.description,
                    how="",
                    caution="",
                )
                for meta in metas
            ),
            principles=_FALLBACK_PRINCIPLES,
        )


# ── 조립 헬퍼 (함수 길이 40줄 규칙 · if 중첩 2단 규칙) ───────────────────────


def _role_block(roles: tuple[RoleSection, ...]) -> str:
    if not roles:
        return ""
    lines = "\n".join(f"- {r.title}: {r.detail}" for r in roles)
    return f"{_ROLES_HEADER}\n{lines}"


def _tool_block(guides: tuple[ToolGuide, ...]) -> str:
    if not guides:
        return ""
    lines = "\n".join(_guide_lines(g) for g in guides)
    return f"{_TOOLS_HEADER}\n{lines}"


def _guide_lines(guide: ToolGuide) -> str:
    """`- {name} ({tool_id}): {when} / {how}` + 선택적 주의 줄.

    when·how 중 빈 값은 구분자째 생략한다 — 폴백 경로(how="")에서 매달린
    " / " 가 남지 않아야 한다.
    """
    detail = " / ".join(p for p in (guide.when.strip(), guide.how.strip()) if p)
    head = f"- {guide.name} ({guide.tool_id}): {detail}".rstrip(": ")
    caution = guide.caution.strip()
    if not caution:
        return head
    return f"{head}\n  주의: {caution}"


def _principle_block(principles: tuple[str, ...]) -> str:
    if not principles:
        return ""
    lines = "\n".join(f"- {p}" for p in principles)
    return f"{_PRINCIPLES_HEADER}\n{lines}"


def _with_catalog_name(guide: ToolGuide, meta: ToolMeta) -> ToolGuide:
    """표기 이름을 카탈로그 값으로 고정한다 (LLM 의 개명 방지)."""
    if guide.name == meta.name:
        return guide
    return ToolGuide(
        tool_id=guide.tool_id,
        name=meta.name,
        when=guide.when,
        how=guide.how,
        caution=guide.caution,
    )


def _replace_guides(
    sections: PromptSections, guides: tuple[ToolGuide, ...]
) -> PromptSections:
    return PromptSections(
        purpose=sections.purpose,
        roles=sections.roles,
        tool_guides=guides,
        principles=sections.principles,
    )


def _turn_field(turn, key: str) -> str:
    """객체 속성과 dict 키를 모두 받는다."""
    if isinstance(turn, dict):
        return str(turn.get(key, ""))
    return str(getattr(turn, key, ""))


def _fallback_purpose(user_request: str) -> str:
    excerpt = " ".join(user_request.split())[:_FALLBACK_REQUEST_CHARS]
    if not excerpt:
        return _FALLBACK_PURPOSE_BASE
    return f"{_FALLBACK_PURPOSE_BASE}{_FALLBACK_REQUEST_PREFIX}{excerpt}"
