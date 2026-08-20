"""프롬프트 조립·폐기·절단·폴백 규칙 — 순수 함수만.

Design Ref: §3.2 / §2.4 P4 (prompt-composer) · §4.3 / §5 (prompt-depth).

Plan SC-03 / prompt-depth FR-08 — `assemble()` 은 시간·UUID·랜덤을 쓰지 않는다.
인자만으로 결정되므로 동일 입력은 항상 바이트 동일 출력을 낸다. 이 성질이 섹션
단위 재생성·diff 의 전제다.

prompt-depth §4.3 — 조립 표기가 대괄호 블록에서 **마크다운 헤딩**으로 바뀌었다.
섹션 번호와 에이전트 이름 제목을 쓰지 않는다(A-3/A-4): 빈 섹션을 헤더째 생략하는
규칙과 번호는 양립하지 않고, 프롬프트 생성 시점에 이름은 아직 확정값이 아니다.

prompt-depth §5.3 — 부분 교체는 전부 `dataclasses.replace()` 로 한다. 필드를
하나씩 나열해 재구성하면 섹션이 늘 때마다 신규 필드가 조용히 유실된다
(실제로 `_replace_guides` 가 그 상태였다).

Design Q3 — `clamp_history` 는 `agent_composer.ComposePolicy.clamp_history` 를
재사용하지 않고 복제한다. 재사용하면 domain/prompt_composer → domain/agent_composer
의존이 생겨 "기존 경로 물리적 무변경"(D1)이 첫 지점에서 깨진다.
"""
from dataclasses import replace

from src.domain.prompt_composer.schemas import (
    ContextSection,
    PromptSections,
    RoleSection,
    ToolGuide,
    ToolMeta,
    WorkflowSection,
)

# ── 섹션 헤딩 (prompt-depth §4.3 — 출력 계약) ────────────────────────────────
_H_IDENTITY = "## Role and Identity"
_H_CONTEXT = "## Context"
_H_ROLES = "## Core Responsibilities"
_H_TOOLS = "## Tool Guidelines"
_H_WORKFLOW = "## Workflow"
_H_STYLE = "## Communication Style"
_H_NOTES = "## Important Notes"

_BACKGROUND_LABEL = "배경:"

_FALLBACK_PURPOSE_BASE = "사용자의 요청을 처리하는 에이전트입니다."
_FALLBACK_REQUEST_PREFIX = " 요청 요약: "
_FALLBACK_REQUEST_CHARS = 200

# prompt-depth §5.1 (A-6) — 폴백은 고정 문구로 7섹션을 전부 채운다.
# 값이 전부 모듈 상수라는 사실이 폴백 관측성을 유지한다: 요청이 달라도 같은
# 문구가 나오므로 출력만 보고 폴백임을 식별할 수 있다. 1차 신호(degraded=True /
# reason / steps.prompt=DEGRADED)는 그대로다.
_FALLBACK_IDENTITY = "사용자의 요청을 처리하는 범용 에이전트입니다."
_FALLBACK_CONTEXT = ContextSection(
    constraints=("제공된 제약 조건이 없으므로 일반적인 안전 기준을 따른다",),
    background=(),
)
_FALLBACK_ROLES = (
    RoleSection(
        title="요청 처리",
        detail="사용자의 요청을 확인하고 가능한 범위에서 답한다",
    ),
)
_FALLBACK_WORKFLOWS = (
    WorkflowSection(
        situation="일반 요청",
        steps=(
            "요청 내용을 확인한다",
            "필요하면 도구를 사용한다",
            "결과를 정리해 답한다",
        ),
    ),
)
_FALLBACK_STYLE = "한국어로 간결하게 답한다."
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
    # prompt-depth §5.2 — 신규 섹션 상한. 평문 섹션은 항목 수가 없으므로
    # 길이로 자른다.
    MAX_CONSTRAINTS = 10
    MAX_BACKGROUND = 5
    MAX_WORKFLOWS = 5
    MAX_WORKFLOW_STEPS = 8
    MAX_IDENTITY_CHARS = 500
    MAX_STYLE_CHARS = 500

    # ── 조립 ────────────────────────────────────────────────────────────

    @staticmethod
    def assemble(sections: PromptSections) -> str:
        """섹션 → 최종 시스템 프롬프트 문자열 (prompt-depth §4.3).

        FR-07/FR-08: 결정적. `purpose` 는 헤더 없는 리드 문단으로 남고, 나머지는
        마크다운 헤딩 블록이 된다. 빈 섹션은 헤더째 생략하며 끝 개행을 남기지
        않는다.
        """
        blocks = (
            sections.purpose.strip(),
            _text_block(_H_IDENTITY, sections.identity),
            _context_block(sections.context),
            _role_block(sections.roles),
            _tool_block(sections.tool_guides),
            _workflow_block(sections.workflows),
            _text_block(_H_STYLE, sections.style),
            _bullet_block(_H_NOTES, sections.principles),
        )
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
        # prompt-depth §5.3 — replace() 로 교체한다. 필드 나열식 재구성은
        # 섹션이 늘 때마다 신규 필드를 떨어뜨린다.
        return replace(sections, tool_guides=tuple(kept)), tuple(dropped)

    # ── 절단 ────────────────────────────────────────────────────────────

    @staticmethod
    def clamp_sections(sections: PromptSections) -> PromptSections:
        """섹션별 상한 적용. 항목은 앞쪽을, 평문은 앞부분을 유지한다 (FR-09)."""
        cls = PromptAssemblyPolicy
        return replace(
            sections,
            identity=sections.identity[: cls.MAX_IDENTITY_CHARS],
            context=_clamp_context(sections.context),
            roles=sections.roles[: cls.MAX_ROLES],
            tool_guides=sections.tool_guides[: cls.MAX_TOOL_GUIDES],
            workflows=tuple(
                _clamp_workflow(w) for w in sections.workflows[: cls.MAX_WORKFLOWS]
            ),
            style=sections.style[: cls.MAX_STYLE_CHARS],
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

        prompt-depth FR-10 / A-6 — 신규 섹션까지 고정 문구로 채워 7섹션 구조를
        유지한다. `purpose` 만 요청 발췌를 담고 나머지는 전부 모듈 상수다
        (§5.1 — 상수라는 사실이 폴백 관측성을 유지한다).

        `tool_guides` 는 실제 메타에서 만든다 — 폴백이라도 없는 도구를 지어내지
        않는다. 도구가 0개면 조립 단계에서 해당 섹션만 생략된다 (§4.3-4).
        """
        return PromptSections(
            purpose=_fallback_purpose(user_request),
            identity=_FALLBACK_IDENTITY,
            context=_FALLBACK_CONTEXT,
            roles=_FALLBACK_ROLES,
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
            workflows=_FALLBACK_WORKFLOWS,
            style=_FALLBACK_STYLE,
            principles=_FALLBACK_PRINCIPLES,
        )


# ── 조립 헬퍼 (함수 길이 40줄 규칙 · if 중첩 2단 규칙) ───────────────────────


def _text_block(header: str, body: str) -> str:
    """평문 섹션 — identity / style 공용. 빈 값이면 헤더째 생략한다."""
    stripped = body.strip()
    if not stripped:
        return ""
    return f"{header}\n{stripped}"


def _bullet_block(header: str, items: tuple[str, ...]) -> str:
    """단순 불릿 섹션 — principles 및 context 하위 목록 공용."""
    lines = [item.strip() for item in items if item.strip()]
    if not lines:
        return ""
    body = "\n".join(f"- {line}" for line in lines)
    return f"{header}\n{body}"


def _context_block(context: ContextSection | None) -> str:
    """제약 불릿 + (있으면) 배경 불릿. 둘 다 비면 헤더째 생략한다 (FR-02)."""
    if context is None:
        return ""
    constraints = _bullet_block(_H_CONTEXT, context.constraints)
    background = _bullet_block(_BACKGROUND_LABEL, context.background)
    if not constraints:
        return f"{_H_CONTEXT}\n{background}" if background else ""
    if not background:
        return constraints
    return f"{constraints}\n\n{background}"


def _role_block(roles: tuple[RoleSection, ...]) -> str:
    if not roles:
        return ""
    lines = "\n".join(f"- {r.title}: {r.detail}" for r in roles)
    return f"{_H_ROLES}\n{lines}"


def _tool_block(guides: tuple[ToolGuide, ...]) -> str:
    if not guides:
        return ""
    lines = "\n".join(_guide_lines(g) for g in guides)
    return f"{_H_TOOLS}\n{lines}"


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


def _workflow_block(workflows: tuple[WorkflowSection, ...]) -> str:
    """상황별 절차 (FR-03). 단계가 없는 항목은 통째로 생략한다 — 상황 제목만
    남으면 프롬프트에 아무 지시도 되지 못한다."""
    entries = [_workflow_entry(w) for w in workflows]
    body = "\n\n".join(e for e in entries if e)
    if not body:
        return ""
    return f"{_H_WORKFLOW}\n{body}"


def _workflow_entry(workflow: WorkflowSection) -> str:
    steps = [s.strip() for s in workflow.steps if s.strip()]
    if not steps:
        return ""
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, start=1))
    situation = workflow.situation.strip()
    if not situation:
        return numbered
    return f"### {situation}\n{numbered}"


def _with_catalog_name(guide: ToolGuide, meta: ToolMeta) -> ToolGuide:
    """표기 이름을 카탈로그 값으로 고정한다 (LLM 의 개명 방지)."""
    if guide.name == meta.name:
        return guide
    return replace(guide, name=meta.name)


# ── 절단 헬퍼 ───────────────────────────────────────────────────────────────


def _clamp_context(context: ContextSection | None) -> ContextSection | None:
    """None 은 None 으로 남긴다 — "없음"과 "비어 있음"의 구분을 지운다."""
    if context is None:
        return None
    cls = PromptAssemblyPolicy
    return replace(
        context,
        constraints=context.constraints[: cls.MAX_CONSTRAINTS],
        background=context.background[: cls.MAX_BACKGROUND],
    )


def _clamp_workflow(workflow: WorkflowSection) -> WorkflowSection:
    return replace(
        workflow, steps=workflow.steps[: PromptAssemblyPolicy.MAX_WORKFLOW_STEPS]
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
