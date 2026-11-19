"""원본 조회 실패 구분 (Design §4.2). 라우터가 404·415 로 바꾼다."""


class OriginalNotAvailableError(LookupError):
    """원본이 보관되지 않았다 — 보관 기능 이전 문서, 저장 실패, 잘못된 id."""

    code = "ORIGINAL_NOT_AVAILABLE"


class UnsupportedOriginalError(ValueError):
    """원본 뷰어가 렌더할 수 없는 형식(pdf/docx 외)."""

    code = "ORIGINAL_UNSUPPORTED"
