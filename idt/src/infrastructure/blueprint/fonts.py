"""FontCatalog — 서버 설치 폰트 스캔·기본 폰트·원본 폰트명 매핑 제안.

Design Ref: golden-sample-blueprint Plan FR-07 / §8.3 BLUEPRINT_FONT_DIR
- 폰트 파일 복제는 범위 밖(Plan §2.2). 폰트명 → 설치 폰트명 매핑만 제안한다.
- 미매핑은 원본 폰트명 유지 + 경고 (blueprint-style-fidelity FR-01 / DR-3).
  기본 폰트는 원본명이 비어 있을 때만 쓴다.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.domain.blueprint.policies import FontFamilyPolicy

_FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}
_NORMALIZE = re.compile(r"[\s\-_]+")

# 흔한 한글/오피스 폰트 별칭 → 계열 힌트 (설치 폰트명에 포함되는 키워드)
_FAMILY_ALIASES: dict[str, str] = {
    "맑은고딕": "gothic",
    "malgungothic": "gothic",
    "나눔고딕": "gothic",
    "nanumgothic": "gothic",
    "돋움": "gothic",
    "dotum": "gothic",
    "굴림": "gothic",
    "gulim": "gothic",
    "notosanskr": "gothic",
    "notosanscjk": "gothic",
    "바탕": "myeongjo",
    "batang": "myeongjo",
    "나눔명조": "myeongjo",
    "nanummyeongjo": "myeongjo",
}


def _norm(name: str) -> str:
    return _NORMALIZE.sub("", name).lower()


class FontCatalog:
    def __init__(self, font_dir: Path | None, default: str) -> None:
        self._default = default
        self._installed = self._scan(font_dir)

    @staticmethod
    def _scan(font_dir: Path | None) -> tuple[str, ...]:
        if font_dir is None or not font_dir.is_dir():
            return ()
        names = {
            p.stem for p in font_dir.iterdir() if p.suffix.lower() in _FONT_SUFFIXES
        }
        return tuple(sorted(names))

    def installed(self) -> tuple[str, ...]:
        return self._installed

    def default_font(self) -> str:
        return self._default

    def suggest(self, source_font: str) -> str | None:
        """설치 폰트명(정확 일치 → 정규화 일치 → 별칭 계열) 중 하나. 없으면 None."""
        if not self._installed:
            return None
        by_norm = {_norm(n): n for n in self._installed}
        family, _ = FontFamilyPolicy.normalize(source_font)
        for key in (_norm(source_font), _norm(family)):
            if key in by_norm:
                return by_norm[key]
        alias = _FAMILY_ALIASES.get(FontFamilyPolicy.alias_key(source_font))
        if alias is None:
            return None
        # 굵기는 run 의 bold 속성으로 표현하므로 후보는 regular 계열을 우선한다.
        candidates = [n for n in self._installed if alias in _norm(n)]
        regular = [n for n in candidates if "bold" not in _norm(n)]
        return (regular or candidates or [None])[0]

    def propose_mapping(
        self, source_fonts: tuple[str, ...]
    ) -> tuple[dict[str, str], tuple[str, ...]]:
        """원본 폰트명 → 사용할 폰트명. 미설치라도 패밀리명으로 정규화한다(FR-01)."""
        mapping: dict[str, str] = {}
        warnings: list[str] = []
        for font in source_fonts:
            target = self.suggest(font) or self._normalized_or_none(font)
            if target is None:
                target = font or self._default
                if font:
                    warnings.append(f"font '{font}' not installed — kept as-is")
            mapping[font] = target
        return mapping, tuple(warnings)

    @staticmethod
    def _normalized_or_none(font: str) -> str | None:
        """정규화로 이름이 실제 바뀐 경우에만 채택 (안 바뀌면 미해결로 본다)."""
        family, _ = FontFamilyPolicy.normalize(font)
        return family if family and family != font else None
