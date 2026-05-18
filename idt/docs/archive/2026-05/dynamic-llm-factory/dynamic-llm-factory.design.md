# Dynamic LLM Factory Design Document

> **Summary**: LlmModel 엔티티 기반 중앙 LLMFactory를 도입하여 Agent/대화 UseCase의 provider 고정을 제거한다
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-08
> **Status**: Draft
> **Planning Doc**: [dynamic-llm-factory.plan.md](../01-plan/features/dynamic-llm-factory.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. `ChatOpenAI` 직접 생성을 제거하고 `LLMFactory.create(LlmModel)` 단일 진입점으로 통합
2. 기존 `WorkflowCompiler._build_llm()` 로직을 재사용 가능한 독립 클래스로 추출
3. DDD 레이어 규칙 준수: UseCase → `LLMFactoryInterface`(domain) 참조, 구현체는 infrastructure
4. 기존 API 계약 하위 호환성 유지 (breaking change 없음)

### 1.2 Design Principles

- **OCP (Open-Closed Principle)**: 새 provider 추가 시 Factory 한 곳만 수정
- **DIP (Dependency Inversion)**: UseCase는 추상 인터페이스만 의존
- **Single Responsibility**: Factory는 LLM 인스턴스 생성만 담당, 모델 조회는 별도 레이어
- **최소 변경**: 기존 동작을 보존하면서 확장 포인트만 추가

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────┐
│ Interfaces Layer (src/api/)                              │
│                                                          │
│  main.py (DI)                                            │
│    ├─ LLMFactory 싱글톤 생성                              │
│    ├─ LlmModelRepository → find_default() 조회           │
│    └─ UseCase에 factory + default_model 주입              │
│                                                          │
│  routes/general_chat_router.py                           │
│  routes/rag_agent_router.py                              │
└────────────────┬─────────────────────────────────────────┘
                 │ DI 주입
┌────────────────▼─────────────────────────────────────────┐
│ Application Layer (src/application/)                     │
│                                                          │
│  GeneralChatUseCase                                      │
│    └─ self._llm_factory.create(self._llm_model)          │
│  RAGAgentUseCase                                         │
│    └─ self._llm_factory.create(self._llm_model)          │
│  AgentSpecInferenceService                               │
│    └─ self._llm_factory.create(self._llm_model)          │
│  WorkflowCompiler                                        │
│    └─ self._llm_factory.create(llm_model)                │
└────────────────┬─────────────────────────────────────────┘
                 │ 인터페이스 참조
┌────────────────▼─────────────────────────────────────────┐
│ Domain Layer (src/domain/)                               │
│                                                          │
│  llm/interfaces.py                                       │
│    └─ LLMFactoryInterface(ABC)                           │
│         create(llm_model, temperature) → BaseChatModel   │
│                                                          │
│  llm_model/entity.py  (변경 없음)                         │
│    └─ LlmModel(provider, model_name, api_key_env, ...)   │
│  llm_model/interfaces.py  (변경 없음)                     │
│    └─ LlmModelRepositoryInterface                        │
└──────────────────────────────────────────────────────────┘
                 ▲ implements
┌────────────────┴─────────────────────────────────────────┐
│ Infrastructure Layer (src/infrastructure/)               │
│                                                          │
│  llm/llm_factory.py                                      │
│    └─ LLMFactory(LLMFactoryInterface)                    │
│         ├─ "openai"    → ChatOpenAI                      │
│         ├─ "anthropic" → ChatAnthropic                   │
│         └─ "ollama"    → ChatOllama                      │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
API 요청
  → Router (request_id 생성)
  → UseCase.execute()
    → self._llm_factory.create(self._llm_model, temperature=0)
      → LLMFactory: provider 분기
        → "openai":    ChatOpenAI(model=..., api_key=env[api_key_env])
        → "anthropic": ChatAnthropic(model=..., api_key=env[api_key_env])
        → "ollama":    ChatOllama(model=...)
      ← BaseChatModel 반환
    → create_react_agent(llm, tools=...)
    → agent.ainvoke(messages)
  ← Response
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `LLMFactory` | `langchain_openai`, `langchain_anthropic`, `langchain_ollama` | Provider별 LLM 클라이언트 생성 |
| `LLMFactory` | `LLMFactoryInterface` (domain) | 인터페이스 구현 |
| `GeneralChatUseCase` | `LLMFactoryInterface` (domain) | LLM 생성 위임 |
| `RAGAgentUseCase` | `LLMFactoryInterface` (domain) | LLM 생성 위임 |
| `WorkflowCompiler` | `LLMFactoryInterface` (domain) | 기존 `_build_llm` 교체 |
| `AgentSpecInferenceService` | `LLMFactoryInterface` (domain) | LLM 생성 위임 |
| `main.py` (DI) | `LlmModelRepositoryInterface` | 기본 LlmModel 조회 |

---

## 3. Data Model

### 3.1 기존 엔티티 (변경 없음)

```python
# src/domain/llm_model/entity.py — 변경 없음
@dataclass
class LlmModel:
    id: str                  # PK (UUID)
    provider: str            # "openai" | "anthropic" | "ollama"
    model_name: str          # API 호출명 (e.g. "gpt-4o")
    display_name: str        # UI 표시명
    description: str | None
    api_key_env: str         # 환경변수명 (e.g. "OPENAI_API_KEY")
    max_tokens: int | None
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime
```

### 3.2 DB 시드 데이터 (기존 유지)

| provider | model_name | display_name | is_default |
|----------|-----------|--------------|:----------:|
| openai | gpt-4o | GPT-4o | ✅ |
| openai | gpt-4o-mini | GPT-4o Mini | ☐ |
| anthropic | claude-sonnet-4-6 | Claude Sonnet 4.6 | ☐ |

### 3.3 스키마 변경 없음

DB 테이블 `llm_model`, `agent_definition` 변경 없음. 기존 `agent_definition.llm_model_id` FK 관계 그대로 유지.

---

## 4. Interface & Class Specification

### 4.1 LLMFactoryInterface (신규 — Domain Layer)

**파일**: `src/domain/llm/interfaces.py`

```python
from abc import ABC, abstractmethod
from langchain_core.language_models import BaseChatModel
from src.domain.llm_model.entity import LlmModel


class LLMFactoryInterface(ABC):
    """LlmModel 엔티티 기반 LLM 인스턴스 팩토리."""

    @abstractmethod
    def create(
        self,
        llm_model: LlmModel,
        temperature: float = 0.0,
    ) -> BaseChatModel:
        """provider에 맞는 LLM 인스턴스를 생성한다.

        Args:
            llm_model: DB에서 조회한 LlmModel 도메인 엔티티
            temperature: 생성 온도 (0.0~2.0)

        Returns:
            LangChain BaseChatModel 인스턴스

        Raises:
            ValueError: 지원하지 않는 provider
            RuntimeError: API 키 환경변수 미설정
        """
```

> **참고**: `langchain_core`는 LangChain의 핵심 추상 패키지로, domain 레이어에서
> `BaseChatModel` 타입 힌트 참조는 허용한다. (LangChain 자체가 이 프로젝트의 핵심 도메인 도구)

### 4.2 LLMFactory (신규 — Infrastructure Layer)

**파일**: `src/infrastructure/llm/llm_factory.py`

```python
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel


class LLMFactory(LLMFactoryInterface):
    """provider 분기로 LLM 인스턴스를 생성하는 팩토리."""

    def create(
        self,
        llm_model: LlmModel,
        temperature: float = 0.0,
    ) -> BaseChatModel:
        provider = llm_model.provider
        if provider == "openai":
            return self._create_openai(llm_model, temperature)
        if provider == "anthropic":
            return self._create_anthropic(llm_model, temperature)
        if provider == "ollama":
            return self._create_ollama(llm_model, temperature)
        raise ValueError(f"지원하지 않는 provider: {provider}")

    def _create_openai(
        self, llm_model: LlmModel, temperature: float
    ) -> ChatOpenAI:
        api_key = self._resolve_api_key(llm_model)
        return ChatOpenAI(
            model=llm_model.model_name,
            api_key=api_key,
            temperature=temperature,
        )

    def _create_anthropic(
        self, llm_model: LlmModel, temperature: float
    ) -> ChatAnthropic:
        api_key = self._resolve_api_key(llm_model)
        return ChatAnthropic(
            model=llm_model.model_name,
            api_key=api_key,
            temperature=temperature,
        )

    def _create_ollama(
        self, llm_model: LlmModel, temperature: float
    ) -> ChatOllama:
        return ChatOllama(
            model=llm_model.model_name,
            temperature=temperature,
        )

    def _resolve_api_key(self, llm_model: LlmModel) -> str:
        api_key = os.environ.get(llm_model.api_key_env, "")
        if not api_key:
            raise RuntimeError(
                f"환경변수 '{llm_model.api_key_env}'가 설정되지 않았습니다. "
                f"provider={llm_model.provider}, model={llm_model.model_name}"
            )
        return api_key
```

### 4.3 UseCase 변경 명세

#### 4.3.1 GeneralChatUseCase

**파일**: `src/application/general_chat/use_case.py`

**Before → After 시그니처:**

```python
# Before
def __init__(
    self, ...,
    openai_api_key: str = "",
    model_name: str = "gpt-4o",
    max_iterations: int = 10,
) -> None:

# After
def __init__(
    self, ...,
    llm_factory: LLMFactoryInterface,
    llm_model: LlmModel,
    max_iterations: int = 10,
) -> None:
```

**`_create_agent` 변경:**

```python
# Before
def _create_agent(self, tools: list):
    llm = ChatOpenAI(
        model=self._model_name,
        api_key=self._api_key or None,
        temperature=0,
    )
    return create_react_agent(llm, tools=tools, prompt=_SYSTEM_PROMPT)

# After
def _create_agent(self, tools: list):
    llm = self._llm_factory.create(self._llm_model, temperature=0)
    return create_react_agent(llm, tools=tools, prompt=_SYSTEM_PROMPT)
```

**제거되는 import:**
```python
# 삭제
from langchain_openai import ChatOpenAI
```

#### 4.3.2 RAGAgentUseCase

**파일**: `src/application/rag_agent/use_case.py`

**Before → After 시그니처:**

```python
# Before
def __init__(
    self,
    hybrid_search_use_case: object,
    openai_api_key: str,
    model_name: str,
    logger: LoggerInterface,
) -> None:

# After
def __init__(
    self,
    hybrid_search_use_case: object,
    llm_factory: LLMFactoryInterface,
    llm_model: LlmModel,
    logger: LoggerInterface,
) -> None:
```

**`execute` 내부 LLM 생성 변경:**

```python
# Before
llm = ChatOpenAI(
    model=self._model_name,
    api_key=self._api_key,
    temperature=0,
)

# After
llm = self._llm_factory.create(self._llm_model, temperature=0)
```

#### 4.3.3 AgentSpecInferenceService

**파일**: `src/application/auto_agent_builder/agent_spec_inference_service.py`

**Before → After 시그니처:**

```python
# Before
def __init__(self, model_name: str, logger: LoggerInterface) -> None:

# After
def __init__(
    self,
    llm_factory: LLMFactoryInterface,
    llm_model: LlmModel,
    logger: LoggerInterface,
) -> None:
```

**`infer` 메서드 변경:**

```python
# Before
llm = ChatOpenAI(model=model_name or self._model_name, temperature=0)

# After
llm = self._llm_factory.create(self._llm_model, temperature=0)
```

> **참고**: 기존 `infer(model_name: str | None)` 파라미터는 제거. 
> LlmModel이 이미 모델명을 포함하므로 중복.

#### 4.3.4 WorkflowCompiler

**파일**: `src/application/agent_builder/workflow_compiler.py`

**Before → After:**

```python
# Before
class WorkflowCompiler:
    def __init__(self, tool_factory: ToolFactory, logger: LoggerInterface) -> None:
        self._tool_factory = tool_factory
        self._logger = logger

    def _build_llm(self, llm_model: LlmModel, temperature: float = 0.0) -> BaseChatModel:
        # ... provider 분기 로직 (69~84줄)

# After
class WorkflowCompiler:
    def __init__(
        self,
        tool_factory: ToolFactory,
        llm_factory: LLMFactoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._tool_factory = tool_factory
        self._llm_factory = llm_factory
        self._logger = logger

    # _build_llm 메서드 제거 → compile()에서 직접 호출
    #   llm = self._build_llm(llm_model, temperature)
    # → llm = self._llm_factory.create(llm_model, temperature)
```

**제거되는 import:**
```python
# 삭제
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
```

### 4.4 DI 변경 (main.py)

```python
# 1. LLMFactory 싱글톤 생성 (앱 시작 시 1회)
_llm_factory = LLMFactory()

# 2. 기본 LlmModel 조회 (startup 이벤트에서)
async def _load_default_llm_model(session: AsyncSession) -> LlmModel:
    repo = LlmModelRepository(session)
    default = await repo.find_default(request_id="startup")
    if default is None:
        raise RuntimeError("기본 LLM 모델이 설정되지 않았습니다. llm_model 시드 데이터를 확인하세요.")
    return default

# 3. GeneralChatUseCase 팩토리 변경
return GeneralChatUseCase(
    ...,
    llm_factory=_llm_factory,
    llm_model=_default_llm_model,   # startup에서 조회한 기본 모델
)

# 4. RAGAgentUseCase 팩토리 변경
return RAGAgentUseCase(
    hybrid_search_use_case=hybrid_search_uc,
    llm_factory=_llm_factory,
    llm_model=_default_llm_model,
    logger=app_logger,
)

# 5. AgentSpecInferenceService 변경
inference_service = AgentSpecInferenceService(
    llm_factory=_llm_factory,
    llm_model=_default_llm_model,
    logger=app_logger,
)

# 6. WorkflowCompiler 변경
compiler = WorkflowCompiler(
    tool_factory=tool_factory,
    llm_factory=_llm_factory,
    logger=app_logger,
)
```

---

## 5. API Specification

### 5.1 API 변경 없음

현재 스코프에서는 API 계약 변경 없음. Agent별 설정은 이미 기존 `CreateAgentRequest.llm_model_id` 필드를 통해 지원됨.

| Endpoint | 변경 | 비고 |
|----------|------|------|
| `POST /api/v1/chat` | 없음 | 내부적으로 DB 기본 모델 사용 |
| `POST /api/v1/rag-agent/query` | 없음 | 내부적으로 DB 기본 모델 사용 |
| `POST /api/v1/agent-builder/create` | 없음 | 기존 `llm_model_id` 유지 |
| `POST /api/v1/agent-builder/run` | 없음 | 기존 agent.llm_model_id FK 유지 |

### 5.2 기존 Agent Builder API 흐름 (변경 없음)

```
POST /api/v1/agent-builder/create
  body: { llm_model_id: "uuid" (optional) }
  → CreateAgentUseCase._resolve_llm_model_id()
    → llm_model_id 있으면 find_by_id, 없으면 find_default
  → AgentDefinition 저장 (llm_model_id FK)

POST /api/v1/agent-builder/run/{agent_id}
  → RunAgentUseCase.execute()
    → agent = repository.find_by_id(agent_id)
    → llm_model = llm_model_repository.find_by_id(agent.llm_model_id)
    → compiler.compile(workflow, llm_model=llm_model)  ← LLMFactory 내부 사용
```

---

## 6. Error Handling

### 6.1 Factory 에러 시나리오

| 에러 | 원인 | 처리 |
|------|------|------|
| `ValueError("지원하지 않는 provider: xxx")` | DB에 잘못된 provider 값 | 로그 + 500 Internal Server Error |
| `RuntimeError("환경변수 'XXX' 미설정")` | API 키 환경변수 누락 | 로그 + 500 (startup 시 검증 권장) |
| `RuntimeError("기본 LLM 모델 미설정")` | DB 시드 누락 | startup 실패 (빠른 실패) |

### 6.2 기존 에러 흐름 유지

UseCase의 `try/except`에서 Factory 에러도 동일하게 잡혀서 기존 `logger.error()` + `raise` 패턴 유지.

---

## 7. Security Considerations

- [x] API 키를 코드에 하드코딩하지 않음 (환경변수 참조)
- [x] `LlmModel.api_key_env`는 환경변수 **이름**만 저장 (실제 키 값은 DB에 없음)
- [x] Factory가 `os.environ.get()`으로 런타임에 키 조회
- [x] API 키 없으면 `RuntimeError` (빈 문자열로 호출하지 않음)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | 파일 |
|------|--------|------|------|
| Unit Test | LLMFactory | pytest + mock | `tests/unit/infrastructure/llm/test_llm_factory.py` |
| Unit Test | GeneralChatUseCase (리팩토링 후) | pytest + mock | 기존 테스트 수정 |
| Unit Test | RAGAgentUseCase (리팩토링 후) | pytest + mock | 기존 테스트 수정 |
| Unit Test | WorkflowCompiler (리팩토링 후) | pytest + mock | 기존 테스트 수정 |
| Unit Test | AgentSpecInferenceService (리팩토링 후) | pytest + mock | 기존 테스트 수정 |

### 8.2 LLMFactory 테스트 케이스

```python
# tests/unit/infrastructure/llm/test_llm_factory.py

class TestLLMFactory:
    """LLMFactory.create() 단위 테스트."""

    # --- Happy Path ---

    def test_create_openai_returns_chat_openai(self):
        """provider="openai" → ChatOpenAI 인스턴스 반환."""
        # Given: openai provider LlmModel + OPENAI_API_KEY 환경변수
        # When: factory.create(model)
        # Then: ChatOpenAI 타입, model_name 일치

    def test_create_anthropic_returns_chat_anthropic(self):
        """provider="anthropic" → ChatAnthropic 인스턴스 반환."""

    def test_create_ollama_returns_chat_ollama(self):
        """provider="ollama" → ChatOllama 인스턴스 반환 (API 키 불필요)."""

    def test_temperature_passed_correctly(self):
        """temperature 파라미터가 LLM 인스턴스에 정확히 전달된다."""

    # --- Error Cases ---

    def test_unsupported_provider_raises_value_error(self):
        """지원하지 않는 provider → ValueError."""

    def test_missing_api_key_raises_runtime_error(self):
        """환경변수 미설정 → RuntimeError (openai/anthropic)."""

    def test_ollama_no_api_key_required(self):
        """ollama는 API 키 없이도 정상 생성."""
```

### 8.3 UseCase 테스트 변경 패턴

기존 `ChatOpenAI` mock 패치를 `LLMFactoryInterface` mock 주입으로 교체:

```python
# Before (기존 테스트)
@patch("src.application.general_chat.use_case.ChatOpenAI")
async def test_execute(self, mock_openai):
    mock_openai.return_value = mock_llm
    use_case = GeneralChatUseCase(..., openai_api_key="key", model_name="gpt-4o")

# After (새 테스트)
async def test_execute(self):
    mock_factory = Mock(spec=LLMFactoryInterface)
    mock_factory.create.return_value = mock_llm
    use_case = GeneralChatUseCase(..., llm_factory=mock_factory, llm_model=fake_model)
```

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Interfaces** | DI 구성, API 라우팅 | `src/api/main.py`, `src/api/routes/` |
| **Application** | UseCase, Workflow 오케스트레이션 | `src/application/` |
| **Domain** | 엔티티, 인터페이스, 순수 규칙 | `src/domain/` |
| **Infrastructure** | LLM 클라이언트 생성, DB 어댑터 | `src/infrastructure/` |

### 9.2 Dependency Rules

```
Interfaces ──→ Application ──→ Domain ←── Infrastructure
                    │                        │
                    └──→ Infrastructure ──────┘
                         (DI 구성에서만)

Rule: Domain 레이어는 Infrastructure를 절대 참조하지 않는다.
```

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `LLMFactoryInterface` | Domain | `src/domain/llm/interfaces.py` (신규) |
| `LLMFactory` | Infrastructure | `src/infrastructure/llm/llm_factory.py` (신규) |
| `GeneralChatUseCase` | Application | `src/application/general_chat/use_case.py` (수정) |
| `RAGAgentUseCase` | Application | `src/application/rag_agent/use_case.py` (수정) |
| `AgentSpecInferenceService` | Application | `src/application/auto_agent_builder/agent_spec_inference_service.py` (수정) |
| `WorkflowCompiler` | Application | `src/application/agent_builder/workflow_compiler.py` (수정) |
| DI 구성 | Interfaces | `src/api/main.py` (수정) |

### 9.4 Import 규칙 검증

| From (소스) | Import (대상) | 허용 여부 |
|------------|--------------|:---------:|
| `application/general_chat/use_case.py` | `domain/llm/interfaces.py` | ✅ |
| `application/general_chat/use_case.py` | `infrastructure/llm/llm_factory.py` | ❌ 금지 |
| `infrastructure/llm/llm_factory.py` | `domain/llm/interfaces.py` | ✅ |
| `infrastructure/llm/llm_factory.py` | `domain/llm_model/entity.py` | ✅ |
| `api/main.py` | `infrastructure/llm/llm_factory.py` | ✅ (DI 구성) |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| Target | Rule | Example |
|--------|------|---------|
| Interface | `~Interface` 접미사 | `LLMFactoryInterface` |
| Implementation | 접미사 없음 | `LLMFactory` |
| 메서드 | snake_case, 동사 시작 | `create()`, `_resolve_api_key()` |
| private 메서드 | `_` prefix | `_create_openai()` |
| 테스트 | `test_` prefix + 행동 설명 | `test_create_openai_returns_chat_openai` |

### 10.2 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 타입 힌트 | 모든 파라미터·리턴에 명시 (PEP 484) |
| 함수 길이 | 40줄 이하 (CLAUDE.md 규칙) |
| 에러 처리 | logger + raise (스택 트레이스 보존) |
| Import 순서 | stdlib → 3rd party → src (isort) |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/
│   ├── llm/                          ← 신규 디렉토리
│   │   ├── __init__.py               ← 신규
│   │   └── interfaces.py             ← 신규: LLMFactoryInterface
│   └── llm_model/                    ← 변경 없음
│       ├── entity.py
│       └── interfaces.py
├── infrastructure/
│   └── llm/                          ← 기존 디렉토리
│       ├── claude_client.py          ← 변경 없음
│       └── llm_factory.py            ← 신규: LLMFactory
├── application/
│   ├── general_chat/
│   │   └── use_case.py               ← 수정
│   ├── rag_agent/
│   │   └── use_case.py               ← 수정
│   ├── auto_agent_builder/
│   │   └── agent_spec_inference_service.py  ← 수정
│   └── agent_builder/
│       └── workflow_compiler.py       ← 수정
├── api/
│   └── main.py                        ← 수정 (DI)
tests/
└── unit/
    └── infrastructure/
        └── llm/
            └── test_llm_factory.py    ← 신규
```

### 11.2 Implementation Order (TDD)

1. [ ] **`src/domain/llm/__init__.py` + `interfaces.py`** 생성 — LLMFactoryInterface ABC
2. [ ] **`tests/unit/infrastructure/llm/test_llm_factory.py`** 작성 — Red (테스트 먼저)
3. [ ] **`src/infrastructure/llm/llm_factory.py`** 구현 — Green (테스트 통과)
4. [ ] **`src/application/agent_builder/workflow_compiler.py`** 수정 — `_build_llm` → Factory 위임
5. [ ] **`src/application/general_chat/use_case.py`** 수정 — Factory + LlmModel DI
6. [ ] **`src/application/rag_agent/use_case.py`** 수정 — Factory + LlmModel DI
7. [ ] **`src/application/auto_agent_builder/agent_spec_inference_service.py`** 수정 — Factory + LlmModel DI
8. [ ] **`src/api/main.py`** DI 팩토리 업데이트 — Factory 싱글톤 + 기본 모델 조회
9. [ ] **기존 테스트 수정** — ChatOpenAI mock → Factory mock으로 전환
10. [ ] **전체 테스트 실행** — regression 확인

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-08 | Initial draft | 배상규 |
