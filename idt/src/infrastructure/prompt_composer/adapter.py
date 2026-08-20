"""시스템 프롬프트 생성 LLM 어댑터.

Design Ref: §2.4 P2/P3/P5 · §4.4 · E1~E4.

**`_PromptDraft` 를 쓰는 이유** (Design §1.3): 시스템이 계산하는 필드
(`degraded` / `dropped_tool_ids` / `unknown_tool_ids` / `elapsed_ms`)가 LLM
스키마에 아예 없으므로, LLM 이 그 값을 오염시킬 경로 자체가 존재하지 않는다.
선행 사이클의 intent 모듈이 `IntentResult` 를 겸용하고 3층 방어를 쌓았다가
계산 필드가 늘면서 실패한 선례를 따르지 않는다
(`infrastructure/intent/adapter.py:6-10`). 본 모듈은 결과를 DB 에 영속하므로
오염값이 되돌릴 수 없게 남는다는 점에서 대가가 더 크다.

Plan SC-02: 모든 실패(예외·타임아웃·스키마 위반·빈 결과)를 degraded=True 로
graceful degrade 한다. **예외를 밖으로 던지지 않는다** (P5) — 호출부(UseCase)에
try/except 가 생기면 실패 경로가 2벌이 된다.
"""
import asyncio
import time
from typing import Protocol

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.prompt_composer.policies import PromptAssemblyPolicy
from src.domain.prompt_composer.schemas import (
    ContextSection,
    PromptSections,
    RoleSection,
    ToolGuide,
    ToolMeta,
    WorkflowSection,
)
from src.infrastructure.config.prompt_composer_config import PromptComposerConfig
from src.infrastructure.prompt_composer import prompts

_REASON_ERROR = "error"
_REASON_TIMEOUT = "timeout"
_REASON_SCHEMA = "schema"
_REASON_EMPTY = "empty"


# ── LLM 이 보는 유일한 스키마 (P2) ───────────────────────────────────────────


class _RoleDraft(BaseModel):
    title: str = Field(description="역할 이름 (짧게)")
    detail: str = Field(default="", description="이 역할이 무엇을 하는지")


class _GuideDraft(BaseModel):
    """도구 지침. **name 필드가 없다** — 표기 이름은 카탈로그가 정한다."""

    tool_id: str = Field(description="위 도구 목록에 있는 tool_id 그대로")
    when: str = Field(default="", description="언제 이 도구를 사용하는지")
    how: str = Field(default="", description="어떤 입력으로 호출하는지")
    caution: str = Field(default="", description="주의사항")


class _ContextDraft(BaseModel):
    """prompt-depth §3.2 / FR-02."""

    constraints: list[str] = Field(
        default_factory=list,
        description="반드시 지켜야 할 것과 하지 말아야 할 것",
    )
    background: list[str] = Field(
        default_factory=list, description="이 에이전트가 알아야 할 배경·전제"
    )


class _WorkflowDraft(BaseModel):
    """prompt-depth §3.2 / FR-03."""

    situation: str = Field(description="이 절차가 적용되는 상황")
    steps: list[str] = Field(
        default_factory=list, description="순서대로 수행할 단계"
    )


class _PromptDraft(BaseModel):
    """LLM 이 채우는 값만 담은 초안 (prompt-depth §3.2 — 7섹션).

    시스템이 계산하는 degraded / dropped_tool_ids / unknown_tool_ids /
    elapsed_ms 는 여기 없다 (P2).

    **strict 불변식** (FR-05 / Plan R-01): 이 스키마의 재귀 전개에 자유 키
    dict(`dict[str, X]`)가 0건이어야 한다. 하나라도 있으면 OpenAI structured
    outputs 가 매 호출 400 을 돌려 판정이 **항상** degraded 로 떨어지고, 폴백이
    그 사실을 가린다 (intent 모듈에서 3개월 은폐된 실사례).
    `tests/infrastructure/prompt_composer/test_adapter.py` 의 재귀 탐색 테스트가
    이를 정적으로 차단한다.

    필드 이름은 `PromptSections` 와 1:1 이다 — 매핑(`_to_sections`)이 기계적이고,
    어긋나면 필드 집합 동등성 테스트가 잡는다 (§3.4).
    """

    purpose: str = Field(description="이 에이전트가 무엇을 하는지 1~2문장")
    identity: str = Field(
        default="",
        description="어떤 성격·전문성을 가진 존재인지, 누구를 위해 일하는지",
    )
    context: _ContextDraft | None = None
    roles: list[_RoleDraft] = Field(default_factory=list)
    tool_guides: list[_GuideDraft] = Field(default_factory=list)
    workflows: list[_WorkflowDraft] = Field(default_factory=list)
    style: str = Field(default="", description="응답 말투·형식·구조")
    principles: list[str] = Field(
        default_factory=list, description="동작 원칙 (응답 언어·거절 조건 등)"
    )


class PromptChain(Protocol):
    """프롬프트→LLM→구조화 출력 체인의 최소 계약 (테스트 대역 주입용)."""

    async def ainvoke(self, payload: dict, config: dict | None = None) -> object: ...


class LLMPromptGeneratorAdapter:
    """LangChain structured output 기반 프롬프트 생성기 (`PromptGeneratorPort`)."""

    def __init__(
        self,
        logger: LoggerInterface,
        config: PromptComposerConfig | None = None,
        chain: PromptChain | None = None,
    ) -> None:
        self._logger = logger
        self._config = config or PromptComposerConfig()
        self._chain: PromptChain = (
            chain if chain is not None else self._build_chain()
        )

    def _build_chain(self) -> PromptChain:
        llm = ChatOpenAI(
            model=self._config.PROMPT_COMPOSER_MODEL,
            temperature=self._config.PROMPT_COMPOSER_TEMPERATURE,
        )
        prompt = ChatPromptTemplate.from_messages(
            [("system", prompts.SYSTEM), ("human", prompts.HUMAN)]
        )
        chain: PromptChain = prompt | llm.with_structured_output(_PromptDraft)
        return chain

    async def generate(
        self,
        user_request: str,
        metas: tuple[ToolMeta, ...],
        intent: dict | None,
        history: list[dict],
        request_id: str,
    ) -> tuple[PromptSections, bool, str | None, int]:
        """→ (sections, degraded, reason, elapsed_ms). 예외를 던지지 않는다 (P5)."""
        selected = self._select_metas(metas, request_id)
        payload = self._build_payload(user_request, selected, intent, history)
        started = time.perf_counter()
        try:
            raw = await asyncio.wait_for(
                self._chain.ainvoke(payload),
                timeout=self._config.PROMPT_COMPOSER_TIMEOUT_SEC,
            )
            draft = _coerce(raw)
        except TimeoutError:
            return self._degrade(_REASON_TIMEOUT, None, metas, user_request,
                                 request_id, started, warn=True)
        except Exception as e:  # noqa: BLE001 — 어떤 예외도 새어 나가면 안 된다
            reason = _REASON_SCHEMA if _is_schema_error(e) else _REASON_ERROR
            return self._degrade(reason, e, metas, user_request, request_id,
                                 started)

        if not draft.purpose.strip():
            return self._degrade(_REASON_EMPTY, None, metas, user_request,
                                 request_id, started, warn=True)

        sections = _to_sections(draft, selected)
        elapsed = _elapsed_ms(started)
        self._log_success(sections, request_id, elapsed)
        return sections, False, None, elapsed

    # ── 내부 ────────────────────────────────────────────────────────────

    def _select_metas(
        self, metas: tuple[ToolMeta, ...], request_id: str
    ) -> tuple[ToolMeta, ...]:
        """프롬프트에 실을 도구 상한 적용. 초과분은 절단 + 경고 (Plan R7)."""
        limit = self._config.PROMPT_COMPOSER_MAX_TOOLS
        if len(metas) <= limit:
            return metas
        self._logger.warning(
            "prompt composer tools truncated",
            request_id=request_id,
            total=len(metas),
            max_tools=limit,
        )
        return metas[:limit]

    def _build_payload(
        self,
        user_request: str,
        metas: tuple[ToolMeta, ...],
        intent: dict | None,
        history: list[dict],
    ) -> dict:
        return {
            "tools_block": prompts.tools_block(metas),
            "intent_block": prompts.intent_block(intent),
            "history_block": prompts.history_block(history),
            "user_request": user_request,
        }

    def _log_success(
        self, sections: PromptSections, request_id: str, elapsed: int
    ) -> None:
        """프롬프트 본문은 남기지 않는다 — 사용자 입력이 섞여 PII 위험이 있다.

        prompt-depth §6.2 — 섹션별 카운트를 남긴다. 어떤 섹션이 상습적으로
        비는지(R-02) 와 실제 생성 길이(R-03 토큰 비용)는 실측 없이 판단할 수 없다.
        """
        context = sections.context
        self._logger.info(
            "prompt composed",
            request_id=request_id,
            degraded=False,
            latency_ms=elapsed,
            role_count=len(sections.roles),
            guide_count=len(sections.tool_guides),
            principle_count=len(sections.principles),
            identity_len=len(sections.identity),
            constraint_count=len(context.constraints) if context else 0,
            background_count=len(context.background) if context else 0,
            workflow_count=len(sections.workflows),
            style_len=len(sections.style),
            assembled_chars=len(PromptAssemblyPolicy.assemble(sections)),
        )

    def _degrade(
        self,
        reason: str,
        exception: Exception | None,
        metas: tuple[ToolMeta, ...],
        user_request: str,
        request_id: str,
        started: float,
        warn: bool = False,
    ) -> tuple[PromptSections, bool, str, int]:
        """생성 실패 → 규칙기반 폴백 섹션 (Design E1~E4)."""
        log = self._logger.warning if warn else self._logger.error
        log(
            f"prompt generation {reason}, fallback=degraded",
            exception=exception,
            request_id=request_id,
            latency_ms=_elapsed_ms(started),
        )
        sections = PromptAssemblyPolicy.fallback_sections(metas, user_request)
        return sections, True, reason, _elapsed_ms(started)


# ── 매핑 (P3 — Draft → VO 변환은 이 함수 하나뿐) ─────────────────────────────


def _to_sections(
    draft: _PromptDraft, metas: tuple[ToolMeta, ...]
) -> PromptSections:
    """Draft → 도메인 VO. 도구 표기 이름은 카탈로그 값으로 채운다.

    후보 밖 tool_id 는 여기서 거르지 않는다 — 폐기와 관측은
    `PromptAssemblyPolicy.drop_hallucinated` 의 책임이다 (단일 책임).
    """
    by_id = {meta.tool_id: meta for meta in metas}
    sections = PromptSections(
        purpose=draft.purpose.strip(),
        identity=draft.identity.strip(),
        context=_to_context(draft.context),
        roles=tuple(
            RoleSection(title=r.title, detail=r.detail) for r in draft.roles
        ),
        tool_guides=tuple(
            ToolGuide(
                tool_id=g.tool_id,
                name=_display_name(g.tool_id, by_id),
                when=g.when,
                how=g.how,
                caution=g.caution,
            )
            for g in draft.tool_guides
        ),
        workflows=tuple(
            WorkflowSection(
                situation=w.situation.strip(),
                steps=tuple(s for s in w.steps if s.strip()),
            )
            for w in draft.workflows
        ),
        style=draft.style.strip(),
        principles=tuple(p for p in draft.principles if p.strip()),
    )
    return PromptAssemblyPolicy.clamp_sections(sections)


def _to_context(draft: _ContextDraft | None) -> ContextSection | None:
    """LLM 이 생략한 `context` 는 None 으로 남긴다 — "없음"과 "비었음"을 구분한다."""
    if draft is None:
        return None
    return ContextSection(
        constraints=tuple(c for c in draft.constraints if c.strip()),
        background=tuple(b for b in draft.background if b.strip()),
    )


def _display_name(tool_id: str, by_id: dict[str, ToolMeta]) -> str:
    meta = by_id.get(tool_id)
    return meta.name if meta is not None else tool_id


def _coerce(raw: object) -> _PromptDraft:
    """구조화 출력이 dict 로 와도 받아들인다. 스키마 위반이면 ValidationError."""
    if isinstance(raw, _PromptDraft):
        return raw
    return _PromptDraft.model_validate(raw)


def _is_schema_error(exception: Exception) -> bool:
    """pydantic ValidationError 를 이름으로 판별한다 (import 없이 E3 구분)."""
    return type(exception).__name__ == "ValidationError"


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
