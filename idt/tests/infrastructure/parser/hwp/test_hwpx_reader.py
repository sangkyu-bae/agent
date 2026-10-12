"""HwpxReader — HWPX(ZIP+XML) 해석 단위 테스트.

hwp-parser Design §3.4, §8 U-08·U-09. HWPX는 메모리에서 실제 ZIP을 만들어 검증한다.
"""
import io
import zipfile

import pytest
from src.domain.parser.exceptions import HwpEncryptedError, HwpParseError
from src.infrastructure.parser.hwp.hwpx_reader import HwpxReader

_NS = (
    'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
)
_LIMIT = 1024 * 1024


def _p(inner: str) -> str:
    return f"<hp:p><hp:run>{inner}</hp:run></hp:p>"


def _t(text: str) -> str:
    return f"<hp:t>{text}</hp:t>"


def _cell(*paras: str) -> str:
    body = "".join(_p(_t(x)) for x in paras)
    return f"<hp:tc><hp:subList>{body}</hp:subList></hp:tc>"


def _table(rows: list[list[str]]) -> str:
    trs = "".join(
        "<hp:tr>" + "".join(_cell(c) for c in row) + "</hp:tr>" for row in rows
    )
    return f"<hp:tbl>{trs}</hp:tbl>"


def _section(body: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><hs:sec {_NS}>{body}</hs:sec>'


def _hwpx(sections: dict[str, str], manifest: str = "<manifest/>") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("META-INF/manifest.xml", manifest)
        for name, xml in sections.items():
            zf.writestr(f"Contents/{name}", xml)
    return buf.getvalue()


@pytest.fixture
def reader() -> HwpxReader:
    return HwpxReader(max_decompressed_bytes=_LIMIT)


class TestParagraphs:
    def test_paragraph_text(self, reader):
        data = _hwpx({"section0.xml": _section(_p(_t("여신")) + _p(_t("심사")))})
        assert reader.read_sections(data) == ["여신\n심사"]

    def test_tab_and_line_break(self, reader):
        inner = "<hp:t>제1조<hp:tab/>목적</hp:t><hp:t>첫째<hp:lineBreak/>둘째</hp:t>"
        data = _hwpx({"section0.xml": _section(_p(inner))})
        assert reader.read_sections(data) == ["제1조\t목적첫째\n둘째"]

    def test_sections_sorted_numerically(self, reader):
        sections = {
            f"section{i}.xml": _section(_p(_t(f"s{i}"))) for i in (10, 2, 0, 1)
        }
        assert reader.read_sections(_hwpx(sections)) == ["s0", "s1", "s2", "s10"]

    def test_header_footer_excluded(self, reader):
        inner = (
            "<hp:ctrl><hp:header><hp:subList>"
            + _p(_t("머리말"))
            + "</hp:subList></hp:header></hp:ctrl>"
            + _t("본문")
        )
        data = _hwpx({"section0.xml": _section(_p(inner))})
        assert reader.read_sections(data) == ["본문"]


class TestTables:
    # U-08: §3.3과 같은 표기
    def test_table_rows_and_cells(self, reader):
        body = (
            _p(_t("앞") + _table([["구분", "한도"], ["신용", "1억"]]))
            + _p(_t("뒤"))
        )
        data = _hwpx({"section0.xml": _section(body)})
        assert reader.read_sections(data) == ["앞\n\n구분 | 한도\n신용 | 1억\n\n뒤"]

    def test_cell_paragraphs_joined_by_space(self, reader):
        tbl = "<hp:tbl><hp:tr>" + _cell("가", "나") + "</hp:tr></hp:tbl>"
        data = _hwpx({"section0.xml": _section(_p(tbl))})
        assert reader.read_sections(data) == ["가 나"]

    def test_nested_table_flattened(self, reader):
        nested = _table([["안"]])
        outer = (
            "<hp:tbl><hp:tr><hp:tc><hp:subList>"
            + _p(_t("밖"))
            + _p(nested)
            + "</hp:subList></hp:tc></hp:tr></hp:tbl>"
        )
        data = _hwpx({"section0.xml": _section(_p(outer))})
        assert reader.read_sections(data) == ["밖 안"]


class TestRejections:
    # U-09
    def test_not_a_zip(self, reader):
        with pytest.raises(HwpParseError):
            reader.read_sections(b"plain text, not a zip")

    def test_zip_without_sections(self, reader):
        with pytest.raises(HwpParseError):
            reader.read_sections(_hwpx({}))

    def test_doctype_rejected(self, reader):
        xml = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaa">]>' + _section("")
        with pytest.raises(HwpParseError):
            reader.read_sections(_hwpx({"section0.xml": xml}))

    def test_encrypted_manifest(self, reader):
        manifest = "<manifest><encryption-data/></manifest>"
        data = _hwpx({"section0.xml": _section(_p(_t("x")))}, manifest=manifest)
        with pytest.raises(HwpEncryptedError):
            reader.read_sections(data)

    def test_broken_xml(self, reader):
        with pytest.raises(HwpParseError):
            reader.read_sections(_hwpx({"section0.xml": "<hs:sec><unclosed>"}))

    def test_over_size_limit(self):
        big = _section(_p(_t("가" * 5000)))
        small_reader = HwpxReader(max_decompressed_bytes=1000)
        with pytest.raises(HwpParseError):
            small_reader.read_sections(_hwpx({"section0.xml": big}))


class TestTraversalAlignedWithHwp5:
    """분석 I-4: HWPX도 재귀 수집 + 이름 기반 제외로 HWP 5.0과 같은 기준을 쓴다."""

    def test_textbox_text_included_after_anchor(self, reader):
        textbox = (
            "<hp:rect><hp:drawText><hp:subList>"
            + _p(_t("글상자 안 본문"))
            + "</hp:subList></hp:drawText></hp:rect>"
        )
        body = _p(_t("앞") + textbox) + _p(_t("뒤"))
        data = _hwpx({"section0.xml": _section(body)})
        assert reader.read_sections(data) == ["앞\n글상자 안 본문\n뒤"]

    def test_footnote_excluded(self, reader):
        footnote = (
            "<hp:ctrl><hp:footNote><hp:subList>"
            + _p(_t("각주"))
            + "</hp:subList></hp:footNote></hp:ctrl>"
        )
        data = _hwpx({"section0.xml": _section(_p(_t("본문") + footnote))})
        assert reader.read_sections(data) == ["본문"]

    def test_footnote_in_cell_excluded(self, reader):
        footnote = (
            "<hp:ctrl><hp:footNote><hp:subList>"
            + _p(_t("각주"))
            + "</hp:subList></hp:footNote></hp:ctrl>"
        )
        cell = f"<hp:tc><hp:subList>{_p(_t('셀') + footnote)}</hp:subList></hp:tc>"
        tbl = f"<hp:tbl><hp:tr>{cell}{_cell('다음')}</hp:tr></hp:tbl>"
        data = _hwpx({"section0.xml": _section(_p(tbl))})
        assert reader.read_sections(data) == ["셀 | 다음"]

    def test_nested_multi_cell_table_separated_by_space(self, reader):
        nested = _table([["a", "b"]])
        outer = (
            "<hp:tbl><hp:tr><hp:tc><hp:subList>"
            + _p(nested)
            + "</hp:subList></hp:tc></hp:tr></hp:tbl>"
        )
        data = _hwpx({"section0.xml": _section(_p(outer))})
        assert reader.read_sections(data) == ["a b"]

    def test_special_space_elements(self, reader):
        inner = "<hp:t>가<hp:nbSpace/>나<hp:fwSpace/>다<hp:hyphen/>라</hp:t>"
        data = _hwpx({"section0.xml": _section(_p(inner))})
        assert reader.read_sections(data) == ["가 나 다-라"]
