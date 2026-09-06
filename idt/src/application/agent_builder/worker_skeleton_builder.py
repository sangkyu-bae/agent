"""워커 스켈레톤 빌드 공용 모듈 (agent-update-tool-editing D §2.3 / §9.4).

CreateAgentUseCase 가 갖고 있던 워커 빌드 private 메서드를 행위보존 추출한 것.
생성(create)과 수정(update)이 도구 ID 정규화·MCP 해석·빌트인 주입·worker_id
생성 규칙을 **한 벌**로 공유한다 — 두 벌로 두면 한쪽만 고쳐져 조용히 어긋난다.
"""
from __future__ import annotations

from src.application.agent_builder.schemas import RagToolConfigRequest
from src.domain.agent_builder.rag_tool_config import sanitize_tool_name
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowSkeleton
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.mcp_tool_id import parse_mcp_tool_id


def normalize_tool_id(raw_key: str) -> str:
    """카탈로그 형식을 저장 형식으로 정규화.

    MCP는 개별 도구 단위(`mcp:{srv}:{tool}`)를 **그대로** 저장한다.
    서버 단위로 접으면 사용자가 고른 도구가 소실되고, 실행 시 서버가
    먼저 돌려준 임의의 도구가 바인딩된다.
    레거시 `mcp_{srv}`도 그대로 통과시킨다(기존 에이전트 호환).
    `internal:{id}`만 접두사를 벗긴다.
    """
    if parse_mcp_tool_id(raw_key) is not None:
        return raw_key
    return raw_key.split(":")[-1] if ":" in raw_key else raw_key


def make_worker_id(tool_id: str) -> str:
    """worker_id는 LangGraph 노드명·LLM 노출명이라 콜론을 못 쓴다.

    Design Ref: §10.4 — 추출 전에는 tool_ids 경로만 sanitize를 거치고
    configs·빌트인 경로는 f-string 을 직접 썼다. 공용 빌더에서는 이 함수
    하나로 통일한다 (MCP 콜론 포함 ID 안전).
    """
    return sanitize_tool_name(f"{tool_id}_worker", fallback="mcp_worker")


class WorkerSkeletonBuilder:
    """도구 워커 목록을 구성한다. 저장·정책 검증은 호출부(UseCase) 책임."""

    def __init__(
        self,
        logger: LoggerInterface,
        mcp_server_repo=None,
        tool_catalog_repo=None,
    ) -> None:
        self._logger = logger
        # nl-agent-composer FR-08: mcp_* tool_id 메타 해석용 (미주입 시 mcp_* 거부)
        self._mcp_server_repo = mcp_server_repo
        # builtin-tools D5: 빌트인 주입용 (미주입 시 주입 생략 — 무회귀)
        self._tool_catalog_repo = tool_catalog_repo

    def build_from_configs(
        self,
        tool_configs: dict[str, RagToolConfigRequest],
        request_id: str,
    ) -> WorkflowSkeleton:
        workers: list[WorkerDefinition] = []
        for i, (raw_key, config) in enumerate(tool_configs.items()):
            tool_id = normalize_tool_id(raw_key)
            meta = get_tool_meta(tool_id)
            workers.append(WorkerDefinition(
                tool_id=tool_id,
                worker_id=make_worker_id(tool_id),
                description=meta.description,
                sort_order=i,
                tool_config=config.model_dump(),
            ))
        self._logger.info(
            "Built skeleton from tool_configs",
            request_id=request_id,
            tool_ids=[w.tool_id for w in workers],
        )
        return WorkflowSkeleton(workers=workers, flow_hint=_flow_hint(workers))

    async def build_from_tool_ids(
        self,
        tool_ids: list[str],
        tool_configs: dict[str, RagToolConfigRequest] | None,
        request_id: str,
    ) -> WorkflowSkeleton:
        """사용자가 화면에서 직접 선택한 도구로 스켈레톤을 구성한다.

        tool_configs가 함께 오면 normalize한 tool_id로 매칭하여
        해당 워커에 설정을 주입한다.
        mcp_* tool_id는 MCP 레지스트리에서 메타를 해석한다(nl-agent-composer FR-08).
        """
        configs_by_id = {
            normalize_tool_id(k): v for k, v in (tool_configs or {}).items()
        }
        workers: list[WorkerDefinition] = []
        seen: set[str] = set()
        for raw_id in tool_ids:
            tool_id = normalize_tool_id(raw_id)
            # 완전히 동일한 tool_id만 중복 제거 (서버가 같아도 도구가 다르면 별개)
            if tool_id in seen:
                continue
            seen.add(tool_id)
            config = configs_by_id.get(tool_id)
            workers.append(WorkerDefinition(
                tool_id=tool_id,
                worker_id=make_worker_id(tool_id),
                description=await self._resolve_description(tool_id, request_id),
                sort_order=len(workers),
                tool_config=config.model_dump() if config else None,
            ))
        self._logger.info(
            "Built skeleton from tool_ids",
            request_id=request_id,
            tool_ids=[w.tool_id for w in workers],
        )
        return WorkflowSkeleton(workers=workers, flow_hint=_flow_hint(workers))

    async def build_builtin_workers(
        self,
        existing_workers: list[WorkerDefinition],
        exclude_tool_ids: list[str] | None,
        request_id: str,
    ) -> list[WorkerDefinition]:
        """builtin-tools D5: 빌트인 도구(is_builtin AND is_active)를 워커로 주입.

        수동 opt-out(exclude_builtin_tool_ids)만 제외하며, 사용자 선택 도구와
        정규화 ID 기준으로 중복 주입하지 않는다.
        """
        if self._tool_catalog_repo is None:
            return []
        entries = await self._tool_catalog_repo.list_builtin(request_id)
        exclude = {normalize_tool_id(x) for x in (exclude_tool_ids or [])}
        seen = {w.tool_id for w in existing_workers if w.worker_type == "tool"}
        workers: list[WorkerDefinition] = []
        for entry in entries:
            storage_id = normalize_tool_id(entry.tool_id)
            if storage_id in exclude or storage_id in seen:
                continue
            description = await self._resolve_builtin_description(
                storage_id, request_id
            )
            if description is None:
                continue
            seen.add(storage_id)
            workers.append(WorkerDefinition(
                tool_id=storage_id,
                worker_id=make_worker_id(storage_id),
                description=description,
                sort_order=len(existing_workers) + len(workers),
            ))
        if workers:
            self._logger.info(
                "Builtin tools injected",
                request_id=request_id,
                tool_ids=[w.tool_id for w in workers],
            )
        return workers

    async def _resolve_description(self, tool_id: str, request_id: str) -> str:
        if parse_mcp_tool_id(tool_id) is not None:
            return await self._resolve_mcp_description(tool_id, request_id)
        return get_tool_meta(tool_id).description

    async def _resolve_builtin_description(
        self, storage_id: str, request_id: str
    ) -> str | None:
        """빌트인 도구 설명 해석 — 실패 시 None 반환으로 해당 도구만 제외.

        FR-07: MCP 서버 비활성/미등록·레지스트리 이탈 잔재가 에이전트 생성을
        실패시키면 안 된다 (경고 로그 후 격하).
        """
        try:
            return await self._resolve_description(storage_id, request_id)
        except ValueError as e:
            self._logger.warning(
                "Builtin tool skipped",
                request_id=request_id, tool_id=storage_id, exception=e,
            )
            return None

    async def _resolve_mcp_description(
        self, tool_id: str, request_id: str
    ) -> str:
        """MCP 워커 설명을 해석한다.

        개별 도구(`mcp:{srv}:{tool}`)는 카탈로그 설명이 가장 구체적이므로
        우선 쓰고, 카탈로그에 없으면 서버 등록정보로 폴백한다.
        서버 활성 여부는 두 경우 모두 레지스트리로 검증한다.
        """
        ref = parse_mcp_tool_id(tool_id)
        if ref is None or self._mcp_server_repo is None:
            raise ValueError(f"Unknown tool_id: {tool_id!r}")

        reg = await self._mcp_server_repo.find_by_id(ref.server_id, request_id)
        if reg is None or not reg.is_active:
            raise ValueError(
                f"등록되지 않았거나 비활성화된 MCP 도구입니다: {tool_id}"
            )

        if not ref.is_server_level:
            entry = await self._find_catalog_entry(tool_id, request_id)
            if entry is not None and entry.description:
                return entry.description
            return f"{reg.description or reg.name} - {ref.tool_name}"
        return reg.description or reg.name

    async def _find_catalog_entry(self, tool_id: str, request_id: str):
        """카탈로그 조회 실패가 에이전트 생성을 막아선 안 된다."""
        if self._tool_catalog_repo is None:
            return None
        try:
            return await self._tool_catalog_repo.find_by_tool_id(
                tool_id, request_id
            )
        except Exception as e:
            self._logger.warning(
                "Tool catalog lookup failed — falling back to server meta",
                request_id=request_id, tool_id=tool_id, exception=e,
            )
            return None


def _flow_hint(workers: list[WorkerDefinition]) -> str:
    return " → ".join(w.tool_id for w in workers)
