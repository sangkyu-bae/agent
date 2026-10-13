"""excel-preview 도메인 예외 (Design §4.2 오류 계약).

라우터에서 HTTP로 매핑: 404 / 403 / 415 / 422.
"""


class PreviewFileNotFoundError(Exception):
    """파일 없음 또는 TTL 만료 (404 FILE_NOT_FOUND)."""


class PreviewForbiddenError(Exception):
    """소유자 불일치 (403 FORBIDDEN)."""


class PreviewUnsupportedError(Exception):
    """.xlsx 외 확장자 (415 PREVIEW_UNSUPPORTED)."""


class PreviewParseFailedError(Exception):
    """손상 파일 등 파싱 실패 (422 PREVIEW_PARSE_FAILED). 원인은 __cause__로 체이닝."""
