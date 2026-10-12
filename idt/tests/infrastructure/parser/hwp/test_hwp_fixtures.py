"""한글 프로그램으로 만든 실제 파일 검증 (hwp-parser Design §8.2 F-01~F-05).

픽스처 출처·라이선스는 tests/fixtures/hwp/NOTICE.md 참고. 거짓 초록을 막기 위해
파일이 없으면 skip하지 않고 실패한다 (Design §8.5).
"""
from pathlib import Path

import pytest
from src.infrastructure.parser.hwp import HwpDocumentParser
from src.infrastructure.parser.hwp.hwp5_reader import Hwp5Reader
from src.infrastructure.parser.hwp.hwpx_reader import HwpxReader

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "hwp"
_LIMIT = 50 * 1024 * 1024


def _load(name: str) -> bytes:
    path = FIXTURES / name
    assert path.exists(), f"픽스처가 없습니다: {path} (NOTICE.md 참고)"
    return path.read_bytes()


def _assert_in_order(text: str, phrases: list[str]) -> None:
    pos = 0
    for phrase in phrases:
        found = text.find(phrase, pos)
        assert found >= 0, f"{phrase!r} 가 순서대로 나오지 않음:\n{text[:2000]}"
        pos = found + len(phrase)


def _assert_no_control_residue(text: str) -> None:
    bad = sorted({hex(ord(ch)) for ch in text if ord(ch) < 32 and ch not in "\t\n"})
    assert not bad, f"컨트롤 문자 잔여물: {bad}"


class TestBasicsReportHwp:
    """hwp.js basicsReport.hwp — 한글로 만든 압축 HWP 5.0, 표 포함."""

    @pytest.fixture(scope="class")
    def text(self) -> str:
        reader = Hwp5Reader(max_decompressed_bytes=_LIMIT)
        return "\n".join(reader.read_sections(_load("hwpjs_basics_report.hwp")))

    def test_body_paragraphs(self, text):
        # F-01
        _assert_in_order(text, ["리포트의 제목", "두 줄로 작성", "R E P O R T"])
        _assert_no_control_residue(text)

    def test_table_rows_and_cells(self, text):
        # F-02: 셀 " | ", 행 줄바꿈 — _CELL_ROW_OFFSET=10 실파일 검증
        _assert_in_order(
            text,
            ["리포트의 제목", "과목명 | ○○○○\n담당교수 | ○○○\n학과명 | ○○○○과"],
        )

    def test_tab_preserved(self, text):
        assert "과목명\t\tOOOO" in text


class TestNestedTableHwpx:
    """rhwp centered_cell_nested_table.hwpx — 한글로 만든 HWPX, 중첩 표."""

    def test_nested_table_flattened(self):
        # F-03
        sections = HwpxReader(max_decompressed_bytes=_LIMIT).read_sections(
            _load("rhwp_nested_table.hwpx")
        )
        assert sections == ["HOSTLINE\n\nCENTERME INNER1 INNER2"]


class TestFootnoteInTextboxHwp:
    """rhwp footnote-tbox-01.hwp — 글상자와 각주(본문·글상자 안)."""

    @pytest.fixture(scope="class")
    def text(self) -> str:
        reader = Hwp5Reader(max_decompressed_bytes=_LIMIT)
        return "\n".join(reader.read_sections(_load("rhwp_footnote_textbox.hwp")))

    def test_textbox_text_included(self, text):
        # F-05
        _assert_in_order(
            text,
            [
                "글상자 내부에 각주가 있는 경우",
                "와우",
                "여기에 각주가 들어있는",
                "경우",
                "사람들은",
            ],
        )

    def test_footnote_bodies_excluded(self, text):
        assert "글상자 내부 각주" not in text
        assert "일반 문단내 각주" not in text


class TestAdapterOnRealFile:
    def test_documents_and_metadata(self):
        docs = HwpDocumentParser(max_decompressed_mb=50).parse_bytes(
            _load("hwpjs_basics_report.hwp"), "보고서.hwp", "u1"
        )
        assert len(docs) >= 1
        assert {d.metadata["parser"] for d in docs} == {"hwp"}
        assert [d.metadata["page"] for d in docs] == list(range(1, len(docs) + 1))
