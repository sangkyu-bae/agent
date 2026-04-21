"""LLM 모델 시드 데이터 등록.

LLM-MODEL-REG-001 §6-3, §7.
서비스 기동 시 기본 모델 3개를 등록한다 (중복 스킵).
"""
import uuid
from datetime import datetime, timezone

from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

DEFAULT_MODELS: list[dict] = [
    {
        "provider": "openai",
        "model_name": "gpt-4o",
        "display_name": "GPT-4o",
        "description": "OpenAI 최신 멀티모달 모델",
        "api_key_env": "OPENAI_API_KEY",
        "max_tokens": 128000,
        "is_default": True,
    },
    {
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "display_name": "GPT-4o Mini",
        "description": "OpenAI 소형 고속 모델",
        "api_key_env": "OPENAI_API_KEY",
        "max_tokens": 128000,
        "is_default": False,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-sonnet-4-6",
        "display_name": "Claude Sonnet 4.6",
        "description": "Anthropic Sonnet 계열 고성능 모델",
        "api_key_env": "ANTHROPIC_API_KEY",
        "max_tokens": 200000,
        "is_default": False,
    },
]


async def seed_default_models(
    repository: LlmModelRepositoryInterface,
    logger: LoggerInterface,
    request_id: str,
) -> None:
    """기본 모델 3개 등록 (이미 존재하면 스킵)."""
    logger.info("seed_default_models start", request_id=request_id)
    try:
        now = datetime.now(timezone.utc)
        for spec in DEFAULT_MODELS:
            existing = await repository.find_by_provider_and_name(
                spec["provider"], spec["model_name"], request_id
            )
            if existing is not None:
                continue
            model = LlmModel(
                id=str(uuid.uuid4()),
                provider=spec["provider"],
                model_name=spec["model_name"],
                display_name=spec["display_name"],
                description=spec.get("description"),
                api_key_env=spec["api_key_env"],
                max_tokens=spec.get("max_tokens"),
                is_active=True,
                is_default=spec["is_default"],
                created_at=now,
                updated_at=now,
            )
            await repository.save(model, request_id)
            logger.info(
                "seed_default_models inserted",
                request_id=request_id,
                provider=spec["provider"],
                model_name=spec["model_name"],
            )
        logger.info("seed_default_models done", request_id=request_id)
    except Exception as e:
        logger.error(
            "seed_default_models failed", exception=e, request_id=request_id
        )
        raise
