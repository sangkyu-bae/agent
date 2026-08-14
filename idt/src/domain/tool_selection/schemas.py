"""도구 선별 VO — Design Ref: §3.1.

DB 스키마 없음. 전부 인메모리 frozen dataclass다.
"""
from dataclasses import dataclass
from enum import Enum


class ToolSource(str, Enum):
    """도구 출처. 설명 보강 규칙(§3.3)이 MCP 여부에 따라 달라지지 않도록
    보강은 저신호 판별로만 결정하지만, 관측·필터링을 위해 출처를 남긴다."""

    INTERNAL = "internal"
    MCP = "mcp"


@dataclass(frozen=True)
class ToolCandidate:
    """선별 대상 도구 1건.

    tool_id는 카탈로그 표기를 쓴다 (§3.2):
      내부  → ``internal:{tool_id}``
      MCP  → ``mcp:{server_id}:{tool_name}``
    저장·런타임 표기(``mcp_{server_id}``)로의 변환은 어댑터 책임이며
    이 모듈은 관여하지 않는다.
    """

    tool_id: str
    name: str
    description: str = ""
    source: ToolSource = ToolSource.INTERNAL
    server_name: str | None = None


@dataclass(frozen=True)
class SelectionResult:
    """선별 결과 + 관측 정보.

    Design Ref: §6.1 — 실패도 예외가 아니라 이 타입으로 표현된다.
    ``fallback``/``reason``을 보면 어떤 경로로 왔는지 항상 알 수 있다.
    """

    selected_ids: tuple[str, ...]
    """모델이 고른 것 (화이트리스트 정제 후)."""

    required_ids: tuple[str, ...]
    """호출부가 주입한 필수 세트. 항상 final_ids에 포함된다."""

    final_ids: tuple[str, ...]
    """required ∪ selected. 후보 원순서를 따르는 결정적 순서."""

    candidate_count: int
    elapsed_ms: int = 0
    fallback: bool = False
    reason: str | None = None
    dropped_ids: tuple[str, ...] = ()
    """환각으로 폐기된 ID (§6.1 #6)."""
