"""fwctl HTTP 클라이언트.

Design Ref: firewall-admin-console §4.3, §6.1 — 계약은 fireware docs/fwctl-api.md
v0.1.0 그대로. 재시도 없음(차단은 사람이 확인한 1회 호출), 타임아웃 5초.
httpx.AsyncClient 는 앱 수명 동안 1개를 재사용한다(app-lifetime-client-singleton).
토큰은 요청 헤더에만 쓰고 로그·오류 메시지에 넣지 않는다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from src.domain.firewall_admin.errors import (
    FirewallAdminError,
    ForbiddenWhitelistError,
    FwctlAuditError,
    FwctlAuthFailedError,
    FwctlTimeoutError,
    FwctlUnavailableError,
    InvalidIpError,
    InvalidTtlError,
)
from src.domain.firewall_admin.models import (
    BlockEntry,
    BlockList,
    BlockResult,
    FwctlHealth,
    UnblockResult,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface

FWCTL_TIMEOUT_SECONDS = 5.0


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


class FwctlClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        logger: LoggerInterface,
        timeout: float = FWCTL_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or "").strip().rstrip("/")
        self._token = (token or "").strip()
        self._logger = logger
        self._client = httpx.AsyncClient(
            base_url=self._base_url or "http://fwctl.invalid",
            timeout=timeout,
            transport=transport,
        )

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._token)

    async def aclose(self) -> None:
        await self._client.aclose()

    # ── 조회 ──────────────────────────────────────────────────────

    async def health(self) -> FwctlHealth:
        """생존·모드 확인. 장애를 예외로 올리지 않고 reachable=False 로 알린다."""
        if not self._base_url:
            return FwctlHealth(reachable=False)
        try:
            response = await self._client.get("/healthz")
            body = response.json()
            if response.status_code not in (200, 503) or not isinstance(body, dict):
                return FwctlHealth(reachable=False)
            return FwctlHealth(
                reachable=True,
                dry_run=bool(body["dry_run"]),
                max_ttl_seconds=int(body["max_ttl_seconds"]),
                ipset_exists=bool(body["ipset_exists"]),
                version=str(body.get("version") or "") or None,
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            # 상태 조회의 정상 결과(연결 안 됨)라 debug 로 남긴다. 화면이 30초마다 묻기 때문에
            # warning 이면 fwctl 이 내려가 있는 동안 같은 경고가 계속 쌓인다 (Check G5).
            # 차단·해제 경로의 연결 실패는 _request 가 warning 으로 남긴다.
            self._logger.debug("fwctl.health_unreachable", exception=e)
            return FwctlHealth(reachable=False)

    async def list_blocks(self, *, request_id: str) -> BlockList:
        body = await self._request("GET", "/v1/blocks", request_id=request_id)
        try:
            items = tuple(
                BlockEntry(
                    ip=str(row["ip"]),
                    ttl_remaining_seconds=int(row["ttl_remaining_seconds"]),
                    packets=int(row.get("packets") or 0),
                    bytes=int(row.get("bytes") or 0),
                )
                for row in body["data"]
            )
            return BlockList(items=items, dry_run=bool(body["dry_run"]))
        except (KeyError, TypeError, ValueError) as e:
            raise self._drift(request_id, "list response shape") from e

    # ── 변경 ──────────────────────────────────────────────────────

    async def block(
        self, *, ip: str, ttl_seconds: int | None, reason: str, actor: str, request_id: str
    ) -> BlockResult:
        payload: dict[str, Any] = {"ip": ip, "reason": reason, "actor": actor}
        if ttl_seconds is not None:
            payload["ttl_seconds"] = ttl_seconds
        body = await self._request("POST", "/v1/blocks", request_id=request_id, json=payload)
        try:
            data = body["data"]
            return BlockResult(
                ip=str(data["ip"]),
                ttl_seconds=int(data["ttl_seconds"]),
                expires_at=_parse_ts(data["expires_at"]),
                reason=str(data.get("reason") or reason),
                dry_run=bool(data["dry_run"]),
                request_id=str(data.get("request_id") or request_id),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise self._drift(request_id, "block response shape") from e

    async def unblock(self, *, ip: str, request_id: str) -> UnblockResult:
        body = await self._request(
            "DELETE", f"/v1/blocks/{ip}", request_id=request_id, not_found_ok=True
        )
        if body is None:  # 404 — 이미 없음
            return UnblockResult(ip=ip, removed=False, dry_run=None, already_absent=True)
        try:
            data = body["data"]
            return UnblockResult(
                ip=str(data["ip"]),
                removed=bool(data["removed"]),
                dry_run=bool(data["dry_run"]),
                already_absent=False,
            )
        except (KeyError, TypeError, ValueError) as e:
            raise self._drift(request_id, "unblock response shape") from e

    # ── 내부 ──────────────────────────────────────────────────────

    def _drift(self, request_id: str, what: str) -> FwctlUnavailableError:
        self._logger.warning(f"fwctl.contract_drift: {what}", request_id=request_id)
        return FwctlUnavailableError(details={"reason": "contract_drift"})

    async def _request(
        self,
        method: str,
        path: str,
        *,
        request_id: str,
        json: dict[str, Any] | None = None,
        not_found_ok: bool = False,
    ) -> dict[str, Any] | None:
        if not self.configured:
            # 토큰 없이 보내면 fwctl 감사에 무의미한 401 만 쌓인다.
            raise FwctlAuthFailedError(details={"reason": "not_configured"})
        headers = {"Authorization": f"Bearer {self._token}", "X-Request-Id": request_id}
        try:
            response = await self._client.request(method, path, headers=headers, json=json)
        except httpx.TimeoutException as e:
            self._logger.warning("fwctl.timeout", request_id=request_id, path=path)
            raise FwctlTimeoutError() from e
        except httpx.HTTPError as e:
            self._logger.warning("fwctl.unavailable", exception=e, request_id=request_id)
            raise FwctlUnavailableError() from e

        status = response.status_code
        try:
            body = response.json()
        except ValueError:
            body = None

        if status in (200, 201):
            if not isinstance(body, dict):
                raise self._drift(request_id, "non-json success body")
            return body
        if status == 404 and not_found_ok:
            return None
        raise self._map_error(status, body, request_id)

    def _map_error(self, status: int, body: Any, request_id: str) -> FirewallAdminError:
        error = body.get("error") if isinstance(body, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        details = error.get("details") if isinstance(error, dict) else None
        details = details if isinstance(details, dict) else {}

        if status == 400 and code == "INVALID_IP":
            return InvalidIpError()
        if status == 400:
            # idt 가 먼저 걸러야 하는 값이 fwctl 까지 갔다 — 계약이 어긋났다는 신호.
            return self._drift(request_id, f"fwctl 400 {code}")
        if status == 401:
            return FwctlAuthFailedError()
        if status == 403 and code == "FORBIDDEN_WHITELIST":
            return ForbiddenWhitelistError(details={"matched": details.get("matched")})
        if status == 422 and code == "INVALID_TTL":
            max_ttl = details.get("max_ttl_seconds")
            message = f"유지 시간은 1~{max_ttl}초입니다" if max_ttl else None
            return InvalidTtlError(message, details={"max_ttl_seconds": max_ttl})
        if status == 500 and code == "AUDIT_ERROR":
            self._logger.error("fwctl.audit_error", request_id=request_id)
            return FwctlAuditError()
        self._logger.warning(
            "fwctl.unexpected_status", request_id=request_id, status=status, code=code
        )
        return FwctlUnavailableError(details={"status": status, "code": code})
