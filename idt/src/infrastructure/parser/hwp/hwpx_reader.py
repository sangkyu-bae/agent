"""HWPX(OWPML, ZIP+XML) 리더.

Design Ref: §3.4 — 표준 zipfile + ElementTree만 쓴다. 네임스페이스는 로컬 이름으로
매칭해 버전 차이에 영향받지 않는다. 표 표기는 HWP 5.0 리더와 같다(§3.3).
"""
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator

from src.domain.parser.exceptions import HwpEncryptedError, HwpParseError
from src.infrastructure.parser.hwp._types import join_blocks, render_table

_SECTION_RE = re.compile(r"Contents/section(\d+)\.xml")
_MANIFEST = "META-INF/manifest.xml"
_DOCTYPE_RE = re.compile(rb"<!DOCTYPE|<!ENTITY", re.IGNORECASE)
# Design Ref: §3.4 — 본문 흐름 밖 텍스트는 이름으로 제외한다.
# HWP 5.0 리더의 컨트롤 ID 제외(head/foot/fn/en)와 같은 기준.
_SKIPPED = frozenset({"header", "footer", "footNote", "endNote"})
# t 안의 인라인 요소 → 글자 (나머지 요소는 꼬리 글자만 살린다)
_INLINE_CHARS = {
    "tab": "\t",
    "lineBreak": "\n",
    "nbSpace": " ",
    "fwSpace": " ",
    "hyphen": "-",
}


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(elem: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in elem if _local(c.tag) == name]


def _t_text(t: ET.Element) -> str:
    parts = [t.text or ""]
    for child in t:
        parts.append(_INLINE_CHARS.get(_local(child.tag), ""))
        parts.append(child.tail or "")
    return "".join(parts)


def _own_text(elem: ET.Element) -> str:
    """요소 자신의 글자만 모은다. 안쪽 문단(p)·제외 대상은 들어가지 않는다."""
    parts: list[str] = []
    for child in elem:
        name = _local(child.tag)
        if name in _SKIPPED or name == "p":
            continue
        parts.append(_t_text(child) if name == "t" else _own_text(child))
    return "".join(parts)


def _iter_paragraphs(elem: ET.Element) -> Iterator[ET.Element]:
    """제외 대상 밖의 모든 문단을 문서 순서대로 (중첩 표·글상자 포함)."""
    for child in elem:
        name = _local(child.tag)
        if name in _SKIPPED:
            continue
        if name == "p":
            yield child
        yield from _iter_paragraphs(child)


def _cell_text(tc: ET.Element) -> str:
    """셀 안 문단(중첩 표 포함)을 공백으로 평탄화한다 — HWP 5.0과 같은 표기."""
    texts = (_own_text(p).strip() for p in _iter_paragraphs(tc))
    return " ".join(t for t in texts if t)


def _render_tbl(tbl: ET.Element) -> str:
    rows = [
        [_cell_text(tc) for tc in _children(tr, "tc")]
        for tr in _children(tbl, "tr")
    ]
    return render_table(rows)


def _embedded_blocks(elem: ET.Element, blocks: list[str]) -> None:
    """요소 아래 표는 표 블록으로, 글상자 등 안쪽 문단은 별도 블록으로 쌓는다."""
    for child in elem:
        name = _local(child.tag)
        if name in _SKIPPED:
            continue
        if name == "tbl":
            blocks.append(f"\n{_render_tbl(child)}\n")
        elif name == "p":
            blocks.append(_own_text(child))
            _embedded_blocks(child, blocks)
        else:
            _embedded_blocks(child, blocks)


def section_text(root: ET.Element) -> str:
    """문단 글자 → 그 문단에 박힌 표·글상자 순서 (HWP 5.0 리더와 같은 순서)."""
    blocks: list[str] = []
    _embedded_blocks(root, blocks)
    return join_blocks(blocks)


class HwpxReader:
    """HWPX 파일 → 섹션별 텍스트 (HwpSectionReader 구현)."""

    def __init__(self, max_decompressed_bytes: int) -> None:
        self._max_bytes = max_decompressed_bytes

    def read_sections(self, data: bytes) -> list[str]:
        buffer = io.BytesIO(data)
        if not zipfile.is_zipfile(buffer):
            raise HwpParseError("올바른 HWPX 파일이 아닙니다")
        try:
            with zipfile.ZipFile(buffer) as zf:
                self._check_container(zf)
                return [self._read_section(zf, name) for name in _section_names(zf)]
        except zipfile.BadZipFile as e:
            raise HwpParseError("HWPX 압축 구조가 손상됐습니다") from e

    def _check_container(self, zf: zipfile.ZipFile) -> None:
        total = sum(info.file_size for info in zf.infolist())
        if total > self._max_bytes:
            raise HwpParseError("한글 문서 압축 해제 크기가 상한을 넘었습니다")
        names = set(zf.namelist())
        if _MANIFEST in names and b"encryption-data" in zf.read(_MANIFEST):
            raise HwpEncryptedError()

    @staticmethod
    def _read_section(zf: zipfile.ZipFile, name: str) -> str:
        raw = zf.read(name)
        if _DOCTYPE_RE.search(raw):
            raise HwpParseError("HWPX 섹션에 허용되지 않는 DOCTYPE이 있습니다")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            raise HwpParseError(f"HWPX 섹션 XML이 손상됐습니다: {name}") from e
        return section_text(root)


def _section_names(zf: zipfile.ZipFile) -> list[str]:
    numbered: list[tuple[int, str]] = []
    for name in zf.namelist():
        match = _SECTION_RE.fullmatch(name)
        if match:
            numbered.append((int(match.group(1)), name))
    if not numbered:
        raise HwpParseError("HWPX 본문 섹션이 없습니다")
    return [name for _, name in sorted(numbered)]
