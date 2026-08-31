"""블루프린트 폰트명 정규화 — 저장된 오염 폰트명을 로드 경계에서 바로잡는다.

Design Ref: blueprint-font-mapping-migration §2 (Option C) / DR-1·DR-2·DR-5·DR-6
- font_mapping 은 추출 시점에 blueprint_json 으로 고정 저장된다. 재추출 없이도
  유효한 패밀리명이 되도록, 읽기 경계에서 이 함수를 통과시킨다.
- style.fonts(조회 키)와 font_mapping(조회 표)을 **함께** 정규화한다 (DR-2).
  렌더러는 전자를 키로 후자를 조회하므로(pptx_renderer._Ctx.font), 한쪽만 바꾸면
  조회가 빗나가 매핑이 무력해진다.
- 순수 함수: 예외를 던지지 않고 로깅도 하지 않는다 (설계 §6).
"""

from __future__ import annotations

from dataclasses import replace

from src.domain.blueprint.policies import FontFamilyPolicy
from src.domain.blueprint.value_objects import DocumentBlueprint


def normalize_blueprint_fonts(blueprint: DocumentBlueprint) -> DocumentBlueprint:
    """style.fonts 와 font_mapping 의 폰트명을 패밀리명으로 정규화한다 (FR-01/02).

    이미 정규화된 블루프린트는 **같은 객체**를 그대로 돌려준다 (Plan SC-2 멱등).
    """
    style = blueprint.style
    fonts = _normalized_fonts(style.fonts)
    mapping = _normalized_mapping(blueprint.font_mapping)
    if fonts == style.fonts and mapping == blueprint.font_mapping:
        return blueprint
    return replace(
        blueprint,
        style=replace(style, fonts=fonts),
        font_mapping=mapping,
    )


def _family(name: str) -> str:
    """패밀리명만 취한다. 굵기 힌트는 버린다 — run 의 bold 속성이 이미 표현 (DR-5)."""
    family, _ = FontFamilyPolicy.normalize(name)
    return family or name


def _normalized_fonts(fonts: dict[str, str]) -> dict[str, str]:
    return {role: _family(name) for role, name in fonts.items()}


def _normalized_mapping(mapping: dict[str, str]) -> dict[str, str]:
    """키·값을 함께 정규화한다. 같은 패밀리로 접힌 키는 사전순 첫 값을 남긴다 (DR-6)."""
    grouped: dict[str, set[str]] = {}
    for source, target in mapping.items():
        grouped.setdefault(_family(source), set()).add(_family(target))
    return {key: sorted(values)[0] for key, values in grouped.items()}
