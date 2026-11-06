"""PiiGuardedLLMFactory 단위 테스트 — Design §4.4, §11.1 (FR-06)."""

from unittest.mock import MagicMock

from src.application.pii_masking.guarded_llm import GuardedLlm
from src.application.pii_masking.guarded_llm_factory import PiiGuardedLLMFactory

from tests.application.pii_masking._support import make_masker


def _inner_factory(model):
    factory = MagicMock()
    factory.create = MagicMock(return_value=model)
    return factory


def test_create_wraps_model_when_masker_present():
    raw = MagicMock(name="raw")
    masker = make_masker()
    factory = PiiGuardedLLMFactory(_inner_factory(raw), lambda: masker)
    out = factory.create("llm-model", 0.3)
    assert isinstance(out, GuardedLlm)
    assert out.inner is raw
    assert out.scope is None  # 앱 싱글턴 소비자 — 호출 단위 scope


def test_create_passes_arguments_through():
    inner = _inner_factory(MagicMock())
    PiiGuardedLLMFactory(inner, lambda: make_masker()).create("m", temperature=0.7)
    inner.create.assert_called_once_with("m", temperature=0.7)


def test_create_returns_raw_when_masking_disabled():
    raw = MagicMock(name="raw")
    factory = PiiGuardedLLMFactory(_inner_factory(raw), lambda: None)
    assert factory.create("m") is raw


def test_masker_resolved_at_call_time_not_construction():
    masker_box: list = [None]
    raw = MagicMock(name="raw")
    factory = PiiGuardedLLMFactory(_inner_factory(raw), lambda: masker_box[0])
    assert factory.create("m") is raw
    masker_box[0] = make_masker()
    assert isinstance(factory.create("m"), GuardedLlm)


def test_guard_wraps_externally_built_model():
    raw = MagicMock(name="chatopenai")
    factory = PiiGuardedLLMFactory(_inner_factory(MagicMock()), lambda: make_masker())
    guarded = factory.guard(raw)
    assert isinstance(guarded, GuardedLlm) and guarded.inner is raw


def test_guard_does_not_double_wrap():
    factory = PiiGuardedLLMFactory(_inner_factory(MagicMock()), lambda: make_masker())
    once = factory.guard(MagicMock())
    assert factory.guard(once) is once
