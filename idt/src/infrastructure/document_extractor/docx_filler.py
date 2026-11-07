"""DocxFiller: 보관된 원본 DOCX 에 칸 값을 직접 넣는다 (서식 보존).

Design Ref: docx-format-preserving-fill §2.1·§3.2·§3.3 — HTML 왕복 없이
`word/document.xml` 만 고치고 나머지 파트(스타일·번호·테마·이미지)는 바이트 그대로 둔다.

- 칸은 템플릿 순서대로, 매 칸 문서를 다시 색인해 예시값의 첫 출현을 바꾼다 (D1).
- 값은 예시값 첫 run 의 서식을 따른다 (D3). 공란은 `[미기재]` + 노란 형광펜.
- 실패 흡수 지점은 `fill` 하나다 (D4): 못 찾은 칸·원본 없음·파싱 실패는 예외 없이
  `file_bytes=None` + 사유로 돌려주고, 호출자(composer)가 HTML 경로로 폴백한다.
"""

import copy
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from src.domain.document_extractor.policies import (
    SampleSpanPolicy,
    SlotValuePolicy,
    UnfilledSlotPolicy,
)
from src.domain.document_extractor.schemas import TemplateSlot
from src.domain.logging.interfaces.logger_interface import LoggerInterface

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_DOCUMENT_PART = "word/document.xml"
UNFILLED_HIGHLIGHT = "yellow"

# CT_RPr 스키마 순서상 highlight 뒤에 와야 하는 요소들.
# 그 앞에 끼워야 Word 가 파일을 손상으로 보지 않는다.
_AFTER_HIGHLIGHT = {
    "u",
    "effect",
    "bdr",
    "shd",
    "fitText",
    "vertAlign",
    "rtl",
    "cs",
    "em",
    "lang",
    "eastAsianLayout",
    "specVanish",
    "oMath",
}


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


@dataclass(frozen=True)
class DocxFillResult:
    file_bytes: bytes | None
    missing_keys: list[str] = field(default_factory=list)
    reason: str | None = None  # None | sample_not_found | source_missing | parse_error


class DocxFiller:
    def __init__(self, logger: LoggerInterface) -> None:
        self._logger = logger

    def fill(
        self,
        source_path: str,
        slots: list[TemplateSlot],
        values: dict,
        request_id: str,
    ) -> DocxFillResult:
        path = Path(source_path or "")
        if not source_path or not path.is_file():
            self._logger.warning(
                "DocxFiller source missing", request_id=request_id, path=source_path
            )
            return DocxFillResult(None, reason="source_missing")
        try:
            data = path.read_bytes()
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                root = etree.fromstring(zf.read(_DOCUMENT_PART))
        except (OSError, zipfile.BadZipFile, KeyError, etree.XMLSyntaxError) as e:
            self._logger.warning(
                "DocxFiller parse failed", request_id=request_id, exception=e
            )
            return DocxFillResult(None, reason="parse_error")

        # 1단계: 칸 순서대로 위치만 잡는다 (자리표시). 값을 바로 넣으면 다음 칸이
        # 방금 넣은 값 안을 찾을 수 있다 (예: 문서번호 값 안의 연도). 프론트가
        # {{key}} 로 토큰화하는 것과 같은 의미다.
        missing = [
            s.key
            for i, s in enumerate(slots)
            if not _place_slot(root, s, _placeholder(i))
        ]
        if missing:
            return DocxFillResult(None, missing_keys=missing, reason="sample_not_found")
        # 2단계: 자리표시를 실제 값으로
        for i, slot in enumerate(slots):
            _materialize(root, _placeholder(i), values.get(slot.key))
        return DocxFillResult(_rezip(data, root))


# ── 색인 (Design §3.3) ─────────────────────────────────────────────────────


def _paragraph_segments(root: etree._Element) -> list[list[etree._Element]]:
    """본문·표 단락별 w:t 목록 (문서 순서). 텍스트 상자 안 단락은 제외한다."""
    result: list[list[etree._Element]] = []
    for p in root.iter(_w("p")):
        if any(a.tag == _w("txbxContent") for a in p.iterancestors()):
            continue
        result.append([t for t in p.iter(_w("t")) if _owned_by(t, p)])
    return result


def _owned_by(t: etree._Element, p: etree._Element) -> bool:
    """w:t 가 이 단락의 직속 run(또는 하이퍼링크 안 run)에 속하는지."""
    run = t.getparent()
    if run is None or run.tag != _w("r"):
        return False
    holder = run.getparent()
    if holder is p:
        return True
    return (
        holder is not None and holder.tag == _w("hyperlink") and holder.getparent() is p
    )


def _placeholder(index: int) -> str:
    """사용자 정의 영역 문자로 감싼 자리표시 — 어떤 예시값과도 매칭되지 않는다."""
    return f"{index}"


def _place_slot(root: etree._Element, slot: TemplateSlot, placeholder: str) -> bool:
    for segments in _paragraph_segments(root):
        texts = [t.text or "" for t in segments]
        span = SampleSpanPolicy.find_span("".join(texts), slot.sample_value)
        if span is None:
            continue
        parts = SampleSpanPolicy.split_span([len(s) for s in texts], span)
        _apply(segments, parts, placeholder)
        return True
    return False


def _materialize(root: etree._Element, placeholder: str, raw) -> None:
    """자리표시 하나만 담은 run 을 값 run 으로 바꾼다.

    첫 run 서식은 1단계에서 이미 복사돼 있다.
    """
    for t in root.iter(_w("t")):
        if t.text == placeholder:
            run = t.getparent()
            run.remove(t)
            _fill_value(run, raw)
            return


# ── 적용 (Design §3.2) ─────────────────────────────────────────────────────


def _apply(segments: list, parts: list[tuple[int, int, int]], placeholder: str) -> None:
    first_idx, first_start, first_end = parts[0]
    for idx, start, end in parts[1:]:
        t = segments[idx]
        _set_text(t, (t.text or "")[:start] + (t.text or "")[end:])

    t0 = segments[first_idx]
    run = t0.getparent()
    text = t0.text or ""
    trailing = list(t0.itersiblings())  # t0 뒤의 탭·줄바꿈 등은 after run 으로 옮긴다
    _set_text(t0, text[:first_start])
    rpr = run.find(_w("rPr"))

    slot_run = _new_run(rpr)
    _append_text(slot_run, placeholder)
    new_runs = [slot_run]
    after = text[first_end:]
    if after or trailing:
        new_runs.append(_after_run(rpr, after, trailing))
    anchor = run
    for new in new_runs:
        anchor.addnext(new)
        anchor = new


def _fill_value(run: etree._Element, raw) -> None:
    if UnfilledSlotPolicy.is_unfilled(raw):
        rpr = run.find(_w("rPr"))
        _add_highlight(rpr if rpr is not None else _ensure_rpr(run))
        _append_text(run, UnfilledSlotPolicy.UNFILLED_MARKER)
        return
    lines = SlotValuePolicy.sanitize(str(raw)).split("\n")
    for i, line in enumerate(lines):
        if i:
            etree.SubElement(run, _w("br"))
        _append_text(run, line)


def _after_run(rpr, text: str, trailing: list) -> etree._Element:
    run = _new_run(rpr)
    if text:
        _append_text(run, text)
    for node in trailing:
        run.append(node)  # 원래 run 에서 이동
    return run


def _new_run(rpr) -> etree._Element:
    run = etree.Element(_w("r"))
    if rpr is not None:
        run.append(copy.deepcopy(rpr))
    return run


def _ensure_rpr(run: etree._Element) -> etree._Element:
    rpr = etree.Element(_w("rPr"))
    run.insert(0, rpr)
    return rpr


def _add_highlight(rpr: etree._Element) -> None:
    for old in rpr.findall(_w("highlight")):
        rpr.remove(old)
    highlight = etree.Element(_w("highlight"))
    highlight.set(_w("val"), UNFILLED_HIGHLIGHT)
    for i, child in enumerate(rpr):
        if etree.QName(child).localname in _AFTER_HIGHLIGHT:
            rpr.insert(i, highlight)
            return
    rpr.append(highlight)


def _append_text(run: etree._Element, text: str) -> None:
    _set_text(etree.SubElement(run, _w("t")), text)


def _set_text(t: etree._Element, text: str) -> None:
    t.text = text
    t.set(_XML_SPACE, "preserve")


# ── 저장 (D5) ──────────────────────────────────────────────────────────────


def _rezip(original: bytes, root: etree._Element) -> bytes:
    """document.xml 만 교체하고 나머지 파트는 원래 순서·압축 방식·바이트 그대로."""
    xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            payload = (
                xml if info.filename == _DOCUMENT_PART else src.read(info.filename)
            )
            dst.writestr(info, payload, compress_type=info.compress_type)
    return out.getvalue()
