"""Domain interface for HTML to PDF converter.

Implementations live in infrastructure layer.
No external API calls allowed here.
"""
from abc import ABC, abstractmethod
from typing import Optional


class HtmlToPdfConverterInterface(ABC):
    """HTML → PDF 변환기 추상 인터페이스."""

    @abstractmethod
    def convert(
        self,
        html_content: str,
        css_content: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> bytes:
        """HTML 문자열을 PDF bytes로 변환한다.

        Args:
            html_content: HTML 문자열
            css_content: 추가 CSS 스타일 (선택)
            base_url: 상대 경로 리소스 기준 URL (선택)

        Returns:
            PDF 파일 bytes

        Raises:
            ValueError: html_content가 비어있을 때
            RuntimeError: 변환 라이브러리 오류 발생 시
        """

    @abstractmethod
    def get_converter_name(self) -> str:
        """변환기 구현체 이름을 반환한다."""
