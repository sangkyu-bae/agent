"""관리자 모델 변경 → 어댑터 반영 전 구간 통합 테스트.

Design Ref: admin-default-llm-routing — Plan FR-5 / FR-3 / DoD.

실물 컴포넌트로 체인을 잇는다 (모킹은 LLM 생성 지점 하나뿐):
    UpdateLlmModelUseCase          (module-3)
        → invalidate_llm_model_cache
        → UtilityLLMProvider       (module-2)
            → InMemoryCache        (module-1)
            → LLMFactory (스텁)
        → LLMSearchDecisionAdapter (module-4)

증명하는 것
    FR-5  관리자가 기본 모델을 바꾸면 **서버 재시작 없이** 다음 호출부터 반영된다
    FR-3  is_default 모델이 어댑터의 LLM 이 된다
    DoD   해석된 모델의 base_url 이 self-host 주소로 전달된다 (OpenAI 아님)

증명하지 못하는 것 (환경 필요)
    NPU 엔드포인트가 실제로 응답하는지 — Step 0(vLLM tool-calling 검증) 대상
"""
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.runnables import RunnableLambda

from src.application.llm_model.schemas import UpdateLlmModelRequest
from src.application.llm_model.update_llm_model_use_case import (
    UpdateLlmModelUseCase,
)
from src.application.llm_model.utility_llm_provider import UtilityLLMProvider
from src.domain.llm_model.entity import LlmModel
from src.domain.search_decision.schemas import WebSearchDecision
from src.infrastructure.cache.in_memory_cache import InMemoryCache
from src.infrastructure.search_decision.adapter import LLMSearchDecisionAdapter

from tests.application.llm_model.conftest import InMemoryLlmModelRepository


class RecordingLLM:
    """LLMFactory 가 만든 LLM. 어느 모델에서 왔는지 기억한다."""

    def __init__(self, model: LlmModel) -> None:
        self.model_name = model.model_name
        self.base_url = model.base_url

    def with_structured_output(self, schema: Any, **kwargs: Any) -> RunnableLambda:
        # 어느 모델이 판단했는지 결과에 실어 보낸다.
        name = self.model_name
        return RunnableLambda(
            lambda _p: WebSearchDecision(needs_web_search=name.startswith("gemma"))
        )


class RecordingFactory:
    """LLMFactory 스텁 — 전달된 LlmModel 을 기록한다."""

    def __init__(self) -> None:
        self.created: list[LlmModel] = []

    def create(self, llm_model: LlmModel, temperature: float = 0.0) -> RecordingLLM:
        self.created.append(llm_model)
        return RecordingLLM(llm_model)


class FakeSession:
    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


def _model(
    model_id: str,
    model_name: str,
    *,
    is_default: bool,
    base_url: str | None = None,
) -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id=model_id,
        provider="openai",
        model_name=model_name,
        display_name=model_name,
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=is_default,
        created_at=now,
        updated_at=now,
        base_url=base_url,
    )


@pytest.fixture
def chain_env() -> dict[str, Any]:
    """실물 캐시·저장소·provider·어댑터를 배선한 환경."""
    logger = MagicMock()
    repo = InMemoryLlmModelRepository()
    cache = InMemoryCache(default_ttl_seconds=60.0, max_entries=64)
    factory = RecordingFactory()

    provider = UtilityLLMProvider(
        cache=cache,
        llm_factory=factory,
        session_factory=lambda: FakeSession(),
        repo_builder=lambda _session: repo,
        logger=logger,
        utility_model_name=None,  # 기본 모델을 따라간다
        ttl_seconds=60.0,
        max_instances=8,
    )
    adapter = LLMSearchDecisionAdapter(logger=logger, llm_provider=provider)
    use_case = UpdateLlmModelUseCase(
        repository=repo, logger=logger, llm_provider=provider
    )
    return {
        "repo": repo,
        "cache": cache,
        "factory": factory,
        "provider": provider,
        "adapter": adapter,
        "use_case": use_case,
    }


class TestRestartFreeModelSwap:
    """FR-5 — 재시작 없이 관리자 모델 변경이 반영된다."""

    async def test_default_model_swap_reflects_without_restart(
        self, chain_env: dict[str, Any]
    ) -> None:
        repo, adapter, use_case = (
            chain_env["repo"],
            chain_env["adapter"],
            chain_env["use_case"],
        )
        factory: RecordingFactory = chain_env["factory"]

        openai_model = _model("m-openai", "gpt-4o-mini", is_default=True)
        npu_model = _model(
            "m-npu", "gemma-3-27b", is_default=False,
            base_url="http://npu-host:8000/v1",
        )
        repo._by_id[openai_model.id] = openai_model
        repo._by_id[npu_model.id] = npu_model

        # 1) 최초 호출 — 기본 모델(OpenAI)이 판단한다
        before = await adapter.decide("질문", "분석", "req-1")
        assert before.needs_web_search is False
        assert factory.created[-1].model_name == "gpt-4o-mini"

        # 2) 관리자가 NPU 모델을 기본으로 변경 (서버 재시작 없음)
        await use_case.execute(
            npu_model.id,
            UpdateLlmModelRequest(is_default=True),
            request_id="req-admin",
        )

        # 3) 다음 호출부터 NPU 모델이 판단한다
        after = await adapter.decide("질문", "분석", "req-2")

        assert after.needs_web_search is True, "재시작 없이 새 모델이 반영되지 않았다"
        assert factory.created[-1].model_name == "gemma-3-27b"

    async def test_selfhost_base_url_reaches_llm_factory(
        self, chain_env: dict[str, Any]
    ) -> None:
        """DoD — self-host base_url 이 LLMFactory 까지 온전히 전달된다.

        LLMFactory._create_openai 가 이 값을 ChatOpenAI(base_url=...) 로 넘긴다
        → 요청이 OpenAI 가 아니라 NPU 엔드포인트로 나간다.
        """
        repo, adapter = chain_env["repo"], chain_env["adapter"]
        factory: RecordingFactory = chain_env["factory"]

        repo._by_id["m-npu"] = _model(
            "m-npu", "gemma-3-27b", is_default=True,
            base_url="http://npu-host:8000/v1",
        )

        await adapter.decide("질문", "분석", "req-base-url")

        assert factory.created[-1].base_url == "http://npu-host:8000/v1"

    async def test_no_redundant_db_query_between_swaps(
        self, chain_env: dict[str, Any]
    ) -> None:
        """FR-5 의 이면 — 무효화 전까지는 캐시가 DB 조회를 막는다."""
        repo, adapter = chain_env["repo"], chain_env["adapter"]
        factory: RecordingFactory = chain_env["factory"]

        repo._by_id["m1"] = _model("m1", "gpt-4o-mini", is_default=True)

        await adapter.decide("q", "a", "r1")
        await adapter.decide("q", "a", "r2")
        await adapter.decide("q", "a", "r3")

        # L1/L2 히트로 LLM 생성은 최초 1회뿐이다
        assert len(factory.created) == 1


class TestInvalidationIsWhatMakesItWork:
    """무효화가 빠지면 반영되지 않는다 — D-8 구멍의 회귀 방지."""

    async def test_without_invalidation_stale_model_persists(
        self, chain_env: dict[str, Any]
    ) -> None:
        """provider 미주입 UseCase 로 바꾸면 캐시가 낡은 채 남는다.

        module-3 이전 상태(무효화 훅 없음)를 재현해, 무효화가 FR-5 의
        필수 조건임을 증명한다.
        """
        repo, adapter = chain_env["repo"], chain_env["adapter"]
        factory: RecordingFactory = chain_env["factory"]
        logger = MagicMock()

        repo._by_id["m-openai"] = _model("m-openai", "gpt-4o-mini", is_default=True)
        repo._by_id["m-npu"] = _model(
            "m-npu", "gemma-3-27b", is_default=False,
            base_url="http://npu-host:8000/v1",
        )

        await adapter.decide("q", "a", "r1")

        # llm_provider 미주입 = 무효화 훅 없음 (D-8 이전 상태)
        no_invalidate = UpdateLlmModelUseCase(repository=repo, logger=logger)
        await no_invalidate.execute(
            "m-npu", UpdateLlmModelRequest(is_default=True), request_id="r-stale"
        )

        result = await adapter.decide("q", "a", "r2")

        # 캐시가 낡은 채 남아 여전히 OpenAI 모델이 판단한다
        assert result.needs_web_search is False
        assert factory.created[-1].model_name == "gpt-4o-mini"
