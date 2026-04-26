# Analysis: agent-collection-visibility-sync

> Feature: 에이전트 생성 시 컬렉션 scope 기반 visibility 자동 상속
> Design: `docs/02-design/features/agent-collection-visibility-sync.design.md`
> Analyzed: 2026-04-26
> Match Rate: **93%** (13/14 items)
> Iteration: Act-1 적용 후 86% → 93%

---

## 1. 설계 vs 구현 매칭 결과

### 1.1 Backend 구현 파일 (6/6 — 100%)

| # | 설계 항목 | 파일 | 상태 | 비고 |
|---|----------|------|:----:|------|
| 1 | `SCOPE_TO_VISIBILITY`, `VISIBILITY_RANK`, `max_visibility_for_scopes()`, `clamp_visibility()` | `src/domain/agent_builder/policies.py` | ✅ | 설계와 완전 일치. Visibility Enum도 추가됨 |
| 2 | DI에 `perm_repo` 추가, `_resolve_visibility()`, `_extract_collection_names()`, `_lookup_collection_scopes()`, Step 2.5 | `src/application/agent_builder/create_agent_use_case.py` | ✅ | 설계와 일치. tuple 반환으로 clamped/max_vis 전달 |
| 3 | DI에 `perm_repo` 추가, visibility 변경 시 scope 검증 (explicit reject) | `src/application/agent_builder/update_agent_use_case.py` | ✅ | 설계 대로 ValueError raise |
| 4 | `CreateAgentResponse`에 `visibility_clamped`, `max_visibility` 필드 | `src/application/agent_builder/schemas.py` | ✅ | 설계와 일치 |
| 5 | `CollectionInfo.scope` 추가, `list_collections`에 권한 필터 + scope 조회 | `src/api/routes/rag_tool_router.py` | ✅ | DI 플레이스홀더 포함 |
| 6 | CreateAgentUseCase → perm_repo, rag_tool_router → perm_service DI 연결 | `src/api/main.py` | ✅ | 두 DI 모두 연결 확인 |

### 1.2 Backend 테스트 (4/4 — 100%)

| # | 설계 항목 | 파일 | 상태 | 테스트 수 |
|---|----------|------|:----:|:---------:|
| T1 | `max_visibility_for_scopes`, `clamp_visibility` 단위 테스트 | `tests/domain/agent_builder/test_visibility_policy.py` | ✅ | 17개 (기존 can_access 포함) |
| T2 | scope 기반 visibility 자동 조정 통합 테스트 | `tests/application/agent_builder/test_create_agent_use_case.py` | ✅ | 11개 (5개 visibility clamping) |
| T3 | visibility 초과 시 에러 반환 테스트 | `tests/application/agent_builder/test_update_agent_use_case.py` | ✅ | 8개 (3개 scope 검증) |
| T4 | 컬렉션 권한 필터링 + scope 포함 테스트 | `tests/api/test_rag_tool_router.py` | ✅ | 8개 (2개 scope/필터) |

**전체 테스트**: 54개 PASSED (5.75s), 0 FAILED

### 1.3 Frontend 구현 파일 (2/3 — 67%)

| # | 설계 항목 | 파일 | 상태 | 비고 |
|---|----------|------|:----:|------|
| 7 | `CollectionInfo.scope` 타입 추가 | `idt_front/src/types/ragToolConfig.ts` | ✅ | `CollectionScope` 타입도 export |
| 8 | scope 뱃지 표시 | `idt_front/src/components/agent-builder/RagConfigPanel.tsx` | ✅ | SCOPE_LABELS 색상 매핑, 드롭다운 뱃지 + 인라인 안내문 |
| 9 | `visibility_clamped` 시 toast 안내 | `idt_front/src/pages/AgentBuilderPage/index.tsx` | ❌ | 미구현 — 페이지가 아직 mock 데이터 기반 |

### 1.4 Frontend 테스트 (1/1 — 100%) [Act-1에서 보완]

| # | 설계 항목 | 파일 | 상태 | 비고 |
|---|----------|------|:----:|------|
| T5 | scope 뱃지 렌더링 테스트 | `idt_front/src/components/agent-builder/RagConfigPanel.test.tsx` | ✅ | Act-1에서 추가 (5개 테스트) |

---

## 2. Gap 상세 분석

### Gap 1: AgentBuilderPage visibility_clamped toast (설계 항목 #9) — 잔여 Gap

- **설계 요구**: `CreateAgentResponse.visibility_clamped === true`일 때 toast 표시
- **현재 상태**: AgentBuilderPage가 mock 데이터(`MOCK_AGENTS`)로 동작하며 실제 API를 호출하지 않음
- **영향**: 백엔드에서 자동 조정된 visibility를 사용자에게 알려줄 수 없음
- **의존성**: API 통합(실제 POST /agents 호출)이 선행되어야 toast 구현이 의미 있음
- **심각도**: Medium — RagConfigPanel의 인라인 안내문이 부분적 대체 역할 수행
- **결론**: API 통합 feature에서 함께 구현 예정. 현재 단계에서는 구조적으로 불가

### ~~Gap 2: RagConfigPanel.test.tsx (설계 항목 #T5)~~ — Act-1에서 해결

- **해결**: `RagConfigPanel.test.tsx` 생성 (5개 테스트)
- **추가 수정**: MSW handler에 `scope` 필드 추가 (API 계약 동기화)

---

## 3. 설계 규칙 준수 확인

| 규칙 | 준수 | 근거 |
|------|:----:|------|
| domain → infrastructure 참조 금지 | ✅ | `VisibilityPolicy`는 순수 문자열만 처리 |
| router에 비즈니스 로직 금지 | ✅ | `rag_tool_router`는 `perm_service` 호출만 |
| TDD 필수 | ✅ | 백엔드 테스트 54개 전체 통과 |
| 함수 40줄 미만 | ✅ | 모든 신규 메서드 10줄 이내 |
| API 계약 동기화 | ✅ | `CollectionInfo.scope` 백엔드↔프론트 동시 반영 |
| Repository 내부 commit/rollback 금지 | ✅ | `find_by_collection_name`은 조회만 |
| print() 금지, logger 사용 | ✅ | 기존 logger 패턴 유지 |

---

## 4. 품질 메트릭

| 메트릭 | 이전 (Check) | 현재 (Act-1) |
|--------|:-----------:|:------------:|
| **Match Rate** | 86% (12/14) | **93% (13/14)** |
| Backend Match | 100% (10/10) | 100% (10/10) |
| Frontend Match | 50% (2/4) | **75% (3/4)** |
| 백엔드 테스트 | 54 passed | 54 passed |
| 프론트엔드 테스트 | — | 10 passed (5 hook + 5 component) |
| 아키텍처 위반 | 0건 | 0건 |

---

## 5. Act-1 변경 사항

| 파일 | 변경 내용 |
|------|----------|
| `idt_front/src/components/agent-builder/RagConfigPanel.test.tsx` | 신규 생성 — scope 뱃지 렌더링 5개 테스트 |
| `idt_front/src/__tests__/mocks/handlers.ts` | 컬렉션 mock에 `scope` 필드 추가 (API 계약 동기화) |

---

## 6. 잔여 Gap 및 권장 사항

| 우선순위 | 항목 | 상태 |
|:--------:|------|:----:|
| ~~P2~~ | ~~RagConfigPanel.test.tsx 테스트 추가~~ | ✅ Act-1 해결 |
| P3 | AgentBuilderPage API 통합 후 visibility_clamped toast 추가 | 별도 feature 의존 |

> **결론**: Match Rate **93%** (>= 90%) 달성. 백엔드 100%, 프론트엔드 75%.
> 잔여 Gap 1건(toast)은 AgentBuilderPage API 통합 시 함께 구현 예정.
> **Report 단계 진행 가능.**
