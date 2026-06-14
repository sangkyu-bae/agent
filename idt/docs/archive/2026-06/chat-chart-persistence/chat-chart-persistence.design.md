# Design: chat-chart-persistence

> Created: 2026-06-10
> Phase: Design
> Plan: `docs/01-plan/features/chat-chart-persistence.plan.md`
> Scope: 풀스택 — `conversation_message.charts` JSON 컬럼 신설로 차트 페이로드 영속화 + 이력 API/프론트 복원

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 차트(`state["charts"]`)가 `ANSWER_COMPLETED` 스트리밍 이벤트로만 전달되고 assistant 메시지 저장에는 텍스트만 영속화 → 채팅방 재진입 시 차트 영구 소실 |
| **Solution** | `conversation_message`에 nullable JSON 컬럼 `charts` 추가. Agent Run·General Chat 양 경로에서 assistant 메시지와 함께 N개 차트 배열을 저장하고, 이력 API → 프론트 `Message.charts`로 복원 |
| **Function UX Effect** | 재진입 시 과거 턴 차트가 `MessageBubble` 기존 렌더링으로 그대로 복원. 라이브 스트리밍 UX·이벤트 스키마 무변경 |
| **Core Value** | 차트가 대화 기록의 일부가 됨. 차트는 표시 전용 메타데이터로 LLM 컨텍스트·요약 정책은 불변 |

---

## 1. 설계 결정 (Design Decisions)

| # | 결정 | 근거 |
|---|------|------|
| **D1** | MySQL `JSON` nullable 컬럼 1개 (`charts`). 차트 배열 통째 직렬화 `[{config1}, ..., {configN}]` | N개 수용 구조(사용자 확인 완료). 메시지:차트 = 1:N이지만 차트 독립 조회 요구 없음 → JOIN 불필요한 부속 데이터 |
| **D2** | **빈 차트는 NULL로 저장** (빈 배열 `[]` 저장 금지) | 대부분의 메시지는 차트 없음 — NULL이 스토리지·의미론 모두 명확. 조회 시 NULL → 응답에서 `null`/생략 |
| **D3** | 저장 레이어에 개수 상한 두지 않음 — **생성단 `chart_max_count`(config.py:81)가 유일한 상한** | 중복 상한은 설정 변경 시 이중 수정 함정. 저장은 생성된 것을 그대로 보존 |
| **D4** | General Chat: `_maybe_build_charts()`를 `_persist_messages()` **앞으로 이동**, `_persist_messages(charts=...)` 파라미터 추가 | 현재 저장이 차트 생성보다 먼저라 구조적으로 저장 불가. 차트 빌드는 실패 시 `[]` 반환(graceful)이므로 저장을 막지 않음 |
| **D5** | Agent Run: `_save_assistant_message(..., charts=state.charts or None)` — 시그니처에 키워드 전용 `charts` 추가 | `_StreamState.charts`는 `ANSWER_COMPLETED` 직전에 이미 확정(저장 호출과 같은 지점) — 순서 변경 불필요 |
| **D6** | 도메인 엔티티 `ConversationMessage.charts: Optional[list[dict]] = None` (기본값 None) | frozen dataclass 맨 뒤 기본값 필드 → 기존 위치 인자 호출부 전부 무변경 호환 |
| **D7** | **LLM 컨텍스트·요약에 charts 미투입** — `_build_messages`/`_build_full_context`/summarizer는 `content`만 사용(기존 코드 무변경, 테스트로 고정) | 대화 메모리 정책 보존(CLAUDE.md 절대 금지: 메모리 정책 변경). 차트 JSON은 토큰 낭비 |
| **D8** | user 메시지는 항상 `charts=None` | 차트는 assistant 답변의 부속물 |
| **D9** | 스트리밍 이벤트 스키마 무변경 | `ANSWER_COMPLETED.payload["charts"]` 기존 그대로 — 라이브 경로는 본 기능과 독립 |

---

## 2. 데이터 흐름 (To-Be)

```
[라이브 (기존 유지)]
chart_builder → state["charts"] → _StreamState.charts → ANSWER_COMPLETED.charts → 프론트 렌더

[영속화 (신규)]                                          [복원 (신규)]
Agent:   state.charts ─┐                                 GET /conversations/.../messages
General: _maybe_build_charts() ─┤→ ConversationMessage     → MessageItem.charts
                                │   (charts=list|None)      → MessageItemAPI.charts
                                └→ conversation_message     → HistoryMessageItem.charts
                                    .charts (JSON|NULL)     → toMessage() → Message.charts
                                                            → MessageBubble (기존 렌더링)
```

---

## 3. 상세 설계 — 백엔드

### 3-1. DB 마이그레이션 (신규)

`db/migration/V031__alter_conversation_message_add_charts.sql`

```sql
-- chat-chart-persistence: assistant 메시지의 Chart.js config 배열 (N개, NULL=차트 없음)
ALTER TABLE conversation_message
    ADD COLUMN charts JSON NULL COMMENT 'Chart.js config 배열 (chat-chart-persistence)';
```

- 인덱스 불필요 (차트 기준 검색 요구 없음, D1).
- 기존 row는 자동 NULL — 소급 복원 없음 (Plan N4).

### 3-2. ORM 모델

`src/infrastructure/persistence/models/conversation.py`

```python
from sqlalchemy import JSON  # import 추가

class ConversationMessageModel(Base):
    ...
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # chat-chart-persistence: Chart.js config 배열 (NULL = 차트 없음)
    charts: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

### 3-3. 도메인 엔티티

`src/domain/conversation/entities.py`

```python
@dataclass(frozen=True)
class ConversationMessage:
    id: Optional[MessageId]
    user_id: UserId
    session_id: SessionId
    agent_id: AgentId
    role: MessageRole
    content: str
    turn_index: TurnIndex
    created_at: datetime
    # chat-chart-persistence D6: 표시 전용 차트 메타 (LLM 컨텍스트 미투입, D7)
    charts: Optional[list[dict]] = None

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("Message content cannot be empty")
        # D2: 빈 배열 금지 — 없으면 None
        if self.charts is not None and len(self.charts) == 0:
            raise ValueError("charts must be None when empty")
```

> 기본값 필드를 **맨 뒤에 추가** → `ConversationMessage(...)` 위치 인자 호출부(run_agent_use_case, general_chat use_case, 테스트) 전부 무변경.

### 3-4. 매퍼

`src/infrastructure/persistence/mappers/conversation_mapper.py`

```python
# to_entity: charts=model.charts (JSON → list|None 그대로)
# to_model:  charts=entity.charts
```

양방향 1줄씩 추가. JSON 컬럼은 SQLAlchemy가 list↔JSON 자동 직렬화.

### 3-5. Agent Run 경로

`src/application/agent_builder/run_agent_use_case.py`

```python
# stream() 내 (:241~244)
await self._save_assistant_message(
    answer, request.user_id, session_id, agent_id,
    charts=state.charts or None,          # D5: 빈 리스트 → None (D2)
)

# _save_assistant_message (:794~816)
async def _save_assistant_message(
    self, answer: str, user_id: str, session_id: str, agent_id: str,
    *, charts: Optional[list[dict]] = None,
) -> None:
    ...
    assistant_msg = ConversationMessage(
        ..., charts=charts,
    )
```

### 3-6. General Chat 경로 (순서 변경, D4)

`src/application/general_chat/use_case.py` — `stream()` 내 (:199~205)

```python
# Before: persist → build_charts        # After: build_charts → persist
charts = await self._maybe_build_charts(
    request.message, answer, sources, tools_used,
)
await self._persist_messages(
    user_id, session_id, request.message, answer, len(history),
    charts=charts or None,                # D2
)
```

`_persist_messages` (:447~464): 키워드 전용 `charts: Optional[list[dict]] = None` 추가 — **assistant 메시지에만** 전달, user 메시지는 `charts=None` (D8).

> 영향 검토: `_maybe_build_charts`는 분류 LLM 호출이 포함되어 저장이 차트 생성 시간만큼 늦어진다. 단, 두 호출 모두 `ANSWER_COMPLETED` yield 앞에 있어 **사용자 체감 지연은 기존과 동일**하고, 차트 빌드 실패 시 `[]` 반환으로 저장은 항상 수행된다.

### 3-7. 이력 조회 (domain 스키마 → use case → router)

`src/domain/conversation/history_schemas.py`

```python
@dataclass(frozen=True)
class MessageItem:
    id: int
    role: str
    content: str
    turn_index: int
    created_at: datetime
    charts: Optional[List[dict]] = None   # 신규 (맨 뒤 기본값 — 호출부 호환)
```

`src/application/conversation/history_use_case.py` — `get_messages`(:66~75)·`get_messages_by_agent`(:179~188) 두 곳의 `MessageItem(...)` 생성에 `charts=m.charts` 추가.

`src/api/routes/conversation_history_router.py`

```python
class MessageItemAPI(BaseModel):
    id: int
    role: str
    content: str
    turn_index: int
    created_at: datetime
    charts: Optional[list[dict]] = Field(None, description="Chart.js config 배열 (없으면 null)")
```

`get_messages`(:114~137)·`get_agent_session_messages`(:197~225) 두 엔드포인트의 `MessageItemAPI(...)` 생성에 `charts=m.charts` 추가.
(세션 목록·에이전트 목록 엔드포인트는 메시지를 반환하지 않으므로 무변경.)

---

## 4. 상세 설계 — 프론트엔드 (API 계약 동기화 §4-1)

### 4-1. 타입

`idt_front/src/types/chat.ts`

```typescript
export interface HistoryMessageItem {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  turn_index: number;
  created_at: string;
  /** chat-chart-persistence: Chart.js config 배열 (없으면 null/생략) */
  charts?: ChartPayload[] | null;
}
```

`Message.charts?: ChartPayload[]`는 기존 존재 (`chat.ts:21`) — 무변경.

### 4-2. 서비스 매핑

`idt_front/src/services/chatService.ts` — `toMessage`(:32~37)

```typescript
const toMessage = (item: HistoryMessageItem): Message => ({
  id: String(item.id),
  role: item.role,
  content: item.content,
  createdAt: item.created_at,
  ...(item.charts?.length ? { charts: item.charts } : {}),
});
```

`getSessionMessages`·`getAgentSessionMessages` 모두 `toMessage` 공용 — 추가 변경 없음.

### 4-3. 렌더링

`MessageBubble.tsx` — **무변경**. `message.charts` 배열 순회 렌더링 기존 로직 재사용.

### 4-4. MSW 핸들러

`idt_front/src/__tests__/mocks/handlers.ts` — 이력 응답 메시지에 `charts` 필드(배열/null 케이스) 추가.

---

## 5. 구현 순서 (TDD — Red → Green → Refactor)

| 단계 | 작업 | 테스트 먼저 |
|------|------|------------|
| 1 | 마이그레이션 `V031` 작성 + 로컬 DB 적용 | — (SQL) |
| 2 | domain: `ConversationMessage.charts` + `MessageItem.charts` | `tests/domain/` — 기본값 None, 빈 배열 거부, 값 보존 |
| 3 | infrastructure: ORM 컬럼 + 매퍼 양방향 | `tests/infrastructure/test_conversation_repository_impl.py` — save/find round-trip (N개 배열, NULL) |
| 4 | application(agent): `_save_assistant_message` charts 전달 | `tests/application/agent_builder/` — stream 완료 후 저장 호출에 `state.charts` 반영, 빈 리스트 → None |
| 5 | application(general chat): 순서 변경 + `_persist_messages` charts | `tests/application/general_chat/test_use_case.py` — 차트 생성→저장 순서, 차트 실패 시에도 저장 보장, user 메시지 charts=None |
| 6 | application(메모리 정책 고정): | `_build_messages`/`_build_full_context` 결과에 charts 미포함 (D7 회귀 방지) |
| 7 | interfaces: history use case + router charts | `tests/api/` — 응답 charts 직렬화 (배열/null) |
| 8 | frontend: 타입 + `toMessage` + MSW | Vitest `--pool=threads` — 이력 로드 시 `Message.charts` 매핑, `MessageBubble` 렌더 |

---

## 6. 검증 기준 (Check 단계 Match 항목)

1. `V031` 마이그레이션 파일 존재 + `charts JSON NULL`
2. `ConversationMessageModel.charts` / 매퍼 양방향 / 엔티티 기본값 None
3. Agent Run: 차트 생성 런의 assistant row에 charts 저장, 비차트 런은 NULL
4. General Chat: 차트 생성→저장 순서 + charts 저장
5. 이력 API 2종 응답에 `charts` 필드 (있음=배열 / 없음=null)
6. `_build_messages` 류 LLM 컨텍스트에 charts 미포함 (테스트 고정)
7. 프론트 이력 로드 → `MessageBubble` 차트 복원 (MSW 테스트)
8. 기존 테스트 회귀 없음 (단, 2026-06-10 기준 사전 실패 tests/api 28건·infra 30건은 제외하고 판단)

---

## 7. 주의사항 / 영향 범위

- **DB 스키마 변경**: 본 Design 승인이 곧 변경 승인 — `ALTER TABLE`은 V031 마이그레이션으로만 수행, ORM `create_all` 의존 금지.
- **frozen dataclass 필드 추가**: 기본값이 있으므로 하위호환이나, `ConversationMessage(` 생성부 전수 확인(grep) 후 진행.
- **레이어 규칙**: charts는 `list[dict]` 원시 타입으로 도메인에 전달 — 도메인이 Chart.js 스키마(인프라 관심사)를 알지 않게 유지.
- **Windows pytest**: 교차 실행 시 이벤트 루프 teardown 산발 실패 이력 — 의심 시 모듈 격리 실행으로 검증.
