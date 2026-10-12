"""HWP 5.0(OLE 바이너리) 리더.

Design Ref: §3.2 — olefile로 컨테이너를 열고 BodyText/SectionN 레코드에서
PARA_TEXT를 직접 읽는다 (pyhwp는 AGPL이라 쓰지 않음).
Design Ref: §3.3 — 표는 셀 " | ", 행 줄바꿈. 행 주소를 못 읽으면 한 줄로 강하.
"""
import io
import re
import struct
import zlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

import olefile

from src.domain.parser.exceptions import HwpEncryptedError, HwpParseError
from src.infrastructure.parser.hwp._types import join_blocks, render_table

# HWPTAG_BEGIN(16) + 오프셋
TAG_PARA_TEXT = 67
TAG_CTRL_HEADER = 71
TAG_LIST_HEADER = 72
TAG_TABLE = 77

_SIGNATURE = b"HWP Document File"
_FLAGS_OFFSET = 36
_FLAG_COMPRESSED = 0x1
_FLAG_PASSWORD = 0x2
_FLAG_DISTRIBUTION = 0x4

# 컨트롤 ID는 UINT32 LE로 저장돼 4글자가 뒤집혀 있다
_CTRL_TABLE = b" lbt"  # "tbl "
_CTRL_SKIPPED = frozenset({b"daeh", b"toof", b"  nf", b"  ne"})  # head, foot, fn, en

# §3.2 PARA_TEXT 컨트롤 문자 표 — 인라인·확장 컨트롤은 8 WCHAR를 차지한다
_WIDE_CONTROLS = frozenset(
    {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}
)
_CONTROL_WIDTH = 8
_CHAR_REPLACEMENTS = {9: "\t", 10: "\n", 24: "-", 30: " ", 31: " "}

# 셀 LIST_HEADER: 문단 리스트 헤더 8바이트 뒤 열 주소(UINT16), 행 주소(UINT16).
# 명세 문서는 리스트 헤더를 6바이트로 적지만 실파일은 8바이트다.
# pyhwp table.hwp 실파일로 확인 (Design §3.3):
# 오프셋 8=열, 10=행, 12=열 병합, 14=행 병합
_CELL_ROW_OFFSET = 10

_SECTION_RE = re.compile(r"Section(\d+)")


@dataclass(frozen=True)
class HwpRecord:
    tag_id: int
    level: int
    data: bytes


def iter_records(stream: bytes) -> Iterator[HwpRecord]:
    """레코드 헤더(TagID 10비트, Level 10비트, Size 12비트)를 따라 레코드를 읽는다."""
    pos, end = 0, len(stream)
    while pos + 4 <= end:
        (header,) = struct.unpack_from("<I", stream, pos)
        pos += 4
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if pos + 4 > end:
                raise HwpParseError("HWP 레코드 헤더가 잘렸습니다")
            (size,) = struct.unpack_from("<I", stream, pos)
            pos += 4
        if pos + size > end:
            raise HwpParseError("HWP 레코드가 잘렸습니다")
        yield HwpRecord(header & 0x3FF, (header >> 10) & 0x3FF, stream[pos:pos + size])
        pos += size


def decode_para_text(data: bytes) -> str:
    """PARA_TEXT(UTF-16LE)에서 컨트롤 문자를 걷어낸 글자만 돌려준다."""
    count = len(data) // 2
    codes = struct.unpack_from(f"<{count}H", data)
    units: list[int] = []
    i = 0
    while i < count:
        code = codes[i]
        if code >= 32:
            units.append(code)
            i += 1
            continue
        replacement = _CHAR_REPLACEMENTS.get(code)
        if replacement is not None:
            units.append(ord(replacement))
        i += _CONTROL_WIDTH if code in _WIDE_CONTROLS else 1
    packed = struct.pack(f"<{len(units)}H", *units)
    return packed.decode("utf-16-le", errors="replace")


def parse_file_header(header: bytes) -> bool:
    """FileHeader를 검사하고 본문 압축 여부를 돌려준다. 암호·배포용이면 거부."""
    if len(header) < _FLAGS_OFFSET + 4 or not header.startswith(_SIGNATURE):
        raise HwpParseError("올바른 HWP 파일이 아닙니다")
    (flags,) = struct.unpack_from("<I", header, _FLAGS_OFFSET)
    if flags & (_FLAG_PASSWORD | _FLAG_DISTRIBUTION):
        raise HwpEncryptedError()
    return bool(flags & _FLAG_COMPRESSED)


def inflate(raw: bytes, limit: int) -> bytes:
    """raw deflate를 풀되 limit 바이트를 넘으면 중단한다 (압축 폭탄 방지)."""
    decompressor = zlib.decompressobj(-15)
    try:
        out = decompressor.decompress(raw, limit + 1)
    except zlib.error as e:
        raise HwpParseError("HWP 본문 압축을 풀 수 없습니다") from e
    if len(out) > limit or decompressor.unconsumed_tail:
        raise HwpParseError("한글 문서 압축 해제 크기가 상한을 넘었습니다")
    return out


@dataclass
class _Table:
    """표 1개. 레코드 순서는 CTRL(tbl) → [캡션 LIST_HEADER·문단] → TABLE → 셀들.

    TABLE 레코드 전의 LIST_HEADER는 캡션이다 — 셀로 세면 캡션이 첫 셀이 된다
    (pyhwp table-caption.hwp 실파일로 확인).
    """

    level: int
    rows: list[list[list[str]]] = field(default_factory=list)
    caption: list[str] = field(default_factory=list)
    _body: bool = False
    _row: int | None = None
    _cell: list[str] | None = None

    def feed(self, record: HwpRecord) -> None:
        own_level = record.level == self.level + 1
        if record.tag_id == TAG_TABLE and own_level:
            self._body = True
        elif record.tag_id == TAG_LIST_HEADER and own_level:
            self._open_list(record.data)
        elif record.tag_id == TAG_PARA_TEXT and self._cell is not None:
            self._cell.append(decode_para_text(record.data).strip())

    def _open_list(self, data: bytes) -> None:
        if self._body:
            self._start_cell(data)
        else:
            self._cell = self.caption

    def _start_cell(self, data: bytes) -> None:
        row = _read_cell_row(data)
        if not self.rows or (row is not None and row != self._row):
            self.rows.append([])
            self._row = row
        self._cell = []
        self.rows[-1].append(self._cell)

    def render(self) -> str:
        rows = [[" ".join(p for p in cell if p) for cell in row] for row in self.rows]
        caption = " ".join(p for p in self.caption if p)
        return "\n".join(part for part in (caption, render_table(rows)) if part)


def _read_cell_row(data: bytes) -> int | None:
    if len(data) < _CELL_ROW_OFFSET + 2:
        return None
    (row,) = struct.unpack_from("<H", data, _CELL_ROW_OFFSET)
    return row


class _SectionBuilder:
    """레코드를 순서대로 받아 문단·표 블록을 쌓는다."""

    def __init__(self) -> None:
        self._blocks: list[str] = []
        self._table: _Table | None = None
        self._skip_level: int | None = None

    def feed(self, record: HwpRecord) -> None:
        self._close_scopes(record.level)
        if self._skip_level is not None:
            return
        ctrl_id = record.data[:4] if record.tag_id == TAG_CTRL_HEADER else b""
        # 머리말·꼬리말·각주·미주는 표 셀 안에서도 제외한다 (Design §3.2)
        if ctrl_id in _CTRL_SKIPPED:
            self._skip_level = record.level
        elif self._table is not None:
            self._table.feed(record)
        elif ctrl_id == _CTRL_TABLE:
            self._table = _Table(level=record.level)
        elif record.tag_id == TAG_PARA_TEXT:
            self._blocks.append(decode_para_text(record.data))

    def _close_scopes(self, level: int) -> None:
        if self._skip_level is not None and level <= self._skip_level:
            self._skip_level = None
        if self._table is not None and level <= self._table.level:
            self._flush_table()

    def _flush_table(self) -> None:
        if self._table is not None:
            self._blocks.append(f"\n{self._table.render()}\n")
            self._table = None

    def finish(self) -> str:
        self._flush_table()
        return join_blocks(self._blocks)


def section_text(records: Iterable[HwpRecord]) -> str:
    builder = _SectionBuilder()
    for record in records:
        builder.feed(record)
    return builder.finish()


class Hwp5Reader:
    """HWP 5.0 파일 → 섹션별 텍스트 (HwpSectionReader 구현)."""

    def __init__(self, max_decompressed_bytes: int) -> None:
        self._max_bytes = max_decompressed_bytes

    def read_sections(self, data: bytes) -> list[str]:
        if not olefile.isOleFile(data=data):
            raise HwpParseError("올바른 HWP 파일이 아닙니다")
        with olefile.OleFileIO(io.BytesIO(data)) as ole:
            compressed = parse_file_header(_read_stream(ole, "FileHeader"))
            budget = self._max_bytes
            sections: list[str] = []
            for path in _section_paths(ole):
                body = _read_stream(ole, path)
                if compressed:
                    body = inflate(body, budget)
                budget -= len(body)
                sections.append(section_text(iter_records(body)))
            return sections


def _read_stream(ole: olefile.OleFileIO, path: str) -> bytes:
    if not ole.exists(path):
        raise HwpParseError(f"HWP 스트림이 없습니다: {path}")
    return ole.openstream(path).read()


def _section_paths(ole: olefile.OleFileIO) -> list[str]:
    numbered: list[tuple[int, str]] = []
    for entry in ole.listdir():
        if len(entry) != 2 or entry[0] != "BodyText":
            continue
        match = _SECTION_RE.fullmatch(entry[1])
        if match:
            numbered.append((int(match.group(1)), "/".join(entry)))
    if not numbered:
        raise HwpParseError("HWP 본문 섹션이 없습니다")
    return [path for _, path in sorted(numbered)]


__all__ = [
    "Hwp5Reader",
    "HwpRecord",
    "TAG_CTRL_HEADER",
    "TAG_LIST_HEADER",
    "TAG_PARA_TEXT",
    "decode_para_text",
    "inflate",
    "iter_records",
    "parse_file_header",
    "section_text",
]
