## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | fix-tool-name-openai-validation |
| 작성일 | 2026-05-11 |
| 예상 소요 | 30분 |

### Value Delivered

| 관점 | 내용 |
|------|------|
| Problem | Agent Builder로 만든 에이전트 실행 시 OpenAI API 400 에러 — tool name에 한글/공백 포함 |
| Solution | tool name을 OpenAI 패턴(`^[a-zA-Z0-9_-]+$`)에 맞도록 sanitize + 기본값 수정 |
| Function UX Effect | 에이전트 실행이 정상 동작하며, 사용자 정의 한글 tool_name도 안전하게 변환됨 |
| Core Value | Agent Builder 핵심 기능(에이전트 실행)의 안정성 확보 |

---

## 1. 문제 분석

### 에러 메시지
```
openai.BadRequestError: Invalid 'tools[0].function.name': string does not match pattern.
Expected a string that matches the pattern '^[a-zA-Z0-9_-]+$'.
```

### 원인 추적

1. `RagToolConfig.tool_name` 기본값 = `"내부 문서 검색"` (한글 + 공백)
2. `ToolFactory.create()` → `InternalDocumentSearchTool(name=rag_config.tool_name)` 으로 전달
3. LangGraph `create_react_agent`가 tool을 OpenAI API에 등록할 때 `function.name` 필드로 사용
4. OpenAI API는 `^[a-zA-Z0-9_-]+$` 패턴만 허용 → 400 에러

### 영향 범위

| 파일 | 역할 |
|------|------|
| `src/domain/agent_builder/rag_tool_config.py` | `tool_name` 기본값 정의 |
| `src/infrastructure/agent_builder/tool_factory.py` | tool 생성 시 name 전달 |
| `src/application/rag_agent/tools.py` | `InternalDocumentSearchTool.name` 필드 |

---

## 2. 해결 방안

### 2-1. 기본값 수정
`RagToolConfig.tool_name` 기본값을 `"internal_document_search"` (ASCII)로 변경.

### 2-2. Sanitize 로직 추가
사용자가 한글 tool_name을 입력해도 OpenAI에 전달되는 `name`은 항상 유효하도록:
- `InternalDocumentSearchTool`에서 `name`과 `description`을 분리
- `name`은 항상 OpenAI-safe한 ASCII 식별자로 고정
- 사용자 정의 `tool_name`(한글 가능)은 `description`에 반영

### 2-3. 검증 정책 강화
`RagToolConfig.__post_init__` 또는 `RagToolConfigPolicy.validate`에서 `tool_name`이 OpenAI 패턴에 맞는지 검증하거나, 자동 sanitize.

---

## 3. 구현 계획

| 순서 | 작업 | 파일 | TDD |
|------|------|------|-----|
| 1 | `RagToolConfig.tool_name` 기본값을 ASCII로 변경 | `rag_tool_config.py` | 기존 테스트 수정 |
| 2 | `ToolFactory.create()`에서 name sanitize 함수 적용 | `tool_factory.py` | 단위 테스트 추가 |
| 3 | `InternalDocumentSearchTool` - 한글 이름은 description으로 이동 | `tools.py` | - |
| 4 | `RagToolConfigPolicy`에 tool_name 패턴 검증 추가 | `rag_tool_config.py` | 단위 테스트 추가 |

### Sanitize 함수 로직
```python
import re

def sanitize_tool_name(name: str) -> str:
    """OpenAI tool name 패턴(^[a-zA-Z0-9_-]+$)에 맞도록 변환."""
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized.strip('_') or "unnamed_tool"
```

---

## 4. 테스트 계획

| 테스트 | 검증 내용 |
|--------|----------|
| `test_rag_tool_config_default_name_is_ascii` | 기본값이 OpenAI 패턴 매칭 |
| `test_sanitize_tool_name_korean` | 한글 입력 → ASCII 변환 |
| `test_sanitize_tool_name_spaces` | 공백 → underscore |
| `test_tool_factory_creates_valid_name` | 실제 tool 생성 시 name 패턴 검증 |
| `test_workflow_compiler_integration` | 전체 흐름에서 에러 없이 컴파일 |

---

## 5. 리스크

| 리스크 | 대응 |
|--------|------|
| DB에 이미 한글 tool_name이 저장된 에이전트 존재 | sanitize를 런타임에 적용하여 기존 데이터 호환 |
| tool_name 변경 시 LangSmith 트레이스 식별 어려움 | description에 원본 한글 이름 유지 |
