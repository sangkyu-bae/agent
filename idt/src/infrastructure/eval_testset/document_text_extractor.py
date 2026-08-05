"""문서 텍스트 추출기 — PDF(pymupdf)/DOCX(zip+XML) (eval-hub Design A6).

python-docx 미설치 환경이므로 DOCX는 표준 라이브러리(zipfile + ElementTree)로
word/document.xml의 텍스트 런을 추출한다.
"""
import io
import zipfile
import xml.etree.ElementTree as ET

_DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_document_text(file_bytes: bytes, filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".pdf"):
        return _extract_pdf(file_bytes)
    if lowered.endswith(".docx"):
        return _extract_docx(file_bytes)
    raise ValueError("지원하지 않는 문서 형식입니다 (.pdf, .docx만 가능)")


def _extract_pdf(file_bytes: bytes) -> str:
    import fitz

    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception as e:
        raise ValueError(f"PDF 파싱에 실패했습니다: {e}") from e


def _extract_docx(file_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            xml_bytes = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ValueError(f"DOCX 파싱에 실패했습니다: {e}") from e

    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for para in root.iter(f"{_DOCX_NS}p"):
        runs = [node.text or "" for node in para.iter(f"{_DOCX_NS}t")]
        text = "".join(runs).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)
