"""로컬 DB에 등록된 MCP 서버를 열거하고 실제 연결(list_tools)을 테스트하는 진단 스크립트.

uvicorn 없이 프로덕션과 동일한 코드 경로를 재사용한다:
  MCPServerRepository(find_all_active)  → 로컬 MySQL에서 등록 목록 + 시크릿 복호화
  MCPConnectionTestUseCase.execute()    → MCPToolLoader._build_config → MCPCallClient.list_tools

에이전트 런타임은 is_active=True 서버만 로드하므로, 기본은 활성 서버만 테스트한다
(--user 로 특정 사용자 범위 조회 가능).

실행:
    python -m scripts.verify_mcp_connections
    python -m scripts.verify_mcp_connections --user <user_id>
    python -m scripts.verify_mcp_connections --json

주의: 이 스크립트는 읽기 전용이다(DB 변경 없음).
"""
import argparse
import asyncio
import json
import logging
import sys
import uuid

from src.application.mcp_registry.mcp_connection_test_use_case import (
    MCPConnectionTestUseCase,
)
from src.config import settings
from src.infrastructure.logging import StructuredLogger
from src.infrastructure.mcp_registry.mcp_server_repository import MCPServerRepository
from src.infrastructure.persistence.database import get_session_factory
from src.infrastructure.security.secret_cipher import SecretCipher


def _cipher() -> SecretCipher | None:
    """settings.mcp_secret_key가 있으면 복호화기를, 없으면 None (main._mcp_cipher와 동일 규칙)."""
    key = settings.mcp_secret_key
    return SecretCipher(key) if key else None


async def _run(user_id: str | None) -> list[dict]:
    request_id = f"verify-mcp-{uuid.uuid4().hex[:8]}"
    level = logging.DEBUG if settings.debug else logging.INFO
    logger = StructuredLogger(name="verify-mcp", level=level)
    cipher = _cipher()
    factory = get_session_factory()

    async with factory() as session:
        repo = MCPServerRepository(session=session, logger=logger, cipher=cipher)
        use_case = MCPConnectionTestUseCase(repository=repo, logger=logger)

        if user_id:
            registrations = await repo.find_by_user(user_id, request_id)
        else:
            registrations = await repo.find_all_active(request_id)

        results: list[dict] = []
        for reg in registrations:
            resp = await use_case.execute(reg.id, request_id)
            results.append(
                {
                    "id": reg.id,
                    "name": reg.name,
                    "transport": reg.transport.value,
                    "is_active": reg.is_active,
                    "ok": bool(resp and resp.ok),
                    "tool_count": len(resp.tools) if resp and resp.ok else 0,
                    "elapsed_ms": resp.elapsed_ms if resp else None,
                    "error": (resp.error if resp and not resp.ok else None),
                }
            )
        return results


def _print_table(results: list[dict]) -> None:
    if not results:
        print("등록된 MCP 서버가 없습니다 (활성 서버 0건).")
        return

    print(f"\n총 {len(results)}개 MCP 서버 연결 테스트 결과\n")
    print(f"{'상태':<5}{'이름':<24}{'transport':<18}{'도구':<6}{'ms':<8}비고")
    print("-" * 90)
    ok_count = 0
    for r in results:
        mark = "OK  " if r["ok"] else "FAIL"
        if r["ok"]:
            ok_count += 1
        note = "" if r["ok"] else (r["error"] or "")
        note = note if len(note) <= 60 else note[:57] + "..."
        print(
            f"{mark:<5}{r['name'][:22]:<24}{r['transport']:<18}"
            f"{r['tool_count']:<6}{str(r['elapsed_ms'] or '-'):<8}{note}"
        )
    print("-" * 90)
    print(f"성공 {ok_count} / 실패 {len(results) - ok_count}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="로컬 DB의 등록 MCP 서버 연결 테스트 (읽기 전용 진단)"
    )
    parser.add_argument("--user", help="특정 user_id 범위로 조회 (미지정 시 활성 서버 전체)")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args()

    # Windows 콘솔(cp949) mojibake 방지 — 한글 출력을 UTF-8로 고정
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    results = asyncio.run(_run(args.user))

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        _print_table(results)

    # 실패가 하나라도 있으면 non-zero exit (CI/파이프라인 연동용)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
