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


class HwpParseError(ValueError):
    """한글 문서(.hwp/.hwpx)를 읽을 수 없음 (hwp-parser Design §6.1).

    손상, 시그니처 불일치, 압축 해제 실패, 크기 상한 초과 등.
    ValueError 계열이라 기존 라우터의 422 매핑을 그대로 탄다.
    """


class HwpEncryptedError(HwpParseError):
    """암호가 걸렸거나 배포용으로 저장된 한글 문서."""

    def __init__(
        self,
        message: str = "암호가 걸렸거나 배포용으로 저장된 한글 문서는 지원하지 않습니다",
    ) -> None:
        super().__init__(message)
