"""xhtml2pdf 기반 HTML → PDF 변환기 구현체.

외부 라이브러리: xhtml2pdf (순수 Python, 시스템 의존성 없음)
WeasyPrint 인터페이스와 호환되는 래퍼 이름을 유지합니다.

fix-doc-generator-korean-font FR-07: 기본 폰트(Helvetica)에는 한글 글리프가
없어 이 경로도 MCP 경로와 같은 증상을 갖는다. 렌더러가 reportlab 이라
data URI 대신 @font-face 로 로컬 폰트 파일을 등록한다.
"""
import io
from pathlib import Path
from typing import Optional

import xhtml2pdf.pisa as pisa

from src.domain.pdf_export.interfaces import HtmlToPdfConverterInterface

_WEIGHT_FILES = ((400, "Regular", "normal"), (700, "Bold", "bold"))
_SELECTORS = "html,body,table,th,td,li,p,h1,h2,h3,strong,em"


class WeasyprintConverter(HtmlToPdfConverterInterface):
    """xhtml2pdf를 사용하는 HTML → PDF 변환기.

    WeasyPrint 대체 구현체로, 동일한 인터페이스를 제공합니다.
    Windows 환경에서 GTK 의존성 없이 동작합니다.
    """

    def __init__(
        self, font_dir: Optional[Path] = None, family: str = "Pretendard"
    ) -> None:
        self._font_dir = Path(font_dir) if font_dir else _default_font_dir()
        self._family = family

    def convert(
        self,
        html_content: str,
        css_content: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> bytes:
        if not html_content.strip():
            raise ValueError("html_content must not be empty")

        # 한글 폰트를 먼저 깔고, 호출자 CSS 가 그 위를 덮도록 순서를 둔다.
        prefix = self._font_css()
        if css_content:
            prefix += f"<style>{css_content}</style>"
        html_content = prefix + html_content

        try:
            output = io.BytesIO()
            result = pisa.CreatePDF(
                src=io.StringIO(html_content),
                dest=output,
                default_css=None,
                path=base_url,
            )
            if result.err:
                raise RuntimeError(f"xhtml2pdf 변환 오류: {result.err}")
            return output.getvalue()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"PDF 변환 중 오류가 발생했습니다: {exc}") from exc

    def get_converter_name(self) -> str:
        return "xhtml2pdf"

    # ── 폰트 ─────────────────────────────────────────────────────────────
    def _font_css(self) -> str:
        """폰트를 reportlab 에 등록하고, 그 이름을 쓰는 CSS 를 돌려준다.

        @font-face + url(로컬 파일) 은 xhtml2pdf 가 임시 파일로 복사하는 과정에서
        Windows 에서 실패한다("Can't open file ...tmp.ttf"). reportlab 에 직접
        등록하고 xhtml2pdf 의 폰트명 매핑에 얹는 쪽이 안정적이다.
        """
        if not self._register_fonts():
            return ""
        return (
            f'<style>{_SELECTORS}{{font-family:"{self._family}";}}</style>'
        )

    def _register_fonts(self) -> bool:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from xhtml2pdf.default import DEFAULT_FONT

        registered: dict[int, str] = {}
        for weight, path, _css_weight in self._available_faces():
            name = f"{self._family}-{'Bold' if weight == 700 else 'Regular'}"
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(path)))
            registered[weight] = name

        if 400 not in registered:
            return False

        regular = registered[400]
        bold = registered.get(700, regular)
        pdfmetrics.registerFontFamily(
            regular, normal=regular, bold=bold, italic=regular,
            boldItalic=bold,
        )
        DEFAULT_FONT[self._family.lower()] = regular
        return True

    def _available_faces(self):
        for weight, suffix, css_weight in _WEIGHT_FILES:
            path = self._font_dir / f"{self._family}-{suffix}.ttf"
            if path.exists():
                yield weight, path, css_weight


def _default_font_dir() -> Path:
    # src/infrastructure/pdf_export/… → 프로젝트 루트(idt/)
    return Path(__file__).resolve().parents[3] / "resources" / "fonts"
