"""파서 도메인 예외 (kb-excel-upload D2)."""
from src.domain.parser.supported_formats import supported_formats_display


class UnsupportedFileFormatError(ValueError):
    """미지원 확장자 업로드 시도.

    ValueError 서브클래스로 두어 기존 라우터의 ValueError→422 매핑에
    라우터 수정 없이 편승한다 (knowledge_base_router._raise_http,
    unified_upload_router의 except ValueError).
    """

    def __init__(self, extension: str) -> None:
        super().__init__(
            f"Unsupported file format '{extension}'. "
            f"Supported: {supported_formats_display()}"
        )
        self.extension = extension
