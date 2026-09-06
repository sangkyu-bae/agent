"""PDF 글리프 누락(.notdef) 검사기 — 테스트 전용 헬퍼.

Design Ref: fix-doc-generator-korean-font §8.5 — 2026-09-04 test.pdf 진단에
사용한 방법을 자동화한 것. "PDF는 열리는데 글자가 안 보이는" 상태를 기계적으로
잡아내, 같은 사고를 다시 놓치지 않게 한다.

두 가지 전략을 순서대로 시도한다:
  1. cmap-cid       — /Encoding CMap 의 begincidchar 에서 CID 0 비율을 센다.
                      WeasyPrint(pydyf) 계열 산출물이 여기에 해당한다.
  2. embedded-outline — 임베드된 폰트의 cmap 이 코드를 .notdef 로 보내는지 센다.
                      reportlab(xhtml2pdf) 처럼 단순 TrueType 으로 심는 산출물용.

폰트가 하나도 임베드되지 않은 PDF 는 "정상"이 아니라 **검증 불가**(verifiable
=False)로 돌려준다. 기본 14폰트(Helvetica)로 한글을 그리려 한 PDF 가 조용히
통과하던 사각지대를 막기 위한 것이다.

프로덕션 코드가 아니므로 src/ 규칙(레이어·40줄)을 강제받지 않으나,
판정 로직은 단순하고 검증 가능하게 유지한다.
"""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass

_STREAM_RE = re.compile(rb"stream\r?\n")
_BASEFONT_RE = re.compile(rb"/BaseFont\s*/([A-Za-z0-9+#_\-]+)")
_CIDCHAR_BLOCK_RE = re.compile(
    r"begincidchar(.*?)endcidchar", re.DOTALL
)
_CIDCHAR_PAIR_RE = re.compile(r"<([0-9a-fA-F]{2,8})>\s+(\d+)")

_SFNT_MAGICS = (b"\x00\x01\x00\x00", b"true", b"ttcf", b"OTTO")


@dataclass(frozen=True)
class GlyphCheckResult:
    """검사 결과. ratio 가 0이어야 '한글이 보이는 PDF'다."""

    strategy: str
    total_codes: int
    notdef_codes: int
    missing_chars: tuple[str, ...]
    base_fonts: tuple[str, ...]

    @property
    def ratio(self) -> float:
        if self.total_codes == 0:
            return 0.0
        return self.notdef_codes / self.total_codes

    @property
    def is_broken(self) -> bool:
        return self.notdef_codes > 0

    @property
    def verifiable(self) -> bool:
        """수치 판정이 가능한 경우에만 True.

        폰트가 아예 없거나(no-fonts) cmap 을 버린 서브셋(embedded-unparsed)이면
        '깨지지 않았다'고 말할 수 없다.
        """
        return self.strategy in ("cmap-cid", "embedded-outline")

    @property
    def has_embedded_font(self) -> bool:
        return self.strategy != "no-fonts"


def check_glyphs(pdf_bytes: bytes) -> GlyphCheckResult:
    """PDF 바이트에서 글리프 누락 비율을 계산한다."""
    streams = _extract_streams(pdf_bytes)
    base_fonts = _extract_base_fonts(pdf_bytes, streams)

    cid_result = _check_by_cid_cmap(streams, base_fonts)
    if cid_result is not None:
        return cid_result

    outline_result = _check_by_embedded_outline(streams, base_fonts)
    if outline_result is not None:
        return outline_result

    return GlyphCheckResult("no-fonts", 0, 0, (), base_fonts)


# ── 전략 1: Encoding CMap 의 CID 0 ───────────────────────────────────────
def _check_by_cid_cmap(
    streams: list[bytes], base_fonts: tuple[str, ...]
) -> GlyphCheckResult | None:
    total = 0
    notdef = 0
    for text in _as_text(streams):
        for block in _CIDCHAR_BLOCK_RE.findall(text):
            for _code, cid in _CIDCHAR_PAIR_RE.findall(block):
                total += 1
                if int(cid) == 0:
                    notdef += 1
    if total == 0:
        return None
    return GlyphCheckResult("cmap-cid", total, notdef, (), base_fonts)


# ── 전략 2: 임베드 폰트 cmap → .notdef 여부 ───────────────────────────────
def _check_by_embedded_outline(
    streams: list[bytes], base_fonts: tuple[str, ...]
) -> GlyphCheckResult | None:
    from fontTools.ttLib import TTFont  # 테스트 헬퍼에서만 필요

    total = 0
    notdef = 0
    embedded = False
    for raw in streams:
        if not raw.startswith(_SFNT_MAGICS):
            continue
        embedded = True
        try:
            font = TTFont(_BytesReader(raw), fontNumber=0, lazy=True)
            tables = font["cmap"].tables
        except Exception:
            continue  # cmap 을 버린 서브셋 — 아래에서 unparsed 로 보고한다
        for table in tables:
            for glyph in table.cmap.values():
                total += 1
                if glyph == ".notdef":
                    notdef += 1
    if total:
        return GlyphCheckResult("embedded-outline", total, notdef, (), base_fonts)
    if embedded:
        # 폰트는 심겼는데 cmap 이 없어 수치를 낼 수 없다 — '정상'이라고 말하지
        # 않되, '폰트 없음'과도 구분한다 (PPTX→PDF 산출물이 여기 해당).
        return GlyphCheckResult("embedded-unparsed", 0, 0, (), base_fonts)
    return None


# ── 공통 파싱 ────────────────────────────────────────────────────────────
def _extract_streams(pdf_bytes: bytes) -> list[bytes]:
    out: list[bytes] = []
    for match in _STREAM_RE.finditer(pdf_bytes):
        start = match.end()
        end = pdf_bytes.find(b"endstream", start)
        if end == -1:
            continue
        raw = pdf_bytes[start:end]
        try:
            out.append(zlib.decompress(raw))
        except zlib.error:
            out.append(raw)
    return out


def _extract_base_fonts(
    pdf_bytes: bytes, streams: list[bytes]
) -> tuple[str, ...]:
    names: set[str] = set()
    for blob in (pdf_bytes, *streams):
        for found in _BASEFONT_RE.findall(blob):
            names.add(found.decode("latin1"))
    return tuple(sorted(names))


def _as_text(streams: list[bytes]):
    for raw in streams:
        if b"begincmap" not in raw and b"begincidchar" not in raw:
            continue
        yield raw.decode("latin1")


class _BytesReader:
    """TTFont 가 요구하는 최소 file-like 래퍼."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def read(self, size: int = -1) -> bytes:
        end = len(self._data) if size < 0 else min(self._pos + size, len(self._data))
        chunk = self._data[self._pos:end]
        self._pos = end
        return chunk

    def seek(self, offset: int, whence: int = 0) -> int:
        base = (0, self._pos, len(self._data))[whence]
        self._pos = base + offset
        return self._pos

    def tell(self) -> int:
        return self._pos

    def close(self) -> None:
        return None
