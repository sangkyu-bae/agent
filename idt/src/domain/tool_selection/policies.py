"""도구 선별 정책 — Design Ref: §3.3, §6.1.

전부 순수 함수다. 여기에 I/O·LLM·로깅이 들어오면 도메인 순수성이 깨진다.
"""
import hashlib
import re
from collections.abc import Iterable, Sequence

from src.domain.tool_selection.schemas import ToolCandidate

DEFAULT_TOP_K = 8
"""선별 상한 기본값. 실제 값은 설정으로 주입한다 (CLAUDE.md §3 하드코딩 금지)."""


class SelectionReason:
    """SelectionResult.reason 값 — Design §6.1 실패 모드 표와 1:1 대응."""

    UNDER_THRESHOLD = "under_threshold"
    NO_CANDIDATES = "no_candidates"
    CACHE_HIT = "cache_hit"
    LLM_ERROR = "llm_error"
    LLM_TIMEOUT = "llm_timeout"
    PARSE_ERROR = "parse_error"
    SANITIZED = "sanitized"
    EMPTY_SELECTION = "empty_selection"


# ── 저신호 설명 보강 (§3.3) ──────────────────────────────────────────────────

_LOW_SIGNAL_PREFIX = "MCP tool: "
"""infrastructure/mcp/tool_registry.py:88 이 설명 없는 MCP 도구에 채우는 스텁."""

_LOW_SIGNAL_STUB = re.compile(r"^MCP tool:\s*\S+$")
"""스텁 전문 패턴.

주의: 스텁의 꼬리는 **원본 MCP 도구명**(``mcp_tool.name``)인 반면, 어댑터의
``name``은 ``sanitize(f"{server}_{tool}")``로 서버명이 앞에 붙는다
(tool_registry.py:83-90). 즉 둘은 애초에 일치하지 않으므로 name 대조만으로는
스텁을 잡을 수 없다 — 패턴으로 판별해야 한다.
"""

_TOKEN_SPLIT = re.compile(r"[_\-.:/]+")


def is_low_signal(description: str, name: str) -> bool:
    """설명이 비었거나 ``MCP tool: {x}`` 스텁이면 True.

    ``"MCP tool: 무언가"`` 한 줄만 있는 설명은 정보량이 0이다. 실제 설명이
    우연히 이 형태(접두어 + 공백 없는 토큰 1개)일 확률은 무시할 수 있다.
    """
    text = (description or "").strip()
    if not text:
        return True
    if text == f"{_LOW_SIGNAL_PREFIX}{name}":
        return True
    return bool(_LOW_SIGNAL_STUB.match(text))


def tokenize_name(name: str) -> str:
    """``search_blog_posts`` → ``"search blog posts"``."""
    return " ".join(token for token in _TOKEN_SPLIT.split(name or "") if token)


def effective_description(candidate: ToolCandidate) -> str:
    """저신호 설명을 이름 토큰 + 서버명으로 보강한다.

    Plan SC: Recall — MCP 도구 설명이 스텁이면 셀렉터에 정보량이 0이 되어
    정답 도구를 놓친다. 추가 의존 없이 이름에서 신호를 복구한다.
    """
    if not is_low_signal(candidate.description, candidate.name):
        return candidate.description
    tokens = tokenize_name(candidate.name)
    if candidate.server_name:
        return f"{candidate.server_name} 서버의 '{tokens}' 기능"
    return f"'{tokens}' 기능"


# ── 선별 규칙 ────────────────────────────────────────────────────────────────


def needs_selection(candidate_count: int, top_k: int) -> bool:
    """후보가 상한보다 많을 때만 LLM을 부른다 (FR-08 — 불필요 비용 차단)."""
    return candidate_count > top_k


def sanitize(
    model_ids: Iterable[object],
    known_ids: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """모델 출력을 화이트리스트로 검증한다 → ``(kept, dropped)``.

    Design Ref: §7 — 목록에 없는 도구를 만들어낼 수 없게 하는 방어선.
    프롬프트 인젝션이 성공해도 후보 집합 밖으로는 나갈 수 없다.
    """
    known = set(known_ids)
    kept: list[str] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for raw in model_ids:
        if not isinstance(raw, str):
            dropped.append(str(raw))
            continue
        tool_id = raw.strip()
        if not tool_id or tool_id in seen:
            continue
        seen.add(tool_id)
        (kept if tool_id in known else dropped).append(tool_id)
    return tuple(kept), tuple(dropped)


def merge(
    required_ids: Sequence[str],
    selected_ids: Sequence[str],
    candidate_order: Sequence[str],
) -> tuple[str, ...]:
    """필수 세트 ∪ 추천 결과 — Plan FR-04.

    순서는 ``candidate_order``를 따른다 (결정성). 후보에 없는 required는
    뒤에 원순서대로 덧붙여, 호출부가 준 필수 도구가 절대 사라지지 않게 한다.
    """
    wanted = set(required_ids) | set(selected_ids)
    ordered = [tid for tid in candidate_order if tid in wanted]
    seen = set(ordered)
    for tool_id in required_ids:
        if tool_id not in seen:
            seen.add(tool_id)
            ordered.append(tool_id)
    return tuple(ordered)


def build_cache_key(query: str, candidate_ids: Sequence[str]) -> str:
    """``sha256(query | sorted(candidate_ids))`` — Design §4.2.

    후보 집합이 바뀌면 키가 달라져 캐시가 자동 무효화된다. v1은 NullCache라
    쓰이지 않지만, 나중에 TTL 캐시로 교체할 때 무효화 로직을 새로 짤 필요가 없다.
    """
    payload = "\x1f".join([query, *sorted(candidate_ids)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
