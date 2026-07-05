"""AgentComposer: 자연어 요청 + 후보 도구(내부/MCP) → 에이전트 초안 LLM 조합.

nl-agent-composer D3: 역량 분해·coverage 근거·도구 선택·flow_hint·system_prompt·
이름 제안을 structured output 1회 호출로 통합. 기존 ToolSelector/PromptGenerator와
독립된 신규 컴포넌트(생성 공통단 미재사용).
"""
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.application.agent_composer.schemas import ComposeCurrentConfig
from src.domain.agent_composer.schemas import CandidateTool
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.langsmith.langsmith import make_composer_tracer

_RUN_NAME_PREVIEW_LEN = 30


class _CapabilityOutput(BaseModel):
    """요청에서 분해한 단위 역량과 매칭 근거."""

    capability: str = Field(description="요청에서 분해한 단위 역량")
    matched_tool_ids: list[str] = Field(
        description="이 역량을 커버하는 후보 tool_id 목록. 커버 불가면 빈 배열"
    )
    reason: str = Field(description="매칭 근거 또는 커버 불가 사유")
    suggestion: str = Field("", description="커버 불가 시 대안(예: 특정 MCP 서버 등록)")


class _WorkerOutput(BaseModel):
    tool_id: str = Field(description="후보 목록에 있는 tool_id 그대로 사용")
    worker_id: str = Field(description="snake_case 워커 이름 e.g. search_worker")
    description: str = Field(description="이 워커가 담당하는 역할")
    sort_order: int = Field(description="실행 순서 (0부터 시작)")
    instruction: str = Field(
        "",
        description=(
            "이 도구의 사용 지침 — 언제 사용하는지, 어떤 입력으로 호출하는지, "
            "주의사항 (한국어 2~4문장, 300자 이내)"
        ),
    )


class _ComposeOutput(BaseModel):
    capabilities: list[_CapabilityOutput]
    workers: list[_WorkerOutput]
    flow_hint: str = Field(description="워커 실행 순서 설명 (1~2 문장)")
    system_prompt: str = Field(
        description="에이전트 시스템 프롬프트 (한국어, 2000자 이내)"
    )
    agent_name: str = Field(description="에이전트 이름 제안 (간결한 한국어)")
    notes: str = Field("", description="조합 근거·대체 선택·주의사항 요약")


class AgentComposer:
    """LLM 1회 호출로 에이전트 초안을 조합한다."""

    _SYSTEM_PROMPT = """\
당신은 AI 에이전트 설계 전문가입니다. 사용자의 요청을 단위 역량(capability)으로
분해하고, 아래 후보 도구만으로 에이전트를 설계하세요.

[후보 도구]
{candidates_block}

[규칙]
- 후보 목록에 있는 tool_id만 workers에 사용하세요. 목록에 없는 도구를 지어내지 마세요.
- 각 역량마다 matched_tool_ids를 반드시 인용하세요. 커버할 후보가 없으면
  matched_tool_ids를 빈 배열로 두고 reason에 사유, suggestion에 대안을 쓰세요.
- workers에는 matched_tool_ids에 인용된 도구만 포함하세요.
- 요청이 후보 도구와 전혀 무관하면 workers를 빈 배열로 두세요.
- 각 worker의 instruction 필드에 해당 도구의 사용 지침을 한국어 2~4문장으로 쓰세요:
  언제 사용하는지, 어떤 입력으로 호출하는지, 주의사항.
- system_prompt는 한국어로 작성하세요:
  1) 에이전트 목적 (1~2문장)
  2) [역할] 섹션: 각 워커의 역할과 언제 사용하는지
  3) [도구 지침] 섹션: 각 도구의 사용 시점·호출 방법·주의사항
     (workers의 instruction과 일관되게)
  4) [동작 원칙] 섹션: 실행 순서, 응답 언어, 주의사항
- worker_id는 snake_case, sort_order는 0부터 시작하는 정수입니다.
"""

    # fix-agent-composer: 증분 수정 시 현재 설정 블록 (current_config 있을 때만 부착)
    _CURRENT_CONFIG_BLOCK = """
[현재 에이전트 설정]
- 이름: {name}
- 사용 중 도구: {tools}
- 시스템 프롬프트:
{system_prompt}

[증분 수정 규칙]
- 위 설정은 사용자가 이미 구성한 상태입니다. 사용자의 요청에서 명시적으로
  요구된 변경만 적용하고, 나머지 설정(도구 구성, 프롬프트의 목적·방향)은 유지하세요.
- 유지할 기존 도구도 workers에 반드시 포함하세요 (누락하면 해제로 처리됩니다).
- system_prompt는 기존 내용을 바탕으로 요청된 변경만 반영해 다시 작성하세요.
"""

    def __init__(
        self,
        llm: ChatOpenAI,
        logger: LoggerInterface,
        max_candidates: int = 100,
    ) -> None:
        self._llm = llm.with_structured_output(_ComposeOutput)
        self._logger = logger
        self._max_candidates = max_candidates

    async def compose(
        self,
        user_request: str,
        candidates: list[CandidateTool],
        request_id: str,
        current_config: ComposeCurrentConfig | None = None,
        history: list[dict] | None = None,
    ) -> _ComposeOutput:
        """자연어 요청 + 후보 도구 (+ 현재 설정/이전 대화) → 초안 structured output.

        history는 호출부(use case)가 ComposePolicy.clamp_history로 절단한
        {role, content} dict 목록이다.
        """
        self._logger.info(
            "AgentComposer start",
            request_id=request_id,
            candidate_count=len(candidates),
            has_current_config=current_config is not None,
            history_turns=len(history) if history else 0,
        )
        try:
            block = self._build_candidates_block(candidates, request_id)
            system = self._SYSTEM_PROMPT.format(candidates_block=block)
            if current_config is not None:
                system += self._build_current_config_block(current_config)
            messages: list[dict] = [{"role": "system", "content": system}]
            messages += history or []
            messages.append({"role": "user", "content": user_request})
            config = self._build_trace_config(
                user_request, request_id, current_config
            )
            output: _ComposeOutput = await self._llm.ainvoke(
                messages, config=config
            )
            self._logger.info(
                "AgentComposer done",
                request_id=request_id,
                agent_name=output.agent_name,
                worker_count=len(output.workers),
                capability_count=len(output.capabilities),
            )
            return output
        except Exception as e:
            self._logger.error(
                "AgentComposer failed", exception=e, request_id=request_id
            )
            raise

    def _build_trace_config(
        self,
        user_request: str,
        request_id: str,
        current_config: ComposeCurrentConfig | None,
    ) -> dict:
        """LangSmith 추적 config — 프로젝트 'agent-composer'에 이름으로 추적.

        run_name: 수정 요청이면 기존 에이전트명, 신규면 요청 앞부분 프리뷰.
        tracer가 None(API 키 없음)이면 callbacks 미설정 — 본 흐름 영향 없음.
        """
        name = (current_config.name or "").strip() if current_config else ""
        if not name:
            name = " ".join(user_request.split())[:_RUN_NAME_PREVIEW_LEN]
        tags = ["agent-composer"]
        config: dict = {
            "run_name": f"compose:{name}",
            "tags": tags,
            "metadata": {
                "request_id": request_id,
                "has_current_config": current_config is not None,
            },
        }
        tracer = make_composer_tracer(tags=tags)
        if tracer is not None:
            config["callbacks"] = [tracer]
        return config

    def _build_current_config_block(self, config: ComposeCurrentConfig) -> str:
        """현재 폼 스냅샷을 증분 수정 컨텍스트 블록으로 변환."""
        return self._CURRENT_CONFIG_BLOCK.format(
            name=config.name or "(미정)",
            tools=", ".join(config.tool_ids) if config.tool_ids else "(없음)",
            system_prompt=config.system_prompt or "(없음)",
        )

    def _build_candidates_block(
        self, candidates: list[CandidateTool], request_id: str
    ) -> str:
        """후보 도구를 프롬프트 라인으로 변환. 상한 초과분은 절단 + 경고 로그."""
        selected = candidates[: self._max_candidates]
        if len(candidates) > self._max_candidates:
            self._logger.warning(
                "AgentComposer candidates truncated",
                request_id=request_id,
                total=len(candidates),
                max_candidates=self._max_candidates,
            )
        return "\n".join(
            f"- {c.tool_id} ({c.source}): {c.name} — {c.description}"
            for c in selected
        )
