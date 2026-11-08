"""DocxFiller — 원본 DOCX 직접 채움.

docx-format-preserving-fill Design §3.2·§3.3, I-01~12.

픽스처는 테스트 안에서 최소 DOCX(zip)로 만든다 — 바이너리 커밋 없음.
"""

import io
import zipfile
from unittest.mock import MagicMock

from lxml import etree
from src.domain.document_extractor.schemas import TemplateSlot
from src.infrastructure.document_extractor.docx_filler import (
    UNFILLED_HIGHLIGHT,
    DocxFiller,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
STYLES = (
    b'<?xml version="1.0"?><w:styles xmlns:w="'
    + W.encode()
    + b'"><!-- keep --></w:styles>'
)


def _run(text: str, rpr: str = "") -> str:
    return f'<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r>'


def _p(*runs: str) -> str:
    return f"<w:p>{''.join(runs)}</w:p>"


def _docx(tmp_path, body: str, name: str = "src.docx") -> str:
    xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>{body}<w:sectPr/></w:body></w:document>'
    )
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("_rels/.rels", "<Relationships/>")
        z.writestr("word/document.xml", xml)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/media/image1.png", b"\x89PNG-binary")
    return str(path)


def _slot(key: str, sample: str, label: str = "") -> TemplateSlot:
    return TemplateSlot(
        key=key, label=label or key, slot_type="value", sample_value=sample
    )


def _doc(result) -> etree._Element:
    with zipfile.ZipFile(io.BytesIO(result.file_bytes)) as z:
        return etree.fromstring(z.read("word/document.xml"))


def _text(root) -> str:
    return "|".join("".join(p.itertext()) for p in root.iter(f"{{{W}}}p"))


def _filler() -> tuple[DocxFiller, MagicMock]:
    logger = MagicMock()
    return DocxFiller(logger), logger


BOLD32 = '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr>'


class TestFillHappyPath:
    def test_single_run_keeps_rpr(self, tmp_path):  # I-01
        src = _docx(tmp_path, _p(_run("주식회사 한빛상사", BOLD32)))
        res = _filler()[0].fill(
            src, [_slot("co", "주식회사 한빛상사")], {"co": "대한상사"}, "r"
        )
        assert (
            res.file_bytes is not None and res.missing_keys == [] and res.reason is None
        )
        root = _doc(res)
        assert _text(root) == "대한상사"
        run = root.find(".//w:r", NS)
        assert run.find("w:rPr/w:b", NS) is not None
        assert run.find("w:rPr/w:sz", NS).get(f"{{{W}}}val") == "32"

    def test_sample_across_runs_uses_first_run_rpr(self, tmp_path):  # I-02
        body = _p(
            _run("금", "<w:rPr><w:i/></w:rPr>"),
            _run(" 오억", "<w:rPr><w:b/></w:rPr>"),
            _run("원 끝", '<w:rPr><w:u w:val="single"/></w:rPr>'),
        )
        src = _docx(tmp_path, body)
        res = _filler()[0].fill(
            src, [_slot("amt", "금 오억원")], {"amt": "금 칠억원"}, "r"
        )
        root = _doc(res)
        assert _text(root) == "금 칠억원 끝"
        runs = [r for r in root.iter(f"{{{W}}}r") if "".join(r.itertext())]
        value_run = next(r for r in runs if "칠억" in "".join(r.itertext()))
        assert value_run.find("w:rPr/w:i", NS) is not None  # 첫 run 서식
        assert value_run.find("w:rPr/w:b", NS) is None

    def test_before_and_after_text_preserved(self, tmp_path):  # I-03
        src = _docx(tmp_path, _p(_run("연 5.8% 고정", BOLD32)))
        res = _filler()[0].fill(src, [_slot("rate", "5.8%")], {"rate": "6.1%"}, "r")
        root = _doc(res)
        assert _text(root) == "연 6.1% 고정"
        assert all(r.find("w:rPr/w:b", NS) is not None for r in root.iter(f"{{{W}}}r"))

    def test_sequential_overlap(self, tmp_path):  # I-04 / SC-3
        body = _p(_run("문서번호: 2026-여신-0042   심의일자: 2026년 11월 06일"))
        src = _docx(tmp_path, body)
        slots = [
            _slot("doc_no", "2026-여신-0042"),
            _slot("year", "2026"),
            _slot("month", "11"),
            _slot("day", "06"),
        ]
        vals = {"doc_no": "2026-여신-0099", "year": "2027", "month": "01", "day": "15"}
        res = _filler()[0].fill(src, slots, vals, "r")
        t = _text(_doc(res))
        assert "문서번호: 2026-여신-0099" in t
        assert "2027년 01월 15일" in t

    def test_table_cell(self, tmp_path):  # I-05
        body = (
            '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/></w:tblPr><w:tr>'
            f"<w:tc>{_p(_run('업체명'))}</w:tc><w:tc>{_p(_run('한빛상사'))}</w:tc>"
            "</w:tr></w:tbl>"
        )
        src = _docx(tmp_path, body)
        res = _filler()[0].fill(src, [_slot("co", "한빛상사")], {"co": "대한상사"}, "r")
        root = _doc(res)
        assert _text(root) == "업체명|대한상사"
        assert root.find(".//w:tblStyle", NS).get(f"{{{W}}}val") == "TableGrid"

    def test_unfilled_marker_highlight(self, tmp_path):  # I-06 / SC-2
        src = _docx(tmp_path, _p(_run("문서번호: 2026-0042", BOLD32)))
        res = _filler()[0].fill(src, [_slot("no", "2026-0042")], {"no": None}, "r")
        root = _doc(res)
        assert _text(root) == "문서번호: [미기재]"
        marker = next(
            r for r in root.iter(f"{{{W}}}r") if "[미기재]" in "".join(r.itertext())
        )
        hl = marker.find("w:rPr/w:highlight", NS)
        assert hl is not None and hl.get(f"{{{W}}}val") == UNFILLED_HIGHLIGHT
        assert marker.find("w:rPr/w:b", NS) is not None  # 원 서식 위에 형광펜

    def test_multiline_value_uses_br(self, tmp_path):  # I-07
        src = _docx(tmp_path, _p(_run("의견 자리")))
        res = _filler()[0].fill(
            src, [_slot("op", "의견 자리")], {"op": "첫 줄\n둘째 줄"}, "r"
        )
        root = _doc(res)
        assert len(root.findall(".//w:br", NS)) == 1
        assert _text(root) == "첫 줄둘째 줄"

    def test_xml_special_chars_escaped(self, tmp_path):
        src = _docx(tmp_path, _p(_run("값")))
        res = _filler()[0].fill(src, [_slot("v", "값")], {"v": "A&B <C>"}, "r")
        assert _text(_doc(res)) == "A&B <C>"

    def test_other_parts_byte_identical(self, tmp_path):  # I-11
        src = _docx(tmp_path, _p(_run("한빛상사")))
        res = _filler()[0].fill(src, [_slot("co", "한빛상사")], {"co": "x"}, "r")
        with (
            zipfile.ZipFile(src) as a,
            zipfile.ZipFile(io.BytesIO(res.file_bytes)) as b,
        ):
            assert a.namelist() == b.namelist()
            for name in a.namelist():
                if name != "word/document.xml":
                    assert a.read(name) == b.read(name)

    def test_result_is_valid_docx(self, tmp_path):  # I-12
        src = _docx(tmp_path, _p(_run("한빛상사")))
        res = _filler()[0].fill(src, [_slot("co", "한빛상사")], {"co": "x"}, "r")
        assert zipfile.is_zipfile(io.BytesIO(res.file_bytes))
        assert _doc(res).tag == f"{{{W}}}document"


class TestFallback:
    def test_textbox_is_not_indexed(self, tmp_path):  # I-08
        body = (
            "<w:p><w:r><w:pict><w:txbxContent>"
            f"{_p(_run('한빛상사'))}"
            "</w:txbxContent></w:pict></w:r></w:p>"
        )
        src = _docx(tmp_path, body)
        res = _filler()[0].fill(src, [_slot("co", "한빛상사")], {"co": "x"}, "r")
        assert res.file_bytes is None
        assert res.reason == "sample_not_found" and res.missing_keys == ["co"]

    def test_missing_key_reported(self, tmp_path):  # I-09
        src = _docx(tmp_path, _p(_run("한빛상사")))
        slots = [
            _slot("co", "한빛상사"),
            _slot("ghost", "없는값"),
            _slot("empty", "  "),
        ]
        res = _filler()[0].fill(
            src, slots, {"co": "x", "ghost": "y", "empty": "z"}, "r"
        )
        assert res.file_bytes is None
        assert res.missing_keys == ["ghost", "empty"]

    def test_source_missing(self, tmp_path):  # I-10
        filler, logger = _filler()
        res = filler.fill(
            str(tmp_path / "nope.docx"), [_slot("a", "a")], {"a": "b"}, "r"
        )
        assert res.file_bytes is None and res.reason == "source_missing"

    def test_not_a_zip(self, tmp_path):  # I-10
        bad = tmp_path / "bad.docx"
        bad.write_bytes(b"not a zip")
        filler, logger = _filler()
        res = filler.fill(str(bad), [_slot("a", "a")], {"a": "b"}, "r")
        assert res.file_bytes is None and res.reason == "parse_error"
        assert logger.warning.called
        assert "exception" in logger.warning.call_args.kwargs


# ── Act-1 (Analysis G1~G4) ────────────────────────────────────────────────


class TestAct1:
    def test_digit_sample_does_not_hit_earlier_placeholder(self, tmp_path):  # G1
        """자리표시에 숫자가 있으면 뒤 칸의 숫자 예시값('1')이 그 안을 찾았다."""
        texts = ["갑"] + [f"A{i}" for i in range(11)] + ["끝 1"]
        src = _docx(tmp_path, "".join(_p(_run(t)) for t in texts))
        slots = (
            [_slot("k0", "갑")]
            + [_slot(f"a{i}", f"A{i}") for i in range(11)]
            + [_slot("one", "1")]
        )
        values = {s.key: f"V_{s.key}" for s in slots}
        res = _filler()[0].fill(src, slots, values, "r")
        assert res.file_bytes is not None
        text = _text(_doc(res))
        for s in slots:
            assert f"V_{s.key}" in text
        assert "끝 V_one" in text
        assert not any(0xE000 <= ord(c) <= 0xF8FF for c in text)

    def test_value_control_chars_are_stripped(self, tmp_path):  # G2
        src = _docx(tmp_path, _p(_run("값")))
        res = _filler()[0].fill(src, [_slot("v", "값")], {"v": "A\x00B\x0bC\r\nD"}, "r")
        assert res.file_bytes is not None
        root = _doc(res)
        assert _text(root) == "ABCD"
        assert len(root.findall(".//w:br", NS)) == 1

    def test_unexpected_error_after_parse_falls_back(self, tmp_path, monkeypatch):  # G2
        from src.infrastructure.document_extractor import docx_filler as mod

        def boom(*a, **k):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(mod, "_rezip", boom)
        src = _docx(tmp_path, _p(_run("값")))
        filler, logger = _filler()
        res = filler.fill(src, [_slot("v", "값")], {"v": "x"}, "r")
        assert res.file_bytes is None and res.reason == "fill_error"
        assert "exception" in logger.warning.call_args.kwargs

    def test_highlight_before_underline_and_rprchange(self, tmp_path):  # G3
        rpr = (
            '<w:rPr><w:b/><w:u w:val="single"/>'
            '<w:rPrChange w:id="1" w:author="a"><w:rPr/></w:rPrChange></w:rPr>'
        )
        src = _docx(tmp_path, _p(_run("값", rpr)))
        res = _filler()[0].fill(src, [_slot("v", "값")], {"v": None}, "r")
        marker = next(
            r
            for r in _doc(res).iter(f"{{{W}}}r")
            if "[미기재]" in "".join(r.itertext())
        )
        names = [etree.QName(c).localname for c in marker.find("w:rPr", NS)]
        assert names.index("highlight") < names.index("u") < names.index("rPrChange")

    def test_highlight_before_foreign_namespace_element(self, tmp_path):  # G3
        w14 = "http://schemas.microsoft.com/office/word/2010/wordml"
        rpr = f'<w:rPr xmlns:w14="{w14}"><w:b/><w14:ligatures w14:val="all"/></w:rPr>'
        src = _docx(tmp_path, _p(_run("값", rpr)))
        res = _filler()[0].fill(src, [_slot("v", "값")], {"v": None}, "r")
        marker = next(
            r
            for r in _doc(res).iter(f"{{{W}}}r")
            if "[미기재]" in "".join(r.itertext())
        )
        names = [etree.QName(c).localname for c in marker.find("w:rPr", NS)]
        assert names.index("highlight") < names.index("ligatures")

    def test_external_entity_not_resolved(self, tmp_path):  # G4
        secret = tmp_path / "secret.txt"
        secret.write_text("TOPSECRET", encoding="utf-8")
        xml = (
            '<?xml version="1.0"?>'
            f'<!DOCTYPE d [<!ENTITY x SYSTEM "file:///{secret.as_posix()}">]>'
            f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>&x; 값</w:t></w:r></w:p>'
            "</w:body></w:document>"
        )
        path = tmp_path / "xxe.docx"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("word/document.xml", xml)
        res = _filler()[0].fill(str(path), [_slot("v", "값")], {"v": "x"}, "r")
        if res.file_bytes is not None:
            assert "TOPSECRET" not in _text(_doc(res))

    def test_zip_without_document_xml(self, tmp_path):  # I-10 보강
        path = tmp_path / "nodoc.docx"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("word/styles.xml", STYLES)
        res = _filler()[0].fill(str(path), [_slot("v", "값")], {"v": "x"}, "r")
        assert res.file_bytes is None and res.reason == "parse_error"


def test_lost_placeholder_is_not_returned_as_success(
    tmp_path, monkeypatch
):  # G1 안전망
    from src.infrastructure.document_extractor import docx_filler as mod

    monkeypatch.setattr(mod, "_materialize", lambda root, ph, raw: False)
    src = _docx(tmp_path, _p(_run("값")))
    res = _filler()[0].fill(src, [_slot("v", "값")], {"v": "x"}, "r")
    assert res.file_bytes is None
    assert res.reason == "placeholder_lost" and res.missing_keys == ["v"]
