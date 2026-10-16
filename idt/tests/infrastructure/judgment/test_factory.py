"""build_judgment_backend — Design §8.3 #1~4 (off / 누락 / 미설치 / 정상)."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from src.domain.judgment.value_objects import JudgmentBackendKind
from src.infrastructure.judgment.anyjev.adapter import AnyJevJudgmentAdapter
from src.infrastructure.judgment.factory import build_judgment_backend


def _settings(**overrides) -> SimpleNamespace:
    base = dict(
        judgment_backend="off",
        judgment_timeout_seconds=3.0,
        typesafe_api_key=None,
        typesafe_base_url=None,
        typesafe_model="jev-latest",
        anyjev_base_url=None,
        anyjev_model=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_off_returns_none():
    assert build_judgment_backend(_settings(), Mock()) is None


@pytest.mark.parametrize("raw", ["jev2", "", "  "])
def test_unknown_kind_raises(raw):
    with pytest.raises(ValueError):
        build_judgment_backend(_settings(judgment_backend=raw), Mock())


def test_jev_requires_api_key():
    with pytest.raises(ValueError, match="typesafe_api_key"):
        build_judgment_backend(_settings(judgment_backend="jev"), Mock())


def test_anyjev_requires_base_url():
    with pytest.raises(ValueError, match="anyjev_base_url"):
        build_judgment_backend(_settings(judgment_backend="anyjev"), Mock())


@pytest.mark.parametrize("url", ["ftp://x:1", "anyjev.internal:8100", "http://"])
def test_anyjev_rejects_non_http_url(url):
    with pytest.raises(ValueError, match="http"):
        build_judgment_backend(
            _settings(judgment_backend="anyjev", anyjev_base_url=url), Mock()
        )


def test_non_positive_timeout_raises():
    with pytest.raises(ValueError, match="timeout"):
        build_judgment_backend(
            _settings(
                judgment_backend="anyjev",
                anyjev_base_url="http://a:1",
                judgment_timeout_seconds=0,
            ),
            Mock(),
        )


def test_jev_missing_sdk_raises_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "typesafe_sdk", None)
    monkeypatch.delitem(
        sys.modules, "src.infrastructure.judgment.jev.adapter", raising=False
    )
    monkeypatch.delitem(
        sys.modules, "src.infrastructure.judgment.jev.mapping", raising=False
    )
    with pytest.raises(ImportError):
        build_judgment_backend(
            _settings(judgment_backend="jev", typesafe_api_key="k"), Mock()
        )


def test_anyjev_builds_adapter_and_logs():
    logger = Mock()
    backend = build_judgment_backend(
        _settings(
            judgment_backend="ANYJEV",
            anyjev_base_url=" http://anyjev.internal:8100/ ",
            anyjev_model="Tacit-9B",
        ),
        logger,
    )
    assert isinstance(backend, AnyJevJudgmentAdapter)
    assert backend.kind is JudgmentBackendKind.ANYJEV
    logger.info.assert_called_once()
    assert logger.info.call_args.kwargs["backend"] == "anyjev"


def test_jev_builds_adapter():
    pytest.importorskip("typesafe_sdk")
    from src.infrastructure.judgment.jev.adapter import JevJudgmentAdapter

    backend = build_judgment_backend(
        _settings(
            judgment_backend="jev", typesafe_api_key=" tsk-x ", typesafe_base_url=""
        ),
        Mock(),
    )
    assert isinstance(backend, JevJudgmentAdapter)
    assert backend.kind is JudgmentBackendKind.JEV
