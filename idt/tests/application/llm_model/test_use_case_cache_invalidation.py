"""LLM 모델 변경 UseCase의 캐시 무효화 의무 호출 테스트.

Design Ref: admin-default-llm-routing §8.4 시나리오 U1~U6 / AD-3.

★ 핵심 계약: 관리자가 모델을 바꾸면 UseCase 가 provider.invalidate() 를
   반드시 호출한다. router/테스트가 빼먹어도 여기서 강제 검증한다
   (update_llm_model_pricing_use_case 의 cost_calculator 선례와 동일 취지).
"""
from decimal import Decimal
from typing import Any

import pytest

from src.application.llm_model.create_llm_model_use_case import (
    CreateLlmModelUseCase,
)
from src.application.llm_model.deactivate_llm_model_use_case import (
    DeactivateLlmModelUseCase,
)
from src.application.llm_model.schemas import (
    CreateLlmModelRequest,
    UpdateLlmModelRequest,
    UpdatePricingRequest,
)
from src.application.llm_model.update_llm_model_pricing_use_case import (
    UpdateLlmModelPricingUseCase,
)
from src.application.llm_model.update_llm_model_use_case import (
    UpdateLlmModelUseCase,
)
from src.domain.llm.interfaces import UtilityLLMProviderPort

from tests.application.llm_model.conftest import InMemoryLlmModelRepository


class SpyProvider(UtilityLLMProviderPort):
    """invalidate 호출 횟수를 세는 스파이."""

    def __init__(self, raises: Exception | None = None) -> None:
        self.invalidate_calls = 0
        self._raises = raises

    async def get(self, temperature: float = 0.0) -> Any:
        return None

    async def invalidate(self) -> None:
        if self._raises is not None:
            raise self._raises
        self.invalidate_calls += 1


class SpyCostCalculator:
    """CostCalculator 스텁 — 기존 M1 G1 계약이 유지되는지 함께 본다."""

    def __init__(self) -> None:
        self.invalidated: list[str | None] = []

    def invalidate(self, llm_model_id: str | None = None) -> None:
        self.invalidated.append(llm_model_id)


@pytest.fixture
def provider() -> SpyProvider:
    return SpyProvider()


def _create_request() -> CreateLlmModelRequest:
    return CreateLlmModelRequest(
        provider="openai",
        model_name="gemma-3-27b",
        display_name="Gemma 3 27B (NPU)",
        api_key_env="NPU_API_KEY",
        base_url="http://npu:8000/v1",
    )


class TestInvalidationIsMandatory:
    """U1~U4 — 네 경로 모두 무효화를 호출한다."""

    async def test_u1_update_invalidates_cache(
        self,
        repo: InMemoryLlmModelRepository,
        mock_logger: Any,
        seeded_model: Any,
        provider: SpyProvider,
    ) -> None:
        """U1: UpdateLlmModelUseCase — D-8 이 지적한 핵심 구멍."""
        use_case = UpdateLlmModelUseCase(
            repository=repo, logger=mock_logger, llm_provider=provider
        )

        await use_case.execute(
            seeded_model.id,
            UpdateLlmModelRequest(display_name="변경됨"),
            request_id="req-u1",
        )

        assert provider.invalidate_calls == 1

    async def test_u1_is_default_change_invalidates_cache(
        self,
        repo: InMemoryLlmModelRepository,
        mock_logger: Any,
        seeded_model: Any,
        provider: SpyProvider,
    ) -> None:
        """U1: is_default 토글이 무효화를 유발한다 (관리자 모델 교체 경로)."""
        use_case = UpdateLlmModelUseCase(
            repository=repo, logger=mock_logger, llm_provider=provider
        )

        await use_case.execute(
            seeded_model.id,
            UpdateLlmModelRequest(is_default=False),
            request_id="req-u1b",
        )

        assert provider.invalidate_calls == 1

    async def test_u2_create_invalidates_cache(
        self,
        repo: InMemoryLlmModelRepository,
        mock_logger: Any,
        provider: SpyProvider,
    ) -> None:
        """U2: CreateLlmModelUseCase."""
        use_case = CreateLlmModelUseCase(
            repository=repo, logger=mock_logger, llm_provider=provider
        )

        await use_case.execute(_create_request(), request_id="req-u2")

        assert provider.invalidate_calls == 1

    async def test_u3_deactivate_invalidates_cache(
        self,
        repo: InMemoryLlmModelRepository,
        mock_logger: Any,
        seeded_model: Any,
        provider: SpyProvider,
    ) -> None:
        """U3: DeactivateLlmModelUseCase — 비활성화된 모델이 계속 쓰이면 안 된다."""
        use_case = DeactivateLlmModelUseCase(
            repository=repo, logger=mock_logger, llm_provider=provider
        )

        await use_case.execute(seeded_model.id, request_id="req-u3")

        assert provider.invalidate_calls == 1

    async def test_u4_pricing_invalidates_both_caches(
        self,
        repo: InMemoryLlmModelRepository,
        mock_logger: Any,
        seeded_model: Any,
        provider: SpyProvider,
    ) -> None:
        """U4: 가격 변경은 cost_calculator 와 provider 를 모두 무효화한다."""
        cost_calc = SpyCostCalculator()
        use_case = UpdateLlmModelPricingUseCase(
            repository=repo,
            cost_calculator=cost_calc,
            logger=mock_logger,
            llm_provider=provider,
        )

        await use_case.execute(
            seeded_model.id,
            UpdatePricingRequest(
                input_price_per_1k_usd=Decimal("0.01"),
                output_price_per_1k_usd=Decimal("0.03"),
            ),
            request_id="req-u4",
        )

        assert cost_calc.invalidated == [seeded_model.id]  # 기존 M1 G1 유지
        assert provider.invalidate_calls == 1


class TestInvalidationFailureIsolation:
    """U5 — 무효화 실패가 관리자 요청을 실패시키지 않는다 (§6.1)."""

    async def test_u5_update_succeeds_when_invalidate_raises(
        self,
        repo: InMemoryLlmModelRepository,
        mock_logger: Any,
        seeded_model: Any,
    ) -> None:
        """모델 수정은 이미 DB에 반영됐다 — 캐시 실패로 500을 내면 안 된다."""
        bad = SpyProvider(raises=RuntimeError("cache backend down"))
        use_case = UpdateLlmModelUseCase(
            repository=repo, logger=mock_logger, llm_provider=bad
        )

        resp = await use_case.execute(
            seeded_model.id,
            UpdateLlmModelRequest(display_name="그래도 저장됨"),
            request_id="req-u5",
        )

        assert resp.display_name == "그래도 저장됨"
        mock_logger.warning.assert_called()

    async def test_u5_deactivate_succeeds_when_invalidate_raises(
        self,
        repo: InMemoryLlmModelRepository,
        mock_logger: Any,
        seeded_model: Any,
    ) -> None:
        bad = SpyProvider(raises=RuntimeError("cache backend down"))
        use_case = DeactivateLlmModelUseCase(
            repository=repo, logger=mock_logger, llm_provider=bad
        )

        resp = await use_case.execute(seeded_model.id, request_id="req-u5b")

        assert resp.is_active is False


class TestBackwardCompatibility:
    """U6 — provider 미주입 시 기존 동작 유지 (FR-9)."""

    async def test_u6_update_without_provider(
        self,
        repo: InMemoryLlmModelRepository,
        mock_logger: Any,
        seeded_model: Any,
    ) -> None:
        use_case = UpdateLlmModelUseCase(repository=repo, logger=mock_logger)

        resp = await use_case.execute(
            seeded_model.id,
            UpdateLlmModelRequest(display_name="주입 없음"),
            request_id="req-u6",
        )

        assert resp.display_name == "주입 없음"

    async def test_u6_create_without_provider(
        self, repo: InMemoryLlmModelRepository, mock_logger: Any
    ) -> None:
        use_case = CreateLlmModelUseCase(repository=repo, logger=mock_logger)

        resp = await use_case.execute(_create_request(), request_id="req-u6b")

        assert resp.model_name == "gemma-3-27b"

    async def test_u6_deactivate_without_provider(
        self,
        repo: InMemoryLlmModelRepository,
        mock_logger: Any,
        seeded_model: Any,
    ) -> None:
        use_case = DeactivateLlmModelUseCase(repository=repo, logger=mock_logger)

        resp = await use_case.execute(seeded_model.id, request_id="req-u6c")

        assert resp.is_active is False

    async def test_u6_pricing_without_provider(
        self,
        repo: InMemoryLlmModelRepository,
        mock_logger: Any,
        seeded_model: Any,
    ) -> None:
        cost_calc = SpyCostCalculator()
        use_case = UpdateLlmModelPricingUseCase(
            repository=repo, cost_calculator=cost_calc, logger=mock_logger
        )

        await use_case.execute(
            seeded_model.id,
            UpdatePricingRequest(
                input_price_per_1k_usd=Decimal("0.01"),
                output_price_per_1k_usd=Decimal("0.03"),
            ),
            request_id="req-u6d",
        )

        assert cost_calc.invalidated == [seeded_model.id]
