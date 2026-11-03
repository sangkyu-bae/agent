# agent-run-source-citations Design Document

> **Summary**: 실행 기록을 읽어 근거 목록을 조립하는 단일 정책을 만들고, WS 답변 이벤트와 인증된 세션 근거 API로 전달해 `SourceCitation`에 표시한다.
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-02
> **Status**: Draft
> **Planning Doc**: [agent-run-source-citations.plan.md](../../01-plan/features/agent-run-source-citations.plan.md)

---

## Context Anchor

> Copied from Plan document. Ensures strategic context survives Design→Do handoff.

| Key | Value |
|-----|-------|
| **WHY** | 근거는 저장되지만 에이전트 답변에 표시되지 않아 사용자가 답변을 원문과 대조할 수 없다. |
| **WHO** | P1 여신 심사역, P4 일반 사용자(최종 사용자). P2 에이전트 소유자는 답변 품질 확인에 활용한다. |
| **RISK** | MCP 결과의 근거 판별 오류와 민감정보 노출, 공유 에이전트에서 KB 권한이 없는 사용자에게 청크 발췌 노출, 검색 근거를 "실제 인용"으로 오해할 가능성. |
| **SUCCESS** | 실시간과 재진입의 칩 목록 일치, 4종 근거의 실런 표시, 답변 흐름 비차단, 기존 경로 회귀 0건. |
| **SCOPE** | M1 근거 조립 정책 → M2 실시간 경로 → M3 세션 근거 API → M4 프론트 칩·발췌 패널 |

---

## 1. Overview

### 1.1 Design Goals

- 실시간과 재진입이 같은 코드 경로로 같은 근거 목록을 만든다.
- 쓰기 경로와 스키마를 변경하지 않고 기존 실행 기록만 읽는다.
- 근거 처리 실패가 답변과 히스토리를 막지 않는다.
- 인증된 경로로만 발췌를 전달한다.

### 1.2 Design Principles

- 근거 판정은 도메인 순수 정책 한 곳에 둔다.
- 계약 변경은 additive로 하고 기존 소비자를 수정하지 않는다.
- 근거 여부를 판단할 수 없는 MCP 호출은 표시하지 않는다.
- 실패 흡수는 서비스 한 곳에서 처리한다.

### 1.3 실측 결과 (2026-11-02, 로컬 DB)

| 항목 | 결과 | 설계 영향 |
|------|------|----------|
| 히스토리 API 인증 | `conversation_history_router.py`에 `get_current_user` 없음, 앱 미들웨어에도 인증 없음 | 응답에 발췌를 싣지 않고 인증 엔드포인트 신설 (§4) |
| 문서 라벨 키 | `metadata_json.source` 0건, `filename` 134/223건 | `document_metadata.filename` 일괄 조회 보강 (§3.3) |
| `document_metadata` 일치 | 문서 5개 중 4개 | `kb_name` 폴백 필수 |
| `metadata_json` 내용 | `morph_text`, `morph_keywords`, `user_id` 포함 | 원본을 응답으로 내보내지 않음 |
| MCP 실패 표기 | 170건 중 50건이 `status=SUCCESS`이면서 본문이 `Error executing tool` | 본문으로 실패 재판정 (§3.3) |
| MCP 요약 형식 | 170건 중 144건이 `{"content": "..."}` 래퍼, 절단 가능 | 래퍼 해제 함수 필요 |
| MCP 도구명 | `mcp_{uuid}_{tool}`, 64자 초과 시 해시 접미사 | 문자열 역파싱 대신 카탈로그에서 정방향 계산 |
| MCP `category` | 26개 전부 NULL, `requires_approval` 3개 | 제외 방식 채택 |
| 위키 | `wiki_read` 19건, `article_id`와 `[위키 문서: 제목]` 저장 | `ai_tool_call`에서 조립 |
| 런↔메시지 | 메시지당 런 1건(200건), 런 38건은 `user_message_id` 없음 | 마지막 런 규칙 유지, 없으면 근거 없음 |
| 서브에이전트 | 깊이 1 이상 스텝의 도구 호출 기록 존재 (표본 1개 런) | `run_id`로 조회. 실런에서 재확인 |
| 포트 구현체 | `AgentRunRepositoryInterface` 1개, `DocumentMetadataRepositoryInterface` 2개, fake 상속 없음 | 추상 메서드 추가 가능 |

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | UseCase 내부 조립, 메시지별 조회 | 전용 모듈, 읽기 모델 포트·어댑터 | 순수 정책 + 공유 서비스 + 인증 API 1개 |
| **New Files** | 1 | 12 | 5 (백 4, 프론트 1) |
| **Modified Files** | 10 | 18 | 18 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | N+1, SC-1 불일치 | 과도한 추상화 | 낮음 |
| **Recommendation** | FR-09 위반 | 소비자 2곳에 과함 | **선택** |

**Selected**: Option C — **Rationale**: 소비자가 실시간과 재진입 2곳이라 공유 서비스 1개로 충분하다. 두 경로가 같은 코드를 지나므로 SC-1이 구조로 보장된다.

### 2.1 Component Diagram

```
                    ┌────────────────────────────────┐
 ws_router ───────▶ │ RunAgentUseCase.stream          │
 include_sources    │  (include_sources=True)         │
                    └───────────────┬────────────────┘
                                    ▼
                    ┌────────────────────────────────┐
                    │ SessionScopedRunSourcesReader   │  세션 1개 생성
                    └───────────────┬────────────────┘
                                    ▼
 agent_run_router ─▶ GetSessionSourcesUseCase ─▶ RunSourcesService
 GET .../sources                                   │  실패 흡수
                                                   ▼
          AgentRun repo · DocumentMetadata repo · ToolCatalog repo
                                                   │
                                                   ▼
                                  RunSourcePolicy.build (domain, 순수)
```

### 2.2 Data Flow

```
실시간
  graph 종료 → 답변 저장 → load_for_run(run_id) → ANSWER_COMPLETED.sources
  → useAgentRunStream → view.sources → Message.sources → SourceCitation

재진입
  GET messages (기존, 비인증) ┐
                              ├─ useAgentSessionMessages 병합 → Message.sources
  GET sources  (신규, 인증)   ┘
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `RunSourcePolicy` | 없음 (`dataclass`, `re`, `json`) | 필터·라벨·중복 제거·상한 |
| `RunSourcesService` | 저장소 포트 3종, 정책, logger | 증거 수집, 실패 흡수 |
| `SessionScopedRunSourcesReader` | `session_factory`, repo 빌더 | 실시간 경로용 세션 관리 |
| `GetSessionSourcesUseCase` | 메시지 저장소, 런 저장소, 서비스 | 세션 단위 조립 |
| `RunAgentUseCase` | `RunSourcesReaderPort \| None` | optional 마지막 인자 |

---

## 3. Data Model

스키마 변경은 없다. 신규 타입은 코드 수준이다.

### 3.1 Entity Definition

```python
# domain/agent_run/source_policy.py
class SourceKind(StrEnum):
    DOCUMENT = "document"
    WIKI = "wiki"
    WEB = "web"
    MCP = "mcp"

@dataclass(frozen=True)
class RunSourceItem:
    kind: SourceKind
    label: str          # 칩 표시 이름
    excerpt: str        # 발췌. 없으면 ""
    key: str            # 문서 id / 위키 id / URL / mcp tool_id
    url: Optional[str] = None  # web 전용, http/https만

@dataclass(frozen=True)
class McpToolInfo:
    display_name: str
    requires_approval: bool
    category: Optional[str]

@dataclass(frozen=True)
class RunEvidence:
    retrievals: list[RetrievalSource]
    tool_calls: list[ToolCall]
    filenames: dict[str, str]             # document_id → filename
    mcp_tools: dict[str, McpToolInfo]     # 런타임 tool_name → 정보
```

### 3.2 Wire Format

프론트 `DocumentSource`와 같은 키를 쓴다. 에이전트 근거에는 `score`가 없다.

```json
{
  "kind": "web",
  "source": "한국 금리결정",
  "content": "발췌 텍스트",
  "chunk_id": "https://kr.investing.com/...",
  "url": "https://kr.investing.com/..."
}
```

`url`은 `kind=web`일 때만 존재한다. `chunk_id`는 모든 종류에서 항상 채운다(React key, 위키 이동 id).

### 3.3 정책 규칙

| 종류 | 입력 | 제외 | 중복 제거 키 | 라벨 |
|------|------|------|-------------|------|
| web | `collection_name=tavily_web` | - | `url_full` → `document_id` | `metadata.title` → URL 호스트 |
| document | 그 외 retrieval | - | 파일명 → `document_id` → `chunk_id` (실측: 재업로드 문서의 칩 중복) | `metadata.filename` → `filenames[document_id]` → `metadata.clause_title` → `metadata.kb_name` → `"문서"` |
| wiki | `tool_name=wiki_read` | `[위키 문서:` 헤더 없음 (열람 실패) | `article_id` | 헤더의 제목 |
| mcp | `mcp_tools`에 있는 `tool_name` | 아래 표 | `tool_name` | `display_name` |

MCP 제외 규칙은 하나라도 해당하면 표시하지 않는다.

| 규칙 | 근거 |
|------|------|
| 카탈로그에서 찾을 수 없음 | 부작용 여부를 판단할 수 없어 fail-closed |
| `requires_approval=true` | 사용자 결정 (send_mail 등) |
| `category="action"` | 사용자 결정 |
| `status=FAILED` | 실패 호출 |
| 해제 후 본문이 비었음 | 근거 없음 |
| 해제 후 본문이 `Error executing tool`로 시작 | 실측 50건 (`MCPToolAdapter`가 `isError`를 보지 않음) |

**정렬과 상한**

1. 종류별로 `(created_at, rank_index, id)` 오름차순으로 정렬한다. `id` 타이브레이커로 결과를 결정적으로 만든다.
2. 키별 첫 항목을 대표로 남긴다.
3. `document → wiki → web → mcp` 순서로 라운드로빈해 총 N건을 고른다. 한 종류가 상한을 독점하지 않게 하여 Plan의 절단 위험을 해소한다.
4. 출력은 종류 순서로 묶는다. 검색 방식 간 점수는 비교하지 않는다.

**`RunSourceItem.excerpt`**

- document, web: `content_preview` (기록 시 500바이트 상한)
- wiki, mcp: 래퍼를 해제한 `result_summary` (기록 시 1KB 상한)

래퍼 해제(`unwrap_tool_summary`)는 `json.loads` 후 `content`를 쓰고, 절단으로 실패하면 `{"content": "` 접두를 제거하고 `\"`, `\n`, `\\`만 되돌린다. 그 외 문자열은 원문을 그대로 쓴다.

**MCP 런타임 이름 계산**

`tool_id = mcp:{srv}:{tool}`에서 `MCPConnectionPolicy.build_tool_name(f"mcp_{srv}_{tool}")`을 계산해 `mcp_tools` 맵의 키로 쓴다. 해시 접미사가 붙은 이름도 같은 함수로 일치한다.

### 3.4 저장소 추가

| 포트 | 메서드 | 쿼리 |
|------|--------|------|
| `AgentRunRepositoryInterface` | `find_latest_runs_by_user_messages(ids) -> dict[int, AgentRun]` | `user_message_id IN (...)`, `started_at` 오름차순 후 마지막 |
| `AgentRunRepositoryInterface` | `find_retrievals_by_runs(run_ids) -> dict[str, list]` | `run_id IN (...)` |
| `AgentRunRepositoryInterface` | `find_tool_calls_by_runs(run_ids) -> dict[str, list]` | `run_id IN (...)` |
| `DocumentMetadataRepositoryInterface` | `find_filenames(document_ids, request_id) -> dict[str, str]` | `document_id IN (...)` |

`ToolCatalogRepositoryInterface.list_active`는 기존 메서드를 재사용한다. `find_filenames`는 `DocumentMetadataRepository`와 `SessionScopedDocumentMetadataRepository`에 모두 구현한다. Repository 내부에서 commit하지 않는다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/conversations/agents/{agent_id}/sessions/{session_id}/sources` | 세션의 assistant 메시지별 근거 | Required |
| WS | `/ws/agent/{room}` `agent_answer_completed` | optional `sources` 추가 | 기존 |

기존 메시지 API는 변경하지 않는다.

### 4.2 Detailed Specification

#### `GET .../sessions/{session_id}/sources`

`agent_run_router.py`에 추가한다. 이 라우터는 `get_current_user`를 쓰고 있다.

**Response (200):**
```json
{
  "session_id": "s1",
  "items": [
    {
      "message_id": 102,
      "sources": [
        { "kind": "document", "source": "최선집행기준설명서.pdf", "content": "...", "chunk_id": "4f34..." }
      ]
    }
  ]
}
```

**처리 순서**

1. `find_by_session(current_user.id, session_id)`로 메시지를 읽는다. `user_id`는 쿼리로 받지 않는다.
2. `id` 오름차순으로 순회하며 assistant를 직전 user 메시지와 짝짓는다. `turn_index`를 쓰지 않아 수정 전 데이터도 처리된다.
3. user 메시지별 마지막 런을 일괄 조회하고 `agent_id`가 다른 런을 버린다.
4. `RunSourcesService.build_for_runs`로 조립한다. 근거가 없는 메시지는 `items`에서 뺀다.

**응답 규칙**

| 상황 | 결과 |
|------|------|
| 세션 없음 또는 타인 세션 | `200`, `items: []` (존재 여부 비노출) |
| 근거 조립 실패 | `200`, `items: []`, warning 로그 |
| 메시지 조회 실패 | 전파 (`500`) — 근거 조회 자체가 불가능 |
| 토큰 없음 | `401` |

#### `agent_answer_completed`

근거가 있을 때만 `sources`를 싣는다 (`charts` 선례). 페이로드 형식은 §3.2와 같다.

| 경로 | `sources` |
|------|-----------|
| 정상 완료 | 포함 |
| 승인 대기 (`approval_pending`) | 포함. 게이트 이전 조회분 |
| recursion limit 강등 | 포함 |
| prompt guard 차단 | 없음. 그래프를 실행하지 않음 |
| 웹훅·백그라운드·RAGAS (`include_sources=False`) | 조회하지 않음 |

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
에이전트 답변 본문
──────────────────────────────────────
참고 문서
[① 문서 최선집행기준.pdf] [위키 배포 승인 절차] [웹 한국 금리결정 ↗] [도구 get_inquiry]
┌────────────────────────────────────┐
│ 선택한 칩의 발췌                    │  문서·도구 칩을 눌렀을 때만 표시
└────────────────────────────────────┘
```

### 5.2 User Flow

```
답변 완료 → 칩 표시 → 문서·도구 칩 클릭 → 발췌 펼침 → 같은 칩 재클릭 → 닫힘
                    → 웹 칩 클릭 → 새 탭
                    → 위키 칩 클릭 → /knowledge/{id}
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `SourceCitation` | `components/chat/` | 칩 목록, 열린 칩 상태, 발췌 패널 |
| `isSafeHttpUrl` | `utils/safeUrl.ts` | http/https 판별 |
| `SOURCE_KIND` | `types/chat.ts` | `as const` 종류 값 (컴포넌트 파일 런타임 export 금지 규칙) |

`SourceCitation`이 200줄을 넘으면 같은 폴더에 `SourceChip.tsx`로 분리한다.

### 5.4 Page UI Checklist

#### ChatPage 에이전트 답변

- [ ] 제목: `참고 문서`
- [ ] 문서 칩: 번호, 종류 텍스트 `문서`, 파일명, 점수 없음
- [ ] 위키 칩: `BookOpen` 아이콘, 종류 텍스트 `위키`, 문서 제목, 점수 없음
- [ ] 웹 칩: 종류 텍스트 `웹`, 제목, 외부 링크 아이콘, `target="_blank"` + `rel="noopener noreferrer"`
- [ ] 위험한 URL의 웹 칩: 링크 없이 텍스트만 표시
- [ ] MCP 칩: 종류 텍스트 `도구`, `mcp_tool_name`, UUID 미노출
- [ ] 문서·MCP 칩: `aria-expanded` 토글, 발췌 없으면 클릭 불가
- [ ] 발췌 패널: 일반 텍스트, `whitespace-pre-wrap`, `max-h-60 overflow-y-auto`, 동시에 1개만 열림
- [ ] 근거 없음: 칩 영역 미표시

#### ChatPage 일반 채팅 (회귀)

- [ ] 문서 칩의 파일명과 `%` 점수 유지
- [ ] 위키 칩의 `위키 근거` 문구, 점수, `/knowledge` 이동 유지
- [ ] 문서 칩 발췌 패널 동작 (신규)

---

## 6. Error Handling

### 6.1 Error Code Definition

| 상황 | 처리 | 사용자 영향 |
|------|------|------------|
| 실시간 근거 조회 실패 | `RunSourcesService`가 `exception=e`로 warning, 빈 목록 | 답변 정상, 칩 없음 |
| 세션 근거 API 실패 (프론트) | `useAgentSessionMessages`가 빈 맵으로 폴백 | 메시지 정상, 칩 없음 |
| 파일명 조회만 실패 | 서비스가 빈 맵으로 진행 | `kb_name` 폴백 라벨 |
| 카탈로그 조회만 실패 | 서비스가 빈 맵으로 진행 | MCP 칩만 제외 (fail-closed) |
| 잘못된 JSON 요약 | 원문 사용 | 발췌가 원문으로 표시 |

기준은 `degradation-vs-failure-boundary.md`를 따른다. 근거는 부가 정보이므로 답변과 메시지 조회를 막지 않는다.

### 6.2 Error Response Format

기존 `HTTPException`과 `ApiError` 경로를 그대로 쓴다. 신규 오류 코드는 없다.

---

## 7. Security Considerations

- [ ] 세션 근거 API는 `current_user.id`로만 조회하고 쿼리의 `user_id`를 받지 않는다.
- [ ] 기존 비인증 메시지 API에 근거를 싣지 않는다.
- [ ] 응답 DTO는 §3.2 필드만 내보낸다. `metadata_json`(`morph_text`, `user_id`)과 `arguments_json`은 나가지 않는다.
- [ ] 발췌는 React 텍스트 노드로 렌더링한다. 마크다운과 HTML을 해석하지 않는다.
- [ ] 웹 URL은 서버 정책과 프론트 양쪽에서 http/https만 허용한다.
- [ ] 위키 이동 id는 `encodeURIComponent`로 감싼다.
- [ ] 공유 에이전트 발췌는 에이전트를 실행한 본인에게 표시한다 (사용자 결정). 다른 구독자의 세션은 조회할 수 없다.
- [ ] MCP 발췌에 개인정보가 포함될 수 있다. `pii-masking-integration` 적용 지점에 이 표시 경로를 포함할지 해당 사이클에서 판단한다.

**이번 범위에서 고치지 않는 기존 문제**

- `conversation_history_router.py` 전체가 인증 없이 `user_id` 쿼리로 대화를 반환한다.
- `InternalDocumentSearchTool`은 `metadata.source`를 읽어 LLM에게 `[출처: unknown]`을 전달한다 (`tools.py:431`).

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| 단위 | 정책, 래퍼 해제, 이름 계산 | pytest | Do |
| 단위 | 서비스 실패 흡수, 쿼리 횟수 | pytest | Do |
| 계약 | `include_sources` 호출자 1곳, 위키 헤더 왕복 | pytest AST | Do |
| L1 API | 세션 근거 API | pytest + 실런 | Do |
| L2 UI | `SourceCitation`, 훅, ChatPage | Vitest + RTL + MSW | Do |
| L3 실런 | 4종 근거, 재진입 일치 | `TestClient` WS + 브라우저 | Do |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Method | Test Description | Expected Status | Expected Response |
|---|----------|--------|-----------------|:--------------:|-------------------|
| 1 | `.../sources` | GET | 본인 세션 | 200 | `items[].message_id`가 assistant id |
| 2 | `.../sources` | GET | 토큰 없음 | 401 | - |
| 3 | `.../sources` | GET | 타인 세션 | 200 | `items: []` |
| 4 | `.../sources` | GET | 다른 `agent_id` | 200 | 해당 런 제외 |
| 5 | `.../sources` | GET | 근거 없는 메시지 | 200 | `items`에서 제외 |
| 6 | `.../sources` | GET | 서비스 예외 | 200 | `items: []` |
| 7 | `.../sources` | GET | 응답 키 | 200 | `metadata_json`, `arguments_json`, `score` 없음 |
| 8 | `.../sources` | GET | 메시지 200건 세션 | 200 | 쿼리 횟수 고정 |

### 8.3 L2: UI Action Test Scenarios

| # | Page | Action | Expected Result | Data Verification |
|---|------|--------|----------------|-------------------|
| 1 | Citation | 4종 렌더 | §5.4 요소 표시 | 종류 텍스트, 점수 없음 |
| 2 | Citation | 문서 칩 클릭 | 패널 열림, `aria-expanded=true` | 발췌 텍스트 |
| 3 | Citation | 같은 칩 재클릭 | 패널 닫힘 | - |
| 4 | Citation | 다른 칩 클릭 | 패널 교체 | 1개만 표시 |
| 5 | Citation | `javascript:` URL | 링크 없음 | `<a>` 없음 |
| 6 | Citation | `<img onerror>` 발췌 | 문자열 그대로 | DOM에 `img` 없음 |
| 7 | Citation | 기존 테스트 4건 | 무수정 통과 | - |
| 8 | 훅 | `agent_answer_completed` 수신 | `sources` 반영 | 부재 시 `[]` |
| 9 | 훅 | 세션 메시지 + 근거 | 메시지별 병합 | id 일치 |
| 10 | 훅 | 근거 API 실패 | 메시지 정상 | `sources` 없음 |
| 11 | 훅 | `super` 세션 | 근거 API 미호출 | 호출 0회 |
| 12 | ChatPage | 에이전트 답변 완료 | 칩 표시 | `view.sources` 연결 |

### 8.4 L3: E2E Scenario Test Scenarios

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | 문서 + 웹 | KB·Tavily 에이전트 실행 → 칩 확인 → 재진입 | SC-1, 파일명 라벨 |
| 2 | 위키 | `wiki_read` 유도 실행 → 칩 클릭 | `/knowledge/{id}` 이동 |
| 3 | MCP 성공 | `get_product_rates` 실행 | 도구 칩, 발췌 표시 |
| 4 | MCP 실패 | 인자 누락 호출 | 칩 없음, 답변 정상 (SC-3) |
| 5 | 승인 필요 | `send_mail` 게이트 런 | 해당 칩 없음 |
| 6 | 서브에이전트 | 서브에이전트 내부 검색 | 칩 포함, `run_id` 일치 확인 |
| 7 | 조회 실패 주입 | 저장소 예외 강제 | 답변 정상 (SC-4) |
| 8 | 웹훅 | 웹훅 실행 | 응답 불변, 조회 0회 (SC-6) |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:------------:|---------------------|
| 일회용 KB·컬렉션 | 1 | 업로드 문서 1건 (로컬 Qdrant 실체 없음) |
| 실런 에이전트 | 1 | `[L3]` 접두, 문서·Tavily·위키·MCP 도구, 종료 후 삭제 |
| 위키 문서 | 1 | 승인 상태 |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | 근거 판정 정책, VO, 포트 | `idt/src/domain/agent_run/` |
| **Application** | 서비스, 세션 근거 UseCase, opt-in 분기 | `idt/src/application/agent_run/`, `agent_builder/` |
| **Infrastructure** | 일괄 조회, 세션 스코프 리더 | `idt/src/infrastructure/` |
| **Interfaces** | 라우터, 응답 스키마 | `idt/src/api/routes/`, `interfaces/schemas/` |

### 9.2 Dependency Rules

`RunSourcePolicy`는 표준 라이브러리와 `domain/agent_run/entities`만 의존한다. MCP 런타임 이름 계산은 `RunSourcesService`가 `MCPConnectionPolicy`로 수행해 `mcp_tools` 맵으로 넘긴다.

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `source_policy.py` | 표준 라이브러리, `domain/agent_run/entities` | application, infrastructure, LangChain |
| `run_sources.py` | domain 포트, 정책 | SQLAlchemy 모델 |
| `run_agent_use_case.py` | `RunSourcesReaderPort` | `SessionScopedRunSourcesReader` |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `RunSourcePolicy`, `RunSourceItem`, `RunEvidence` | Domain | `src/domain/agent_run/source_policy.py` |
| `RunSourcesReaderPort` | Domain | `src/domain/agent_run/interfaces.py` |
| `RunSourcesService` | Application | `src/application/agent_run/run_sources.py` |
| `GetSessionSourcesUseCase` | Application | `src/application/agent_run/use_cases/get_session_sources_use_case.py` |
| `SessionScopedRunSourcesReader` | Infrastructure | `src/infrastructure/agent_run/run_sources_reader.py` |
| `SessionSourcesResponse` | Interfaces | `src/interfaces/schemas/agent_run_response.py` |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

프로젝트 규칙을 따른다. wire 문자열은 `StrEnum` 값으로 고정한다. 값 변경은 프론트 계약 변경이다.

### 10.2 Import Order

프로젝트 규칙을 따른다.

### 10.3 Environment Variables

| Variable | Purpose | Scope | Default |
|----------|---------|-------|---------|
| `AGENT_RUN_SOURCES_MAX_ITEMS` | 답변당 근거 칩 상한 | Server | 6 |

소비 지점은 `RunSourcesService.__init__`이다. `.env.example`은 세션 정책상 수기로 추가한다.

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 호출자 opt-in | `stream(..., include_sources: bool = False)`, `inject_memory` 동형 |
| 협력자 주입 | `run_sources: RunSourcesReaderPort \| None = None` 마지막 인자. `__new__` 픽스처 1줄 보정 |
| 로깅 | `logger.warning(..., exception=e)` |
| 함수 길이 | 40줄 이하. `_attach_sources(payload, run_id, include_sources)` 헬퍼로 분리 |
| 프론트 상수 | `as const`는 `types/`에 둠 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/src/
├── domain/agent_run/
│   ├── source_policy.py                         (신규)
│   └── interfaces.py                            (포트·메서드 추가)
├── domain/doc_browse/interfaces.py              (find_filenames)
├── application/agent_run/
│   ├── run_sources.py                           (신규)
│   └── use_cases/get_session_sources_use_case.py (신규)
├── application/agent_builder/run_agent_use_case.py (opt-in)
├── infrastructure/agent_run/run_sources_reader.py (신규)
├── infrastructure/doc_browse/*metadata_repository.py (2개)
├── infrastructure/persistence/repositories/agent_run_repository.py
├── interfaces/schemas/agent_run_response.py
├── api/routes/{ws_router,agent_run_router}.py
├── api/main.py
└── config.py

idt_front/src/
├── types/{chat,websocket}.ts
├── constants/api.ts
├── utils/safeUrl.ts                             (신규)
├── services/chatService.ts
├── hooks/{useAgentRunStream,useChat}.ts
├── pages/ChatPage/index.tsx
├── components/chat/SourceCitation.tsx
└── __tests__/mocks/handlers.ts
```

### 11.2 Implementation Order

1. [ ] 정책과 래퍼 해제 (테스트 먼저)
2. [ ] 저장소 일괄 조회
3. [ ] 서비스, 리더, `RunAgentUseCase` opt-in, WS 연결
4. [ ] 실런 스모크 1회 (배선 직후 DoD)
5. [ ] 세션 근거 UseCase, 라우터, DI
6. [ ] 프론트 타입, 스트림, 뷰, 병합
7. [ ] `SourceCitation` 확장
8. [ ] L3 시나리오와 회귀 diff

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 근거 정책 | `module-1` | `source_policy.py`, 저장소 일괄 조회 4종 | 25 |
| 실시간 경로 | `module-2` | 서비스, 리더, opt-in, WS, 실런 스모크 | 25 |
| 세션 근거 API | `module-3` | UseCase, 라우터, 스키마, DI | 20 |
| 프론트 | `module-4` | 타입, 훅, 병합, `SourceCitation` | 30 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `--scope module-1,module-2` | 50 |
| Session 2 | Do | `--scope module-3,module-4` | 50 |
| Session 3 | Check + Report | 전체 | 30 |

### 11.4 FR 역추적

| FR | 설계 위치 | 검증 |
|----|----------|------|
| FR-01 | §4.2 경로 표 | L2-8, L3-1 |
| FR-02 | §2.1 서비스 공유 | L3-1 |
| FR-03 | §3.3 표 | 정책 단위 |
| FR-04 | §3.3 정렬과 상한, §10.3 | 정책 단위 |
| FR-05 | §3.3 라벨 | 정책 단위, L3-1 |
| FR-06 | §3.3, §5.4 | L2-1, L2-5 |
| FR-07 | §3.3 wiki | L3-2, 위키 헤더 계약 |
| FR-08 | §3.3 제외 규칙 | L3-3~5 |
| FR-09 | §4.2 신규 API | L1-1~8 |
| FR-10 | §4.2 처리 순서 | L1 단위 |
| FR-11 | §6.1 | L1-6, L2-10, L3-7 |
| FR-12 | §10.4, §4.2 | AST 계약, L3-8 |
| FR-13 | §3.2, §11.1 | L2-8, L2-9 |
| FR-14 | §5.4 | L2-1, L2-7 |
| FR-15 | §5.4, §7 | L2-2~6 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | Initial draft (Option C, MCP 제외 방식, 발췌는 실행 본인 표시) | 배상규 |
