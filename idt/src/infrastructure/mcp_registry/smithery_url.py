"""Smithery Streamable HTTP URL/헤더 빌더.

Smithery 호스팅 MCP 서버(예: Naver Search)는 Streamable HTTP transport이며
플랫폼 인증(api_key/profile)을 쿼리로, 다운스트림 서버 config를 base64 JSON
'config' 쿼리로 전달한다. 본 모듈은 그 조립 규칙을 단일 지점에 격리한다.

infrastructure 레이어 — 네트워크 없음, 순수 함수.
"""
import base64
import json
from urllib.parse import urlencode, urlsplit, urlunsplit


def _ensure_mcp_path(endpoint: str) -> tuple[str, str, str]:
    """endpoint를 (scheme, netloc, path)로 분해하고 path 끝을 /mcp로 보정한다."""
    parts = urlsplit(endpoint)
    path = parts.path.rstrip("/")
    if not path.endswith("/mcp"):
        path = f"{path}/mcp"
    return parts.scheme, parts.netloc, path


def _encode_config(server_config: dict | None) -> str | None:
    """server_config dict를 Smithery 'config' 쿼리용 base64(JSON)로 인코딩한다."""
    if not server_config:
        return None
    raw = json.dumps(server_config, ensure_ascii=False, sort_keys=True)
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


def build_streamable_http(
    endpoint: str,
    auth_config: dict | None,
    server_config: dict | None,
) -> tuple[str, dict[str, str]]:
    """Smithery Streamable HTTP 호출용 (url, headers)를 조립한다.

    - endpoint path 끝이 /mcp가 아니면 보정
    - auth_config.api_key / profile → 쿼리 파라미터
    - server_config → base64(JSON) 'config' 쿼리 파라미터
    - auth_config.headers → 추가 HTTP 헤더(Authorization 등)

    Returns:
        (쿼리가 포함된 URL, 정적 헤더 dict)
    """
    auth = auth_config or {}
    scheme, netloc, path = _ensure_mcp_path(endpoint)

    query: dict[str, str] = {}
    if auth.get("api_key"):
        query["api_key"] = str(auth["api_key"])
    if auth.get("profile"):
        query["profile"] = str(auth["profile"])
    encoded_config = _encode_config(server_config)
    if encoded_config:
        query["config"] = encoded_config

    url = urlunsplit((scheme, netloc, path, urlencode(query), ""))
    headers: dict[str, str] = dict(auth.get("headers") or {})
    return url, headers
