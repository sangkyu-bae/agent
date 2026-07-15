# kb-content-browser Gap Analysis

> Date: 2026-07-14 · Feature: kb-content-browser
> Design: `docs/02-design/features/kb-content-browser.design.md` · Plan: `docs/01-plan/features/kb-content-browser.plan.md`
> Scope: 백엔드(`idt/`) + 프론트(`idt_front/`) 풀스택
> Analyzer: gap-detector agent

## 1. Match Rate 요약

**전체 Match Rate: 97.4%** (Match 37 + Partial 2×0.5 = 38.0 / 대조 39항목, Deferred 1건 제외)

| 카테고리 | 대조 | Match | Partial | Missing | Changed | Deferred | % |
|----------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 결정사항 D1~D9 | 9 | 9 | 0 | 0 | 0 | 0 | 100% |
| 백엔드 설계 §4 | 10 | 9 | 1 | 0 | 0 | 0 | 95% |
| 프론트 설계 §5 | 10 | 9 | 1 | 0 | 0 | 0 | 95% |
| 테스트 §6 | 2 | 2 | 0 | 0 | 0 | 0 | 100% |
| 수용 기준 §8 | 8(+1) | 8 | 0 | 0 | 0 | 1 | 100% |
| **합계** | **39** | **37** | **2** | **0** | **0** | **1** | **97.4%** |

- Partial 2건은 모두 기능 동등(계약 무영향). Deferred 1건은 `kb-pipeline-e2e-pending` ⑤로 이월된 브라우저 실측 — Missing 아님.

## 2. 결정사항(D1~D9) 대조표

| ID | 결정 요지 | 상태 | 근거 |
|----|-----------|:---:|------|
| D1 | KB 라우터 하위 신규 3종, 기존 무변경 | Match | `knowledge_base_router.py:564,601,645`; `get_chunks_use_case.py:33-38` 시그니처 보존 |
| D2 | 전 API `source`(기본 qdrant) + 프론트 토글 | Match | `knowledge_base_router.py:551,576,613,658`; `KbDocumentContentPanel.tsx:110,134-155` |
| D3 | q 검색 ES=match/Qdrant=contains, search_mode | Match | `get_kb_document_chunks_use_case.py:36,66-81,125-151`; `KbChunkList.tsx:18-21,156-160` |
| D4 | 공통 가드 404/403 + kb_id 일치, collection_name·filename | Match | `content_browse_guard.py:40-67` |
| D5 | summary_text 정규화 + payload를 metadata dict 노출 | Match | `browse_sources.py:37-56`; `KbPayloadMeta.tsx` |
| D6 | 요약 미생성 시 `{exists:false}` | Match | `get_kb_document_summary_use_case.py:67-71`; `KbDocumentContentPanel.tsx:68-74` |
| D7 | Qdrant scroll 직접 + chunk_type 필터, 청크는 요약 제외 | Match | `browse_sources.py:59-83`; `chunk_assembler.py:36-40` |
| D8 | 서버 페이지네이션 없이 전량 반환, 프론트 client 페이징 | Match | `browse_sources.py:21,115`; `KbChunkList.tsx:15,139-143` |
| D9 | 잡 상태 프론트 연동, running 5초 폴링, 완료 refetch | Match | `useKnowledgeBases.ts:128-168` |

## 3. 백엔드 설계 대조 (§4)

| # | 항목 | 상태 | 근거 |
|---|------|:---:|------|
| B1 | 3 엔드포인트 URL/메서드 | Match | `knowledge_base_router.py:564,601,645` |
| B2 | 응답 스키마 필드 | Match | `:197-237` |
| B3 | `source` 검증 = `Literal[...]` (§4.3) | **Partial** | 구현은 `Query(pattern="^(qdrant\|es)$")` `:551,576` — 422 동작 동일, 타입 표현만 상이 |
| B4 | chunk_assembler 추출 + GetChunksUseCase 위임(무변경) | Match | `chunk_assembler.py:29-153`; `get_chunks_use_case.py:46-53` |
| B5 | UseCase 3종 동일 의존성 | Match | summary:33 / sections:37 / chunks:39 |
| B6 | KbDocumentGuard 404/403 + kb_id NULL/불일치 | Match | `content_browse_guard.py:40-67` |
| B7 | Qdrant scroll / ES bool filter + ES `_id`→chunk_id | Match | `browse_sources.py:59-125` |
| B8 | 결과 dataclass `domain/knowledge_base/browse_schemas.py` | Match | `browse_schemas.py:11-55` |
| B9 | DI `create_kb_browse_factories` + overrides 3건 | Match | `main.py:2750-2823`, `:3812-3820` |
| B10 | 무변경 명시(doc_browse/파이프라인/스키마) | Match | GetChunksUseCase 응답 동일, payload index 생성 코드 부재 유지 |

소스별 로직(§4.2 표): 문서요약·섹션요약·청크 3계층 모두 Qdrant filter / ES term+must_not 구성이 설계와 일치, parent 매칭 시 children 전체 유지(`_filter_groups:153-180`)까지 Match.

## 4. 프론트 설계 대조 (§5)

| # | 항목 | 상태 | 근거 |
|---|------|:---:|------|
| C1 | 타입 전종 | **Partial** | `knowledgeBase.ts:80-155` 전부 존재하나, §5.1의 `types/collection.ts` 재사용 import 대신 로컬 `KbBrowseChunkDetail/ParentGroup` 신규(`:82-96`) |
| C2 | 상수 5종 | Match | `constants/api.ts:99-108` |
| C3 | 서비스 5종 | Match | `knowledgeBaseService.ts:86-140` |
| C4 | 훅 5종 | Match | `useKnowledgeBases.ts:66-168` |
| C5 | queryKeys 4종 | Match | `queryKeys.ts:106-113` |
| C6 | KbDocumentContentPanel(토글·3탭·exists=false·메타) | Match | `KbDocumentContentPanel.tsx:105-204` |
| C7 | KbSectionSummaryList(진행률·재시도·목록) | Match | `KbSectionSummaryList.tsx:21-140` |
| C8 | KbChunkList(debounce·include_parent·계층·힌트·페이징) | Match | `KbChunkList.tsx:73-218` |
| C9 | KbDocumentTable(onRowClick/selectedId) | Match | `KbDocumentTable.tsx:9-10,73-76` |
| C10 | Page selectedDoc 연결(재클릭 닫기) | Match | `KnowledgeBaseDetailPage/index.tsx:18,90-104` |

## 5. 테스트 목록 대조 (§6)

백엔드 6종(`test_chunk_assembler`, `test_kb_document_guard`, `test_get_kb_document_summary_use_case`, `test_list_kb_section_summaries_use_case`, `test_get_kb_document_chunks_use_case`, `tests/api/test_knowledge_base_browse_router`) 전부 존재 — Match. 프론트 4종(`KbChunkList/KbSectionSummaryList/KbDocumentContentPanel/KbDocumentTable.test.tsx`) 존재 — Match.

실측 결과(Do 단계, 2026-07-14): 백엔드 신규+회귀 69건 통과(간헐 WinError 10014 환경 이슈는 지정 재실행으로 전건 통과 확인), 프론트 신규 20건 + 기존 KB 3건 통과, `tsc --noEmit` 오류 없음.

## 6. Gap 상세

**Partial (기능 동등):**
- **P1 (B3)** `knowledge_base_router.py:551` — 설계 `Literal["qdrant","es"]` vs 구현 정규식 `pattern`. 영향 낮음(422 동일). → **문서 갱신 권장**(Code is truth).
- **P2 (C1)** `knowledgeBase.ts:82-96` — 설계 collection 타입 재사용 vs 로컬 신규 타입. 영향 낮음(필드 동일, 타입 2벌). → **의도적 분리로 기록** (KB 응답은 `chunk_type: string`·`metadata: Record<string,string>`로 collection 타입과 계약이 미세하게 달라 분리가 타당) 또는 후속 통합.

**Missing / Changed: 없음.** 설계 명시 파일·엔드포인트·UseCase·컴포넌트·테스트 전부 존재, 계약 필드 일치.

**Deferred:** DF1 = §8 저장소 토글 브라우저 실측(ES/Qdrant 미기동) → `kb-pipeline-e2e-pending` ⑤(V047 선행). Missing 아님.

## 7. Added (설계 외 구현)

| # | 항목 | 평가 |
|---|------|------|
| A1 | `KbPayloadMeta.tsx` 독립 컴포넌트(설계는 inline MetadataToggle) | 3뷰 공유 재사용 승격 — 긍정적 |
| A2 | `browse_sources.py` 소스 헬퍼 모듈(설계는 UseCase private) | 3 UseCase DRY 강화 |
| A3 | `KbDocumentContext.chunk_strategy` 추가 필드 | filename 폴백 활용 — 경미한 확장 |
| A4 | 요약 본문 다중 키 폴백(summary_text/summary/content) | ES/Qdrant 필드차 흡수 — 견고성 |

## 8. 결론 및 권고

- **97.4%** — 정합 매우 양호. D1~D9 전부 구현, 무변경 계약(GetChunksUseCase 시그니처·doc_browse 라우터·요약 파이프라인) 준수, CLAUDE.md 규칙 부합(라우터 위임만, domain의 infra 참조 없음).
- Missing/Changed 0건. 차이는 Partial 2건(기능 동등)·Added 4건(품질 개선)뿐.
- 권고: ① 설계 §4.3을 `pattern` 방식으로 갱신, ② P2 분리를 의도 기록, ③ Qdrant/ES 기동 시 E2E ⑤ 실측, ④ pytest/vitest 실측 통과 확인(완료 — §5 참조).
- **PDCA 판정: Match Rate ≥ 90% → Act(iterate) 불필요.** `/pdca report kb-content-browser` 진행 권장 (DF1은 E2E 체크리스트에서 별도 추적).
