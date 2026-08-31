"""PresentationGenerationUseCase — blueprint + 근거 → PPTX(+PDF).

Design Ref: golden-sample-blueprint §2.2 (생성 흐름) / §6.3 (degraded 경계) / D5 /
FR-12~15
- plan: SlidePlanner → SlidePlanValidationPolicy. 미존재 pattern_id 가 있거나 계획이
  비면 피드백과 함께 1회 재시도, 그래도 위반인 슬라이드는 제외 + warning.
  계획이 비면 예외.
- write: 슬라이드당 SlotWriter 1회(Semaphore 동시). 작성 실패 → 빈 슬롯 + warning,
  슬롯 위반 → 해당 슬롯 제외 + warning (SlotContentPolicy).
- render → AttachmentStore 저장 → output_format=pdf 면 MCP 변환
  (실패/미설정 → PPTX 만 + warning).
- LLM 출력은 구조화 데이터로만 렌더러에 전달된다 (§7).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from src.domain.agent_attachment.interfaces import AttachmentStoreInterface
from src.domain.agent_attachment.value_objects import AttachmentType
from src.domain.blueprint.errors import PresentationGenerateError
from src.domain.blueprint.interfaces import SlideRendererPort
from src.domain.blueprint.policies import (
    SlidePlanValidationPolicy,
    SlotContentPolicy,
    TocContentPolicy,
)
from src.domain.blueprint.schemas import SlideContentDraft, SlidePlanDraft
from src.domain.blueprint.tool_config import PresentationGeneratorToolConfig
from src.domain.blueprint.value_objects import (
    ChartSpec,
    DocumentBlueprint,
    PagePattern,
    PatternKind,
    PresentationResult,
    SlideContent,
    SlidePlan,
    SlotContent,
    SlotKind,
    TableSpec,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class SlidePlannerPort(Protocol):
    last_usage: dict | None

    async def plan(
        self,
        blueprint: DocumentBlueprint,
        topic: str,
        instruction: str,
        evidence: str,
        max_slides: int,
        feedback: Sequence[str] | None,
    ) -> SlidePlanDraft: ...


class SlotWriterPort(Protocol):
    usages: list[dict]

    async def write(
        self,
        blueprint: DocumentBlueprint,
        pattern: PagePattern,
        plan: SlidePlan,
        evidence: str,
        conversation: str,
        index: int,
        total: int,
    ) -> SlideContentDraft: ...


class PptxToPdfPort(Protocol):
    async def to_pdf_from_pptx(
        self, pptx_bytes: bytes, mcp_tool_id: str, request_id: str
    ) -> bytes: ...


@dataclass(frozen=True)
class _Planned:
    plans: list[SlidePlan]
    warnings: list[str]


class PresentationGenerationUseCase:
    def __init__(
        self,
        planner_factory: Callable[[Any, list | None], SlidePlannerPort],
        writer_factory: Callable[[Any, list | None], SlotWriterPort],
        renderer: SlideRendererPort,
        store: AttachmentStoreInterface,
        converter: PptxToPdfPort | None,
        logger: LoggerInterface,
        concurrency: int = 4,
        input_max_chars: int = 20000,
    ) -> None:
        self._planner_factory = planner_factory
        self._writer_factory = writer_factory
        self._renderer = renderer
        self._store = store
        self._converter = converter
        self._logger = logger
        self._concurrency = concurrency
        self._input_max_chars = input_max_chars

    # ── public ────────────────────────────────────────────────────────────────

    async def generate(
        self,
        llm: Any,
        blueprint: DocumentBlueprint,
        assets: Mapping[str, bytes],
        tool_config: PresentationGeneratorToolConfig,
        evidence_block: str,
        conversation_block: str,
        user_instruction: str,
        owner_user_id: str,
        request_id: str,
        callbacks: list | None = None,
    ) -> PresentationResult:
        evidence = self._truncate(evidence_block)
        conversation = self._truncate(conversation_block)
        planner = self._planner_factory(llm, callbacks)
        writer = self._writer_factory(llm, callbacks)

        planned = await self._plan(
            planner, blueprint, user_instruction, evidence, tool_config
        )
        slides = await self._write_all(
            writer, blueprint, planned.plans, evidence, conversation
        )
        warnings = planned.warnings + [w for s in slides for w in s.warnings]
        slides = self._drop_empty(blueprint, slides, warnings)

        pptx = self._renderer.render(blueprint, slides, assets, blueprint.font_mapping)
        stored = self._save(pptx, f"{blueprint.name}.pptx", owner_user_id)
        pdf_file_id = await self._maybe_pdf(
            pptx, blueprint, tool_config, owner_user_id, request_id, warnings
        )
        result = _result(stored, pdf_file_id, slides, warnings, planner, writer)
        self._log_done(request_id, blueprint, result)
        return result

    def _drop_empty(
        self,
        blueprint: DocumentBlueprint,
        slides: Sequence[SlideContent],
        warnings: list[str],
    ) -> list[SlideContent]:
        """그릴 것이 하나도 없는 슬라이드를 제외한다 (pptx-font-fidelity FR-04).

        표지·이미지 슬롯이 있는 패턴은 내용이 없어도 배경/에셋을 그리므로 남긴다.
        """
        kept: list[SlideContent] = []
        for slide in slides:
            pattern = blueprint.pattern(slide.plan.pattern_id)
            if pattern is None or _has_renderable(slide, pattern):
                kept.append(slide)
                continue
            reason = f"slide {slide.plan.index}: 내용 없음 — 슬라이드 제외"
            self._logger.warning(
                "blueprint.render slide skipped — no renderable content",
                slide=slide.plan.index,
                pattern_id=slide.plan.pattern_id,
            )
            warnings.append(reason)
        return kept

    def _save(self, data: bytes, filename: str, owner_user_id: str):
        return self._store.save(
            file_bytes=data,
            filename=filename,
            attachment_type=AttachmentType.DOCUMENT,
            owner_user_id=owner_user_id,
        )

    # ── plan ──────────────────────────────────────────────────────────────────

    async def _plan(
        self,
        planner: SlidePlannerPort,
        blueprint: DocumentBlueprint,
        instruction: str,
        evidence: str,
        cfg: PresentationGeneratorToolConfig,
    ) -> _Planned:
        async def attempt(feedback: list[str] | None):
            draft = await planner.plan(
                blueprint,
                blueprint.name,
                instruction,
                evidence,
                cfg.max_slides,
                feedback,
            )
            return _validate(draft, blueprint, cfg.max_slides)

        outcome = await attempt(None)
        feedback = [r for r in outcome.rejected if "unknown pattern_id" in r]
        if feedback or not outcome.kept:
            self._logger.warning(
                "blueprint.plan rejected — retrying once",
                rejected=list(outcome.rejected),
            )
            retry = await attempt(feedback or None)
            if len(retry.kept) >= len(outcome.kept):
                outcome = retry
        if not outcome.kept:
            raise PresentationGenerateError(
                "슬라이드 계획이 비어 있습니다 (재시도 포함 2회)"
            )
        return _Planned(plans=list(outcome.kept), warnings=list(outcome.rejected))

    # ── write ─────────────────────────────────────────────────────────────────

    async def _write_all(
        self,
        writer: SlotWriterPort,
        blueprint: DocumentBlueprint,
        plans: Sequence[SlidePlan],
        evidence: str,
        conversation: str,
    ) -> list[SlideContent]:
        sem = asyncio.Semaphore(self._concurrency)
        total = len(plans)

        kinds = {p.id: p.kind for p in blueprint.patterns}

        async def one(plan: SlidePlan) -> SlideContent:
            pattern = blueprint.pattern(plan.pattern_id)
            assert pattern is not None  # 계획 검증 통과
            # Design Ref: blueprint-slot-content-fill FR-04 — 목차는 계획 제목에서
            # 결정론적으로 만든다. LLM 을 경유하지 않는다.
            if pattern.kind is PatternKind.TOC:
                content, toc_warnings = TocContentPolicy.apply(
                    plan, plans, kinds, pattern
                )
                if content is not None:
                    return content
                self._logger.warning(
                    "blueprint.toc deterministic fill failed — writer fallback",
                    slide=plan.index,
                    reasons=list(toc_warnings),
                )
            async with sem:
                return await self._write_one(
                    writer, blueprint, pattern, plan, evidence, conversation, total
                )

        return list(await asyncio.gather(*(one(p) for p in plans)))

    async def _write_one(
        self,
        writer: SlotWriterPort,
        blueprint: DocumentBlueprint,
        pattern: PagePattern,
        plan: SlidePlan,
        evidence: str,
        conversation: str,
        total: int,
    ) -> SlideContent:
        try:
            draft = await writer.write(
                blueprint, pattern, plan, evidence, conversation, plan.index, total
            )
        except Exception as e:  # noqa: BLE001 — 건별 degraded (§6.3)
            self._logger.warning(
                "blueprint.write slide failed — empty slots",
                slide=plan.index,
                exception=e,
            )
            return SlideContent(plan, (), (f"slide {plan.index}: writer failed ({e})",))
        contents, shape_errors = _convert_slots(draft.slots)
        outcome = SlotContentPolicy.apply(contents, pattern)
        warnings = tuple(
            f"slide {plan.index}: {w}" for w in (*shape_errors, *outcome.warnings)
        )
        return SlideContent(plan, outcome.kept, warnings)

    # ── pdf ───────────────────────────────────────────────────────────────────

    async def _maybe_pdf(
        self,
        pptx: bytes,
        blueprint: DocumentBlueprint,
        cfg: PresentationGeneratorToolConfig,
        owner_user_id: str,
        request_id: str,
        warnings: list[str],
    ) -> str | None:
        if cfg.output_format != "pdf":
            return None
        if self._converter is None or not cfg.mcp_pptx_to_pdf_tool_id:
            warnings.append("PDF 변환 도구 미설정 — PPTX 만 제공")
            return None
        try:
            pdf = await self._converter.to_pdf_from_pptx(
                pptx, cfg.mcp_pptx_to_pdf_tool_id, request_id
            )
        except Exception as e:  # noqa: BLE001 — degraded (§6.3)
            self._logger.warning("blueprint.pdf convert failed", exception=e)
            warnings.append(f"PDF 변환 실패 — PPTX 만 제공 ({e})")
            return None
        return self._save(pdf, f"{blueprint.name}.pdf", owner_user_id).file_id

    # ── misc ──────────────────────────────────────────────────────────────────

    def _truncate(self, text: str) -> str:
        return (text or "").strip()[: self._input_max_chars]

    def _log_done(
        self, request_id: str, blueprint: DocumentBlueprint, result: PresentationResult
    ) -> None:
        self._logger.info(
            "blueprint.generate done",
            request_id=request_id,
            blueprint_id=blueprint.id,
            file_id=result.file_id,
            pdf_file_id=result.pdf_file_id,
            slide_count=result.slide_count,
            chart_count=result.chart_count,
            warnings=len(result.warnings),
            usage=result.usage,
        )


# ── helpers (순수) ───────────────────────────────────────────────────────────


def _validate(draft: SlidePlanDraft, blueprint: DocumentBlueprint, max_slides: int):
    plans = [
        SlidePlan(i, s.pattern_id, s.title, s.intent, s.data_hint)
        for i, s in enumerate(draft.slides, start=1)
        if s.pattern_id
    ]
    return SlidePlanValidationPolicy.apply(plans, blueprint.patterns, max_slides)


def _result(
    stored,
    pdf_file_id: str | None,
    slides: Sequence[SlideContent],
    warnings: Sequence[str],
    planner: SlidePlannerPort,
    writer: SlotWriterPort,
) -> PresentationResult:
    return PresentationResult(
        file_id=stored.file_id,
        filename=stored.filename,
        pdf_file_id=pdf_file_id,
        slide_count=len(slides),
        chart_count=sum(1 for s in slides for c in s.slots if c.chart is not None),
        warnings=tuple(warnings),
        usage=_sum_usage([planner.last_usage, *writer.usages]),
    )


def _has_renderable(slide: SlideContent, pattern: PagePattern) -> bool:
    """제목 폴백·이미지 에셋·표지 배경도 '그릴 것'으로 친다 (FR-04)."""
    if pattern.kind is PatternKind.COVER:
        return True
    if any(s.kind is SlotKind.IMAGE for s in pattern.slots):
        return True
    if slide.plan.title and any(s.kind is SlotKind.TITLE for s in pattern.slots):
        return True
    return bool(slide.slots)


def _convert_slots(drafts) -> tuple[list[SlotContent], list[str]]:
    """Draft → VO 변환. VO 검증 실패(ValueError)는 슬롯 제외 + 경고 (§6.3 degraded)."""
    contents: list[SlotContent] = []
    errors: list[str] = []
    for s in drafts:
        try:
            contents.append(_slot_content(s))
        except ValueError as e:
            errors.append(f"slot '{s.slot_id}': invalid {e}")
    return contents, errors


def _slot_content(s) -> SlotContent:
    table = (
        TableSpec(tuple(s.table.header), tuple(tuple(r) for r in s.table.rows))
        if s.table
        else None
    )
    chart = (
        ChartSpec(
            s.chart.type,
            tuple(s.chart.categories),
            tuple((se.name, tuple(se.values)) for se in s.chart.series),
            s.chart.unit,
        )
        if s.chart
        else None
    )
    heading = (getattr(s, "heading", None) or "").strip()
    return SlotContent(
        slot_id=s.slot_id,
        text=s.text,
        bullets=tuple(s.bullets) if s.bullets is not None else None,
        table=table,
        chart=chart,
        heading=heading or None,
    )


def _sum_usage(items: Sequence[dict | None]) -> dict[str, int]:
    total: dict[str, int] = {}
    for usage in items:
        for k, v in (usage or {}).items():
            if isinstance(v, int):
                total[k] = total.get(k, 0) + v
    return total
