"""저장·포크·상세 공용 도구 권한 판정 — 생성·수정·포크 UseCase 가 같은 규칙을 쓴다.

Design Ref: tool-access-control §2.2, §3.2 (gated_worker_validation 과 같은 공용 모듈 형태)
- 저장: 기존 정의에 없던 도구만 검증한다 — 기존 도구는 권한과 무관하게 유지 (Plan FR-06).
  다른 부서원이 쓰던 도구가 소유자의 저장 한 번으로 사라지지 않게 하기 위함.
- 포크·빌트인: 허용되지 않은 도구 워커를 뺀다 (FR-07, FR-08).
- 판정 규칙은 ToolAccessSet 이 가진다. 이 모듈은 워커·표기 변환 배선만 한다.
"""
from collections.abc import Iterable, Mapping

from src.application.tool_access.schemas import ExcludedToolInfo, ToolAccessInfo
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.agent_builder.tool_registry import TOOL_REGISTRY
from src.domain.tool_access.exceptions import ToolAccessDeniedError
from src.domain.tool_access.tool_ids import INTERNAL_PREFIX, to_catalog_tool_id
from src.domain.tool_access.value_objects import ToolAccessSet
from src.domain.tool_catalog.mcp_tool_id import parse_mcp_tool_id


def _key(tool_id: str) -> str:
    """표기가 달라도 같은 도구면 같은 키 (레거시 서버 단위는 원문 그대로)."""
    return to_catalog_tool_id(tool_id) or tool_id


def ensure_new_tools_allowed(
    access: ToolAccessSet,
    tool_ids: Iterable[str],
    previous_tool_ids: Iterable[str] = (),
) -> None:
    """previous 에 없던 도구 중 불허가 있으면 ToolAccessDeniedError (403)."""
    previous = {_key(t) for t in previous_tool_ids if t}
    denied = [
        _key(t) for t in tool_ids
        if t and _key(t) not in previous and not access.allows_reference(t)
    ]
    if denied:
        raise ToolAccessDeniedError(denied)


def partition_tool_workers(
    access: ToolAccessSet,
    workers: Iterable[WorkerDefinition],
    keep_tool_ids: Iterable[str] = (),
) -> tuple[list[WorkerDefinition], list[WorkerDefinition]]:
    """(유지, 제외) — 순서 보존. 서브에이전트 워커는 항상 유지(대상 아님)."""
    keep = {_key(t) for t in keep_tool_ids if t}
    kept: list[WorkerDefinition] = []
    excluded: list[WorkerDefinition] = []
    for w in workers:
        if (
            w.worker_type != "tool"
            or _key(w.tool_id) in keep
            or access.allows_reference(w.tool_id)
        ):
            kept.append(w)
        else:
            excluded.append(w)
    return kept, excluded


def tool_display_name(
    tool_id: str, catalog_names: Mapping[str, str] | None = None
) -> str:
    """카탈로그 이름 → 내부 레지스트리 이름 → MCP 도구명 조각 → 원문."""
    catalog_id = to_catalog_tool_id(tool_id)
    if catalog_names and catalog_id and catalog_id in catalog_names:
        return catalog_names[catalog_id]
    if catalog_id and catalog_id.startswith(INTERNAL_PREFIX):
        meta = TOOL_REGISTRY.get(catalog_id[len(INTERNAL_PREFIX):])
        if meta is not None:
            return meta.name
    ref = parse_mcp_tool_id(tool_id)
    if ref is not None and ref.tool_name:
        return ref.tool_name
    return tool_id


def excluded_info(
    workers: Iterable[WorkerDefinition],
    catalog_names: Mapping[str, str] | None = None,
) -> list[ExcludedToolInfo]:
    # 서브에이전트·상위가 같은 도구를 빼면 중복되므로 tool_id 기준 1회 (순서 보존)
    seen: set[str] = set()
    out: list[ExcludedToolInfo] = []
    for w in workers:
        key = _key(w.tool_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(ExcludedToolInfo(
            tool_id=key, name=tool_display_name(w.tool_id, catalog_names),
        ))
    return out


def excluded_tools_notice(excluded: Iterable[WorkerDefinition]) -> str:
    """실행 시 제외 도구 안내 블록 — supervisor·최종 답변 프롬프트 앞에 붙는다 (FR-11).

    도구 **이름**만 싣는다 — tool_id·서버 id 는 LLM 에 노출하지 않는다 (Design §7).
    """
    names = sorted({tool_display_name(w.tool_id) for w in excluded})
    if not names:
        return ""
    return (
        "## 사용할 수 없는 도구\n"
        f"다음 도구는 현재 사용자에게 권한이 없어 이번 실행에서 제외되었다: {', '.join(names)}.\n"
        "이 도구가 필요한 요청이면 권한이 없어 해당 작업을 수행할 수 없다고 사용자에게 안내하라.\n\n"
    )


def tool_access_info(
    access: ToolAccessSet,
    workers: Iterable[WorkerDefinition],
    catalog_names: Mapping[str, str] | None = None,
) -> list[ToolAccessInfo]:
    """에이전트 도구 워커별 허용 여부 — 빌더 칩 표시용 (FR-13)."""
    return [
        ToolAccessInfo(
            tool_id=_key(w.tool_id),
            name=tool_display_name(w.tool_id, catalog_names),
            permitted=access.allows_reference(w.tool_id),
        )
        for w in workers
        if w.worker_type == "tool" and w.tool_id
    ]
