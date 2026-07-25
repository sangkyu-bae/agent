# Wiki Agentic Navigation Design Document

> **Summary**: 위키 목차 프롬프트 주입 + `wiki_read` 명시 열람 도구의 상세 설계 — Plan에서 미확정이던 주입 지점(컴파일 시 prepend, async 확인됨)·목차 포맷·출처 표기(`wiki:{title}`)를 코드 추적 근거로 확정
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-23
> **Status**: Draft
> **Plan Doc**: `docs/01-plan/features/wiki-agentic-navigation.plan.md`

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | Plan에서 3가지 결정이 미확정이었음: ① 목차 주입 지점(compile prepend vs 그래프 노드) ② 목차 포맷·상한 ③ 벡터 경로 출처 표기. 또한 wiki_read 열람 기록(FR-05)·카탈로그 노출(FR-01)의 배선 실체가 미검증이었음 |
| **Solution** | 코드 추적으로 전부 확정: ① `WorkflowCompiler.compile()`이 **async**이므로 컴파일 시 목차 조회 + supervisor 프롬프트 prepend + wiki_read 워커(react agent)의 `prompt` 파라미터 이중 주입 ② 목차는 id 병기·갱신일 내림차순·건수/바이트 상한(settings 신설 2종) ③ 출처는 `wiki:{title}` ④ 열람 기록은 기존 `UsageCallback.on_tool_start`가 모든 BaseTool을 자동 영속화하므로 **신규 배선 0** ⑤ 카탈로그는 `TOOL_REGISTRY` 등록만으로 `internal:wiki_read` 자동 동기화(패턴 `^internal:[a-z_]+$` 통과) — 프론트 변경 0 |
| **Function UX Effect** | 에이전트가 대화 시작부터 자기 위키 전체상(문서 id·경로·갱신일)을 인지하고, supervisor는 위키 워커로 라우팅, 워커는 목차에서 id를 골라 `wiki_read`로 본문 드릴다운. 운영자는 run 상세 tool_call의 `article_id` 인자로 열람 문서를 결정적으로 확인 |
| **Core Value** | 신규 파일 3개 + 기존 파일 수정 5개, 마이그레이션 0, 신규 배선 최소(관측성·카탈로그는 기존 인프라 무임승차) — 위키를 검색 경쟁자에서 탐색 가능한 상위 지식 계층으로 격상 |

---

## 1. Design Overview

### 1.1 전체 구조 (런타임 시퀀스)

```
[대화 요청]
RunAgentUseCase
  ├─ set_current_run_context(RunContext(agent_id, ...))          # 기존
  └─ _prepare_graph → WorkflowCompiler.compile(..., agent_id=A)  # ★ agent_id kwarg 추가
        │
        ├─ ★ wiki_read 워커 존재 + provider 주입 + agent_id 있음?
        │     └─ toc_block = await WikiTocProvider.render_block(A)
        │          ├─ repo.list_searchable_tree_items(A, now)     # ★ 승인+미만료 경량 조회
        │          └─ render_wiki_toc_block(items, limits)        # ★ 순수 렌더 함수
        │
        ├─ supervisor_prompt = user_context_block + toc_block + 원본   # 기존 prepend 선례 확장
        │
        └─ wiki_read 워커: create_react_agent(llm, tools=[WikiReadTool],
                                              prompt=toc_block + 사용지시)  # ★ 워커에도 주입
[답변 생성 중]
supervisor ─(목차 인지, 라우팅)→ wiki_read 워커(react agent)
  └─ LLM이 목차에서 id 선택 → WikiReadTool._arun(article_id)
        ├─ UsageCallback.on_tool_start → record_tool_call(ai_tool_call)   # 기존 자동 — 배선 0
        └─ session_factory() → WikiArticleReadUseCase.execute(id, A, now)
              ├─ repo.find_by_id(id)                              # 기존 메서드
              └─ 소유(agent_id)·APPROVED·미만료 가드 → 본문 or None
```

### 1.2 컴포넌트 배치 (레이어)

| 컴포넌트 | 레이어 | 파일 | 신규/수정 |
|----------|--------|------|:---------:|
| `wiki_read` ToolMeta | domain | `src/domain/agent_builder/tool_registry.py` | 수정 |
| `WikiArticleReadUseCase` | application | `src/application/wiki/read_article_use_case.py` | **신규** |
| `WikiTocProvider` | application | `src/application/wiki/toc_provider.py` | **신규** |
| `render_wiki_toc_block` | application | `src/application/agent_run/prompt_rendering.py` | 수정 |
| `WikiReadTool` (BaseTool) | infrastructure | `src/infrastructure/wiki/wiki_read_tool.py` | **신규** |
| `list_searchable_tree_items` | infrastructure | `src/infrastructure/wiki/wiki_repository.py` | 수정 |
| ToolFactory `wiki_read` 분기 | infrastructure | `src/infrastructure/agent_builder/tool_factory.py` | 수정 |
| compile 목차 주입 | application | `src/application/agent_builder/workflow_compiler.py` | 수정 |
| compile 호출부 agent_id 전달 | application | `src/application/agent_builder/run_agent_use_case.py` | 수정 |
| 출처 표기 (S4) | application | `src/application/wiki/wiki_first_search_use_case.py` | 수정 |
| DI 배선 | api | `src/api/main.py` | 수정 |
| 상한 설정 | config | `src/config.py` | 수정 |

LangChain(BaseTool)은 infrastructure에 격리(tavily 선례), 가드 규칙은 application UseCase,
렌더링은 `prompt_rendering.py`의 순수 함수(테스트 용이) — 기존 레이어 관례 준수.

---

## 2. 확정 결정 (Plan §6.2 미확정분 해소)

| # | 결정 | 선택 | 근거 (코드 추적) |
|---|------|------|------|
| D1 | 목차 주입 지점 | **compile 시 prepend + wiki_read 워커 prompt 이중 주입** | `compile()`은 `async def` (`workflow_compiler.py:134`) — DB 조회 await 가능. supervisor prepend 선례(`:170-177`)와 동일 패턴. 단 supervisor만 주입하면 워커 react agent(`:256-258`, prompt 미지정)가 목차를 못 봐 id 선택 불가 → 워커 생성 시 `prompt=` 파라미터로 동일 블록+사용지시 주입 |
| D2 | agent_id 전달 | compile에 `agent_id: str \| None = None` kwarg 추가 (additive) | compile 시그니처에 agent_id 부재. RunContext는 compile 전에 설정되나(`run_agent_use_case.py:518`) 암묵 의존보다 명시 파라미터가 테스트 용이. 기본 None → 미전달 호출부(compile 재귀·sub_agent 포함) 전부 목차 비활성으로 무회귀 |
| D3 | 출처 표기 | **`wiki:{title}`** | `_format_results`가 `hit.metadata["source"]`를 그대로 렌더(`tools.py:431,440`) — metadata에 `"source": f"wiki:{title}"` 추가만으로 해결. title 포함이 후속 인용 강제(attribution)에서 사람이 읽을 수 있는 인용 단위가 됨. 기존 키 부재 상태라 추가는 순수 additive |
| D4 | 열람 기록 배선 | **신규 배선 0 — 기존 자동 기록 검증만** | `UsageCallback.on_tool_start`가 **모든 BaseTool** 호출을 `record_tool_call`로 영속화(`usage_callback.py:249-296`, arguments JSON 포함). wiki_read도 BaseTool이므로 자동 적용. FR-05는 구현이 아니라 통합 테스트로 고정 |
| D5 | 카탈로그 노출 | **TOOL_REGISTRY 등록만 — 프론트 변경 0** | `agent_builder_router.py:109-133` + `sync_internal_tools_use_case.py`가 `get_all_tools()`에서 `internal:{id}` 자동 생성. `wiki_read`는 정책 패턴 `^internal:[a-z_]+$`(`tool_catalog/policies.py:6`) 통과 |
| D6 | 워커 노드 형태 | ToolMeta **category 미지정** → react agent 경로 | category="search"면 search 파이프라인 노드로, "analysis"면 분석 노드로 분기(`workflow_compiler.py:225,244`). wiki_read는 기본 분기(`:256`) react agent가 맞음 — LLM이 목차 보고 여러 문서를 연속 열람 가능 |
| D7 | 목차 조회 | 신규 repo 메서드 `list_searchable_tree_items(agent_id, now)` | `list_tree_items`는 전체 status + path 정렬(관리화면용, `wiki_repository.py:165-192`) — 시그니처 불변 유지. 신규 메서드는 SQL WHERE로 승인+미만료 필터, `updated_at DESC` 정렬("최근 결정" 대응), 본문 미조회 경량 유지 |
| D8 | 상한 config | `wiki_toc_max_items: int = 50`, `wiki_toc_max_bytes: int = 4000` | `config.py` LLM Wiki 섹션(`:15-16`)에 추가 — 하드코딩 금지 규칙 준수. 초과 시 최신순 절단 + 생략 표시 |

---

## 3. 상세 설계

### 3.1 D-A. `wiki_read` 도구

#### tool_registry 등록 (domain)

```python
"wiki_read": ToolMeta(
    tool_id="wiki_read",
    name="에이전트 위키 열람",
    description=(
        "이 에이전트가 보유한 승인 지식 위키 문서의 본문을 열람합니다. "
        "시스템 프롬프트의 [에이전트 지식 위키 목차]에서 문서 id를 골라 전달하세요. "
        "최근 결정사항, 정리된 지식, 축적된 판단 기준 확인에 사용하세요."
    ),
    requires_env=[],
    # category 미지정 (D6) — react agent 워커 경로
),
```

#### `WikiArticleReadUseCase` (application/wiki/read_article_use_case.py — 신규)

```python
class WikiArticleReadUseCase:
    """agent 소유 + 승인 + 미만료 위키 단건 열람. 실패 사유는 구분하지 않는다(FR-02)."""

    def __init__(self, wiki_repo: WikiArticleRepository) -> None: ...

    async def execute(
        self, article_id: str, agent_id: str, now: datetime, request_id: str
    ) -> WikiArticle | None:
        article = await self._wiki_repo.find_by_id(article_id, request_id)  # 기존 메서드
        if article is None:
            return None
        if article.agent_id != agent_id:        # 수평 권한 상승 차단
            return None
        if not article.is_searchable(now):      # APPROVED + 미만료 (entity:104-106 재사용)
            return None
        return article
```

- 미존재/타 에이전트/미승인/만료 전부 `None` 단일 수렴 — 도구가 동일 실패 텍스트로 렌더링해
  사유가 LLM에 누설되지 않음 (id 존재 여부 오라클 차단)

#### `WikiReadTool` (infrastructure/wiki/wiki_read_tool.py — 신규)

```python
class WikiReadArgs(BaseModel):
    article_id: str = Field(description="열람할 위키 문서 id (목차의 id 값)")

class WikiReadTool(BaseTool):
    name: str = "wiki_read"
    description: str = TOOL_REGISTRY 설명과 동일 취지
    args_schema: type[BaseModel] = WikiReadArgs

    # DI: session_factory, repo_builder((session)->WikiArticleRepository), logger
    # RunScopedWikiSearch 패턴 (run_scoped_wiki_search.py:21-31) — 싱글톤 안전 per-call 세션

    async def _arun(self, article_id: str, ...) -> str:
        ctx = get_current_run_context()
        agent_id = getattr(ctx, "agent_id", None) if ctx is not None else None
        if not agent_id:
            return _FAIL_TEXT                     # graph 외부 호출 방어
        async with self._session_factory() as session:
            use_case = WikiArticleReadUseCase(self._repo_builder(session))
            article = await use_case.execute(
                article_id, agent_id, datetime.now(timezone.utc), self.request_id
            )
        if article is None:
            return _FAIL_TEXT
        return _render_article(article)
```

- 반환 포맷:

```
[위키 문서: {title}]
경로: {path or "-"} | 갱신: {updated_at:%Y-%m-%d} | 출처유형: {source_type}

{content}
```

- 실패 텍스트(`_FAIL_TEXT`, 상수):
  `"요청한 위키 문서를 찾을 수 없거나 열람할 수 없습니다. 시스템 프롬프트의 위키 목차에 있는 id인지 확인하세요."`
- `_run`(sync)은 `NotImplementedError` (async 전용 — 기존 도구 관례 확인 후 동일하게)
- 열람 기록: 별도 코드 없음 — `UsageCallback.on_tool_start`가 `ai_tool_call`에
  `arguments_json={"article_id": ...}`로 자동 기록 (D4)

#### ToolFactory 분기 (수정)

```python
case "wiki_read":
    from src.infrastructure.wiki.wiki_read_tool import WikiReadTool
    return WikiReadTool(
        session_factory=self._wiki_session_factory,   # ★ ctor 신규 optional 주입
        repo_builder=self._wiki_repo_builder,          # ★ ctor 신규 optional 주입
        request_id=request_id,
        logger=self._logger,
    )
```

- ToolFactory ctor에 `wiki_session_factory=None`, `wiki_repo_builder=None` optional 추가.
  미주입 상태에서 `wiki_read` 생성 요청 시 명확한 ValueError(설정 오류 조기 표면화).
- `main.py`의 기존 `_wiki_repo_builder`(≈2376행)·`get_session_factory()` 재사용 — 신규 인프라 0.

### 3.2 D-B. 위키 목차 블록

#### `list_searchable_tree_items` (wiki_repository.py — 신규 메서드)

```python
async def list_searchable_tree_items(
    self, agent_id: str, now: datetime, request_id: str
) -> list[WikiTreeItem]:
    """프롬프트 목차용: 승인+미만료만, 갱신 내림차순, 본문 미조회.

    주의: WHERE 절은 entity.is_searchable(now)의 SQL 미러 —
    의미 변경 시 양쪽 동기 수정 (테스트 test_searchable_filter_mirrors_entity로 고정).
    """
    # WHERE agent_id = :a AND status = 'approved'
    #   AND (valid_until IS NULL OR valid_until > :now)
    # ORDER BY updated_at DESC
```

- 기존 `list_tree_items`(전체 status·path 정렬·관리화면용) 시그니처/동작 불변 (Plan 리스크 대응)
- 반환 `WikiTreeItem`은 id·title·path·updated_at 포함 (기존 스키마 재사용, 변경 0)

#### `render_wiki_toc_block` (prompt_rendering.py — 신규 순수 함수)

```python
def render_wiki_toc_block(
    items: list[WikiTreeItem], max_items: int, max_bytes: int
) -> str:
    """승인 위키 목차 블록. items가 비면 '' (FR-04 — 빈 블록 노이즈 금지)."""
```

- 출력 형식 (user_context_block 관례 준수 — 말미 `\n---\n\n` 구분자):

```
[에이전트 지식 위키 목차]
이 에이전트가 보유한 승인 지식 문서 목록입니다 (최신 갱신순).
문서의 상세 내용이 필요하면 wiki_read 도구에 아래 id를 전달해 본문을 열람하세요.
목차만으로 답하지 말고, 인용이 필요하면 반드시 본문을 열람한 뒤 답하세요.

- (id: {id}) {path + "/" if path else ""}{title} — 갱신 {updated_at:%Y-%m-%d}
- ...

(전체 {total}건 중 {shown}건 표시 — 이후 생략)   # 절단 발생 시에만
---

```

- 절단 규칙: `max_items` 초과분 제거 → 직렬화 결과가 `max_bytes` 초과면 뒤에서부터
  줄 단위 제거 — 두 상한 모두 적용 후 생략 표시 1줄
- 사용 지시(2~3행)를 블록 안에 포함 — "LLM이 wiki_read를 호출하지 않음" 리스크(Plan §5)의 1차 방어

#### `WikiTocProvider` (application/wiki/toc_provider.py — 신규)

```python
class WikiTocProvider:
    """compile 시점 목차 블록 생성. RunScopedWikiSearch와 동일한 per-call 세션 패턴."""

    def __init__(self, session_factory, repo_builder, max_items, max_bytes, logger): ...

    async def render_block(self, agent_id: str, request_id: str) -> str:
        try:
            async with self._session_factory() as session:
                items = await self._repo_builder(session).list_searchable_tree_items(
                    agent_id, datetime.now(timezone.utc), request_id
                )
            return render_wiki_toc_block(items, self._max_items, self._max_bytes)
        except Exception as e:
            self._logger.warning("WikiTocProvider render failed (best-effort)",
                                 exception=e, agent_id=agent_id)
            return ""   # 목차 실패가 대화를 차단하지 않음 — best-effort
```

#### WorkflowCompiler 주입 (수정)

```python
# ctor: wiki_toc_provider=None (optional — 미주입 시 완전 비활성, 무회귀)
# compile(): agent_id: str | None = None kwarg 추가 (D2)

has_wiki_read = any(w.tool_id == "wiki_read" for w in workflow.workers)
wiki_toc_block = ""
if has_wiki_read and self._wiki_toc_provider is not None and agent_id:
    wiki_toc_block = await self._wiki_toc_provider.render_block(agent_id, request_id)

effective_supervisor_prompt = user_context_block + wiki_toc_block + workflow.supervisor_prompt
```

- 워커 생성 분기(`:256` 인근):

```python
if worker_def.tool_id == "wiki_read" and wiki_toc_block:
    worker_agent = create_react_agent(
        llm, tools=[tool], name=worker_def.worker_id,
        prompt=wiki_toc_block + _WIKI_WORKER_INSTRUCTION,
    )
else:
    worker_agent = create_react_agent(llm, tools=[tool], name=worker_def.worker_id)
```

- `_WIKI_WORKER_INSTRUCTION`: "목차에서 질문과 관련된 문서 id를 골라 wiki_read로 열람하고,
  열람한 본문에 근거해 답하세요. 관련 문서가 없으면 '위키에서 확인되지 않습니다'라고 답하세요."
- sub_agent 재귀 컴파일(`_compile_sub_agent`)에는 agent_id 미전달 → 중첩 에이전트 목차 비활성
  (자기 위키는 자기 레벨에서만 — 의도된 격리)

#### run_agent_use_case / main.py 배선 (수정)

- `_prepare_graph` → `compile(..., agent_id=agent.id)` 전달 (1줄)
- `main.py`: `WikiTocProvider(get_session_factory(), _wiki_repo_builder, settings.wiki_toc_max_items, settings.wiki_toc_max_bytes, app_logger)` 생성 → `WorkflowCompiler(wiki_toc_provider=...)` 주입

### 3.3 D-C. 벡터 경로 출처 표기 (S4)

`wiki_first_search_use_case.py` `_to_result` metadata에 1키 추가:

```python
metadata={
    "source": f"wiki:{article.title}",   # ★ D3 — _format_results [출처: ...] 렌더용
    "title": article.title,
    ...기존 그대로,
}
```

- `_format_results`(`tools.py:431`)와 `DocumentSource.source`가 자동으로 이 값을 사용 —
  다른 코드 무변경. `[출처: unknown]` → `[출처: wiki:{title}]`
- `fusion_source`는 `hit.source`(top-level 필드) 기반이므로 관측성 값 `'wiki'` 불변 (회귀 없음)

---

## 4. FR 매핑 & 테스트 설계 (TDD 순서)

| FR | 검증 | 테스트 파일 (신규/추가) |
|----|------|------|
| FR-01 | `get_tool_meta("wiki_read")` 조회 성공 + 카탈로그 동기화 use case가 `internal:wiki_read` 생성 + 정책 패턴 통과 | `tests/domain/agent_builder/test_tool_registry.py`(추가), 기존 sync 테스트 패턴 |
| FR-02 | UseCase 4분기(미존재/타 agent/DRAFT/만료) 전부 None, 정상 케이스 반환. Tool 레벨: None→실패 텍스트 동일성, ctx 없음→실패 텍스트 | `tests/application/wiki/test_read_article_use_case.py`(신규), `tests/infrastructure/wiki/test_wiki_read_tool.py`(신규) |
| FR-03 | `render_wiki_toc_block`: id·title·path·날짜 포함, 상한 2종 절단+생략 표시, 사용 지시 포함. compile: wiki_read 워커 有+provider 有+agent_id 有 → supervisor 프롬프트에 블록 포함 | `tests/application/agent_run/test_prompt_rendering.py`(추가), `tests/application/agent_builder/test_workflow_compiler_wiki_toc.py`(신규) |
| FR-04 | items 빈 리스트 → `''`. wiki_read 미선택 / provider 미주입 / agent_id None → supervisor 프롬프트 바이트 불변 | 위 두 파일에 케이스 추가 |
| FR-05 | WikiReadTool이 BaseTool이고 `_arun` 실행됨을 단언(on_tool_start 자동 기록의 전제) — usage_callback 기존 테스트가 범용 커버, 추가로 arguments에 article_id 포함 통합 단언 1건 | `test_wiki_read_tool.py` |
| FR-06 | 기존 `test_search_pipeline` / `test_supervisor_*` / wiki 기존 테스트 무회귀 (격리 실행) | 기존 스위트 |
| FR-07 | `_to_result` metadata["source"] == `wiki:{title}`, 기존 키 보존 | `tests/application/wiki/test_wiki_first_search.py`(추가) |
| FR-08 | E2E 수동 — run tool_call 실측 (아래 §6) | 수동 체크리스트 |
| D7 미러 | `list_searchable_tree_items` 필터가 entity `is_searchable`와 동치(승인+미만료 4분기) + updated_at DESC 정렬 + `list_tree_items` 무회귀 | `tests/infrastructure/wiki/test_wiki_repository_toc.py`(신규 — 기존 repo 테스트 패턴 따름) |

구현 순서 (Red → Green 단위):

```
1. FR-02  UseCase 테스트 → read_article_use_case.py
2. FR-02/05  Tool 테스트 → wiki_read_tool.py → registry 등록(FR-01) → ToolFactory 분기
3. D7  repo 테스트 → list_searchable_tree_items
4. FR-03/04  렌더 테스트 → render_wiki_toc_block → provider → compile 주입 + agent_id 배선
5. FR-07  출처 테스트 → _to_result 수정
6. config 상한 2종 + main.py DI → 전체 격리 pytest + verify-architecture/logging/tdd
7. FR-08  E2E 수동
```

---

## 5. 설정 (config.py 추가)

```python
# LLM Wiki (LLM-WIKI-001)
wiki_collection_name: str = "wiki_knowledge"     # 기존
# wiki-agentic-navigation D8: 프롬프트 목차 상한 (초과 시 최신순 절단)
wiki_toc_max_items: int = 50
wiki_toc_max_bytes: int = 4000
```

- 환경변수 override 가능(pydantic Settings 기존 메커니즘), 마이그레이션·신규 env 필수값 없음

---

## 6. E2E 수동 검증 시나리오 (FR-08)

전제: 에이전트에 `wiki_read` 도구 추가(카탈로그에서 선택), 승인 위키 2건 이상 존재.

1. "이 에이전트가 아는 최근 결정사항 알려줘"
   → 기대: supervisor가 wiki_read 워커 라우팅 → `wiki_read` tool_call ≥ 1회
   → 확인: `GET /agents/runs/{run_id}` tool_calls에 `wiki_read` + `arguments.article_id`
2. "(목차의 특정 문서 제목) 내용 기준으로 답해줘"
   → 기대: 해당 문서 id로 wiki_read 호출, 답변에 본문 근거 반영
3. 부정 케이스: 위키 0건 에이전트 → 목차 블록 미주입(LangSmith 프롬프트 확인),
   wiki_read 호출 시 실패 텍스트 → "위키에서 확인되지 않습니다" 계열 답변
4. 회귀: `use_wiki_first` 에이전트 기존 검색 동작 + `[출처: wiki:{title}]` 표기 확인

---

## 7. 리스크 재점검 (Plan §5 대비 변동분)

| 리스크 | Plan 시점 | Design 확정 후 |
|--------|-----------|---------------|
| compile async 불가 | Medium | **해소** — `async def compile` 확인, await 조회 가능 (D1) |
| 열람 기록 배선 누락 | (미식별) | **해소** — on_tool_start 범용 자동 기록 확인 (D4) |
| 카탈로그 프론트 계약 | Medium | **해소** — internal: 자동 동기화 + 패턴 통과 확인 (D5) |
| 워커가 목차를 못 보는 문제 | (미식별) | **신규 식별→설계 반영** — supervisor만 주입 시 워커 LLM이 id를 모름 → 이중 주입(D1)으로 해결 |
| SQL 필터 ↔ entity 미러 불일치 | Low | 테스트로 고정 (D7 미러 테스트) |
| create_react_agent prompt 파라미터 시그니처 | (신규) | 구현 시 langgraph 버전 시그니처 확인 — 미지원이면 SystemMessage prepend 방식으로 대체 (동일 효과) |

---

## 8. Out of Scope 재확인

- general_chat 경로 (custom agent 한정), 인용 강제(wiki-usage-attribution 후속),
  위키 생성·승인 플로우, `use_wiki_first` 동작 변경(D3 metadata 1키 추가 제외), DB 스키마

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-23 | Initial — Plan 미확정 결정 D1~D8 코드 추적 근거로 확정 | 배상규 |
