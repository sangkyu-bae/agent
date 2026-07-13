# Completion Report: retrieval-observability

> **Feature**: 질문별 검색 근거(뽑힌 문서) 기록 — general_chat 배선 + rewrite 쿼리 추적 + 스키마 확장 + 조회 API
> **Period**: 2026-07-09 ~ 2026-07-10
> **Status**: Completed (Match Rate 100%)
> **Docs**: [Plan](../01-plan/features/retrieval-observability.plan.md) · [Design](../02-design/features/retrieval-observability.design.md) · [Analysis](../03-analysis/retrieval-observability.analysis.md)

---

## 1. Executive Summary

### 1.1 개요

| 항목 | 내용 |
|------|------|
| Feature | retrieval-observability |
| 시작 | 2026-07-09 (Plan) |
| 완료 | 2026-07-10 (Check 100%) |
| PDCA 사이클 | Plan → Design → Do → Check, iterate 0회 (일발 통과) |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| Match Rate | **100%** (41/41 — D1~D9 결정 9 + 컴포넌트 32) |
| 신규 테스트 | 5개 파일, 40+ 케이스 (전부 통과) |
| 회귀 | tests/domain + tests/application **3,628개 통과**, 기존 agent_run 경로 무손상 |
| 프로덕션 변경 | 15개 파일 (신규 2: 마이그레이션 V046, 조회 UseCase) |
| 스키마 변경 | ALTER 1건 — nullable 컬럼 8개 additive (기존 데이터 무해) |
| Act(iterate) | 0회 — 차단성 갭 없음, advisory 1건(타입 힌트) 즉시 반영 |

### 1.3 Value Delivered

| 관점 | 전달된 가치 |
|------|------------|
| **Problem** | general_chat 검색이 관측성 사각지대였고(tracker 미주입), rewrite 재작성 쿼리는 어디에도 남지 않았으며, 통합 score 하나만 있어 검색 품질 분석이 불가능했다. |
| **Solution** | 기존 `ai_retrieval_source`/`RunTracker` 인프라를 general_chat에 배선(ai_run 생성 + deferred attach)하고, hit 단위로 검색 실행 쿼리·모드·BM25/벡터 개별 점수를 기록(V046), 메시지 기준 조회 API를 신설했다. 신규 테이블 0개 — 전부 기존 인프라 확장. |
| **Function UX Effect** | `GET /api/v1/conversations/messages/{id}/retrievals` 한 번으로 "이 질문 → 어떤 재작성 쿼리 → 어떤 문서(개별 점수 포함)" 전체 체인 조회. LangSmith run URL 연결로 트레이스 점프 가능. general_chat LLM 비용도 `ai_llm_call`에 기록되기 시작(부수 이득). |
| **Core Value** | RAG 파이프라인의 마지막 블랙박스(검색 단계)가 데이터화되어 vector threshold·RRF·rewrite 프롬프트 튜닝의 근거 데이터를 확보. 답변 품질 이슈의 검색 단계 원인 분석이 즉시 가능. |

---

## 2. 구현 내역

### 2.1 데이터 (V046)

`ai_retrieval_source`에 nullable 컬럼 8개 추가: `search_query`, `query_source`(original|multi_query),
`search_mode`(hybrid|bm25_only|vector_only|routed), `bm25_score`, `vector_score`, `bm25_rank`,
`vector_rank`, `fusion_source`. 도메인 엔티티/ORM/매퍼 왕복 반영. FK·인덱스 추가 없음(collation 이슈 원천 회피).

### 2.2 기록 경로

- **RunTracker**: `record_retrieval` 확장 kwargs(전부 optional — 하위호환) + `attach_user_message`(D2 deferred, best-effort)
- **Tool** (`InternalDocumentSearchTool`): 3개 검색 경로 모두 기록 컨텍스트 전달
  - 단일: `search_query`=tool 입력, 개별 점수는 `HybridSearchResult` 기존 필드에서 전달(버려지던 값)
  - multi_query: `MultiQueryResult.per_query_hits` 신설 → fused hit별 기여 쿼리 태깅(`search_query`=첫 기여 쿼리, `metadata.matched_queries`=전체)
  - routed: `search_mode=routed`, 개별 점수 NULL(점수 스케일 혼합 금지 유지)
- **general_chat**: `_begin_observability`(chart-edit 분기 이후 run open, 실패 시 degraded 진행) →
  `UsageCallback` config 부착 → 메시지 저장 후 `attach_user_message` → `complete_run`(LangSmith trace) / 예외 시 `fail_run`

### 2.3 DI & 조회

- `get_run_tracker()` lazy singleton — agent_builder·general_chat(HTTP/WS 공용) 동일 인스턴스
- `GET /api/v1/conversations/messages/{message_id}/retrievals` — 소유 검증(본인/admin, 404/403) → run별 → 재작성 쿼리별 그룹 응답
- `RunDetailResponse` retrievals에도 신규 8필드 반영

### 2.4 변경 파일

| 구분 | 파일 |
|------|------|
| 신규 | `db/migration/V046__alter_ai_retrieval_source_add_query_context.sql`, `src/application/agent_run/use_cases/get_message_retrievals_use_case.py` |
| 수정 (domain) | `agent_run/entities.py`, `agent_run/interfaces.py`, `multi_query/schemas.py` |
| 수정 (application) | `agent_run/tracker.py`, `agent_run/exceptions.py`, `multi_query/use_case.py`, `rag_agent/tools.py`, `general_chat/use_case.py` |
| 수정 (infrastructure) | `persistence/models/agent_run.py`, `persistence/repositories/agent_run_repository.py` |
| 수정 (interfaces/api) | `schemas/agent_run_response.py`, `routes/agent_run_router.py`, `api/main.py` |
| 테스트 (신규 5) | `test_tracker_retrieval_context.py`, `test_per_query_hits.py`, `test_tool_retrieval_context.py`, `test_observability.py`, `test_message_retrievals_api.py` |

---

## 3. 품질 검증

| 검증 | 결과 |
|------|------|
| TDD | 전 단계 Red → Green (테스트 선작성 후 구현) |
| 신규 테스트 | 40+ 케이스 통과 |
| 회귀 | tests/domain + tests/application 3,628개 통과 (변경 전 기준선 대비 신규 실패 0) |
| Gap 분석 | Match Rate 100% (gap-detector, 41항목) |
| 아키텍처 | 레이어 규칙·Repository commit 금지·best-effort 계약·additive 하위호환·대화 메모리 정책 불변 — 전부 Pass |
| 알려진 환경 이슈 | tests/api 간헐 소켓 에러(WinError 10014)는 stash 기준선에서도 동일 재현 — 기존 환경 이슈 |

---

## 4. 배포 체크리스트 & 후속 과제

**배포 전**
- [ ] DB에 V046 마이그레이션 적용 (nullable ADD COLUMN — 무중단 안전)
- [ ] `LANGSMITH_TRACING` 설정 확인 (trace URL 연결은 tracing 활성 시에만)

**후속 과제 (Out of Scope 확정분)**
- collection_search / wiki-first / hybrid 직접 API 경로 배선
- 프론트엔드 메시지별 검색 근거 표시 UI (+ `/api-contract-sync` 타입 동기화)
- 검색 품질 분석 대시보드 / `ai_retrieval_source` 보존 정책

---

## 5. Lessons Learned

1. **"신규 구축"처럼 보이는 요구가 실제로는 배선 갭**: agent-run-observability(2026-05)가 이미 테이블·트래커를 구축해둔 상태 — Plan 전 현황 조사가 범위를 "새 시스템"에서 "확장 4종"으로 축소시켰다.
2. **deferred attach 패턴**: 저장 순서가 다른 두 경로(agent: 선저장 / general_chat: 후저장)를 FK로 잇는 문제는 NULL→UPDATE 지연 연결로 해결 — 대화 메모리 정책 불변 + FK 락 경합(Error 1205) 원천 회피를 동시에 달성.
3. **버려지던 데이터의 회수**: BM25/벡터 개별 점수(`HybridSearchResult`)와 재작성 쿼리별 hit(`per_query_results` state)은 이미 계산되고 있었으나 반환 경계에서 유실 — 관측성 작업의 상당 부분은 "새 계산"이 아니라 "기존 값의 전달 경로 확보"였다.
