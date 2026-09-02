"""SyncOutcome: MCP 도구 동기화 시도 결과 값 객체 + 진단 힌트 매핑.

Design Ref: mcp-tool-auto-sync §3.1, §6.2, §9.3
  - 부수효과 sync의 성패를 호출자(등록/수정 UseCase)와 응답 스키마에 전달한다.
  - domain이 아닌 application에 두는 이유: 비즈니스 규칙이 아니라 "부수효과 시도
    결과"라는 흐름 제어 정보이며, domain이 인프라 사정(네트워크 실패)을 알면 안 된다.
"""
import asyncio
import re
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True)
class SyncOutcome:
    """MCP 도구 동기화 1회 시도의 결과.

    Attributes:
        attempted: sync를 시도했는가. 의존성 미주입 시 False (FR-06).
        ok: 시도했고 성공했는가.
        synced_count: 동기화된 도구 수.
        error_hint: 실패 시 관리자용 진단 힌트. 원본 예외 메시지가 아니다 (§7).
    """

    attempted: bool
    ok: bool
    synced_count: int
    error_hint: str | None

    @classmethod
    def skipped(cls) -> "SyncOutcome":
        """sync 의존성 미주입 — 기존 동작 유지 경로 (FR-06)."""
        return cls(attempted=False, ok=False, synced_count=0, error_hint=None)

    @classmethod
    def succeeded(cls, count: int) -> "SyncOutcome":
        return cls(attempted=True, ok=True, synced_count=count, error_hint=None)

    @classmethod
    def failed(cls, hint: str) -> "SyncOutcome":
        return cls(attempted=True, ok=False, synced_count=0, error_hint=hint)


# ── 진단 힌트 매핑 (§6.2) ────────────────────────────────────────────
# 원본 예외 메시지를 클라이언트에 그대로 노출하지 않는다 — 내부 URL·api_key가
# 쿼리스트링에 섞여 있을 수 있기 때문(§7).

DEFAULT_SYNC_HINT = (
    "MCP 서버에서 도구 목록을 가져오지 못했습니다. "
    "[테스트]로 연결을 확인한 뒤 [동기화]를 다시 실행하세요."
)

# TOOL-MCP-001 §3: 'Session terminated'는 세션 만료가 아니라 대부분 HTTP 404이며,
# 주 원인은 빈 api_key가 URL에서 누락된 경우다. 404 규칙보다 먼저 검사한다.
_HINT_RULES: tuple[tuple[str, str], ...] = (
    (
        "session terminated",
        "MCP 서버가 요청을 거부했습니다. api_key 누락으로 인한 404 가능성이 높습니다 — "
        "인증 설정을 확인한 뒤 [동기화]를 다시 실행하세요.",
    ),
    (
        "timeout",
        "MCP 서버 응답이 지연되어 동기화를 중단했습니다. "
        "서버 상태를 확인한 뒤 [동기화]를 다시 실행하세요.",
    ),
    (
        "401",
        "MCP 서버 인증에 실패했습니다(401). api_key를 확인하세요.",
    ),
    (
        "403",
        "MCP 서버가 접근을 거부했습니다(403). 권한 설정을 확인하세요.",
    ),
    (
        "404",
        "MCP 서버 엔드포인트를 찾을 수 없습니다(404). endpoint와 인증 설정을 확인하세요.",
    ),
)


def hint_for(exc: Exception) -> str:
    """예외를 관리자용 진단 힌트로 매핑한다.

    매칭 실패 시 기본 문구를 돌려주며, 어떤 경우에도 원본 메시지를 포함하지 않는다.
    """
    # asyncio.TimeoutError는 str()이 빈 문자열이라 클래스명까지 검사 대상에 넣는다.
    haystack = f"{type(exc).__name__} {exc}".lower()
    for needle, hint in _HINT_RULES:
        if needle in haystack:
            return hint
    return DEFAULT_SYNC_HINT


async def run_tool_sync(
    sync_use_case,
    server_id: str,
    request_id: str,
    timeout_sec: float,
    logger,
) -> SyncOutcome:
    """MCP 서버 등록/수정 직후의 도구 카탈로그 동기화 (best-effort).

    Design Ref: mcp-tool-auto-sync §2.0, §6.1 — 예외 분류가 이 함수의 존재 이유다.
      - SQLAlchemyError: 세션을 오염시켜 삼켜도 커밋이 실패하므로 재전파한다.
        (삼키면 등록 API가 뒤늦게 500이 되어 FR-03 계약이 깨진다)
      - CancelledError: BaseException이라 아래 except에 걸리지 않고 자연 전파된다.
      - 그 외(네트워크·MCP·타임아웃): 흡수하고 등록/수정을 성공시킨다.

    Register/Update 두 UseCase가 동일 로직을 쓰므로 헬퍼로 승격했다.
    """
    if sync_use_case is None:
        return SyncOutcome.skipped()  # FR-06

    try:
        count = await asyncio.wait_for(
            sync_use_case.execute(server_id, request_id),
            timeout=timeout_sec,
        )
        return SyncOutcome.succeeded(count)
    except SQLAlchemyError:
        raise
    except Exception as e:
        logger.warning(
            "MCP tool sync failed after registry write",
            request_id=request_id,
            server_id=server_id,
            error_type=type(e).__name__,
            error=_redact(str(e)),
        )
        return SyncOutcome.failed(hint_for(e))


_SECRET_QUERY_KEYS = ("api_key", "apikey", "token", "secret", "password")


def _redact(message: str) -> str:
    """로그에 남길 예외 메시지에서 시크릿 쿼리 파라미터 값을 가린다 (§7).

    MCP endpoint는 `?api_key=...` 형태로 키를 실어 나르며, 예외 메시지에 URL이
    통째로 섞여 들어오는 경우가 있다.
    """
    def _mask(match: re.Match[str]) -> str:
        return f"{match.group(1)}=***"

    pattern = "|".join(_SECRET_QUERY_KEYS)
    return re.sub(rf"({pattern})=[^&\s\"']+", _mask, message, flags=re.IGNORECASE)


__all__ = [
    "SyncOutcome",
    "hint_for",
    "run_tool_sync",
    "DEFAULT_SYNC_HINT",
]
