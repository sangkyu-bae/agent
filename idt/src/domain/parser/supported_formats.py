"""업로드 지원 포맷 판정 단일 진실원 (kb-excel-upload D1).

파서 라우팅·유스케이스 정책 분기·에러 메시지가 이 모듈 하나를 공유한다.
포맷 추가 시 SUPPORTED_EXTENSIONS만 수정한다.
"""
from pathlib import PurePosixPath, PureWindowsPath

FORMAT_PDF = "pdf"
FORMAT_EXCEL = "excel"

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": FORMAT_PDF,
    ".xlsx": FORMAT_EXCEL,
    ".xls": FORMAT_EXCEL,
}


def resolve_format(filename: str) -> str | None:
    """파일명 확장자로 포맷을 판정한다. 미지원이면 None."""
    suffix = _suffix_of(filename)
    return SUPPORTED_EXTENSIONS.get(suffix)


def supported_formats_display() -> str:
    """에러 메시지용 지원 확장자 나열 (예: "pdf, xlsx, xls")."""
    return ", ".join(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS)


def _suffix_of(filename: str) -> str:
    # 경로 구분자가 섞여 들어와도 basename의 확장자만 본다
    name = PureWindowsPath(filename).name
    return PurePosixPath(name).suffix.lower()
