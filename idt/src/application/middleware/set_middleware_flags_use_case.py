"""SetMiddlewareFlagsUseCase: 빌트인/강제/기본 설정 갱신 (관리자 전용, D4).

- 미존재 middleware_type → LookupError (라우터 404 매핑)
- config 검증 위반 → ValueError (라우터 400 매핑)
"""
from src.application.middleware.schemas import MiddlewareCatalogItemResponse
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.middleware.config_policy import MiddlewareConfigPolicy
from src.domain.middleware.entities import MiddlewareType
from src.domain.middleware.interfaces import MiddlewareCatalogRepositoryInterface


class SetMiddlewareFlagsUseCase:
    def __init__(
        self,
        repository: MiddlewareCatalogRepositoryInterface,
        llm_model_repository: LlmModelRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._llm_model_repository = llm_model_repository
        self._logger = logger

    async def execute(
        self,
        middleware_type: str,
        *,
        is_builtin: bool | None,
        is_enforced: bool | None,
        default_config: dict | None,
        request_id: str,
    ) -> MiddlewareCatalogItemResponse:
        self._logger.info(
            "SetMiddlewareFlagsUseCase start",
            request_id=request_id,
            middleware_type=middleware_type,
        )
        try:
            existing = await self._repository.find_by_type(
                middleware_type, request_id
            )
            if existing is None:
                raise LookupError(f"Unknown middleware_type: {middleware_type!r}")

            if default_config is not None:
                await self._validate_config(
                    existing.middleware_type, default_config, request_id
                )

            updated = await self._repository.update_flags(
                middleware_type,
                is_builtin=is_builtin,
                is_enforced=is_enforced,
                default_config=default_config,
                request_id=request_id,
            )
            if updated is None:
                raise LookupError(f"Unknown middleware_type: {middleware_type!r}")
            self._logger.info(
                "SetMiddlewareFlagsUseCase done",
                request_id=request_id,
                middleware_type=middleware_type,
                is_builtin=updated.is_builtin,
                is_enforced=updated.is_enforced,
            )
            return MiddlewareCatalogItemResponse.from_entity(updated)
        except (LookupError, ValueError):
            raise
        except Exception as e:
            self._logger.error(
                "SetMiddlewareFlagsUseCase failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def _validate_config(
        self, middleware_type: MiddlewareType, config: dict, request_id: str
    ) -> None:
        active_model_names: set[str] | None = None
        if middleware_type is MiddlewareType.MODEL_FALLBACK:
            models = await self._llm_model_repository.list_active(request_id)
            active_model_names = {m.model_name for m in models}
        MiddlewareConfigPolicy.validate(
            middleware_type, config, active_model_names
        )
