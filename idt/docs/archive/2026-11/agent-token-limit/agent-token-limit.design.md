# agent-token-limit Design Document

> **Summary**: `agent_definition.token_limit`(V085, 기본 50000, 8000~500000)을 단일 소스로 두고 생성/수정/조회/포크 API·Studio 설정 패널·실행 경로(루트·승인 재개·서브 에이전트)에 배선한다. 토큰 한도 가드는 반복 한도 가드와 같은 `limit_reached` 신호에 `limit_reason`("iteration" | "token")을 더해 final_answer 안내 문구·`ANSWER_COMPLETED` payload·채팅 배지까지 사유를 구분한다.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front Studio/Chat)
> **Author**: 배상규
> **Date**: 2026-11-05
> **Status**: Draft
> **Planning Doc**: [agent-token-limit.plan.md](../../01-plan/features/agent-token-limit.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 토큰 한도가 코드 상수 8000으로 전 에이전트 고정이라 긴 수집 1회로 후속 워커가 실행되지 못하고, 한도 종료 사실도 사용자에게 전달되지 않는다. |
| **WHO** | P2 KB 운영자/에이전트 소유자(설정), 최종 사용자(완주된 답변 또는 한도 안내). |
| **RISK** | 기본값 상향으로 LLM 비용 상한이 느슨해진다 → 반복 한도가 2차 상한으로 남고, 범위 상한 500000으로 캡. 토큰 가드가 `limit_reached`를 세우면서 되물음 루프 회귀 가능 → 기존 Gap-06 테스트 유지·확장. |
| **SUCCESS** | 2026-11-05 재현 런(스크랩→분석→발표자료)이 기본값으로 완주. 에이전트별 값이 API·UI 왕복 보존. 토큰 한도 도달 시 final_answer 안내와 `limit_reached` 플래그가 반복 한도와 동일하게 나간다. 기존 회귀 테스트 전부 통과. |
| **SCOPE** | DB(V085)+도메인 정책 → 유스케이스/API 스키마 → 실행 경로(루트·서브·재개) → 프론트 타입/설정 패널/배지. 집계 방식 변경·서브 에이전트 상속 규칙 복원은 범위 밖. |

---

## 1. Overview

### 1.1 Design Goals

1. `token_limit`의 출처를 `agent_definition` 한 곳으로 모으고, `max_iterations`와 **같은 배선 지점**을 그대로 거친다(누락 방지).
2. 토큰 한도 도달을 반복 한도 도달과 **같은 종료 경로**(limit_reached → final_answer 안내 → payload)로 합치되, 사유를 구분하는 키 하나만 **additive**로 더한다.
3. 서브 에이전트는 컴파일 시 이미 로드된 자기 정의의 값을 쓴다. 부모 절반 상속 코드는 제거한다.
4. 집계 방식(산출 글자 수 ÷ 4)·되물음 불변식(`_challenge_reset`)·라우팅 함수는 건드리지 않는다.

### 1.2 Design Principles

- **선례 복제**: agent-recursion-limit(V045)의 정책·엔티티·스키마·유스케이스·프론트 배선을 1:1로 따른다.
- **Additive only**: state·payload·타입에 새 키만 추가한다. 기존 키의 의미는 `limit_reached`가 토큰 도달에도 True가 되는 것 하나만 바뀐다(Plan 결정).
- **도메인이 최종 방어선**: 범위 검증은 `TokenLimitPolicy`가, API는 422로 조기 거부.
- **프론트 안내는 기존 패턴**: `excluded_tools` 안내문과 같은 stream 훅 → ChatPage → Message → MessageBubble 경로.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 배선 복제, `limit_reached`만 공유, 사유 없음 | `ExecutionBudget` VO로 반복·토큰 한도 통합 재구성 | 배선 복제 + 독립 `TokenLimitPolicy` + `limit_reason` additive |
| **New Files** | 1 | 4~5 | 3 (V085, limitNotice.ts, LimitNumberField.tsx) |
| **Modified Files** | 백 12 / 프 6 | 백 18+ / 프 6 | 백 14 / 프 11 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Low | Medium (state 구조 변경 → 재개 스냅샷 영향) | Low |

**Selected**: Option C — **Rationale**: 재개 스냅샷·기존 테스트에 영향을 주지 않으면서 사유 구분이 가능하다(사용자 선택, 2026-11-05).

### 2.1 Component Diagram

```
[Studio SettingsPanel] ──token_limit──▶ [POST/PUT /agents] ──▶ [create/update UseCase] ──▶ [AgentDefinition(domain, TokenLimitPolicy.validate)]
                                                                                              │
                                                                                              ▼
                                                                               [agent_definition.token_limit (V085)]
                                                                                              │ find_by_id
          ┌───────────────────────────────────────────────────────────────────────────────────┤
          ▼                                                                                   ▼
[run_agent_use_case :985/:1363]                                              [workflow_compiler._compile_sub_agent :1426]
  SupervisorConfig(max_iterations, token_limit=agent.token_limit)              sub_agent.token_limit ──▶ _wrap_sub_agent(token_limit=…)
          │                                                                                   │
          ▼                                                                                   ▼
[build_initial_state] state.token_limit / limit_reached=False / limit_reason=""   [sub graph initial state]
          │
          ▼
[supervisor_node 가드]  token_usage >= token_limit → {next_worker:"__end__", limit_reached:True, limit_reason:"token", **_challenge_reset()}
          │
          ▼
[route_to_worker_or_final] (변경 없음) ── limit_reached → final_answer
          │
          ▼
[final_answer_node]  limit_reason별 안내 블록 ("[토큰 한도 도달 안내]" / "[반복 한도 도달 안내]")
          │
          ▼
[run_agent_use_case latch] state.limit_reached / state.limit_reason ──▶ _answer_payload(limit_reached=True, limit_reason="token")
          │
          ▼
[useAgentRunStream] limitReached/limitReason ──▶ [ChatPage] ──▶ [Message.limitReason] ──▶ [MessageBubble 배지]
```

### 2.2 Data Flow

```
설정:   SettingsPanel(tokenLimit draft → clamp) → form.tokenLimit → create/update 요청 token_limit → 422 또는 저장 → detail 응답 token_limit → agentDetailMapping → form 프라임
실행:   agent.token_limit → SupervisorConfig → state.token_limit → 가드 → limit_reached+limit_reason → final_answer 안내 → payload → 배지
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `TokenLimitPolicy` | 없음 (domain) | DEFAULT/MIN/MAX/validate |
| `AgentDefinition` | `TokenLimitPolicy` | `__post_init__` 검증 |
| `SupervisorConfig` | `TokenLimitPolicy.DEFAULT` | 기본값 단일 소스 |
| `supervisor_node` 토큰 가드 | `_challenge_reset` | 되물음 불변식 유지 |
| `final_answer_node` | `state.limit_reason` | 안내 문구 분기 |
| `_answer_payload` | `_StreamState.limit_reason` | payload 사유 |
| `MessageBubble` | `utils/limitNotice.ts` | 배지 문구 |
| `SettingsPanel` | `constants/agentSettings.TOKEN_LIMIT`, `LimitNumberField` | 입력·clamp |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# src/domain/agent_builder/policies.py — D2
class TokenLimitPolicy:
    """supervisor 토큰 예산 도메인 규칙 (agent-token-limit D2).
    단위는 SupervisorState.token_usage(워커 산출 글자 수 ÷ 4 누적 추정치) — 실제 LLM 토큰이 아니다.
    """
    DEFAULT = 50000
    MIN = 8000
    MAX = 500000

    @classmethod
    def validate(cls, value: int) -> None:
        if not (cls.MIN <= value <= cls.MAX):
            raise ValueError(f"token_limit는 {cls.MIN}~{cls.MAX} 범위여야 합니다. (입력값: {value})")

# src/domain/agent_builder/schemas.py — D3
@dataclass(frozen=True)
class SupervisorConfig:
    max_iterations: int = IterationLimitPolicy.DEFAULT
    token_limit: int = TokenLimitPolicy.DEFAULT        # 8000 → 정책 상수
    ...

@dataclass
class AgentDefinition:
    ...
    max_iterations: int = IterationLimitPolicy.DEFAULT
    # agent-token-limit D3: supervisor 토큰 예산 (기본 50000, 8000~500000). 실행 시 SupervisorConfig 단일 소스.
    token_limit: int = TokenLimitPolicy.DEFAULT
    def __post_init__(self):
        ...
        IterationLimitPolicy.validate(self.max_iterations)
        TokenLimitPolicy.validate(self.token_limit)
```

`with_updates`류 복사 경로(`schemas.py:144-162`의 `max_iterations: int | None = None` 패턴)에 `token_limit: int | None = None`을 같은 형태로 추가한다.

### 3.2 SupervisorState 추가 키 (D8)

```python
# src/application/agent_builder/supervisor_state.py
limit_reached: bool          # 기존 — 토큰 도달에도 True
# agent-token-limit D8: 한도 도달 사유 ("iteration" | "token" | ""). limit_reached와 함께 세워진다.
# final_answer 안내 문구·payload 사유 분기에만 쓰이고 라우팅은 읽지 않는다.
limit_reason: str
```

`build_initial_state`(`supervisor_nodes.py:330-360`)에 `"limit_reason": ""` 추가. 재개 스냅샷(`final_state`)은 키 부재 시 `state.get("limit_reason", "")`로 읽는다(하위호환).

### 3.3 Database Schema (D1)

```sql
-- V085__alter_agent_definition_add_token_limit.sql
-- agent-token-limit Design D1: supervisor 토큰 예산을 에이전트별로 둔다 (기본 50000 / 범위 8000~500000은 도메인 정책 검증).
-- 단위는 워커 산출 글자 수 ÷ 4 누적 추정치. 기존 행은 DEFAULT 적용. additive.
-- ⚠️ COMMENT 안에 콤마 금지 — tests/db/test_migration_ddl_comments.py 파서 제약.

ALTER TABLE agent_definition
  ADD COLUMN token_limit INT NOT NULL DEFAULT 50000
  COMMENT 'supervisor 토큰 예산 상한 — 워커 산출 글자수÷4 누적 추정치 기준이며 범위는 도메인 정책이 검증'
  AFTER max_iterations;
```

```python
# src/infrastructure/agent_builder/models.py
# agent-token-limit V085: supervisor 토큰 예산 (기본 50000, 범위는 도메인 정책 검증).
token_limit: Mapped[int] = mapped_column(
    nullable=False, default=50000,
    comment="supervisor 토큰 예산 상한 — 워커 산출 글자수÷4 누적 추정치 기준이며 범위는 도메인 정책이 검증",
)
```

Repository: `agent_definition_repository.py:40`(save), `:117`(update), `:432`(row→entity)에 `token_limit` 1줄씩.

---

## 4. API Specification

### 4.1 Endpoint List (변경 없음 — 필드 추가만)

| Method | Path | 변경 |
|--------|------|------|
| POST | /api/v1/agents | 요청 `token_limit?` (기본 50000) / 응답 `token_limit` |
| PUT | /api/v1/agents/{id} | 요청 `token_limit?` (None = 변경 없음) / 응답 `token_limit` |
| GET | /api/v1/agents/{id} | 상세 응답 `token_limit` |
| POST | /api/v1/agents/{id}/fork | 원본 값 복사 (FR-08) |

### 4.2 Schema (D4)

```python
# src/application/agent_builder/schemas.py
class CreateAgentRequest:      token_limit: int = Field(50000, ge=8000, le=500000)
class UpdateAgentRequest:      token_limit: int | None = Field(None, ge=8000, le=500000)   # None = 변경 안 함
class CreateAgentResponse:     token_limit: int = 50000
class GetAgentResponse:        token_limit: int = 50000   # edit 폼 프라임용
```

> Check 정정(G-4): `UpdateAgentResponse`는 `max_iterations`도 싣지 않는 기존 구조라 `token_limit`도 싣지 않는다. 프론트는 수정 후 상세를 재조회하므로 영향 없음. §4.1의 PUT 행은 "요청만"으로 읽는다(실제 메서드는 PATCH).

범위 밖 → FastAPI 422 (`ge/le`). 도메인 `ValueError`는 2차 방어(유스케이스 테스트에서 직접 검증).

### 4.3 `ANSWER_COMPLETED` payload (D10)

```json
{
  "answer": "...",
  "tools_used": ["..."],
  "limit_reached": true,          // 기존 — 반복·토큰 어느 쪽이든 True
  "limit_reason": "token"         // 신규 additive: "iteration" | "token". limit_reached가 없으면 함께 없다.
}
```

`_answer_payload`는 truthy 플래그만 싣는다 — `limit_reason=""`이면 키가 생략된다. 검증: `test_agent_token_limit_runtime.py::TestAnswerCompletedLimitReason::test_reason_absent_when_not_reached` (Check 정정 G-6: 이전에 적은 `test_answer_payload_contract`는 존재하지 않는 이름).

---

## 5. UI/UX Design

### 5.1 Screen Layout — Studio 설정 탭 (D12)

```
┌ 에이전트 실행 설정 ───────────────────────────────┐
│ ⚙ Recursion Limit                                  │
│   ⓘ 반복 실행 최대 횟수 …                            │
│   최대 반복 횟수  [  25 ] ↺  (범위: 10 - 1000)        │
│                                                     │
│ ⚙ Token Limit                        ← 신규 섹션     │
│   ⓘ 한 번의 실행에서 워커 산출물에 쓸 수 있는 토큰 예산입니다. │
│      긴 수집 결과가 많으면 값을 올리세요. (추정치 기준)       │
│   토큰 예산      [ 50000 ] ↺  (범위: 8000 - 500000)   │
│   기본값: 50000.                                     │
│                                                     │
│ Webhook … / MCP … / Telegram …                      │
└─────────────────────────────────────────────────────┘
```

### 5.2 Screen Layout — 채팅 답변 배지 (D11)

```
┌ assistant ──────────────────────────────────────┐
│ (답변 본문 markdown)                                │
│ [charts] [sources] [tool trace]                   │
│ ⚠ 토큰 예산 한도에 도달해 지금까지 수집한 정보로 답변했습니다. │  ← warning 스타일 p (excludedToolsNotice와 동일 클래스)
│ [권한 제외 도구 안내] [👍👎]                          │
└───────────────────────────────────────────────────┘
```

문구(`utils/limitNotice.ts`):

| limit_reason | 문구 |
|---|---|
| `"token"` | 토큰 예산 한도에 도달해 지금까지 수집한 정보로 답변했습니다. 설정 탭에서 토큰 예산을 올릴 수 있습니다. |
| `"iteration"` | 반복 실행 한도에 도달해 지금까지 수집한 정보로 답변했습니다. |
| 기타(`limit_reached`만 True) | 실행 한도에 도달해 지금까지 수집한 정보로 답변했습니다. — Check 정정(G-1): 유틸 `limitReachedNotice`의 폴백으로만 존재한다. `Message`는 `limitReason`만 가지므로 배지 경로에서는 도달하지 않으며, 현 서버는 `limit_reached`와 사유를 항상 함께 보낸다. |

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `LimitNumberField` (신규) | `src/components/agent-builder/settings/LimitNumberField.tsx` | 숫자 입력 + blur/Enter clamp + 복원 버튼. 반복 한도·토큰 한도가 공유. props: `id, label, value, min, max, defaultValue, onChange, rangeHint` |
| `SettingsPanel` (수정) | `settings/SettingsPanel.tsx` | Recursion Limit 섹션을 `LimitNumberField`로 교체, Token Limit 섹션 추가. props `tokenLimit`, `onTokenLimitChange` |
| `AgentTestPanel` (수정) | `agent-builder/AgentTestPanel.tsx` | `tokenLimit`·`onTokenLimitChange` 패스스루 |
| `StudioLayout` (수정, Check 추가) | `agent-builder/StudioLayout.tsx` | 페이지→`AgentTestPanel` 사이의 `onTokenLimitChange` 패스스루 (Do에서 발견) |
| `AgentBuilderPage` (수정) | `pages/AgentBuilderPage/index.tsx` | form 초기값 `tokenLimit: TOKEN_LIMIT.DEFAULT`, create/update 전송 `token_limit`, 핸들러 |
| `agentDetailMapping` (수정) | `utils/agentDetailMapping.ts` | `tokenLimit: detail.token_limit ?? TOKEN_LIMIT.DEFAULT` |
| `limitReachedNotice` (신규) | `src/utils/limitNotice.ts` | `(reason, reached) → string | null` |
| `MessageBubble` (수정) | `components/chat/MessageBubble.tsx` | 배지 렌더 (스트리밍 완료 후, excludedTools 안내 앞) |
| `useAgentRunStream` (수정) | `hooks/useAgentRunStream.ts` | `limitReached`, `limitReason` 상태 |
| `ChatPage` (수정) | `pages/ChatPage/index.tsx` | view → `updateMessage({ limitReason })` |

상수: `constants/agentSettings.ts`에 `TOKEN_LIMIT = { DEFAULT: 50000, MIN: 8000, MAX: 500000 } as const` (백엔드 정책 미러 주석). 컴포넌트 파일에서 런타임 상수 export 금지 규칙 준수.

### 5.4 Page UI Checklist

#### Studio 설정 탭 (SettingsPanel)

- [ ] Section: "Token Limit" 제목 + 안내문(추정치 기준임을 명시)
- [ ] Input: `#token-limit-input` type=number, min 8000, max 500000, 자유 타이핑 → blur/Enter clamp, 비숫자는 이전 값 복원
- [ ] Button: "기본값으로 복원" (aria-label) → 50000
- [ ] Text: "(범위: 8000 - 500000)", "기본값: 50000"
- [ ] 기존 Recursion Limit 섹션 동작·테스트 불변 (`SettingsPanel.test.tsx` 통과)
- [ ] 헤더 저장 → create/update 요청에 `token_limit` 포함, edit 진입 시 서버 값 프라임

#### 채팅 답변 (MessageBubble)

- [ ] Notice: `limitReason="token"` → 토큰 문구, `"iteration"` → 반복 문구, 없음 → 미표시
- [ ] 스트리밍 중에는 표시하지 않음
- [ ] 히스토리 재조회 메시지에는 없음(실시간 답변 전용 — excludedTools와 동일 정책)

---

## 6. Error Handling

| Code | 상황 | 처리 |
|------|------|------|
| 422 | `token_limit` 범위 밖 (7999, 500001) 또는 타입 오류 | FastAPI 검증, 필드 오류 반환 |
| ValueError | 유스케이스가 범위 밖 값으로 `AgentDefinition` 생성 | 기존 예외 매핑(도메인 오류 → 400/422)을 그대로 탄다 |
| 가드 | `token_usage >= token_limit` | `limit_reached=True, limit_reason="token"`, LLM 호출 없음, `_challenge_reset()` 포함 |
| 키 부재 | 재개 스냅샷에 `limit_reason` 없음 | `state.get("limit_reason", "")` |
| 구 서버 | payload에 `limit_reason` 없음 | 프론트 `?? ''`, 배지는 `limit_reached`만으로 일반 문구 |

---

## 7. Security Considerations

- [x] 입력 검증: Pydantic `ge/le` + 도메인 정책
- [x] 권한: 기존 에이전트 수정 권한 그대로 (신규 엔드포인트 없음)
- [x] 상한 500000으로 비용 폭주 캡. 반복 한도가 2차 상한

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| 단위(domain) | `TokenLimitPolicy.validate`, `AgentDefinition.__post_init__`, `SupervisorConfig` 기본값 | pytest | Do |
| 단위(application) | 토큰 가드 출력 키, final_answer 안내 분기, payload 사유, 서브 에이전트 주입, 루트·재개 주입 | pytest | Do |
| 단위(infra) | repository save/update/row 매핑, V085 COMMENT | pytest | Do |
| API | create/update/get/fork 왕복, 422 | pytest TestClient | Do |
| 프론트 단위 | `limitReachedNotice`, `LimitNumberField` clamp, `SettingsPanel` 토큰 섹션, `useAgentRunStream` 키 매핑, `MessageBubble` 배지 | Vitest + RTL + MSW | Do |
| 프론트 통합 | `AgentBuilderPage` create/update 시 `token_limit` 전송·프라임 | Vitest + MSW | Do |

### 8.2 L1: 백엔드 테스트 시나리오

| # | 대상 | 시나리오 | 기대 |
|---|------|---------|------|
| 1 | `TokenLimitPolicy` | 7999 / 8000 / 500000 / 500001 | ValueError / OK / OK / ValueError |
| 2 | `AgentDefinition` | `token_limit=7999` | ValueError |
| 3 | `SupervisorConfig()` | 기본값 | `token_limit == 50000` |
| 4 | 토큰 가드 (`test_agent_iteration_limit.py:182` **갱신**) | `token_usage=9000, token_limit=8000` | `next_worker=="__end__"`, `limit_reached is True`, `limit_reason=="token"`, LLM 미호출 |
| 5 | 반복 가드 | `iteration_count>=max_iterations` | 기존 + `limit_reason=="iteration"` |
| 6 | 되물음 불변식 (`test_supervisor_empty_block.py:186` **갱신**) | 토큰 가드 + `finish_challenge_pending=True` | `finish_challenge_pending is False`, `limit_reached is True` → route가 final_answer (supervisor 재진입 없음) |
| 7 | `route_to_worker_or_final` | `__end__ + limit_reached + finish_challenge_pending` | `"final_answer"` (기존 동작 확인) |
| 8 | `build_initial_state` | 초기값 | `limit_reason == ""` |
| 9 | final_answer 프롬프트 | `limit_reason="token"` / `"iteration"` / `""`+`limit_reached` | "[토큰 한도 도달 안내]" / "[반복 한도 도달 안내]" / "[실행 한도 도달 안내]" 블록 포함 |
| 10 | `_StreamState` latch + payload | chain_end output `{limit_reached: True, limit_reason: "token"}` | payload `limit_reached: true, limit_reason: "token"` |
| 11 | payload 계약 | `limit_reason=""` | 키 생략 |
| 12 | GraphRecursionError 강등 경로(`:774`) | 예외 | `limit_reached=True, limit_reason="iteration"` |
| 13 | `run_agent_use_case` 루트 주입 | `agent.token_limit=12345` | 컴파일에 전달된 `SupervisorConfig.token_limit == 12345` (`:985`) |
| 14 | 승인 재개 주입 (`:1363`) | 동일 | 동일 |
| 15 | 서브 에이전트 | 부모 100000, 서브 정의 20000 | 서브 초기 state `token_limit == 20000` (절반 50000 아님) |
| 16 | 서브 에이전트 하위호환 | `_wrap_sub_agent` 인자 생략 | `TokenLimitPolicy.DEFAULT` |
| 17 | repository | save → find_by_id | `token_limit` 보존; update 변경 반영 |
| 18 | API create | 미전달 / 8000 / 7999 | 200 & 50000 / 200 / 422 |
| 19 | API update | `None` / 60000 | 변경 없음 / 60000 |
| 20 | API fork, auto_fork | 원본 60000 | 복사본 60000 |
| 21 | V085 | `test_migration_ddl_comments.py` | COMMENT 검사 통과 |

### 8.3 L2: 프론트 테스트 시나리오

| # | 대상 | 액션 | 기대 |
|---|------|------|------|
| 1 | `LimitNumberField` | "999" 입력 후 blur (min 8000) | onChange(8000), 표시 8000 |
| 2 | `LimitNumberField` | "abc" 입력 후 Enter | 이전 값 복원, onChange 미호출 |
| 3 | `SettingsPanel` | 렌더 | 토큰 섹션·범위 문구·복원 버튼 존재, 반복 섹션 기존 테스트 통과 |
| 4 | `AgentBuilderPage` | create 저장 | 요청 body `token_limit: 50000` |
| 5 | `AgentBuilderPage` | edit 진입(detail `token_limit: 60000`) → 저장 | 입력 60000 프라임, update body `token_limit: 60000` |
| 6 | `useAgentRunStream` | `agent_answer_completed {limit_reached:true, limit_reason:"token"}` | state `limitReached=true, limitReason="token"` |
| 7 | `limitReachedNotice` | token / iteration / reached-only / none | 각 문구 / null |
| 8 | `MessageBubble` | `limitReason="token"`, isStreaming=false | 배지 표시; isStreaming=true면 미표시 |

### 8.4 L3: 시나리오

| # | Scenario | Steps | Success |
|---|----------|-------|---------|
| 1 | 재현 런 완주 (SC-1) | 기본값 50000 에이전트로 URL 스크랩 → 분석 → 발표자료 | 두 번째 supervisor가 LLM 결정 수행, 토큰 가드 미발동 |
| 2 | 토큰 도달 안내 (SC-3) | `token_limit=8000` 에이전트로 같은 질의 | 답변에 토큰 한도 안내 + 채팅 배지 "토큰 예산 한도…" |
| 3 | 설정 왕복 (SC-2/6) | Studio에서 60000 저장 → 재진입 → 포크 | 값 유지, 포크본 60000 |

### 8.5 Seed Data

기존 픽스처의 `AgentDefinition` 생성자는 `token_limit` 기본값을 쓰므로 추가 시드 불필요. 로컬 DB에는 V085를 1회 적용(메모리 규칙: 적용 이력 기록, 재적용 금지).

---

## 9. Clean Architecture

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `TokenLimitPolicy` | Domain | `src/domain/agent_builder/policies.py` |
| `AgentDefinition.token_limit`, `SupervisorConfig.token_limit` | Domain | `src/domain/agent_builder/schemas.py` |
| 요청/응답 스키마 | Application (interfaces 계약) | `src/application/agent_builder/schemas.py` |
| create/update/get/fork/auto_fork 유스케이스 | Application | `src/application/agent_builder/*_use_case.py`, `auto_fork_service.py` |
| 실행 주입·가드·final_answer·payload | Application | `run_agent_use_case.py`, `supervisor_nodes.py`, `supervisor_state.py`, `workflow_compiler.py` |
| 모델·repository | Infrastructure | `src/infrastructure/agent_builder/models.py`, `agent_definition_repository.py` |
| V085 | Infrastructure | `db/migration/` |
| 타입·상수·유틸 | Frontend domain | `src/types/agentBuilder.ts`, `agentStore.ts`, `websocket.ts`, `chat.ts`, `constants/agentSettings.ts`, `utils/limitNotice.ts` |
| 컴포넌트·훅·페이지 | Frontend presentation | `settings/*`, `AgentTestPanel.tsx`, `AgentBuilderPage/index.tsx`, `chat/MessageBubble.tsx`, `hooks/useAgentRunStream.ts`, `pages/ChatPage/index.tsx` |

의존 방향: domain ← application ← infrastructure/interfaces. 라우터 변경 없음(필드 추가는 스키마 레벨).

---

## 10. Coding Convention Reference

| Item | Convention |
|------|-----------|
| 백엔드 네이밍 | `token_limit` (snake), 정책 `TokenLimitPolicy` |
| 프론트 네이밍 | `tokenLimit` / `token_limit`(wire), `TOKEN_LIMIT` 상수, `limitReason` / `limit_reason`(wire) |
| 코드 주석 | `# agent-token-limit D{n}` / `// agent-token-limit D{n}` + `Plan SC: SC-n` |
| 테스트 | TDD, `uv run python -m pytest` / 프론트 `npm test -- --no-file-parallelism` |
| DDL | COMMENT 필수, 콤마 금지 |
| 프론트 상수 | 컴포넌트 파일 런타임 상수 export 금지 → `constants/`·`types/` |

---

## 11. Implementation Guide

### 11.1 Decision Record

| ID | 결정 | 근거 |
|----|------|------|
| D1 | V085 `token_limit INT NOT NULL DEFAULT 50000` AFTER `max_iterations`, COMMENT 포함 | V045 선례, DDL 규칙 |
| D2 | `TokenLimitPolicy`(50000 / 8000 / 500000) 독립 클래스 | 반복 정책과 단위가 달라 공통 추상 불필요 |
| D3 | `AgentDefinition.token_limit` + `__post_init__` 검증, `SupervisorConfig` 기본값을 정책 상수로 | 단일 소스 |
| D4 | create `Field(50000, ge, le)`, update `None`=변경 없음, 응답 2종에 포함 | `max_iterations` D10 선례 |
| D5 | create/update/get/fork/auto_fork + repository 3지점 | Plan 6.2 소비자 전수 |
| D6 | `run_agent_use_case.py:985`·`:1363` 두 곳 모두 `token_limit=agent.token_limit` | 승인 재개 누락 방지 |
| D7 | `_compile_sub_agent`가 `sub_agent.token_limit`을 `_wrap_sub_agent(token_limit=…)`로 전달. 기본 인자 `TokenLimitPolicy.DEFAULT`. `state["token_limit"] // 2` 제거. 부모의 `token_usage += sub_token_usage` 합산은 유지 | 사용자 결정(독립), 테스트 하위호환 |
| D8 | 토큰 가드 반환에 `limit_reached: True, limit_reason: "token"` 추가. 반복 가드에 `limit_reason: "iteration"` 추가. `SupervisorState.limit_reason: str`, 초기값 `""`. `route_to_worker_or_final`·`_challenge_reset` 무변경 | 라우팅은 이미 `limit_reached`로 final_answer 우회. 되물음 분기는 `not limit_reached`로 자동 차단 |
| D9 | final_answer 안내 블록을 사유별 3종 문구로 분기(`token` / `iteration` / 기타). 블록 구조·위치 동일 | 기존 D7-① 확장 |
| D10 | `_StreamState.limit_reason`, chain_end latch에서 `limit_reached`가 True일 때 `limit_reason` 캡처(최초값 유지). `_answer_payload(limit_reason=…)`. GraphRecursionError 강등 경로는 `"iteration"`. **Act-1 (Check G-2)**: latch는 최상위 이벤트(`parent_ids` 길이 ≤ 1)에서만 — 서브 에이전트 그래프의 가드 신호가 부모 payload에 새지 않게 한다 | truthy-only 계약 유지. 중첩 이벤트 전파는 LangGraph 소형 실험으로 확인(최상위 노드 1·최상위 그래프 0·중첩 3) |
| D11 | 프론트 타입 `limit_reached?: boolean; limit_reason?: 'iteration' \| 'token'`(websocket.ts), `Message.limitReason?`, 훅·페이지 매핑, `utils/limitNotice.ts`, `MessageBubble` warning p. 실시간 전용(히스토리 없음) | `excluded_tools` 선례 |
| D12 | `LimitNumberField` 추출(반복·토큰 공용), `SettingsPanel` 토큰 섹션, `TOKEN_LIMIT` 상수, form `tokenLimit`, create/update 전송, detail 프라임 | 중복 clamp 로직 방지 |

### 11.2 Implementation Order

1. [ ] module-1: `TokenLimitPolicy` 테스트 → 구현, `SupervisorConfig`·`AgentDefinition` 테스트 → 구현, V085 + 모델 + repository 테스트 → 구현
2. [ ] module-2: 앱 스키마·create/update/get/fork/auto_fork 테스트 → 구현, API 왕복 테스트
3. [ ] module-3: 가드·state·final_answer·latch·payload 테스트(기존 2건 갱신) → 구현, 루트·재개·서브 주입 테스트 → 구현
4. [ ] module-4: 프론트 설정 — 상수·타입·`LimitNumberField`·`SettingsPanel`·`AgentTestPanel`·`AgentBuilderPage`·`agentDetailMapping` 테스트 → 구현, `/api-contract-sync`
5. [ ] module-5: 프론트 배지 — `websocket.ts`·`chat.ts` 타입, `limitNotice.ts`, 훅·`ChatPage`·`MessageBubble` 테스트 → 구현
6. [ ] 로컬 DB V085 적용, 재현 런(SC-1/SC-3) 실행, `/verify-architecture`·`/verify-tdd`

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| DB + 도메인 | `module-1` | V085, 모델, repository, `TokenLimitPolicy`, 엔티티·Config | 15-20 |
| API + 유스케이스 | `module-2` | 스키마 4종, create/update/get/fork/auto_fork, API 테스트 | 20-25 |
| 실행 경로 + 가드 + payload | `module-3` | 루트·재개·서브 주입, 가드 `limit_reason`, final_answer 분기, latch·payload | 25-30 |
| 프론트 설정 패널 | `module-4` | 상수·타입·`LimitNumberField`·`SettingsPanel`·페이지·매핑, contract sync | 25-30 |
| 프론트 배지 | `module-5` | WS/Message 타입, `limitNotice`, 훅·ChatPage·MessageBubble | 15-20 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| 1 | Do | `--scope module-1,module-2` | 40-45 |
| 2 | Do | `--scope module-3` | 25-30 |
| 3 | Do | `--scope module-4,module-5` | 40-50 |
| 4 | Check + Report | 전체 + 재현 런 | 30-40 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-05 | Initial draft — Option C 선택, 배지 UI 포함 | 배상규 |
| 0.2 | 2026-11-05 | Check 정정: G-1/G-4/G-6 문구, §5.3 StudioLayout, D10 Act-1 latch 깊이 필터 | 배상규 |
