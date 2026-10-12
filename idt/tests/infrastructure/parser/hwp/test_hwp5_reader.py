"""Hwp5Reader — HWP 5.0 바이너리 해석 단위 테스트.

hwp-parser Design §3.2, §3.3, §8 U-02~U-07.

실제 OLE 파일은 코드로 만들 수 없어서, 레코드·디코딩·헤더·압축 해제·섹션 조립을
바이트 단위로 각각 검증한다. 실제 파일 검증은 test_hwp_fixtures.py가 맡는다.
"""
import struct
import zlib

import pytest
from src.domain.parser.exceptions import HwpEncryptedError, HwpParseError
from src.infrastructure.parser.hwp.hwp5_reader import (
    TAG_CTRL_HEADER,
    TAG_LIST_HEADER,
    TAG_PARA_TEXT,
    Hwp5Reader,
    decode_para_text,
    inflate,
    iter_records,
    parse_file_header,
    section_text,
)

_TABLE_ID = b" lbt"  # "tbl " — UINT32 LE로 저장돼 바이트가 뒤집혀 있다
_HEADER_ID = b"daeh"  # "head"


def _units(*codes: int) -> bytes:
    return struct.pack(f"<{len(codes)}H", *codes)


def _text(s: str) -> bytes:
    return s.encode("utf-16-le")


def _ctrl(code: int) -> bytes:
    """인라인·확장 컨트롤: 코드 + 7 WCHAR (총 8 WCHAR)."""
    return _units(code, *([0] * 7))


def _record(tag: int, level: int, data: bytes) -> bytes:
    size = len(data)
    if size >= 0xFFF:
        header = tag | (level << 10) | (0xFFF << 20)
        return struct.pack("<II", header, size) + data
    return struct.pack("<I", tag | (level << 10) | (size << 20)) + data


def _cell_header(row: int, col: int = 0) -> bytes:
    # 문단 리스트 헤더 8바이트 + 셀 속성(열 주소, 행 주소 ...)
    return struct.pack("<HHI", 1, 0, 0) + struct.pack("<HH", col, row) + b"\x00" * 20


class TestIterRecords:
    def test_reads_tag_level_and_data(self):
        stream = _record(TAG_PARA_TEXT, 1, b"ab") + _record(TAG_CTRL_HEADER, 2, b"")
        records = list(iter_records(stream))
        assert [(r.tag_id, r.level, r.data) for r in records] == [
            (TAG_PARA_TEXT, 1, b"ab"),
            (TAG_CTRL_HEADER, 2, b""),
        ]

    def test_extended_size(self):
        # U-03: Size == 0xFFF면 다음 DWORD가 실제 크기
        payload = b"x" * 5000
        (record,) = list(iter_records(_record(TAG_PARA_TEXT, 0, payload)))
        assert record.data == payload

    def test_truncated_record_raises(self):
        stream = _record(TAG_PARA_TEXT, 0, b"abcd")[:-2]
        with pytest.raises(HwpParseError):
            list(iter_records(stream))


class TestDecodeParaText:
    # U-02: §3.2 컨트롤 문자 표
    def test_plain_korean(self):
        assert decode_para_text(_text("여신 한도")) == "여신 한도"

    def test_paragraph_end_is_dropped(self):
        assert decode_para_text(_text("가나") + _units(13)) == "가나"

    def test_line_break_and_char_controls(self):
        data = _text("a") + _units(10) + _text("b") + _units(24, 30, 31) + _text("c")
        assert decode_para_text(data) == "a\nb-  c"

    def test_tab_is_inline_control_of_8_units(self):
        data = _text("a") + _ctrl(9) + _text("b")
        assert decode_para_text(data) == "a\tb"

    def test_extended_control_skips_8_units(self):
        # 표 위치 표시(11)가 8 WCHAR를 차지하므로 뒤 글자가 밀리지 않아야 한다
        data = _text("표:") + _ctrl(11) + _text("끝") + _units(13)
        assert decode_para_text(data) == "표:끝"

    def test_other_inline_controls_dropped(self):
        data = _ctrl(4) + _text("x") + _ctrl(20) + _ctrl(23) + _text("y")
        assert decode_para_text(data) == "xy"

    def test_surrogate_pair_preserved(self):
        assert decode_para_text(_text("𝄞a")) == "𝄞a"

    def test_no_control_residue(self):
        data = _units(0, 1, 2, 3, 0, 0, 0, 0, 0) + _text("z")
        out = decode_para_text(data)
        assert all(ch in "\t\n" or ord(ch) >= 32 for ch in out)


class TestParseFileHeader:
    @staticmethod
    def _header(flags: int) -> bytes:
        sig = b"HWP Document File".ljust(32, b"\x00")
        return sig + struct.pack("<II", 0x05000300, flags) + b"\x00" * 216

    def test_compressed_flag(self):
        assert parse_file_header(self._header(0x1)) is True
        assert parse_file_header(self._header(0x0)) is False

    @pytest.mark.parametrize("flags", [0x2, 0x4, 0x7])
    def test_password_or_distribution_rejected(self, flags):
        # U-06
        with pytest.raises(HwpEncryptedError):
            parse_file_header(self._header(flags))

    def test_bad_signature(self):
        with pytest.raises(HwpParseError):
            parse_file_header(b"NOT HWP".ljust(256, b"\x00"))

    def test_too_short(self):
        with pytest.raises(HwpParseError):
            parse_file_header(b"HWP Document File")


class TestInflate:
    @staticmethod
    def _deflate(raw: bytes) -> bytes:
        c = zlib.compressobj(wbits=-15)
        return c.compress(raw) + c.flush()

    def test_round_trip(self):
        assert inflate(self._deflate(b"hello" * 10), limit=1000) == b"hello" * 10

    def test_over_limit_raises(self):
        # U-07: 압축 폭탄 방지
        with pytest.raises(HwpParseError):
            inflate(self._deflate(b"\x00" * 10_000), limit=1000)

    def test_exact_limit_ok(self):
        assert len(inflate(self._deflate(b"a" * 1000), limit=1000)) == 1000

    def test_corrupt_raises_parse_error(self):
        with pytest.raises(HwpParseError):
            inflate(b"\xff\xff\xff\xff", limit=1000)


def _records(*raw: bytes):
    return iter_records(b"".join(raw))


class TestSectionText:
    def test_paragraphs_joined_by_newline(self):
        out = section_text(
            _records(
                _record(TAG_PARA_TEXT, 1, _text("첫 문단") + _units(13)),
                _record(TAG_PARA_TEXT, 1, _text("둘째 문단") + _units(13)),
            )
        )
        assert out == "첫 문단\n둘째 문단"

    def test_empty_paragraphs_dropped(self):
        out = section_text(
            _records(
                _record(TAG_PARA_TEXT, 1, _units(13)),
                _record(TAG_PARA_TEXT, 1, _text("본문") + _units(13)),
            )
        )
        assert out == "본문"

    def test_table_rows_and_cells(self):
        # §3.3: 같은 행은 " | ", 행이 바뀌면 줄바꿈, 표 앞뒤 빈 줄
        out = section_text(
            _records(
                _record(TAG_PARA_TEXT, 1, _text("앞") + _ctrl(11) + _units(13)),
                _record(TAG_CTRL_HEADER, 1, _TABLE_ID + b"\x00" * 8),
                _record(77, 2, b"\x00" * 24),  # HWPTAG_TABLE
                _record(TAG_LIST_HEADER, 2, _cell_header(row=0, col=0)),
                _record(TAG_PARA_TEXT, 3, _text("항목") + _units(13)),
                _record(TAG_LIST_HEADER, 2, _cell_header(row=0, col=1)),
                _record(TAG_PARA_TEXT, 3, _text("한도") + _units(13)),
                _record(TAG_LIST_HEADER, 2, _cell_header(row=1, col=0)),
                _record(TAG_PARA_TEXT, 3, _text("신용") + _units(13)),
                _record(TAG_LIST_HEADER, 2, _cell_header(row=1, col=1)),
                _record(TAG_PARA_TEXT, 3, _text("1억") + _units(13)),
                _record(TAG_PARA_TEXT, 1, _text("뒤") + _units(13)),
            )
        )
        assert out == "앞\n\n항목 | 한도\n신용 | 1억\n\n뒤"

    def test_cell_with_multiple_paragraphs_joined_by_space(self):
        out = section_text(
            _records(
                _record(TAG_CTRL_HEADER, 1, _TABLE_ID),
                _record(77, 2, b"\x00" * 24),  # HWPTAG_TABLE
                _record(TAG_LIST_HEADER, 2, _cell_header(row=0)),
                _record(TAG_PARA_TEXT, 3, _text("가") + _units(13)),
                _record(TAG_PARA_TEXT, 3, _text("나") + _units(13)),
            )
        )
        assert out == "가 나"

    def test_short_list_header_falls_back_to_single_line(self):
        # 행 주소를 못 읽어도 글자는 남는다
        out = section_text(
            _records(
                _record(TAG_CTRL_HEADER, 1, _TABLE_ID),
                _record(77, 2, b"\x00" * 24),  # HWPTAG_TABLE
                _record(TAG_LIST_HEADER, 2, b"\x01\x00"),
                _record(TAG_PARA_TEXT, 3, _text("a")),
                _record(TAG_LIST_HEADER, 2, b"\x01\x00"),
                _record(TAG_PARA_TEXT, 3, _text("b")),
            )
        )
        assert out == "a | b"

    def test_nested_table_flattened_into_outer_cell(self):
        out = section_text(
            _records(
                _record(TAG_CTRL_HEADER, 1, _TABLE_ID),
                _record(77, 2, b"\x00" * 24),  # HWPTAG_TABLE
                _record(TAG_LIST_HEADER, 2, _cell_header(row=0)),
                _record(TAG_PARA_TEXT, 3, _text("밖") + _units(13)),
                _record(TAG_CTRL_HEADER, 3, _TABLE_ID),
                _record(TAG_LIST_HEADER, 4, _cell_header(row=0)),
                _record(TAG_PARA_TEXT, 5, _text("안") + _units(13)),
            )
        )
        assert out == "밖 안"

    def test_header_footer_text_excluded(self):
        # Plan §2.2: 머리말·꼬리말은 본문 흐름 밖이라 제외
        out = section_text(
            _records(
                _record(TAG_CTRL_HEADER, 1, _HEADER_ID),
                _record(TAG_LIST_HEADER, 2, b"\x01\x00" * 4),
                _record(TAG_PARA_TEXT, 3, _text("머리말") + _units(13)),
                _record(TAG_PARA_TEXT, 1, _text("본문") + _units(13)),
            )
        )
        assert out == "본문"


class TestHwp5ReaderEntry:
    def test_non_ole_bytes_rejected(self):
        # U-05
        with pytest.raises(HwpParseError):
            reader = Hwp5Reader(max_decompressed_bytes=1000)
            reader.read_sections(b"not an ole file" * 200)


class _FakeStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeOle:
    """olefile.OleFileIO 대역 — 경로 → 바이트 사전."""

    def __init__(self, streams: dict[str, bytes]) -> None:
        self._streams = streams

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def exists(self, path: str) -> bool:
        return path in self._streams

    def openstream(self, path: str) -> _FakeStream:
        return _FakeStream(self._streams[path])

    def listdir(self) -> list[list[str]]:
        return [path.split("/") for path in self._streams]


def _file_header(flags: int) -> bytes:
    sig = b"HWP Document File".ljust(32, b"\x00")
    return sig + struct.pack("<II", 0x05000300, flags) + b"\x00" * 216


def _deflate(raw: bytes) -> bytes:
    c = zlib.compressobj(wbits=-15)
    return c.compress(raw) + c.flush()


def _section_stream(text: str) -> bytes:
    return _record(TAG_PARA_TEXT, 0, _text(text) + _units(13))


@pytest.fixture
def fake_ole(monkeypatch):
    """분석 I-2: read_sections의 OLE 경로를 대역으로 검증한다."""
    target = "src.infrastructure.parser.hwp.hwp5_reader.olefile"

    def install(streams: dict[str, bytes]) -> None:
        fake = type(
            "FakeOlefile",
            (),
            {
                "isOleFile": staticmethod(lambda data=None: True),
                "OleFileIO": staticmethod(lambda _buf: _FakeOle(streams)),
            },
        )
        monkeypatch.setattr(target, fake)

    return install


class TestReadSectionsOlePath:
    def test_uncompressed_sections_sorted_numerically(self, fake_ole):
        fake_ole(
            {
                "FileHeader": _file_header(0x0),
                "BodyText/Section10": _section_stream("열"),
                "BodyText/Section2": _section_stream("둘"),
                "BodyText/Section0": _section_stream("영"),
                "DocInfo": b"",
            }
        )
        reader = Hwp5Reader(max_decompressed_bytes=1000)
        assert reader.read_sections(b"ole") == ["영", "둘", "열"]

    def test_compressed_sections_inflated(self, fake_ole):
        fake_ole(
            {
                "FileHeader": _file_header(0x1),
                "BodyText/Section0": _deflate(_section_stream("압축 본문")),
            }
        )
        reader = Hwp5Reader(max_decompressed_bytes=1000)
        assert reader.read_sections(b"ole") == ["압축 본문"]

    def test_size_budget_shared_across_sections(self, fake_ole):
        # 섹션 하나하나는 상한 이하여도 합계가 넘으면 거부 (압축 폭탄 분할 방지)
        body = _section_stream("가" * 200)  # 약 410바이트
        fake_ole(
            {
                "FileHeader": _file_header(0x1),
                "BodyText/Section0": _deflate(body),
                "BodyText/Section1": _deflate(body),
            }
        )
        reader = Hwp5Reader(max_decompressed_bytes=600)
        with pytest.raises(HwpParseError):
            reader.read_sections(b"ole")

    def test_encrypted_header_rejected(self, fake_ole):
        fake_ole(
            {
                "FileHeader": _file_header(0x2),
                "BodyText/Section0": b"",
            }
        )
        with pytest.raises(HwpEncryptedError):
            Hwp5Reader(max_decompressed_bytes=1000).read_sections(b"ole")

    def test_missing_body_text_rejected(self, fake_ole):
        fake_ole({"FileHeader": _file_header(0x0)})
        with pytest.raises(HwpParseError):
            Hwp5Reader(max_decompressed_bytes=1000).read_sections(b"ole")

    def test_missing_file_header_rejected(self, fake_ole):
        fake_ole({"BodyText/Section0": _section_stream("x")})
        with pytest.raises(HwpParseError):
            Hwp5Reader(max_decompressed_bytes=1000).read_sections(b"ole")


class TestSkippedControlsInsideTable:
    def test_footnote_in_cell_excluded(self):
        # 분석 검증 필요 항목: 표 셀 안 각주도 본문 흐름 밖이므로 제외
        footnote_id = b"  nf"
        out = section_text(
            _records(
                _record(TAG_CTRL_HEADER, 1, _TABLE_ID),
                _record(77, 2, b"\x00" * 24),  # HWPTAG_TABLE
                _record(TAG_LIST_HEADER, 2, _cell_header(row=0)),
                _record(TAG_PARA_TEXT, 3, _text("셀") + _ctrl(17) + _units(13)),
                _record(TAG_CTRL_HEADER, 3, footnote_id),
                _record(TAG_LIST_HEADER, 4, b"\x01\x00" * 4),
                _record(TAG_PARA_TEXT, 5, _text("각주 내용") + _units(13)),
                _record(TAG_LIST_HEADER, 2, _cell_header(row=0, col=1)),
                _record(TAG_PARA_TEXT, 3, _text("다음") + _units(13)),
            )
        )
        assert out == "셀 | 다음"


TAG_TABLE = 77  # HWPTAG_TABLE — 캡션 리스트 뒤, 셀 리스트 앞에 온다
# 실파일 캡션 LIST_HEADER 22바이트 그대로 — 오프셋 10(셀이라면 행 주소 자리)이 0
_CAPTION_HEADER = struct.pack("<11H", 1, 0, 0, 0, 2, 0, 8504, 0, 850, 20976, 0)


class TestTableCaption:
    # 실파일(pyhwp table-caption.hwp) 레코드 순서: CTRL(tbl) → 캡션 LIST_HEADER·문단
    # → TABLE → 셀 LIST_HEADER들. 캡션을 첫 셀로 오인하지 않아야 한다.
    def test_caption_rendered_as_line_above_rows(self):
        out = section_text(
            _records(
                _record(TAG_CTRL_HEADER, 1, _TABLE_ID),
                _record(TAG_LIST_HEADER, 2, _CAPTION_HEADER),
                _record(TAG_PARA_TEXT, 3, _text("표 1 한도") + _units(13)),
                _record(TAG_TABLE, 2, b"\x00" * 24),
                _record(TAG_LIST_HEADER, 2, _cell_header(row=0, col=0)),
                _record(TAG_PARA_TEXT, 3, _text("구분") + _units(13)),
                _record(TAG_LIST_HEADER, 2, _cell_header(row=0, col=1)),
                _record(TAG_PARA_TEXT, 3, _text("한도") + _units(13)),
                _record(TAG_LIST_HEADER, 2, _cell_header(row=1, col=0)),
                _record(TAG_PARA_TEXT, 3, _text("신용") + _units(13)),
            )
        )
        assert out == "표 1 한도\n구분 | 한도\n신용"
