---
title: Graph RAG 모듈 경계 — 확장 훅 4슬롯·wire_graph_rag·계약 테스트 C1~C5
status: approved
source_type: conversation
source_refs:
  - idt/src/domain/extension_hooks/registry.py (_SLOTS, owner 충돌 ValueError, is_visible 닫힘)
  - idt/src/domain/extension_hooks/ports.py, events.py (SupplementalGrant·SupplementalQuery·SupplementalResult)
  - idt/src/api/graph_rag_di.py (wire_graph_rag, _build_store, start_graph_rag, _fail_interrupted_jobs)
  - idt/src/api/graph_rag_runtime_store.py (RuntimeGraphStore)
  - idt/src/api/main.py (wire_graph_rag 호출, lifespan start/close_graph_rag)
  - idt/src/application/knowledge_base/upload_use_case.py, idt/src/application/doc_browse/delete_document_use_case.py (코어 호출 지점)
  - idt/src/infrastructure/agent_builder/tool_factory.py, idt/src/application/agent_builder/workflow_compiler.py (grant 키워드 체인)
  - idt/tests/contracts/test_extension_boundaries.py (C1~C5)
  - docs/02-design/features/graph-rag-foundation.design.md
confidence: 0.85
version: 1
created: 2026-11-21
updated: 2026-11-27
verified_at: 49b0970
reviewer: 배상규
---

# Graph RAG 모듈 경계 — 확장 훅 4슬롯·wire_graph_rag·계약 테스트 C1~C5

## 문제

그래프 RAG는 "빼도 앱이 뜬다"를 목표로 들어왔다. 코어 쪽 업로드·삭제·RAG 도구·에이전트 저장
경로에 그래프 기능을 꽂아야 하지만, 코어가 `graph_rag` 패키지를 import하면 떼어낼 수 없다.
새 보조 검색 공급자나 업로드 후처리 모듈을 붙일 때 같은 구조를 재사용해야 한다.

## 검증된 사실

### 1. 코어는 `domain/extension_hooks/`만 안다

| 슬롯 | 포트 · 메서드 | 코어 호출 지점 | 그래프 구현 |
|------|---------------|----------------|-------------|
| `post_ingest` | `PostIngestHook.on_document_ingested(event, request_id)` | KB `upload_use_case.py` (Qdrant·ES 쓰기 완료 뒤) | `GraphIngestHook` |
| `deletion` | `DocumentDeletionHook.on_document_deleted(event, request_id)` | `delete_document_use_case.py` `_notify_deleted` (단건·검증·일괄 공통) | `GraphDeletionHook` |
| `supplemental` | `SupplementalRetrievalSource.retrieve(SupplementalQuery) -> SupplementalResult` | `rag_agent/tools.py` | `GraphRetrievalSource` |
| `exposure` | `FeatureExposurePort.is_visible(feature, caller_is_admin)` | `agent_builder/supplemental_flag.py` | `GraphExposure` |

- 슬롯 이름은 `registry.py`의 `_SLOTS` 튜플로 **고정**. 다른 이름은 `ValueError`.
- 다른 owner가 이미 차지한 슬롯에 등록하면 **기동 시 `ValueError`**. 같은 owner 재등록은 교체. 그래프 owner는 `"graph_rag"`.
  → 슬롯 하나당 공급자 하나다. 두 번째 보조 검색 공급자를 붙이려면 슬롯 설계부터 바꿔야 한다.
- `is_visible`은 미등록·예외일 때 `False`(닫힘).
- 아무것도 등록하지 않으면 모든 슬롯이 `None`이고 코어 호출 지점은 바로 반환한다.
- 코어 호출 지점은 훅 예외를 **로그만 남기고 삼킨다** — 업로드·삭제 결과는 훅 실패와 무관.
- `SupplementalResult`는 `label, hits, weight(기본 0.5), skip_reason`. "실행 안 함"은 예외가 아니라 빈 hits + `skip_reason`으로 표현.
- `SupplementalQuery`의 hard/lenient 필터는 `MappingProxyType`으로 동결된다(공급자가 도구 필터를 못 바꿈).
- 코드 기준 동작: Plan은 훅 3개였으나 코드는 4개(`exposure` 추가). Design의 `on_kb_deleted`는 없다(KB 삭제는 soft delete라 결과 청크를 ES에서 재조회하는 단계에서 걸러짐).

### 2. grant는 키워드로만 흐른다

```
대화 라우트 3곳: ws_router(WS) · agent_builder_router POST /{agent_id}/run · GET 스트림
  supplemental_grant=SupplementalGrant.for_role(auth_ctx.role)   (role == "admin" → caller_is_admin)
→ RunAgentUseCase.execute / stream → _prepare_graph
→ WorkflowCompiler.compile  (서브에이전트 _compile_sub_agent → compile 재귀에도 전달)
→ 도구 생성 시 grant가 있을 때만 **{"supplemental_grant": grant} 로 펼침
→ ToolFactory.create → RAG 도구(InternalDocumentSearchTool)에만 전달
```

- 조건부 펼침은 기존 fake ToolFactory 테스트 호환용(시그니처에 없는 키워드를 넘기지 않음).
- `supplemental_source`는 `ToolFactory`가 레지스트리에서 읽는다.
- "호출자 opt-in"을 bool 플래그가 아니라 객체 존재로 표현한다: grant 객체가 있으면 opt-in, 관리자 여부는 그 안의 필드.

### 3. 조립: `wire_graph_rag` + lifespan 2줄

`main.py`에는 `wire_graph_rag(app, ...)` 호출 1곳과 lifespan `start_graph_rag()`·`close_graph_rag()`만 있다
(Plan의 `register_graph_rag(app)` 한 줄 안은 Design 단계에서 바뀜).

`wire_graph_rag` 순서: 설정 캐시 리더 → `_build_store`(Neo4j) → 추출 구성 → 검색 구성 →
레지스트리 4슬롯 등록 → 관리자·공개 라우터 등록 → 모듈 전역 `_runtime` 기록.

- `_build_store`는 `GRAPH_BACKEND`가 `off`(기본)/알 수 없는 값, URI·비밀번호 누락, **드라이버 생성 실패(neo4j 미설치 포함)** 면 경고 후 `None`.
- `RuntimeGraphStore`는 매 호출마다 현재 store를 찾아 위임한다. 기동 중 store가 꺼져도 미리 만든
  러너·검색 소스가 이전 store를 붙잡지 않게 하려는 장치. store가 없으면 `GraphBackendUnavailableError`.
  그래서 DI가 넘기는 store 객체는 항상 존재하고, "store 없음"은 첫 저장소 호출의 예외로 드러난다.
- `start_graph_rag`: ① pending·processing 잡을 전부 `failed`(`interrupted`)로 정리 ② `ensure_schema`.
  벡터 차원 불일치(`GraphEmbeddingDimMismatchError`)면 store를 닫고 모듈 비활성, 그 밖 예외(Aura 정지 등)는 경고만 남기고 store 유지.

### 4. 계약 테스트 C1~C5 (`tests/contracts/test_extension_boundaries.py`)

| ID | 막는 것 | 검사 방식 |
|----|---------|-----------|
| C1 | 코어 파일의 `graph_rag` import (예외: 경로/파일명에 graph_rag, `api/main.py`, `*_di.py`) | AST |
| C2 | 대화 라우트의 grant 전달 누락 (`ws_router.py` ≥1, `agent_builder_router.py` ≥2) | AST 호출·키워드 |
| C3 | 비대화 호출자(웹훅·백그라운드 워커·스케줄·RAGAS target_executor·승인 결정/실행 스케줄러)에 `supplemental_grant`/`SupplementalGrant` 등장 | 소스 문자열 |
| C3b | RAGAS headless 실행에서 grant를 `SupplementalGrant(...) if allow_supplemental else None` 한 형태로만 생성, `ragas_router.py`에 `allow_supplemental`·`403` 존재 | AST+문자열 |
| C4 | 키워드 체인 단절(`_prepare_graph`·`stream`, 컴파일러 조건부 펼침, 서브에이전트 재귀) | AST |
| C5 | 에이전트 저장 경로(create·update·fork)에서 `strip_unexposed_graph_flag(` 누락 | 소스 문자열 |

C3·C5는 문자열 검사라 다른 이름으로 우회하면 못 잡는다. 문자열 vs AST 선택 기준은 [[ast-source-contract-tests]].

## 다음에 적용하는 법

1. **새 부가 모듈을 코어 경로에 붙일 때** 코어 수정은 `extension_hooks` 슬롯 호출 지점까지만. 모듈 쪽은 `*_di.py`의 `wire_*` 함수 + lifespan 2줄로 조립하고, C1과 같은 import 금지 테스트에 패키지명을 추가한다.
2. **새 슬롯이 필요하면** `_SLOTS` 튜플·`ExtensionHooks` 필드·포트를 함께 늘린다. 공급자 다중화는 현재 구조로 불가(owner 충돌 = 기동 실패).
3. **실행 경로를 새로 만들 때**(새 트리거·새 배치) grant를 넘길지 먼저 결정하고, 넘기지 않는다면 C3 목록에 그 파일을 추가한다. 대화 라우트를 새로 만들면 C2 기대 개수를 올린다.
4. **"store is None" 분기에 의존하지 말 것** — 실제 조립에서는 `RuntimeGraphStore`가 예외를 던진다. 저장소 부재 처리는 `GraphBackendUnavailableError`를 잡는 쪽으로 쓴다.

## 관련 문서

- [[overview]] (Graph RAG 개요) · [[execution-gates-and-rollout]] · [[detachable-module-seam]] · [[ast-source-contract-tests]]
