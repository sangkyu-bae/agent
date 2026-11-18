"""graph_rag 도메인 VO (Design §3.1) — 값 검증은 GraphRagSettings 한 곳."""
import dataclasses

import pytest
from src.domain.graph_rag.value_objects import (
    DEFAULT_ENTITY_TYPES,
    DEFAULT_RELATION_TYPES,
    OTHER_TYPE,
    GraphRagSettings,
    RolloutStage,
)


def _settings(**over) -> GraphRagSettings:
    return dataclasses.replace(GraphRagSettings.defaults(), **over)


def test_defaults_are_closed_and_valid():
    s = GraphRagSettings.defaults()
    assert s.rollout_stage is RolloutStage.OFF
    assert s.extraction_enabled is False
    assert s.jev_enabled is False
    assert (s.link_threshold, s.new_threshold) == (0.8, 0.4)
    assert OTHER_TYPE in s.entity_types and OTHER_TYPE in s.relation_types
    assert s.entity_types == DEFAULT_ENTITY_TYPES
    assert s.relation_types == DEFAULT_RELATION_TYPES


@pytest.mark.parametrize("raw, stage", [
    ("off", RolloutStage.OFF), (" Admin_Only ", RolloutStage.ADMIN_ONLY),
    ("general", RolloutStage.GENERAL),
])
def test_stage_from_string(raw, stage):
    assert RolloutStage.from_string(raw) is stage


@pytest.mark.parametrize("raw", ["", None, "public", "on"])
def test_stage_from_string_rejects_unknown(raw):
    with pytest.raises(ValueError):
        RolloutStage.from_string(raw)


@pytest.mark.parametrize("over", [
    {"new_threshold": 0.8, "link_threshold": 0.8},   # new < link 위반
    {"new_threshold": 0.0},                          # 0 < new
    {"link_threshold": 1.01},
    {"concurrency": 0}, {"concurrency": 9},
    {"max_llm_calls_per_doc": 0}, {"max_llm_calls_per_doc": 2001},
    {"candidate_top_k": 0}, {"candidate_top_k": 9},
    {"max_hops": 0}, {"max_hops": 4},
    {"graph_rrf_weight": -0.1}, {"graph_rrf_weight": 1.1},
    {"retrieval_timeout_ms": 99}, {"retrieval_timeout_ms": 5001},
])
def test_range_violations_raise(over):
    with pytest.raises(ValueError):
        _settings(**over)


def test_types_must_include_other_and_be_unique_nonempty():
    with pytest.raises(ValueError):
        _settings(entity_types=("상품",))
    with pytest.raises(ValueError):
        _settings(relation_types=("요건", "요건", OTHER_TYPE))
    with pytest.raises(ValueError):
        _settings(entity_types=("", OTHER_TYPE))
    with pytest.raises(ValueError):
        _settings(entity_types=tuple(f"t{i}" for i in range(40)) + (OTHER_TYPE,))


def test_types_are_trimmed():
    s = _settings(entity_types=(" 상품 ", OTHER_TYPE))
    assert s.entity_types == ("상품", OTHER_TYPE)


def test_rejudge_model_falls_back_to_extraction_model():
    s = _settings(extraction_llm_model_id="m1", rejudge_llm_model_id=None)
    assert s.effective_rejudge_model_id == "m1"
    s2 = _settings(extraction_llm_model_id="m1", rejudge_llm_model_id="m2")
    assert s2.effective_rejudge_model_id == "m2"
