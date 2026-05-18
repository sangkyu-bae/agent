# fix-agent-run-di-missing-logger Planning Document

> **Summary**: Agent Builder `run_uc_factory`에서 `LangChainSummarizer` 생성 시 `logger` 인자 누락으로 인한 TypeError 수정
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-11
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `POST /api/v1/agents/{agent_id}/run` 호출 시 `LangChainSummarizer.__init__()` missing 'logger' TypeError로 에이전트 실행이 불가능 |
| **Solution** | `main.py:1313`의 `LangChainSummarizer` 생성자에 `logger=app_logger` 인자 추가 |
| **Function/UX Effect** | 에이전트 실행 API가 정상 동작하여 multi-turn 대화 기능 사용 가능 |
| **Core Value** | DI 일관성 확보 및 에이전트 실행 기능 복구 |

---

## 1. Overview

### 1.1 Purpose

Agent Builder의 에이전트 실행 엔드포인트(`POST /api/v1/agents/{agent_id}/run`)에서 `LangChainSummarizer` 인스턴스 생성 시 필수 인자인 `logger`가 누락되어 `TypeError`가 발생하는 버그를 수정한다.

### 1.2 Background

`agent-chat-multiturn` 기능 개발 과정에서 `RunAgentUseCase`에 대화 요약 기능을 추가하면서 `LangChainSummarizer`를 DI로 주입하도록 변경했다. 그러나 `run_uc_factory` (main.py:1310)에서 `LangChainSummarizer`를 생성할 때 `logger` 인자를 빠뜨렸다.

동일한 클래스를 사용하는 다른 두 지점에서는 정상적으로 `logger`를 전달하고 있어, 복사 누락으로 추정된다:
- `main.py:545` (ConversationUseCase factory) — `logger=app_logger` ✅
- `main.py:1205` (GeneralChatUseCase factory) — `logger=app_logger` ✅
- `main.py:1313` (RunAgentUseCase factory) — **logger 누락** ❌

---

## 2. Error Analysis

### 2.1 에러 메시지

```
TypeError: LangChainSummarizer.__init__() missing 1 required positional argument: 'logger'
```

### 2.2 호출 체인

```
Request: POST /api/v1/agents/{agent_id}/run
  → FastAPI Dependency Injection
    → run_uc_factory() (main.py:1310)
      → LangChainSummarizer(model_name=..., api_key=...)  ← logger 누락
        → TypeError 발생
          → exception_handler_middleware가 500 반환
```

### 2.3 LangChainSummarizer 생성자 시그니처

```python
# src/infrastructure/conversation/langchain_summarizer.py:22-29
def __init__(
    self,
    model_name: str,
    api_key: str,
    logger: LoggerInterface,   # ← 필수 인자
) -> None:
```

### 2.4 근본 원인

`run_uc_factory` 함수에서 `LangChainSummarizer` 생성 시 `logger` 키워드 인자를 전달하지 않음. 다른 factory 함수들(line 545, 1205)에서는 `logger=app_logger`를 올바르게 전달하고 있으므로 단순 복사 누락.

---

## 3. Fix Plan

### 3.1 수정 대상

| # | 파일 | 위치 | 수정 내용 |
|---|------|------|-----------|
| 1 | `src/api/main.py` | L1313-1316 | `LangChainSummarizer` 생성자에 `logger=app_logger` 추가 |

### 3.2 수정 코드 (Before → After)

**Before** (main.py:1313-1316):
```python
summarizer = LangChainSummarizer(
    model_name=settings.openai_llm_model,
    api_key=settings.openai_api_key,
)
```

**After**:
```python
summarizer = LangChainSummarizer(
    model_name=settings.openai_llm_model,
    api_key=settings.openai_api_key,
    logger=app_logger,
)
```

### 3.3 테스트 확인

- `tests/application/agent_builder/test_run_agent_use_case.py`에서 `LangChainSummarizer` mock이 올바르게 logger를 포함하는지 확인
- 서버 기동 후 `POST /api/v1/agents/{agent_id}/run` 호출 시 TypeError 발생하지 않음을 확인

---

## 4. Impact Analysis

### 4.1 영향 범위

- **직접 영향**: `POST /api/v1/agents/{agent_id}/run` 엔드포인트 정상화
- **간접 영향**: 없음 (다른 factory 함수는 이미 정상)

### 4.2 리스크

- **리스크**: 매우 낮음 (1줄 추가, 기존 패턴과 동일)
- **롤백**: 해당 없음 (버그 수정이므로 롤백 불필요)

---

## 5. Checklist

- [ ] `main.py:1313` LangChainSummarizer에 `logger=app_logger` 추가
- [ ] 서버 기동 확인 (import 에러 없음)
- [ ] `POST /api/v1/agents/{agent_id}/run` API 호출 정상 동작 확인
- [ ] 기존 테스트 통과 확인
