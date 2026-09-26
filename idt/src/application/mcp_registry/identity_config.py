"""MCP 등록/수정 UseCase 의 identity_config 해석 (흐름 제어만, 규칙은 도메인).

Design Ref: mcp-identity-header §4.2 — PUT 은 auth_config 와 달리 통째 교체가
아니다. 필드 없음=불변, null=해제, 객체=IdentityHeaderConfig.merge_update.
"""
from pydantic import BaseModel

from src.domain.mcp_registry.identity import IdentityHeaderConfig
from src.domain.mcp_registry.policies import MCPRegistrationPolicy

_FIELD = "identity_config"
_NO_CIPHER = (
    "MCP_SECRET_KEY가 설정되지 않아 신원 헤더 서명 비밀을 저장할 수 없습니다. "
    ".env에 MCP_SECRET_KEY를 설정하세요"
)
_HEADER_CONFLICT = "identity header_name conflicts with auth_config.headers"
_UNREADABLE = (
    "신원 헤더 설정을 읽을 수 없습니다(암호화 키 누락·변경). "
    "서명 비밀을 포함해 다시 입력하거나 해제(null)하세요"
)


def resolve_for_register(
    raw: dict | None, secrets_enabled: bool
) -> IdentityHeaderConfig | None:
    if raw is None:
        return None
    _require_cipher(secrets_enabled)
    return IdentityHeaderConfig.from_dict(raw)


def resolve_for_update(
    existing: IdentityHeaderConfig | None,
    request: BaseModel,
    secrets_enabled: bool,
    existing_unreadable: bool = False,
) -> IdentityHeaderConfig | None:
    """요청에 필드가 없으면 기존 값을 그대로 돌려준다 (JSON null 과 구분).

    Check G-3: 기존 값을 읽을 수 없으면 '그대로'가 곧 삭제다 — 필드 없는 수정을
    거부해 관리자가 다시 입력하거나 명시적으로 해제하게 한다.
    """
    if _FIELD not in request.model_fields_set:
        if existing_unreadable:
            raise ValueError(_UNREADABLE)
        return existing
    raw = getattr(request, _FIELD)
    if raw is None:
        return None
    _require_cipher(secrets_enabled)
    return IdentityHeaderConfig.merge_update(existing, raw)


def ensure_no_header_conflict(
    identity: IdentityHeaderConfig | None, auth_config: dict | None
) -> None:
    if not MCPRegistrationPolicy.validate_identity_headers(identity, auth_config):
        raise ValueError(_HEADER_CONFLICT)


def _require_cipher(secrets_enabled: bool) -> None:
    if not secrets_enabled:
        raise ValueError(_NO_CIPHER)
