"""UtilityLLMProvider: 관리자 설정 LLM을 런타임에 해석해 공급한다.

Design Ref: admin-default-llm-routing §2.3 / §3.1~§3.3 / DR-1~DR-4, DR-7.

2계층 캐시 (DR-1)
-----------------
L1  값 캐시 — ``CachePort`` 경유. JSON 직렬화 가능한 dict 만 담는다.
              Redis 어댑터로 교체되는 계층이다.
L2  인스턴스 캐시 — 프로세스 로컬 dict. ``BaseChatModel`` 은 직렬화가
              불가능하므로 절대 ``CachePort`` 에 담지 않는다.

L2 키에 ``updated_at`` 을 포함해(DR-3), 관리자가 모델을 수정하면 L1 갱신이
새 ``updated_at`` 을 실어오고 L2 키가 자연히 달라진다 — L2 를 따로
무효화할 필요가 없다.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from langchain_core.language_models import BaseChatModel

from src.domain.cache.interfaces import CachePort
from src.domain.llm.interfaces import LLMFactoryInterface, UtilityLLMProviderPort
from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_KEY_DEFAULT = "llm_model:default"
_KEY_NAME_PREFIX = "llm_model:name:"
_REQUEST_ID = "utility-llm-provider"


class UtilityLLMProvider(UtilityLLMProviderPort):
    """보조 LLM 공급자 — 해석 + 2계층 캐시.

    저장소는 ``repo_builder`` 로 주입받는다. application 레이어가
    infrastructure 의 Repository 구현을 직접 임포트하지 않기 위함이다
    (MemoryExtractionService 선례).

    세션은 보유하지 않는다. 캐시 미스 시에만 ``session_factory`` 로 단기
    읽기 세션을 연다 (Design §9.4 — lifespan singleton 의 세션 보유 금지).
    """

    def __init__(
        self,
        cache: CachePort,
        llm_factory: LLMFactoryInterface,
        session_factory: Callable[[], Any],
        repo_builder: Callable[[Any], LlmModelRepositoryInterface],
        logger: LoggerInterface,
        *,
        utility_model_name: str | None = None,
        ttl_seconds: float = 60.0,
        max_instances: int = 32,
    ) -> None:
        self._cache = cache
        self._llm_factory = llm_factory
        self._session_factory = session_factory
        self._repo_builder = repo_builder
        self._logger = logger
        self._utility_model_name = utility_model_name
        self._ttl = ttl_seconds
        self._max_instances = max_instances
        # L2: (model_id, updated_at_iso, temperature) -> BaseChatModel
        self._instances: dict[tuple[str, str, float], BaseChatModel] = {}

    # ── 공개 API ────────────────────────────────────────────────────────

    async def get(self, temperature: float = 0.0) -> BaseChatModel | None:
        """현재 유효한 보조 LLM. 실패 시 None (예외 전파 없음 — DR-7)."""
        try:
            model = await self._resolve_model()
            if model is None:
                return None
            return self._get_instance(model, temperature)
        except Exception as e:
            self._logger.error(
                "Utility LLM resolution failed — falling back to caller default",
                exception=e,
                request_id=_REQUEST_ID,
            )
            return None

    async def invalidate(self) -> None:
        """L1 해석 캐시를 비운다. L2는 updated_at 키 변화로 자연 만료된다."""
        try:
            await self._cache.delete(_KEY_DEFAULT)
            if self._utility_model_name:
                await self._cache.delete(
                    _KEY_NAME_PREFIX + self._utility_model_name
                )
            self._logger.info(
                "LLM model cache invalidated", request_id=_REQUEST_ID
            )
        except Exception as e:
            # 무효화 실패가 관리자 요청을 실패시켜서는 안 된다 (§6.1).
            self._logger.warning(
                "LLM model cache invalidation failed — will expire by TTL",
                request_id=_REQUEST_ID,
                error=str(e),
            )

    # ── L1: 모델 해석 ───────────────────────────────────────────────────

    async def _resolve_model(self) -> LlmModel | None:
        """보조 모델 → 실패 시 기본 모델 (2단 폴백)."""
        name = self._utility_model_name
        if name:
            model = await self._resolve_by_name(name)
            if model is not None:
                return model
            self._logger.warning(
                "Utility LLM model unresolved — falling back to default",
                request_id=_REQUEST_ID,
                model_name=name,
                fallback_to="default",
            )
        return await self._resolve_default()

    async def _resolve_by_name(self, name: str) -> LlmModel | None:
        """활성 모델 중 model_name 일치 1건. 비활성은 자동 제외된다."""
        key = _KEY_NAME_PREFIX + name

        cached = await self._cache_get(key)
        if cached is not None:
            return _from_cache_dict(cached)

        async with self._session_factory() as session:
            repo = self._repo_builder(session)
            actives = await repo.list_active(_REQUEST_ID)

        model = next((m for m in actives if m.model_name == name), None)
        if model is None:
            return None

        await self._cache_set(key, model)
        self._log_resolved(model, cache="L1_miss", source="utility")
        return model

    async def _resolve_default(self) -> LlmModel | None:
        """관리자가 지정한 기본 모델(is_default=True)."""
        cached = await self._cache_get(_KEY_DEFAULT)
        if cached is not None:
            return _from_cache_dict(cached)

        async with self._session_factory() as session:
            repo = self._repo_builder(session)
            model = await repo.find_default(_REQUEST_ID)

        if model is None:
            self._logger.warning(
                "No default LLM model registered — utility LLM disabled",
                request_id=_REQUEST_ID,
            )
            return None

        await self._cache_set(_KEY_DEFAULT, model)
        self._log_resolved(model, cache="L1_miss", source="default")
        return model

    # ── L2: 인스턴스 캐시 ───────────────────────────────────────────────

    def _get_instance(
        self, model: LlmModel, temperature: float
    ) -> BaseChatModel:
        key = (model.id, model.updated_at.isoformat(), temperature)

        cached = self._instances.get(key)
        if cached is not None:
            # L2 히트는 호출마다 발생하므로 debug 로 둔다 (FR-00c 는 L1 미스만
            # INFO 로 올린다 — 그쪽이 "모델이 바뀌었다"를 알려주는 지점이다).
            self._log_instance_hit(model)
            return cached

        llm = self._llm_factory.create(model, temperature=temperature)
        self._evict_instances_if_needed()
        self._instances[key] = llm
        return llm

    def _evict_instances_if_needed(self) -> None:
        while self._instances and len(self._instances) >= self._max_instances:
            oldest = next(iter(self._instances))
            self._instances.pop(oldest, None)

    # ── 캐시 접근 (실패는 miss 취급 — DR-7) ─────────────────────────────

    async def _cache_get(self, key: str) -> dict[str, Any] | None:
        try:
            return await self._cache.get(key)
        except Exception as e:
            self._logger.debug(
                "Cache get failed — treated as miss",
                request_id=_REQUEST_ID,
                key=key,
                error=str(e),
            )
            return None

    async def _cache_set(self, key: str, model: LlmModel) -> None:
        try:
            await self._cache.set(
                key, _to_cache_dict(model), ttl_seconds=self._ttl
            )
        except Exception as e:
            self._logger.debug(
                "Cache set failed — ignored",
                request_id=_REQUEST_ID,
                key=key,
                error=str(e),
            )

    def _log_resolved(self, model: LlmModel, *, cache: str, source: str) -> None:
        # base_url 을 남기는 것이 self-host(NPU) 전환 실측의 근거다 (§6.2).
        #
        # prompt-fallback-visibility FR-00c — 레벨이 debug 였던 탓에 기본 로그
        # 설정(INFO)에서 한 줄도 보이지 않았다. 2026-09-04 에 기본 모델이 추론
        # 모델로 바뀌어 프롬프트 생성이 2주간 100% 폴백으로 떨어졌는데도 "어떤
        # 모델로 도는가"가 어디에도 없었다. 캐시 미스에서만 찍히므로(TTL 주기)
        # INFO 로 올려도 양이 많지 않다.
        #
        # source: "utility" = UTILITY_LLM_MODEL_NAME 으로 명시된 모델
        #         "default" = 미설정이라 관리자 기본 모델을 따라간 것 ← 위험 신호
        self._logger.info(
            "Utility LLM resolved",
            request_id=_REQUEST_ID,
            model_name=model.model_name,
            provider=model.provider,
            base_url=model.base_url,
            cache=cache,
            source=source,
        )

    def _log_instance_hit(self, model: LlmModel) -> None:
        """L2 인스턴스 캐시 히트 — 호출마다 발생하므로 debug.

        필드 집합은 `_log_resolved` 와 동일하게 유지한다(Check G5) — 같은
        메시지명("Utility LLM resolved")으로 나가므로 스키마가 갈리면 로그
        수집기에서 한쪽만 파싱된다. 이 경로는 해석 출처를 모르므로 "cached".
        """
        self._logger.debug(
            "Utility LLM resolved",
            request_id=_REQUEST_ID,
            model_name=model.model_name,
            provider=model.provider,
            base_url=model.base_url,
            cache="L2_hit",
            source="cached",
        )


# ── 직렬화 경계 (DR-2) ──────────────────────────────────────────────────
# CachePort 계약: 값은 JSON 직렬화 가능해야 한다. Decimal·datetime 을
# 문자열로 변환해 Redis 어댑터로 교체해도 소비자가 수정되지 않게 한다.


def _to_cache_dict(model: LlmModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "provider": model.provider,
        "model_name": model.model_name,
        "display_name": model.display_name,
        "description": model.description,
        "api_key_env": model.api_key_env,
        "max_tokens": model.max_tokens,
        "is_active": model.is_active,
        "is_default": model.is_default,
        "created_at": model.created_at.isoformat(),
        "updated_at": model.updated_at.isoformat(),
        "input_price_per_1k_usd": _decimal_to_str(model.input_price_per_1k_usd),
        "output_price_per_1k_usd": _decimal_to_str(
            model.output_price_per_1k_usd
        ),
        "pricing_updated_at": (
            model.pricing_updated_at.isoformat()
            if model.pricing_updated_at
            else None
        ),
        "base_url": model.base_url,
        "supports_vision": model.supports_vision,
    }


def _from_cache_dict(data: dict[str, Any]) -> LlmModel:
    return LlmModel(
        id=data["id"],
        provider=data["provider"],
        model_name=data["model_name"],
        display_name=data["display_name"],
        description=data["description"],
        api_key_env=data["api_key_env"],
        max_tokens=data["max_tokens"],
        is_active=data["is_active"],
        is_default=data["is_default"],
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
        input_price_per_1k_usd=_str_to_decimal(data["input_price_per_1k_usd"]),
        output_price_per_1k_usd=_str_to_decimal(data["output_price_per_1k_usd"]),
        pricing_updated_at=(
            datetime.fromisoformat(data["pricing_updated_at"])
            if data["pricing_updated_at"]
            else None
        ),
        base_url=data["base_url"],
        supports_vision=data["supports_vision"],
    )


def _decimal_to_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _str_to_decimal(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None
