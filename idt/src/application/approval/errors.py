"""approval-gate 애플리케이션 오류 — 라우터가 HTTP 상태로 매핑한다.

Design Ref: §6.1. 코드 문자열을 오류가 소유해 라우터·프론트가 같은 이름을 본다.
"""


class ApprovalError(Exception):
    """승인 흐름 오류의 기반. `code` 로 HTTP 매핑한다."""

    code = "APPROVAL_ERROR"
    http_status = 500


class ApprovalNotFoundError(ApprovalError):
    code = "APPROVAL_NOT_FOUND"
    http_status = 404


class ApprovalForbiddenError(ApprovalError):
    code = "APPROVAL_FORBIDDEN"
    http_status = 403


class ApprovalConflictError(ApprovalError):
    """이미 처리된 건. **중복 클릭의 정상 응답**이다 (Design §6.1)."""

    code = "APPROVAL_NOT_PENDING"
    http_status = 409


class ApprovalExpiredError(ApprovalError):
    code = "APPROVAL_EXPIRED"
    http_status = 410


class ApprovalInvalidWindowError(ApprovalError):
    """expires_at < execute_after — 영원히 집행되지 않는 조합 (FR-26)."""

    code = "APPROVAL_INVALID_WINDOW"
    http_status = 400


class ApprovalAgentChangedError(ApprovalError):
    """에이전트 정의 변경으로 재개 불가 (FR-14). execute_only 로 우회 가능."""

    code = "APPROVAL_AGENT_CHANGED"
    http_status = 409
