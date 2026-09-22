"""보조 LLM 해석 관측성 — prompt-fallback-visibility FR-00c.

**왜 필요한가** (Design §1-1):
`UTILITY_LLM_MODEL_NAME` 이 비어 있으면 보조 작업(프롬프트 생성·의도 판정)이
관리자가 정한 **기본 모델**을 그대로 따라간다. 2026-09-04 에 기본 모델이
추론 모델(gpt-5.1)로 바뀌자 프롬프트 생성이 항상 21~22초 걸려
`PROMPT_COMPOSER_TIMEOUT_SEC=20` 을 넘겼고, 폴백이 그 사실을 가렸다.

그 2주간 **"어떤 모델로 돌고 있는지"가 어디에도 남지 않았다.**
여기서 고정하는 것은 그 한 줄이다.
"""
from typing import Any

import pytest

from src.application.llm_model.utility_llm_provider import UtilityLLMProvider
from src.infrastructure.cache.in_memory_cache import InMemoryCache

from tests.application.llm_model.test_utility_llm_provider import (
    CountingRepository,
    FakeSession,
    RecordingLLMFactory,
    _build,
    _model,
)


class RecordingLogger:
    """레벨별 (message, kwargs) 를 모으는 로거."""

    def __init__(self) -> None:
        self.infos: list[tuple[str, dict]] = []
        self.warnings: list[tuple[str, dict]] = []
        self.errors: list[tuple[str, dict]] = []

    def debug(self, message: str, **kwargs: Any) -> None: ...

    def info(self, message: str, **kwargs: Any) -> None:
        self.infos.append((message, kwargs))

    def warning(self, message: str, **kwargs: Any) -> None:
        self.warnings.append((message, kwargs))

    def error(self, message: str, exception: Any = None, **kwargs: Any) -> None:
        self.errors.append((message, kwargs))

    def critical(self, message: str, exception: Any = None, **kwargs: Any) -> None: ...

    # ── 조회 헬퍼 ──
    def all_kwargs(self) -> list[dict]:
        return [kw for _, kw in self.infos + self.warnings + self.errors]

    def model_names_logged(self) -> list[str]:
        return [
            str(kw[k])
            for kw in self.all_kwargs()
            for k in ("model_name", "model")
            if k in kw
        ]


@pytest.fixture
def logger() -> RecordingLogger:
    return RecordingLogger()


async def _repo_with(*models) -> CountingRepository:
    """InMemoryLlmModelRepository 는 save() 로만 채운다."""
    r = CountingRepository()
    for m in models:
        await r.save(m, "test")
    return r


@pytest.fixture
def cache() -> InMemoryCache:
    return InMemoryCache(default_ttl_seconds=60.0, max_entries=100)


class TestDefaultResolutionIsObservable:
    """FR-00c — 기본 모델로 해석될 때 그 모델명이 로그에 남는다."""

    async def test_logs_resolved_model_name(
        self, cache: InMemoryCache, logger: RecordingLogger,
    ) -> None:
        repo = await _repo_with(_model("m1", "gpt-5.1", is_default=True))
        provider = _build(cache, RecordingLLMFactory(), repo, logger)

        llm = await provider.get(0.2)

        assert llm is not None
        assert "gpt-5.1" in logger.model_names_logged(), (
            "기본 모델로 해석됐는데 모델명이 어느 로그에도 없다 — "
            "설정이 바뀐 사실을 운영자가 알 길이 없다 (Design §1-1)"
        )

    async def test_marks_source_as_default(
        self, cache: InMemoryCache, logger: RecordingLogger,
    ) -> None:
        """'보조 모델 미설정이라 기본 모델을 따라간다'가 구분돼야 한다."""
        repo = await _repo_with(_model("m1", "gpt-5.1", is_default=True))
        provider = _build(cache, RecordingLLMFactory(), repo, logger)

        await provider.get(0.2)

        sources = [kw.get("source") for kw in logger.all_kwargs()]
        assert "default" in sources


class TestExplicitUtilityModelIsObservable:
    """보조 모델을 명시했을 때도 어떤 모델인지 남는다."""

    async def test_logs_explicit_model(
        self, cache: InMemoryCache, logger: RecordingLogger,
    ) -> None:
        repo = await _repo_with(
            _model("m1", "gpt-4o-mini"),
            _model("m2", "gpt-5.1", is_default=True),
        )
        provider = _build(
            cache, RecordingLLMFactory(), repo, logger,
            utility_model_name="gpt-4o-mini",
        )

        await provider.get(0.2)

        assert "gpt-4o-mini" in logger.model_names_logged()
        sources = [kw.get("source") for kw in logger.all_kwargs()]
        assert "utility" in sources


class TestUnresolvableNameStillWarns:
    """기존 경고(:111-117)는 유지된다 — 회귀 방지."""

    async def test_warns_when_name_unresolved(
        self, cache: InMemoryCache, logger: RecordingLogger,
    ) -> None:
        repo = await _repo_with(_model("m1", "gpt-5.1", is_default=True))
        provider = _build(
            cache, RecordingLLMFactory(), repo, logger,
            utility_model_name="does-not-exist",
        )

        await provider.get(0.2)

        assert any("unresolved" in m.lower() for m, _ in logger.warnings)
