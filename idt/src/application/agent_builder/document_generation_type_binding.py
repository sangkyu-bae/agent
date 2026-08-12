"""document_generation_type ↔ 에이전트 바인딩 공용 로직 (doc-generator Design §4-3).

create/update 유스케이스가 공유 (document_template_binding 동형):
- build_document_generation_type_plan: 검증(SectionPolicy/GenerationTypePolicy) +
  워커 tool_config 주입 + 저장 계획 생성
- persist_document_generation_type: document_generation_type 저장(동일 세션, R6)

추출기와 달리 파일 업로드가 없으므로 원본 승격(source_archiver) 단계가 없다.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.document_generator.policies import (
    GenerationTypePolicy,
    SectionPolicy,
)
from src.domain.document_generator.schemas import (
    GENERATION_TYPE_STATUS_ACTIVE,
    DocumentGenerationType,
    DocumentSection,
)
from src.domain.document_generator.tool_config import DocumentGeneratorToolConfig

DOCUMENT_GENERATOR_TOOL_ID = "document_generator"


@dataclass(frozen=True)
class DocumentGenerationTypePlan:
    """검증 완료된 문서 유형 저장 계획 (에이전트 저장 후 persist에 사용)."""

    type_id: str
    worker_id: str
    name: str
    description: str
    sections: list[DocumentSection]
    output_format: str


def build_document_generation_type_plan(
    type_request,
    workers: list[WorkerDefinition],
    max_sections: int,
) -> DocumentGenerationTypePlan:
    """검증 + 대상 워커 tool_config 주입 후 저장 계획 반환.

    Raises:
        ValueError: document_generator 도구 워커 부재
        InvalidGenerationTypeError: 검증 실패 (요청 전체 롤백)
    """
    worker = _find_generator_worker(workers)
    sections = [
        DocumentSection(title=s.title, guidance=s.guidance)
        for s in type_request.sections
    ]
    GenerationTypePolicy.validate(
        type_request.name, type_request.description, type_request.output_format
    )
    SectionPolicy.validate(sections, max_sections)

    type_id = str(uuid.uuid4())
    config = DocumentGeneratorToolConfig(
        type_id=type_id,
        mcp_html_to_doc_tool_id=type_request.mcp_html_to_doc_tool_id,
        output_format=type_request.output_format,
    )
    worker.tool_config = config.model_dump()

    return DocumentGenerationTypePlan(
        type_id=type_id,
        worker_id=worker.worker_id,
        name=type_request.name,
        description=type_request.description,
        sections=sections,
        output_format=type_request.output_format,
    )


async def persist_document_generation_type(
    plan: DocumentGenerationTypePlan,
    agent_id: str,
    type_repo,
    request_id: str,
) -> DocumentGenerationType:
    """document_generation_type 저장. 동일 요청 세션 트랜잭션 편승(R6)."""
    now = datetime.now(timezone.utc)
    gen_type = DocumentGenerationType(
        id=plan.type_id,
        agent_id=agent_id,
        worker_id=plan.worker_id,
        name=plan.name,
        description=plan.description,
        sections=plan.sections,
        output_format=plan.output_format,
        status=GENERATION_TYPE_STATUS_ACTIVE,
        created_at=now,
        updated_at=now,
    )
    return await type_repo.save(gen_type, request_id)


def ensure_generation_type_wiring(type_repo) -> None:
    """문서 유형 요청이 왔는데 저장 구성이 미배선이면 명확히 실패."""
    if type_repo is None:
        raise ValueError(
            "문서 유형 저장 구성이 초기화되지 않았습니다 "
            "(document_generation_type_repo 미주입)."
        )


def _find_generator_worker(workers: list[WorkerDefinition]) -> WorkerDefinition:
    worker = next(
        (
            w for w in workers
            if w.worker_type == "tool" and w.tool_id == DOCUMENT_GENERATOR_TOOL_ID
        ),
        None,
    )
    if worker is None:
        raise ValueError(
            "document_generator 도구가 선택되지 않았습니다. "
            "문서 유형을 등록하려면 문서생성기 도구를 함께 선택하세요."
        )
    return worker
