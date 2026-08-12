"""DocumentGenerator: 런타임 문서 생성 (doc-generator Design §4-4).

역할(D1·D2): 조사·분석은 상류 워커가 담당 — 이 컴포넌트는 누적 근거+대화를 받아
① 작성 LLM 1회(+섹션 커버리지 재시도 1회) ② sanitize ③ MCP html→pdf/docx 변환
④ 첨부 저장만 수행한다. 변환은 추출기 DocumentConversionAdapter 재사용 (D7).
"""
import re
from dataclasses import dataclass

from src.domain.agent_attachment.value_objects import AttachmentType
from src.domain.document_extractor.exceptions import McpToolNotConfiguredError
from src.domain.document_extractor.policies import HtmlSanitizePolicy
from src.domain.document_generator.exceptions import GenerateError
from src.domain.document_generator.policies import (
    GENERATE_GUIDELINES,
    SectionCoveragePolicy,
)
from src.domain.document_generator.schemas import (
    DocumentGenerationType,
    GenerateResult,
)
from src.domain.document_generator.tool_config import DocumentGeneratorToolConfig
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.langsmith.langsmith import (
    DOCUMENT_GENERATOR_PROJECT_NAME,
    make_document_generator_tracer,
)

_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n|\n```$")

_NO_EVIDENCE_MARK = "(수집된 근거 없음 — 대화 문맥만으로 작성)"


@dataclass(frozen=True)
class _Draft:
    html: str
    missing: list


class DocumentGenerator:
    """누적 컨텍스트 + 문서 유형 → HTML 작성 → MCP 변환 → 첨부 저장."""

    def __init__(
        self,
        conversion_adapter,
        attachment_store,
        logger: LoggerInterface,
        default_html_to_doc_tool_id: str = "",
        fallback_html_to_doc_tool_id: str = "",
        llm_input_max_chars: int = 20000,
    ) -> None:
        self._adapter = conversion_adapter
        self._store = attachment_store
        self._logger = logger
        # D5 폴백 체인: tool_config → generator 설정 → extractor 설정
        self._default_h2d = default_html_to_doc_tool_id
        self._fallback_h2d = fallback_html_to_doc_tool_id
        self._input_max_chars = llm_input_max_chars

    async def generate(
        self,
        llm,
        gen_type: DocumentGenerationType,
        tool_config: DocumentGeneratorToolConfig,
        evidence_block: str,
        conversation_block: str,
        owner_user_id: str,
        request_id: str,
    ) -> GenerateResult:
        mcp_tool_id = self._resolve_mcp_tool_id(tool_config)
        draft = await self._write_html(
            llm, gen_type, evidence_block, conversation_block, request_id
        )
        html = HtmlSanitizePolicy.clean(draft.html)

        file_bytes = await self._adapter.to_document(
            html, tool_config.output_format, mcp_tool_id, request_id,
        )
        filename = f"{gen_type.name}.{tool_config.output_format}"
        stored = self._store.save(
            file_bytes=file_bytes,
            filename=filename,
            attachment_type=AttachmentType.DOCUMENT,
            owner_user_id=owner_user_id,
        )
        self._logger.info(
            "DocumentGenerator done",
            request_id=request_id,
            type_id=gen_type.id,
            file_id=stored.file_id,
            section_count=len(gen_type.sections),
            missing_count=len(draft.missing),
        )
        return GenerateResult(
            file_id=stored.file_id,
            filename=stored.filename,
            section_count=len(gen_type.sections),
            missing_sections=draft.missing,
            used_evidence=bool(evidence_block.strip()),
        )

    # ── 작성 (D2: LLM 1회 + 커버리지 재시도 1회) ────────────────────────────
    async def _write_html(
        self,
        llm,
        gen_type: DocumentGenerationType,
        evidence_block: str,
        conversation_block: str,
        request_id: str,
    ) -> _Draft:
        messages = [
            {"role": "system", "content": self._build_prompt(gen_type)},
            {
                "role": "user",
                "content": self._build_user_content(
                    evidence_block, conversation_block
                ),
            },
        ]
        config = self._build_trace_config(gen_type, request_id)

        first = await self._invoke(llm, messages, config, gen_type)
        if first is not None and not first.missing:
            return first

        retry_messages = messages + [self._retry_instruction(first, gen_type)]
        second = await self._invoke(llm, retry_messages, config, gen_type)

        chosen = self._choose_draft(first, second)
        if chosen is None:
            raise GenerateError(
                "문서 작성 LLM 응답이 비어 있습니다 (재시도 포함 2회)."
            )
        if chosen.missing:
            self._logger.warning(
                "DocumentGenerator sections still missing after retry",
                request_id=request_id,
                type_id=gen_type.id,
                missing=chosen.missing,
            )
        return chosen

    async def _invoke(self, llm, messages, config, gen_type) -> "_Draft | None":
        response = await llm.ainvoke(messages, config=config)
        content = getattr(response, "content", str(response))
        html = _CODE_FENCE_RE.sub("", (content or "").strip()).strip()
        if not html:
            return None
        missing = SectionCoveragePolicy.missing_titles(html, gen_type.sections)
        return _Draft(html=html, missing=missing)

    @staticmethod
    def _retry_instruction(first: "_Draft | None", gen_type) -> dict:
        missing = first.missing if first is not None else [
            s.title for s in gen_type.sections
        ]
        return {
            "role": "user",
            "content": (
                "다음 섹션이 누락되었거나 출력이 비어 있습니다: "
                f"{', '.join(missing)}. 섹션 아웃라인의 모든 섹션 heading을 "
                "포함해 완결된 HTML 문서를 다시 출력하세요."
            ),
        }

    @staticmethod
    def _choose_draft(
        first: "_Draft | None", second: "_Draft | None"
    ) -> "_Draft | None":
        if first is None:
            return second
        if second is None:
            return first
        return second if len(second.missing) <= len(first.missing) else first

    # ── 프롬프트 ─────────────────────────────────────────────────────────
    @staticmethod
    def _build_prompt(gen_type: DocumentGenerationType) -> str:
        section_lines = "\n".join(
            f"{i}. {s.title}" + (f" — {s.guidance}" if s.guidance else "")
            for i, s in enumerate(gen_type.sections, start=1)
        )
        description = f"\n설명: {gen_type.description}" if gen_type.description else ""
        return (
            f"{GENERATE_GUIDELINES}\n"
            f"[문서 유형]\n{gen_type.name}{description}\n\n"
            f"[섹션 아웃라인]\n{section_lines}"
        )

    def _build_user_content(
        self, evidence_block: str, conversation_block: str
    ) -> str:
        evidence = self._truncate(evidence_block) or _NO_EVIDENCE_MARK
        conversation = self._truncate(conversation_block) or "(대화 없음)"
        return f"[근거 자료]\n{evidence}\n\n[대화]\n{conversation}"

    def _truncate(self, text: str) -> str:
        return (text or "").strip()[: self._input_max_chars]

    # ── 설정 해석 (D5) ────────────────────────────────────────────────────
    def _resolve_mcp_tool_id(
        self, tool_config: DocumentGeneratorToolConfig
    ) -> str:
        effective = (
            tool_config.mcp_html_to_doc_tool_id
            or self._default_h2d
            or self._fallback_h2d
        )
        if not effective:
            raise McpToolNotConfiguredError(
                "html→pdf/doc 변환 MCP 도구가 지정되지 않았습니다. "
                "문서 유형 설정에 변환 도구를 지정하거나 "
                "DOCUMENT_GENERATOR_HTML_TO_DOC_TOOL_ID 설정을 등록하세요."
            )
        return effective

    @staticmethod
    def _build_trace_config(
        gen_type: DocumentGenerationType, request_id: str
    ) -> dict:
        """LangSmith 추적 config — 프로젝트 'document-generator' per-run 기록 (D7)."""
        tags = [DOCUMENT_GENERATOR_PROJECT_NAME, "generate"]
        config: dict = {
            "run_name": f"generate:{gen_type.name}",
            "tags": tags,
            "metadata": {
                "request_id": request_id,
                "type_id": gen_type.id,
            },
        }
        tracer = make_document_generator_tracer(tags=tags)
        if tracer is not None:
            config["callbacks"] = [tracer]
        return config
