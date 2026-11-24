"""Grafana HTTP 클라이언트 — 알림 룰 상태와 Loki 쿼리(데이터소스 프록시).

Design Ref: firewall-admin-console §4.4 — 2026-11-23 Grafana 12.0.0 에서 Viewer
서비스 계정 토큰으로 3개 경로를 실측했다. 응답 형식이 어긋나면 빈 목록이 아니라
GrafanaUnavailableError 로 드러낸다(조용히 비어 보이지 않게).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from src.domain.firewall_admin.errors import GrafanaUnavailableError
from src.domain.firewall_admin.models import (
    AlertInstance,
    AlertRule,
    LokiLine,
    LokiSample,
    normalize_alert_state,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface

GRAFANA_TIMEOUT_SECONDS = 10.0
# fireware observability/grafana/provisioning 의 고정값
DETECTION_RULE_GROUP = "firewall-detection"
LOKI_DATASOURCE_UID = "loki"

_RULES_PATH = "/api/prometheus/grafana/api/v1/rules"
_LOKI_PROXY = f"/api/datasources/proxy/uid/{LOKI_DATASOURCE_UID}/loki/api/v1"


def _parse_ts(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw or raw.startswith("0001-"):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class GrafanaClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        logger: LoggerInterface,
        timeout: float = GRAFANA_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or "").strip().rstrip("/")
        self._token = (token or "").strip()
        self._logger = logger
        self._client = httpx.AsyncClient(
            base_url=self._base_url or "http://grafana.invalid",
            timeout=timeout,
            transport=transport,
        )

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._token)

    async def aclose(self) -> None:
        await self._client.aclose()

    # ── 알림 ──────────────────────────────────────────────────────

    async def alert_rules(self) -> tuple[AlertRule, ...]:
        """탐지 룰 그룹의 룰 전부. 그룹이 없으면 실패로 본다."""
        body = await self._get(_RULES_PATH, {})
        try:
            groups = body["data"]["groups"]
            group = next(g for g in groups if g.get("name") == DETECTION_RULE_GROUP)
            return tuple(self._rule(raw) for raw in group["rules"])
        except StopIteration as e:
            self._logger.warning("grafana.rule_group_missing", group=DETECTION_RULE_GROUP)
            raise GrafanaUnavailableError(details={"reason": "rule_group_missing"}) from e
        except (KeyError, TypeError, AttributeError) as e:
            raise self._shape_error("rules") from e

    @staticmethod
    def _rule(raw: dict[str, Any]) -> AlertRule:
        labels = raw.get("labels") or {}
        annotations = raw.get("annotations") or {}
        healthy = raw.get("health", "ok") == "ok"
        instances = tuple(
            AlertInstance(
                src_ip=(alert.get("labels") or {}).get("src_ip") or None,
                state=normalize_alert_state(alert.get("state")),
                active_at=_parse_ts(alert.get("activeAt")),
                value=str(alert["value"]) if alert.get("value") not in (None, "") else None,
            )
            for alert in (raw.get("alerts") or [])
        )
        return AlertRule(
            uid=str(raw["uid"]),
            name=str(raw["name"]),
            rule_id=str(labels.get("rule_id") or ""),
            kind=str(labels.get("kind") or ""),
            severity=str(labels.get("severity") or ""),
            action_hint=str(labels.get("action_hint") or ""),
            state=normalize_alert_state(raw.get("state")) if healthy else "error",
            # summary 는 Grafana 가 템플릿 원문으로 돌려주므로 쓰지 않는다.
            description=str(annotations.get("description") or ""),
            last_evaluation=_parse_ts(raw.get("lastEvaluation")),
            instances=instances,
        )

    # ── Loki ──────────────────────────────────────────────────────

    async def loki_instant(self, query: str, *, at_ns: int) -> list[LokiSample]:
        body = await self._get(f"{_LOKI_PROXY}/query", {"query": query, "time": str(at_ns)})
        try:
            data = body["data"]
            if data["resultType"] != "vector":
                raise TypeError(data["resultType"])
            return [
                LokiSample(labels=dict(row.get("metric") or {}), value=float(row["value"][1]))
                for row in data["result"]
            ]
        except (KeyError, TypeError, ValueError, IndexError) as e:
            raise self._shape_error("loki_instant") from e

    async def loki_range(
        self, query: str, *, start_ns: int, end_ns: int, limit: int
    ) -> list[LokiLine]:
        """최신순 줄 목록. 스트림이 여러 개여도 시각 기준으로 합쳐 limit 만큼 돌려준다."""
        body = await self._get(
            f"{_LOKI_PROXY}/query_range",
            {
                "query": query, "start": str(start_ns), "end": str(end_ns),
                "limit": str(limit), "direction": "backward",
            },
        )
        try:
            data = body["data"]
            if data["resultType"] != "streams":
                raise TypeError(data["resultType"])
            lines = [
                LokiLine(ts_ns=int(ts), labels=dict(stream.get("stream") or {}), line=str(line))
                for stream in data["result"]
                for ts, line in stream["values"]
            ]
        except (KeyError, TypeError, ValueError) as e:
            raise self._shape_error("loki_range") from e
        lines.sort(key=lambda x: x.ts_ns, reverse=True)
        return lines[:limit]

    # ── 내부 ──────────────────────────────────────────────────────

    def _shape_error(self, what: str) -> GrafanaUnavailableError:
        self._logger.warning(f"grafana.unexpected_shape: {what}")
        return GrafanaUnavailableError(details={"reason": "unexpected_shape"})

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.configured:
            raise GrafanaUnavailableError(details={"reason": "not_configured"})
        try:
            response = await self._client.get(
                path, params=params, headers={"Authorization": f"Bearer {self._token}"}
            )
        except httpx.HTTPError as e:
            self._logger.warning("grafana.unavailable", exception=e, path=path)
            raise GrafanaUnavailableError(details={"reason": "unreachable"}) from e
        if response.status_code != 200:
            self._logger.warning("grafana.bad_status", status=response.status_code, path=path)
            raise GrafanaUnavailableError(details={"status": response.status_code})
        try:
            body = response.json()
        except ValueError as e:
            raise self._shape_error("non-json") from e
        if not isinstance(body, dict) or body.get("status") != "success":
            raise self._shape_error("status")
        return body
