"""FontSubsetter — 사용 문자만 남긴 TTF 서브셋 생성.

Design Ref: fix-doc-generator-korean-font §2.3 / §4.2 — 전체 폰트를 base64 로
실으면 MCP 변환 페이로드가 수 MB 로 불어난다. 문서에 실제 등장하는 글자만
남겨 수십 KB 수준으로 유지하는 것이 Plan §5 최대 리스크의 완화책이다.

woff2 가 아니라 TTF 인 이유: 서브셋 이후에는 압축 이득이 작고, brotli 의존을
늘리지 않으며, WeasyPrint 와 reportlab 양쪽에서 같은 자산을 재사용할 수 있다.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

from src.domain.document_font.schemas import EmbeddedFont

_WEIGHT_FILES = {400: "Regular", 700: "Bold"}
_DATA_URI_PREFIX = "data:font/ttf;base64,"


class FontSubsetter:
    """폰트 자산을 읽어 weight 별 서브셋 EmbeddedFont 를 만든다."""

    def __init__(self, font_dir: Path, family: str) -> None:
        self._font_dir = Path(font_dir)
        self._family = family
        # 원본 폰트는 2.7MB 다. 매 문서마다 디스크에서 두 번씩 읽으면 서브셋
        # 오버헤드가 NFR(300ms)을 넘는다 — 파일 바이트와 cmap 을 캐시한다.
        self._bytes_cache: dict[str, bytes] = {}
        self._cmap_cache: dict[str, frozenset[int]] = {}

    def subset(self, weight: int, chars: frozenset[str]) -> EmbeddedFont:
        """chars 만 담은 서브셋 폰트를 만든다.

        Raises:
            FileNotFoundError: 해당 weight 의 폰트 자산이 없을 때.
        """
        path = self._resolve_path(weight)
        missing = self._find_missing(path, chars)
        usable = frozenset(chars) - set(missing)
        data = self._build_subset(self._read(path), usable)

        return EmbeddedFont(
            family=self._family,
            weight=weight,
            data_uri=_DATA_URI_PREFIX + base64.b64encode(data).decode("ascii"),
            byte_size=len(data),
            missing_chars=missing,
        )

    # ── 내부 ─────────────────────────────────────────────────────────────
    def _resolve_path(self, weight: int) -> Path:
        suffix = _WEIGHT_FILES.get(weight, _WEIGHT_FILES[400])
        path = self._font_dir / f"{self._family}-{suffix}.ttf"
        if not path.exists():
            raise FileNotFoundError(f"폰트 자산을 찾을 수 없습니다: {path}")
        return path

    def _read(self, path: Path) -> bytes:
        key = str(path)
        if key not in self._bytes_cache:
            self._bytes_cache[key] = path.read_bytes()
        return self._bytes_cache[key]

    def _find_missing(self, path: Path, chars: frozenset[str]) -> tuple[str, ...]:
        """폰트 cmap 에 없는 문자 — 예외 대신 보고 대상 (Plan FR-09)."""
        covered = self._covered_codepoints(path)
        return tuple(sorted(c for c in chars if ord(c) not in covered))

    def _covered_codepoints(self, path: Path) -> frozenset[int]:
        key = str(path)
        if key not in self._cmap_cache:
            with TTFont(io.BytesIO(self._read(path)), lazy=True) as font:
                self._cmap_cache[key] = frozenset(font.getBestCmap().keys())
        return self._cmap_cache[key]

    @staticmethod
    def _build_subset(font_bytes: bytes, chars: frozenset[str]) -> bytes:
        options = subset.Options()
        options.layout_features = ["kern", "liga"]
        options.notdef_outline = True
        options.recalc_bounds = False
        options.drop_tables += ["DSIG"]

        font = subset.load_font(io.BytesIO(font_bytes), options)
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(text="".join(sorted(chars)))
        subsetter.subset(font)

        buffer = io.BytesIO()
        subset.save_font(font, buffer, options)
        font.close()
        return buffer.getvalue()
