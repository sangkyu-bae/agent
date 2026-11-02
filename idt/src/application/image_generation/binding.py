"""image_generate 워커 설정 바인딩 — image-generation-tool Design §4.2 / §4.3.

presentation_generator_binding 동형: 요청 → 도메인 VO 검증 → 대상 워커 tool_config 주입.
모델 검증(활성 image 종류)은 저장 UseCase 가 repo 로 수행한다 (D-05).
ValueError 메시지는 라우터가 422 로 매핑한다. 코드 접두어(IMAGE_MODEL_INVALID /
IMAGE_CONFIG_INVALID)는 프론트가 필드 오류로 구분하기 위한 계약이다.
"""
from __future__ import annotations

from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.image_generation.tool_config import ImageGenerationToolConfig
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.llm_model.policies import LlmModelPolicy

IMAGE_GENERATE_TOOL_ID = "image_generate"
IMAGE_MODEL_INVALID = "IMAGE_MODEL_INVALID"
IMAGE_CONFIG_INVALID = "IMAGE_CONFIG_INVALID"


def find_image_generate_worker(
    workers: list[WorkerDefinition],
) -> WorkerDefinition | None:
    return next(
        (
            w for w in workers
            if w.worker_type == "tool" and w.tool_id == IMAGE_GENERATE_TOOL_ID
        ),
        None,
    )


def apply_image_generation_config(
    config_request, workers: list[WorkerDefinition]
) -> ImageGenerationToolConfig:
    """검증 + 대상 워커 tool_config 주입 (presentation_generator_binding 동형).

    Raises:
        ValueError: image_generate 워커 부재 또는 설정 검증 실패 (요청 422)
    """
    worker = find_image_generate_worker(workers)
    if worker is None:
        raise ValueError(
            f"{IMAGE_CONFIG_INVALID}: image_generate 도구 워커가 없어 "
            "이미지 생성 설정을 적용할 수 없습니다."
        )
    try:
        config = ImageGenerationToolConfig(
            llm_model_id=config_request.llm_model_id,
            default_size=config_request.default_size,
            quality=config_request.quality,
        )
    except ValueError as e:
        raise ValueError(f"{IMAGE_CONFIG_INVALID}: {e}") from e
    worker.tool_config = config.model_dump()
    return config


async def validate_image_generation_model(
    workers: list[WorkerDefinition],
    llm_model_repo: LlmModelRepositoryInterface | None,
    request_id: str,
) -> None:
    """image_generate 워커가 있으면 설정 모델이 활성 image 종류인지 검증 (Design §4.2).

    워커가 없거나 설정이 아직 없으면(도구만 부착) 통과 — 실행 시 노드가 안내한다.
    """
    worker = find_image_generate_worker(workers)
    if worker is None or not worker.tool_config:
        return
    if llm_model_repo is None:
        raise ValueError(
            f"{IMAGE_MODEL_INVALID}: 이미지 모델 검증에 llm_model_repo 주입이 "
            "필요합니다."
        )
    model_id = str(worker.tool_config.get("llm_model_id") or "")
    model = await llm_model_repo.find_by_id(model_id, request_id)
    if model is None:
        raise ValueError(
            f"{IMAGE_MODEL_INVALID}: 이미지 생성 모델을 찾을 수 없습니다: {model_id}"
        )
    try:
        LlmModelPolicy.require_image_model(model)
    except ValueError as e:
        raise ValueError(f"{IMAGE_MODEL_INVALID}: {e}") from e
