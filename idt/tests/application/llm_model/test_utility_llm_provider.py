"""UtilityLLMProvider 단위 테스트.

Design Ref: admin-default-llm-routing §8.3 시나리오 P1~P14.

L1(값 캐시)은 module-1의 InMemoryCache 실물을 주입해 실제 동작을 검증한다.
L2(인스턴스 캐시)는 LLMFactory 호출 횟수로 관찰한다.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.application.llm_model.utility_llm_provider import UtilityLLMProvider
from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.domain.llm_model.entity import LlmModel
from src.infrastructure.cache.in_memory_cache import InMemoryCache

from tests.application.llm_model.conftest import InMemoryLlmModelRepository


# ── 테스트 더블 ──────────────────────────────────────────────────────────


class FakeLLM:
    """BaseChatModel 자리표시자 — 동일성 비교만 사용한다."""

    def __init__(self, model_name: str, temperature: float) -> None:
        self.model_name = model_name
        self.temperature = temperature


class RecordingLLMFactory:
    """LLMFactoryInterface 스텁. create 호출을 기록한다."""

    def __init__(self, raises: Exception | None = None) -> None:
        self.calls: list[tuple[str, float]] = []
        self._raises = raises

    def create(self, llm_model: LlmModel, temperature: float = 0.0) -> Any:
        if self._raises is not None:
            raise self._raises
        self.calls.append((llm_model.model_name, temperature))
        return FakeLLM(llm_model.model_name, temperature)


class CountingRepository(InMemoryLlmModelRepository):
    """DB 조회 횟수를 세는 저장소."""

    def __init__(self) -> None:
        super().__init__()
        self.find_default_calls = 0
        self.list_active_calls = 0
        self.raises: Exception | None = None

    async def find_default(self, request_id: str):
        if self.raises is not None:
            raise self.raises
        self.find_default_calls += 1
        return await super().find_default(request_id)

    async def list_active(self, request_id: str):
        if self.raises is not None:
            raise self.raises
        self.list_active_calls += 1
        return await super().list_active(request_id)


class FakeSession:
    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


class ExplodingCache(InMemoryCache):
    """get 이 항상 예외를 던지는 캐시 — DR-7 낙하 검증용."""

    async def get(self, key: str) -> Any | None:
        raise RuntimeError("cache backend down")


# ── 픽스처 ───────────────────────────────────────────────────────────────


def _model(
    model_id: str,
    model_name: str,
    *,
    is_default: bool = False,
    is_active: bool = True,
    base_url: str | None = None,
    updated_at: datetime | None = None,
) -> LlmModel:
    now = updated_at or datetime.now(timezone.utc)
    return LlmModel(
        id=model_id,
        provider="openai",
        model_name=model_name,
        display_name=model_name,
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=is_active,
        is_default=is_default,
        created_at=now,
        updated_at=now,
        base_url=base_url,
    )


@pytest.fixture
def counting_repo() -> CountingRepository:
    return CountingRepository()


@pytest.fixture
def cache() -> InMemoryCache:
    return InMemoryCache(default_ttl_seconds=60.0, max_entries=100)


@pytest.fixture
def factory() -> RecordingLLMFactory:
    return RecordingLLMFactory()


def _build(
    cache: InMemoryCache,
    factory: RecordingLLMFactory,
    repo: InMemoryLlmModelRepository,
    logger: Any,
    utility_model_name: str | None = None,
) -> UtilityLLMProvider:
    return UtilityLLMProvider(
        cache=cache,
        llm_factory=factory,
        session_factory=lambda: FakeSession(),
        repo_builder=lambda _session: repo,
        logger=logger,
        utility_model_name=utility_model_name,
        ttl_seconds=60.0,
        max_instances=8,
    )


@pytest.fixture
def provider(
    cache: InMemoryCache,
    factory: RecordingLLMFactory,
    counting_repo: CountingRepository,
    mock_logger: Any,
) -> UtilityLLMProvider:
    return _build(cache, factory, counting_repo, mock_logger)


# ── 시나리오 ─────────────────────────────────────────────────────────────


class TestPortContract:
    def test_implements_port(self, provider: UtilityLLMProvider) -> None:
        assert isinstance(provider, UtilityLLMProviderPort)

    def test_port_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            UtilityLLMProviderPort()  # type: ignore[abstract]


class TestResolution:
    """P1~P5 — 기본/보조 모델 해석과 2단 폴백."""

    async def test_p1_uses_default_model_when_utility_name_unset(
        self, provider: UtilityLLMProvider, counting_repo: CountingRepository
    ) -> None:
        """P1: 보조 모델명 미설정 + 기본 모델 존재 → 기본 모델."""
        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)

        llm = await provider.get(temperature=0.0)

        assert llm is not None
        assert llm.model_name == "gpt-4o"

    async def test_p2_uses_utility_model_when_configured(
        self,
        cache: InMemoryCache,
        factory: RecordingLLMFactory,
        counting_repo: CountingRepository,
        mock_logger: Any,
    ) -> None:
        """P2: 보조 모델명 설정 + DB에 존재 → 보조 모델."""
        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)
        counting_repo._by_id["u"] = _model("u", "gpt-4o-mini")
        provider = _build(
            cache, factory, counting_repo, mock_logger, "gpt-4o-mini"
        )

        llm = await provider.get()

        assert llm is not None
        assert llm.model_name == "gpt-4o-mini"

    async def test_p3_falls_back_to_default_when_utility_missing(
        self,
        cache: InMemoryCache,
        factory: RecordingLLMFactory,
        counting_repo: CountingRepository,
        mock_logger: Any,
    ) -> None:
        """P3: 보조 모델명이 DB에 없음 → warning + 기본 모델 폴백."""
        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)
        provider = _build(cache, factory, counting_repo, mock_logger, "no-such")

        llm = await provider.get()

        assert llm is not None
        assert llm.model_name == "gpt-4o"
        mock_logger.warning.assert_called()

    async def test_p4_falls_back_when_utility_model_inactive(
        self,
        cache: InMemoryCache,
        factory: RecordingLLMFactory,
        counting_repo: CountingRepository,
        mock_logger: Any,
    ) -> None:
        """P4: 보조 모델이 비활성 → warning + 기본 모델 폴백."""
        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)
        counting_repo._by_id["u"] = _model("u", "dead", is_active=False)
        provider = _build(cache, factory, counting_repo, mock_logger, "dead")

        llm = await provider.get()

        assert llm is not None
        assert llm.model_name == "gpt-4o"
        mock_logger.warning.assert_called()

    async def test_p5_returns_none_when_no_default_model(
        self, provider: UtilityLLMProvider, mock_logger: Any
    ) -> None:
        """P5: 기본 모델도 없음 → warning + None."""
        assert await provider.get() is None
        mock_logger.warning.assert_called()


class TestInstanceCache:
    """P6~P10 — L1/L2 캐시 동작."""

    async def test_p6_same_temperature_reuses_instance(
        self,
        provider: UtilityLLMProvider,
        counting_repo: CountingRepository,
        factory: RecordingLLMFactory,
    ) -> None:
        """P6: 동일 temperature 2회 호출 → LLMFactory.create 1회만."""
        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)

        first = await provider.get(0.0)
        second = await provider.get(0.0)

        assert first is second
        assert len(factory.calls) == 1

    async def test_p7_different_temperature_creates_new_instance(
        self,
        provider: UtilityLLMProvider,
        counting_repo: CountingRepository,
        factory: RecordingLLMFactory,
    ) -> None:
        """P7: 다른 temperature → 키가 달라 create 2회."""
        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)

        await provider.get(0.0)
        await provider.get(0.7)

        assert len(factory.calls) == 2
        assert factory.calls[0][1] == 0.0
        assert factory.calls[1][1] == 0.7

    async def test_p8_l1_cache_avoids_repeat_db_query(
        self, provider: UtilityLLMProvider, counting_repo: CountingRepository
    ) -> None:
        """P8: 2회 호출 사이 L1 히트 → DB 조회 1회만."""
        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)

        await provider.get(0.0)
        await provider.get(0.7)  # L2 미스지만 L1 히트여야 한다

        assert counting_repo.find_default_calls == 1

    async def test_p9_invalidate_forces_db_requery(
        self, provider: UtilityLLMProvider, counting_repo: CountingRepository
    ) -> None:
        """P9: invalidate() 후 호출 → DB 재조회."""
        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)
        await provider.get(0.0)

        await provider.invalidate()
        await provider.get(0.0)

        assert counting_repo.find_default_calls == 2

    async def test_p10_updated_at_change_yields_new_instance(
        self, provider: UtilityLLMProvider, counting_repo: CountingRepository
    ) -> None:
        """P10: updated_at 이 바뀌면 L2 키가 달라져 새 인스턴스가 만들어진다 (DR-3)."""
        old = datetime.now(timezone.utc)
        counting_repo._by_id["d"] = _model(
            "d", "gpt-4o", is_default=True, updated_at=old
        )
        first = await provider.get(0.0)

        # 관리자가 모델을 수정한 상황 — updated_at 갱신 후 캐시 무효화
        counting_repo._by_id["d"] = _model(
            "d", "gpt-4o", is_default=True, updated_at=old + timedelta(minutes=1)
        )
        await provider.invalidate()
        second = await provider.get(0.0)

        assert first is not second

    async def test_l2_respects_max_instances(
        self,
        cache: InMemoryCache,
        factory: RecordingLLMFactory,
        counting_repo: CountingRepository,
        mock_logger: Any,
    ) -> None:
        """L2 상한 초과 시 가장 오래된 인스턴스가 축출된다 (§3.3)."""
        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)
        provider = UtilityLLMProvider(
            cache=cache,
            llm_factory=factory,
            session_factory=lambda: FakeSession(),
            repo_builder=lambda _s: counting_repo,
            logger=mock_logger,
            ttl_seconds=60.0,
            max_instances=2,
        )

        await provider.get(0.1)
        await provider.get(0.2)
        await provider.get(0.3)  # 0.1 축출
        await provider.get(0.1)  # 재생성

        assert len(factory.calls) == 4


class TestFailureIsolation:
    """P11~P13 — provider 는 예외를 던지지 않는다 (DR-7)."""

    async def test_p11_db_error_returns_none_without_raising(
        self, provider: UtilityLLMProvider, counting_repo: CountingRepository,
        mock_logger: Any,
    ) -> None:
        """P11: DB 조회 예외 → error 로그 + None."""
        counting_repo.raises = RuntimeError("db down")

        assert await provider.get() is None
        mock_logger.error.assert_called()

    async def test_p12_factory_error_returns_none_without_raising(
        self,
        cache: InMemoryCache,
        counting_repo: CountingRepository,
        mock_logger: Any,
    ) -> None:
        """P12: LLMFactory.create 예외 → error 로그 + None."""
        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)
        provider = _build(
            cache,
            RecordingLLMFactory(raises=RuntimeError("bad provider")),
            counting_repo,
            mock_logger,
        )

        assert await provider.get() is None
        mock_logger.error.assert_called()

    async def test_p13_cache_error_is_treated_as_miss(
        self,
        factory: RecordingLLMFactory,
        counting_repo: CountingRepository,
        mock_logger: Any,
    ) -> None:
        """P13: 캐시 get 예외 → miss 취급, 정상 동작."""
        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)
        provider = _build(
            ExplodingCache(default_ttl_seconds=60.0),
            factory,
            counting_repo,
            mock_logger,
        )

        llm = await provider.get()

        assert llm is not None
        assert llm.model_name == "gpt-4o"

    async def test_invalidate_never_raises(
        self,
        factory: RecordingLLMFactory,
        counting_repo: CountingRepository,
        mock_logger: Any,
    ) -> None:
        """무효화 실패는 관리자 요청을 실패시키지 않는다 (§6.1)."""

        class BadCache(InMemoryCache):
            async def delete(self, key: str) -> None:
                raise RuntimeError("delete failed")

        provider = _build(
            BadCache(default_ttl_seconds=60.0), factory, counting_repo, mock_logger
        )

        await provider.invalidate()  # 예외가 나면 테스트 실패


class TestObservability:
    """P14 — NPU 전환 실측 근거."""

    async def test_p14_base_url_is_logged_on_resolution(
        self, provider: UtilityLLMProvider, counting_repo: CountingRepository,
        mock_logger: Any,
    ) -> None:
        """P14: base_url 있는 모델 해석 시 로그에 base_url 이 포함된다."""
        counting_repo._by_id["d"] = _model(
            "d", "gemma-3-27b", is_default=True, base_url="http://npu:8000/v1"
        )

        await provider.get()

        logged = [
            call.kwargs
            for call in mock_logger.debug.call_args_list
            if "base_url" in call.kwargs
        ]
        assert logged, "해석 로그에 base_url 이 없다"
        assert logged[-1]["base_url"] == "http://npu:8000/v1"


class TestSerializationContract:
    """L1 에 담기는 값은 JSON 직렬화 가능해야 한다 (DR-2)."""

    async def test_l1_stores_json_serializable_value(
        self, provider: UtilityLLMProvider, counting_repo: CountingRepository,
        cache: InMemoryCache,
    ) -> None:
        import json

        counting_repo._by_id["d"] = _model("d", "gpt-4o", is_default=True)
        await provider.get()

        cached = await cache.get("llm_model:default")
        assert cached is not None
        json.dumps(cached)  # 예외가 나면 Redis 전환 시 깨진다
