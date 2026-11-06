"""PII 탐지 코퍼스 검증 — 코퍼스가 규칙을 검증한다 (Design §1.2, §8.2)."""
import pytest
from src.infrastructure.pii_masking.regex_detectors import RegexPiiDetector

from tests.infrastructure.pii_masking._corpus import (
    load_benign,
    load_known_fp,
    load_pii,
)

_detect = RegexPiiDetector().detect


@pytest.mark.parametrize(("pii_type", "value", "sentence"), load_pii())
def test_detect_pii_sentence_returns_exact_value(pii_type, value, sentence):
    found = [(m.pii_type, m.text) for m in _detect(sentence)]
    assert (pii_type, value) in found


@pytest.mark.parametrize("sentence", load_benign())
def test_detect_benign_sentence_returns_nothing(sentence):
    assert [(m.pii_type.value, m.text) for m in _detect(sentence)] == []


@pytest.mark.parametrize(("pii_type", "value", "sentence"), load_known_fp())
def test_detect_known_false_positive_stays_pinned(pii_type, value, sentence):
    found = [(m.pii_type, m.text) for m in _detect(sentence)]
    assert found == [(pii_type, value)]
