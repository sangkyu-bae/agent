# wiki-guided-routing Design Document

> **Summary**: 기존 "위키 목차 → 수퍼바이저 LLM 판단 → wiki_read 워커 열람" 설계를 유지한 채, LLM이 위키를 열람할지 판단하는 **신호**를 보강한다. D1 목차 발췌(SQL 절단), D2 프레이밍 문구, D3 위키 우선 결정 규칙(조건부), D4 수집 실패 신호(state 필드 `last_worker_error`) + 되묻기 규칙, D5 도구 편집 시 `## Tool Guidelines` 섹션 한정 재생성. 신규 파일 0(테스트 제외), 메시지 규약·DB 스키마·API 계약 무변경.
>
> **Project**: sangplusbot / idt (백엔드)
> **Version**: HEAD a07ef09 기준
> **Author**: 배상규
> **Date**: 2026-09-12
> **Status**: Draft
> **Planning Doc**: [wiki-guided-routing.plan.md](./wiki-guided-routing.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 위키 목차가 제목 한 줄뿐이고 "지침도 위키에 있다"는 프레이밍이 없어, 수퍼바이저 LLM이 위키를 건너뛰고 외부 수집 도구를 추측 호출한다 (실제 런 `8ccc097f` 재현). |
| **WHO** | P2 에이전트 소유자(위키로 경로·절차를 등록하는 사람)와 그 에이전트를 쓰는 최종 사용자. |
| **RISK** | 프롬프트 규칙이 "위키 항상 먼저"로 과잉 적용되면 매 턴 wiki_read 왕복이 생겨 토큰·지연이 는다. 목록 프레이밍 금지 계약([[supervisor-graph-contracts]] §2)에 따라 "관련 항목이 있을 때만"으로 한정한다. |
| **SUCCESS** | 동일 에이전트·동일 질문 재실행 시 `ai_run_step`에 `wiki_read_worker` → 수집 워커(fsb.or.kr) 순서가 기록되고 최종 답변에 fsb.or.kr 출처 데이터가 포함된다. 기존 테스트 FAILED 목록 diff 0. |
| **SCOPE** | Phase 1: 목차 발췌 + 프레이밍 + 결정 규칙 + 실패 폴백(프롬프트 계층). Phase 2: Tool Guidelines 섹션 재생성(수정 UseCase). 표 추출 정확도·강제 라우팅·스키마 변경은 제외. |

---

## 1. Overview

### 1.1 Design Goals

- 수퍼바이저가 **목차만 보고도** 위키 문서의 관련성을 판단할 수 있게 한다 (발췌).
- 위키를 "지식 인용"뿐 아니라 "작업 절차·출처 지침"의 저장소로 프레이밍한다.
- 외부 수집 전·수집 실패 후에 위키를 확인하는 규칙을 **조건부**로 넣는다 — 위키 미등록 에이전트의 프롬프트는 바이트 동일.
- 도구 오류는 **결정적으로 감지**하고(state 필드), 그 후 판단은 LLM에 맡긴다 (책임 분리, [[supervisor-graph-contracts]] §3).
- 도구 편집 시 저장 프롬프트의 도구 목록만 정합시키고 사용자 편집분은 보존한다.

### 1.2 Design Principles

- **기존 설계 보존**: 목차 prepend → LLM 판단 → wiki_read 워커 체인, 워커 산출물 AIMessage(name) 1건 규약, 결정적 라우팅은 확실한 신호 전용.
- **additive**: `WikiTreeItem` optional 필드, `SupervisorState` 필드 1개, 조건부 블록은 빈 문자열이면 무영향.
- **메시지 본문 규약 무변경**: `is_search_result`/`is_worker_output`/재주입 마커를 공유하는 소비자(첨부·데이터 연속성·시각화)에 교차 회귀를 만들지 않는다.
- **config는 소비 지점 기준 단일 출처** ([[config-single-source-at-consumption]]).

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 기존 함수 인라인 수정, 실패 신호를 워커 AIMessage 본문 마커로 전달 | 신규 도메인 모듈(위키 라우팅 정책·섹션 교체 정책) + 훅 프로토콜 확장 | state 필드 1개 + 도메인 순수 함수 + supervisor_nodes 기존 `_render_*` 패턴 + `PromptAssemblyPolicy` 메서드 |
| **New Files** | 0 | 3 | 0 (테스트 제외) |
| **Modified Files** | 8 | 10 | 9 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium (메시지 규약 소비자 전수 재확인) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 마커가 final_answer·분석 컨텍스트에 노출 | 과추상화(두꺼운 DDD 금지와 긴장) | Low |
| **Recommendation** | 핫픽스 | 장기 | **Default choice** |

**Selected**: Option C — **Rationale**: 메시지 본문 규약을 건드리지 않아 교차 회귀가 없고, 신규 파일 없이 기존 패턴(`_render_attachment_block`, `_blocked_step_summary`, `PromptAssemblyPolicy`)만 확장한다. 사용자 선택(2026-09-12).

### 2.1 Component Diagram

```
                     ┌──────────────────────── compile (WorkflowCompiler) ────────────────────────┐
wiki_article ──SQL──▶ WikiArticleRepository.list_searchable_tree_items(excerpt_chars)  [D1]        │
                         │ WikiTreeItem(+excerpt)                                                  │
                         ▼                                                                         │
                     WikiTocProvider.render_block ─▶ render_wiki_toc_block  [D1·D2]                │
                         │ wiki_toc_block                                                           │
                         ├─▶ effective_supervisor_prompt (prepend)                                  │
                         └─▶ wiki_read 워커 system_prompt (+_WIKI_WORKER_INSTRUCTION [D2])          │
                                                                                                   │
   create_supervisor_node(..., wiki_worker_id, wiki_guidance_block [D3])                           │
        │                                                                                          │
        ▼  매 결정                                                                                  │
   decision_prompt = supervisor_prompt + 워커목록 + 첨부 + 데이터 + 시각화 + docgen                 │
                     + wiki_guidance_block [D3] + _render_worker_error_block(state) [D4] + 선택지   │
                                                                                                   │
   _wrap_worker / create_collect_node ──▶ state.last_worker_error  [D4]  (도구 오류 결정적 감지)     │
                                                                                                   │
   UpdateAgentUseCase._rebuild_tool_workers ──▶ PromptAssemblyPolicy.replace_tool_section [D5]      │
```

### 2.2 Data Flow (재현 시나리오 기대 흐름)

```
사용자: "저축은행별 금리 전체 표"
 → supervisor iter=0: 목차 "…경로참조 — 금리에 대한 정보를 원할시 https://www.fsb.or.kr/… 스크래핑…" + D3 규칙
   → wiki_read_worker 선택 (task: "금리 관련 지침 문서 열람")
 → wiki_read 워커: 본문 열람 → AIMessage(name=wiki_read_worker)
 → supervisor iter=1: 지침의 URL을 task에 명시 → scrape_url_worker / browser_open_worker
 → (실패 시) state.last_worker_error 세팅 → supervisor에 "[직전 수집 실패]" 블록
   → 위키 미열람이면 wiki_read, 이미 열람했으면 FINISH+answer(대상 URL 되묻기)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `WikiTocProvider` | `WikiArticleRepository`, `settings.wiki_toc_excerpt_chars` | 발췌 포함 목차 조회·렌더 |
| `create_supervisor_node` | `WorkerDefinition` 목록(위키 워커 id 판별), `SupervisorState.last_worker_error` | 조건부 블록 렌더 |
| `_wrap_worker`, `create_collect_node` | `ToolErrorPolicy`(domain 순수 함수) | 도구 오류 결정적 감지 |
| `UpdateAgentUseCase` | `PromptAssemblyPolicy.replace_tool_section` | 섹션 한정 재생성 |

---

## 3. Data Model

### 3.1 Entity Definition (변경분만)

```python
# src/application/wiki/schemas.py
@dataclass
class WikiTreeItem:
    id: str
    title: str
    status: str
    source_type: str
    path: str | None
    updated_at: datetime | None = None
    excerpt: str | None = None   # D1 additive — 프롬프트 목차 전용, 트리 API 미노출

# src/application/agent_builder/supervisor_state.py
class SupervisorState(TypedDict):
    ...
    # wiki-guided-routing D4: 직전 워커의 도구 오류 요약. 워커 노드가 매번 덮어쓴다
    # (성공 시 ""). supervisor는 이 값이 비어 있지 않을 때만 안내 블록을 렌더한다.
    last_worker_error: str
```

`build_initial_state`에 `"last_worker_error": ""` 추가.

### 3.2 Entity Relationships

변경 없음. `wiki_article.agent_id` 소프트 참조·승인 조건(approved + 미만료) 그대로.

### 3.3 Database Schema

**변경 없음** (마이그레이션 0). 조회만 변경:

```sql
-- list_searchable_tree_items — SELECT 절에 발췌 컬럼 추가
SELECT id, title, status, source_type, path, updated_at,
       SUBSTRING(content, 1, :excerpt_chars) AS excerpt
FROM wiki_article
WHERE agent_id = :agent_id AND status = 'approved'
  AND (valid_until IS NULL OR valid_until > :now)
ORDER BY updated_at DESC
```

SQLAlchemy: `func.substring(WikiArticleModel.content, 1, excerpt_chars).label("excerpt")`. 본문 전체 미조회 계약은 "content 컬럼 자체를 SELECT하지 않는다"로 재정의하고, `test_wiki_repository_toc`의 단언을 `"content" not in sql.split("FROM")[0].replace("SUBSTRING(", "")` 류(SUBSTRING 인자 안에서만 허용)로 갱신한다.

---

## 4. API Specification

**엔드포인트 추가·변경 없음.** `GET /api/v1/wiki/tree`는 `WikiTreeItemResponse(...)`를 명시 매핑으로 만들므로 `excerpt`는 응답에 나가지 않는다 (`wiki_router.py:132`). 프론트 타입 무변경.

---

## 5. UI/UX Design

해당 없음 (백엔드 프롬프트·UseCase 계층만).

---

## 6. 결정 상세 (D1~D5)

### D1 — 목차 발췌

**저장소** (`src/infrastructure/wiki/wiki_repository.py`)
- `list_searchable_tree_items(agent_id, now, request_id, excerpt_chars: int = 0)` — additive 기본 인자. `excerpt_chars <= 0`이면 기존 SELECT 그대로(발췌 컬럼 미조회, `excerpt=None`). 인터페이스(`src/application/repositories/wiki_repository.py`)도 같은 기본 인자로 확장(기존 페이크 무회귀).

**제공자** (`src/application/wiki/toc_provider.py`)
- 생성자에 `excerpt_chars: int = 0` 추가, `render_block`이 저장소에 전달. `main.py` 배선에서 `settings.wiki_toc_excerpt_chars` 주입.
- (Check G-02 반영) 값이 0보다 클 때만 `excerpt_chars` kwarg를 넘긴다 — 구 시그니처 구현체·페이크(`list_searchable_tree_items(agent_id, now, request_id)`)가 그대로 동작해야 한다.

**렌더** (`src/application/agent_run/prompt_rendering.py`)
```python
def _toc_line(item: WikiTreeItem) -> str:
    updated = ...
    location = ...
    excerpt = _normalize_excerpt(item.excerpt)   # 개행·연속 공백 → 단일 공백, strip
    tail = f" — {excerpt}" if excerpt else ""
    return f"- (id: {item.id}) {location} — 갱신 {updated}{tail}\n"
```
- `excerpt`가 None/빈 문자열이면 **기존 출력과 바이트 동일**.
- 발췌 절단은 SQL이 담당(글자 수). 줄 단위 `max_bytes` 예산·"(전체 N건 중 M건 표시)" 알림은 기존 로직 그대로.

**config** (`src/config.py`)
```python
# wiki-guided-routing D1: 목차 발췌 글자 수 (0 = 발췌 없음).
# 소비 지점: src/application/wiki/toc_provider.py (저장소 전달) →
#            src/application/agent_run/prompt_rendering.py:_toc_line (표시)
wiki_toc_excerpt_chars: int = 120
```
기본값 120자 근거: 이번 지침 문서(144자)의 URL까지 포함되고, 50건 × 120자여도 `wiki_toc_max_bytes`(4000) 예산 안에서 절단 알림이 동작한다.

### D2 — 프레이밍 문구

| 위치 | 변경 |
|------|------|
| `prompt_rendering.py` `_TOC_HEADER` | 2행을 "이 에이전트가 보유한 승인 지식 문서 목록입니다 (최신 갱신순). **정리된 지식뿐 아니라 작업 절차·참조할 출처 URL·처리 경로 같은 지침도 여기에 있습니다.**"로 확장. 나머지 행 유지 |
| `prompt_rendering.py` `_FOLDER_HEADER` | 같은 문장 1행 추가. `WIKI_FOLDER_HEADER_TAG` 문자열은 **불변**(compiler 모드 판별 계약) |
| `tool_registry.py` `wiki_read.description` | "최근 결정사항, 정리된 지식, 축적된 판단 기준, **그리고 어떤 출처·URL·절차로 작업할지 정한 지침** 확인에 사용하세요." |
| `tool_registry.py` `wiki_list.description` | 말미에 "작업 지침 문서를 찾을 때도 사용합니다." |
| `workflow_compiler.py` `_WIKI_WORKER_INSTRUCTION` / `_WIKI_FOLDER_WORKER_INSTRUCTION` | "열람한 본문에 근거해 답하세요" 뒤에 "**본문에 URL·절차 같은 작업 지침이 있으면 그 값을 그대로 옮겨 적으세요(요약·변형 금지).**" 추가 |

### D3 — 위키 우선 결정 규칙 (조건부)

`create_supervisor_node(..., wiki_guidance_block: str = "")` 파라미터 추가. `workflow_compiler.py` 호출부에서 `self._render_wiki_guidance_block(workflow.workers, wiki_toc_block)`로 생성:

- 주입 조건: `wiki_toc_block`이 비어 있지 않고(=목차 렌더됨) `wiki_read` 워커가 있으며 **그 외 tool 워커가 1개 이상**. 아니면 `""`.
- 블록 문안 (docgen 블록과 같은 위치·톤, 목록 프레이밍 금지):

```
[위키 지침 처리 기준]
- 시스템 프롬프트의 [에이전트 지식 위키 목차]에 이번 요청과 관련된 항목(주제·출처·절차)이 보이면,
  외부에서 자료를 수집하는 워커를 부르기 전에 먼저 {wiki_worker_id}로 그 문서를 열람하세요.
- 열람한 지침에 URL·경로·절차가 적혀 있으면, 다음 워커의 task에 그 값을 그대로 적으세요.
  지침이 있는데 다른 URL을 추측해 쓰지 마세요.
- 목차에 관련 항목이 없으면 이 기준은 적용하지 않습니다.
```

- 결정 프롬프트 조립 순서: `... {docgen_guidance_block}{wiki_guidance_block}{worker_error_block}\n\n다음 중 선택하세요:` — 기존 블록 뒤, 선택지 앞.

### D4 — 수집 실패 신호 + 되묻기 규칙

**감지 (domain 순수 함수)** — `src/domain/agent_builder/policies.py`에 `ToolErrorPolicy` 추가 (LangChain 미참조, duck typing):

```python
class ToolErrorPolicy:
    """react 워커 트레이스의 도구 오류 식별 — 결정적 신호만 담당."""
    ERROR_PREFIXES = ("Error executing tool",)   # langchain-mcp-adapters 오류 응답 형식(실측)
    MAX_SUMMARY_CHARS = 200

    @classmethod
    def summarize(cls, messages: list) -> str:
        """type=='tool'인 메시지 중 status=='error' 또는 content가 ERROR_PREFIXES로
        시작하는 것을 찾아 첫 건을 요약. 없으면 ''."""
```

**워커 노드**
- `_wrap_worker`: `_blocked_step_summary` 옆에서 `error = ToolErrorPolicy.summarize(result_messages)` → `out["last_worker_error"] = error` (성공 시 `""`).
- `create_collect_node`: `_BodyOutcome.ok is False`이면 본문(`"수집 실패: …"`) 앞 200자를, 인자 차단이면 차단 메시지를 `last_worker_error`로. 정상이면 `""`.
- search/analysis/sub_agent/document_extractor 노드: `last_worker_error`를 쓰지 않는다 → LangGraph state는 이전 값을 유지하므로, **supervisor가 블록을 렌더한 직후 `""`로 리셋**한다(반환 dict에 포함). 이렇게 하면 블록은 실패 직후 결정 1회에만 나타난다.

**렌더 (application, supervisor_nodes.py)**
```python
def _render_worker_error_block(state, wiki_worker_id: str, messages) -> str:
    err = state.get("last_worker_error", "")
    if not err:
        return ""
    wiki_read_done = any(is_worker_output(m) and m.name == wiki_worker_id for m in current_turn(messages))
    ...
```
- 재주입분(REINJECTED_MARKER)은 `current_turn` 판정에서 제외 (§3 계약).
- 문안:

```
[직전 수집 실패]
직전 워커({last_worker_id})의 도구 호출이 실패했습니다: {err}
- {wiki_worker_id가 있고 미열람일 때} 위키 목차에 관련 지침이 있는지 먼저 {wiki_worker_id}로 확인하세요.
- 지침에도 대상이 없으면 URL·식별자를 추측해 재시도하지 말고 'FINISH'를 선택하고,
  answer에 어떤 사이트(URL)를 대상으로 할지 사용자에게 묻는 문장을 쓰세요.
- 같은 인자로 같은 워커를 다시 부르지 마세요.
```
- `wiki_worker_id`가 없는 에이전트는 두 번째 줄만 생략(첫·셋째 줄은 유지) — 실패 폴백 자체는 위키 유무와 무관하게 적용.
- (Check G-06 반영) 빌트인 `wiki_read`는 문서 0건 에이전트에도 있으므로, 컴파일러는 **목차 블록이 비어 있으면 `wiki_worker_id`를 빈 문자열로** 넘긴다 — 열람할 문서가 없는데 "위키 확인" 줄이 나오지 않게.
- (Check G-04 알려진 한계) `ToolErrorPolicy`는 도구 오류 status·오류 접두어만 감지한다. HTTP 200으로 "404" 본문을 돌려주는 soft 404는 오류로 보지 않는다(런 `4829bde0` 관찰). "확실한 신호만 결정적으로" 원칙에 따른 의도된 범위이며, 그 경우의 판단은 LLM이 본문을 보고 한다.

**되묻기는 인터럽트 없이** 기존 `FINISH + answer` 경로를 쓴다. 채팅 실행 경로에 HITL 인터럽트가 없으므로 상태 추가 없음.

### D5 — Tool Guidelines 섹션 한정 재생성

**도메인 정책** (`src/domain/prompt_composer/policies.py`)
```python
class PromptAssemblyPolicy:
    @staticmethod
    def replace_tool_section(prompt: str, guides: tuple[ToolGuide, ...]) -> str:
        """`## Tool Guidelines` 헤딩 블록만 교체. 헤딩이 없으면 prompt 그대로 반환.
        블록 범위 = 헤딩 줄부터 다음 `## ` 헤딩 직전(또는 끝)까지. guides가 비면 블록 제거."""
```
- 결정적, 시간·랜덤 미사용. `_tool_block(guides)` 재사용. 앞뒤 구분은 기존 `assemble`과 같은 `"\n\n"` 규칙.

**UseCase** (`update_agent_use_case.py`) — `_rebuild_tool_workers` 마지막(`agent.flow_hint = skeleton.flow_hint` 직후):
```python
agent.system_prompt = PromptAssemblyPolicy.replace_tool_section(
    agent.system_prompt, _tool_guides_from_workers(tool_workers, catalog_entries)
)
```
- `agent.system_prompt`는 이 시점에 이미 `apply_update(system_prompt=request.system_prompt)`가 반영된 값 → "요청에 함께 오면 요청값 기준" 요구 충족.
- `ToolGuide(tool_id=카탈로그 표기, name=도구 이름, when=worker.description)`. (Check G-05 반영) 카탈로그를 재조회하지 않는다 — 내부 도구 이름은 `TOOL_REGISTRY`, MCP는 `mcp:{srv}:{tool}`의 마지막 조각(카탈로그 name과 같은 값), 설명은 워커 재구성 시 이미 카탈로그에서 실린 `description`을 쓴다(빌트인 워커 포함). `how`/`caution`은 비움 → `_guide_lines`가 구분자째 생략.
- 기존 폴백 프롬프트의 `## Tool Guidelines` 형식(`- name (tool_id): description`)과 동일 출력.
- 순수 함수이므로 `UpdateAgentUseCase`에 새 의존성 주입 없음.

---

## 7. Error Handling

| 상황 | 처리 |
|------|------|
| 발췌 조회 실패(SQL 오류 등) | `WikiTocProvider.render_block`의 기존 best-effort try/except → `""` (warning, `exception=e`) — 대화 차단 없음 |
| `last_worker_error` 키 부재(구 state) | `state.get("last_worker_error", "")` |
| 트레이스에 ToolMessage 형태가 예상과 다름 | `ToolErrorPolicy.summarize`는 속성 부재 시 건너뜀, 예외 없음 |
| Tool Guidelines 헤딩 없음 | 무변경 반환 (사용자가 지운 섹션 존중) |
| 헤딩이 2개 이상 | 첫 번째만 교체, 나머지 보존 (테스트로 고정) |

Error code·응답 형식 변경 없음.

---

## 8. Security Considerations

- [x] 발췌는 approved 문서만(기존 WHERE 유지). 승인 전 CONVERSATION/draft 문서 미노출.
- [x] 발췌 본문은 프롬프트 데이터. LLM 지시 주입 표면은 기존 wiki_read 열람과 동일 범위(신규 표면 없음).
- [x] `last_worker_error`는 도구 오류 문자열 200자 절단 — 스택 트레이스·내부 경로 미포함(오류 메시지 첫 줄만).
- [x] 인가·권한 로직 무변경.

---

## 9. Test Plan

> 백엔드 전용 기능이라 L2/L3(Playwright)는 해당 없음. L1은 API 변경이 없어 계약 유지 테스트만. 핵심은 단위·통합(pytest)과 재현 시나리오(FR-07).

### 9.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit | 저장소 쿼리, 렌더 함수, 정책 순수 함수, 섹션 교체 | pytest | Do |
| Integration | compile → 결정 프롬프트 조립, 워커 래퍼 → state | pytest (fake LLM/tool) | Do |
| L1 계약 | `GET /wiki/tree` 응답 필드 불변 | pytest TestClient | Do |
| Runtime 재현 | 대상 에이전트 실행 → `ai_run_step` 순서 | 수동 + DB 조회 | Check |

### 9.2 Unit / Integration Scenarios (TDD 순서)

| # | 파일 | 테스트 | 기대 |
|---|------|--------|------|
| 1 | `tests/infrastructure/wiki/test_wiki_repository_toc.py` | `excerpt_chars=120`이면 SQL에 `SUBSTRING`·`excerpt` 포함, bare `content` 컬럼은 SELECT에 없음; `excerpt_chars=0`이면 기존 SQL과 동일; 행→`WikiTreeItem.excerpt` 매핑 | D1 |
| 2 | `tests/application/agent_run/test_prompt_rendering.py` | 발췌 있는 항목은 `— {excerpt}` 꼬리, 개행이 공백으로 정규화; 발췌 None이면 기존 출력과 바이트 동일; 헤더에 지침 문구 포함; `WIKI_FOLDER_HEADER_TAG` 불변 | D1·D2 |
| 3 | `tests/application/wiki/test_toc_provider.py` | provider가 `excerpt_chars`를 저장소에 전달 | D1 |
| 4 | `tests/domain/agent_builder/test_tool_error_policy.py` (신규) | status=='error' 감지, `Error executing tool` 접두 감지, 정상 ToolMessage/AIMessage는 `''`, 200자 절단, 속성 없는 객체 무시 | D4 |
| 5 | `tests/application/agent_builder/test_workflow_compiler_wiki_toc.py` | 위키 워커+타 워커 → 결정 프롬프트에 `[위키 지침 처리 기준]` 포함; 위키 워커만 있으면 미포함; 목차 빈 문자열이면 미포함(기존 `test_empty_toc_block_no_injection` 확장) | D3 |
| 6 | `tests/application/agent_builder/test_supervisor_worker_error.py` (신규) | `last_worker_error` 비면 블록 없음; 있으면 `[직전 수집 실패]` + 오류 문자열; 위키 워커 미열람이면 wiki 안내 줄, 열람 후면 생략; 재주입분은 열람으로 안 침; supervisor 반환 dict가 `last_worker_error`를 `""`로 리셋 | D4 |
| 7 | `tests/application/agent_builder/test_worker_trace_leak.py` 확장 | react 트레이스에 오류 ToolMessage → `out["last_worker_error"]` 세팅, state 메시지에는 여전히 AIMessage 1건만 | D4 |
| 8 | `tests/application/agent_builder/test_collect_pipeline*.py` 확장 | 도구 실패/차단 → `last_worker_error` 세팅, 정상 → `""` | D4 |
| 9 | `tests/domain/prompt_composer/test_policies.py` 확장 | 헤딩 있음 → 해당 블록만 교체, 다른 섹션 바이트 동일; 헤딩 없음 → 입력 그대로; 헤딩 2개 → 첫 번째만; guides 빈 튜플 → 블록 제거; 결정성 | D5 |
| 10 | `tests/application/agent_builder/test_update_agent_tool_editing.py` 확장 | `tool_ids` 변경 후 `system_prompt`의 Tool Guidelines에 신규 도구 포함·제거 도구 부재; 사용자 편집 `## Important Notes` 보존; 헤딩 없는 프롬프트는 무변경; `system_prompt`+`tool_ids` 동시 요청 시 요청 프롬프트 기준 | D5 |
| 11 | `tests/api/test_wiki_router.py` | tree 응답 키 집합 불변(`excerpt` 미포함) | 계약 |
| 12 | `tests/api/test_tool_catalog_router.py`, `test_worker_skeleton_builder.py` | wiki 도구 설명 문자열 단언이 있으면 갱신 | D2 |

### 9.3 Runtime 재현 (Check 단계, FR-07)

| # | 절차 | 성공 기준 |
|---|------|-----------|
| 1 | 에이전트 `f41c622e…`로 "현재 기준 각 저축은행별 금리 전체 표" 질문 | `ai_run_step`: `supervisor → wiki_read_worker → supervisor → (scrape_url 또는 browser_open)_worker …` |
| 2 | 같은 런의 `ai_tool_call.arguments_json` | 수집 도구 URL이 `www.fsb.or.kr/ratedepo_0100.act` |
| 3 | 위키가 없는 에이전트로 존재하지 않는 도메인 질문 | 최종 답변이 URL을 지어내지 않고 대상 URL을 되묻는다 |
| 4 | 위키 미등록 에이전트 임의 질문 | 결정 프롬프트 토큰이 변경 전과 동일(±0) — `ai_llm_call.total_tokens` 비교 |

### 9.4 Seed Data

로컬 DB의 기존 에이전트·위키 문서를 그대로 사용. 단위 테스트는 fake 저장소·fake LLM.

### 9.5 회귀 증명

`pytest -q` 전후 **정렬된 FAILED 목록 diff** 로 증명 ([[false-green-quality-gates]]). 기존 baseline 실패는 그대로 두고 신규 실패 0.

---

## 10. Clean Architecture

### 10.1 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `ToolErrorPolicy` (순수 함수) | Domain | `src/domain/agent_builder/policies.py` |
| `PromptAssemblyPolicy.replace_tool_section` | Domain | `src/domain/prompt_composer/policies.py` |
| `wiki_read`/`wiki_list` 설명 | Domain | `src/domain/agent_builder/tool_registry.py` |
| `WikiTreeItem.excerpt` | Application (DTO) | `src/application/wiki/schemas.py` |
| `WikiTocProvider` excerpt 전달 | Application | `src/application/wiki/toc_provider.py` |
| `render_wiki_toc_block`, 헤더 | Application | `src/application/agent_run/prompt_rendering.py` |
| `_render_wiki_guidance_block`, `_wrap_worker` 오류 요약, 지시문 | Application | `src/application/agent_builder/workflow_compiler.py` |
| `_render_worker_error_block`, 결정 프롬프트 조립 | Application | `src/application/agent_builder/supervisor_nodes.py` |
| `SupervisorState.last_worker_error` | Application | `src/application/agent_builder/supervisor_state.py` |
| collect 노드 `last_worker_error` | Application | `src/application/agent_builder/collect_pipeline.py` |
| 섹션 재생성 호출 | Application | `src/application/agent_builder/update_agent_use_case.py` |
| SUBSTRING 조회 | Infrastructure | `src/infrastructure/wiki/wiki_repository.py` |
| 인터페이스 기본 인자 | Application (port) | `src/application/repositories/wiki_repository.py` |
| config 키 + 배선 | Config / Interfaces | `src/config.py`, `src/api/main.py` |

### 10.2 Dependency Rules 준수

- `ToolErrorPolicy`는 LangChain 타입을 import하지 않고 `type`/`status`/`content` 속성만 읽는다 (domain → 외부 라이브러리 금지).
- `PromptAssemblyPolicy`는 문자열·dataclass만 다룬다.
- UseCase는 세션을 직접 만들지 않으며(기존 저장소 경유), Repository는 commit하지 않는다.

---

## 11. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 함수 길이 | 40줄 이내 — `_render_worker_error_block`은 판정(`_wiki_read_done`)과 문안 조립을 분리 |
| 로깅 | 발췌 조회 실패는 기존 provider warning(`exception=e`) 경유. print 금지 |
| config | 키 docstring에 소비 지점 파일 명기 |
| 코드 주석 | `# Design Ref: wiki-guided-routing D{n}` / `# Plan SC: FR-0{n}` 표기 |
| 테스트 | Red → Green, 회귀는 FAILED diff |

---

## 12. Implementation Guide

### 12.1 File Structure (변경 파일)

```
src/
├── config.py                                   (D1 config)
├── api/main.py                                 (D1 배선)
├── domain/agent_builder/policies.py            (D4 ToolErrorPolicy)
├── domain/agent_builder/tool_registry.py       (D2)
├── domain/prompt_composer/policies.py          (D5 replace_tool_section)
├── application/repositories/wiki_repository.py (D1 port 기본 인자)
├── application/wiki/schemas.py                 (D1 excerpt)
├── application/wiki/toc_provider.py            (D1)
├── application/agent_run/prompt_rendering.py   (D1·D2)
├── application/agent_builder/supervisor_state.py  (D4)
├── application/agent_builder/supervisor_nodes.py  (D3·D4)
├── application/agent_builder/workflow_compiler.py (D2·D3·D4)
├── application/agent_builder/collect_pipeline.py  (D4)
├── application/agent_builder/update_agent_use_case.py (D5)
└── infrastructure/wiki/wiki_repository.py      (D1)
tests/ … §9.2 목록 (신규 2, 확장 10)
```

### 12.2 Implementation Order

1. [ ] **module-1 (D1·D2)**: 저장소 쿼리 테스트 갱신 → SUBSTRING 구현 → `WikiTreeItem.excerpt` → provider 전달 → `_toc_line`/헤더/도구 설명/지시문 → config·배선
2. [ ] **module-2 (D3·D4)**: `ToolErrorPolicy` 테스트 → 구현 → `SupervisorState` 필드 + `build_initial_state` → `_wrap_worker`/collect 노드 세팅 → `_render_wiki_guidance_block`·`_render_worker_error_block` → `create_supervisor_node` 조립·리셋
3. [ ] **module-3 (D5)**: `replace_tool_section` 테스트 → 구현 → `_rebuild_tool_workers` 호출 + 가이드 변환 → UseCase 테스트
4. [ ] 전체 `pytest -q` FAILED diff → 재현 시나리오(§9.3) → `/pdca analyze wiki-guided-routing`

### 12.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 목차 발췌·프레이밍 | `module-1` | D1 저장소/DTO/렌더/config, D2 문구 | 15-20 |
| 결정 규칙·실패 신호 | `module-2` | D3 조건부 블록, D4 정책·state·워커 노드·supervisor | 25-30 |
| Tool Guidelines 재생성 | `module-3` | D5 정책 메서드 + UseCase 호출 | 12-15 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-3` | 30-35 |
| Session 3 | Do | `--scope module-2` | 25-30 |
| Session 4 | Check + 재현 + Report | 전체 | 20-30 |

---

## 13. Risk 재확인 (Plan §5 대비)

| Plan 리스크 | 설계 대응 |
|-------------|-----------|
| 위키 규칙 과잉 적용 | D3 블록은 "관련 항목이 보이면"·"없으면 적용 안 함"을 명시, 위키 워커만 있는 에이전트에는 미주입 |
| 발췌로 목차 절단 증가 | 기본 120자 + 기존 4000바이트 예산·알림 유지, 테스트 #2 |
| 실패 판정 오탐/미탐 | `ToolErrorPolicy` 순수 함수 + 케이스 테스트 #4, 블록은 결정 1회만 노출(리셋) |
| 사용자 편집 프롬프트 덮어씀 | D5 헤딩 있을 때만 그 블록만 교체, 테스트 #9·#10 |
| 쿼리 문자열 고정 테스트 | 의도된 Red → 단언 재정의(테스트 #1) |
| 결정 프롬프트 변경의 교차 영향 | 블록 순서 유지·조건부 빈 문자열, 위키 미등록 에이전트 토큰 ±0 (§9.3 #4) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-12 | 초안 — Option C 선택, D1~D5 확정, 테스트 계획 12건 | 배상규 |
