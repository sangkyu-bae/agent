"""DocumentComposer: 런타임 문서 합성 (Design §4-3, GB2·GB3·GB6).

역할 분리(D6): LLM은 "슬롯 값 결정"만 담당(JSON {key: value|null}).
문서 변형은 순수 문자열 토큰 치환 — 재현성 100%.
"""
import html as html_lib
import json
import re
from dataclasses import dataclass, field

from src.domain.agent_attachment.value_objects import AttachmentType
from src.domain.document_extractor.exceptions import ComposeError
from src.domain.document_extractor.policies import (
    COMPOSE_GUIDELINES,
    SlotValuePolicy,
    UnfilledSlotPolicy,
)
from src.domain.document_extractor.schemas import DocumentTemplate, TemplateSlot
from src.domain.document_extractor.tool_config import DocumentExtractorToolConfig
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.langsmith.langsmith import (
    DOCUMENT_EXTRACTOR_PROJECT_NAME,
    make_document_extractor_tracer,
)

_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n|\n```$")


@dataclass(frozen=True)
class ComposeResult:
    file_id: str
    filename: str
    filled_slots: dict = field(default_factory=dict)      # {label: value}
    unfilled_labels: list = field(default_factory=list)   # GB6 공란 슬롯 label


class DocumentComposer:
    """지정 템플릿 + 누적 컨텍스트 → 채운 HTML → MCP 변환 → 첨부 저장."""

    def __init__(
        self, conversion_adapter, attachment_store, logger: LoggerInterface
    ) -> None:
        self._adapter = conversion_adapter
        self._store = attachment_store
        self._logger = logger

    async def compose(
        self,
        llm,
        template: DocumentTemplate,
        tool_config: DocumentExtractorToolConfig,
        evidence_block: str,
        conversation_block: str,
        owner_user_id: str,
        request_id: str,
    ) -> ComposeResult:
        values = await self._decide_slot_values(
            llm, template, evidence_block, conversation_block, request_id
        )
        html, filled, unfilled = self._replace_tokens(template, values)

        file_bytes = await self._adapter.to_document(
            html,
            tool_config.output_format,
            tool_config.mcp_html_to_doc_tool_id,
            request_id,
        )
        filename = f"{template.name}.{tool_config.output_format}"
        stored = self._store.save(
            file_bytes=file_bytes,
            filename=filename,
            attachment_type=AttachmentType.DOCUMENT,
            owner_user_id=owner_user_id,
        )
        self._logger.info(
            "DocumentComposer done",
            request_id=request_id,
            template_id=template.id,
            file_id=stored.file_id,
            filled_count=len(filled),
            unfilled_count=len(unfilled),
        )
        return ComposeResult(
            file_id=stored.file_id,
            filename=stored.filename,
            filled_slots=filled,
            unfilled_labels=unfilled,
        )

    async def _decide_slot_values(
        self,
        llm,
        template: DocumentTemplate,
        evidence_block: str,
        conversation_block: str,
        request_id: str,
    ) -> dict:
        """LLM 1회(+재시도 1회)로 {key: value|null} 결정 (D6 계약)."""
        messages = [
            {"role": "system", "content": self._build_prompt(template)},
            {
                "role": "user",
                "content": (
                    f"[근거 자료]\n{evidence_block or '(수집된 근거 없음)'}\n\n"
                    f"[대화]\n{conversation_block or '(대화 없음)'}"
                ),
            },
        ]
        required_keys = {s.key for s in template.slots}
        config = self._build_trace_config(template, request_id)
        last_error = ""
        for attempt in (1, 2):
            response = await llm.ainvoke(messages, config=config)
            content = getattr(response, "content", str(response))
            values, error = self._parse_values(content, required_keys)
            if values is not None:
                return values
            last_error = error
            self._logger.warning(
                "DocumentComposer llm contract violation, retrying",
                request_id=request_id,
                attempt=attempt,
                error=error,
            )
        raise ComposeError(
            f"문서 합성 LLM 응답이 계약(JSON {{key: value|null}})을 위반했습니다: "
            f"{last_error}"
        )

    @staticmethod
    def _build_trace_config(template: DocumentTemplate, request_id: str) -> dict:
        """LangSmith 추적 config — 프로젝트 'document-extractor'로 per-run 기록.

        run_name 'compose:{템플릿명}'으로 어떤 문서를 합성했는지 식별.
        tracer가 None(API 키 없음)이면 callbacks 미설정 — 본 흐름 영향 없음.
        """
        tags = [DOCUMENT_EXTRACTOR_PROJECT_NAME, "compose"]
        config: dict = {
            "run_name": f"compose:{template.name}",
            "tags": tags,
            "metadata": {
                "request_id": request_id,
                "template_id": template.id,
            },
        }
        tracer = make_document_extractor_tracer(tags=tags)
        if tracer is not None:
            config["callbacks"] = [tracer]
        return config

    @staticmethod
    def _build_prompt(template: DocumentTemplate) -> str:
        slot_lines = "\n".join(
            f"- {s.key} ({s.slot_type}): {s.label}"
            + (f" — {s.description}" if s.description else "")
            + (f" / 힌트: {s.fill_hint}" if s.fill_hint else "")
            for s in template.slots
        )
        return (
            f"{COMPOSE_GUIDELINES}\n"
            f"[문서]\n{template.name}\n\n"
            f"[슬롯 정의]\n{slot_lines}\n\n"
            f'출력 예시: {{"slot_key": "값", "no_evidence_key": null}}'
        )

    @staticmethod
    def _parse_values(
        content: str, required_keys: set
    ) -> tuple[dict | None, str]:
        text = _CODE_FENCE_RE.sub("", content.strip()).strip()
        try:
            values = json.loads(text)
        except (ValueError, TypeError) as e:
            return None, f"JSON 파싱 실패: {e}"
        if not isinstance(values, dict):
            return None, f"JSON 오브젝트가 아님: {type(values).__name__}"
        missing = required_keys - set(values.keys())
        if missing:
            return None, f"누락된 슬롯 key: {sorted(missing)}"
        return values, ""

    @staticmethod
    def _replace_tokens(
        template: DocumentTemplate, values: dict
    ) -> tuple[str, dict, list]:
        """순수 문자열 치환 (재현성 100%). GB6: 공란 → 하이라이트."""
        html = template.html_skeleton
        filled: dict = {}
        unfilled: list = []
        for slot in template.slots:
            raw = values.get(slot.key)
            if UnfilledSlotPolicy.is_unfilled(raw):
                replacement = UnfilledSlotPolicy.render_unfilled(slot)
                unfilled.append(slot.label)
            else:
                value = SlotValuePolicy.sanitize(str(raw))
                replacement = html_lib.escape(value)
                filled[slot.label] = value
            html = html.replace(slot.anchor, replacement)
        return html, filled, unfilled
