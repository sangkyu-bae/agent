# Dynamic LLM Factory Planning Document

> **Summary**: 중앙 집중식 LLM Factory를 도입하여 Agent/대화 영역에서 provider별 동적 LLM 선택을 지원한다
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-08
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | LLM 생성이 각 UseCase에 분산되어 ChatOpenAI를 직접 호출하며, provider 변경 시 코드 수정이 필수적이다 |
| **Solution** | `WorkflowCompiler._build_llm()`의 provider 분기 로직을 독립 `LLMFactory`로 추출하고, Agent/대화 UseCase가 이를 DI로 주입받아 사용한다 |
| **Function/UX Effect** | Agent 생성/실행 시 DB 레지스트리의 모든 활성 모델(GPT-4o, Claude, Ollama 등)을 관리자가 선택 가능 |
| **Core Value** | LLM provider 교체/추가 시 Factory 한 곳만 수정하면 되는 OCP(개방-폐쇄 원칙) 준수 구조 |

---

## 1. Overview

### 1.1 Purpose

현재 `GeneralChatUseCase`, `RAGAgentUseCase` 등 Agent/대화 영역의 UseCase에서 `ChatOpenAI`를 직접 생성하고 있어:
- provider가 OpenAI로 고정됨 (Anthropic, Ollama 등 사용 불가)
- 모델 변경 시 `settings.openai_llm_model` 환경변수만 사용 가능하고, DB의 `LlmModel` 레지스트리를 활용하지 못함
- 동일한 LLM 생성 로직이 여러 곳에 중복됨

이를 해결하기 위해 중앙 집중식 `LLMFactory`를 도입하여 `LlmModel` 도메인 엔티티 기반으로 동적 LLM 인스턴스를 생성한다.

### 1.2 Background

**현재 상태 분석:**

| 위치 | 현재 패턴 | 문제 |
|------|----------|------|
| `WorkflowCompiler._build_llm()` | LlmModel 기반 provider 분기 | 클래스 내부에 private으로 묻혀 재사용 불가 |
| `GeneralChatUseCase` | `ChatOpenAI(model=self._model_name)` 직접 생성 | OpenAI 고정, DB 레지스트리 미사용 |
| `RAGAgentUseCase` | `ChatOpenAI(model=self._model_name)` 직접 생성 | OpenAI 고정, DB 레지스트리 미사용 |
| `AgentSpecInferenceService` | `ChatOpenAI(model=model_name)` 직접 생성 | OpenAI 고정 |
| `main.py` DI 팩토리들 | `ChatOpenAI(model=settings.openai_llm_model)` | OpenAI 고정, 환경변수 의존 |

**이미 존재하는 인프라:**
- `LlmModel` 도메인 엔티티 (`src/domain/llm_model/entity.py`)
- `LlmModelRepository` 인터페이스 및 구현체 (`find_by_id`, `find_default`, `list_active`)
- DB 시드 데이터: GPT-4o, GPT-4o Mini, Claude Sonnet 4.6
- `AgentDefinition.llm_model_id` FK 관계

### 1.3 Related Documents

- 기존 LlmModel 도메인: `src/domain/llm_model/`
- WorkflowCompiler: `src/application/agent_builder/workflow_compiler.py`
- CLAUDE.md 아키텍처 규칙: `idt/CLAUDE.md`

---

## 2. Scope

### 2.1 In Scope

- [x] `LLMFactory` 클래스 신규 생성 (infrastructure 레이어)
- [x] `LLMFactoryInterface` 도메인 인터페이스 정의
- [x] `GeneralChatUseCase`에 LLMFactory DI 적용
- [x] `RAGAgentUseCase`에 LLMFactory DI 적용
- [x] `WorkflowCompiler._build_llm()` → LLMFactory 위임으로 교체
- [x] `AgentSpecInferenceService`에 LLMFactory DI 적용
- [x] `main.py` DI 팩토리 업데이트
- [x] 각 변경에 대한 단위 테스트 작성

### 2.2 Out of Scope

- research_agent 내부 어댑터 (router, relevance, generator) — 내부 전용 모델 고정 유지
- query_rewrite, hallucination 어댑터 — 특정 모델 최적화 유지
- conversation/langchain_llm, langchain_summarizer — 대화 기록 관련 내부 모듈
- `OpenAIAdapter` (llm_adapter.py) — 범용 어댑터로 별도 관리
- 프론트엔드 UI 변경
- 새로운 LLM provider 추가 (현재 openai/anthropic/ollama 유지)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `LLMFactory`가 `LlmModel` 엔티티를 받아 `BaseChatModel`을 반환한다 | High | Pending |
| FR-02 | openai, anthropic, ollama 3개 provider를 지원한다 | High | Pending |
| FR-03 | 지원하지 않는 provider 입력 시 `ValueError`를 발생시킨다 | High | Pending |
| FR-04 | `GeneralChatUseCase`가 Factory를 통해 LLM을 생성한다 | High | Pending |
| FR-05 | `RAGAgentUseCase`가 Factory를 통해 LLM을 생성한다 | High | Pending |
| FR-06 | `WorkflowCompiler`가 Factory를 위임 호출한다 | Medium | Pending |
| FR-07 | `AgentSpecInferenceService`가 Factory를 통해 LLM을 생성한다 | Medium | Pending |
| FR-08 | UseCase에 `llm_model_id`가 전달되지 않으면 DB의 기본 모델(`is_default=True`)을 사용한다 | High | Pending |
| FR-09 | API 요청 시 `llm_model_id`를 선택적으로 전달할 수 있다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 성능 | Factory 호출 오버헤드 < 1ms | 단위 테스트 실행 시간 측정 |
| 확장성 | 새 provider 추가 시 Factory에 elif 1개 추가로 완료 | 코드 리뷰 |
| 테스트 | Factory 단위 테스트 커버리지 100% | pytest --cov |
| 의존성 역전 | UseCase는 LLMFactoryInterface(도메인)만 참조 | verify-architecture 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `LLMFactory` 클래스 및 도메인 인터페이스 구현 완료
- [ ] 4개 UseCase/서비스에 DI 적용 완료
- [ ] 기존 테스트 전부 통과 (regression 없음)
- [ ] 신규 Factory 테스트 작성 및 통과
- [ ] `ChatOpenAI` 직접 import가 대상 UseCase에서 제거됨

### 4.2 Quality Criteria

- [ ] Factory 테스트 커버리지 100%
- [ ] UseCase 테스트에서 Factory mock 주입으로 provider 독립적 테스트 가능
- [ ] 레이어 규칙 위반 없음 (domain → infrastructure 참조 금지)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 기존 테스트 깨짐 | High | Medium | DI 인터페이스 유지, 기존 시그니처 호환성 확보. 기본값으로 fallback |
| API 키 환경변수 누락 시 런타임 에러 | Medium | Low | Factory에서 api_key None 체크 후 명확한 에러 메시지 |
| Anthropic/Ollama 모델 동작 차이 | Medium | Medium | provider별 통합 테스트로 확인. 초기에는 OpenAI를 기본값으로 유지 |
| DI 그래프 복잡도 증가 | Low | Medium | main.py 팩토리 함수 정리, 의존성 주석 추가 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic systems | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Factory 위치 | domain / infrastructure | infrastructure | LangChain 의존성이 있어 domain 불가. 인터페이스만 domain에 배치 |
| Factory 패턴 | Simple Factory / Abstract Factory / Strategy | Simple Factory + DI | provider 3개로 충분. 과도한 추상화 불필요 |
| LlmModel 해석 | Factory 내부 조회 / 외부에서 전달 | 외부에서 전달 | Factory는 생성만 담당. 조회 책임은 UseCase 또는 DI |
| 기존 코드 마이그레이션 | 점진적 / 일괄 | 일괄 | 대상이 4곳으로 제한적. 한번에 전환 가능 |

### 6.3 Clean Architecture Approach

```
Domain Layer (순수):
  src/domain/llm/
    interfaces.py          ← LLMFactoryInterface 정의
  src/domain/llm_model/
    entity.py              ← 기존 LlmModel (변경 없음)
    interfaces.py          ← 기존 Repository 인터페이스 (변경 없음)

Infrastructure Layer (구현):
  src/infrastructure/llm/
    llm_factory.py         ← LLMFactory 구현체 (ChatOpenAI/ChatAnthropic/ChatOllama 생성)

Application Layer (사용):
  src/application/general_chat/use_case.py     ← LLMFactoryInterface DI 주입
  src/application/rag_agent/use_case.py        ← LLMFactoryInterface DI 주입
  src/application/agent_builder/
    workflow_compiler.py                        ← _build_llm → Factory 위임
    agent_spec_inference_service.py             ← LLMFactoryInterface DI 주입

Interfaces Layer (DI 구성):
  src/api/main.py          ← Factory 인스턴스 생성 및 UseCase에 주입
```

**의존성 흐름:**
```
UseCase ──depends on──→ LLMFactoryInterface (domain)
                              ↑ implements
                        LLMFactory (infrastructure)
                              ↓ uses
                   ChatOpenAI / ChatAnthropic / ChatOllama
```

---

## 7. Implementation Strategy

### 7.1 파일별 변경 계획

| 순서 | 파일 | 변경 내용 | 영향 범위 |
|------|------|----------|----------|
| 1 | `src/domain/llm/interfaces.py` (신규) | `LLMFactoryInterface` ABC 정의 | 없음 (신규) |
| 2 | `src/infrastructure/llm/llm_factory.py` (신규) | `LLMFactory` 구현. `WorkflowCompiler._build_llm()` 로직 추출 | 없음 (신규) |
| 3 | `tests/unit/infrastructure/llm/test_llm_factory.py` (신규) | provider별 생성 테스트, 미지원 provider 에러 테스트 | 없음 (신규) |
| 4 | `src/application/agent_builder/workflow_compiler.py` | `_build_llm()` → `self._llm_factory.create()` 위임 | WorkflowCompiler 테스트 |
| 5 | `src/application/general_chat/use_case.py` | `model_name: str` → `LLMFactoryInterface` + `LlmModel` 주입 | GeneralChat 테스트 |
| 6 | `src/application/rag_agent/use_case.py` | `model_name: str` → `LLMFactoryInterface` + `LlmModel` 주입 | RAGAgent 테스트 |
| 7 | `src/application/auto_agent_builder/agent_spec_inference_service.py` | Factory DI 주입 | AgentSpec 테스트 |
| 8 | `src/api/main.py` | DI 팩토리 함수에서 `LLMFactory` 인스턴스 생성 및 주입 | 전체 DI 그래프 |
| 9 | `src/api/routes/general_chat_router.py` | 요청에 `llm_model_id` 선택적 파라미터 추가 | API 계약 |
| 10 | `src/api/routes/rag_agent_router.py` | 요청에 `llm_model_id` 선택적 파라미터 추가 | API 계약 |

### 7.2 핵심 인터페이스 설계 (예시)

```python
# src/domain/llm/interfaces.py
from abc import ABC, abstractmethod
from langchain_core.language_models import BaseChatModel
from src.domain.llm_model.entity import LlmModel

class LLMFactoryInterface(ABC):
    @abstractmethod
    def create(self, llm_model: LlmModel, temperature: float = 0.0) -> BaseChatModel:
        """LlmModel 엔티티 기반으로 LLM 인스턴스를 생성한다."""
```

```python
# src/infrastructure/llm/llm_factory.py
class LLMFactory(LLMFactoryInterface):
    def create(self, llm_model: LlmModel, temperature: float = 0.0) -> BaseChatModel:
        provider = llm_model.provider
        if provider == "openai":
            api_key = os.environ.get(llm_model.api_key_env)
            return ChatOpenAI(model=llm_model.model_name, api_key=api_key, temperature=temperature)
        if provider == "anthropic":
            api_key = os.environ.get(llm_model.api_key_env)
            return ChatAnthropic(model=llm_model.model_name, api_key=api_key, temperature=temperature)
        if provider == "ollama":
            return ChatOllama(model=llm_model.model_name, temperature=temperature)
        raise ValueError(f"지원하지 않는 provider: {provider}")
```

### 7.3 UseCase 변경 패턴 (예시: GeneralChatUseCase)

```python
# Before
class GeneralChatUseCase:
    def __init__(self, ..., openai_api_key: str = "", model_name: str = "gpt-4o"):
        self._api_key = openai_api_key
        self._model_name = model_name

    def _create_agent(self, tools):
        llm = ChatOpenAI(model=self._model_name, api_key=self._api_key, temperature=0)
        return create_react_agent(llm, tools=tools, prompt=_SYSTEM_PROMPT)

# After
class GeneralChatUseCase:
    def __init__(self, ..., llm_factory: LLMFactoryInterface, llm_model: LlmModel):
        self._llm_factory = llm_factory
        self._llm_model = llm_model

    def _create_agent(self, tools):
        llm = self._llm_factory.create(self._llm_model, temperature=0)
        return create_react_agent(llm, tools=tools, prompt=_SYSTEM_PROMPT)
```

---

## 8. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section
- [x] DDD 레이어 규칙 (domain → infrastructure 참조 금지)
- [x] TDD 필수 (테스트 먼저 작성)
- [x] 함수 40줄 초과 금지
- [x] 타입 힌트 필수 (pydantic / typing)

### 7.2 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `OPENAI_API_KEY` | OpenAI API 인증 | Server | 기존 |
| `ANTHROPIC_API_KEY` | Anthropic API 인증 | Server | 기존 |
| `OLLAMA_BASE_URL` | Ollama 서버 주소 | Server | 기존 |

신규 환경변수 없음 — 기존 `LlmModel.api_key_env` 필드를 통해 동적으로 참조.

---

## 8. Next Steps

1. [ ] Design 문서 작성 (`/pdca design dynamic-llm-factory`)
2. [ ] TDD: Factory 테스트 먼저 작성
3. [ ] Factory 구현 → UseCase 마이그레이션 → DI 업데이트

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-08 | Initial draft | 배상규 |
