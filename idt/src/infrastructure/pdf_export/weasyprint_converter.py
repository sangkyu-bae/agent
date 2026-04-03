"""xhtml2pdf 기반 HTML → PDF 변환기 구현체.

외부 라이브러리: xhtml2pdf (순수 Python, 시스템 의존성 없음)
WeasyPrint 인터페이스와 호환되는 래퍼 이름을 유지합니다.
"""
import io
from typing import Optional

import xhtml2pdf.pisa as pisa

from src.domain.pdf_export.interfaces import HtmlToPdfConverterInterface


class WeasyprintConverter(HtmlToPdfConverterInterface):
    """xhtml2pdf를 사용하는 HTML → PDF 변환기.

    WeasyPrint 대체 구현체로, 동일한 인터페이스를 제공합니다.
    Windows 환경에서 GTK 의존성 없이 동작합니다.
    """

    def convert(
        self,
        html_content: str,
        css_content: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> bytes:
        if not html_content.strip():
            raise ValueError("html_content must not be empty")

        if css_content:
            html_content = f"<style>{css_content}</style>" + html_content

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
