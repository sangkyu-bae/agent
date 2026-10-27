# agent-opener Design Document

> **Summary**: 에이전트별 "대화 시작 예시 질문"(오프너)을 `agent_opener` 테이블에 저장하고, 빌더 오프너 탭에서 등록·수정, 채팅 빈 상태에서 카드로 노출해 클릭 즉시 전송한다. 백엔드는 별도 포트·리포지토리(agent_skill 패턴)로 실행 경로 무영향, 프론트는 폼 staged + 상단 저장 통합.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-10-24
> **Status**: Draft
> **Planning Doc**: [agent-opener.plan.md](../../01-plan/features/agent-opener.plan.md)
> **목표 UI**: `docs/img/offner.png`

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트별 "무엇을 물어볼지"를 첫 화면에서 안내할 수단이 없고, 빌더 오프너 탭은 placeholder뿐이다 |
| **WHO** | P2 에이전트 소유자(등록) · P1 채팅 이용자(클릭해 시작) |
| **RISK** | 목록 API(`/agents/my`)에 오프너를 합치며 N+1 조회 추가 → 배치 로드 필수. 수정 가능 필드 4곳 세트(스키마·use_case·repo·DI) 누락 시 조용히 미저장 |
| **SUCCESS** | 빌더에서 12개까지 등록·저장·재진입 프라임 OK, 채팅 빈 상태에서 카드 노출·클릭 즉시 전송 OK, 오프너 없는 에이전트·super는 기존 화면 그대로, 기존 FAILED 목록 diff 0 |
| **SCOPE** | module-1 백엔드(테이블·도메인·API·포크) → module-2 빌더 오프너 탭 → module-3 채팅 빈 상태 노출 |

---

## 1. Overview

### 1.1 Design Goals

- 실행 hot path(`RunAgentUseCase` → `find_by_id`)에 쿼리를 추가하지 않는다. 오프너는 별도 포트로 필요한 use case만 읽는다.
- 모든 API 계약 확장은 additive(optional 요청 필드, 기본값 있는 응답 필드)로 기존 소비자·MSW·테스트 무변경.
- 검증 규칙(12개·200자·빈 항목·중복)의 SoT는 백엔드 한 곳(Pydantic 상한 + `OpenerPolicy` 정규화). 프론트 상수는 UX 가드일 뿐.
- 응답 상태 코드는 두 라우터(POST/PATCH)에서 동일하게 422. 라우터의 `ValueError` 문자열 매퍼 함정을 피한다(§6.3).

### 1.2 Design Principles

- **agent_skill 동형**: 포트(`domain/agent_opener/interfaces.py`) + 리포지토리(`infrastructure/agent_opener/`) + ORM(`persistence/models/agent_opener/`). 단, 권한 검증이 없으므로 별도 sync use case는 두지 않는다(선택안 C).
- **None = 변경 안 함**: `UpdateAgentRequest.openers`가 None이면 미동기화, `[]`면 전부 삭제, `[...]`면 전체 교체(`skill_ids`·`middleware_types` 관례).
- **데이터는 있고 노출 경로만 없다 방지**: 상세·목록 두 응답에 모두 싣는다(빌더 프라임 + 채팅 노출).
- **프론트 상수는 `constants/`**: 컴포넌트 파일 런타임 export 금지(`tsx-authoring-pitfalls`).

### 1.3 Plan 대비 확정 사항 (2026-10-24 코드 확인)

| Plan "확인 필요" | 확정 |
|---|---|
| 에이전트 삭제가 소프트 삭제인가 | **예** — `agent_definition_repository.py:356` `status="deleted"` UPDATE. CASCADE 미발동, 오프너 행 잔존은 무해(목록·상세가 deleted를 걸러냄). 하드 삭제 도입 시 FK CASCADE가 정리 |
| `find_by_id` hot path 영향 | **없음** — 오프너는 별도 리포지토리, `AgentDefinition` 엔티티에 필드를 두지 않는다 |
| `/agents/my` 소비자 | `AgentChatLayout`(채팅) · `AgentStorePage` "내 에이전트" 탭(`useMyAgents`) 2곳. 둘 다 추가 필드 무시 |
| 수정 API 메서드 | **PATCH** `/api/v1/agents/{agent_id}` (Plan의 PUT 표기는 오기) |
| 라우터 에러 매핑 | POST는 `_attach_skill_http_error`: 메시지에 "찾을 수 없"→404, "이미 부착"/"**최대**"→409, 그 외 422. PATCH도 유사 분기(`:261-267`). → 개수·길이는 Pydantic이 422로 거부하고, 정책 메시지에 "최대"·"이미"·"찾을 수 없" 문자열을 쓰지 않는다 |

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | `AgentDefinitionRepository`에 오프너 로드/교체 내장, 엔티티 필드로 전파 | 포트·리포지토리 + `SyncAgentOpenersUseCase` (agent_skill 완전 동형) | 포트·리포지토리 분리, sync use case 없이 각 use case가 optional 주입받아 직접 호출 |
| **New Files (BE)** | 2 | 7 | 5 |
| **Modified Files (BE)** | 6 | 8 | 8 |
| **Hot path 영향** | `find_by_id`마다 조인 | 없음 | 없음 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | run_agent 등 광범위 경로에 쿼리 추가 | 권한 검증 없는 기능에 계층 과잉 | Low |

**Selected**: **Option C** — 사용자 선택(2026-10-24). 실행 경로 무영향 + 계층 과잉 없음.

### 2.1 Component Diagram

```
idt_front                                   idt
┌──────────────────────────┐   POST/PATCH   ┌─────────────────────────────────────┐
│ AgentBuilderPage         │ ─ openers[] ─▶ │ agent_builder_router                │
│  └ AgentTestPanel        │                │  ├ Create/UpdateAgentUseCase        │
│     └ OpenerPanel (new)  │ ◀─ GET detail ─│  │   └ AgentOpenerRepository.replace │
│                          │   openers[]    │  ├ GetAgentUseCase                  │
├──────────────────────────┤                │  │   └ .list_by_agent_id            │
│ AgentChatLayout          │ ◀─ GET /my ────│  ├ ListMyAgentsUseCase              │
│  └ useMyAgents → openers │   openers[]    │  │   └ .list_by_agent_ids (배치 1회) │
│ ChatPage.EmptyAgentState │                │  └ ForkAgentUseCase                 │
│  └ SuggestionCards items │                │      └ list → replace (복사)        │
└──────────────────────────┘                └──────────────┬──────────────────────┘
                                                           ▼
                                             agent_opener (V080, agent_id FK CASCADE)
```

### 2.2 Data Flow

```
[등록]  OpenerPanel 입력 → form.openers (staged)
       → StudioHeader 저장 → handleSave → create/update payload.openers
       → Pydantic(개수≤12, 각 ≤200) → OpenerPolicy.normalize(strip·빈값·중복)
       → AgentOpenerRepository.replace(agent_id, texts)  [DELETE agent_id → INSERT n건]
[프라임] GET /agents/{id}.openers → mapDetailToForm → form.openers
[노출]  GET /agents/my.agents[].openers → toAgentSummary → selectedAgent.openers
       → EmptyAgentState: openers.length>0 ? 오프너 카드 : 고정 카드 → 클릭 → handleSend(text)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `OpenerPolicy` | 없음 (domain 순수) | 정규화·검증 |
| `AgentOpenerRepository` | `AgentOpenerModel`, `MySQLBaseRepository` | 영속 |
| Create/Update/Get/ListMy/Fork UseCase | `AgentOpenerRepositoryInterface` (optional, 기본 None) | 저장/조회/복사. 미주입 시 기존 동작 그대로(테스트 호환) |
| `OpenerPanel` | `constants/agentOpener.ts` | 상한 표시·가드 |
| `EmptyAgentState` | `SuggestionCards.items` | 분기 렌더 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# src/domain/agent_opener/schemas.py
@dataclass
class AgentOpener:
    id: str
    agent_id: str
    text: str          # strip 완료, 1~200자
    sort_order: int    # 0부터, 배열 인덱스
    created_at: datetime
```

```python
# src/domain/agent_opener/policies.py
class OpenerPolicy:
    MAX_COUNT = 12
    MAX_LENGTH = 200

    @classmethod
    def normalize(cls, texts: list[str]) -> list[str]:
        """strip → 빈 항목 거부 → 중복 거부 → 개수·길이 재검증. 순서 보존.
        예외 메시지에 '최대'·'이미'·'찾을 수 없' 문자열 금지(라우터 매퍼가 409/404로 바꿈).
        """
```

정책 예외 메시지(고정):

| 조건 | 메시지 |
|---|---|
| strip 후 빈 문자열 | `오프너 {n}번째 항목이 비어 있습니다` |
| 중복(정확 일치, strip 후) | `오프너 {n}번째 항목이 앞의 항목과 중복됩니다` |
| 길이 > 200 | `오프너 {n}번째 항목은 200자 이하여야 합니다` |
| 개수 > 12 | `오프너는 12개까지 등록할 수 있습니다` |

> Check G1(2026-10-25): 메시지에 **사용자 텍스트를 절대 넣지 않는다** — 텍스트에 '최대'·'이미'·'찾을 수 없'이 섞이면 라우터 매퍼가 409/404로 바꾼다. 위치 번호 `{n}`(1부터)만 쓴다.

> 개수·길이는 Pydantic이 먼저 422로 막는다. 정책 재검증은 use case를 직접 호출하는 경로(포크·테스트)를 위한 2차 방어.

### 3.2 Entity Relationships

```
[agent_definition] 1 ──── N [agent_opener]   (agent_id, ON DELETE CASCADE)
```

- `AgentDefinition` 도메인 엔티티에는 필드를 추가하지 않는다 (hot path 무영향, Option C).
- 기존 `erd-agent` 위키 관례와 동일: "FK 진실은 SQL", ORM에는 FK 미선언.

### 3.3 Database Schema

```sql
-- V080__create_agent_opener.sql
-- agent-opener Design §3.3:
--   에이전트별 대화 시작 예시 질문. 순서는 sort_order(배열 인덱스). 전체 교체 저장.
--   agent_definition 삭제는 소프트(status=deleted)라 CASCADE는 하드 삭제 대비용.
-- ⚠️ FK 콜레이션 주의(errno 3780, V034/V037 선례): agent_definition은 SQLAlchemy create_all 생성 —
--   테이블 레벨 COLLATE 미명시로 DB 기본 콜레이션 상속.
-- ⚠️ COMMENT 안에 최상위 콤마 금지(tests/db/test_migration_ddl_comments.py 파서).
CREATE TABLE agent_opener (
    id          VARCHAR(36)  PRIMARY KEY,
    agent_id    VARCHAR(36)  NOT NULL,
    text        VARCHAR(200) NOT NULL COMMENT '예시 질문 본문(strip 완료)',
    sort_order  INT          NOT NULL DEFAULT 0 COMMENT '표시 순서(작을수록 먼저)',
    created_at  DATETIME     NOT NULL,
    CONSTRAINT fk_agent_opener_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition(id) ON DELETE CASCADE,
    INDEX ix_agent_opener_agent (agent_id)
) ENGINE=InnoDB;
```

ORM (`src/infrastructure/persistence/models/agent_opener/models.py`): `AgentSkillModel`과 같은 형태, `__tablename__ = "agent_opener"`, FK 미선언, `agent_id` index=True.

### 3.4 Repository Port

```python
# src/domain/agent_opener/interfaces.py
class AgentOpenerRepositoryInterface(ABC):
    async def list_by_agent_id(self, agent_id: str, request_id: str) -> list[str]: ...
    async def list_by_agent_ids(self, agent_ids: list[str], request_id: str) -> dict[str, list[str]]:
        """배치 1쿼리. 빈 입력 → {} (쿼리 없음). 없는 agent_id는 키 자체 부재."""
    async def replace(self, agent_id: str, texts: list[str], request_id: str) -> list[str]:
        """DELETE agent_id 전부 → INSERT enumerate(texts). commit/rollback 금지(세션 미들웨어)."""
```

반환형을 엔티티가 아닌 `list[str]`로 둔 이유: 모든 소비자(API 응답·채팅·포크)가 텍스트 배열만 쓴다. 엔티티는 리포지토리 내부 매핑용.

---

## 4. API Specification

### 4.1 Endpoint List (변경분만 — 신규 엔드포인트 없음)

| Method | Path | 변경 | Auth |
|--------|------|------|------|
| POST | `/api/v1/agents` | 요청 `openers?`, 응답 `openers` | Required |
| PATCH | `/api/v1/agents/{agent_id}` | 요청 `openers?` (None=무변경, []=전부 삭제) | Required (can_edit) |
| GET | `/api/v1/agents/{agent_id}` | 응답 `openers: string[]` | Required |
| GET | `/api/v1/agents/my` | 응답 `agents[].openers: string[]` | Required |
| POST | `/api/v1/agents/{agent_id}/fork` | 동작: 원본 오프너 복사 (계약 무변경) | Required |

### 4.2 Detailed Specification

#### `CreateAgentRequest` / `UpdateAgentRequest` (application/agent_builder/schemas.py)

```python
# agent-opener D4: 대화 시작 예시 질문. None = (create) 없음 / (update) 변경 안 함.
# 개수·길이 상한은 여기서 422. 정규화(strip·빈값·중복)는 OpenerPolicy.
openers: list[str] | None = Field(None, max_length=12)
# 항목 길이는 Annotated[str, StringConstraints(max_length=200)] 로 선언 (strip 전 길이 기준 — 200자 초과 입력은 즉시 거부)
```

#### `GetAgentResponse` / `MyAgentSummary` / `CreateAgentResponse`

```python
# agent-opener D4: sort_order ASC. 미주입·없음 = []
openers: list[str] = []
```

#### 요청/응답 예시

```json
// PATCH /api/v1/agents/{id}
{ "openers": ["저축은행 BIS 비율 상위/하위 3개사를 분석해줘", "이번 분기 BIS 비율 변동 원인을 요약해줘"] }

// GET /api/v1/agents/my (항목)
{ "agent_id": "…", "name": "…", "description": "…", "source_type": "owned", "openers": ["…", "…"], … }
```

**Error Responses**

| 상태 | 조건 | 발생 지점 |
|---|---|---|
| 422 | 13개 이상 / 항목 201자 이상 | Pydantic (FastAPI 기본 `detail` 배열) |
| 422 | strip 후 빈 항목 / 중복 | `OpenerPolicy` ValueError → 라우터 매퍼 기본 분기 |
| 403 | can_edit 아님 | 기존 Update 가드 |
| 404 | 에이전트 없음 | 기존 |

### 4.3 Use Case 변경

| Use case | 변경 | 비고 |
|---|---|---|
| `CreateAgentUseCase` | `opener_repo: AgentOpenerRepositoryInterface \| None = None` 주입. `saved` 직후(Step 4.5 스킬 동기화 옆) `if request.openers and repo: texts = OpenerPolicy.normalize(...); await repo.replace(saved.id, texts)`. 응답 `openers=texts` | 정규화는 **save 전**에 수행해 무효면 에이전트도 저장하지 않는다(all-or-nothing은 세션 롤백) |
| `UpdateAgentUseCase` | 동일 주입. `if request.openers is not None and repo: replace(agent.id, normalize(...))` | `[]` → replace(…, []) = 전부 삭제 |
| `GetAgentUseCase` | 동일 주입. `openers = await repo.list_by_agent_id(...)` if repo else [] | `agent_skill_repo` 선례와 같은 자리 |
| `ListMyAgentsUseCase` | 동일 주입. `all_items` 조립 완료 후 **페이지 슬라이스된 항목의 id로** `list_by_agent_ids` 1회 → 각 summary에 부착 | 페이지 밖 항목은 조회하지 않는다 |
| `ForkAgentUseCase` | 동일 주입. `save(forked)` 후 `src = list_by_agent_id(source)`; `if src: replace(new_id, src)` | 정규화 불필요(이미 저장된 값) |
| `AutoForkService` | 변경 없음 | 내부 포크 경로는 범위 밖, 보고에 명시 |

### 4.4 DI (`src/api/main.py`)

- `_make_agent_opener_repo(session)` 헬퍼 추가 (`_make_agent_skill_repo` 옆).
- `create_uc_factory` · `update_uc_factory` · `get_uc_factory` · `list_my_uc_factory` · `fork_uc_factory` 5곳에 `opener_repo=` 전달.
- 배선 계약 테스트: `tests/api/test_agent_builder_router.py`에 "PATCH openers 후 GET detail에 반영" 왕복 1건 (TestClient 인프로세스, 메모리 레시피 참조). 정적 검사만으로 종료 금지(`false-green-quality-gates`).

---

## 5. UI/UX Design

### 5.1 Screen Layout — 빌더 오프너 탭 (`docs/img/offner.png`)

```
┌ Fix 에이전트 │ 테스트 │ [오프너] │ 파일 │ 스킬 │ 스케줄 │ 설정 ┐
├────────────────────────────────────────────────────────────────┤
│ 사용자가 대화를 시작할 수 있는 예시 질문을 설정하세요   3/12  [+ 추가] │
├────────────────────────────────────────────────────────────────┤
│ ┌────────────────────────────────────────────────────────────┐ │
│ │ (1)  저축은행 BIS 비율 상위/하위 3개사를 분석해줘        [×] │ │
│ └────────────────────────────────────────────────────────────┘ │
│ ┌────────────────────────────────────────────────────────────┐ │
│ │ (2)  이번 분기 BIS 비율 변동 원인을 요약해줘             [×] │ │
│ └────────────────────────────────────────────────────────────┘ │
│ ┌────────────────────────────────────────────────────────────┐ │
│ │ (3)  저축은행별 BIS 비율 비교 보고서를 작성해줘          [×] │ │
│ └────────────────────────────────────────────────────────────┘ │
│                                                                │
│ (0개일 때) "아직 등록된 오프너가 없습니다. + 추가로 시작하세요"      │
└────────────────────────────────────────────────────────────────┘
```

- 각 행: 번호 배지(회색 원) + `input`(maxLength 200, placeholder "예시 질문을 입력하세요") + 삭제 버튼(`aria-label="오프너 {n} 삭제"`, 시안에는 보이지 않으나 hover/우측에 배치).
- `+ 추가`: 빈 행을 끝에 추가하고 그 input에 focus. 12개면 disabled + title "최대 12개".
- 카운터 `n/12`: 빈 행 포함 현재 행 수.
- 저장 버튼은 StudioHeader. 저장 시 `form.openers`에서 strip 후 빈 행을 **제거**해 전송(빈 행은 422가 아니라 조용히 버림 — 입력 중 빈 행 때문에 저장이 막히지 않게). 중복은 프론트에서 막지 않고 서버 422 메시지를 기존 에러 경로로 표시.

### 5.2 채팅 빈 상태 (`/chatpage`, 메시지 0건)

```
                 [로고]
        {agent.name}와 대화하세요
        {agent.description}
   ┌──────────────────────┐ ┌──────────────────────┐
   │ 💬 저축은행 BIS 비율… │ │ 💬 이번 분기 BIS …   │
   └──────────────────────┘ └──────────────────────┘
   ┌──────────────────────┐
   │ 💬 저축은행별 BIS …  │
   └──────────────────────┘
```

- 오프너 카드: 기존 `SuggestionCards` 스타일 그대로(2열 그리드), 아이콘은 `MessageSquare` 고정, `label` = 텍스트 전체(1줄 생략 없이 줄바꿈 허용), 보조 텍스트 없음.
- `agent.openers?.length > 0` → 오프너 카드. 아니면 기존 고정 4종. `selectedAgent.id === 'super'` → 항상 고정 4종(super의 `AgentSummary`에는 openers를 넣지 않는다).
- 빌더 테스트 탭(`TestChatView`) 빈 상태는 **변경 없음**(범위 밖).

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `OpenerPanel` (new) | `components/agent-builder/opener/OpenerPanel.tsx` | 안내문·카운터·추가·행 목록·삭제. props: `openers: string[]`, `onChange(next: string[])` |
| `OpenerRow` (new, 같은 파일 내부 컴포넌트 또는 `OpenerRow.tsx`) | 같은 폴더 | 번호·입력·삭제 1행 |
| `AgentTestPanel` (mod) | `components/agent-builder/AgentTestPanel.tsx` | `opener.enabled: true`, 분기 추가, docstring 갱신 |
| `StudioLayout` (mod) | 같은 폴더 | `onOpenersChange` prop 전달 |
| `AgentBuilderPage` (mod) | `pages/AgentBuilderPage/index.tsx` | 초기값 `openers: []`, `handleOpenersChange`, create/update 페이로드 `openers` |
| `agentDetailMapping` (mod) | `utils/agentDetailMapping.ts` | `openers: detail.openers ?? []` |
| `SuggestionCards` (mod) | `components/chat/MessageList.tsx` | `items?: Suggestion[]` optional prop |
| `EmptyAgentState` (mod) | `pages/ChatPage/index.tsx` | 오프너 → items 변환·분기 |
| `toAgentSummary` (mod) | `services/agentSubscriptionService.ts` | `openers: agent.openers ?? []` |
| 타입 (mod) | `types/agentBuilder.ts`, `types/agent.ts` | 요청·폼·`MyAgent`·`AgentSummary` 필드 |
| 상수 (new) | `constants/agentOpener.ts` | `OPENER_LIMITS = { MAX_COUNT: 12, MAX_LENGTH: 200 } as const` |

### 5.4 Page UI Checklist

#### 빌더 오프너 탭 (`/agent-builder`, `/agent-builder?agentId=…`)

- [ ] Tab: "오프너" 탭이 활성(클릭 가능, "준비중" 툴팁 없음)
- [ ] Text: 안내문 "사용자가 대화를 시작할 수 있는 예시 질문을 설정하세요"
- [ ] Counter: `{n}/12` (행 수 반영)
- [ ] Button: `+ 추가` — 클릭 시 빈 행 추가 + focus, 12개면 disabled
- [ ] Row: 번호 배지 1..n, input(maxLength 200, value=text), 삭제 버튼(aria-label)
- [ ] Empty: 0개일 때 안내 문구
- [ ] Save: StudioHeader 저장 → create 페이로드 `openers`(빈 행 제거), update 페이로드 `openers`(항상 전송 = 전체 교체 기준선)
- [ ] Prime: edit 진입 시 detail.openers로 행 채움
- [ ] Error: 서버 422(중복) 메시지가 기존 저장 실패 경로로 표시, 입력값 유지

#### 채팅 빈 상태 (`/chatpage?agentId=…`)

- [ ] Card: 오프너 수만큼 카드(2열), 텍스트 전체 표시, `MessageSquare` 아이콘
- [ ] Click: 카드 클릭 → `handleSend(text)` 호출(사용자 메시지로 즉시 전송)
- [ ] Fallback: openers 없음 → 기존 고정 4종 카드
- [ ] Super: `super` 선택 시 고정 4종
- [ ] Safety: `<script>` 포함 텍스트가 문자 그대로 렌더

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | 조건 | 발생 | 처리 |
|------|------|------|------|
| 422 | 13개↑ / 201자↑ | Pydantic | 프론트 가드로 사실상 미발생, 발생 시 저장 실패 모달 |
| 422 | 빈 항목 / 중복 | OpenerPolicy | 저장 실패 모달에 메시지, 폼 유지 |
| 403 | 수정 권한 없음 | 기존 | 기존 |
| 404 | 에이전트 없음 | 기존 | 기존 |

### 6.2 Error Response Format

기존 FastAPI `{"detail": "..."}` / Pydantic `{"detail": [...]}`. 프론트는 `ApiError(message,status,code)` 인터셉터 경로 그대로(메모리 `idt-front-apierror-interceptor`).

### 6.3 라우터 매퍼 함정 (반드시 지킬 것)

`_attach_skill_http_error`(POST)와 PATCH의 분기는 **메시지 문자열**로 상태 코드를 정한다. `OpenerPolicy` 메시지에 `최대`, `이미`, `찾을 수 없`이 들어가면 409/404로 바뀐다. 테스트로 고정: 두 라우터 각각 중복 입력 → 422 단언.

---

## 7. Security Considerations

- [x] 입력 검증: 길이·개수 Pydantic, 정규화 도메인. HTML/마크다운 미해석(React 텍스트 렌더).
- [x] 인가: create/update는 기존 소유자·can_edit 가드 뒤. 목록/상세는 기존 가시성 규칙 그대로(오프너는 에이전트와 같은 가시성).
- [x] 민감정보 없음. 암호화 불필요.
- [ ] Rate limiting: 기존 정책 그대로(추가 없음).

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| 단위 (BE) | `OpenerPolicy.normalize` | pytest | Do (module-1) |
| 단위 (BE) | 5개 use case의 opener_repo 호출(fake repo) | pytest | Do (module-1) |
| L1 API | POST/PATCH/GET detail/GET my 계약 + 422 | pytest TestClient (인프로세스, 로컬 DB) | Do (module-1) |
| 단위 (FE) | `OpenerPanel`, `SuggestionCards items`, `EmptyAgentState` 분기 | Vitest + RTL | Do (module-2/3) |
| 통합 (FE) | `AgentBuilderPage` 저장 페이로드·프라임 | Vitest + MSW | Do (module-2) |
| L3 수동 E2E | 등록 → 저장 → 재진입 → 채팅 노출 → 클릭 전송 | 브라우저 | Check |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Method | Test | Expected |
|---|----------|--------|------|----------|
| 1 | `/api/v1/agents` | POST | `openers` 2건 포함 생성 | 201, 응답 `openers` 2건 순서 보존 |
| 2 | `/api/v1/agents` | POST | `openers` 미전달 | 201, `openers: []` (기존 테스트 무변경) |
| 3 | `/api/v1/agents` | POST | 13건 | 422 |
| 4 | `/api/v1/agents` | POST | 201자 항목 | 422 |
| 5 | `/api/v1/agents` | POST | `["a","a"]` 중복 | **422** (409 아님) |
| 6 | `/api/v1/agents/{id}` | PATCH | `openers: ["x"]` → GET detail | 200 → `openers == ["x"]` (4곳 세트 왕복 증명) |
| 7 | `/api/v1/agents/{id}` | PATCH | `openers: []` | 200 → GET `openers == []` |
| 8 | `/api/v1/agents/{id}` | PATCH | `openers` 미전달(name만) | GET `openers` 이전 값 유지 |
| 9 | `/api/v1/agents/{id}` | PATCH | `[" a ", "a"]` | 422 (strip 후 중복) |
| 10 | `/api/v1/agents/my` | GET | 오프너 있는/없는 에이전트 혼재 | 각 항목 `openers` 정확, 리포지토리 `list_by_agent_ids` **1회 호출** |
| 11 | `/api/v1/agents/{id}/fork` | POST | 원본 오프너 3건 | 사본 GET `openers` 3건 동일 |
| 12 | DDL | — | V080 | `test_migration_ddl_comments.py` 통과 |

### 8.3 L2: UI Action Test Scenarios

| # | Page | Action | Expected |
|---|------|--------|----------|
| 1 | 빌더 | 오프너 탭 클릭 | 안내문·`0/12`·`+ 추가` 표시, 빈 안내 문구 |
| 2 | 빌더 | `+ 추가` ×3, 입력 | `3/12`, 번호 1~3, input value 반영 |
| 3 | 빌더 | 12행에서 `+ 추가` | 버튼 disabled |
| 4 | 빌더 | 2번 행 삭제 | 2행, 번호 재부여 |
| 5 | 빌더(create) | 행 2개(하나 빈값) + 저장 | create 요청 `openers`에 1건만 |
| 6 | 빌더(edit) | detail.openers 2건으로 진입 | 행 2개 프라임, 저장 시 update 요청 `openers` 2건 |
| 7 | 빌더 | 서버 422 응답 | 실패 모달 메시지, 행 유지 |
| 8 | 채팅 | openers 3건 에이전트 선택 | 카드 3개, 고정 4종 미표시 |
| 9 | 채팅 | 카드 클릭 | `handleSend` 해당 텍스트로 1회 |
| 10 | 채팅 | openers 없는 에이전트 / super | 고정 4종 |
| 11 | 채팅 | `<script>alert(1)</script>` 오프너 | 텍스트로 렌더 |

### 8.4 L3: E2E Scenario

| # | Scenario | Steps | Success |
|---|----------|-------|---------|
| 1 | 등록→노출→전송 | 빌더 edit → 오프너 3건 → 저장 → 새로고침 프라임 확인 → `/chatpage` 해당 에이전트 → 카드 3개 → 클릭 → 사용자 메시지 전송·응답 수신 | 전 단계 통과 |
| 2 | 회귀 | 오프너 없는 기존 에이전트·super 채팅 | 기존 화면 동일 |

### 8.5 Seed Data

| Entity | 수 | 필드 |
|--------|:--:|------|
| agent_definition | 2 (오프너 있음/없음) | 로컬 사용자 소유, status=active |
| agent_opener | 3 | 위 1번 에이전트, sort_order 0..2 |

로컬 DB에 Flyway 이력이 없으므로 V080은 수동 적용(메모리 `idt-local-db-and-run-repro`).

---

## 9. Clean Architecture

### 9.1 This Feature's Layer Assignment (백엔드)

| Component | Layer | Location |
|-----------|-------|----------|
| `AgentOpener`, `OpenerPolicy`, `AgentOpenerRepositoryInterface` | Domain | `src/domain/agent_opener/{schemas,policies,interfaces}.py` |
| 스키마 필드·5 use case 변경 | Application | `src/application/agent_builder/` |
| `AgentOpenerModel` | Infrastructure | `src/infrastructure/persistence/models/agent_opener/models.py` |
| `AgentOpenerRepository` | Infrastructure | `src/infrastructure/agent_opener/agent_opener_repository.py` |
| DI 5곳 | API | `src/api/main.py` |

### 9.2 Dependency Rules

- Domain `agent_opener`는 외부 import 없음. `agent_builder` use case → `agent_opener` 포트 (application → domain, 허용).
- `AgentDefinition` 엔티티·`AgentDefinitionRepository`는 **무변경**.

### 9.3 프론트 배치

| Component | Layer | Location |
|---|---|---|
| 타입·상수 | Domain | `types/agentBuilder.ts`, `types/agent.ts`, `constants/agentOpener.ts` |
| `OpenerPanel` | Presentation | `components/agent-builder/opener/` |
| 페이로드·프라임 | Application | `pages/AgentBuilderPage`, `utils/agentDetailMapping.ts` |
| 채팅 분기 | Presentation | `pages/ChatPage`, `components/chat/MessageList.tsx` |
| 변환 | Infrastructure | `services/agentSubscriptionService.ts` |

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 네이밍 | 테이블 `agent_opener`, API `openers`, 폼 `openers`, 컴포넌트 `OpenerPanel`/`OpenerRow`, 상수 `OPENER_LIMITS` |
| 상수 위치 | `constants/agentOpener.ts` (컴포넌트 파일 런타임 export 금지) |
| 코드 주석 | 파일 머리 `// Design Ref: agent-opener §N` / 핵심 로직 `// Plan SC: FR-NN` |
| 마이그레이션 | V080, ENGINE만, COMMENT 최상위 콤마 금지 |
| 테스트 실행 | `uv run python -m pytest`(uv run pytest 금지), 회귀는 정렬된 FAILED 목록 diff |
| 뮤테이션 버튼 | 신규 뮤테이션 없음(저장은 기존 StudioHeader) |
| 계약 동기화 | 스키마 변경 후 `/api-contract-sync` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
  db/migration/V080__create_agent_opener.sql                     (new)
  src/domain/agent_opener/__init__.py, schemas.py, policies.py, interfaces.py   (new)
  src/infrastructure/persistence/models/agent_opener/__init__.py, models.py     (new)
  src/infrastructure/agent_opener/__init__.py, agent_opener_repository.py       (new)
  src/application/agent_builder/schemas.py                        (mod: 5 스키마)
  src/application/agent_builder/{create,update,get,list_my,fork}_agent_use_case.py (mod)
  src/api/main.py                                                 (mod: 헬퍼 + DI 5곳)
  tests/domain/agent_opener/test_opener_policy.py                 (new)
  tests/application/agent_builder/test_agent_opener_use_cases.py  (new)
  tests/api/test_agent_builder_router.py                          (mod: 422·왕복)
idt_front/src/
  constants/agentOpener.ts                                        (new)
  types/agentBuilder.ts, types/agent.ts                           (mod)
  components/agent-builder/opener/OpenerPanel.tsx (+ .test.tsx)   (new)
  components/agent-builder/AgentTestPanel.tsx, StudioLayout.tsx   (mod)
  pages/AgentBuilderPage/index.tsx (+ index.test.tsx)             (mod)
  utils/agentDetailMapping.ts                                     (mod)
  components/chat/MessageList.tsx                                 (mod: items prop)
  pages/ChatPage/index.tsx                                        (mod: 분기)
  services/agentSubscriptionService.ts                            (mod)
```

### 11.2 Implementation Order

1. [ ] V080 + ORM + 포트 + `OpenerPolicy`(테스트 먼저)
2. [ ] `AgentOpenerRepository` (replace/list/list_by_agent_ids)
3. [ ] 스키마 5종 + use case 5종(fake repo 테스트) + DI
4. [ ] 라우터 TestClient 테스트(422 ×2, PATCH→GET 왕복, my 배치) + 로컬 V080 적용 + 실런 스모크
5. [ ] 프론트 타입·상수 → `OpenerPanel`(테스트 먼저) → 탭 활성 → 페이지 페이로드·프라임
6. [ ] `SuggestionCards items` → `EmptyAgentState` 분기 → `toAgentSummary`
7. [ ] `/api-contract-sync` 체크, FAILED diff, 수동 E2E

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 백엔드 저장·API | `module-1` | 11.2의 1~4 (idt) | 35-45 |
| 빌더 오프너 탭 | `module-2` | 11.2의 5 (idt_front) | 25-35 |
| 채팅 빈 상태 | `module-3` | 11.2의 6~7 (idt_front) | 15-20 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| 1 | Plan + Design | 전체 | 완료 |
| 2 | Do | `--scope module-1` | 35-45 |
| 3 | Do | `--scope module-2,module-3` | 40-55 |
| 4 | Check + Report | 전체 | 25-35 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-24 | 초안 — Option C 선택, Plan 확인 필요 4건 확정, 라우터 매퍼 함정 반영 | 배상규 |
| 0.2 | 2026-10-25 | Check G1 반영 — 정책 메시지에서 사용자 텍스트 제거(위치 번호만) | 배상규 |
