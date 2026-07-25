# LLM Wiki 런타임 읽기 흐름 (LLM-WIKI-001)

> 에이전트가 답변 생성 시 "자기 위키"를 언제, 어디서, 어떻게 읽는지의 전체 경로.
> 작성일: 2026-07-23 / 기준 코드: master (PR #45 머지 후)

---

## 0. 한 줄 요약

위키는 **시스템 프롬프트에 미리 로드되지 않는다.**
LLM이 `internal_document_search` 도구를 호출하는 순간, 그 도구 내부의 검색 어댑터가
**Qdrant `wiki_knowledge` 컬렉션 → MySQL `wiki_article` 하이드레이션 → 승인+미만료 필터**
순서로 위키를 조회하고, 부족분만 기존 하이브리드 검색(원본 청크)으로 폴백한다.
결과는 도구 응답 텍스트로 LLM 컨텍스트에 들어간다.

```
[앱 기동]   main.py: RunScopedWikiSearch 싱글톤 조립 → ToolFactory에 주입
                │
[대화 요청] RunAgentUseCase: RunContext(agent_id) ContextVar 설정
                │
[그래프 실행] LLM이 internal_document_search 도구 호출 결정
                │
[도구 실행] InternalDocumentSearchTool._arun(query)
                │  hybrid_search_use_case ← 실은 RunScopedWikiSearch (use_wiki_first=True일 때)
                ▼
        RunScopedWikiSearch.execute()
                │  ContextVar에서 agent_id 획득 (없으면 → 기존 hybrid로 폴백, 위키 미조회)
                ▼
        WikiFirstSearchUseCase.execute()
                │  ① wiki_repo.search_similar(agent_id, query, top_k)
                │     - 쿼리 임베딩(OpenAI) → Qdrant wiki_knowledge 벡터 검색(agent_id 필터)
                │     - hit id로 MySQL wiki_article 하이드레이션
                │     - is_searchable(now): APPROVED + 미만료만 통과
                │  ② 위키 hit ≥ top_k → 위키만 반환
                │     위키 hit < top_k → HybridSearchUseCase(원본 ES/Qdrant) 폴백 후 병합
                ▼
        HybridSearchResult(source="wiki", metadata={wiki:"true", title, ...})
                │
[포맷팅]  _format_results(): "[출처: …]\n{content}" 텍스트로 변환 → LLM에 도구 결과로 반환
                │  동시에 hit별 tracker.record_retrieval() → ai_retrieval_source
                │  (위키 hit은 fusion_source='wiki'로 저장 → 근거 API/배지에서 식별)
                ▼
[LLM]     도구 결과를 컨텍스트로 최종 답변 생성
```

---

## 1. 기동 시점 — 배선 (한 번만 실행)

**위치: `src/api/main.py` (약 2362~2401행)**

앱이 뜰 때 위키 검색 어댑터가 조립되어 `ToolFactory`에 주입된다. 이 시점에는 아무 위키도 읽지 않는다 — 읽을 "통로"만 만든다.

```python
# LLM-WIKI-001 Step6: 승인 위키 우선 검색 어댑터(run-scoped 세션)
_wiki_collection   = settings.wiki_collection_name        # 기본 "wiki_knowledge"
_wiki_embedding    = OpenAIEmbedding(...)                 # 쿼리/본문 임베딩용
_wiki_vector_store = QdrantVectorStore(collection_name=_wiki_collection)

_wiki_search = RunScopedWikiSearch(
    session_factory=get_session_factory(),        # 호출마다 MySQL 세션 새로 염
    repo_builder=_wiki_repo_builder,              # (session) -> WikiArticleRepository
    inner_search_getter=get_configured_hybrid_search_use_case,  # 폴백용
    logger=app_logger,
)

tool_factory = ToolFactory(..., wiki_search=_wiki_search)
```

핵심 설계: `ToolFactory`는 앱 싱글톤이므로 MySQL 세션을 미리 들고 있을 수 없다.
그래서 `RunScopedWikiSearch`가 **매 검색 호출마다** `session_factory`로 세션을 열고 닫는다
(RunTracker와 동일 패턴, DB-001 준수).

---

## 2. 도구 생성 시점 — use_wiki_first 스위치

**위치: `src/infrastructure/agent_builder/tool_factory.py:64-68`**

에이전트별 RAG 도구 설정(`RagToolConfig`, DB의 agent tool_config JSON)에
`use_wiki_first: bool` 필드가 있다 (`src/domain/agent_builder/rag_tool_config.py:47`, 기본 `False`).

```python
def _select_search(self, rag_config: RagToolConfig):
    """use_wiki_first=True이고 위키 어댑터가 있으면 위키 우선 검색을, 아니면 hybrid를 반환."""
    if rag_config.use_wiki_first and self._wiki_search is not None:
        return self._wiki_search          # ← 위키 경로
    return self._get_hybrid_search()      # ← 기존 경로 (위키 완전 미개입)
```

선택된 검색 객체는 `InternalDocumentSearchTool(hybrid_search_use_case=...)`로 주입된다.
**도구 입장에서는 위키 여부를 모른다** — 두 구현 모두 `.execute(request, request_id)`
시그니처가 같아서(duck typing) 도구 코드는 무수정이다.

> ⚠️ `use_wiki_first=False`(기본값)인 에이전트는 위키를 **전혀 읽지 않는다.**
> "위키를 읽는데 반영이 안 된다"를 조사하기 전에 이 플래그부터 확인할 것.

---

## 3. 요청 시점 — agent_id는 어디서 오나

**위치: `src/application/agent_builder/run_agent_use_case.py:518-525`**

대화 요청이 들어오면 그래프 실행 직전에 `RunContext`가 ContextVar에 설정된다.

```python
ctx_token = set_current_run_context(
    RunContext(run_id=run_id, user_id=..., agent_id=agent_id, callback=...)
)
```

`RunScopedWikiSearch`는 이 ContextVar에서 agent_id를 꺼낸다
(`src/application/wiki/run_scoped_wiki_search.py:37-41`):

```python
ctx = get_current_run_context()
agent_id = getattr(ctx, "agent_id", None) if ctx is not None else None
if not agent_id:
    # 에이전트 컨텍스트 없음(graph 외부 호출 등) → 기존 검색으로 폴백
    return await inner.execute(request, request_id)
```

즉 **위키 격리 단위는 agent_id**다. 에이전트 A의 실행에서는 A의 위키만 검색된다.
graph 밖에서 검색이 호출되면(관리 화면의 검색 테스트 등) 위키 없이 원본 검색만 탄다.

---

## 4. 검색 시점 — 실제 위키 읽기 (핵심)

### 4-1. 위키 우선 + 폴백 병합

**위치: `src/application/wiki/wiki_first_search_use_case.py:29-46`**

```python
articles = await self._wiki_repo.search_similar(agent_id, request.query, request.top_k, now, ...)
wiki_results = [self._to_result(a) for a in articles]

if len(wiki_results) >= request.top_k:
    return wiki_results[:top_k]                      # 위키만으로 충족

fallback = await self._inner.execute(request, ...)   # 원본 하이브리드 검색
merged = self._merge(wiki_results, fallback.results, top_k)  # 위키 우선, id 중복 시 위키 유지
```

- 위키가 top_k(도구 설정, 보통 5)를 채우면 **원본 검색은 아예 실행 안 됨**
- 부족하면 원본 청크로 보충 — 순서는 항상 위키 먼저

### 4-2. 위키 저장소 검색 내부

**위치: `src/infrastructure/wiki/wiki_repository.py:150-163, 212-220`**

```python
async def search_similar(self, agent_id, query, top_k, now, request_id):
    vector = await self._embedding.embed_text(query)          # ① 쿼리 임베딩
    docs = await self._vector_store.search_by_vector(         # ② Qdrant 벡터 검색
        vector=vector, top_k=top_k,
        filter=SearchFilter(metadata={"agent_id": agent_id}), # agent 격리
        collection_name="wiki_knowledge",
    )
    ids = [d.id.value for d in docs]
    return await self._hydrate_searchable(ids, now, ...)      # ③ MySQL 하이드레이션+필터
```

`_hydrate_searchable`: 벡터 hit의 id로 MySQL `wiki_article`을 조회한 뒤,

```python
return [a for a in ordered if a.is_searchable(now)]
```

**`is_searchable` = `status == APPROVED` AND 미만료** (`src/domain/wiki/entity.py:104-106`).

> 이중 저장 구조: 위키 본문·상태의 원본은 **MySQL**, 유사도 검색용 임베딩은 **Qdrant**.
> Qdrant에는 DRAFT도 색인되어 있을 수 있지만, MySQL 하이드레이션 단계에서
> APPROVED가 아니면 걸러진다. → **승인 안 된 위키는 LLM에게 절대 노출되지 않는다.**
> 부수효과: DRAFT hit이 top_k 슬롯을 차지했다가 필터로 빠지면 위키 결과가
> top_k 미만이 되어 폴백이 발동한다(의도된 보수적 동작).

### 4-3. 검색 결과 표현

**위치: `wiki_first_search_use_case.py:63-82`**

위키 항목은 원본 청크와 같은 `HybridSearchResult` 형태로 변환되되 마킹이 붙는다:

```python
HybridSearchResult(
    id=article.id,
    content=article.content,       # 위키 본문 전문
    score=article.confidence,      # 검색 유사도가 아니라 위키 신뢰도값임에 주의
    source="wiki",                 # ★ 식별 마커 1
    metadata={"title": ..., "source_type": ..., "wiki": "true", ...},  # ★ 마커 2
)
```

---

## 5. LLM 전달 시점 — 프롬프트에 어떻게 들어가나

**위치: `src/application/rag_agent/tools.py:406-485` (`_format_results`)**

도구가 검색 결과를 텍스트로 포맷해 **도구 호출 결과(ToolMessage)** 로 LLM에 반환한다:

```python
source = hit.metadata.get("source", "unknown")
lines.append(f"[출처: {source}]\n{hit.content}")
```

✅ **해결됨 (wiki-agentic-navigation FR-07, 2026-07-23)**: 위키 hit의 metadata에
`source="wiki:{title}"` 키가 추가되어 `[출처: wiki:{title}]`로 렌더링된다.
(과거: `source` 키 부재로 `[출처: unknown]` — LLM이 위키임을 인지 못함)

동시에 hit별로 관측성 기록이 남는다 (`tools.py:458-476`):

```python
await self.tracker.record_retrieval(
    ...,
    fusion_source=getattr(hit, "source", None),   # 위키 hit → 'wiki'
    metadata=dict(hit.metadata),                  # wiki:"true", title 포함
)
```

→ `ai_retrieval_source.fusion_source='wiki'` 로 저장되어
메시지 근거 API(`GET .../messages/{id}/retrievals`)와 프론트 근거 배지에서 식별 가능.

---

## 6. 위키 데이터는 어떻게 만들어지나 (읽기 전 단계, 참고)

| 생성 경로 | source_type | 코드 |
|-----------|-------------|------|
| 원본 문서 증류(배치) | `DISTILLED` | `src/application/wiki/distill_use_case.py` |
| 이유 있는 👎 피드백 환류 | `CONVERSATION` | `src/application/wiki/feedback_service.py` |
| 관리자 직접 작성 | `HUMAN` | `src/application/wiki/human_write_use_case.py` |

모든 경로는 DRAFT로 생성 → 검토 승인(`review_use_case.py`)을 거쳐 APPROVED가 되어야
비로소 §4의 검색에 노출된다. 저장 시 `_index_vector`가 본문 임베딩을 Qdrant에 색인한다.

---

## 7. "읽었는지" 시스템적으로 확인하는 방법

| 확인 대상 | 방법 |
|-----------|------|
| 이 에이전트가 위키 경로를 타는가 | agent tool_config의 `use_wiki_first` 값 확인 |
| 이번 답변에 위키가 컨텍스트로 들어갔는가 | `SELECT * FROM ai_retrieval_source WHERE run_id=? AND fusion_source='wiki'` 또는 메시지 근거 API의 `fusion_source` |
| LLM 프롬프트 실물 확인 | `ai_run.langsmith_run_url` → LangSmith trace에서 ToolMessage 내용 |
| 위키가 검색됐지만 승인 필터에 걸렸는가 | Qdrant hit은 있는데 `ai_retrieval_source`에 wiki 행이 없는 경우 → MySQL `wiki_article.status` 확인 |
| 답변이 위키를 실제로 **참고**했는가 | 현재 미지원 — 인용 강제(청크 ID 태깅) 또는 LLM-judge groundedness 평가 필요 (후속 과제) |

---

## 8. 관련 파일 인덱스

| 역할 | 파일 |
|------|------|
| 배선(싱글톤 조립) | `src/api/main.py` ≈2362-2401 |
| 검색 경로 선택 스위치 | `src/infrastructure/agent_builder/tool_factory.py:64-68` |
| 도구별 opt-in 플래그 | `src/domain/agent_builder/rag_tool_config.py:47` |
| RunContext 설정 | `src/application/agent_builder/run_agent_use_case.py:518` |
| 런타임 어댑터(세션/컨텍스트) | `src/application/wiki/run_scoped_wiki_search.py` |
| 위키 우선+폴백 병합 | `src/application/wiki/wiki_first_search_use_case.py` |
| 벡터 검색+하이드레이션 | `src/infrastructure/wiki/wiki_repository.py:150-220` |
| 승인+만료 정책 | `src/domain/wiki/entity.py:104-106` |
| LLM 전달 포맷+관측 기록 | `src/application/rag_agent/tools.py:406-485` |
