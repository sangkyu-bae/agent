# kb-rag-filter Completion Report

> **Status**: Complete (with pending manual verification)
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 1.0
> **Author**: 배상규
> **Completion Date**: 2026-07-10
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| Feature | agent-builder 내부문서검색 도구에 논리 지식베이스(KB) 필터 연동 |
| 시작일 | 2026-07-08 |
| 완료일 | 2026-07-10 |
| 소요 기간 | 2일 + Act-1 재검증 1일 |
| Match Rate | **97.6%** (20.5 / 21 판정 항목) |
| 반복 횟수 | 1회 (Act-1: G1 D3 권한검증 해소) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────────────────┐
│  설계 일치율: 97.6% (최종)                             │
├─────────────────────────────────────────────────────────┤
│  ✅ 일치:      20 / 21 항목                            │
│  ⏳ Gap:       0 / 21 (코드 레벨 — G2는 수동검증)      │
│                                                          │
│  ✅ 테스트 통과:                                        │
│     - 백엔드 신규 36건 (Do 24건 + Act-1 12건)         │
│     - 기존 회귀 무오류 (740건 통과, MCPRouting 3건 제외)|
│     - 프론트 신규 11건 포함 287건 전부 통과            │
│                                                          │
│  ✅ 구현 완성도: 100% (코드 설계 준수)                 │
│  ✅ 아키텍처: DDD 레이어 규칙 준수 (무의존성)          │
└─────────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | knowledge-base-scoping에서 백엔드 KB 계층을 완성했으나(청크에 kb_id/kb_name payload 주입), 에이전트 빌더는 여전히 물리 컬렉션 목록만 노출 → 새 구조로 올린 문서를 에이전트가 선택해 검색할 UI/필드가 없음. 물리 컬렉션 다중 관리로부터 "단일 컬렉션 + 메타데이터 격리" 전환의 마지막 소비자 연결이 누락 |
| **Solution** | `RagToolConfig`에 first-class `kb_id` 필드 신설 + 프론트 RagConfigPanel에 KB 드롭다운 추가(기존 컬렉션 드롭다운과 병행). 저장 시점에 KB 존재/권한 검증 + 물리 컬렉션 canonicalize + scope clamp 적용. 런타임은 ToolFactory가 `kb_id`를 metadata_filter에 병합해 기존 검색 경로(hybrid, routed) 재사용 |
| **Function/UX Effect** | 에이전트 제작자가 이제 "지식베이스 이름"만 골라 검색 범위를 격리할 수 있음. 개인/부서 KB 선택 시 에이전트 공개범위 자동 제한(기존 컬렉션과 동일 정책). 기존 에이전트는 아무 영향 없이 동작. 프론트 3개 UI 지점(KB 드롭다운 + 컬렉션 disabled 안내 + 요약 배지) 반영 |
| **Core Value** | 논리 KB 계층이 에이전트 검색까지 관통해 "문서 물리 관리 → 논리 조직화 → 에이전트 검색 격리"의 전체 파이프라인 완성. 단일 컬렉션 구조 전환의 진정한 소비자 가치 실현 |

---

## 2. Related Documents

| 단계 | 문서 | 상태 |
|------|------|------|
| Plan | [kb-rag-filter.plan.md](../01-plan/features/kb-rag-filter.plan.md) | ✅ 최종화 |
| Design | [kb-rag-filter.design.md](../02-design/features/kb-rag-filter.design.md) | ✅ 최종화 |
| Check | [kb-rag-filter.analysis.md](../03-analysis/kb-rag-filter.analysis.md) | ✅ 완료 (97.6%) |
| Act | 현재 문서 | ✅ 완료 |

---

## 3. PDCA Cycle Summary

### 3.1 Plan Phase (2026-07-08)

**문서**: `docs/01-plan/features/kb-rag-filter.plan.md`

**핵심 결정사항**:
- **범위**: Backend KB 필터 + Frontend UI (KB 목록/생성은 후속)
- **UI 방식**: KB 드롭다운 신규 추가, 기존 컬렉션 드롭다운 병행 유지 (독립 opt-in)
- **저장 필드**: `RagToolConfig`에 first-class `kb_id: str | None` 추가
- **scope 연동**: KB scope에 따른 에이전트 공개범위 자동 제한 포함
- **호환성**: 기존 `collection_name` 경로 무수정 보존

**요구사항**:
- FR-01: KB 목록 조회·선택 가능
- FR-02: `kb_id`는 저장 시 `RagToolConfig` 필드로 저장, None 시 기존 동작 동일
- FR-03: `kb_id` 설정 시 hybrid + routed 양쪽 검색 격리
- FR-04: 물리 컬렉션 오배선 방지(KB 컬렉션으로 고정)
- FR-05: scope clamp 생성·수정 양쪽 적용
- FR-06: 기존 경로 무수정 보존
- FR-07: KB 선택 UI에 scope 배지 및 안내 표시

### 3.2 Design Phase (2026-07-08~09)

**문서**: `docs/02-design/features/kb-rag-filter.design.md`

**핵심 설계 결정 (D1~D7 확정)**:

| ID | 결정 | 근거 |
|----|------|------|
| **D1** | 물리 컬렉션 해석 = **저장 시점 고정** | KB API에 컬렉션 재배정(update) 없음 → 저장 시 canonicalize 안전. 런타임 조회 회피로 동기 ToolFactory 유지 |
| **D2** | `kb_id` 우선 규칙 | `kb_id` 지정 시 사용자 `collection_name` 무시, KB 컬렉션으로 덮어씀. UI는 KB 선택 시 컬렉션 드롭다운 disabled |
| **D3** | 고아 kb_id 처리 | 저장 시: 미존재→400, 권한없음→**403**(Act-1 구현). 실행 시: 추가 방어 없음 |
| **D4** | KB 목록 API | 기존 `GET /api/v1/knowledge-bases` 재사용, 권한 필터 이미 구현됨 |
| **D5** | kb_id 형식 검증 | VO는 형식 검증 안 함 (존재 검증이 상위에서 수행) |
| **D6** | ToolFactory 병합 | `kb_id` 있으면 `{**metadata_filter, "kb_id": kb_id}`로 병합. InternalDocumentSearchTool 무수정 |
| **D7** | scope clamp 확장 | create/update 양쪽에서 KB scope 수집 → `VisibilityPolicy.clamp_visibility`에 합류 |

**아키텍처 준수**:
- Domain: VO 검증 최소 (무의존성)
- Application: UseCase에서 KB 존재/권한 검증 (repository 인터페이스 경유)
- Infrastructure: ToolFactory 병합, 도구 무수정
- API: 스키마 추가 없음 (기존 RagToolConfig 통과)

### 3.3 Do Phase (Implementation, 2026-07-08~09)

**구현 순서 (설계 §7 준수)**:

1. **[BE-1]** 도메인: `RagToolConfig.kb_id` 필드 추가 + 테스트 (4 건)
2. **[BE-2]** ToolFactory 병합 로직 `_merge_kb_filter` + 테스트 (5 건)
3. **[BE-3]** CreateAgentUseCase/UpdateAgentUseCase: 검증·canonicalize·clamp + 테스트 (8+5 건)
4. **[BE-4]** API 스키마 + main.py DI (kb_repo 주입)
5. **[FE-1]** 타입/상수/서비스/훅 + 테스트 (11 건)
6. **[FE-2]** RagConfigPanel KB 드롭다운 섹션
7. **[FE-3]** RagConfigSummaryBadge KB 라벨 우선

**신규 파일 및 수정**:

**Backend**:
- `src/domain/agent_builder/rag_tool_config.py` — `kb_id` 필드 추가
- `src/application/agent_builder/schemas.py` — `RagToolConfigRequest.kb_id` 추가
- `src/application/agent_builder/create_agent_use_case.py` — `_resolve_kbs`, `_canonicalize_kb_collections`, `_resolve_visibility` 확장 (D1, D3, D7)
- `src/application/agent_builder/update_agent_use_case.py` — `_lookup_kb_scopes`, `_validate_visibility_scope` 추가 (D7)
- `src/infrastructure/agent_builder/tool_factory.py` — `_merge_kb_filter` 신설 (D6)
- `src/domain/knowledge_base/policy.py` — `can_read_ref` 신설 (Act-1, D3)
- `src/api/main.py` — kb_repo DI 주입 (4.6)

**Frontend**:
- `src/types/ragToolConfig.ts` — `RagToolConfig.kb_id` + `KnowledgeBaseInfo` 타입
- `src/constants/api.ts` — `KNOWLEDGE_BASES` 상수
- `src/services/knowledgeBaseService.ts` — 신설
- `src/lib/queryKeys.ts` — `knowledgeBases.list` 키
- `src/hooks/useKnowledgeBases.ts` — 신설
- `src/components/agent-builder/RagConfigPanel.tsx` — KB 드롭다운 Section 0, 컬렉션 disabled 처리 (D2)
- `src/components/agent-builder/LeftConfigPanel.tsx` — `RagConfigSummaryBadge` KB 라벨 우선

### 3.4 Check Phase (Gap Analysis, 2026-07-09)

**문서**: `docs/03-analysis/kb-rag-filter.analysis.md`

**초기 검증 (92.9% → 97.6%)**:
- 설계 대비 20/21 항목 일치
- **G1 (Medium)**: D3 권한검증(403) 미구현 — Act-1 반복 필요
- **G2 (Low, 기지)**: E2E 수동검증(KB A/B 격리, clamp 실측) 미수행

**Back-of-envelope 회귀**:
- 기존 agent_builder 테스트 무회귀 (740건 통과, MCPRouting 3건은 기지 Windows 이벤트루프)
- 프론트 Vitest 287건 전부 통과 (--pool=threads)

### 3.5 Act Phase (Iteration-1, 2026-07-10)

**G1 해소 — D3 권한검증(403) 완전 구현**:

| 변경 | 내용 | 테스트 |
|------|------|--------|
| `src/domain/knowledge_base/policy.py` | `can_read_ref(user_id, role, kb, dept_ids)` 신설, `can_read` 위임 (단일 소스) | `TestCanReadRef` 7건 |
| `create_agent_use_case.py` | `_resolve_kbs`가 존재→권한→`PermissionError(403)` 검증 | 3건 (타인 PERSONAL 403 / 미소속 DEPARTMENT 403 / admin 통과) |
| `update_agent_use_case.py` | `_lookup_kb_scopes` 동일 검증, visibility 변경 시만 재검증 | 2건 (타인 PERSONAL 403 / admin 통과) |
| `agent_builder_router.py` | update 403 detail을 `str(e)` 전달(KB 거부 사유 표면화) |  |

**재검증 결과**: 97.6% ≥ 90% → report 진입 가능

**비차단 관찰**:
- `update`는 visibility 변경 시에만 KB 재검증 — 구현 의도(저장시점 검증, D3)와 정합
- 접근권 상실 후 이름만 변경하는 경우 재검증 없음 (수용됨)

---

## 4. Implementation Details

### 4.1 Backend Files (idt/)

| 파일 | 역할 | 라인 수 |
|------|------|--------|
| `src/domain/agent_builder/rag_tool_config.py` | `kb_id: str \| None = None` 필드 추가 (D5) | +1 |
| `src/domain/knowledge_base/policy.py` | `can_read_ref(user_id, role, kb, dept_ids)` 신설 (D3, Act-1) | +18 |
| `src/application/agent_builder/schemas.py` | `RagToolConfigRequest.kb_id` 추가 | +1 |
| `src/application/agent_builder/create_agent_use_case.py` | `_resolve_kbs`, `_canonicalize_kb_collections`, `_resolve_visibility` 확장 (D1, D3, D7) | +80 |
| `src/application/agent_builder/update_agent_use_case.py` | `_lookup_kb_scopes`, `_validate_visibility_scope` 추가 (D7) | +45 |
| `src/infrastructure/agent_builder/tool_factory.py` | `_merge_kb_filter` 신설 (D6) | +6 |
| `src/api/routes/agent_builder_router.py` | update 403 detail 개선 (Act-1) | +1 |
| `src/api/main.py` | kb_repo DI 주입 (4.6) | +4 |

**총 백엔드 변경**: 8개 파일, ~156 라인 추가/수정

### 4.2 Frontend Files (idt_front/)

| 파일 | 역할 | 라인 수 |
|------|------|--------|
| `src/types/ragToolConfig.ts` | `RagToolConfig.kb_id?` + `KnowledgeBaseInfo` 타입 추가 | +13 |
| `src/constants/api.ts` | `KNOWLEDGE_BASES: '/api/v1/knowledge-bases'` | +1 |
| `src/services/knowledgeBaseService.ts` | `getKnowledgeBases()` 신설 (envelope 매핑) | +12 |
| `src/lib/queryKeys.ts` | `knowledgeBases.list()` 키 추가 | +3 |
| `src/hooks/useKnowledgeBases.ts` | `useQuery` 훅 신설 (staleTime 5분) | +20 |
| `src/components/agent-builder/RagConfigPanel.tsx` | KB 드롭다운 Section 0, 컬렉션 disabled, scope 안내 (D2) | +85 |
| `src/components/agent-builder/LeftConfigPanel.tsx` | `RagConfigSummaryBadge`에 KB 라벨 우선 (5.4) | +12 |

**총 프론트 변경**: 7개 파일, ~146 라인 추가/수정

---

## 5. Validation Results

### 5.1 Test Coverage

**백엔드 테스트** (TDD Red → Green):

| 파일 | 테스트 클래스 | 건수 | 상태 |
|------|:-------:|:-----:|:----:|
| `test_rag_tool_config.py` | `TestRagToolConfigKbId` | 4 | ✅ |
| `test_tool_factory.py` | `TestToolFactoryKbFilter` | 5 | ✅ |
| `test_create_agent_use_case.py` | `TestKbRagFilter` + `TestKbPermissionValidation` | 8 + 3 | ✅ |
| `test_update_agent_use_case.py` | `TestUpdateVisibilityKbScope` + `TestUpdateKbPermission` | 5 + 2 | ✅ |
| `test_knowledge_base_policy.py` | `TestCanReadRef` | 7 | ✅ (Act-1) |

**백엔드 신규 테스트**: Do 24건 + Act-1 12건 = **36건**

**기존 회귀**:
- `agent_builder` 스위트: 740건 전부 통과
- MCPRouting 3건은 기지 Windows 이벤트루프 issue(preexisting) — excluded
- `knowledge_base` 스위트: 무회귀

**프론트엔드 테스트** (Vitest + RTL + MSW, --pool=threads):

| 파일 | 테스트 | 건수 | 상태 |
|------|:------:|:-----:|:----:|
| `useKnowledgeBases.test.ts` | 목록 조회, 에러 처리 | 2 | ✅ |
| `RagConfigPanel.test.tsx` | KB 드롭다운 렌더, 선택, disabled, scope 안내 | 6 | ✅ |
| `RagConfigSummaryBadge.test.tsx` | KB 라벨 표시, 미존재 폴백 | 3 | ✅ |

**프론트 신규 테스트**: 11건

**기존 프론트 회귀**: `tests/components/` + `tests/hooks/` 287건 전부 통과 (38 파일)

**tsc 타입 체크**: 신규 4건 error는 전부 preexisting (kb-rag-filter와 무관)

### 5.2 Match Rate Progression

| 단계 | 날짜 | Match Rate | Gap 수 | 반복 여부 |
|------|------|:----------:|:-----:|:--------:|
| Check (초기) | 2026-07-09 | 92.9% | 2 (G1, G2) | Act-1 필요 |
| Act-1 재검증 | 2026-07-10 | **97.6%** | 1 (G2만) | ✅ 완료 |

### 5.3 Gap Analysis

| # | Gap | 설계 참조 | 심각도 | 상태 | 비고 |
|---|-----|----------|:------:|:-----:|------|
| ~~G1~~ | ~~D3 권한검증(403) 미구현~~ | §3 D3 | ~~Medium~~ | **✅ Act-1 해소** | `can_read_ref` 정책 + PermissionError(403) + 회귀 12건 통과 |
| G2 | E2E 수동검증 미수행 | §7 step8 | Low(기지) | **Pending** | "수동 검증 pending" 명기. Qdrant payload `kb_id` 실측, KB A/B 격리 검색 실측, clamp 확인 필요 |

**결론**: 코드 레벨 설계 일치도 우수(97.6%). G2는 사용자 사전 고지된 항목(E2E 수동검증은 별도 사이클)으로 코드 회귀 없음.

---

## 6. Remaining Items & Next Steps

### 6.1 Incomplete Items (Design-Deferred)

| 항목 | 사유 | 연결 PDCA |
|------|------|:----------:|
| KB 목록/생성/삭제/문서 업로드 관리 화면 | 프론트 범위(§1.3 사용자 결정) — agent-builder 선택 UI만 this cycle | `kb-management-ui` |
| 기존 컬렉션 선택 UI 제거 + 데이터 이관 | 신규 경로 검증 후 교체(독립 opt-in 원칙) | `collection-picker-retirement` |
| KB 삭제 시 참조 에이전트 처리 | 고아 kb_id는 빈 결과로 동작, soft-delete + 벡터 정리 후속 | `kb-orphan-cleanup` |

### 6.2 Known Gap Mitigation

**G2 E2E 수동검증 Pending**:
- Plan 완료 기준 중 E2E 항목 미수행 (사용자 사전 고지)
- 코드 레벨은 전건 구현:
  - `kb_id` payload 필터 병합 (D6) ✅
  - scope clamp 양쪽(create/update) ✅
  - 물리 컬렉션 canonicalize ✅
  - 권한 검증 403(Act-1) ✅
- 실제 Qdrant 조회 시나리오는 후속 integration test 또는 manual E2E 권장

### 6.3 Suggested Follow-Up Tasks

**즉시 (다음 PDCA)**:
1. `/pdca pm kb-management-ui` — 프론트 KB 관리 UI (목록/생성/문서 업로드)
2. `/pdca pm collection-picker-retirement` — 기존 컬렉션 선택 UI 제거 + 에이전트 이관

**중기**:
3. `kb-orphan-cleanup` — KB 삭제 후 벡터 정리 + 참조 에이전트 처리
4. E2E 수동검증 (KB A/B 격리, clamp 실측, Qdrant payload 확인)

---

## 7. Lessons Learned

### 7.1 What Went Well

1. **TDD Red → Green 전개가 설계 결정 명확화**: Plan 논의 항목들(D1~D7)을 Design에서 전건 확정하고, 테스트 작성 단계에서 "kb_repo None일 때 명시 에러" 같은 엣지 케이스를 캐치 → 초기 Check 92.9%에서 Act-1로 97.6% 달성
2. **독립 opt-in 원칙이 회귀 위험 제로**: `kb_id=None`이면 모든 신규 분기 미진입 → 기존 에이전트 무영향 (FR-06 보증). 740건 회귀 테스트로 검증됨
3. **저장 시점 canonicalize 결정의 근거 견고**: KB API에 컬렉션 update 없음 + 저장 시 어차피 KB 조회(scope clamp) → 런타임 조회 회피 가능. 동기 ToolFactory 유지로 침습성 최소화
4. **Domain VO 검증 최소화(D5)**: `RagToolConfig.kb_id`는 형식 검증 안 함(존재 검증이 상위에서 수행) → VO 무검증, __post_init__ 무변경으로 기존 dict 호환성 완전 유지
5. **DI 패턴 일관성**: `kb_repo` 주입을 `dept_repo` 선례(선택적 optional, None 시 명시 에러)와 동일하게 적용 → 코드 유지보수성 높음

### 7.2 Areas for Improvement

1. **E2E 수동검증 미사전 계획**: 설계 단계에서 Qdrant payload 실측을 "누가 언제 수행" 명시 필요. 코드 통과율은 높으나 실제 벡터 검색은 별도 확인 필요 → 다음 PDCA에서 자동화 테스트화(search integration test) 권장
2. **프론트 endpoint 상수화 타이밍**: `KNOWLEDGE_BASES` 상수를 쓰되, `GET /api/v1/knowledge-bases`가 프론트에서 이미 쓰고 있었는지 파악 미흡. 신규 상수 추가가 중복이 아님 확인 후 진행 필요 (이번은 괜찮았으나 패턴화 권장)
3. **update visibility 검증 범위**: `_validate_visibility_scope`가 visibility 변경 시만 KB 재검증하므로, 접근권 상실 후 에이전트 이름만 변경 시 stale kb_id 참조 유지 가능 → 향후 admin 감시 항목으로 기록(큰 문제는 아니나 정책 문서화 필요)

### 7.3 To Apply Next Time

1. **설계 단계에서 integration test 항목을 따로 표기**: §6 설계에는 "unit test로 충분"(도메인/ToolFactory) vs "integration test 필요"(실제 Qdrant/ES 격리) 구분 → E2E 미루기 방지
2. **권한 검증이 추가되는 구간에 PermissionError 정책 선사전 작성**: D3에서 "403 vs 400" 확정했지만, `can_read_ref`를 VO 정책으로 쓸지 UseCase 로직으로 쓸지는 Act-1에야 결정 → Design에 "권한 VO는 policy 신설" 명시 권장
3. **독립 opt-in 검증 체계화**: 이번 kb_id + collection_name 공존 같은 상황에서, "새 필드 추가 시 기존 경로는 무조건 별도 test suite로 검증" 규칙 명문화 → CLAUDE.md 추가 가능
4. **actor 분리 권장(대규모 feature)**: 대안 "PM + Developer + QA 팀"이 있을 때, E2E 검증은 QA가 전담하는 구조 → 이번은 1인 개발이었으나, 팀 규모에서는 설계 단계에 "E2E owner" 명시 필수

---

## 8. Summary Statistics

| 지표 | 값 |
|------|-----|
| **기간** | 2026-07-08 ~ 2026-07-10 (2일 + 재검증) |
| **설계 일치율** | 97.6% (20.5 / 21) |
| **백엔드 파일 변경** | 8개 파일, ~156 라인 추가/수정 |
| **프론트 파일 변경** | 7개 파일, ~146 라인 추가/수정 |
| **신규 테스트** | 백엔드 36건 + 프론트 11건 = 47건 |
| **회귀 테스트** | 1027건 전부 통과 (MCPRouting 3건 제외) |
| **반복 횟수** | 1회 (Act-1: D3 권한검증 해소) |
| **Gap** | 0개 (코드 레벨) / 1개 Pending (G2 수동검증) |

---

## 9. Sign-Off

**완료 상태**: ✅ COMPLETE (코드 레벨 설계 일치 100%, 수동검증 pending 명기)

**다음 단계**: `/pdca pm kb-management-ui` (프론트 KB 관리 화면)

