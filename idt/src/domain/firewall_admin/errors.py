"""firewall_admin 오류 계열.

Design Ref: firewall-admin-console §6.1 — 오류가 code·http_status 를 소유하고
라우터는 그대로 옮기기만 한다. 코드 이름은 mcp-firewall-server 와 같게 둔다.
"""
from __future__ import annotations

from typing import Any


class FirewallAdminError(Exception):
    code: str = "FIREWALL_ADMIN_ERROR"
    http_status: int = 500
    default_message: str = "방화벽 관리 요청을 처리하지 못했습니다"

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None):
        super().__init__(message or self.default_message)
        self.details: dict[str, Any] = details or {}


class InvalidIpError(FirewallAdminError):
    code = "INVALID_IP"
    http_status = 422
    default_message = "IPv4 주소 한 개를 입력하세요"


class InvalidTtlError(FirewallAdminError):
    code = "INVALID_TTL"
    http_status = 422
    default_message = "유지 시간이 허용 범위를 벗어났습니다"


class InvalidReasonError(FirewallAdminError):
    code = "INVALID_REASON"
    http_status = 422
    default_message = "사유를 1~500자로 입력하세요"


class InvalidFilterError(FirewallAdminError):
    code = "INVALID_FILTER"
    http_status = 422
    default_message = "조회 조건이 올바르지 않습니다"


class InvalidRequestError(FirewallAdminError):
    """본문이 JSON 이 아니거나 받지 않는 필드(actor 등)가 있는 요청."""

    code = "INVALID_REQUEST"
    http_status = 422
    default_message = "요청 형식이 올바르지 않습니다"


class ForbiddenWhitelistError(FirewallAdminError):
    code = "FORBIDDEN_WHITELIST"
    http_status = 403
    default_message = "보호 대상 주소라 차단할 수 없습니다"


class FwctlAuthFailedError(FirewallAdminError):
    code = "FWCTL_AUTH_FAILED"
    http_status = 502
    default_message = "fwctl 인증에 실패했습니다. 서버 설정을 확인하세요"


class FwctlAuditError(FirewallAdminError):
    """fwctl 이 '적용은 됐으나 감사 미기록'을 돌려준 경우 — 실패로 드러낸다."""

    code = "FWCTL_AUDIT_ERROR"
    http_status = 502
    default_message = "차단은 적용됐지만 감사 기록에 실패했습니다. 운영자에게 알려 주세요"


class FwctlUnavailableError(FirewallAdminError):
    code = "FWCTL_UNAVAILABLE"
    http_status = 502
    default_message = "fwctl에 연결할 수 없습니다"


class FwctlTimeoutError(FirewallAdminError):
    code = "FWCTL_TIMEOUT"
    http_status = 504
    default_message = "fwctl 응답이 지연되고 있습니다"


class GrafanaUnavailableError(FirewallAdminError):
    code = "GRAFANA_UNAVAILABLE"
    http_status = 503
    # 탐지·감사 탭이 함께 쓰므로 탭 이름을 넣지 않는다 (Check G4)
    default_message = "Grafana에서 정보를 가져올 수 없습니다. Grafana가 실행 중인지 확인하세요"
