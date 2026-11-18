# graph-rag-foundation Completion Report

> **Status**: Partial. 구현과 Check는 끝났다. 효과 측정(SC-3·SC-4)과 실서버 확인(SC-5·6·9)이 남았다.
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Completion Date**: 2026-11-18
> **Branch**: `feature/graph-rag-foundation` (`790b886`, 커밋 16개, push 전)
> **PDCA Cycle**: Plan v0.5 · Design v0.13 · Check 96.2%(정적)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | graph-rag-foundation: 문서 용어·관계 그래프를 만들고, 그 그래프로 기존 RAG 검색에 근거를 보탠다 |
| Start Date | 2026-11-16 (Plan) |
| End Date | 2026-11-18 (Check·Act) |
| Duration | 3일, module-1~7 + module-4b·5c |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────────┐
│  기능 요구사항(FR 29개)                            │
│  ✅ 완료:            27 / 29                      │
│  ⚠️ 구현 완료·실측 이월: 2 / 29  (FR-19, FR-29)   │
│  ❌ 취소:             0 / 29                      │
├──────────────────────────────────────────────────┤
│  성공 기준(SC 9개)                                 │
│  ✅ 4  ·  ⚠️ 실서버 확인 대기 3  ·  ⏳ 측정 이월 2   │
└──────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 하이브리드 검색(BM25+벡터)은 여러 문서에 걸친 관계와 용어 별칭을 따라가지 못한다. GraphRAG를 받을 저장소·추출·판정·검색 경로도 없었다 |
| **Solution** | 코어에는 확장 훅과 실행별 허용값만 추가했다. 그래프 RAG는 `wire_graph_rag()` 한 줄로 연결되는 독립 모듈로 만들었다. 이 모듈은 업로드 뒤 추출 잡으로 엔티티·관계를 Neo4j에 저장한다. 같은 엔티티인지는 Jev와 LLM이 세 구간으로 판정하고, 문서 주제를 자동으로 분류한다. 검색할 때는 질문 주제로 범위를 좁혀 탐색하고, 결과를 도구의 기존 결과와 RRF로 합친다 |
| **Function/UX Effect** | 관리자는 `/admin/graph-rag`의 6개 탭에서 설정·추출·엔티티·주제·검색 비교·검토를 모두 처리한다. 실데이터 2문서에서 "운전자금대출"은 여신관리 범위의 경로 5개를, "회의실"은 총무 범위의 근거만 찾았다. 그래프 검색 지연은 1.7~3.4초로 측정됐고, 이 중 대부분은 질문 주제 판정(LLM)에 걸린다 |
| **Core Value** | 일반 사용자에게는 아무것도 바뀌지 않는다. 관리자 테스트 단계(`admin_only`)에서는 관리자 대화에서만 그래프를 실행한다. 모듈을 빼도 코어가 동작한다. 그래서 효과를 측정한 뒤에 공개 범위를 넓힐 수 있다 |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | `GRAPH_BACKEND=off`에서 전체 테스트 결과가 master와 같다 | ✅ Met | 같은 환경 기준 새 실패 0. 백엔드 12,292건 통과, 실패 목록이 HEAD와 일치. 프론트 실패 9건은 master와 같다 |
| SC-2 | 관계·언급 근거 역추적 실패 0건 | ✅ Met | `/integrity` 실데이터 누락 0(M5-11), `test_admin_inspect_use_cases.py` |
| SC-3 | 별칭 라벨셋 auto_link 정밀도 ≥ 0.9 | ⏳ 이월 | 판정 사례가 생기는 문서 추출과 라벨 작업이 필요하다(Design §11.12) |
| SC-4 | RAGAS 다문서 부분집합 context_recall 향상, faithfulness 유지 | ⏳ 이월 | 그래프 끔/켬 평가 경로와 전환 근거 검증은 구현했다(M7-1·3). 실행은 하지 못했다 |
| SC-5 | 관리자 화면만으로 완주(DB/Swagger 0회) | ⚠️ 부분 | 화면 흐름은 모두 있다(Vitest 22건). 브라우저 확인 대기 |
| SC-6 | Neo4j를 중지해도 업로드·채팅 정상 | ⚠️ 부분 | 코드 경로와 테스트는 있다(`test_supplemental_fusion.py`, `test_graph_rag_wiring.py`). 실제로 중지해 보지는 못했다 |
| SC-7 | 권한 없는 KB 청크 노출 0건 | ✅ Met | `test_graph_retrieval_source.py`, `test_es_evidence_fetcher.py` |
| SC-8 | `admin_only`에서 일반 사용자 경로 그래프 실행 0건 | ✅ Met | `tests/contracts/test_extension_boundaries.py` C2·C3·C3b·C4 |
| SC-9 | 모듈 등록 줄 제거 시 기동·테스트 통과 | ⚠️ 부분 | AST 경계 테스트(C1)는 통과한다. 등록 줄을 빼고 기동해 보지는 못했다 |

**Success Rate**: 4/9 충족(44%). 부분 3건은 실서버만 있으면 확인할 수 있고, 이월 2건은 측정 작업이 필요하다.

**막힌 이유**: 2026-11-18부터 이 PC에서 Windows Smart App Control(켜짐)이 서명 없는 `kiwipiepy`·`asyncmy` DLL을 막는다. Code Integrity 이벤트 3077·3033으로 확인했다. 이 때문에 백엔드 앱이 기동되지 않는다. Smart App Control에는 파일별 예외 기능이 없다. 해결 방법은 끄거나, 백엔드를 WSL·Docker에서 실행하는 것이다.

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 저장소는 Neo4j. PoC는 Aura Free, 도입 시 자체 호스팅으로 전환(URI만 교체) | ✅ | Aura로 실연결 테스트 5건 통과. 벡터 인덱스는 512차원 |
| [Plan] | 추출 = 규칙(조문 참조) + LLM 구조화 | ✅ | 추출기 v3. 근거가 원문에 없는 관계는 버린다 |
| [Plan] | 엔티티 판정 = Jev 세 구간 + 가운데 구간은 LLM 재판정. Jev가 꺼져 있거나 실패하면 LLM이 대신한다 | ✅ | 로컬은 Jev 미설정이라 LLM 대체로 동작한다. Jev 실호출 측정은 SC-3과 함께 이월 |
| [Plan] | 엔티티는 전역 공유하고 `scope_key`를 예비로 둔다. 권한은 청크 단위로 건다 | ✅ | 반환 직전에 ES로 다시 조회하며 도구의 필터를 그대로 적용한다(SC-7) |
| [Plan] | 노출 = `use_graph` AND 노출 단계 AND 호출자 opt-in(3중 AND) | ✅ | 대화 라우트 3곳만 grant를 만든다. RAGAS는 관리자가 켠 평가에서만 만든다(M7-2) |
| [Design] | Option C: 코어는 훅·grant만 알고 모듈은 한 줄로 연결 | ✅ | 코어의 `graph_rag` import 0건(C1) |
| [Design] | 비관리자가 보낸 `use_graph`는 조용히 False로 저장 | ✅ | 저장 경로 3곳(create·update·fork)에서 정리한다(C5) |
| [Design] | general 전환은 RAGAS 2건 또는 강제 사유 | ✅ | 자리표시 구현을 실검증(`RagasEvalEvidence`)으로 바꿨다(M7-3) |
| [사용자, 4b] | 문서 주제 자동 분류: 2단계, 대표 1 + 보조 2, 관리자 목록 + 자동 추가 | ✅ | 실데이터에서 여신관리·총무를 자동 생성하고, 재추출한 문서는 기존 주제에 연결했다 |
| [사용자, 5] | 질문 주제는 Jev를 먼저 쓰고 LLM이 대체. 임베딩만 쓰는 방식은 거절 | ✅ | QueryTopicRouter. 시간 예산 50%, 10분 캐시 |
| [사용자, 5c] | 시작 엔티티 선택과 탐색에도 주제 범위 적용 | ✅ | 후보 20 → 범위 안 우선 5. 관계에도 `topic_ids`를 복사(M5-12·13) |
| [사용자, Check] | G-2·M-1은 코드 수정, G-1은 결정으로 기록 | ✅ | 단계 off이면 409를 내는 범위를 넓혔다. 문서 삭제 시 판정 기록도 지운다. FR-21 기록 위치는 구조화 로그(Plan v0.5) |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [graph-rag-foundation.plan.md](../01-plan/features/graph-rag-foundation.plan.md) (v0.5) | ✅ |
| Design | [graph-rag-foundation.design.md](../02-design/features/graph-rag-foundation.design.md) (v0.13, 구현 중 결정 §11.5~§11.13) | ✅ |
| Check | [graph-rag-foundation.analysis.md](../03-analysis/graph-rag-foundation.analysis.md) | ✅ 정적 94.6% → 96.2% |
| Guide | `docs/guides/neo4j-aura-setup.md` | ✅ |
| Act | 이 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| 범위 | FR | 상태 | 비고 |
|------|----|:----:|------|
| 저장소·기동 | FR-01·02 | ✅ | `GraphStorePort`, off·연결 실패여도 앱 기동 |
| 설정·단계 | FR-03·23·24 | ✅ | 설정 VO 검증, 단계 이력, capabilities(일반 사용자에게는 stage를 주지 않음) |
| 추출 | FR-04~07·18 | ✅ | 업로드 훅, 규칙+LLM, 근거 필수, 결정적 ID·재개 |
| 판정·검토 | FR-08~11 | ✅ | 후보(정확·별칭·벡터) → Jev/LLM → 판정 기록 → 승인·분리·재연결 |
| 검색 | FR-12~14·20 | ✅ | 청크 단위 권한 재조회, `fusion_source="graph"`, 시간 초과 시 기존 결과만 |
| 삭제 | FR-15 | ✅ | 근거·고아 엔티티·주제 연결·판정 기록 정리 |
| 관리자 API·화면 | FR-16·17 | ✅ | 엔드포인트 19개, 6탭(주제 탭 추가) |
| 노출 차단 | FR-21·22 | ✅ | 일반 사용자는 조용히 건너뛴다(사유는 구조화 로그). 모듈 경계 계약 테스트 |
| 주제 | FR-25~28 | ✅ | V090·V091, 분류기, 검토(승인·분리·이동) |
| 평가 비교 | FR-19 | ⚠️ | 관리자 전용 `allow_supplemental` 평가와 전환 근거 검증 구현. 실행 이월 |
| 질문 주제 | FR-29 | ⚠️ | 구현했고 저장소 단계 실데이터로 확인했다. 앱 전체 실런 이월 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|:------:|
| 그래프 검색 지연 | p95 800ms(Plan) | 1.7~3.4초(실측 4질문, LLM 주제 판정이 대부분) | ❌ → 설정 `retrieval_timeout_ms`(최대 5,000)로 관리. 기본 800이면 대개 시간 초과로 빠진다 |
| 답변 경로 보호 | 그래프 실패가 답변을 깨지 않음 | 시간 상한·예외 → 기존 결과만, 기존 검색이 실패하면 보조 검색 취소 | ✅ |
| 모듈 분리 | 코어 → graph_rag import 0 | 0(AST 계약) | ✅ |
| DB 마이그레이션 | 모든 컬럼에 COMMENT | V086~V091 충족, 로컬 적용 완료 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|:------:|
| 코어 확장 지점 | `idt/src/domain/extension_hooks/`, `application/rag_agent/tools.py`, `application/agent_builder/*` | ✅ |
| 그래프 모듈 | `idt/src/{domain,application,infrastructure}/graph_rag/`, `api/graph_rag_di.py`, `api/routes/*graph_rag*` | ✅ |
| RAGAS 비교 opt-in | `application/ragas/batch_eval_use_case.py`, `infrastructure/ragas/target_executor.py`, `api/routes/ragas_router.py`, `api/main.py:_run_agent_headless` | ✅ |
| 마이그레이션 | `idt/db/migration/V086~V091` (로컬 적용 완료, 재적용 금지) | ✅ |
| 프론트 | `idt_front/src/pages/AdminGraphRagPage/`, `RagConfigPanel.tsx`, `EvalDatasetPage/CreateRunModal.tsx`, types·services·hooks | ✅ |
| 테스트 | 백엔드 graph_rag 단위·SQLite·계약·Aura 실연결(`-m neo4j`), 프론트 Vitest+MSW | ✅ |
| 규모 | 184 files, +21,165줄(문서 포함) | — |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority | 선행 조건 |
|------|--------|:--------:|-----------|
| SC-4 RAGAS 그래프 끔/켬 비교 → general 전환 근거 | 백엔드 기동 불가 | High | 환경 복구, 다문서 질문 테스트셋 |
| SC-3 별칭 정밀도(라벨 30쌍, Jev·LLM 모드 각각) | 판정 사례 부족 + 환경 | High | 27청크 문서 추출(LLM 수십 회, 사용자 승인), 라벨 작업 |
| SC-5·6·9 실확인, FR-29 앱 실런 | 환경 | Medium | 백엔드 기동 |
| 튜닝: `MIN_VECTOR_SIMILARITY` 0.75, `HUB_DEGREE_LIMIT` 15, parent/child 겹침(M5-8) | 측정값 필요 | Medium | SC-3·SC-4 결과 |
| 지연 개선(주제 판정 LLM 1.6~2.5초) | 범위 밖 | Medium | Jev 실호출 확인(Jev가 더 빠를 것으로 예상) |
| M-2 고아 엔티티 정리 쿼리 전체 탐색 / M-3 off에서도 의존 객체 미리 생성 | 규모 측정 후 | Low | — |

### 4.2 Cancelled/On Hold

| Item | Reason | Alternative |
|------|--------|-------------|
| FR-21 미적용 사유를 실행 기록 테이블에 저장 | 코어 관측 구조 변경 필요(사용자 결정 C-1) | 구조화 로그(request_id)에 기록 |
| general 단계 전환 실행 | Plan 범위 밖(이번 사이클은 admin_only까지) | SC-4 통과 후 다음 사이클 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Note |
|--------|--------|-------|------|
| Design Match Rate(정적) | 90% | 96.2% | Check 94.6% → Act 후. 런타임 축 미포함 |
| Structural / Functional / Contract | — | 97% / 95% / 97% | 백엔드↔프론트 타입 불일치 0 |
| 백엔드 회귀 | 새 실패 0 | 0 | 같은 환경 기준(HEAD와 실패 목록 일치) |
| 프론트 회귀 | 새 실패 0 | 0 | master와 같은 9건, `docx-preview` 미설치로 11개 suite 로드 실패(환경) |
| Critical 이슈 | 0 | 0 | |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|:------:|
| 문서 제목 엔티티가 허브가 되어 탐색이 문서 전체로 퍼짐 | 관계 15개를 넘는 노드는 경유하지 않게 했다 + 주제 범위 | ✅ |
| 그래프 검색 직렬 지연 2.3~6.6초 | 주제 판정과 연결을 동시에, 이름 조회 쿼리 통합 → 1.7~3.4초 | ✅ |
| 시작 엔티티 5개가 모두 범위 밖이면 범위가 풀림 | 후보 20개 → 범위 안 우선(M5-12) | ✅ |
| 범위 밖 경로가 경로 상한을 먼저 채움 | 관계에 `topic_ids`를 복사해 범위 안 관계만 탐색(M5-13) | ✅ |
| general 전환 근거를 항상 거절(자리표시) | `RagasEvalEvidence` 실검증 | ✅ |
| 단계 off에서도 검토·주제 API 동작(G-2) | 409 `GRAPH_STAGE_OFF` | ✅ |
| 지운 문서의 판정이 검토 큐에 남음(M-1) | 삭제 훅이 판정 기록도 지운다 | ✅ |
| 엑셀 고객 샘플이 추출 대상이 됨 | 관리자 수동 추출에서도 엑셀·CSV 거절 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **모듈 경계를 먼저 만든 것**(module-1을 그래프 코드 없이). 이후 6개 모듈을 붙이는 동안 코어 회귀가 0이었고, 경계는 AST 계약 테스트로 고정했다.
- **구현 중 결정을 Design §11.x에 표로 남긴 것**. Check에서 gap-detector가 "설계와 다름"과 "승인된 변경"을 구분할 수 있었다.
- **실데이터로 빨리 확인한 것**. 허브 노드 문제, 주제 범위의 약점(①·②), 800ms 시간 상한 문제를 테스트가 아니라 실측에서 찾았다.

### 6.2 What Needs Improvement (Problem)

- **효과 측정을 마지막 module에 몰아 둔 것**. 환경이 막히자 사이클의 "왜"(context_recall 향상)를 숫자로 보이지 못한 채 끝났다.
- **Plan의 지연 목표(p95 800ms)가 질문 주제 판정(LLM) 추가 전에 정해졌다**. 주제 판정을 추가하면서 목표를 다시 정하지 않았다.
- **실행 환경 의존**. 로컬 DLL 차단 한 번으로 앱 실런·회귀 비교·실데이터 확인이 모두 멈췄다.

### 6.3 What to Try Next (Try)

- 효과 지표(RAGAS 부분집합)를 module-3 직후, 추출이 처음 가능해진 시점에 기준선부터 잰다.
- 요구사항을 추가하면(예: FR-25~29) 그 요구사항이 NFR(지연)에 주는 영향을 Plan에서 같이 고친다.
- 백엔드 실행 환경을 WSL·Docker로도 준비해 두어 Windows 정책 변화에 대비한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 요구 추가(v0.4) 때 NFR 재검토 없음 | 버전을 올릴 때 NFR 표를 함께 점검한다 |
| Do | 측정이 마지막 module에 몰림 | 측정 가능한 첫 module 직후에 기준선을 잰다 |
| Check | gap-detector가 턴 한도에 걸림 | 범위를 FR 묶음별로 나누어 맡기고, 핵심 발견은 직접 재확인한다(이번에 오판 1건을 걸러냄) |

### 7.2 Tools/Environment

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| 로컬 실행 | Smart App Control 해제 또는 WSL·Docker 백엔드 | 앱 실런·실측 재개 |
| 프론트 의존성 | 공유 node_modules에 `docx-preview` 설치 | 11개 suite 회귀 복구 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 환경 복구(Smart App Control 끄기 또는 WSL·Docker)
- [ ] SC-5·6·9 실확인, 질문 주제 판정 실데이터 확인
- [ ] SC-4: 같은 에이전트·테스트셋으로 RAGAS 그래프 끔/켬 실행
- [ ] SC-3: 27청크 문서 추출(사용자 승인) → 별칭 라벨 → 정밀도
- [ ] push → PR(`--base master`). module-1만 먼저 분리 PR로 내는 방안 검토
- [ ] 머지 후: 메인 checkout의 미추적 Plan·Design 사본 삭제 → pull, worktree 정리(node_modules junction 먼저 제거)

### 8.2 Next PDCA Cycle

| Item | Priority |
|------|:--------:|
| graph-rag 측정·튜닝(SC-3·4, 지연·임계값) | High |
| general 단계 전환과 KB 화면 노출(P2 KB 운영자) | Medium |
| Neo4j 자체 호스팅 전환(사내 도입 전 보안 검토) | Medium |

---

## 9. Changelog

### graph-rag-foundation (2026-11-18)

**Added:**
- 코어 확장 훅(post_ingest·deletion·supplemental·exposure), `SupplementalGrant` 체인, `merge_many` 결합
- 그래프 모듈: 설정·노출 단계, Neo4j(Aura) 저장소, 추출 잡(규칙+LLM), 엔티티 판정(Jev/LLM)·검토 큐, 문서 주제 분류, 그래프 검색 소스(주제 범위·허브 제한·권한 재조회), 삭제 정리, 정합성 점검
- 관리자 `/admin/graph-rag`(6탭), 빌더 "그래프 검색(테스트)" 토글, RAGAS "그래프 보조 검색 켜고 평가"(관리자)
- DB V086~V091

**Changed:**
- RAGAS 헤드리스 실행: 관리자가 켠 평가에서만 grant(계약 C3b 갱신)
- general 전환 근거: 자리표시 → 실검증

**Fixed:**
- 관리자 수동 추출도 엑셀·CSV 거절, 단계 off 409 범위, 문서 삭제 시 판정 잔존

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-18 | 완료 보고서 작성(Partial — 측정 이월) | 배상규 |
