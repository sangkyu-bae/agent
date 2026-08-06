"""AgentPlanner: 요구 분석 → 빌드 계획 + 보충 질문 (fix-agent-planner-hitl).

Planner→Composer 2단계 파이프라인의 앞단. 요청을 분석해 BuildPlan을 세우고,
초안 품질을 실질적으로 바꿀 정보가 부족하면 구조화 질문을 산출한다(HITL).
도구는 방향 힌트만 제시하며(D5) 최종 선택·검증은 Composer와 서버 보정이 담당한다.
PlannerInterface(application/agent_composer/interfaces.py) 구현체 — DI 교체 지점.
"""
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.application.agent_composer.composer import build_candidates_block
from src.application.agent_composer.interfaces import PlanResult
from src.application.agent_composer.schemas import ComposeCurrentConfig
from src.domain.agent_composer.policies import PlannerPolicy
from src.domain.agent_composer.schemas import (
    BuildPlan,
    CandidateTool,
    ClarificationAnswer,
    ClarifyingQuestion,
    ToolDirectionHint,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.langsmith.langsmith import make_composer_tracer

_RUN_NAME_PREVIEW_LEN = 30


class _ToolHintOutput(BaseModel):
    capability: str = Field(description="요청에서 분해한 단위 역량")
    suggested_tool_ids: list[str] = Field(
        default_factory=list,
        description="이 역량에 어울리는 후보 tool_id (방향 힌트, 확정 아님)",
    )
    note: str = Field("", description="힌트 부연 (선택)")


class _QuestionOutput(BaseModel):
    question: str = Field(description="사용자에게 물을 질문 (한국어 한 문장)")
    options: list[str] = Field(
        default_factory=list, description="선택지 2~4개. 없으면 빈 배열"
    )
    allow_free_text: bool = Field(True, description="자유 입력 허용 여부")


class _PlanOutput(BaseModel):
    requirement_summary: str = Field(description="요구 재정리 (한국어 1~2문장)")
    tool_hints: list[_ToolHintOutput]
    plan_summary: str = Field(
        description="사용자에게 노출할 계획 요약 (한국어 1~3문장)"
    )
    confidence: float = Field(description="계획 확신도 0.0~1.0")
    clarifying_questions: list[_QuestionOutput] = Field(default_factory=list)


class AgentPlanner:
    """LLM 1회 호출로 빌드 계획과 보충 질문을 산출한다."""

    _SYSTEM_PROMPT = """\
당신은 AI 에이전트 빌드 플래너입니다. 사용자의 요청을 분석해 에이전트 구성 계획을
세우고, 계획을 확정하기에 정보가 부족하면 사용자에게 물을 질문을 만드세요.

[후보 도구]
{candidates_block}

[계획 규칙]
- 요청을 단위 역량으로 분해하고, 각 역량에 어울리는 후보 tool_id를 방향 힌트로
  제시하세요. 힌트는 확정이 아니며 후보 목록에 없는 도구를 지어내지 마세요.
- plan_summary는 사용자에게 그대로 노출됩니다 — 한국어 1~3문장으로 쓰세요.
- confidence는 이 계획만으로 좋은 초안을 만들 수 있는 확신도입니다.

[질문 규칙]
- 초안 품질을 실질적으로 바꿀 정보만 질문하세요. 사소한 것은 합리적으로 가정하세요.
- 질문은 최대 {max_questions}개, 각 질문에 가능하면 선택지 2~4개를 제시하세요.
- confidence가 {threshold} 이상이면 clarifying_questions를 빈 배열로 두세요.
- [이전 질문과 답변]에서 "무응답"인 질문은 다시 묻지 말고 합리적 기본값으로
  가정한 뒤 계획에 반영하세요.
"""

    # edit 모드: 기존 구성 유지 전제 (Composer 증분 수정 규칙과 동일 취지)
    _CURRENT_CONFIG_BLOCK = """
[현재 에이전트 설정]
- 이름: {name}
- 사용 중 도구: {tools}
- 시스템 프롬프트:
{system_prompt}

[수정 계획 규칙]
- 위 설정은 사용자가 이미 구성한 상태입니다. 기존 구성 유지를 전제로,
  사용자의 요청에서 명시적으로 요구된 변경만 계획하세요.
"""

    def __init__(
        self,
        llm: ChatOpenAI,
        logger: LoggerInterface,
        max_candidates: int = 100,
    ) -> None:
        self._llm = llm.with_structured_output(_PlanOutput)
        self._logger = logger
        self._max_candidates = max_candidates

    async def plan(
        self,
        user_request: str,
        candidates: list[CandidateTool],
        request_id: str,
        current_config: ComposeCurrentConfig | None = None,
        history: list[dict] | None = None,
        answers: list[ClarificationAnswer] | None = None,
        round_: int = 0,
    ) -> PlanResult:
        """요청 (+ 현재 설정/이전 대화/이전 Q&A) → 빌드 계획 structured output."""
        self._logger.info(
            "AgentPlanner start",
            request_id=request_id,
            candidate_count=len(candidates),
            has_current_config=current_config is not None,
            answer_count=len(answers) if answers else 0,
            round=round_,
        )
        try:
            messages = self._build_messages(
                user_request, candidates, request_id, current_config,
                history, answers,
            )
            config = self._build_trace_config(
                user_request, request_id, current_config, round_
            )
            output: _PlanOutput = await self._llm.ainvoke(messages, config=config)
            result = self._to_result(output)
            self._logger.info(
                "AgentPlanner done",
                request_id=request_id,
                confidence=result.plan.confidence,
                question_count=len(result.questions),
            )
            return result
        except Exception as e:
            self._logger.error(
                "AgentPlanner failed", exception=e, request_id=request_id
            )
            raise

    def _build_messages(
        self,
        user_request: str,
        candidates: list[CandidateTool],
        request_id: str,
        current_config: ComposeCurrentConfig | None,
        history: list[dict] | None,
        answers: list[ClarificationAnswer] | None,
    ) -> list[dict]:
        block = build_candidates_block(
            candidates, self._max_candidates, self._logger, request_id
        )
        system = self._SYSTEM_PROMPT.format(
            candidates_block=block,
            max_questions=PlannerPolicy.MAX_QUESTIONS_PER_ROUND,
            threshold=PlannerPolicy.CONFIDENCE_THRESHOLD,
        )
        if current_config is not None:
            system += self._CURRENT_CONFIG_BLOCK.format(
                name=current_config.name or "(미정)",
                tools=", ".join(current_config.tool_ids)
                if current_config.tool_ids
                else "(없음)",
                system_prompt=current_config.system_prompt or "(없음)",
            )
        user_content = user_request
        if answers:
            qa_lines = "\n".join(
                f"Q: {a.question} / A: {a.answer or '무응답'}" for a in answers
            )
            user_content = f"[이전 질문과 답변]\n{qa_lines}\n\n{user_request}"
        messages: list[dict] = [{"role": "system", "content": system}]
        messages += history or []
        messages.append({"role": "user", "content": user_content})
        return messages

    @staticmethod
    def _to_result(output: _PlanOutput) -> PlanResult:
        """structured output → 도메인 VO. 질문 id는 서버가 순번 부여한다."""
        plan = BuildPlan(
            requirement_summary=output.requirement_summary,
            tool_hints=[
                ToolDirectionHint(
                    capability=h.capability,
                    suggested_tool_ids=h.suggested_tool_ids,
                    note=h.note,
                )
                for h in output.tool_hints
            ],
            plan_summary=output.plan_summary,
            confidence=output.confidence,
        )
        questions = [
            ClarifyingQuestion(
                id=f"q{i + 1}",
                question=q.question,
                options=q.options,
                allow_free_text=q.allow_free_text,
            )
            for i, q in enumerate(output.clarifying_questions)
        ]
        # G3: 교체 구현체와 무관하게 질문 상한을 Planner 계약으로 보장
        # (UseCase의 clamp와 중복 적용 — 무해)
        return PlanResult(
            plan=plan, questions=PlannerPolicy.clamp_questions(questions)
        )

    def _build_trace_config(
        self,
        user_request: str,
        request_id: str,
        current_config: ComposeCurrentConfig | None,
        round_: int,
    ) -> dict:
        """LangSmith 추적 config — composer tracer 재사용, run_name `plan:*`."""
        name = (current_config.name or "").strip() if current_config else ""
        if not name:
            name = " ".join(user_request.split())[:_RUN_NAME_PREVIEW_LEN]
        tags = ["agent-composer", "planner"]
        config: dict = {
            "run_name": f"plan:{name}",
            "tags": tags,
            "metadata": {
                "request_id": request_id,
                "has_current_config": current_config is not None,
                "round": round_,
            },
        }
        tracer = make_composer_tracer(tags=tags)
        if tracer is not None:
            config["callbacks"] = [tracer]
        return config
