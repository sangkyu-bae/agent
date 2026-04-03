"""ToolSelector: LLM 구조화 출력으로 사용자 요청 → 도구 자동 선택."""
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowSkeleton
from src.domain.agent_builder.tool_registry import TOOL_REGISTRY
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class _WorkerOutput(BaseModel):
    """LLM Structured Output 스키마."""
    tool_id: str = Field(description="TOOL_REGISTRY에 있는 tool_id만 선택")
    worker_id: str = Field(description="snake_case 워커 이름 e.g. search_worker")
    description: str = Field(description="이 워커가 담당하는 역할")
    sort_order: int = Field(description="실행 순서 (0부터 시작)")


class _SkeletonOutput(BaseModel):
    workers: list[_WorkerOutput]
    flow_hint: str = Field(description="워커 실행 순서 설명 (1~2 문장)")


class ToolSelector:
    """LLM Step1: 사용자 요청 분석 → 필요한 도구 선택 + 플로우 결정."""

    _SYSTEM_PROMPT = """\
당신은 AI 에이전트 설계 전문가입니다.
사용자의 요청을 분석하여 적합한 도구(tool)를 선택하고 실행 플로우를 설계하세요.

[사용 가능한 도구 목록]
{tool_list}

[규칙]
- 위 목록에 있는 tool_id만 선택하세요.
- 불필요한 도구는 포함하지 마세요.
- worker_id는 snake_case로 작성하세요 (e.g. search_worker, export_worker).
- sort_order는 0부터 시작하는 정수입니다.
"""

    def __init__(self, llm: ChatOpenAI, logger: LoggerInterface) -> None:
        self._llm = llm.with_structured_output(_SkeletonOutput)
        self._logger = logger

    async def select(self, user_request: str, request_id: str) -> WorkflowSkeleton:
        """사용자 요청 → WorkflowSkeleton (도구 목록 + 플로우 힌트)."""
        self._logger.info("ToolSelector start", request_id=request_id)
        try:
            tool_list = "\n".join(
                f"- {meta.tool_id}: {meta.description}"
                for meta in TOOL_REGISTRY.values()
            )
            system = self._SYSTEM_PROMPT.format(tool_list=tool_list)
            output: _SkeletonOutput = await self._llm.ainvoke([
                {"role": "system", "content": system},
                {"role": "user", "content": user_request},
            ])
            workers = [
                WorkerDefinition(
                    tool_id=w.tool_id,
                    worker_id=w.worker_id,
                    description=w.description,
                    sort_order=w.sort_order,
                )
                for w in output.workers
            ]
            self._logger.info(
                "ToolSelector done",
                request_id=request_id,
                tool_ids=[w.tool_id for w in workers],
            )
            return WorkflowSkeleton(workers=workers, flow_hint=output.flow_hint)
        except Exception as e:
            self._logger.error("ToolSelector failed", exception=e, request_id=request_id)
            raise
