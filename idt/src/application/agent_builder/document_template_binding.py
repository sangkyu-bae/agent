"""document_template ↔ 에이전트 바인딩 공용 로직 (Design §3-4).

create/update 유스케이스가 공유:
- build_document_template_plan: 검증(SlotPolicy/TemplateTokenPolicy, D2) +
  워커 tool_config 주입 + 저장 계획 생성
- persist_document_template: 원본 승격(D3) + document_template 저장(동일 세션, R6)
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.document_extractor.policies import SlotPolicy, TemplateTokenPolicy
from src.domain.document_extractor.schemas import (
    TEMPLATE_STATUS_ACTIVE,
    DocumentTemplate,
    TemplateSlot,
)
from src.domain.document_extractor.tool_config import DocumentExtractorToolConfig

DOCUMENT_EXTRACTOR_TOOL_ID = "document_extractor"


@dataclass(frozen=True)
class DocumentTemplatePlan:
    """검증 완료된 템플릿 저장 계획 (에이전트 저장 후 persist에 사용)."""

    template_id: str
    worker_id: str
    name: str
    html_skeleton: str
    slots: list[TemplateSlot]
    source_file_id: str
    source_format: str


def build_document_template_plan(
    template_request,
    workers: list[WorkerDefinition],
    max_slots: int,
) -> DocumentTemplatePlan:
    """검증 + 대상 워커 tool_config 주입 후 저장 계획 반환.

    Raises:
        ValueError: document_extractor 도구 워커 부재
        InvalidSlotError / TemplateTokenMismatchError: 검증 실패 (요청 전체 롤백)
    """
    worker = _find_extractor_worker(workers)
    slots = [dto.to_domain() for dto in template_request.slots]
    SlotPolicy.validate(slots, max_slots)
    TemplateTokenPolicy.validate(template_request.html_skeleton, slots)

    template_id = str(uuid.uuid4())
    config = DocumentExtractorToolConfig(
        template_id=template_id,
        mcp_pdf_to_html_tool_id=template_request.mcp_pdf_to_html_tool_id,
        mcp_html_to_doc_tool_id=template_request.mcp_html_to_doc_tool_id,
        output_format=template_request.source_format,  # 원본 포맷 따름 (결정 4)
    )
    worker.tool_config = config.model_dump()

    return DocumentTemplatePlan(
        template_id=template_id,
        worker_id=worker.worker_id,
        name=template_request.name,
        html_skeleton=template_request.html_skeleton,
        slots=slots,
        source_file_id=template_request.source_file_id,
        source_format=template_request.source_format,
    )


async def persist_document_template(
    plan: DocumentTemplatePlan,
    agent_id: str,
    template_repo,
    source_archiver,
    request_id: str,
) -> DocumentTemplate:
    """원본 승격(D3) + document_template 저장. 동일 요청 세션 트랜잭션 편승(R6)."""
    source_file_ref = source_archiver.promote(
        plan.source_file_id, plan.template_id, request_id
    )
    now = datetime.now(timezone.utc)
    template = DocumentTemplate(
        id=plan.template_id,
        agent_id=agent_id,
        worker_id=plan.worker_id,
        name=plan.name,
        html_skeleton=plan.html_skeleton,
        slots=plan.slots,
        source_file_ref=source_file_ref,
        source_format=plan.source_format,
        status=TEMPLATE_STATUS_ACTIVE,
        created_at=now,
        updated_at=now,
    )
    return await template_repo.save(template, request_id)


def ensure_template_wiring(template_repo, source_archiver) -> None:
    """document_template 요청이 왔는데 저장 구성이 미배선이면 명확히 실패."""
    if template_repo is None or source_archiver is None:
        raise ValueError(
            "문서 템플릿 저장 구성이 초기화되지 않았습니다 "
            "(document_template_repo/source_archiver 미주입)."
        )


def _find_extractor_worker(workers: list[WorkerDefinition]) -> WorkerDefinition:
    worker = next(
        (
            w for w in workers
            if w.worker_type == "tool" and w.tool_id == DOCUMENT_EXTRACTOR_TOOL_ID
        ),
        None,
    )
    if worker is None:
        raise ValueError(
            "document_extractor 도구가 선택되지 않았습니다. "
            "템플릿을 등록하려면 문서추출기 도구를 함께 선택하세요."
        )
    return worker
