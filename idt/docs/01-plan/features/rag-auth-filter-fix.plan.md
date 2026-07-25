# RAG Auth Filter Fix Planning Document

> **Summary**: 에이전트 내부문서 검색이 권한 필터(`viewer_department_ids`/`visibility`) 주입으로 **항상 0건**이 되는 결함 수정 — 검색측 안전화(1단계) + 검색 리라이트 사용자 컨텍스트 주입("나의"→사용자명 치환) + 관측성 결함 2건 + BM25 컬렉션 격리
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-21
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | "내부 문서 데이터 분석 에이전트"가 휴가 질문에 "데이터가 제공되지 않았습니다"로 답함. 실측 결과 supervisor 라우팅·검색 워커 호출은 정상(3회 시도)이었으나 ① `_apply_auth_filter`가 주입한 `viewer_department_ids` 키를 Qdrant/ES가 must 조건으로 그대로 적용 → 색인 페이로드에 해당 필드가 없어 **모든 검색이 무조건 0건**(fail-closed), ② 검색 리라이트 LLM에는 사용자 컨텍스트가 미주입되어 "나의 휴가"가 사용자명("배상규") 없는 일반 쿼리로 재작성됨 — 필터를 고쳐도 개인 데이터 정조준 불가 |
| **Solution** | 검색 인프라에 색인되지 않은 권한 키를 하이브리드 검색 적용 전에 분리 — `viewer_department_ids`는 제외(주석의 원래 의도), `visibility`는 "public OR 필드 없음" 완화 필터로 변경. 검색 파이프라인 rewrite 프롬프트에 supervisor/analysis와 동일한 사용자 컨텍스트 블록 주입 + 1인칭 치환 규칙 추가. 동시에 0건 강등 경고 로그, 한글 tool_name→`unnamed_tool` 관측성 버그, BM25 축 컬렉션 미격리를 함께 수정 |
| **Function/UX Effect** | KB에 업로드한 문서가 에이전트 대화에서 즉시 검색됨(휴가 현황 질문 → 검색 히트 → 데이터 분석 → 차트 생성 경로 복원). 운영자는 `ai_tool_call.tool_name`으로 어떤 도구가 불렸는지 식별 가능해지고, 검색 0건의 원인이 로그로 추적됨 |
| **Core Value** | 에이전트 플랫폼의 핵심 가치사슬(KB 업로드 → 검색 → 분석 → 시각화)의 단절 지점을 복구. 권한 필터의 "가정(Repository가 무시) ≠ 구현(must 적용)" 불일치를 해소하고, 후속 인제스천 색인 시 자연스럽게 엄격한 권한 모델로 이행 가능한 구조 확보 |

---

## 1. Overview

### 1.1 Purpose

내부문서 검색 도구의 검색 결과가 권한 필터 주입 때문에 항상 0건이 되는 결함을 수정한다.
2단계 전략의 **1단계(검색측 안전화)**로, 인제스천 페이로드 확장·백필은 후속 기능으로 분리한다.

### 1.2 Background (현황 실측 — 2026-07-21 로컬 DB/Qdrant/ES 재현 완료)

**증상 실행**: run `ead3267e-3919-460c-955c-7927a6ea8ddb` (agent `2fc01e00`, 세션 `956ddadb`, 09:46)

- `ai_run_step` 실측: supervisor → **internal_document_search_worker(3회 시도, 전부 "관련 내부 문서를 찾지 못했습니다")** → data_analysis_worker("데이터 미제공" 답변) → chart 미생성 → final_answer. 즉 **도구 미호출이 아니라 검색 0건이 원인**
- 휴가 xlsx(`354001b4`, 8청크)는 질문 1분 전 업로드되어 Qdrant `test10`·ES `documents` 인덱스 **양쪽에 정상 색인됨**
- 근본 원인 체인:
  1. `src/application/rag_agent/tools.py:113-130` `_apply_auth_filter`: READ_DEPARTMENT_DOCS 보유 시 `viewer_department_ids=<부서ID CSV>`, 미보유 시 `visibility=public`을 metadata_filter에 주입
  2. 주석은 "Repository 미지원 시 무시"를 가정하지만, `HybridSearchUseCase`(`use_case.py:100-108, 142-144`)는 **모든 키를 그대로** ES term filter + Qdrant must 조건(`qdrant_vectorstore.py:205-208`)으로 적용
  3. 색인 페이로드에 `viewer_department_ids`/`visibility` 필드가 **존재하지 않음** → 어느 분기로 가든 전 문서 탈락
- 재현 결과: BM25 필터 없이 8건 히트 / `viewer_department_ids` term 필터 적용 시 0건. Qdrant도 동일 필터로 0건. **두 검색 축 모두 데이터는 있었고 필터만이 원인**
- 참고: 7/6~7/7 동일 질문 성공은 대화에 엑셀이 직접 첨부되어 검색 없이 `data_analysis`가 처리한 경로로 추정 (KB 휴가 문서는 7/21 업로드)

**공동 원인 2 — 검색 리라이트에 사용자 컨텍스트 미주입 (2026-07-22 사용자 지적으로 확인)**:

- 사용자 컨텍스트 블록(`prompt_rendering.render_user_context_block` — `이름: 배상규`, "'나'=위 사용자" 규칙 포함)은 supervisor(`workflow_compiler.py:169-173`), data_analysis 노드(`:892-896`), excel 워크플로우(`:856-858`)에는 prepend되지만, **검색 파이프라인의 rewrite/validate/compress LLM 호출(`search_pipeline.py:158-218`)에는 전혀 주입되지 않음**
- `REWRITE_SYSTEM_PROMPT`의 지시어 치환 규칙은 대화 지시어("그거, 아까 그 자료")뿐 — 1인칭("나의"→사용자명) 치환 규칙도, 치환에 쓸 이름 정보도 없음
- 실측: 문제 run의 3회 쿼리 모두 `배상규` 미포함 ("나의 남은 휴가 개수와 월별 사용 현황" → "휴가 개수와 월별 사용 현황 그래프 생성 방법" → 동일 변형). 2·3차는 자체 규칙("출력 형식 요구 제거")도 위반하며 "그래프 만드는 방법" 검색으로 표류
- 인과 구분: **0건 자체는 필터가 원인** (필터 없으면 비개인화 쿼리로도 BM25 8건 히트 — 재현 실측). 리라이트 결함은 필터 수정 후의 **정확도/개인화 결함** — 소규모 로컬(118청크)에선 가려지나 코퍼스가 커지면 "나의 X" 질의가 본인 데이터를 정조준하지 못함

**부차 결함 (같은 실측에서 발견)**:

- `ai_tool_call.tool_name`이 전부 `unnamed_tool` — 에이전트 tool_config의 한글 `tool_name: "내부 문서 검색"`이 `sanitize_tool_name`(`rag_tool_config.py:12-18`)에서 전부 치환·strip되어 폴백 `"unnamed_tool"`이 됨. LLM에 노출되는 도구 이름도 동일 → 관측·디버깅 모두 방해 (이번 원인 분석에서도 도구 식별을 지연시킴)
- 검색 0건 강등 시 주입된 필터 키가 로그에 남지 않아 원인 추적 불가
- BM25 축은 전역 `documents` 인덱스를 컬렉션 구분 없이 검색 — ES 문서에 `collection_name`/`kb_id` 필드가 있음에도 필터 미적용 → 타 컬렉션 청크 혼입 가능 (Qdrant 축은 collection 지정으로 격리됨)

### 1.3 사용자 결정 사항 (2026-07-21 확정)

| 결정 | 내용 |
|------|------|
| 수정 전략 | **2단계** — 이번: 검색측 안전화 / 후속: 인제스천 visibility·부서 페이로드 색인 + 백필 + 필터 실효화 |
| 보안 정책 | **완화 수용** — "visibility 필드 없는 기존 문서 = public 취급" (로컬/개발 단계 결정, 후속 색인 시 자연 엄격화) |
| 범위 | 부차 결함 3건(tool_name 관측성, 0건 경고 로그, BM25 축 문제) 모두 포함 |

### 1.4 Related Documents

- 권한 필터 도입 배경: agent-user-context Design §7.2 (tools.py 모듈 docstring 참조)
- 검색 규칙: `docs/rules/rag-retrieval.md`
- 라우팅 검색 필터 3분류 선례: `tools.py:33-38` (`_ROUTED_SCOPE_KEYS`/`_ROUTED_IGNORED_KEYS`) — routed 경로는 이미 `viewer_department_ids` 무시·`visibility` 강등으로 방어됨. 이번 수정은 **기존(비 routed) hybrid 경로**에 같은 원칙을 적용하는 것

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. `viewer_department_ids` 검색 미적용**: hybrid 검색 요청 구성 전 필터에서 제외 (주석의 원래 의도를 코드로 실현). 키 자체는 AuthContext에 유지 — 후속 실효화 시 재사용
- [ ] **S2. `visibility` 완화 필터**: `visibility=public` 강제 조건을 "visibility가 public **이거나 필드가 없는** 문서 통과"로 변경 — Qdrant(should + IsEmpty), ES(bool should + must_not exists) 양쪽
- [ ] **S3. 0건 강등 경고 로그**: 권한 필터가 적용된 검색이 0건이면 주입 키·필터 내용을 warning으로 기록
- [ ] **S4. tool_name sanitize 폴백 개선**: 한글 등 전치환 시 `"unnamed_tool"` 대신 기본값 `"internal_document_search"` 폴백 — LLM 노출 이름과 `ai_tool_call.tool_name` 기록 모두 정상화
- [ ] **S5. BM25 컬렉션 격리**: ES 검색에 `collection_name`(요청에 있으면) term 필터 적용 — Qdrant 축과 동일한 격리 수준
- [ ] **S6. 검색 리라이트 사용자 컨텍스트 주입**: `create_search_pipeline_node`에 사용자 컨텍스트 블록 전달 → rewrite(필요시 validate) 프롬프트에 포함 + "1인칭(나/내/본인)은 사용자 이름으로 치환" 규칙 추가. PII whitelist(`prompt_rendering` 금지 필드) 준수
- [ ] **S7. 회귀 검증**: 휴가 시나리오 재현 테스트 (권한 필터 주입 상태에서 검색 히트 + "나의" 질의가 사용자명 포함 쿼리로 재작성되는지 확인)

### 2.2 Out of Scope (후속 기능으로 분리)

- 인제스천 파이프라인에 `visibility`/`department_ids` 페이로드 색인 + 기존 데이터 백필 + fail-closed 복귀 (**후속: rag-auth-payload-indexing** 으로 기록)
- `viewer_department_ids` OR 매칭 실효화 (인제스천 색인 선행 필요)
- 권한 모델(PermissionCode, role_permissions) 자체 변경
- routed 검색 경로 변경 (이미 강등으로 방어됨)
- 프론트엔드 변경 (백엔드 전용 — API 계약 불변)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `viewer_department_ids` 키는 HybridSearch 요청의 metadata_filter에서 제외되어 Qdrant/ES 어느 쪽에도 조건으로 적용되지 않는다 | High | Pending |
| FR-02 | `visibility=public` 필터는 "visibility=public OR visibility 필드 부재" 문서를 통과시킨다 (Qdrant·ES 동일 의미) | High | Pending |
| FR-03 | 권한 필터가 주입된 검색이 0건일 때 주입 키 목록·필터 내용이 warning 로그(request_id 포함)로 남는다 | High | Pending |
| FR-04 | `sanitize_tool_name` 결과가 빈 문자열이면 `"unnamed_tool"`이 아닌 도구 기본명(`internal_document_search`)으로 폴백한다 | Medium | Pending |
| FR-05 | ES BM25 검색에 요청의 `collection_name` term 필터가 적용된다 (미지정 시 기존 동작 유지) | Medium | Pending |
| FR-06 | 검색 rewrite LLM 프롬프트에 사용자 컨텍스트 블록이 주입되고, 1인칭 질의("나의 X")가 사용자 이름을 포함한 쿼리로 재작성된다 (include_user_context=False면 기존 동작) | High | Pending |
| FR-07 | rewrite 사용자 컨텍스트는 `render_user_context_block` whitelist 준수 — user_id/사번/이메일 미노출 | High | Pending |
| FR-08 | 휴가 시나리오 회귀 테스트: 부서 권한 사용자 + 필드 미색인 페이로드 상태에서 검색이 히트를 반환 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 회귀 안전 | 기존 검색 API/스키마 계약 불변, 기존 pytest 무회귀 (사전 실패분 제외 기준) | pytest 격리 실행 |
| 아키텍처 | 필터 분류 로직은 domain/application 레이어, Qdrant/ES 쿼리 변환은 infrastructure — 레이어 규칙 준수 | verify-architecture 스킬 |
| 보안 추적성 | 완화 결정(필드 부재=public)은 코드 주석+본 문서에 근거 기록, 후속 색인 시 제거 지점 명시 | 코드 리뷰 |
| TDD | 테스트 선행 (Red → Green → Refactor) | verify-tdd 스킬 |
| 로깅 | 신규 로그는 LOG-001 규칙 준수 (structured, request_id) | verify-logging 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 로컬 재현 시나리오: "나의 휴가 남은 휴가개수와 월별 사용 현황 그래프로 보여줄 수 있겠니?" 질문에 검색 워커가 휴가 xlsx 청크를 히트하고, data_analysis → 차트 생성까지 도달 (E2E 수동 확인)
- [ ] Qdrant 직접 쿼리 재현식(완화 필터)이 8건 히트 반환
- [ ] `ai_tool_call.tool_name`에 실제 도구명이 기록됨
- [ ] "나의 휴가..." 질의 시 `ai_tool_call.arguments_json`의 재작성 쿼리에 사용자 이름("배상규")이 포함됨
- [ ] 검색 0건 시 강등 warning 로그 확인
- [ ] 신규 테스트 전부 통과 + 기존 테스트 무회귀

### 4.2 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, config 하드코딩 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 완화로 인해 권한 없는 사용자가 기존 색인 문서 열람 가능 | Medium | High(의도됨) | 사용자 결정으로 수용(로컬/개발). 후속 rag-auth-payload-indexing에서 fail-closed 복귀. 완화 지점에 명시 주석 |
| `viewer_department_ids` 제거가 향후 부서 필터 실효화와 충돌 | Low | Medium | 키를 AuthContext에는 유지하고 검색 적용 단계에서만 분리 — 후속에서 적용 지점만 켜면 됨 |
| Qdrant IsEmpty/ES exists 쿼리의 버전별 문법 차이 | Low | Low | 로컬 Qdrant/ES 대상 통합 재현 스크립트로 검증 (이번 분석에서 사용한 쿼리 재활용) |
| visibility 필터를 쓰는 다른 호출 경로(위키 검색 등) 회귀 | Medium | Low | `metadata_filter['visibility']` 사용처 전수 조사 후 Design에 반영, 기존 테스트로 확인 |
| tool_name 폴백 변경이 기존 에이전트 도구 식별에 영향 | Low | Low | 폴백만 변경(정상 영문명은 무변경) — additive |
| BM25 컬렉션 필터 추가로 기존 전역 검색 사용처 회귀 | Medium | Low | `collection_name` 미지정 시 기존 동작 유지 (opt-in 필터) |
| rewrite에 이름 주입 시 PII 노출 범위 확대 | Medium | Low | `render_user_context_block` whitelist 재사용(이름·부서·역할만), 금지 필드(user_id/사번/이메일) 미전달 — FR-07로 명시 |
| 이름 포함 쿼리가 오히려 일반 정책 문서 검색 정확도 저하 | Low | Medium | 치환 규칙을 "개인 데이터 질의(나의 X)일 때만"으로 한정 — 프롬프트 규칙 설계는 Design에서 확정, 회귀는 기존 검색 테스트로 확인 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation | 기존 프로젝트 구조 (Thin DDD) | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 미색인 키 처리 위치 | Repository에서 무시 / 검색 요청 구성 전 분리 | 요청 구성 전 분리 (tools.py 측) | Repository는 "받은 필터를 그대로 적용"이 단일 책임으로 명확. routed 경로의 키 3분류 선례(`_ROUTED_SCOPE_KEYS`)와 일관 |
| visibility 완화 표현 | 키 제거 / "public OR 필드 없음" 필터 | "public OR 필드 없음" | 보안 의미 보존 — visibility가 색인된 문서에는 즉시 실효, 후속 색인 시 코드 변경 없이 엄격화 |
| 완화 구현 방식 | 기존 metadata_filter(equals 전용) 확장 / 별도 필터 개념 추가 | Design에서 확정 | 기존 equals 계약 보존 + 신규 opt-in 분기 선호 (기존 설정 갈아끼우기 금지 관례) |
| tool_name 폴백 | `unnamed_tool` 유지 / 도구 기본명 폴백 | 도구 기본명 폴백 | LLM 도구 선택·관측 기록 모두에 의미 있는 이름 제공 |
| 2단계 분리 | 한 번에 인제스천까지 / 검색측 먼저 | 검색측 먼저 | 즉시 복구 우선, 인제스천+백필은 독립 기능으로 위험 격리 (사용자 확정) |

### 6.3 변경 대상 파일 (예상)

```
idt/src/
├── application/rag_agent/tools.py            # S1·S2·S3: _apply_auth_filter 키 분리, 강등 로그
├── application/hybrid_search/use_case.py     # S2·S5: 완화 필터·컬렉션 필터 변환 (Design에서 확정)
├── domain/vector/value_objects.py            # S2: SearchFilter 완화 표현 확장 시
├── infrastructure/vector/qdrant_vectorstore.py  # S2: IsEmpty 조건 변환
├── domain/agent_builder/rag_tool_config.py   # S4: sanitize 폴백
├── application/agent_builder/search_pipeline.py  # S6: rewrite 프롬프트 사용자 블록 파라미터
├── application/agent_builder/workflow_compiler.py # S6: create_search_pipeline_node 배선
└── tests/ (해당 모듈 대응 테스트)              # S7 + 각 FR 선행 테스트
```

> 정확한 수정 지점·필터 스키마 표현은 Design 단계에서 확정.

---

## 7. Convention Prerequisites

- [x] DB 세션/로깅/테스트 규칙: `docs/rules/*.md` 준수
- [x] 검증 스킬 존재: verify-architecture, verify-logging, verify-tdd
- [x] 백엔드 테스트 격리 실행 관례 (Windows 이벤트 루프 flakiness)
- 환경변수·마이그레이션·API 계약 변경 **없음** (프론트 동기화 불필요)

---

## 8. Implementation Guide

### 8.1 구현 순서

```
1. FR-01/02  필터 분리·완화: 테스트 먼저 (주입 키별 요청 필터 검증) → tools.py/use_case 구현
2. FR-02     Qdrant/ES 변환: 로컬 재현 쿼리로 실측 검증 (이번 분석의 curl 재현식 재사용)
3. FR-03     강등 warning 로그
4. FR-04     sanitize 폴백 (독립 — 병행 가능)
5. FR-05     BM25 collection_name 필터 (opt-in)
6. FR-06/07  검색 rewrite 사용자 컨텍스트 주입: 테스트 먼저 ("나의 X" → 이름 포함 쿼리) → search_pipeline/compiler 배선
7. FR-08     휴가 시나리오 회귀 테스트 + 전체 pytest + E2E 수동 확인
```

### 8.2 재현/검증 자료 (이번 분석 실측)

- 증상 run: `ead3267e-3919-460c-955c-7927a6ea8ddb` / 세션 `956ddadb-e8b9-4116-9678-eb01091baf49`
- 대상 문서: `354001b4-bfaa-4252-9a7f-66169053c576` (`휴가_현황_10명_샘플 - 복사본.xlsx`, Qdrant `test10` 8청크, ES `documents` 8건)
- 검증 쿼리: Qdrant scroll + `viewer_department_ids`/`visibility` must 필터 → 0건 (버그 재현), 필터 제거 → 히트 (수정 목표)

---

## 9. Next Steps

1. [ ] Write design document (`/pdca design rag-auth-filter-fix`) — visibility 완화 필터의 스키마 표현·수정 지점 확정, `visibility` 필터 사용처 전수 조사 포함
2. [ ] 구현 (TDD)
3. [ ] Gap 분석 (`/pdca analyze rag-auth-filter-fix`)
4. [ ] 후속 기능 등록: `rag-auth-payload-indexing` (인제스천 페이로드 색인 + 백필 + fail-closed 복귀)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-21 | Initial draft — 원인 실측(run/Qdrant/ES 재현) 기반, 사용자 결정 3건 반영 | 배상규 |
| 0.2 | 2026-07-22 | 공동 원인 2 추가 — 검색 rewrite 사용자 컨텍스트 미주입("나의"→사용자명 치환 불가) 실측 확인, FR-06/07·S6 반영 | 배상규 |
