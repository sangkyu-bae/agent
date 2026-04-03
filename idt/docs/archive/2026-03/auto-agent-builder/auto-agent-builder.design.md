# Design: auto-agent-builder

> Feature: 자연어 기반 자동 에이전트 빌더 (AGENT-006)
> Created: 2026-03-24
> Status: Design
> Depends-On: auto-agent-builder.plan.md

---

## 1. 레이어별 파일 구조

```
src/
├── domain/
│   └── auto_agent_builder/
│       ├── __init__.py
│       ├── schemas.py        # AgentSpecResult, AutoBuildSession, ConversationTurn
│       ├── policies.py       # AutoAgentBuilderPolicy
│       └── interfaces.py     # AutoBuildSessionRepositoryInterface
│
├── application/
│   └── auto_agent_builder/
│       ├── __init__.py
│       ├── schemas.py                          # Request/Response Pydantic 모델
│       ├── agent_spec_inference_service.py     # LLM → AgentSpecResult
│       ├── auto_build_use_case.py              # POST /auto 처리
│       └── auto_build_reply_use_case.py        # POST /auto/{session_id}/reply 처리
│
├── infrastructure/
│   └── auto_agent_builder/
│       ├── __init__.py
│       └── auto_build_session_repository.py   # Redis CRUD
│
└── api/
    └── routes/
        └── auto_agent_builder_router.py        # /api/v3/agents/auto
```

---

## 2. Domain Layer

### 2-1. `src/domain/auto_agent_builder/schemas.py`

```python
"""도메인 스키마: AgentSpecResult, AutoBuildSession, ConversationTurn."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ConversationTurn:
    """Q&A 1회 교환 Value Object."""
    questions: list[str]
    answers: list[str]


@dataclass(frozen=True)
class AgentSpecResult:
    """LLM이 추론한 에이전트 명세 Value Object."""
    confidence: float                   # 0.0 ~ 1.0
    tool_ids: list[str]                 # tool_registry 키 목록
    middleware_configs: list[dict]      # [{"type": "...", "config": {...}}]
    system_prompt: str                  # LLM 자동 생성 시스템 프롬프트
    clarifying_questions: list[str]     # 비어있으면 바로 생성 가능
    reasoning: str                      # 선택 이유


@dataclass
class AutoBuildSession:
    """자동 에이전트 빌드 세션 (Redis 저장)."""
    session_id: str
    user_id: str
    user_request: str
    model_name: str
    conversation_turns: list[ConversationTurn] = field(default_factory=list)
    attempt_count: int = 0
    status: str = "pending"             # "pending" | "created" | "failed"
    created_agent_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=datetime.utcnow)

    def add_answers(self, answers: list[str]) -> None:
        """마지막 턴에 사용자 답변을 기록."""
        if not self.conversation_turns:
            return
        last = self.conversation_turns[-1]
        self.conversation_turns[-1] = ConversationTurn(
            questions=last.questions,
            answers=answers,
        )

    def add_questions(self, questions: list[str]) -> None:
        """새 질문 턴을 추가."""
        self.conversation_turns.append(
            ConversationTurn(questions=questions, answers=[])
        )

    def build_context(self) -> str:
        """추론 프롬프트용 대화 이력 문자열 반환."""
        lines = []
        for i, turn in enumerate(self.conversation_turns, 1):
            for q, a in zip(turn.questions, turn.answers):
                lines.append(f"[Round {i}] Q: {q}")
                lines.append(f"[Round {i}] A: {a}")
        return "\n".join(lines)
```

---

### 2-2. `src/domain/auto_agent_builder/policies.py`

```python
"""AutoAgentBuilderPolicy: 자동 빌드 정책 상수 및 검증."""
from src.domain.auto_agent_builder.schemas import AgentSpecResult, AutoBuildSession


class AutoAgentBuilderPolicy:
    CONFIDENCE_THRESHOLD: float = 0.8
    MAX_ATTEMPTS: int = 3
    SESSION_TTL_SECONDS: int = 86400    # 24시간
    MAX_QUESTIONS_PER_TURN: int = 3

    @classmethod
    def is_confident_enough(cls, result: AgentSpecResult) -> bool:
        """확신도 ≥ 0.8 AND 추가 질문 없음."""
        return result.confidence >= cls.CONFIDENCE_THRESHOLD and not result.clarifying_questions

    @classmethod
    def should_force_create(cls, session: AutoBuildSession) -> bool:
        """최대 시도 횟수 도달 → best_effort 강제 생성."""
        return session.attempt_count >= cls.MAX_ATTEMPTS

    @classmethod
    def validate_tool_ids(cls, tool_ids: list[str], available_ids: set[str]) -> None:
        """tool_id가 tool_registry에 존재하는지 검증."""
        unknown = set(tool_ids) - available_ids
        if unknown:
            raise ValueError(f"Unknown tool_ids from LLM response: {unknown}")
```

---

### 2-3. `src/domain/auto_agent_builder/interfaces.py`

```python
"""AutoBuildSessionRepositoryInterface."""
from abc import ABC, abstractmethod
from src.domain.auto_agent_builder.schemas import AutoBuildSession


class AutoBuildSessionRepositoryInterface(ABC):

    @abstractmethod
    async def save(self, session: AutoBuildSession) -> None:
        ...

    @abstractmethod
    async def find(self, session_id: str) -> AutoBuildSession | None:
        ...

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        ...
```

---

## 3. Application Layer

### 3-1. `src/application/auto_agent_builder/schemas.py`

```python
"""Request / Response Pydantic 모델."""
from typing import Literal
from pydantic import BaseModel


class AutoBuildRequest(BaseModel):
    user_request: str
    user_id: str
    model_name: str = "gpt-4o"
    name: str | None = None             # None이면 LLM 자동 생성
    request_id: str


class AutoBuildReplyRequest(BaseModel):
    answers: list[str]
    request_id: str


class AutoBuildResponse(BaseModel):
    status: Literal["created", "needs_clarification", "failed"]
    session_id: str
    agent_id: str | None = None
    explanation: str | None = None
    tool_ids: list[str] | None = None
    middlewares_applied: list[str] | None = None
    questions: list[str] | None = None
    partial_info: str | None = None


class AutoBuildSessionStatusResponse(BaseModel):
    session_id: str
    status: str
    attempt_count: int
    user_request: str
    created_agent_id: str | None
```

---

### 3-2. `src/application/auto_agent_builder/agent_spec_inference_service.py`

```python
"""AgentSpecInferenceService: LLM으로 에이전트 명세 자동 추론."""
import json
from langchain_openai import ChatOpenAI

from src.domain.auto_agent_builder.schemas import AgentSpecResult, ConversationTurn
from src.domain.auto_agent_builder.policies import AutoAgentBuilderPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_SYSTEM_PROMPT = """You are an expert at configuring AI agent pipelines.
Given a user's task description and available tools/middlewares,
determine the optimal agent configuration. Respond ONLY in valid JSON."""

_TOOL_DESCRIPTIONS = """Available tools:
- internal_document_search: 내부 벡터/ES 하이브리드 검색 (정책/지식베이스 질의)
- tavily_search: Tavily 웹 검색 (최신 외부 정보, 뉴스)
- excel_export: pandas Excel 파일 생성 (데이터 정리/보고서)
- python_code_executor: Python 코드 샌드박스 실행 (계산/데이터 처리)"""

_MIDDLEWARE_DESCRIPTIONS = """Available middlewares:
- summarization: 긴 대화 컨텍스트 자동 압축
- pii: 개인정보(이메일/신용카드) 자동 마스킹
- tool_retry: 실패 도구 자동 재시도
- model_call_limit: LLM 호출 횟수 제한 (비용 제어)
- model_fallback: 주 모델 실패 시 대체 모델 전환"""

_RESPONSE_FORMAT = """\nRespond in JSON:
{
  "confidence": 0.0-1.0,
  "tool_ids": ["..."],
  "middlewares": [{"type": "...", "config": {...}}],
  "system_prompt": "...",
  "clarifying_questions": [],
  "reasoning": "..."
}
Note: clarifying_questions must be empty if confidence >= 0.8."""


class AgentSpecInferenceService:

    def __init__(self, model_name: str, logger: LoggerInterface) -> None:
        self._model_name = model_name
        self._logger = logger

    async def infer(
        self,
        user_request: str,
        conversation_history: list[ConversationTurn],
        request_id: str,
        model_name: str | None = None,
    ) -> AgentSpecResult:
        self._logger.info(
            "AgentSpecInferenceService infer start",
            request_id=request_id,
            user_request=user_request[:100],
        )
        try:
            llm = ChatOpenAI(model=model_name or self._model_name, temperature=0)
            messages = self._build_messages(user_request, conversation_history)
            raw = await llm.ainvoke(messages)
            result = self._parse_response(raw.content, request_id)
            self._logger.info(
                "AgentSpecInferenceService infer done",
                request_id=request_id,
                confidence=result.confidence,
                tool_ids=result.tool_ids,
            )
            return result
        except Exception as e:
            self._logger.error(
                "AgentSpecInferenceService infer failed",
                exception=e,
                request_id=request_id,
            )
            raise

    def _build_messages(
        self,
        user_request: str,
        conversation_history: list[ConversationTurn],
    ) -> list[dict]:
        user_content = (
            f"{_TOOL_DESCRIPTIONS}\n\n"
            f"{_MIDDLEWARE_DESCRIPTIONS}\n\n"
            f"User request: {user_request!r}"
        )
        if conversation_history:
            history_lines = []
            for i, turn in enumerate(conversation_history, 1):
                for q, a in zip(turn.questions, turn.answers):
                    history_lines.append(f"[Round {i}] Q: {q}")
                    history_lines.append(f"[Round {i}] A: {a}")
            user_content += "\n\nAdditional context:\n" + "\n".join(history_lines)
        user_content += _RESPONSE_FORMAT
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _parse_response(self, content: str, request_id: str) -> AgentSpecResult:
        """LLM JSON 응답 파싱. 실패 시 ValueError."""
        try:
            # JSON 블록 추출 (```json ... ``` 감싸인 경우 대응)
            text = content.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
        except (json.JSONDecodeError, IndexError) as e:
            self._logger.warning(
                "AgentSpecInferenceService JSON parse failed",
                request_id=request_id,
                raw=content[:200],
            )
            raise ValueError(f"LLM response is not valid JSON: {e}") from e

        return AgentSpecResult(
            confidence=float(data.get("confidence", 0.0)),
            tool_ids=data.get("tool_ids", []),
            middleware_configs=data.get("middlewares", []),
            system_prompt=data.get("system_prompt", ""),
            clarifying_questions=data.get("clarifying_questions", []),
            reasoning=data.get("reasoning", ""),
        )
```

---

### 3-3. `src/application/auto_agent_builder/auto_build_use_case.py`

```python
"""AutoBuildUseCase: 자연어 요청 → 에이전트 자동 빌드 시작."""
import uuid
from datetime import datetime, timedelta

from src.application.auto_agent_builder.agent_spec_inference_service import AgentSpecInferenceService
from src.application.auto_agent_builder.schemas import AutoBuildRequest, AutoBuildResponse
from src.domain.agent_builder.tool_registry import get_all_tools  # AGENT-004 재사용
from src.domain.auto_agent_builder.interfaces import AutoBuildSessionRepositoryInterface
from src.domain.auto_agent_builder.policies import AutoAgentBuilderPolicy
from src.domain.auto_agent_builder.schemas import AutoBuildSession, ConversationTurn
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class AutoBuildUseCase:

    def __init__(
        self,
        inference_service: AgentSpecInferenceService,
        session_repository: AutoBuildSessionRepositoryInterface,
        create_agent_use_case,   # duck typing: CreateMiddlewareAgentUseCase (AGENT-005)
        logger: LoggerInterface,
    ) -> None:
        self._inference = inference_service
        self._session_repo = session_repository
        self._create_agent = create_agent_use_case
        self._logger = logger

    async def execute(self, request: AutoBuildRequest) -> AutoBuildResponse:
        self._logger.info(
            "AutoBuildUseCase start",
            request_id=request.request_id,
            user_id=request.user_id,
        )
        try:
            # 1. tool_id 검증용 가용 도구 목록
            available_ids = {t.tool_id for t in get_all_tools()}

            # 2. LLM 추론
            spec = await self._inference.infer(
                request.user_request, [], request.request_id, request.model_name
            )

            # 3. tool_id 검증
            AutoAgentBuilderPolicy.validate_tool_ids(spec.tool_ids, available_ids)

            session_id = str(uuid.uuid4())
            now = datetime.utcnow()
            expires = now + timedelta(seconds=AutoAgentBuilderPolicy.SESSION_TTL_SECONDS)

            # 4. 확신도 충분 → 바로 생성
            if AutoAgentBuilderPolicy.is_confident_enough(spec):
                return await self._create_and_respond(spec, request, session_id, now, expires)

            # 5. 보충 질문 필요 → 세션 저장
            session = AutoBuildSession(
                session_id=session_id,
                user_id=request.user_id,
                user_request=request.user_request,
                model_name=request.model_name,
                conversation_turns=[
                    ConversationTurn(questions=spec.clarifying_questions, answers=[])
                ],
                attempt_count=1,
                status="pending",
                created_at=now,
                expires_at=expires,
            )
            await self._session_repo.save(session)

            self._logger.info(
                "AutoBuildUseCase needs_clarification",
                request_id=request.request_id,
                session_id=session_id,
                questions_count=len(spec.clarifying_questions),
            )
            return AutoBuildResponse(
                status="needs_clarification",
                session_id=session_id,
                questions=spec.clarifying_questions,
                partial_info=spec.reasoning,
            )

        except Exception as e:
            self._logger.error(
                "AutoBuildUseCase failed",
                exception=e,
                request_id=request.request_id,
            )
            raise

    async def _create_and_respond(
        self, spec, request, session_id: str, now: datetime, expires: datetime
    ) -> AutoBuildResponse:
        """확신도 충분 → CreateMiddlewareAgentUseCase 호출 → 세션 저장."""
        from src.application.middleware_agent.schemas import (  # AGENT-005 재사용
            CreateMiddlewareAgentRequest,
            MiddlewareConfigRequest,
        )
        create_request = CreateMiddlewareAgentRequest(
            user_id=request.user_id,
            name=request.name or f"auto-{spec.tool_ids[0]}",
            description=f"자동 생성: {request.user_request[:100]}",
            system_prompt=spec.system_prompt,
            model_name=request.model_name,
            tool_ids=spec.tool_ids,
            middleware=[
                MiddlewareConfigRequest(
                    type=m["type"],
                    config=m.get("config", {}),
                    sort_order=i,
                )
                for i, m in enumerate(spec.middleware_configs)
            ],
            request_id=request.request_id,
        )
        created = await self._create_agent.execute(create_request)

        session = AutoBuildSession(
            session_id=session_id,
            user_id=request.user_id,
            user_request=request.user_request,
            model_name=request.model_name,
            attempt_count=1,
            status="created",
            created_agent_id=created.agent_id,
            created_at=now,
            expires_at=expires,
        )
        await self._session_repo.save(session)

        return AutoBuildResponse(
            status="created",
            session_id=session_id,
            agent_id=created.agent_id,
            explanation=spec.reasoning,
            tool_ids=spec.tool_ids,
            middlewares_applied=[m["type"] for m in spec.middleware_configs],
        )
```

---

### 3-4. `src/application/auto_agent_builder/auto_build_reply_use_case.py`

```python
"""AutoBuildReplyUseCase: 보충 답변 수신 → 재추론 → 에이전트 생성."""
from src.application.auto_agent_builder.agent_spec_inference_service import AgentSpecInferenceService
from src.application.auto_agent_builder.schemas import AutoBuildReplyRequest, AutoBuildResponse
from src.domain.agent_builder.tool_registry import get_all_tools
from src.domain.auto_agent_builder.interfaces import AutoBuildSessionRepositoryInterface
from src.domain.auto_agent_builder.policies import AutoAgentBuilderPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class AutoBuildReplyUseCase:

    def __init__(
        self,
        inference_service: AgentSpecInferenceService,
        session_repository: AutoBuildSessionRepositoryInterface,
        create_agent_use_case,
        logger: LoggerInterface,
    ) -> None:
        self._inference = inference_service
        self._session_repo = session_repository
        self._create_agent = create_agent_use_case
        self._logger = logger

    async def execute(
        self, session_id: str, request: AutoBuildReplyRequest
    ) -> AutoBuildResponse:
        self._logger.info(
            "AutoBuildReplyUseCase start",
            request_id=request.request_id,
            session_id=session_id,
        )
        try:
            # 1. 세션 로드
            session = await self._session_repo.find(session_id)
            if session is None:
                raise ValueError(f"Session not found: {session_id}")

            # 2. 답변 기록
            session.add_answers(request.answers)
            session.attempt_count += 1

            available_ids = {t.tool_id for t in get_all_tools()}

            # 3. 최대 시도 → 강제 생성 (best_effort)
            if AutoAgentBuilderPolicy.should_force_create(session):
                self._logger.info(
                    "AutoBuildReplyUseCase force_create",
                    request_id=request.request_id,
                    session_id=session_id,
                )
                spec = await self._inference.infer(
                    session.user_request,
                    session.conversation_turns,
                    request.request_id,
                    session.model_name,
                )
                AutoAgentBuilderPolicy.validate_tool_ids(spec.tool_ids, available_ids)
                # force_spec: clarifying_questions 무시하고 바로 생성
                from dataclasses import replace
                forced = replace(spec, clarifying_questions=[])
                return await self._do_create(forced, session, request.request_id)

            # 4. 재추론
            spec = await self._inference.infer(
                session.user_request,
                session.conversation_turns,
                request.request_id,
                session.model_name,
            )
            AutoAgentBuilderPolicy.validate_tool_ids(spec.tool_ids, available_ids)

            if AutoAgentBuilderPolicy.is_confident_enough(spec):
                return await self._do_create(spec, session, request.request_id)

            # 5. 아직 불확실 → 새 질문
            session.add_questions(spec.clarifying_questions)
            await self._session_repo.save(session)

            self._logger.info(
                "AutoBuildReplyUseCase needs_clarification again",
                request_id=request.request_id,
                session_id=session_id,
            )
            return AutoBuildResponse(
                status="needs_clarification",
                session_id=session_id,
                questions=spec.clarifying_questions,
                partial_info=spec.reasoning,
            )

        except Exception as e:
            self._logger.error(
                "AutoBuildReplyUseCase failed",
                exception=e,
                request_id=request.request_id,
                session_id=session_id,
            )
            raise

    async def _do_create(self, spec, session, request_id: str) -> AutoBuildResponse:
        from src.application.middleware_agent.schemas import (
            CreateMiddlewareAgentRequest,
            MiddlewareConfigRequest,
        )
        create_request = CreateMiddlewareAgentRequest(
            user_id=session.user_id,
            name=f"auto-{spec.tool_ids[0] if spec.tool_ids else 'agent'}",
            description=f"자동 생성: {session.user_request[:100]}",
            system_prompt=spec.system_prompt,
            model_name=session.model_name,
            tool_ids=spec.tool_ids,
            middleware=[
                MiddlewareConfigRequest(type=m["type"], config=m.get("config", {}), sort_order=i)
                for i, m in enumerate(spec.middleware_configs)
            ],
            request_id=request_id,
        )
        created = await self._create_agent.execute(create_request)
        session.status = "created"
        session.created_agent_id = created.agent_id
        await self._session_repo.save(session)

        self._logger.info(
            "AutoBuildReplyUseCase created",
            request_id=request_id,
            session_id=session.session_id,
            agent_id=created.agent_id,
        )
        return AutoBuildResponse(
            status="created",
            session_id=session.session_id,
            agent_id=created.agent_id,
            explanation=spec.reasoning,
            tool_ids=spec.tool_ids,
            middlewares_applied=[m["type"] for m in spec.middleware_configs],
        )
```

---

## 4. Infrastructure Layer

### `src/infrastructure/auto_agent_builder/auto_build_session_repository.py`

```python
"""AutoBuildSessionRepository: Redis CRUD."""
import json
from datetime import datetime

from src.domain.auto_agent_builder.interfaces import AutoBuildSessionRepositoryInterface
from src.domain.auto_agent_builder.policies import AutoAgentBuilderPolicy
from src.domain.auto_agent_builder.schemas import AutoBuildSession, ConversationTurn
from src.domain.redis.interfaces import RedisRepositoryInterface


class AutoBuildSessionRepository(AutoBuildSessionRepositoryInterface):
    _KEY_PREFIX = "auto_build_session:"

    def __init__(self, redis: RedisRepositoryInterface) -> None:
        self._redis = redis

    async def save(self, session: AutoBuildSession) -> None:
        key = f"{self._KEY_PREFIX}{session.session_id}"
        value = json.dumps(self._to_dict(session), ensure_ascii=False)
        await self._redis.set(key, value, ttl=AutoAgentBuilderPolicy.SESSION_TTL_SECONDS)

    async def find(self, session_id: str) -> AutoBuildSession | None:
        key = f"{self._KEY_PREFIX}{session_id}"
        value = await self._redis.get(key)
        if value is None:
            return None
        return self._from_dict(json.loads(value))

    async def delete(self, session_id: str) -> None:
        key = f"{self._KEY_PREFIX}{session_id}"
        await self._redis.delete(key)

    @staticmethod
    def _to_dict(session: AutoBuildSession) -> dict:
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "user_request": session.user_request,
            "model_name": session.model_name,
            "conversation_turns": [
                {"questions": t.questions, "answers": t.answers}
                for t in session.conversation_turns
            ],
            "attempt_count": session.attempt_count,
            "status": session.status,
            "created_agent_id": session.created_agent_id,
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
        }

    @staticmethod
    def _from_dict(data: dict) -> AutoBuildSession:
        return AutoBuildSession(
            session_id=data["session_id"],
            user_id=data["user_id"],
            user_request=data["user_request"],
            model_name=data["model_name"],
            conversation_turns=[
                ConversationTurn(questions=t["questions"], answers=t["answers"])
                for t in data.get("conversation_turns", [])
            ],
            attempt_count=data.get("attempt_count", 0),
            status=data.get("status", "pending"),
            created_agent_id=data.get("created_agent_id"),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )
```

---

## 5. API Layer

### `src/api/routes/auto_agent_builder_router.py`

```python
"""자동 에이전트 빌더 라우터 (/api/v3/agents/auto)."""
from fastapi import APIRouter, Depends

from src.application.auto_agent_builder.auto_build_reply_use_case import AutoBuildReplyUseCase
from src.application.auto_agent_builder.auto_build_use_case import AutoBuildUseCase
from src.application.auto_agent_builder.schemas import (
    AutoBuildReplyRequest,
    AutoBuildRequest,
    AutoBuildResponse,
    AutoBuildSessionStatusResponse,
)

router = APIRouter(prefix="/api/v3/agents/auto", tags=["auto-agent-builder"])


# DI placeholders → main.py에서 dependency_overrides로 교체
def get_auto_build_use_case() -> AutoBuildUseCase:
    raise NotImplementedError


def get_auto_build_reply_use_case() -> AutoBuildReplyUseCase:
    raise NotImplementedError


def get_session_repository():
    raise NotImplementedError


@router.post("", response_model=AutoBuildResponse, status_code=202)
async def auto_build(
    request: AutoBuildRequest,
    use_case: AutoBuildUseCase = Depends(get_auto_build_use_case),
):
    """자연어 요청 → 자동 에이전트 빌드 시작."""
    return await use_case.execute(request)


@router.post("/{session_id}/reply", response_model=AutoBuildResponse)
async def auto_build_reply(
    session_id: str,
    request: AutoBuildReplyRequest,
    use_case: AutoBuildReplyUseCase = Depends(get_auto_build_reply_use_case),
):
    """보충 질문 답변 제출 → 재추론 → 에이전트 생성."""
    return await use_case.execute(session_id, request)


@router.get("/{session_id}", response_model=AutoBuildSessionStatusResponse)
async def get_session_status(
    session_id: str,
    session_repo=Depends(get_session_repository),
):
    """빌드 세션 상태 조회."""
    session = await session_repo.find(session_id)
    if session is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return AutoBuildSessionStatusResponse(
        session_id=session.session_id,
        status=session.status,
        attempt_count=session.attempt_count,
        user_request=session.user_request,
        created_agent_id=session.created_agent_id,
    )
```

---

## 6. 실행 흐름 (Sequence)

```
[즉시 생성 경로]
POST /api/v3/agents/auto
  │
  ├─ AutoBuildUseCase.execute()
  │    ├─ AgentSpecInferenceService.infer(user_request, history=[])
  │    │    └─ ChatOpenAI → JSON → AgentSpecResult(confidence=0.9, tool_ids=[...], ...)
  │    │
  │    ├─ validate_tool_ids()          ← tool_registry 키 검증
  │    ├─ is_confident_enough() → True
  │    ├─ CreateMiddlewareAgentUseCase.execute()   ← AGENT-005 재사용
  │    │    └─ MiddlewareAgentRepository.save()    ← MySQL
  │    └─ AutoBuildSessionRepository.save()        ← Redis (status=created)
  │
  └─ AutoBuildResponse(status="created", agent_id=..., explanation=...)

[보충 질문 경로]
POST /api/v3/agents/auto
  │
  ├─ AgentSpecInferenceService.infer() → confidence=0.5
  ├─ is_confident_enough() → False
  ├─ AutoBuildSessionRepository.save()  ← Redis (status=pending, attempt=1)
  └─ AutoBuildResponse(status="needs_clarification", questions=[...])

POST /api/v3/agents/auto/{session_id}/reply
  │
  ├─ AutoBuildReplyUseCase.execute()
  │    ├─ AutoBuildSessionRepository.find()         ← Redis
  │    ├─ session.add_answers(answers)
  │    ├─ AgentSpecInferenceService.infer(enriched_context)
  │    │    └─ confidence=0.88 → is_confident_enough() → True
  │    └─ CreateMiddlewareAgentUseCase.execute()    ← AGENT-005 재사용
  │
  └─ AutoBuildResponse(status="created", agent_id=..., explanation=...)
```

---

## 7. TDD 구현 순서

| # | 테스트 파일 | 구현 파일 |
|---|------------|----------|
| 1 | `tests/domain/auto_agent_builder/test_schemas.py` | `src/domain/auto_agent_builder/schemas.py` |
| 2 | `tests/domain/auto_agent_builder/test_policies.py` | `src/domain/auto_agent_builder/policies.py` |
| 3 | `tests/application/auto_agent_builder/test_agent_spec_inference_service.py` | `agent_spec_inference_service.py` |
| 4 | `tests/infrastructure/auto_agent_builder/test_auto_build_session_repository.py` | `auto_build_session_repository.py` |
| 5 | `tests/application/auto_agent_builder/test_auto_build_use_case.py` | `auto_build_use_case.py` |
| 6 | `tests/application/auto_agent_builder/test_auto_build_reply_use_case.py` | `auto_build_reply_use_case.py` |
| 7 | `tests/api/test_auto_agent_builder_router.py` | `auto_agent_builder_router.py` |

---

## 8. 의존성 설치

```bash
# 기존 의존성으로 충분 (langchain-openai, redis 이미 설치됨)
# 추가 설치 불필요
```

---

## 9. main.py DI 연결 포인트

`src/api/main.py`의 `create_app()` 내부에 다음을 추가:

```python
from src.api.routes.auto_agent_builder_router import (
    router as auto_agent_builder_router,
    get_auto_build_use_case,
    get_auto_build_reply_use_case,
    get_session_repository,
)
# ...
app.include_router(auto_agent_builder_router)
app.dependency_overrides[get_auto_build_use_case] = lambda: AutoBuildUseCase(...)
app.dependency_overrides[get_auto_build_reply_use_case] = lambda: AutoBuildReplyUseCase(...)
app.dependency_overrides[get_session_repository] = lambda: AutoBuildSessionRepository(redis_repo)
```

---

## 10. 아키텍처 제약 확인

| 규칙 | 준수 여부 | 근거 |
|------|----------|------|
| domain → infra 참조 금지 | ✅ | domain/auto_agent_builder/에 외부 의존 없음 |
| LangChain domain 금지 | ✅ | ChatOpenAI는 application/agent_spec_inference_service.py에만 |
| LOG-001 준수 | ✅ | 모든 UseCase/Service에 request_id + exception= 적용 |
| AGENT-004/005 소스 무변경 | ✅ | get_all_tools(), CreateMiddlewareAgentUseCase import만 |
| Redis 직접 접근 금지 (domain) | ✅ | RedisRepositoryInterface 경유 |
| 함수 길이 40줄 이하 | ✅ | 각 메서드 30줄 이내 설계 |
