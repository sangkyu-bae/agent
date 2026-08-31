"""domain/blueprint 포트 (Design §9.3).

- SampleExtractorPort: Golden Sample 바이트 → SampleStats (PyMuPDF / python-pptx 구현)
- PageClassifierPort: 페이지 PNG + 힌트 → PagePatternDraft (비전 LLM)
- SlideRendererPort: blueprint + 슬라이드 내용 → PPTX 바이트
- BlueprintRepository: 영속화
- FontCatalogPort: 서버 설치 폰트 목록·매핑 제안
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from src.domain.blueprint.schemas import NarrativeDraft, PagePatternDraft
from src.domain.blueprint.value_objects import (
    BlueprintAsset,
    DocumentBlueprint,
    PagePattern,
    SampleStats,
    SlideContent,
)


@dataclass(frozen=True)
class PageHints:
    """수치 신호 — 비전 분류의 힌트 (Design §5 리스크 완화)."""

    page_number: int
    page_count: int
    has_tables: bool
    image_count: int
    largest_image_area: float
    title_candidates: tuple[str, ...]


class SampleExtractorPort(Protocol):
    supported_extensions: tuple[str, ...]

    def extract(self, data: bytes, filename: str, max_pages: int) -> SampleStats: ...


class PageClassifierPort(Protocol):
    async def classify(
        self, page_png: bytes, hints: PageHints, language: str
    ) -> PagePatternDraft: ...


class SlideRendererPort(Protocol):
    def render(
        self,
        blueprint: DocumentBlueprint,
        slides: Sequence[SlideContent],
        assets: Mapping[str, bytes],
        font_mapping: Mapping[str, str],
    ) -> bytes: ...


@dataclass(frozen=True)
class StoredAsset:
    asset: BlueprintAsset
    data: bytes


class BlueprintRepository(Protocol):
    async def save(
        self,
        blueprint: DocumentBlueprint,
        assets: Sequence[StoredAsset],
        created_by: str,
    ) -> None: ...

    async def update(self, blueprint: DocumentBlueprint) -> None: ...

    async def replace(
        self, blueprint: DocumentBlueprint, asset_bytes: Mapping[str, bytes]
    ) -> None:
        """재추출(blueprint-style-fidelity §4.3): JSON 전체 + 에셋 행 교체."""
        ...

    async def find_by_id(self, blueprint_id: str) -> DocumentBlueprint | None: ...

    async def list_all(self, include_inactive: bool) -> list[DocumentBlueprint]: ...

    async def load_asset(
        self, blueprint_id: str, asset_id: str
    ) -> StoredAsset | None: ...

    async def load_assets(self, blueprint_id: str) -> dict[str, bytes]: ...


class FontCatalogPort(Protocol):
    def installed(self) -> tuple[str, ...]: ...

    def default_font(self) -> str: ...

    def suggest(self, source_font: str) -> str | None: ...

    def propose_mapping(
        self, source_fonts: tuple[str, ...]
    ) -> tuple[dict[str, str], tuple[str, ...]]:
        """(매핑, 경고) — 미설치 폰트는 기본 폰트로 대체하고 경고를 낸다."""
        ...


class NarrativeSynthesizerPort(Protocol):
    """패턴 순서·제목 후보 → NarrativeDraft (텍스트 LLM)."""

    async def synthesize(
        self,
        patterns: Sequence[PagePattern],
        titles: Sequence[str],
        language: str,
    ) -> NarrativeDraft: ...
