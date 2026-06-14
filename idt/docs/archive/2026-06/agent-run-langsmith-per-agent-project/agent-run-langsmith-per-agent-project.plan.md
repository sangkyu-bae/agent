# agent-run-langsmith-per-agent-project Plan Document

## Executive Summary

> WebSocket(`/ws/agent`)로 에이전트별 채팅 실행 시 LangSmith 추적이 "안 되는 것 같다"는 보고와, LangSmith에서 어떤 에이전트의 실행인지 구분이 안 되는 문제를 해결한다. 진단으로 추적 동작 여부를 먼저 확인하고, 식별성은 **에이전트별 LangSmith 프로젝트 분리**로 개선한다(공통 `stream()` 수정 → 전 transport 일괄 적용).

| 관점 | 내용 |
|------|------|
| **Problem** | `RunAgentUseCase.stream()`이 모든 transport 공통으로 `langsmith(project_name="agent-run")`을 호출하지만 ① WS 화면 실행 시 추적 도달 여부가 검증된 적 없고, ② root run 이름은 기본값 `"LangGraph"`, tags/metadata에는 agent **UUID만** 있어 LangSmith에서 어떤 에이전트의 trace인지 식별할 수 없다. |
| **Solution** | (1) dev 서버에서 WS 채팅 1회 → LangSmith run 도달 여부를 먼저 **진단**(코드 변경 최소). (2) `langsmith()` 호출을 에이전트 로드 직후로 옮겨 `project_name=f"agent-{agent.name}"`로 **에이전트별 프로젝트 분리**, run_name·tags·metadata에 에이전트명 보강. 공통 `stream()` 한 곳 수정으로 HTTP/SSE/WS 모두 반영. |
| **Function/UX Effect** | LangSmith 좌측 프로젝트 목록이 `agent-{에이전트명}`으로 분리 표시되어, 운영자가 특정 에이전트의 실행만 모아 trace·토큰·지연을 추적·디버깅할 수 있다. 어떤 transport(WS 포함)로 실행해도 동일하게 기록된다. |
| **Core Value** | **관측성/운영성**: 멀티 에이전트 플랫폼에서 에이전트 단위 품질·비용·오류 모니터링이 가능해지고, "WS 추적 누락" 의심을 사실 기반으로 종결한다. |

---

> **Project**: sangplusbot (idt)
> **Author**: AI Assistant
> **Date**: 2026-06-03
> **Status**: Draft
> **Entry point**: `src/api/routes/ws_router.py` → `RunAgentUseCase.stream()` (`src/application/agent_builder/run_agent_use_case.py`)

---

## 1. 배경 / 현황 조사 (코드 근거)

### 1.1 추적 wiring 위치
- `RunAgentUseCase.stream()` 시작부(`run_agent_use_case.py:180`)에서 `langsmith(project_name="agent-run")` 호출.
- WS(`/ws/agent`), SSE(`/run/stream`), HTTP(`/run`) **모두 이 `stream()`을 공유** → 추적 wiring은 transport별 차이가 없다.
- 앱 시작 시점의 LangSmith 초기화는 없음. `main.py:20 load_dotenv()`로 `.env` → `os.environ` 적재 후, 추적 활성화는 **매 요청 `stream()` 안에서 `os.environ` 변경**으로 수행.

### 1.2 `langsmith()` 동작 (`src/infrastructure/langsmith/langsmith.py`)
- `LANGCHAIN_API_KEY` / `LANGSMITH_API_KEY` 중 긴 값을 선택, 비어 있으면 **조용히 return**(추적 미설정).
- 키가 있으면 `LANGSMITH_ENDPOINT`, `LANGSMITH_TRACING="true"`, `LANGSMITH_PROJECT=project_name` 설정.
- **설정하지 않는 것**: `LANGCHAIN_TRACING_V2`. (설치된 langchain-core 버전이 이 변수를 기대하면 추적이 누락될 수 있음 → 진단 대상)

### 1.3 환경 확인 (이미 점검됨)
- 실제 `.env`에 `LANGCHAIN_API_KEY` 설정됨(길이 51, 값 미노출). `LANGSMITH_TRACING` 키도 존재.
- 따라서 "키 누락"은 원인이 아님 → 추적 미작동 의심은 **(a) env 변수 이름 호환** 또는 **(b) 단순 인지(식별 불가로 인한 착시)** 가능성.

### 1.4 에이전트 식별 정보 부재
- `graph_config`(`run_agent_use_case.py:460-469`):
  - `metadata = {run_id, conversation_id, user_id, agent_id}` — **agent_name 없음(agent_id=UUID)**
  - `tags = ["agent-platform", agent.id]` — **UUID만**
  - `run_name` **미설정** → LangSmith root run이 기본 `"LangGraph"`로 표기
- `AgentDefinition.name`(`domain/agent_builder/schemas.py:77`) 존재 → 식별자로 사용 가능.

---

## 2. 목표 (Scope)

### 2.1 In Scope
1. **진단**: dev 서버에서 WS(`/ws/agent`) 채팅 1회 실행 → LangSmith에 run이 도달하는지, 어떤 프로젝트/이름으로 기록되는지 확인. (코드 변경 최소)
2. **에이전트별 프로젝트 분리**: `langsmith(project_name=f"agent-{agent.name}")` — `stream()`에서 **에이전트 로드 이후**로 호출 위치 이동.
3. **식별 보강**: `graph_config`의 `run_name`(=에이전트명), `tags`, `metadata`에 `agent_name` 추가.
4. 공통 `stream()` 한 곳 수정 → HTTP/SSE/WS 일괄 반영.

### 2.2 Out of Scope (이번 사이클 제외)
- 추적 인프라 구조 변경(startup 1회 init, per-call `os.environ` 변경 제거 등) → **진단 결과를 보고 별도 결정**(사용자 결정: "진단만, 코드 변경 최소").
- `GeneralChatUseCase`(`/ws/chat`, 일반채팅) 추적/네이밍 → 사용자 결정: 에이전트 실행 전체로 한정.
- LangSmith 대시보드/알림 구성.

---

## 3. 결정 사항 (사용자 확정)

| # | 항목 | 결정 |
|---|------|------|
| 1 | 에이전트 식별 방식 | **에이전트별 LangSmith 프로젝트 분리** (`project_name=f"agent-{name}"`) + run_name/tags/metadata 보강 |
| 2 | 추적 미작동 의심 지점 보강 범위 | **진단만** (코드 변경 최소). env 이름 호환/os.environ 안정화는 진단 결과 보고 후속 결정 |
| 3 | 적용 transport/대화 유형 | **공통 `stream()` 일괄** (HTTP `/run` + SSE `/run/stream` + WS `/ws/agent`). 일반채팅 제외 |

---

## 4. 변경 포인트 (예상 — 상세는 Design에서 확정)

| 파일 | 변경 |
|------|------|
| `src/application/agent_builder/run_agent_use_case.py` | ① `langsmith(...)` 호출을 `_authorize_and_load` **이후**로 이동, `project_name=f"agent-{agent.name}"` (정규화 적용). ② `_prepare_graph`의 `graph_config`에 `run_name=agent.name`, `tags`에 `agent.name` 추가, `metadata["agent_name"]=agent.name` 추가 |
| `src/infrastructure/langsmith/langsmith.py` | (진단 결과에 따라) project_name 정규화 헬퍼 또는 빈/None 방어. 최소 변경 원칙 — 진단 후 결정 |

> 코드 레이어: `RunAgentUseCase`는 application, `langsmith()`는 infrastructure. 현재도 application이 `infrastructure.langsmith`를 import 중(기존 의존성 유지, 신규 위반 없음).

---

## 5. 리스크 / 검토 필요

| 리스크 | 심각도 | 메모 (Design에서 해소) |
|--------|--------|------------------------|
| **per-call `os.environ["LANGSMITH_PROJECT"]` 전역 변경** → 서로 다른 에이전트의 동시 실행 시 프로젝트명 경합(race) | **Medium** | 진단 범위 밖이나, 프로젝트 분리를 도입하면 경합 표면이 커짐. Design에서 per-run tracer(`LangChainTracer(project_name=...)`를 `graph_config["callbacks"]`에 주입)로 전역 변경 없이 per-run 프로젝트 지정하는 대안 검토 |
| `agent.name`에 공백/특수문자/빈 값 → 프로젝트명 부적합 | Low | 정규화(trim, 길이 제한, 빈 값이면 `agent-run` fallback) |
| 프로젝트 수 급증(에이전트 많을수록 LangSmith 프로젝트 폭증) | Low | 사용자가 분리 방식을 명시 선택. 운영상 수용 |
| `langsmith()` 호출 위치 이동으로 인한 회귀 | Low | 이동 후에도 graph 컴파일/실행 전에 호출되면 동일 동작. 테스트로 보장 |
| env 변수 이름 호환(`LANGCHAIN_TRACING_V2`) 실제 누락 여부 | **확인 필요** | §6 진단 단계 결과로 판정 |

---

## 6. 진단 절차 (Step 0 — 코드 변경 전)

1. dev 서버 기동(`uvicorn src.api.main:app --reload --port 8000`).
2. 실제 화면에서 에이전트 선택 → WS(`/ws/agent`) 채팅 1회 전송.
3. LangSmith 콘솔에서 확인:
   - `agent-run` 프로젝트에 run이 **도달하는가?**
   - root run 이름/태그가 무엇으로 보이는가? (`LangGraph` / agent UUID 여부)
4. 판정:
   - **도달 O** → 추적은 정상, 문제는 "식별 불가"였음 → §4 식별 보강만 진행.
   - **도달 X** → `LANGCHAIN_TRACING_V2` 미설정이 원인일 가능성 → Out of Scope였던 env 보강을 본 사이클로 승격할지 사용자 재확인.

---

## 7. 수용 기준 (Acceptance Criteria)

- [ ] (진단) WS 채팅 실행 시 LangSmith 추적 도달 여부가 문서로 확인됨
- [ ] `stream()`이 에이전트 로드 이후 `langsmith(project_name=f"agent-{agent.name}")` 호출
- [ ] LangSmith run의 `run_name`이 에이전트명으로 표기됨 (UI 식별 가능)
- [ ] `tags`·`metadata`에 `agent_name` 포함
- [ ] HTTP `/run`, SSE `/run/stream`, WS `/ws/agent` 모두 동일하게 적용(공통 `stream()`)
- [ ] `agent.name` 비정상 값(빈 문자열 등)에 대한 fallback 동작
- [ ] 신규/기존 테스트 통과(격리 실행 — Windows event-loop flakiness 회피)
- [ ] 동시성 race 리스크가 Design에서 명시적으로 다뤄짐(전역 env vs per-run tracer)

---

## 8. 다음 단계

```
/pdca design agent-run-langsmith-per-agent-project
```

> Design에서 확정할 것: project_name 정규화 규칙, 전역 `os.environ` vs per-run `LangChainTracer` 주입 방식 택1, 테스트 전략(graph_config 인자 검증 + langsmith 호출 인자 검증).
