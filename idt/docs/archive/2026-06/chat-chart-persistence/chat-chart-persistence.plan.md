# Plan: chat-chart-persistence

> Created: 2026-06-10
> Phase: Plan
> Scope: 풀스택 (`idt/` 백엔드 + `idt_front/` 프론트엔드) — 차트 페이로드를 대화 이력과 함께 영속화하여 채팅방 재진입 시 차트 복원

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | chart_builder가 생성한 Chart.js config(`state["charts"]`)는 스트리밍 이벤트(`ANSWER_COMPLETED`)로만 프론트에 전달되고, assistant 메시지 DB 저장(`_save_assistant_message`)에는 **텍스트 답변만 저장**된다. 채팅방을 나갔다 재진입하면 이력 API가 텍스트만 반환하므로 차트가 영구 소실된다 — 답변 본문은 "아래 차트를 참고하세요"라고 차트를 언급하는데 정작 차트는 없다. |
| **Solution** | `conversation_message` 테이블에 nullable JSON 컬럼(`charts`)을 추가하고, Agent Run·General Chat 양 경로의 assistant 메시지 저장 시 차트 페이로드를 함께 영속화한다. 대화 이력 조회 API가 charts를 포함해 반환하고, 프론트는 이력 로드 시 기존 `MessageBubble` 차트 렌더링을 그대로 재사용한다. |
| **Function UX Effect** | 사용자가 채팅방에 재진입해도 과거 턴의 차트가 답변과 함께 그대로 복원되어 표시된다. 라이브 스트리밍 UX는 변경 없음. |
| **Core Value** | "스트리밍으로 본 화면 = 재진입 시 복원되는 화면" 일관성 확보. 차트가 일회성 시각 효과가 아닌 대화 기록의 일부가 됨. |

---

## 1. 배경 / 문제 정의 (코드 근거)

### 1-1. 차트 데이터 흐름 (As-Is)

```
[Supervisor Agent 경로]
chart_builder 노드 → state["charts"]            (workflow_compiler.py:345~359)
  → final_answer 노드: charts 메타만 프롬프트 참조, 비파괴 통과 (:477~561)
  → RunAgentUseCase.stream(): on_chain_end에서 _StreamState.charts 캡처
        (run_agent_use_case.py:580~583)
  → ANSWER_COMPLETED payload["charts"]로 프론트 전송 (:246~250)   ← 휘발성 전달
  → _save_assistant_message(answer, ...) — answer 텍스트만 저장 (:241~244, :794~816)  ← ❌ 유실 지점

[General Chat 경로]
_persist_messages(answer 텍스트만 저장) (general_chat/use_case.py:199~201)
  → _maybe_build_charts() — 저장 "이후" 차트 생성 (:203~205)
  → ANSWER_COMPLETED payload["charts"] (:207~216)                  ← 동일하게 휘발
```

### 1-2. 유실이 확정되는 지점

| # | 위치 | 내용 |
|---|------|------|
| ① | `conversation_message` 테이블 | `content`(Text) 외 차트 저장 컬럼 없음 (`infrastructure/persistence/models/conversation.py:13~33`) |
| ② | `ConversationMessage` 도메인 엔티티 | `content: str`만 보유 (`domain/conversation/entities.py:40~59`) |
| ③ | 이력 조회 API | `MessageItemAPI`에 `id/role/content/turn_index/created_at`만 존재 (`api/routes/conversation_history_router.py:32~39`) — 4개 이력 엔드포인트 모두 동일 |
| ④ | 프론트 이력 로드 | `Message.charts?: ChartPayload[]`(idt_front `types/chat.ts:21`)는 스트리밍 수신 시에만 채워짐. 이력 API 응답에 charts가 없어 재진입 시 복원 불가 |

### 1-3. 추가 문제: General Chat의 저장 순서

General Chat은 `_persist_messages` **이후에** `_maybe_build_charts`를 실행하므로, 단순히 "저장 시 charts 포함"으로는 부족하다 — 차트 생성을 저장 앞으로 옮기거나, 저장 시점에 charts를 전달할 수 있도록 순서 조정이 필요하다.

---

## 2. 목표 / 비목표

### 2-1. 목표

- **G1.** `conversation_message`에 nullable `charts` JSON 컬럼 추가 (Flyway 마이그레이션 `V031__alter_conversation_message_add_charts.sql`).
- **G2.** Agent Run 경로: `_save_assistant_message`에 `state.charts` 전달·저장 (차트 없으면 NULL).
- **G3.** General Chat 경로: 차트 생성 → 저장 순서로 조정 후 charts 함께 저장.
- **G4.** 이력 조회 API 4종(`/sessions/{id}/messages`, `/agents/{agent_id}/sessions/{id}/messages` 등 message 반환 엔드포인트)에 `charts` 필드 추가 (없으면 `null`/생략).
- **G5.** 프론트 동기화 (API 계약 동기화 규칙 §4-1): 이력 응답 타입에 `charts` 추가 → 이력 로드 시 `Message.charts`로 매핑 → 기존 `MessageBubble` 차트 렌더링 재사용.
- **G6.** 대화 메모리 정책 보존: 저장된 charts는 **LLM 컨텍스트(`_build_messages`)·요약(summarizer) 대상에 포함하지 않는다** — 표시 전용 메타데이터. 기존 메모리 정책 변경 없음.
- **G7.** TDD: 백엔드 pytest(엔티티/리포지토리/유스케이스/라우터), 프론트 Vitest+MSW(이력 차트 복원) 테스트 선행.

### 2-2. 비목표

- **N1.** 차트 생성 로직(chart_builder, chart_router, VisualizationRoutingPolicy) 변경 없음.
- **N2.** 스트리밍 이벤트 스키마(`ANSWER_COMPLETED.charts`) 변경 없음 — 라이브 경로는 그대로.
- **N3.** Excel Standalone 분석 경로(`analysis_router`)의 차트 영속화 — 대화 세션이 아니므로 범위 외.
- **N4.** 과거 메시지 소급 복원 — 이미 유실된 차트는 재생성하지 않음 (컬럼은 NULL).
- **N5.** `conversation_summary` 변경 없음 (차트는 요약 대상 아님, G6).

---

## 3. 해결 방안 비교

| 옵션 | 내용 | 평가 |
|------|------|------|
| **A. `conversation_message.charts` JSON 컬럼 (채택)** | nullable JSON(MySQL `JSON` 타입) 컬럼 1개 추가, 저장/조회 시 직렬화 | 스키마 변경 최소(컬럼 1개), 메시지와 차트의 1:1 수명 일치, 이력 조회 쿼리 변경 없음(같은 row) |
| B. `content`에 차트 JSON 임베드 (마커 구분) | 코드 변경만으로 가능 | `content`가 LLM 컨텍스트로 재투입됨 → 토큰 낭비 + 메모리 정책 오염 + 파싱 취약. 기각 |
| C. 별도 `conversation_message_chart` 테이블 | 차트별 row 분리 | 조회 시 JOIN 필요, 차트를 개별 질의할 요구 없음 — 과설계(두꺼운 DDD 금지 원칙). 기각 |

**채택 근거**: 차트는 항상 "특정 assistant 메시지에 부속"되며 독립 조회 요구가 없다. MySQL JSON 컬럼이면 유효성은 DB가 보장하고 ORM 매핑도 단순하다.

---

## 4. 구현 범위 / 영향 파일

### 4-1. 백엔드 (`idt/`)

| 레이어 | 파일 | 변경 |
|--------|------|------|
| DB 마이그레이션 | `db/migration/V031__alter_conversation_message_add_charts.sql` (신규) | `ALTER TABLE conversation_message ADD COLUMN charts JSON NULL` |
| infrastructure | `src/infrastructure/persistence/models/conversation.py` | `ConversationMessageModel.charts: Mapped[Optional[list]]` (JSON 컬럼) |
| infrastructure | `src/infrastructure/persistence/mappers/conversation_mapper.py` | 엔티티↔모델 charts 매핑 |
| domain | `src/domain/conversation/entities.py` | `ConversationMessage.charts: Optional[list[dict]] = None` 필드 추가 (frozen dataclass — 기본값으로 기존 호출부 호환) |
| application | `src/application/agent_builder/run_agent_use_case.py` | `_save_assistant_message(answer, ..., charts=state.charts)` |
| application | `src/application/general_chat/use_case.py` | `_maybe_build_charts`를 `_persist_messages` 앞으로 이동 + charts 전달 저장 |
| application | `src/application/conversation/history_use_case.py` | 메시지 DTO에 charts 포함 |
| interfaces | `src/api/routes/conversation_history_router.py` | `MessageItemAPI.charts: Optional[list] = None` 추가 (메시지 반환 엔드포인트 전체) |

### 4-2. 프론트엔드 (`idt_front/`) — API 계약 동기화

| 파일 | 변경 |
|------|------|
| `src/types/chat.ts` | 이력 응답 메시지 타입에 `charts?: ChartPayload[]` |
| `src/services/chatService.ts` (이력 조회) | 응답 charts 패스스루 |
| `src/hooks/useChat.ts` / 이력 로드 훅 | 이력 메시지 → `Message.charts` 매핑 |
| `src/__tests__/mocks/handlers.ts` | 이력 MSW 핸들러에 charts 필드 추가 |
| (`MessageBubble.tsx`) | 변경 없음 — `message.charts` 렌더링 기존 로직 재사용 |

---

## 5. 제약 / 리스크

| # | 항목 | 대응 |
|---|------|------|
| R1 | **DB 스키마 변경 승인 필요** (CLAUDE.md 절대 금지: 임의 변경) | 본 Plan → Design 승인 후 마이그레이션 진행. Flyway V031로 추적 |
| R2 | charts JSON 크기 (Chart.js config × 최대 `chart_max_count`) | JSON 컬럼(최대 4GB)로 충분. Design에서 저장 전 크기 상한/개수 상한 검토 |
| R3 | `ConversationMessage` frozen dataclass 필드 추가에 따른 기존 생성자 호출부 영향 | 기본값 `None`으로 하위호환. 전체 호출부 grep 후 테스트로 검증 |
| R4 | General Chat 저장 순서 변경(차트 생성 → 저장)으로 차트 생성 실패 시 저장 지연/누락 우려 | `_maybe_build_charts`는 이미 예외 시 `[]` 반환(graceful). 저장 자체는 차트 실패와 무관하게 수행 보장 |
| R5 | 메모리 정책 오염 (charts가 LLM 컨텍스트 재투입) | `_build_messages`/summarizer는 `content`만 사용하도록 유지 — 테스트로 고정 (G6) |
| R6 | 사전 실패 테스트와의 혼동 | 2026-06-10 기준 tests/api 28건·infra 30건 사전 실패 존재 — 신규 회귀와 구분하여 검증 |

---

## 6. 검증 계획 (TDD)

| 대상 | 테스트 |
|------|--------|
| domain | `ConversationMessage` charts 기본값 None / 값 보존 |
| infrastructure | repository save/find round-trip에 charts 포함, NULL 처리 |
| application (agent) | `stream()` 완료 후 저장된 assistant 메시지에 `state.charts` 반영 |
| application (general chat) | 차트 생성 → 저장 순서, 차트 실패 시에도 메시지 저장 |
| application (memory 정책) | `_build_messages` 결과에 charts 미포함 (G6 고정) |
| interfaces | 이력 API 응답 charts 직렬화 (있음/NULL) |
| frontend | MSW 이력 응답에 charts 포함 시 `MessageBubble` 차트 렌더 (Vitest `--pool=threads`) |

---

## 7. 다음 단계

1. `/pdca design chat-chart-persistence` — 컬럼 타입·DTO 스키마·저장 순서 상세 설계
2. 구현 (TDD) → `/pdca analyze chat-chart-persistence`
