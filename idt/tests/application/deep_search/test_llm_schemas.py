"""deep-search-pipeline — LLM 구조화 출력 스키마의 provider 호환성 (D19).

OpenAI structured outputs(strict)는 모든 object에 대해
`additionalProperties: false` + 전 키 `required`를 요구한다.
따라서 `dict[str, str]` 같은 **열린 맵은 표현할 수 없다**.

실제 발생 오류:
    Invalid schema for response_format 'EvidenceExtractOut':
    'required' is required to be supplied and to be an array including
    every key in properties. Extra required key 'attrs' supplied.
"""
from __future__ import annotations

from typing import Iterator

import pytest

from src.application.deep_search.llm_schemas import (
    CoverageVerdictOut,
    EvidenceExtractOut,
    KeyValueOut,
    SearchPlanOut,
    to_mapping,
)

MODELS = [SearchPlanOut, EvidenceExtractOut, CoverageVerdictOut]


def _walk(schema: dict, path: str = "()") -> Iterator[tuple[str, dict]]:
    """JSON Schema를 재귀 순회하며 (경로, 노드)를 낸다."""
    if not isinstance(schema, dict):
        return
    yield path, schema
    for group in ("$defs", "properties"):
        for name, sub in (schema.get(group) or {}).items():
            yield from _walk(sub, f"{path}.{name}")
    if isinstance(schema.get("items"), dict):
        yield from _walk(schema["items"], f"{path}[]")
    for index, sub in enumerate(schema.get("anyOf") or []):
        yield from _walk(sub, f"{path}|{index}")


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_no_open_ended_maps(model):
    """열린 맵이 하나라도 있으면 OpenAI strict 모드에서 400이 난다."""
    offenders = [
        path
        for path, node in _walk(model.model_json_schema())
        if isinstance(node.get("additionalProperties"), dict)
    ]
    assert offenders == [], f"열린 맵 발견: {offenders}"


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_every_object_declares_properties(model):
    """strict 모드는 속성이 명시된 object만 허용한다 (임의 키 금지)."""
    schema = model.model_json_schema()
    for path, node in _walk(schema):
        if node.get("type") != "object":
            continue
        assert "properties" in node, f"{path}: properties 없는 object"


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_passes_openai_strict_contract(model):
    """OpenAI SDK의 실제 strict 변환기로 검증 — 구조 검사보다 강한 보증.

    strict 계약: 모든 object가 `additionalProperties: false`이고
    `required`가 `properties`의 전 키와 일치해야 한다.
    """
    to_strict = pytest.importorskip("openai.lib._pydantic").to_strict_json_schema

    violations: list[str] = []
    for path, node in _walk(to_strict(model)):
        if node.get("type") != "object":
            continue
        if node.get("additionalProperties") is not False:
            violations.append(f"{path}: additionalProperties != false")
        properties = set(node.get("properties") or {})
        required = set(node.get("required") or [])
        if properties != required:
            violations.append(f"{path}: required != properties (diff={properties ^ required})")
    assert violations == []


def test_open_ended_dict_would_violate_strict_contract():
    """회귀 근거 고정: `dict[str, str]`은 열린 맵이라 strict에서 거부된다.

    이 테스트가 깨진다면 provider 제약이 완화된 것이므로 D19를 재검토한다.
    """
    to_strict = pytest.importorskip("openai.lib._pydantic").to_strict_json_schema
    from pydantic import BaseModel

    class _OpenMap(BaseModel):
        attrs: dict[str, str] = {}

    schema = to_strict(_OpenMap)
    assert schema["properties"]["attrs"].get("additionalProperties") is not False


def test_key_value_pair_shape():
    kv = KeyValueOut(key="period", value="latest")
    assert (kv.key, kv.value) == ("period", "latest")


# ── to_mapping: LLM 표현 → 도메인 dict ──────────────────────────


def test_to_mapping_converts_pairs():
    pairs = [KeyValueOut(key="period", value="latest"),
             KeyValueOut(key="align", value="same_period")]
    assert to_mapping(pairs) == {"period": "latest", "align": "same_period"}


def test_to_mapping_on_empty_is_empty_dict():
    assert to_mapping([]) == {}
    assert to_mapping(None) == {}


def test_to_mapping_skips_blank_keys():
    """빈 키는 도메인 dict를 오염시키므로 버린다."""
    pairs = [KeyValueOut(key="  ", value="x"), KeyValueOut(key="period", value="latest")]
    assert to_mapping(pairs) == {"period": "latest"}


def test_to_mapping_last_wins_on_duplicate_key():
    pairs = [KeyValueOut(key="period", value="2025"), KeyValueOut(key="period", value="latest")]
    assert to_mapping(pairs) == {"period": "latest"}


def test_to_mapping_strips_key_whitespace():
    assert to_mapping([KeyValueOut(key=" period ", value="latest")]) == {"period": "latest"}
