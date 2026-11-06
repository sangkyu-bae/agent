# pii-masking-integration Design Document

> **Summary**: 프로세스 안은 원본, 외부 LLM 전송만 placeholder. create_agent 경로는 미들웨어, 직접 호출은 `GuardedLlm` 프록시로 처리하고, 탐지 규칙을 한국어 문장 기준으로 재작성한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 0.6
> **Author**: 배상규
> **Date**: 2026-11-02 (v0.6: 2026-11-05)
> **Status**: Draft
> **Planning Doc**: [pii-masking-integration.plan.md](../../01-plan/features/pii-masking-integration.plan.md)

### Pipeline References

해당 없음. API 스키마, DB 스키마, 프론트 변경이 없다.

---

## Context Anchor

> Copied from Plan document. Ensures strategic context survives Design→Do handoff.

| Key | Value |
|-----|-------|
| **WHY** | 엔진은 있으나 배선이 없어 실효가 없다. 대화 경로의 PII가 외부 LLM으로 원문 전송된다. |
| **WHO** | P1(개인정보가 섞인 질문·문서를 다루는 사용자), P3(개인정보 처리를 통제해야 하는 관리자), P2(별도 설정 없이 보호받는 에이전트 소유자) |
| **RISK** | 미들웨어를 지나지 않는 경로의 누락, 숫자 오탐으로 인한 답변 품질 저하, 스트리밍 중 placeholder 노출 |
| **SUCCESS** | 대화 경로의 모든 외부 LLM 호출 입력에서 원본 PII 0건, 사용자 화면·DB에 placeholder 0건, 코퍼스 오탐 기준 충족, shadow→on 전환이 설정만으로 가능 |
| **SCOPE** | 포함: 엔진 보정, 미들웨어, 직접 호출 경로, 대화 경로 보조 LLM, 스트리밍 원복, MCP 검사, shadow 관측. 제외: 외부 도구 인자 마스킹, 임베딩 API, 이미지, 이름·주소 탐지, vault 영속화, 프론트 UI |

---

## 1. Overview

### 1.1 Design Goals

- 대화 경로에서 외부 LLM으로 나가는 요청에 원본 PII가 포함되지 않는다.
- 그래프 상태, 도구 인자, 승인 초안, DB, 화면은 원본으로 동작한다.
- 새 LLM 호출 지점이 생겨도 진입점 래핑과 계약 테스트로 우회가 드러난다.
- 환경 설정 하나로 shadow, on, 해제를 전환한다.

### 1.2 Design Principles

- **경계에서만 변환**: 마스킹은 전송 직전, 원복은 수신 직후에 한다. 그 외 코드는 PII 마스킹의 존재를 몰라도 된다.
- **코어 1개, 진입점 2개**: 미들웨어와 프록시는 같은 `PiiMessageMasker`를 쓴다.
- **상태를 늘리지 않는다**: 저장되는 매핑은 없다. 런이 끝나면 vault는 사라진다.
- **코퍼스가 규칙을 검증한다**: 선의 문장을 먼저 쓰고 규칙을 맞춘다. 패턴 본문의 SoT는 `patterns.py`다.

### 1.3 검증된 사실 (2026-11-02 실행)

| 항목 | 방법 | 결과 |
|------|------|------|
| `awrap_model_call`의 `request.override`는 그래프 상태를 바꾸지 않음 | 스파이크(`create_agent` + 스크립트 모델) | LLM 입력은 `[PHONE_1]`, 상태 메시지는 원본 |
| system 프롬프트 마스킹 | 스파이크 | `system_message` override로 적용됨 |
| 응답 tool_calls 원복 | 스파이크 | 도구가 원본 인자 수신 |
| 토큰 이벤트 | 스파이크 | `[PH`, `ONE`, `_1]`로 분할 노출. 미들웨어로 막을 수 없음 |
| 체크포인터 | grep | 에이전트 경로 미사용. 재개는 원본 스냅샷 기반 |
| 조사 결합 탐지 | 엔진 실행 | `010-1234-5678로`, `900101-1234567이고`, `110-123-456789로` 미탐지 |
| 표 숫자 | 엔진 실행 | `매출 1200 3400 5600`이 ACCOUNT로 오탐 |

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: 호출 지점 헬퍼 | Option B: 게이트웨이 + 카탈로그 | Option C: 미들웨어 + 프록시 |
|----------|:-:|:-:|:-:|
| **Approach** | 15개 지점과 보조 어댑터를 각각 수정 | `LlmGateway` 포트 DI, 카탈로그 등록 | 진입점 2곳에서 프록시로 감쌈 |
| **New Files** | 3 | 7 + V082 | 4 |
| **Modified Files** | 약 25 | 약 30 | 약 12 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Medium | High | Medium |
| **Risk** | High (누락) | Medium (이중 스위치) | Low |

**Selected**: Option C — **Rationale**: 진입점에서 감싸면 하위 노드를 고치지 않아 누락 위험이 가장 낮고, on/off 지점이 하나다. 사용자 선택(Checkpoint 3).

### 2.1 Component Diagram

```
 RunAgentUseCase / GeneralChatUseCase ──── new_scope() ────┐
        │                                                  │ PiiRunScope (런 1개)
        │ compile(pii_scope=...)                           │  - vault
        ▼                                                  │  - mode (shadow|on)
 WorkflowCompiler                                          │  - counters
   raw_llm = factory.create()                              │
   llm = guard(raw_llm)                                    │
    ├ create_agent(model=raw_llm,                          │
    │    middleware=[PiiMaskingMiddleware, ...기존 체인])──┤
    └ supervisor·final_answer·파이프라인·생성 노드(llm) ───┤
                                                           ▼
 UtilityLLMProvider.get() → GuardedLlm(scope 없음)    PiiMessageMasker
 summarizer·차트 LLM      → GuardedLlm(scope 없음)         │
                                                           ▼
 토큰 이벤트 → PlaceholderStreamRestorer            PiiMaskingService
 MCPToolAdapter / McpActionExecutor → inspect()      └ PiiDetectorPort(RegexPiiDetector)
```

### 2.2 Data Flow

```
on 모드
  상태(원본) ─mask_messages→ 외부 LLM ─restore_message→ 상태(원본)
                               └ 토큰 ─stream_restorer→ TOKEN 이벤트(원본)
  도구: 상태의 원본 인자로 실행 → 결과는 원본으로 상태에 저장 → 다음 호출에서 마스킹

shadow 모드
  상태(원본) ─inspect(건수 기록)→ 외부 LLM (요청 변경 없음)

해제 (PII_MASKING_ENABLED=false)
  서비스 None. 프록시·미들웨어 미부착
```

재시도·폴백은 미들웨어 안쪽에서 실행되므로 fallback 모델도 마스킹된 요청을 받는다. 승인 게이트는 체인 뒤쪽이라 원복된 tool_calls를 본다.

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `PiiMaskingMiddleware` | `PiiMessageMasker`, `PiiRunScope` | create_agent 경로 |
| `GuardedLlm` | `PiiMessageMasker`, 내부 Runnable | 직접 호출 경로 |
| `PiiMessageMasker` | `PiiMaskingService`, langchain_core messages | 메시지 단위 변환 |
| `PlaceholderStreamRestorer` | `TokenVault` | 분할 토큰 원복 |
| `MCPToolAdapter`, `McpActionExecutor` | `PiiInspectPort` (optional) | MCP 검사 |

---

## 3. Data Model

DB 변경 없음. 마이그레이션 없음.

### 3.1 도메인 타입

```python
# src/domain/pii_masking/schemas.py
class PiiMaskingMode(str, Enum):
    SHADOW = "shadow"
    ON = "on"

@dataclass
class TokenVault:
    # 기존 유지. restore()는 대소문자 무시 + 알려진 변형만 처리 (§3.3)
    def reserve_literals(self, text: str) -> None: ...  # §6 충돌 방지
    def counts(self) -> dict[PiiType, int]: ...         # 고유 값 건수

@dataclass
class PiiRunScope:
    """런 1개 범위. 저장·로깅 금지. 동시 워커가 공유한다."""
    mode: PiiMaskingMode
    vault: TokenVault = field(default_factory=TokenVault)
```

`get_or_create_placeholder`는 await 없는 동기 코드이고 asyncio 단일 스레드에서 실행되므로 병렬 워커 간 경합이 없다.

### 3.2 삭제

| 대상 | 사유 |
|------|------|
| `TokenVaultRegistry` | session 단위 보관을 폐기. 프로세스 수명 동안 커지는 문제도 함께 제거 |
| `TokenVaultStorePort` | 영속화 폐기 |
| `MaskingResult`, `PiiMaskingPort`의 session_id 시그니처 | 소비처 없음. vault 인자로 교체 |
| `pii_masking_output_redact`, `PII_MASKING_OUTPUT_REDACT` | §6 D-05 |

선행 테스트 55건 중 session 기반 케이스는 scope 기반으로 옮긴다.

### 3.3 placeholder 변형 처리

대상 변형은 대소문자(`[phone_1]`)만이다. 괄호가 사라진 `PHONE_1`은 일반 문장과 구분하지 않고 원복하지 않는다. 고아 처리 대상이며, Do에서 실모델로 빈도를 측정한다.

---

## 4. API Specification

HTTP 변경 없음. 내부 인터페이스만 정의한다.

### 4.1 PiiMaskingService (application)

```python
class PiiMaskingService:
    def __init__(self, detector, logger, config: PiiMaskingConfig): ...
    def new_scope(self) -> PiiRunScope: ...
    def mask_text(self, text: str, scope: PiiRunScope) -> str: ...     # on 실패 시 fail-closed
    def restore_text(self, text: str, scope: PiiRunScope) -> str: ...  # 복원 + 고아 처리
    def restore_known_text(self, text: str, scope: PiiRunScope) -> str: ...  # 인자용, 고아 유지
    def has_orphan(self, value: object, scope: PiiRunScope) -> bool: ...  # 도구 인자 검사
    def inspect(self, value: object) -> dict[PiiType, int]: ...        # 값 불변, 건수만
```

> v0.2: 인자를 vault에서 scope로 변경했다. shadow 분기를 호출자마다 두지 않고 서비스 한 곳에서 처리한다. `PII_MASKING_TYPES` 오타도 D-02와 같이 예외로 올린다.

### 4.2 PiiMessageMasker (application)

```python
class PiiMessageMasker:
    def mask_messages(self, messages, scope) -> list[BaseMessage]: ...
    def restore_message(self, message, scope) -> BaseMessage: ...
    def restore_output(self, output, scope): ...  # AIMessage | BaseModel | dict | str
```

| 대상 | 처리 |
|------|------|
| System/Human/AI/Tool `content` 문자열 | 마스킹 |
| content 블록 리스트 | text 블록만. 이미지 블록 유지 |
| AIMessage `tool_calls[].args` | 재귀 마스킹. id·name 유지 |
| `additional_kwargs`의 원문 tool_calls | 요청에서 제거하지 않고 같은 규칙으로 마스킹 |
| 응답 `content` | 원복 + 고아 placeholder redact |
| 응답 `tool_calls`, `invalid_tool_calls`, `additional_kwargs` | 알려진 placeholder만 원복, 고아는 유지 (v0.3) |
| 구조화 출력 BaseModel | 문자열 필드 재귀 원복 후 `model_copy` |

shadow 모드는 `mask_messages`가 입력을 그대로 돌려주고 vault에 고유 값만 누적한다.

### 4.3 PiiMaskingMiddleware (application)

```python
class PiiMaskingMiddleware(AgentMiddleware):
    def __init__(self, masker: PiiMessageMasker, scope: PiiRunScope): ...
    async def awrap_model_call(self, request, handler): ...
    def wrap_model_call(self, request, handler): ...
    async def awrap_tool_call(self, request, handler): ...  # 고아 placeholder 차단
    def wrap_tool_call(self, request, handler): ...
```

- `awrap_model_call`: `messages`, `system_message`를 override해 호출하고 `ModelResponse.result`, `structured_response`를 원복한다.
- `awrap_tool_call`: 원복 후에도 인자에 placeholder가 남아 있으면 도구를 호출하지 않고 교정 지시 ToolMessage를 반환한다. `tool_call_id`는 그대로 돌려준다.
- 조립은 `MiddlewareBuilder.build_pii_masking(masker, scope)` 정적 팩토리로 한다(D8 격리).
- 워커마다 새 인스턴스, scope는 공유한다.

### 4.4 GuardedLlm (application)

```python
class GuardedLlm(Runnable):
    def __init__(self, inner, masker, scope: PiiRunScope | None = None): ...
    # scope=None 이면 호출마다 masker.new_scope()
    async def ainvoke(self, input, config=None, **kw): ...
    def invoke(self, input, config=None, **kw): ...
    def with_structured_output(self, *a, **k) -> "GuardedLlm": ...
    def bind_tools(self, *a, **k) -> "GuardedLlm": ...
    def bind(self, **k) -> "GuardedLlm": ...
    def __getattr__(self, name): ...   # 내부 객체 속성 위임
```

- 입력은 str, 메시지 리스트, PromptValue를 메시지로 정규화한다. `prompt | guarded` 체인이 동작한다.
- `scope=None`이면 호출마다 새 scope를 쓴다. 보조 LLM은 앱 싱글턴이고 입력 전체에 원본이 있으므로 호출 단위 vault로 일관성이 유지된다.
- `config`(tags, callbacks)는 그대로 전달한다. `INTERNAL_LLM_TAG` 동작은 변하지 않는다.
- `create_agent`에는 넘기지 않는다. 런타임은 raw 모델에 `bind_tools`를 호출해야 한다.

### 4.5 PlaceholderStreamRestorer (application)

```python
class PlaceholderStreamRestorer:
    def __init__(self, service, scope): ...
    def feed(self, llm_run_id: str, chunk: str) -> str: ...
    def flush(self, llm_run_id: str) -> str: ...
```

- 끝부분이 placeholder 접두(`[`, `[PH`, `[PHONE_`, `[PHONE_1`)이면 보류하고 나머지를 원복해 반환한다. 보류 길이는 24자로 제한한다.
- 병렬 워커 토큰이 섞이므로 LLM 호출의 `run_id`별로 버퍼를 분리한다.
- `on_chat_model_end`에서 flush한다. 보류분이 있으면 TOKEN 이벤트를 1건 추가한다.

### 4.6 MCP 검사

```python
class PiiInspectPort(Protocol):
    def inspect(self, value: object) -> dict[PiiType, int]: ...
    def find_orphan_argument(self, value: object) -> str | None: ...  # v0.6, shadow 는 항상 None
```

| 지점 | 시점 | 동작 |
|------|------|------|
| `MCPToolAdapter._arun` | placeholder URL 검사 다음 | 인자 inspect, `find_orphan_argument`가 값을 돌려주면 교정 문구 반환 |
| `MCPToolAdapter._call` | 결과 수신 후 | 결과 inspect |
| `McpActionExecutor` 집행 | 호출 전후 | 동일 |

기록은 `logger.info("MCP PII inspected", direction, tool_id, counts, request_id)`이며 값은 남기지 않는다. 건수 0이면 기록하지 않는다. MCP로 나가는 인자와 받은 결과의 값은 바꾸지 않고, 결과는 다음 LLM 호출에서 마스킹된다. 파이프라인이 `tool.ainvoke`로 호출해도 어댑터를 지나므로 react 워커와 같은 지점에서 처리된다.

---

## 5. UI/UX Design

해당 없음. 화면에 보이는 텍스트는 현재와 같다.

---

## 6. Error Handling

### 6.1 결정

| ID | 결정 | 사유 |
|----|------|------|
| D-01 | 카탈로그에 등록하지 않고 컴파일러가 항상 맨 앞에 부착 | 카탈로그로 끄면 미들웨어만 꺼지고 프록시가 살아 있어 경계가 절반만 해제된다. 스냅샷에서 뺄 수 없으므로 P2가 해제할 수 없다 |
| D-02 | 모드는 `Literal["shadow", "on"]`, 오타는 기동 실패 | prompt guard의 "오타로 조용히 해제"(G-10) 재발 방지 |
| D-03 | 해제는 `PII_MASKING_ENABLED=false` 하나 | 킬스위치 단일화 |
| D-04 | 사내 모델도 마스킹 (FR-15 이월) | 폴백이 외부 모델로 넘어가면 우회된다. 마스킹해도 사내 모델 동작에 문제가 없다 |
| D-05 | 응답의 미매핑 PII redact 제거 | 토큰과 최종 답변 결과가 달라지고, 정상 도구 인자를 훼손한다. LLM이 원본을 모르므로 이득이 작다 |
| D-06 | LangSmith는 기동 경고 (FR-17) | 체인 단위 추적은 상태 원본을 기록하며 모델 경계에서 막을 수 없다. `langsmith_tracing=true`이고 on 모드면 경고 |
| D-07 | prompt guard 규칙 검사는 원문, 판정 LLM 입력만 마스킹 | `UtilityLLMProvider` 래핑으로 자동 적용 |
| D-08 (v0.5) | 구조화 출력은 알려진 placeholder만 원복하고 고아를 남긴다. 고아 인자는 도구 경계(MCP 어댑터·집행기·미들웨어)가 차단 | search·collect·action 파이프라인은 구조화 출력을 그대로 `tool.ainvoke` 인자로 쓴다. 본문과 같은 규칙(고아 redact)이면 `[REDACTED_EMAIL]`로 MCP가 실행된다 |
| D-09 (v0.5) | 보조 LLM은 `UtilityLLMProvider`를 고치지 않고 넘기는 팩토리를 `PiiGuardedLLMFactory`로 감싼다 | 공급자의 캐시 로직을 건드리지 않는다. 같은 팩토리를 차트·엑셀 viz LLM과 도구 선별기에 재사용한다. compiler는 raw 팩토리 유지(계약 테스트로 고정) |
| D-10 (v0.5, v0.6 수정) | MCP 경계(어댑터·집행기)의 고아 판정은 vault 없이 형태로 한다 (`PiiToolArgumentPolicy`). **on 모드에서만** 차단한다(`PiiInspectPort.find_orphan_argument`). 미들웨어는 런 vault를 가지므로 vault 기준(`has_orphan`)으로 판정한다 | 도구 경계에 도달한 인자는 이미 원복을 거쳤으므로 남은 `[TYPE_n]`은 정의상 고아다. on 모드에서 사용자가 직접 입력한 `[PHONE_1]` 문자열이 막히는 부작용은 수용. shadow는 LLM이 placeholder를 받은 적이 없어 차단이 부작용뿐이므로 막지 않는다(Check G-3) |
| D-11 (v0.6) | placeholder가 실제로 나간 요청에는 system 끝에 안내(`PII_PLACEHOLDER_NOTICE`)를 붙인다. system이 없으면 안내만 담은 SystemMessage를 만든다 | 안내가 없으면 "확인된 값만 써라" 규칙을 가진 action 인자 작성 LLM이 `[EMAIL_1]`을 미확인 값으로 보고 `grounded=false`로 도구 호출을 포기한다. 승인 스모크 실런에서 재현(§8.8). 안내 문구에는 번호 있는 예시를 넣지 않는다 |
| D-12 (v0.6) | FR-13 관측: ai_run 스텝은 에이전트 런 정상 종료 시, 요약 로그(`PII masking summary`)는 모든 종료 경로(실패·한도 초과·승인 재개·일반 채팅)에 남긴다 | shadow 집계가 실패 런·일반 채팅을 빠뜨리지 않게 한다. 실패 경로에서 DB 스텝을 쓰면 원래 오류 처리와 얽혀 로그로 한정 |

### 6.2 실패 처리

| 상황 | shadow | on |
|------|--------|-----|
| 서비스 조립 실패 | warning 후 None, 실행 계속 | 기동 실패 |
| 탐지 예외 | warning, 요청 그대로 전송 | 해당 메시지를 `[PII_MASKING_FAILED]`로 대체 + error 로그(스택 포함). 다른 메시지는 유지 |
| 답변의 고아 placeholder | 해당 없음 | `[REDACTED_<TYPE>]` + warning |
| 도구 인자의 고아 placeholder | 해당 없음 | 도구 미호출, 교정 지시 ToolMessage |
| 입력에 `[PHONE_1]` 문자열이 이미 존재 | 해당 없음 | `reserve_literals`로 해당 번호를 건너뛰고, 복원 시 원문 그대로 둠 |
| 스트림 종료 시 미완성 보류분 | 해당 없음 | 원복 후 내보냄 |
| MCP inspect 예외 | warning, 호출 계속 | 동일. 검사가 도구 실행을 막지 않음 |

---

## 7. Security Considerations

- [ ] vault, placeholder 매핑, 원문을 로그·ai_run·이벤트에 기록하지 않음. 타입별 건수만
- [ ] `PiiRunScope`는 지역 객체로 전달하고 전역·DB·캐시에 두지 않음
- [ ] 런 간 vault 공유 없음. 앱 싱글턴 어댑터는 호출 단위 scope
- [ ] 알려진 잔여 위험: 외부 도구 인자, 임베딩 API, 이미지 바이트, 이름·주소, LangSmith 체인 추적, 대화 경로 외 LLM

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Corpus | 탐지 정확도 | pytest + 픽스처 | Do |
| Unit | masker, proxy, middleware, stream restorer | pytest | Do |
| Graph | compile된 그래프 실행(스크립트 모델로 전송 요청 캡처) | pytest | Do |
| Contract | AST 우회 검사 | pytest | Do |
| Real run | 실제 LLM, REST·WS | TestClient 인프로세스 | Do |

### 8.2 코퍼스 (`tests/fixtures/pii_masking/`)

| 파일 | 내용 | 기준 |
|------|------|------|
| `pii_ko.txt` | 조사 결합, 공백 구분, 표 셀, 괄호, 콜론 뒤, 은행별 계좌 형식 | 누락 0건 |
| `benign_ko.txt` | 날짜, 금액(`1000000000원`, `1,000,000,000`), 금리, 규정 조문, 표 숫자, 사업자번호, 시행령 번호 | 오탐 0건 |
| `known_fp.txt` | 허용 오탐(법인등록번호, 문서번호) + 사유 | 현 상태 고정 |

### 8.3 시나리오

| # | 시나리오 | 기대 |
|---|---------|------|
| 1 | `010-1234-5678로 보내줘` | LLM 입력에 원본 없음, 답변은 원본 |
| 2 | system + 메모리 + 이력 + 도구 결과의 동일 PII | 같은 placeholder |
| 3 | 병렬 워커 2개 토큰 교차 | 원복 정확, 조각 노출 없음 |
| 4 | 토큰을 1자씩 분할 | 조각 노출 없음 |
| 5 | 승인 필요 도구 + 이메일 | 승인 초안·`tool_args`·집행 인자 원본 |
| 6 | 재개(`resume_from_snapshot`) | 새 scope에서 정상 |
| 7 | 서브에이전트 | 자식 compile에 scope 전달 |
| 8 | supervisor 구조화 출력의 reason에 placeholder | 원복 |
| 9 | 근거 판정 재작성 루프 | 정상 답변이 오판되지 않음 |
| 10 | 환각 placeholder `[EMAIL_9]`를 도구 인자로 | 도구 미호출 |
| 11 | shadow | LLM 입력이 원문과 동일, 건수 기록 |
| 12 | 해제 | 프록시·미들웨어 미부착 |
| 13 | MCP react·파이프라인·승인 집행 | 세 경로 모두 검사 로그, 값 불변 |
| 14 | 이미지 첨부 | 이미지 블록 불변 |
| 15 | 카테고리 파이프라인 폴백 LLM | 캐시된 pipeline_llm도 보호 |

### 8.4 계약 테스트

| 테스트 | 검사 |
|--------|------|
| `test_create_agent_sites` | `workflow_compiler.py`, `general_chat/use_case.py`의 `create_agent` 호출이 PII 미들웨어를 포함 |
| `test_direct_chat_model_allowlist` | `src/` 전체의 `ChatOpenAI(`, `ChatAnthropic(`, `ChatOllama(` 생성 지점이 허용 목록과 일치. 목록의 각 항목은 사유 포함 |
| `test_utility_provider_guarded` | `UtilityLLMProvider.get()` 반환이 프록시 |
| `test_no_pii_in_logs` | scope·vault 값이 logger 인자로 전달되지 않음 |

### 8.5 실런 DoD

module-3 완료 시 on 모드 실런 1회를 필수로 한다. 전송 요청 로그로 원본 부재를 확인하고, 실모델이 placeholder를 유지하는 비율을 기록한다.

### 8.6 module-3 실런 결과 (2026-11-03)

TestClient 인프로세스, gpt-4o-mini, 고객 문의 MCP 2종(`list_inquiries`, `get_inquiry`)을 붙인 L3 에이전트, REST·WS 각 1회. `ChatOpenAI._get_request_payload`와 `MCPToolAdapter._arun`을 프로세스 안에서 감싸 기록했다(코드 무수정).

| 항목 | 결과 |
|------|------|
| 외부 요청 | 경로당 8건. supervisor·react 워커·final_answer 7건은 placeholder만 포함 |
| 누출 | 1건/경로 — **근거 판정 LLM**(`get_grounding_judge_llm_provider`). module-4 범위의 보조 LLM이라 아직 프록시 미적용 |
| 실모델 placeholder 유지 | 답변에 `[REDACTED_]` 0건, 원본 복원. 변형 0건 |
| 토큰 | WS TOKEN 223건, placeholder 조각 0건 |
| 미검증 | MCP 결과의 PII 마스킹 — LLM이 필수 인자 `board`를 빠뜨려 도구가 오류만 반환. module-4 실런에서 재확인 |

**on 전환 금지 조건**: module-4(보조 LLM 프록시) 완료 전에는 on 모드에서도 근거 판정으로 원문이 나간다. → module-4에서 해소(§8.7).

### 8.7 module-4 실런 결과 (2026-11-03)

같은 조건에 일반 채팅 REST·WS를 추가하고, 에이전트 질문에 `board=customer`를 넣어 MCP 조회가 성공하게 했다.

| 경로 | 외부 요청 | 원본 PII |
|------|-----------|----------|
| 에이전트 REST | 6건 (근거 판정 포함) | 0건 |
| 에이전트 WS | 6건 | 0건 |
| 일반 채팅 REST | 2건 (도구 선별기 포함) | 0건 |
| 일반 채팅 WS | 3건 (차트 분류기 포함) | 0건 |

- 토큰 574건 조각 노출 0건, 답변 `[REDACTED_]` 0건.
- **미검증**: 고객 문의 MCP는 연락처를 서버에서 `010-****-4222`로 마스킹해 돌려준다. 실제 PII가 담긴 MCP 결과로는 검사·마스킹을 확인하지 못했다(단위·그래프 테스트로만 검증).
- **답변 품질 비교**(일반 채팅, 질문 2종 × 3회): shadow(원문 전송)는 주민번호가 포함된 질문에서 3회 중 2회 답변을 거부했고 연락처를 넣은 답은 0회였다. on은 6회 모두 연락처·이메일을 넣어 답했다. 마스킹은 품질을 떨어뜨리지 않았으나, 사용자가 넣은 개인정보를 다시 쓰는 데 대한 모델 자체의 안전장치는 작동하지 않게 된다.

### 8.8 승인 스모크 실런 (2026-11-05, Check Act-1)

gpt-4o-mini, Outlook Mail MCP `send_mail`(승인 필요) 1개를 가진 L3 에이전트. 질문에 수신자 이메일과 본문 속 전화번호를 넣었다. 집행 단계의 `MCPCallClient.call_tool`은 프로세스 안에서 가로채 인자만 기록하고 가짜 성공을 돌려줬다(실제 메일 미발송).

| 단계 | D-11 전 | D-11 후 |
|------|---------|---------|
| 런 | action 인자 작성 LLM이 `grounded=false`, "수신자 이메일 주소(EMAIL_1)… 확인하지 못했습니다"로 종료. 승인 건 0 | 승인 대기 1건 |
| 승인 초안 `tool_args.to` | — | `lee.test@example.com` (원본) |
| 집행 인자 `to` | — | `lee.test@example.com` (원본) |
| 외부 요청 원본 PII | 0건 (11건) | 0건 (런 8건 + 재개 5건) |

- D-11 전 답변에 괄호 없는 `EMAIL_1`이 그대로 노출됐다(원복 패턴은 괄호를 요구). D-11 후 재현되지 않았다.
- 초안 본문이 요청 문구와 다르게 생성되는 현상("고객센터로 문의해 주세요.")은 shadow에서도 같다("메일을 보낼 수 없습니다."). action 초안 생성기의 기존 동작이며 이 기능과 무관하다.

---

## 9. Clean Architecture

### 9.1 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `PiiMaskingMode`, `PiiRunScope`, `TokenVault` | Domain | `src/domain/pii_masking/schemas.py` |
| 패턴, 계좌·날짜·금액 규칙 | Domain | `src/domain/pii_masking/patterns.py`, `policies.py` |
| `PiiInspectPort`, `PiiDetectorPort` | Domain | `src/domain/pii_masking/interfaces.py` |
| `PiiMaskingService` | Application | `src/application/pii_masking/pii_masking_service.py` |
| `PiiMessageMasker` | Application | `src/application/pii_masking/message_masker.py` |
| `GuardedLlm` | Application | `src/application/pii_masking/guarded_llm.py` |
| `PiiMaskingMiddleware` | Application | `src/application/pii_masking/middleware.py` |
| `PlaceholderStreamRestorer` | Application | `src/application/pii_masking/stream_restorer.py` |
| `RegexPiiDetector` | Infrastructure | `src/infrastructure/pii_masking/regex_detectors.py` |
| DI | Interfaces | `src/api/main.py` |

### 9.2 Import 규칙

- `MCPToolAdapter`(infrastructure)는 domain의 `PiiInspectPort`만 참조한다.
- langchain 미들웨어 클래스 참조는 `middleware.py`와 `MiddlewareBuilder`에 한정한다(D8, `gate_middleware.py` 선례).

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 탐지 규칙 | 패턴 본문은 `patterns.py`, 변경 사유는 docstring에 기록. Design에 복제하지 않음 |
| 설정 | 새 키에 소비 지점 파일을 docstring으로 명기 |
| 탈착 | 협력자는 optional 마지막 인자, `None`이면 기존 경로 유지 |
| 로그 | `exception=e` 스택 포함, 값 미기록 |

### 10.1 탐지 재작성 규칙

| 항목 | 현재 | 변경 |
|------|------|------|
| 숫자 경계 | `\b` | 숫자·대시 lookaround로 교체. 한글 조사 결합 허용 |
| EMAIL | `\w` (한글 포함) | ASCII 문자 클래스, 도메인 끝은 영문 2자 이상 |
| 대시 | 하이픈 | 전각 대시(–, —) 포함. PDF 추출본 대응 |
| PHONE 구분자 | 하이픈, 공백 | 점, 괄호, 공백 낀 대시, `+82` 추가. 유선은 실제 지역번호로 한정 |
| CARD | 임의 위치 공백·하이픈 허용 | 4-4-4-4, 4-6-5, 4-6-4, 연속 13~19자리만. 앞뒤 숫자 그룹이 이어지면 제외 |
| ACCOUNT 구분자 | 하이픈 또는 공백 | 대시만. 표 숫자 오탐 제거 |
| ACCOUNT 그룹 | 2~6자리, 3그룹 | 2~7자리, 3~4그룹. `3333-01-1234567`, `302-1234-5678-91` 탐지 |
| ACCOUNT 총 자릿수 | 제한 없음 | 10~14자리. 날짜 `2026-11-02` 제외 |
| ACCOUNT 연속 숫자 | 10~14 | 금액 단위(원, 만, 억 등)가 뒤따르면 제외 |
| 사업자번호 | ACCOUNT | 3-2-5 형식 + 체크섬 통과 시 제외 |
| RRN | 형식 + 생년월일 + 성별 | 유지. 체크섬은 2020년 이후 번호에 적용 불가 |

### 10.2 Environment Variables

| 변수 | 기본값 | 소비 지점 |
|------|--------|-----------|
| `PII_MASKING_ENABLED` | `true` | `main.py get_pii_masker()` |
| `PII_MASKING_MODE` | `shadow` | `PiiMaskingConfig.from_settings` |
| `PII_MASKING_TYPES` | `rrn,phone,email,card,account` | `PiiMaskingConfig.from_settings` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/domain/pii_masking/          (수정) schemas, patterns, policies, interfaces
src/application/pii_masking/
├── pii_masking_service.py       (수정)
├── message_masker.py            (신규)
├── guarded_llm.py               (신규)
├── middleware.py                (신규)
├── guarded_llm_factory.py       (신규, D-09)
└── stream_restorer.py           (신규)
src/infrastructure/pii_masking/regex_detectors.py   (수정)
src/application/middleware/middleware_builder.py    (수정) build_pii_masking
src/application/agent_builder/workflow_compiler.py  (수정) raw/guarded 분리, scope 전달
src/application/agent_builder/run_agent_use_case.py (수정) scope, 토큰, 스텝, 요약 로그
src/application/general_chat/use_case.py            (수정) 미들웨어, 토큰, reasoning, 요약 로그
src/infrastructure/conversation/langchain_{llm,summarizer}.py (수정) optional llm_guard
src/infrastructure/mcp/tool_adapter.py, tool_registry.py      (수정)
src/infrastructure/mcp_registry/mcp_tool_loader.py  (수정) inspector 전달
src/infrastructure/approval/mcp_executor.py         (수정)
src/api/main.py, src/config.py, .env.example        (수정)
(UtilityLLMProvider 는 수정하지 않음 — D-09)
tests/fixtures/pii_masking/                         (신규)
```

보조 LLM 처리 목록:

| 어댑터 | 경로 | 처리 |
|--------|------|------|
| hallucination, memory extractor, search_decision, intent, prompt_guard judge, prompt_composer, 위키 distiller, eval qa_generator | `UtilityLLMProvider` | `get()` 래핑으로 자동 |
| `llm_tool_selector` | `LLMFactory` | main.py 주입 시 guard |
| `LangChainSummarizer`, `LangChainConversationLLM` | 직접 생성 | optional `llm_guard` |
| 차트·엑셀 viz LLM | `_llm_factory.create` | main.py에서 guard |
| hallucination 레거시 ChatOpenAI 분기, memory extractor 폴백 | 직접 생성 | 프록시 적용 또는 허용 목록 사유 기록 |
| query_rewrite, multi_query | 직접 생성 | 대화 경로 사용 여부를 Do에서 확인 후 결정 |
| ingest, ragas, research_agent, compressor, 레거시 `llm_adapter` | 직접 생성 | 허용 목록 |

### 11.2 Implementation Order

1. [ ] 코퍼스 작성 → 탐지 재작성 (Red→Green)
2. [ ] vault·scope·service 재구성, 삭제 항목 정리, 설정
3. [ ] masker → stream restorer → proxy → middleware
4. [ ] compile raw/guarded 분리, RunAgentUseCase 배선, 그래프 테스트
5. [ ] 에이전트 경로 on 모드 실런
6. [ ] GeneralChat, 보조 LLM, MCP, 관측, 계약 테스트
7. [ ] 일반 채팅 실런, `/verify-*`, `FAILED` 목록 diff

### 11.3 Session Guide

> Use `/pdca do pii-masking-integration --scope module-N` to implement one module per session.

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 탐지 재작성 + 코퍼스 + scope | `module-1` | 패턴·정책·vault·service·설정. 배선 없음 | 25-35 |
| 코어 4종 | `module-2` | masker, stream restorer, proxy, middleware. 스크립트 모델 그래프 테스트 | 30-40 |
| 에이전트 경로 | `module-3` | compile, RunAgentUseCase, 재개, 서브에이전트, ai_run 스텝, 실런 | 35-45 |
| 일반 채팅 + 보조 LLM + MCP | `module-4` | GeneralChat, UtilityLLMProvider, 어댑터, MCP 3경로, 계약 테스트, 실런 | 35-45 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1` | 25-35 |
| Session 3 | Do | `--scope module-2` | 30-40 |
| Session 4 | Do | `--scope module-3` | 35-45 |
| Session 5 | Do | `--scope module-4` | 35-45 |
| Session 6 | Check + Report | 전체 | 30-40 |

### 11.4 FR 추적

| FR | Design | Module |
|----|--------|--------|
| FR-01, 02 | §4.2, §4.3 | 2 |
| FR-03 | §6.1 D-01 | 3, 4 |
| FR-04 | §6.2 | 1 |
| FR-05 | §4.4 | 3 |
| FR-06 | §11.1 보조 LLM 표 | 4 |
| FR-07 | §8.4 | 4 |
| FR-08 | §3.1 | 1, 3 |
| FR-09 | §4.5 | 2, 3, 4 |
| FR-10, 11 | §4.6 | 4 |
| FR-12 | §2.2, §6.2 | 1, 2 |
| FR-13 | run 종료 시 `pii_masking` 스텝(`NodeType.OTHER`, 요약은 모드와 타입별 건수) | 3 |
| FR-14 | §10.1, §8.2 | 1 |
| FR-15 | §6.1 D-04 이월 | 해당 없음 |
| FR-16 | §4.2 | 2 |
| FR-17 | §6.1 D-06 | 4 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | 초안. Option C 선택, 스파이크·엔진 실행 결과 반영 | 배상규 |
| 0.2 | 2026-11-02 | module-1 구현 반영: 서비스 인자를 scope로 변경, `has_orphan` 추가, 탐지 규칙 표 확장(대시, 괄호, CARD 형식) | 배상규 |
| 0.3 | 2026-11-03 | module-2 구현 반영: 도구 인자는 고아 placeholder를 redact하지 않고 유지(`restore_known_text`). redact하면 `[REDACTED_EMAIL]`로 도구가 실행되는 결함을 그래프 테스트가 발견 | 배상규 |
| 0.4 | 2026-11-03 | module-3 구현 반영: 승인 재개는 compile의 scope 자동 생성으로 보호(별도 배선 없음). §8.6 실런 결과, on 전환 금지 조건 추가 | 배상규 |
| 0.5 | 2026-11-03 | module-4 구현 반영: D-08(구조화 출력 고아 유지 + 도구 경계 차단), D-09(PiiGuardedLLMFactory), D-10(형태 기반 고아 판정). 일반 채팅 STEP_REASONING 원복 추가. §8.7 실런·품질 비교 결과 | 배상규 |
| 0.6 | 2026-11-05 | Check Act-1 반영: D-10 수정(MCP 고아 차단은 on 모드만), D-11(placeholder 안내), D-12(FR-13 요약 로그 전 경로), §8.8 승인 스모크. §4.4·§4.6·§10.2·§11.1 드리프트 정리 | 배상규 |
