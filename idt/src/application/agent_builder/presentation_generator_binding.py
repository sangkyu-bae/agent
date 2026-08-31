"""presentation_generator ↔ 에이전트 워커 tool_config 바인딩.

golden-sample-blueprint Design D7 / FR-11 — document_generation_type_binding 동형이되
blueprint 는 전역 라이브러리 자원이라 에이전트별 영속 엔티티가 없다:
요청을 PresentationGeneratorToolConfig 로 검증해 워커 tool_config 에 주입만 한다.
"""

from __future__ import annotations

from dataclasses import asdict

from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.blueprint.tool_config import PresentationGeneratorToolConfig

PRESENTATION_GENERATOR_TOOL_ID = "presentation_generator"


def apply_presentation_generator_config(
    config_request, workers: list[WorkerDefinition]
) -> PresentationGeneratorToolConfig:
    """검증 + 대상 워커 tool_config 주입.

    Raises:
        ValueError: presentation_generator 워커 부재 또는 설정 검증 실패 (요청 400)
    """
    worker = next(
        (
            w
            for w in workers
            if w.worker_type == "tool" and w.tool_id == PRESENTATION_GENERATOR_TOOL_ID
        ),
        None,
    )
    if worker is None:
        raise ValueError(
            "presentation_generator 도구 워커가 없어 발표자료 설정을 적용할 수 "
            "없습니다."
        )
    config = PresentationGeneratorToolConfig(
        blueprint_id=config_request.blueprint_id,
        output_format=config_request.output_format,
        mcp_pptx_to_pdf_tool_id=config_request.mcp_pptx_to_pdf_tool_id,
        max_slides=config_request.max_slides,
    )
    worker.tool_config = asdict(config)
    return config
