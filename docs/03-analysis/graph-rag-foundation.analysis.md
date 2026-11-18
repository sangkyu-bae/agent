# graph-rag-foundation Gap Analysis (Check)

> **Feature**: graph-rag-foundation
> **Date**: 2026-11-18
> **Plan**: v0.4 · **Design**: v0.12 · **Branch**: `feature/graph-rag-foundation` (`be8440b`)
> **방식**: 정적 분석(gap-detector) + 핵심 발견 직접 재확인. 런타임 검증(L1~L3 실서버)은 실행하지 못했다. 이 PC에서 Windows Smart App Control이 kiwipiepy·asyncmy DLL을 막아 백엔드가 기동되지 않는다.

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 여러 문서에 걸친 관계·용어 별칭을 하이브리드 검색이 따라가지 못한다. GraphRAG를 받을 저장소·추출·판정·검색 경로가 없었다 |
| **WHO** | 1차: P3 관리자(테스트 페이지에서 추출·판정·검색 검증). 최종 수혜: P1 심사역·P4 행원(근거 회수 향상), P2 KB 운영자(후속 사이클) |
| **RISK** | 잘못된 엔티티 병합 / 권한 없는 KB 근거 노출 / Aura 외부 보관(PoC 한정) / LLM 비용 / 비대화 경로로 그래프 노출 |
| **SUCCESS** | off에서 기존 동작 동일 · 근거 역추적 실패 0 · RAGAS context_recall 향상 · 관리자 화면만으로 완주 · admin_only에서 일반 사용자 실행 0 · 모듈 제거 가능 |
| **SCOPE** | 독립 모듈 + 노출 단계 off → admin_only(이번 사이클). 관리자 테스트 페이지와 관리자 전용 빌더 토글 |

## 1. 점수

| 축 | 점수 | 근거 |
|----|:----:|------|
| Structural | 97% | §4.1 엔드포인트 16개가 모두 있고 관리자 가드가 있다. 주제 API 3개는 추가분(M6-1). §5.3 컴포넌트와 주제 탭이 있다. V086~V091은 모든 컬럼에 COMMENT가 있다 |
| Functional | 93% | FR 29개 중 ✅ 26, ⚠️ 3(FR-19·21·29) |
| Contract | 95% | 백엔드 스키마와 프론트 타입은 불일치 0이다. Design §4.2 예시 문서가 코드보다 뒤처져 있다(§4) |
| **Overall (정적)** | **94.6%** | 0.2·S + 0.4·F + 0.4·C. 런타임 축 미포함 |

## 2. 전략 정합성

- 핵심 문제(다문서 관계·별칭 검색)를 다루는 경로가 모두 들어갔다: 추출 → 판정 → 주제 → 그래프 검색 → 결합.
- Design의 핵심 결정은 지켜졌다.
  - Option C: 코어는 훅과 grant만 알고, `graph_rag`를 import하지 않는다(계약 테스트 C1).
  - 3중 AND 게이트(FR-20).
  - 청크 단위 권한 재조회(FR-12).
- 효과 증명(SC-3·SC-4)은 측정하지 못했다. 사이클의 "왜"를 숫자로 보이는 일이 남았다.

## 3. Success Criteria

| SC | 상태 | 근거 |
|----|:----:|------|
| SC-1 off에서 회귀 0 | ✅ | 같은 환경 기준 새 실패 0. 백엔드 12,287건 통과, 실패 목록은 HEAD와 같다. 프론트 실패 9건은 master와 같다 |
| SC-2 근거 역추적 실패 0 | ✅ | `/integrity`로 실데이터를 확인했고 누락 0이다(M5-11). `test_admin_inspect_use_cases.py` |
| SC-3 별칭 정밀도 ≥ 0.9 | ❌ 이월 | 판정 사례가 있는 문서 추출과 라벨 작업이 필요하다(§11.12) |
| SC-4 RAGAS 끔/켬 | ❌ 이월 | 실행 경로는 구현했다(M7-1). 실행은 환경 복구 후에 한다 |
| SC-5 관리자 화면 완주 | ⚠️ | 화면 흐름은 다 있다(Vitest 22건). 브라우저 확인은 못 했다 |
| SC-6 Neo4j 중지 시 정상 응답 | ⚠️ | 코드 경로와 테스트는 있다(`test_supplemental_fusion.py`, `test_graph_rag_wiring.py`). 실제로 Neo4j를 멈춰 보지는 못했다 |
| SC-7 권한 없는 청크 노출 0 | ✅ | `test_graph_retrieval_source.py`, `test_es_evidence_fetcher.py` |
| SC-8 일반 사용자 경로 실행 0 | ✅ | `tests/contracts/test_extension_boundaries.py` C2·C3·C3b·C4 |
| SC-9 모듈 제거 가능 | ⚠️ | AST 경계 테스트는 통과한다. 등록 줄을 주석 처리하고 기동해 보지는 못했다 |

**충족 4/9, 부분 3, 이월 2.** 부분 3건(SC-5·6·9)은 실행 환경만 있으면 확인할 수 있는 항목이다.

## 4. 발견 사항

### Important (확신도 ≥ 80, 재확인 완료)

| # | 위치 | 내용 | 선택지 |
|---|------|------|--------|
| G-1 | `idt/src/application/rag_agent/tools.py:219` | FR-21은 "미적용 사유를 실행 기록에 남긴다"이다. 그런데 사유(`grant_not_admin`·`stage_off` 등)는 구조화 로그(request_id)에만 남는다 | (a) 실행 기록(tracker·run metadata)에 남기도록 코어를 수정 / (b) Plan FR-21을 "구조화 로그"로 고치고 §11.x에 결정을 기록 |
| G-2 | `idt/src/application/graph_rag/admin/review_use_case.py`, `topics_use_case.py` | Design §4는 "stage=off이면 설정·health 외에는 409"이다. 검토 승인·거절과 주제 API에는 단계 검사가 없다. 승인·거절은 그래프를 바꾼다. 추출·엔티티·search-test·integrity는 검사한다. 화면은 off일 때 탭을 막으므로 API를 직접 부를 때만 열린다 | (a) review·topics 유스케이스에 `ensure_stage_on`을 추가 / (b) 허용 범위를 §11.x에 기록 |

Critical은 없다.

### Minor

- M-1: 문서를 지워도 `graph_resolution_decision` 행이 남는다. 그래서 지운 문서의 판정이 검토 큐에 남고, 이미 없는 엔티티에 대해 승인·거절을 시도할 수 있다(확신도 75).
- M-2: `DELETE_ORPHAN_ENTITIES`는 문서를 지울 때마다 Entity 전체를 훑는다. 그래프가 커지면 느려질 수 있다.
- M-3: `GRAPH_BACKEND=off`여도 Kiwi·임베딩·ES 객체를 기동 시점에 만든다. 코어도 같은 의존성을 쓰므로 실제 위험은 낮다.
- M-4: Design §4.2 search-test 예시가 코드와 다르다.
  - 문서의 `fusion_source`는 코드에서 `source`다.
  - 문서의 `paths[].chunk_id`는 코드에서 `evidence_chunk_ids`다.
  - 코드에만 있는 필드: `scope`, `skip_reason`, `hybrid_error`, 요청의 `collection_name`.
  - 문서 갱신만 필요하다.
- M-5: Design §6.1에 없는 오류 코드가 추가됐다: `GRAPH_UNSUPPORTED_DOCUMENT`, `GRAPH_REVIEW_NOT_FOUND`, `GRAPH_TOPIC_*`, `JOB_NOT_FOUND`, `GRAPH_ENTITY_NOT_FOUND`. 문서에 추가하면 된다.

## 5. FR 요약

| FR | 상태 | FR | 상태 | FR | 상태 |
|----|:----:|----|:----:|----|:----:|
| 01 | ✅ | 11 | ✅ | 21 | ⚠️ G-1 |
| 02 | ✅ | 12 | ✅ | 22 | ✅ |
| 03 | ✅ | 13 | ✅ | 23 | ✅ |
| 04 | ✅ | 14 | ✅ | 24 | ✅ |
| 05 | ✅ | 15 | ✅ | 25 | ✅ |
| 06 | ✅ | 16 | ✅ | 26 | ✅ |
| 07 | ✅ | 17 | ✅ (6탭, M6-1) | 27 | ✅ |
| 08 | ✅ | 18 | ✅ | 28 | ✅ |
| 09 | ✅ | 19 | ⚠️ 실측 이월 | 29 | ⚠️ 앱 실런 이월 |
| 10 | ✅ | 20 | ✅ | | |

## 6. 이월 (환경 복구 후)

1. 백엔드 기동 → SC-5·6·9 실확인, 질문 주제 판정 실데이터(FR-29)
2. SC-4: 같은 에이전트·테스트셋으로 RAGAS 끔/켬 → general 전환 근거 확인
3. SC-3: 27청크 문서 추출(LLM 수십 회, 사용자 승인 필요) → 별칭 라벨 30쌍 → 정밀도
4. 튜닝: `MIN_VECTOR_SIMILARITY`, `HUB_DEGREE_LIMIT`, parent/child 겹침(M5-8)

## 7. Act 결과 (2026-11-18, 사용자 결정: G-2·M-1 코드 수정, G-1 결정 기록)

| 발견 | 처리 | 근거 |
|------|------|------|
| G-1 | Plan FR-21 문구를 "구조화 로그"로 고쳤다(Plan v0.5). Design §11.13 C-1에 기록 | 코어 실행 기록 구조는 바꾸지 않는다 |
| G-2 | 검토·주제 API도 단계가 off이면 409 `GRAPH_STAGE_OFF`를 낸다 | `test_review_use_case.py::test_stage_off_blocks_review_actions`, `test_topics_use_case.py::test_stage_off_blocks_topic_api`, `test_admin_graph_rag_topics_router.py::test_stage_off_list_endpoints_return_409` |
| M-1 | 문서를 지우면 그 문서의 판정 기록도 지운다 | `test_decision_store.py::test_delete_for_document_removes_only_that_document`, `test_launcher_and_hook.py::test_deletion_hook_removes_decisions_of_document` |
| M-4·M-5 | Design §11.13 C-4에 코드 기준 응답·오류 코드를 기록했다 | — |

수정 후 FR-21은 ✅(결정 반영)로 바뀌고, Functional은 FR 29개 중 ✅ 27·⚠️ 2(FR-19·29, 실측 이월)이다.

| 축 | Check | Act 후 |
|----|:-----:|:------:|
| Structural | 97% | 97% |
| Functional | 93% | 95% |
| Contract | 95% | 97% (Design 문서 동기화) |
| **Overall (정적)** | **94.6%** | **96.2%** |
