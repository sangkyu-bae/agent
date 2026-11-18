# graph-rag-foundation Planning Document

> **Summary**: 문서 업로드 뒤 엔티티·관계를 추출해 Neo4j 그래프로 쌓고, 같은 대상을 가리키는 언급은 Jev 확률 판정으로 하나의 엔티티에 묶으며, 그래프 탐색 결과를 기존 하이브리드 검색의 세 번째 RRF 입력으로 합치는 Graph RAG 기반 계층. 관리자 테스트 페이지에서 추출·판정·검색을 확인한다.
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-16
> **Status**: Draft
> **선행 결정**: `docs/archive/2026-06/llm-wiki-knowledge-base/llm-wiki-knowledge-base.design.md:28` — "GraphRAG MVP 제외, 후속 고도화"로 미룬 항목을 이 사이클이 이어받는다.

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 하이브리드 검색(BM25+벡터 RRF)은 질문과 비슷한 청크를 찾을 뿐이라, 상품→요건→예외처럼 여러 문서에 흩어진 관계나 "한도"="여신 한도" 같은 별칭을 따라가지 못한다. 엔티티·관계를 담을 저장소도 추출 경로도 없다. |
| **Solution** | 그래프 저장소 포트(Neo4j 어댑터), 규칙+LLM 혼합 추출 백그라운드 잡, Jev `ChoiceQuestion` 기반 엔티티 판정(꺼지거나 실패하면 LLM 선택으로 대체), 그래프 검색을 RRF 세 번째 입력으로 넣는 경로, 관리자 테스트 페이지를 만든다. 전부 플래그로 기본 off. |
| **Function/UX Effect** | 관리자가 KB 문서 추출을 실행하고, 엔티티·관계와 근거 청크를 확인하고, 같은 질문을 그래프 검색과 하이브리드 검색으로 나란히 비교하고, 애매하게 판정된 병합을 승인·거절한다. 에이전트 답변의 근거 칩은 지금과 같은 형식으로 나온다. |
| **Core Value** | 여러 문서를 잇는 질문에 근거 청크를 더 찾아오되, 모든 관계가 원문 청크로 역추적되는 "출처 불변식"을 그래프 계층에도 지킨다. 같은 엔티티 판정은 확률로 기록되어 감사할 수 있다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 여러 문서에 걸친 관계·용어 별칭을 하이브리드 검색이 따라가지 못함. GraphRAG를 받을 저장소·추출·판정·검색 경로가 전혀 없음 |
| **WHO** | 1차: P3 관리자(테스트 페이지에서 추출·판정·검색 검증), 최종 수혜: P1 심사역·P4 행원(근거 회수 향상), P2 KB 운영자(후속 사이클에서 KB 화면 노출) |
| **RISK** | 잘못된 엔티티 병합이 그래프 전체 검색을 오염 / 전역 공유 그래프에서 권한 없는 KB 근거 노출 / Aura(외부 클라우드)에 사내 규정 내용 보관 — 개발·PoC 한정, 도입 전 자체 호스팅 전환 / 청크 수 비례 LLM 비용 |
| **SUCCESS** | `GRAPH_BACKEND=off`에서 기존 동작 100% 동일 · 관계·언급의 근거 청크 역추적 실패 0건 · 다문서 질문 부분집합에서 RAGAS context_recall 향상, 나머지 회귀 없음 · 관리자가 DB/Swagger 없이 추출→확인→검색 비교→검토 완주 |
| **SCOPE** | 독립 모듈(코어는 훅 인터페이스만 앎) + 노출 단계 `off → admin_only → general` (이번 사이클은 `admin_only`까지). 백엔드 기반(포트·Neo4j·추출 잡·판정·그래프 검색·설정) + 관리자 테스트 페이지 + 관리자에게만 보이는 빌더 토글. 커뮤니티 요약·그래프 시각화·KB 단위 격리·`general` 전환 실행은 제외 |

---

## 1. Overview

### 1.1 Purpose

지금 검색은 "질문과 비슷한 텍스트 조각"을 찾는다. 다음 두 유형에서 실패한다(사용자가 목표 질의로 선택).

1. **여러 문서에 걸친 관계** — "A상품 대상 고객이 받을 수 있는 예외 규정은?"처럼 상품 정의, 대상 요건, 예외 조항이 서로 다른 문서에 있다. 각 조각은 질문과 유사도가 낮아 상위 K에 들지 못한다.
2. **용어·별칭 연결** — "한도", "여신 한도", "대출 한도"가 같은 개념인데 표기가 달라 BM25가 놓치고, 벡터 검색은 다른 "한도"(카드 한도 등)와 섞는다.

그래프는 "엔티티 → 관계 → 다른 문서의 엔티티 → 그 근거 청크"로 이동해 이 조각들을 모은다.

### 1.2 Background

- **현재 자산** (Explore 조사 결과, 2026-11-16):
  - 적재: `UnifiedUploadUseCase`(`idt/src/application/unified_upload/use_case.py`)가 Qdrant(KB별 컬렉션)와 ES(공용 인덱스, nori)에 병렬로 쓴다. 청크 메타데이터에는 `document_id`·`chunk_id`·`kb_id`·`parent_id`·`clause_title`·`page_*`가 들어간다.
  - 검색: `InternalDocumentSearchTool`(`idt/src/application/rag_agent/tools.py`)이 권한 확인 → 라우팅 검색 또는 하이브리드 검색(`RRFFusionPolicy`)을 수행한다. 리랭커는 인터페이스만 있다.
  - 업로드 뒤 LLM 호출 선례: `section_summary`(잡 테이블 V044, `asyncio.create_task`, `Semaphore(3)`, `uuid5` 결정적 ID, 실패해도 업로드 무관).
  - 판정 포트: `JudgmentPort`(`idt/src/domain/judgment/interfaces.py`) — `NoulQuestion`·`ChoiceQuestion`과 라벨별 확률을 지원한다. Jev·AnyJev 어댑터와 `JUDGMENT_BACKEND`(기본 off)가 있다. **실호출 스모크는 이월 상태**다.
  - 근거 칩: `ai_retrieval_source` 행 → `_attach_sources` → `RunSourcePolicy`. 필요한 필드는 `document_id`·`chunk_id`·`content_preview`·`collection_name`·`filename|clause_title`이다.
- **없는 것**: NER, 엔티티·관계 추출, 관계 테이블, 그래프 DB나 라이브러리, 문맥 기반 청킹.
- **원칙 정합성**:
  - "출처 불변식"(growing-agent-vision 원칙 3): 모든 엣지에 근거 `chunk_id`를 둔다.
  - "LLM은 제안, 사람이 확정": 애매한 병합은 검토 큐에 올린다.
  - "격리"(원칙 7): 추출은 비동기로 하고 답변 경로와 분리한다.
  - "측정 없이 성장 없음"(원칙 5): RAGAS로 켜기 전·후를 비교한다.
  - "일반화가 이긴다": 엔티티 타입은 코드가 아니라 설정 데이터로 둔다.

### 1.3 Related Documents

- 유저 시나리오: `docs/USER-SCENARIOS.md` (S2 규정 근거 확인, P1 사내 용어)
- 비전: `idt/docs/architecture/growing-agent-vision.md` §3 원칙 1~7
- 판정 포트: `docs/archive/2026-10/judgment-backend/`
- 업로드 뒤 LLM 잡 선례: `idt/src/application/section_summary/`
- 전역 설정 선례: `idt/db/migration/V065__create_multimodal_setting.sql` + `AdminMultimodalPage`
- 위키: `docs/wiki/backend/architecture-overview.md`, `docs/wiki/backend/patterns/app-lifetime-client-singleton.md`(Neo4j 드라이버도 앱 수명 싱글턴)

---

## 2. Scope

### 2.1 In Scope

- [ ] **M0 모듈 경계와 노출 단계** (v0.3, 사용자 요구: "일반 사용자에게 공개하지 않고 관리자만 테스트 → 검증이 끝나면 끼워 넣는다")
  - **모듈 경계:** 그래프 코드는 전부 `graph_rag` 패키지에 둔다. 코어(업로드·삭제·하이브리드 검색·에이전트 실행)는 **훅 인터페이스 3개만** 안다. 모듈을 등록하지 않으면 훅은 아무 일도 하지 않는다(no-op).
    1. `PostIngestHook`: 업로드가 끝났을 때 호출
    2. `DocumentDeletionHook`: 문서를 삭제할 때 호출
    3. `SupplementalRetrievalSource`: RRF에 추가 입력을 공급
  - **조립 위치:** DI와 라우터 등록은 `register_graph_rag(app)` 한 곳에서 한다. `main.py`에는 호출 한 줄만 추가한다.
  - **노출 단계:** `graph_rag_setting.rollout_stage`
    - `off`: 모듈 전체 비활성. 추출 잡, 검색, 관리자 API 중 설정 조회를 뺀 나머지가 모두 꺼진다.
    - `admin_only`: 이번 사이클의 목표 상태. 관리자 테스트 페이지와 "관리자가 대화 경로에서 직접 실행한 에이전트"에서만 그래프 검색을 쓴다.
    - `general`: 일반 사용자에게 공개. 전환은 다음 사이클에서 RAGAS 결과(SC-4)를 확인한 뒤 관리자가 실행한다.
  - **실패 시 기본값은 닫힘:** 단계 값을 읽지 못하거나 잘못된 값이면 `off`로 취급한다.
- [ ] **M1 그래프 저장소 포트 + Neo4j 어댑터** — `GraphStorePort`(domain), Neo4j 어댑터(infrastructure), 테스트용 메모리 페이크. `GRAPH_BACKEND=off|neo4j`(기본 off). off이면 앱 기동·검색이 지금과 같다.
- [ ] **M2 전역 설정** — `graph_rag_setting` 단일 행 테이블(V086 후보): 추출 사용 여부, **Jev 모드 on/off**, 판정 기준값(상·하한), 추출 LLM 모델, 동시 실행 수, 최대 탐색 단계, 기본 엔티티 타입 목록. 관리자 API로 조회·수정한다.
- [ ] **M3 추출 잡** — 문서 단위 `graph_extraction_job`(section_summary_job 구조). 규칙 추출(조문 참조 `제N조`·`별표 N`)과 LLM 구조화 추출(엔티티·타입·관계·근거 인용)을 함께 쓴다. 업로드 완료 뒤 자동 실행(전역 설정이 on일 때)하고, 관리자가 수동으로 실행·재실행할 수 있다.
- [ ] **M4 엔티티 판정(resolution)**
  - 후보 검색: 정규화 이름, 별칭, 이름 임베딩 기준 상위 K(기본 5).
  - Jev `ChoiceQuestion{후보…, NEW}`로 판정하고 세 구간으로 나눈다. 상한 이상이면 연결, 하한 미만이면 새 엔티티, 그 사이는 **LLM이 다시 판정**한다.
  - Jev가 꺼져 있거나 실패하면 같은 선택지를 **LLM 선택으로 대체**한다.
  - 모든 판정을 `graph_resolution_decision`에 기록한다(판정자, 확률, 구간, 결과).
- [ ] **M5 검토 큐** — 가운데 구간에서 LLM이 정한 건을 관리자가 사후에 승인(유지)하거나 거절(분리·되돌리기)한다.
- [ ] **M6 그래프 검색** — 질문에서 엔티티를 연결하고(Kiwi 명사 + 정규화 일치 + 이름 벡터), 1~N단계 이웃을 따라가 `MENTIONED_IN` 청크를 모은다. 사용자가 접근할 수 있는 KB·부서 필터를 적용한 뒤, 하이브리드 RRF의 세 번째 입력(`fusion_source="graph"`)으로 합친다. 실제로 그래프 검색을 실행하는 조건은 다음 세 가지가 **모두** 참일 때다(FR-20).
  - 에이전트 `RagToolConfig.use_graph`가 True(기본 False)
  - 노출 단계가 실행을 허용함
  - 호출자가 `allow_graph=True`를 명시적으로 넘김
- [ ] **M6-b 빌더 토글 (관리자 전용)** — 에이전트 빌더의 검색 설정에 "그래프 검색(테스트)" 토글을 둔다. `admin_only` 단계에서는 관리자에게만 보이고, 일반 사용자에게는 화면에도 API 응답에도 나오지 않는다. 일반 사용자가 저장 API로 `use_graph=True`를 보내면 거부하거나 무시한다(Design에서 결정).
- [ ] **M7 삭제·재색인 정합** — 문서를 삭제하면 해당 청크의 언급과, 그 문서만 근거로 둔 관계를 지우고, 고아 엔티티를 정리한다. 재청킹하면 추출 잡을 다시 돌려야 하는 상태로 표시한다.
- [ ] **M8 관리자 테스트 페이지** (`AdminGraphRagPage`, idt_front)
  1. 설정: Jev 토글, 기준값, 추출 on/off, 타입 목록
  2. 문서별 추출 실행·상태: KB를 고르면 문서 목록, 잡 상태, 엔티티·관계 수, 실행·재실행
  3. 엔티티·관계 목록: 검색, 별칭, 연결된 관계, 근거 청크 원문
  4. 그래프 검색 테스트: 질문을 넣으면 연결된 엔티티, 따라간 경로, 찾은 청크를 하이브리드 결과와 나란히 보여준다
  5. 병합 제안 검토 큐
- [ ] **M9 평가** — RAGAS 골든셋에서 `use_graph` on/off를 비교한다. 다문서 질문 부분집합을 따로 집계한다.

### 2.2 Out of Scope

- GraphRAG 커뮤니티 요약과 전역 검색("이 규정집의 핵심 주제는?" 유형). 사용자 선택에서 제외했다.
- 그래프 시각화(노드·엣지 그림). 관리자 페이지는 표만 제공한다.
- **KB 단위 엔티티 격리.** 이번에는 전역 공유로 둔다. 다만 스키마에 `scope_key`를 넣어 두어, 나중에 마이그레이션 없이 KB 단위로 바꿀 수 있게 한다(§7.2 D6).
- 일반 사용자에게 공개하는 `general` 단계 전환 실행. 전환 기능(설정 값)은 만들지만, 실제 전환은 테스트가 끝난 뒤 다음 사이클에서 한다.
- P2용 KB 상세 화면 노출. 후속 사이클에서 한다.
- 리랭커 구현. 인터페이스만 있는 상태로 둔다.
- 운영 배포 compose 변경 커밋. 개발·PoC는 Aura를 쓰므로 compose에 Neo4j 서비스를 넣지 않는다. 자체 호스팅 예시는 가이드 문서로만 남긴다(`deploy/`는 로컬 전용 파일).
- 자체 호스팅 전환 작업 자체와 보안 심사. 사내 도입 단계에서 별도로 진행한다.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `GraphStorePort`가 엔티티 upsert·별칭 추가·관계 upsert·언급 연결·이웃 탐색(최대 N단계)·청크/문서 단위 삭제·엔티티 병합/분리를 제공한다. domain은 Neo4j를 import하지 않는다 | High | Pending |
| FR-02 | `GRAPH_BACKEND=off`(기본)이거나 Neo4j 연결이 실패해도 앱이 기동하고, 업로드·검색이 그래프 없이 지금처럼 동작한다(경고 로그만) | High | Pending |
| FR-03 | `graph_rag_setting` 단일 행을 관리자 API로 조회·수정한다. 값 검증은 도메인 VO 한 곳에서 한다 | High | Pending |
| FR-04 | 업로드가 끝나면 전역 추출 설정이 on일 때 문서 단위 추출 잡을 비동기로 시작한다. 잡이 실패해도 업로드 결과·상태는 바뀌지 않는다. 엑셀 업로드는 기본 제외한다(section_summary 선례) | High | Pending |
| FR-05 | 규칙 추출: `제N조(의N)`, `별표 N`, `부칙` 참조를 조문 엔티티와 `REFERS_TO` 관계로 만든다. LLM을 부르지 않는다 | High | Pending |
| FR-06 | LLM 추출: 청크마다 구조화 출력으로 `{entities:[{name,type,description}], relations:[{source,target,type,evidence}]}`를 받는다. type은 설정의 타입 목록 안에서만 허용하고, 목록 밖이면 `기타`로 둔다. evidence가 청크 원문에 없는 관계는 버린다 | High | Pending |
| FR-07 | 모든 `MENTIONED_IN`과 관계 엣지에 근거 `chunk_id`·`document_id`·`kb_id`를 필수로 남긴다. 근거 없는 엣지는 저장하지 않는다 | High | Pending |
| FR-08 | 엔티티 판정: 후보 상위 K를 찾은 뒤, Jev 모드가 on이면 `ChoiceQuestion`(후보 라벨 + `NEW`)으로 판정한다. 확률이 상한 이상이면 연결, 하한 미만이면 새 엔티티, 그 사이는 LLM 재판정이다. 후보가 0개이면 판정 없이 새 엔티티로 만든다 | High | Pending |
| FR-09 | Jev 모드 off, `JudgmentPort` 미조립, `JudgmentError` 3종(Timeout/Unavailable/Protocol) 중 하나라도 해당하면 같은 선택지를 LLM 선택으로 판정한다. 대체 판정이 일어난 사실을 판정 기록에 남긴다 | High | Pending |
| FR-10 | 모든 판정을 `graph_resolution_decision`에 기록한다: mention 원문, 근거 chunk, 후보 목록, 선택, 판정자(jev/llm/rule/none), 확률, 구간(auto_link/auto_new/llm_rejudge), 검토 상태 | High | Pending |
| FR-11 | 검토 큐: `llm_rejudge` 구간 건을 승인하면 판정 결과를 유지하고, 거절하면 연결을 되돌린다(병합했으면 분리, 새로 만들었으면 지정 엔티티로 병합). 처리자와 시각을 기록한다 | Medium | Pending |
| FR-12 | 그래프 검색: 질문 → 엔티티 연결 → 최대 N단계(기본 2, 설정) 탐색 → 청크 ID 수집 → **사용자가 접근할 수 있는 kb_id·visibility·부서 필터를 청크 단위로 적용** → ES에서 청크 본문 조회 → RRF 세 번째 입력으로 넣는다 | High | Pending |
| FR-13 | 그래프 검색 결과도 `ai_retrieval_source`에 `fusion_source="graph"`로 기록하고, 근거 칩은 기존 `RunSourcePolicy`를 그대로 쓴다 | High | Pending |
| FR-14 | 그래프 검색은 실패하거나 시간이 초과되면 하이브리드 결과만으로 응답한다(예외를 전파하지 않음). 그래프 검색 시간 상한은 설정으로 둔다 | High | Pending |
| FR-15 | 문서를 삭제하면 해당 문서의 언급·관계 근거를 제거하고, 근거가 0개가 된 관계와 엔티티를 지운다 | High | Pending |
| FR-16 | 관리자 API: 설정 조회·수정 / KB·문서별 잡 목록·실행·재실행 / 엔티티 검색·상세(별칭·관계·근거) / 그래프 검색 테스트(경로 포함, 하이브리드와 나란히) / 검토 큐 목록·승인·거절. 전부 관리자 권한 | High | Pending |
| FR-17 | 관리자 테스트 페이지 5개 탭(FR-16 대응). 프론트 타입·서비스·훅을 API 계약과 동기화한다 | High | Pending |
| FR-18 | 추출 잡은 청크 단위로 다시 돌려도 결과가 같아야 한다(결정적 ID, 완료 청크 건너뛰기). 잡에는 처리 청크 수, LLM 호출 수, 실패 수를 기록한다 | Medium | Pending |
| FR-19 | RAGAS 실행에서 `use_graph` on/off 비교 결과를 남긴다(기존 스윕 기능 재사용 가능성은 Design에서 확인) | Medium | Pending |
| FR-20 | 그래프 검색 실행 조건 = `use_graph` AND 노출 단계 허용 AND **호출자 opt-in `allow_graph=True`(keyword-only, 기본 False)**. `admin_only` 단계에서 opt-in을 넘기는 곳은 (a) 관리자 테스트 API, (b) 호출 사용자가 admin인 대화 라우트(WS·REST·SSE) 둘뿐이다. 웹훅·백그라운드 잡·스케줄·승인 재개·RAGAS(비교 실행 제외)는 넘기지 않는다 | High | Pending |
| FR-21 | 관리자가 만든 `use_graph=True` 에이전트를 일반 사용자가 실행하면 그래프 검색 없이 기존 하이브리드 검색으로 동작한다. 오류나 안내 없이 조용히 빠지며, 구조화 로그(request_id)에 미적용 사유를 남긴다(v0.5, Design §11.13 C-1) | High | Pending |
| FR-22 | 코어 모듈은 `graph_rag` 패키지를 import하지 않는다(훅 인터페이스만 사용). 모듈을 등록하지 않거나 `rollout_stage=off`이면 훅이 no-op이 되고, 기존 테스트 결과가 master와 같다 | High | Pending |
| FR-23 | `rollout_stage` 변경은 관리자만 할 수 있고 변경 이력(이전 값·새 값·처리자·시각)을 남긴다. `general`로 바꿀 때는 RAGAS 비교 기록이 없으면 경고를 보여준다(차단 여부는 Design에서 결정) | Medium | Pending |
| FR-25 | 주제 분류(문서): 추출 잡이 문서 앞부분으로 LLM에게 주제(대분류·소분류·보조)를 제안받고, 기존 주제 목록과 비교해 Jev `ChoiceQuestion`(주제 라벨 + `NEW`) 세 구간으로 판정한다. Jev가 꺼져 있거나 실패하면 LLM 선택으로 대체한다. 이름이 정확히 같으면 판정 없이 연결한다 | High | Pending |
| FR-26 | 주제는 2단계(대분류 > 소분류)다. 문서당 대표 1개(대분류+소분류) + 보조 대분류 최대 2개. 보조 주제는 기존 주제에만 연결하고 새로 만들지 않는다 | High | Pending |
| FR-27 | 주제 목록은 관리자가 기본 목록을 만들고, 맞는 주제가 없으면 자동으로 새 주제를 만든다. 자동으로 만든 주제와 애매한 판정은 검토 대기로 보낸다. 승인하면 확정, 거절하면 다른 주제로 옮기고 문서가 없는 자동 주제는 폐기한다 | High | Pending |
| FR-28 | 주제 판정 기록은 `graph_resolution_decision`에 주제 타입으로 남긴다. 주제 목록·문서↔주제 연결은 MySQL(`graph_topic`·`graph_document_topic`)이 원본이고, Neo4j 청크에는 검색 필터용 `topic_ids`를 복사한다 | High | Pending |
| FR-29 | 그래프 검색(질문)은 질문의 주제를 Jev로 고르고, Jev가 꺼져 있거나 확신이 낮으면 LLM이 주제를 고른다. 고른 주제 문서 안에서만 시작 엔티티를 찾고 탐색한다. 주제를 정하지 못하면 범위를 좁히지 않는다. 질문 단계에서는 새 주제를 만들지 않는다 (module-5) | High | Pending |
| FR-24 | 프론트는 `GET /api/graph-rag/capabilities`(가칭)의 응답 `{stage, visible}`로만 그래프 관련 UI 노출을 정한다. 일반 사용자 응답은 `visible=false`이고, 빌더·채팅·근거 칩에 그래프 관련 표시가 나오지 않는다 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 격리 | 추출 잡·Neo4j 장애가 업로드·채팅 응답 실패로 이어지지 않음 | Neo4j 중지 상태 통합 테스트 |
| 지연 | 그래프 검색 추가 지연 p95 < 800ms(2단계 탐색, 로컬). 상한을 넘으면 결과를 버림 | 그래프 검색 테스트 API 응답 시간 로그 |
| 권한 | 접근 불가 KB의 청크가 그래프 검색 결과에 0건 | 다중 KB·다중 사용자 테스트 |
| 출처 | 관계·언급 엣지의 근거 chunk_id가 ES에 실재하지 않는 건 0 | 정합성 점검 스크립트(관리자 API) |
| 비용 | 문서당 LLM 호출 수 상한(설정), 잡에 호출 수 기록 | 잡 테이블 카운터 |
| 메모리 | 개발·PoC는 Aura 사용으로 VM 추가 메모리 0. 자체 호스팅 시 Neo4j heap·pagecache 합계 ≤ 1.5GB(small 프로필) | 배포 가이드 + 전환 시 측정 |
| 용량 | Aura Free 한도(노드 20만·관계 40만) 대비 사용량을 관리자 페이지에 표시 | 관리자 API 집계 |
| 이식성 | Aura ↔ 자체 호스팅 전환이 `NEO4J_URI`·인증 설정 변경만으로 가능(코드 분기 0) | 로컬 Neo4j 컨테이너와 Aura 양쪽에서 같은 통합 테스트 통과 |
| 아키텍처 | domain → infrastructure import 0, Neo4j import는 `infrastructure/graph/`에만 | verify-architecture, AST 경계 테스트 |
| 로깅 | LOG-001 준수(잡·판정·검색에 request/job id) | verify-logging |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: `GRAPH_BACKEND=off`에서 백엔드 전체 테스트 결과가 master와 같다(새 실패 0, 상시 실패 목록 제외)
- [ ] SC-2: Neo4j를 켠 상태에서 샘플 KB(여신 규정 2~3개 문서)를 추출하면, 관계·언급 근거 역추적 실패가 0건이다
- [ ] SC-3: 라벨링한 별칭 쌍 셋(30쌍 내외, 사람이 정답 지정)에서 자동 연결(auto_link) 정밀도가 0.9 이상이다. Jev 모드와 LLM 대체 모드의 정밀도·재현율을 각각 기록한다(Jev 실호출이 불가하면 LLM 모드만 측정하고 이월을 명시)
- [ ] SC-4: RAGAS 다문서 질문 부분집합에서 `use_graph=on`의 context_recall이 off보다 높고, 전체 셋의 faithfulness가 off 대비 낮아지지 않는다
- [ ] SC-5: 관리자가 테스트 페이지만으로 설정 → 추출 실행 → 엔티티 확인 → 검색 비교 → 검토 처리를 완주한다(DB/Swagger 조작 0회)
- [ ] SC-6: Neo4j를 중지해도 업로드 성공, 채팅 응답 정상(그래프 없이 응답)
- [ ] SC-7: 권한 없는 KB 청크 노출 0건(테스트로 증명)
- [ ] SC-8: `admin_only` 단계에서 일반 사용자 경로(대화·웹훅·백그라운드·스케줄) 전부에서 그래프 검색 실행 0건. 호출자 전수 표와 AST/소스 계약 테스트로 증명한다(`tests/api/test_memory_injection_di.py` W2·W3 패턴)
- [ ] SC-9: `graph_rag` 모듈 등록 줄을 주석 처리해도 앱 기동과 전체 테스트가 통과한다(모듈을 뺄 수 있음을 증명). 코어에서 `graph_rag`를 import하는 곳 0건(AST 경계 테스트)

### 4.2 Quality Criteria

- [ ] 새 모듈 테스트 커버리지 80% 이상, TDD(Red→Green) 순서
- [ ] ruff·프론트 lint 오류 0 (`ruff format`은 새 파일에만, `main.py`는 Edit로만 수정)
- [ ] DDL COMMENT 검사 통과(V054 이후 규칙, COMMENT 안에 콤마 금지, CHARSET 명시 금지)
- [ ] 판정 포트 AST 경계 테스트 `_DECLARED_CONSUMERS`에 새 소비 지점 등록

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 관리자가 만든 그래프 에이전트를 부서에 배포하면 일반 사용자에게 그래프가 노출됨 | High | Medium | 에이전트 설정이 아니라 **실행 시점의 호출자와 노출 단계**로 판정한다(FR-20·21). 에이전트에 `use_graph=True`가 남아 있어도 일반 사용자 실행에서는 꺼진다 |
| 웹훅·백그라운드처럼 대화가 아닌 경로로 그래프가 새어 나감(agent-memory-injection 웹훅 노출 사고와 같은 유형) | High | Medium | `auth_ctx` 유무 같은 간접 신호로 판정하지 않는다. keyword-only opt-in 플래그(기본 False)를 쓰고, `RunAgentUseCase` 호출자 전수 표(§6.2)와 계약 테스트를 둔다(SC-8) |
| 모듈 경계가 무너져 코어가 그래프 코드에 의존 → 끼워 넣기·빼기가 불가능해짐 | Medium | Medium | 훅 인터페이스 3개 + `register_graph_rag()` 단일 조립 + AST 경계 테스트(SC-9) |
| 잘못된 병합("카드 한도"와 "여신 한도"를 하나로)이 검색을 오염 | High | Medium | 세 구간 판정, 가운데는 LLM 재판정 후 검토 큐, 판정 기록으로 분리·되돌리기 가능(FR-11). 검색은 엔티티 타입이 다르면 병합을 막는 규칙 추가 |
| 전역 공유 그래프로 권한 없는 KB 근거 노출 | High | Medium | 탐색은 전역으로 하되 **반환 직전 청크 단위로 권한 필터를 적용**(FR-12). 관리자 페이지 외에는 엔티티 이름·경로를 노출하지 않음. 다중 KB 권한 테스트(SC-7) |
| 12GB VM에서 Neo4j 메모리 압박 | Low | Low | 개발·PoC는 Aura Free를 써서 VM에 Neo4j를 띄우지 않는다(D1-a). 자체 호스팅으로 옮길 때만 heap·pagecache 가이드를 적용한다. `GRAPH_BACKEND` 기본 off, 미기동이어도 앱 정상(FR-02) |
| Aura Free 제약: 노드 20만·관계 40만 한도, 쓰기 없이 3일이면 자동 정지, 정지 30일 뒤 삭제, 백업 없음 | Medium | Medium | 그래프는 재추출로 복구되는 파생 데이터(아래 이중 쓰기 행)이므로 삭제돼도 KB 재추출로 복구한다. 관리자 페이지에 노드·관계 수를 표시해 한도에 다가가는지 확인한다. 정지 상태로 연결이 실패하면 FR-02·FR-14 경로(그래프 없이 응답)를 탄다. 한도 수치는 가입 시 가격 페이지에서 재확인 |
| 사내 규정 내용(엔티티 이름·설명·관계)이 외부 클라우드(Aura)에 계속 보관됨 | High | High | Aura는 개발·PoC 전용으로 한정하고, 사내 실도입 전 보안 검토를 거쳐 자체 호스팅 또는 사내 승인 클라우드로 옮긴다(D1-a). 옮길 때는 `NEO4J_URI` 변경과 재추출만 필요하다. PoC 데이터는 실제 고객 정보가 없는 규정 문서로 제한한다 |
| Aura 왕복으로 그래프 검색 지연 증가 | Medium | Medium | 서버와 가까운 리전을 선택하고, p95 800ms 기준을 Aura 환경에서 측정한다. 상한을 넘으면 그래프 결과를 버린다(FR-14) |
| LLM 추출 비용이 청크 수에 비례 | Medium | High | 전역 on/off, 문서당 호출 상한, 엑셀 제외, 규칙으로 잡히는 조문 참조는 LLM에서 제외, 호출 수 기록 |
| Jev 실호출이 검증되지 않음(스모크 이월) | Medium | High | LLM 대체가 기본 동작이 되도록 설계(FR-09). Jev 모드는 관리자 토글. SC-3에서 두 모드를 분리 측정 |
| MySQL(잡·판정 기록)과 Neo4j(그래프) 이중 쓰기 불일치 | Medium | Medium | 그래프는 **다시 만들 수 있는 파생 데이터**로 정의: 문서 재추출로 복구. 판정 기록은 MySQL에 둔다. 정합성 점검 API 제공 |
| 재청킹·재색인 후 chunk_id가 바뀌어 근거가 끊김 | Medium | Medium | 재청킹하면 해당 문서 그래프를 삭제하고 잡을 다시 실행해야 하는 상태로 표시(M7). 정합성 점검으로 끊긴 근거 탐지 |
| 한국어 엔티티 이름 정규화 오류(조사·띄어쓰기) | Medium | Medium | Kiwi로 조사 제거·공백 정규화, 별칭은 원문을 보존하고 정규화 키는 별도 필드에 저장 |
| 그래프 결과가 RRF에서 기존 결과를 밀어내 오히려 품질 하락 | Medium | Medium | 그래프 입력 가중치를 설정으로 두고, RAGAS 비교(SC-4)를 통과하기 전에는 에이전트 기본값 off |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `graph_rag_setting` | DB (신규, V086 후보) | 전역 설정 단일 행 |
| `graph_extraction_job` | DB (신규) | 문서 단위 추출 잡 |
| `graph_resolution_decision` | DB (신규) | 판정 기록과 검토 상태 |
| Neo4j (`:Entity`, `:Chunk`, `MENTIONED_IN`, `RELATES`, `REFERS_TO`) | 외부 저장소 (신규) | 그래프 본체, 파생 데이터 |
| `UnifiedUploadUseCase` | Application | 완료 뒤 추출 잡 런처 호출(실패 무시) |
| 문서 삭제 유스케이스 | Application | 그래프 정리 호출 추가 |
| `HybridSearchUseCase` / `RRFFusionPolicy` | Application/Domain | 선택적 세 번째 입력 |
| `InternalDocumentSearchTool`, `RagToolConfig` | Application/Domain | `use_graph` 필드(기본 False) |
| `ai_retrieval_source.fusion_source` | DB 값 | `"graph"` 값 추가(스키마 변경 없음, Design에서 컬럼 타입 확인) |
| `src/config.py`, `src/api/main.py`, lifespan | Config/DI | `GRAPH_BACKEND`·`NEO4J_URI`(`bolt://` 또는 Aura `neo4j+s://`)·`NEO4J_USER`·`NEO4J_PASSWORD`·`NEO4J_DATABASE`, 드라이버 싱글턴, 종료 시 close. `.env.example`에 Aura 예시 추가 |
| `pyproject.toml` | 의존성 | `neo4j` 드라이버(선택 extra 후보) |
| `JudgmentPort` 소비 지점 | Infrastructure | 판정 어댑터 추가 → AST 경계 테스트 선언 |
| `idt_front` 관리자 라우트·사이드바 | Frontend | `AdminGraphRagPage`, types/services/hooks, `constants/api.ts` |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| UnifiedUploadUseCase | CREATE | `knowledge_base_router` → `KnowledgeBaseUploadUseCase` → `UnifiedUploadUseCase` | 런처 추가, 실패 무시. Needs verification(업로드 상태 불변 테스트) |
| UnifiedUploadUseCase | CREATE | 일반 컬렉션 업로드 경로(kb_id 없음) | kb_id 없는 문서는 추출 대상인지 Design에서 결정. Needs verification |
| HybridSearchUseCase | READ | `InternalDocumentSearchTool._arun`, routed_retrieval 보충(top-up), 리트리버 테스트 API | 세 번째 입력은 옵션이라 기본 경로 불변. Needs verification |
| RRFFusionPolicy | READ | hybrid_search, routed_retrieval(섹션 RRF) | 시그니처를 바꾸지 않고 확장. Needs verification |
| RagToolConfig | READ/UPDATE | tool_factory, 에이전트 정의 JSON 역직렬화, 빌더 저장 | 새 필드 기본값이 있어 구 정의도 로드 가능. Needs verification |
| ai_retrieval_source | CREATE/READ | `tracker.record_retrieval`, 근거 칩, 👎 드릴다운, 도구 실행 내역 | 새 fusion_source 값을 표시하는 프론트 분기 확인 |
| 문서 삭제 | DELETE | KB 문서 삭제 API, 컬렉션 문서 삭제 | 그래프 정리 추가(실패 시 로그, 삭제 자체는 성공) |
| JudgmentPort | READ | `search_decision/judgment_adapter.py`, `main.py` | 소비자 추가만 하고 기존 동작 불변 |
| RunAgentUseCase (`allow_graph` opt-in) | EXECUTE | WS `ws_router.py`, REST·SSE `agent_builder_router.py` | 호출 사용자가 admin이고 단계가 `admin_only` 이상일 때만 True를 넘김 |
| RunAgentUseCase | EXECUTE | 웹훅 `invoke_webhook_agent_use_case.py` | **opt-in을 넘기지 않음** — 소스 계약 테스트로 고정 |
| RunAgentUseCase | EXECUTE | 백그라운드 잡 `background_job/worker.py`, 스케줄, 승인 재개 `_resume_graph` | **opt-in을 넘기지 않음** — 소스 계약 테스트로 고정 |
| RunAgentUseCase | EXECUTE | RAGAS 실행 | 기본은 넘기지 않음. on/off 비교 실행(FR-19)만 관리자 요청으로 넘김 |
| RunAgentUseCase 테스트 픽스처 | TEST | `__new__`로 생성하는 픽스처(`test_identity_subject_wiring.py` 등) | 새 optional 속성에 맞춰 `uc._<attr> = None` 한 줄씩 보정 |
| 에이전트 저장 API | UPDATE | 빌더 저장, 위저드·자동 빌더 | 일반 사용자가 보낸 `use_graph=True` 처리 규칙(FR-20·M6-b) |

> Design 착수 시 `grep "run_uc\.\(execute\|stream\)\|use_case\.\(execute\|stream\)("`로 호출자 목록을 다시 뽑아 이 표와 대조한다(누락 방지).

### 6.3 Verification

- [ ] 위 소비 경로 전부 기존 테스트로 회귀 확인
- [ ] 권한 필터가 그래프 경로에도 같은 규칙(visibility·부서)으로 적용되는지 확인
- [ ] 구 에이전트 정의(`use_graph` 없음) 로드·실행 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter | ☐ |
| Dynamic | ☐ |
| **Enterprise** (DDD 레이어 분리·DI 집중·포트/어댑터) | ☑ |

### 7.2 Key Architectural Decisions

| # | Decision | Options | Selected | Rationale |
|---|----------|---------|----------|-----------|
| D1 | 그래프 저장소 | MySQL 테이블 / **Neo4j** / Qdrant payload | **Neo4j** (사용자 결정) | 여러 단계 탐색을 Cypher로 직접 표현. 포트로 분리해 테스트는 메모리 페이크 |
| D1-a | Neo4j 배치 | VM 자체 호스팅 / **Neo4j Aura(관리형)** | **개발·PoC는 Aura Free, 사내 도입은 자체 호스팅 또는 사내 승인 클라우드** (사용자 결정, v0.2) | Aura도 같은 Bolt 드라이버(`neo4j+s://`)를 쓰므로 `NEO4J_URI` 설정만 바꾸면 전환된다. 코드 분기를 두지 않는다. VM 메모리 부담이 없어지고, 외부 보관 문제는 도입 단계에서 저장 위치를 옮겨 해결한다 |
| D2 | 추출 방식 | 규칙 / LLM / **혼합** | **혼합** (사용자 결정) | 조문 참조는 규칙으로 비용 0에 정확. 개념·관계는 LLM |
| D3 | 같은 엔티티 판정 | LLM 자유응답 / **Jev ChoiceQuestion** | **Jev + 세 구간** (사용자 제안) | 확률을 직접 받아 기준값으로 자를 수 있고 판정 기록이 감사 가능 |
| D4 | 가운데 구간 | 검토 큐만 / 두 구간 / **LLM 재판정** | **LLM 재판정 + 사후 검토 큐** (사용자 결정) | 자동 처리 흐름을 유지하면서 사람이 나중에 바로잡을 수 있음 |
| D5 | Jev 불가 시 | 이름 일치만 / **LLM 선택** / 보류 | **LLM 선택** (사용자 결정) | Jev 실호출 미검증 상태에서도 기능이 동작 |
| D6 | 엔티티 공유 범위 | KB 내부 / 전역 | **전역 + `scope_key` 예비** (사용자 결정) | 지금은 `scope_key="global"`. 나중에 `kb:{id}`로 바꾸면 후보 검색·병합이 KB 안으로 좁혀짐. 권한은 청크 단위로 별도 보장 |
| D7 | 판정 토글 위치 | 환경변수 / **관리자 설정 DB** | **DB 단일 행** | 재기동 없이 관리자 페이지에서 on/off. `JUDGMENT_BACKEND`는 "Jev 사용 가능 여부", 설정 토글은 "Jev 사용 여부" |
| D8 | 잡 실행 방식 | 외부 큐 / **프로세스 내 `asyncio.create_task`** | **section_summary 선례** | 인프라 추가 없음. 재기동하면 잡이 끊기는 점은 재실행 버튼으로 보완 |
| D9 | 이름 임베딩 저장 | Neo4j 벡터 인덱스 / Qdrant 별도 컬렉션 | **Design에서 결정** | Neo4j 버전(5.11+) 벡터 인덱스를 쓰면 저장소가 하나로 줄어듦 |
| D11 | 모듈 결합 방식 | 코어에 직접 호출 / **훅 인터페이스 + 단일 조립 함수** | **훅 3개 + `register_graph_rag(app)`** (v0.3) | 테스트가 끝나면 끼워 넣고, 문제가 생기면 빼낼 수 있어야 한다. 코어는 no-op 기본 구현만 안다 |
| D12 | 노출 제어 | 에이전트 플래그만 / 역할 체크만 / **노출 단계 + 호출자 opt-in + 에이전트 플래그** | **3중 AND, 기본은 닫힘** (v0.3) | 에이전트 플래그만으로는 관리자가 배포한 에이전트가 일반 사용자에게 새어 나간다. 간접 신호(auth_ctx)는 웹훅 사고 선례가 있어 쓰지 않는다 |
| D10 | 그래프 검색 결합 | 별도 도구 / **RRF 세 번째 입력** | **RRF 입력** | 근거 칩·권한·기록 경로를 재사용하고, 결과가 결국 청크라서 "근거 없으면 답하지 않는다" 원칙을 유지 |

### 7.3 Clean Architecture Approach

```
코어 (graph_rag를 모름)                     graph_rag 모듈 (빼낼 수 있음)
─────────────────────────                  ─────────────────────────────
domain/hooks/                              register_graph_rag(app)  ← main.py 한 줄
  PostIngestHook          ◀── 구현 ──────   GraphExtractionLauncher
  DocumentDeletionHook    ◀── 구현 ──────   GraphCleanupHook
  SupplementalRetrievalSource ◀── 구현 ──   GraphRetrievalSource (단계·opt-in 확인)
UnifiedUploadUseCase  → hooks[] 호출       admin_graph_rag_router (require_role("admin"))
HybridSearchUseCase   → sources[] 합류     graph_rag capabilities 라우터
RunAgentUseCase(allow_graph=False)         
```

```
idt/src/
├── domain/hooks/                 # 코어 훅 인터페이스 3개 + no-op 기본 구현 (graph 용어 없음)
├── domain/graph/                 # Entity·Relation·Mention VO, GraphStorePort, ExtractorPort,
│                                 # ResolutionPolicy(세 구간), GraphRagSettings VO(값 검증 단일 출처)
├── application/graph_extraction/ # 런처, 잡 실행기, 판정 유스케이스(Jev→LLM 대체)
├── application/graph_retrieval/  # 엔티티 연결 → 탐색 → 권한 필터 → 청크 조회
├── application/graph_admin/      # 설정·엔티티 조회·검토 큐·검색 테스트
├── infrastructure/graph/neo4j/   # Neo4j 드라이버 어댑터 (neo4j import는 여기만)
├── infrastructure/graph/extract/ # 규칙 추출기, LLM 구조화 추출기
├── api/routes/admin_graph_rag_router.py
└── api/graph_rag_module.py       # register_graph_rag(app): DI·훅 등록·라우터 include 단일 지점

idt_front/src/
├── pages/AdminGraphRagPage/      # 5개 탭
├── types/graphRag.ts · services/graphRagService.ts · hooks/useGraphRag*.ts
└── constants/api.ts              # 엔드포인트 상수
```

Neo4j 모델(초안, Design에서 확정):

```
(:Entity {id, scope_key, name, normalized_name, type, aliases[], description})
(:Chunk  {chunk_id, document_id, kb_id, collection_name})
(:Entity)-[:MENTIONED_IN {decision_id}]->(:Chunk)
(:Entity)-[:RELATES {type, evidence_chunk_id, document_id, kb_id, confidence}]->(:Entity)
(:Entity {type:'조문'})-[:REFERS_TO {evidence_chunk_id}]->(:Entity {type:'조문'})
```

---

## 8. Convention Prerequisites

- 백엔드: `idt/CLAUDE.md`
  - TDD 필수, domain에서 외부 의존 금지.
  - 부모·자식 청크 구조는 바꾸지 않는다(그래프는 기존 chunk_id를 참조만 한다).
  - DB 스키마 변경은 승인이 필요하다. V086~ 마이그레이션은 Design 단계에서 승인받는다.
- Flyway: COMMENT 필수, COMMENT 안 콤마 금지, CHARSET 명시 금지(`docs/wiki/backend/db/mysql-fk-collation.md`). FK 없이 소프트 참조(V065 선례).
- 무거운 클라이언트는 앱 수명 싱글턴(Neo4j 드라이버, `app-lifetime-client-singleton`).
- 프론트: `idt_front/CLAUDE.md`. 런타임 상수는 컴포넌트 파일에서 export하지 않는다. ApiError 인터셉터 경로를 따르고, 테스트는 MSW로 한다.
- API 계약 동기화: `/api-contract-sync`.
- 작업 공간: `/git-workflow`로 worktree `wt/graph-rag-foundation`을 만든다.

---

## 9. Next Steps

1. [ ] `/pdca design graph-rag-foundation`에서 정할 것
   - 3개 설계안 비교
   - D9(이름 임베딩 저장 위치)
   - Neo4j 스키마와 인덱스
   - 테이블 DDL(승인 대상)
   - 엔티티 연결 알고리즘
   - RRF 가중치
   - kb_id 없는 컬렉션 문서의 추출 대상 여부
2. [ ] Design 승인 → worktree 생성 → `/pdca do --scope module-N` 순서로 **M0**→M1→M2→M3→M4→M6→M6-b→M7→M5→M8→M9 진행 (M0의 훅·노출 단계·opt-in을 먼저 만들어, 이후 모듈이 처음부터 경계 안에서 개발되게 한다)
3. [ ] Jev 실호출 스모크 테스트(judgment-backend 이월분)를 SC-3 측정 전에 실행할 수 있는지 확인
4. [ ] Aura Free 인스턴스 생성(리전 선택, 접속 정보는 `idt/.env`에만 두고 커밋 금지), 현재 한도 수치를 가격 페이지에서 확인
5. [ ] Design에서 Aura 지원 기능 확인: 벡터 인덱스(D9 후보), Neo4j 버전, 단일 데이터베이스 제약

### 확인이 필요한 가정 (Design 전에 검토)

- "기존에 있던 주제"는 **이미 그래프에 있는 엔티티**로 해석했다. 별도 주제 분류(토픽 태그)를 뜻했다면 M4에 "타입·주제 분류 ChoiceQuestion"을 추가한다.
- 검토 큐는 "LLM이 가운데 구간을 판정한 건"을 사후에 검토하는 용도로 해석했다(판정이 끝날 때까지 막아두는 대기 큐가 아님).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-16 | 초안 — 질의 유형(다문서·별칭), Neo4j, 혼합 추출, Jev 세 구간+LLM 재판정·대체, 전역 공유+scope_key, 관리자 테스트 페이지 5탭 반영 | 배상규 |
| 0.2 | 2026-11-16 | Neo4j 배치 결정(D1-a): 개발·PoC는 Aura Free, 사내 도입은 자체 호스팅. Aura 제약·외부 보관·지연 위험, 용량·이식성 NFR, 설정 키, 다음 단계 추가 | 배상규 |
| 0.3 | 2026-11-16 | 관리자 전용 테스트 후 끼워 넣기 요구 반영: M0 모듈 경계(훅 3개·단일 조립)와 노출 단계(off/admin_only/general), 호출자 opt-in 3중 AND(FR-20~24), 관리자 전용 빌더 토글(M6-b), SC-8·SC-9, 호출자 전수 표, D11·D12 | 배상규 |
| 0.4 | 2026-11-17 | 주제 분류 요구 추가(FR-25~29): 문서 주제 자동 분류(Jev 세 구간·LLM 대체), 2단계 주제, 대표 1+보조 2, 관리자 기본 목록+자동 추가·검토, 질문 주제로 검색 범위 좁히기(Jev → LLM). DDL V090·V091 승인 | 배상규 |
| 0.5 | 2026-11-18 | Check 결정: FR-21 미적용 사유 기록 위치를 "실행 기록"에서 "구조화 로그"로 변경(코어 실행 기록 구조 변경 없음) | 배상규 |
