# tool-access-control Planning Document

> **Summary**: 도구(내부 도구·MCP 도구)마다 사용할 수 있는 부서·사용자를 관리자가 지정하게 한다. 지정되지 않은 도구는 기본 차단하고, 관리자가 관리하는 "기본 허용 도구" 세트만 전원에게 열린다. 도구 목록 조회, 에이전트 저장, 실행 세 지점에서 실행자 기준으로 판정한다.
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-03
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 도구 카탈로그(`GET /api/v1/tool-catalog`)는 로그인한 모든 사용자에게 활성 도구 전체를 돌려주고, 실행 시 권한을 확인하는 도구는 `internal_document_search` 하나뿐이다. 부서·직무와 관계없이 누구나 MCP 도구·코드 실행기 등으로 사내 시스템과 자료에 접근할 수 있다. |
| **Solution** | 도구별 허용 규칙(기본 허용 세트 + 부서 허용 + 사용자 허용, 합집합)을 저장하고, 규칙이 없는 도구는 차단한다. 판정 정책 하나를 카탈로그 조회·에이전트 저장·실행(서브에이전트·스케줄·잡·웹훅 포함)에서 공유한다. 인증이 없던 MCP 레지스트리 API도 이번 범위에서 막는다. |
| **Function/UX Effect** | 관리자는 부서·사용자를 고르고 도구 체크리스트에서 허용할 도구를 선택한다. 이때 기본 허용 도구와 부서에서 상속된 도구는 체크·잠금 상태로 표시된다. 일반 사용자는 도구 선택 화면에 허용된 도구만 보이며, 권한 없는 도구가 붙은 공개 에이전트를 실행하면 그 도구만 빠지고 안내가 표시된다. |
| **Core Value** | P2가 만든 에이전트를 전 부서에 배포해도 각 사용자는 자신에게 허용된 도구로만 자료에 접근한다. 확장 경로(여신 부서 → 전 부서 → 그룹)에서 필요한 접근 통제를 코드 수정 없이 데이터로 운영한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 도구 선택·실행에 부서·사용자 조건이 없어 권한과 관계없이 누구나 도구를 통해 자료에 접근한다. |
| **WHO** | P3 시스템 관리자(권한 지정), P2 에이전트 소유자(허용된 도구로 구성·배포), P1·P4 실행 사용자(허용된 도구만 사용). |
| **RISK** | 기본 차단 전환으로 기존 에이전트 도구가 일제히 막히는 회귀, 실행 경로 중 판정이 빠진 우회로(서브에이전트·빌트인 주입·서버 단위 MCP 참조·포크), 도구 ID 이중 네임스페이스로 인한 판정 불일치. |
| **SUCCESS** | 배포 직후 기존 에이전트 동작 변화 0건(기본 세트 시드), 권한 없는 도구가 목록·저장·실행 어느 경로로도 쓰이지 않음(실행 경로 전수 테스트), MCP 레지스트리 무인증 호출 401. |
| **SCOPE** | M1 판정 정책·저장소·마이그레이션 → M2 관리자 권한 API + MCP 레지스트리 인증 → M3 목록·저장·포크 적용 → M4 실행 시점 필터(전 실행 경로) → M5 관리자 권한 화면 → M6 빌더·채팅 표시 |

---

## 1. Overview

### 1.1 Purpose

관리자가 도구마다 사용할 수 있는 부서·사용자를 지정하고, 지정된 범위 밖의 사용자는 그 도구를 고를 수도, 실행할 수도 없게 한다.

### 1.2 Background

코드 대조 결과는 다음과 같다.

| 항목 | 현재 상태 | 근거 |
|------|----------|------|
| 부서 | `department`, `user_department`(다중 소속, `is_primary`) 존재 | `idt/src/domain/department/entity.py` |
| 권한 코드 | `role_permissions` ∪ `user_permissions`. 코드 8개, 부서 단위 부여 없음 | `idt/src/domain/permission/resolver.py`, `V029__seed_permissions.sql` |
| 런타임 사용자 정보 | `AuthContext`에 `department_ids`, `permissions` 포함. 웹훅·백그라운드 잡도 트리거 소유자 기준 `auth_ctx`를 넘김 | `domain/agent_run/auth_context.py`, `invoke_webhook_agent_use_case.py:94`, `background_job/worker.py:303` |
| 도구 카탈로그 조회 | `list_active()` 결과 전체 반환. 사용자 조건 없음 | `application/tool_catalog/list_tool_catalog_use_case.py` |
| 실행 시 도구 권한 확인 | `internal_document_search`만 `USE_RAG_SEARCH`·`READ_DEPARTMENT_DOCS` 확인. `USE_WEB_SEARCH`는 정의만 있고 확인하는 코드 없음. MCP·코드 실행기·문서 생성기 등은 확인 없음 | `application/rag_agent/tools.py:163,179` |
| KB 접근 | `PERSONAL/DEPARTMENT/PUBLIC` 범위로 판정 (이번 범위 밖, 그대로 둔다) | `domain/knowledge_base/policy.py` |
| 에이전트 접근 | `private/department/public` + `VisibilityPolicy.can_access`. 접근 가능하면 붙은 도구를 모두 사용 | `run_agent_use_case.py:820-840` |
| MCP 레지스트리 API | 6개 엔드포인트에 인증 의존성 없음. 프론트 소비처는 `/admin/mcp-servers` 하나 | `api/routes/mcp_registry_router.py`, `idt_front/src/services/mcpServerService.ts` |

### 1.3 Related Documents

- 유저 시나리오: `docs/USER-SCENARIOS.md` (P2 주인공, 일반화 우선)
- 위키: `docs/wiki/backend/db/erd-tool-catalog.md` (sync 보존 컬럼 규칙, 서버 삭제 CASCADE), `docs/wiki/backend/api/router-map.md` (도구 ID 이중 네임스페이스), `docs/wiki/conventions/additive-contract-extension.md`, `docs/wiki/conventions/false-green-quality-gates.md`
- 선행 설계: agent-user-context (AuthContext·PermissionCode), builtin-tools, approval-gate (`tool_catalog` 관리자 컬럼 패턴)

---

## 2. Scope

### 2.1 In Scope

- [ ] 도구 허용 규칙 저장: 기본 허용 세트, 부서 허용, 사용자 허용 (개별 tool_id 단위)
- [ ] 판정 정책 1개: `admin` 전부 허용 / 기본 세트 / 소속 부서 중 하나라도 허용 / 사용자 허용 → 합집합. 그 외 차단
- [ ] 배포 마이그레이션: 현재 카탈로그의 모든 도구를 기본 세트로 시드. 이후 sync로 새로 들어오는 도구는 기본 차단
- [ ] 관리자 API: 기본 세트·부서별·사용자별 허용 도구 조회/전체 교체
- [ ] 관리자 화면(부서·사용자 중심): 대상 선택 → 도구 체크리스트. 기본 세트·부서 상속분은 체크·잠금 + 출처 표시
- [ ] 도구 카탈로그 조회 필터: 비관리자는 허용 도구만 받음
- [ ] 에이전트 생성·수정 저장 검증: 새로 추가한 도구가 허용 밖이면 403. 기존에 붙어 있던 도구는 유지 허용
- [ ] 포크: 포크하는 사용자에게 허용되지 않은 도구는 빼고 복제, 제외 목록을 응답으로 반환
- [ ] 빌트인 자동 주입: 생성자에게 허용되지 않은 빌트인은 주입하지 않음
- [ ] 실행 시점 필터: 실행자 기준으로 허용되지 않은 도구는 바인딩하지 않고 실행 계속. 채팅·서브에이전트 워커·스케줄·백그라운드 잡·웹훅 전 경로
- [ ] 실행 시 제외 안내: 제외된 도구를 사용자에게 알림 (additive 응답 필드 + 답변 안내)
- [ ] 빌더 표시: 에이전트에 붙어 있으나 현재 사용자에게 허용되지 않은 도구에 "권한 없음" 표시
- [ ] MCP 레지스트리 API 인증: 등록·수정·삭제·연결 테스트·조회 모두 admin 전용 (v0.2 — 조회 응답에 사내 서버 주소가 실려 Do 단계에서 변경)

### 2.2 Out of Scope

- 사용자 단위 차단(deny) 규칙 — 합집합 모델만 둔다. 필요해지면 `PermissionResolver`의 deny 확장 지점에서 후속 처리
- 부서 관리자 역할 신설, 부서 관리자의 권한 위임 — 관리 주체는 시스템 관리자만
- MCP 서버 단위 규칙·상속 — 개별 도구 단위만. 화면에서 "서버 도구 일괄 선택"은 편의 기능으로만 제공
- 별도 권한 그룹(역할 그룹) 신설
- KB·컬렉션·스킬·서브에이전트 자체의 접근 범위 변경 (KB는 기존 범위 판정 유지)
- 소유자 권한 위임 실행(소유자 권한으로 남에게 도구 실행)
- 기존 권한 코드(`USE_RAG_SEARCH`, `USE_WEB_SEARCH`) 정리 — `USE_RAG_SEARCH` 확인은 도구 권한과 별개의 추가 검사로 그대로 둔다. `USE_WEB_SEARCH` 미사용 상태는 그대로 두고 보고만 한다
- 권한 변경 이력(감사 로그) 화면 — 규칙 행에 `granted_by`·`granted_at`만 남긴다

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 도구 허용 규칙을 저장한다. 대상은 기본 세트(전원), 부서, 사용자 3종이며 키는 카탈로그 `tool_id`다. 규칙에 부여자·부여 시각을 남긴다. | High | Pending |
| FR-02 | 판정 정책 `ToolAccessPolicy`: 실행자 역할이 `admin`이면 허용. 그 외에는 기본 세트 ∪ 소속 부서 허용(다중 소속은 하나라도) ∪ 사용자 허용에 포함될 때만 허용. 익명 `AuthContext`는 전부 차단(Fail-Closed). 판정은 이 정책 한 곳에서만 한다. | High | Pending |
| FR-03 | 배포 마이그레이션이 현재 `tool_catalog`의 모든 도구를 기본 세트로 시드한다. 이후 MCP sync·내부 도구 sync로 새로 생기는 도구는 기본 세트에 들어가지 않는다(기본 차단). sync는 기본 세트 여부를 덮어쓰지 않는다. | High | Pending |
| FR-04 | 관리자 API: 기본 세트, 부서별, 사용자별 허용 도구를 조회하고 전체 교체(PUT)한다. 사용자별 조회는 사용자 직접 허용 외에 기본 세트·부서 상속분을 출처와 함께 돌려준다. `admin` 전용. | High | Pending |
| FR-05 | `GET /api/v1/tool-catalog`: 비관리자에게는 허용된 도구만 반환한다. 관리자는 기존과 같이 전체를 받는다. 응답 스키마는 변경하지 않는다(필요 시 optional 필드만 추가). | High | Pending |
| FR-06 | 에이전트 생성·수정·자동 생성(위저드·파이프라인·compose 포함) 저장 시, 기존 정의에 없던 도구 중 저장하는 사용자에게 허용되지 않은 것이 있으면 403과 해당 tool_id 목록을 반환한다. 기존 정의에 이미 있던 도구는 허용 여부와 무관하게 유지 저장된다. | High | Pending |
| FR-07 | 빌트인 도구 자동 주입 시 생성자에게 허용되지 않은 빌트인은 주입하지 않는다. | Medium | Pending |
| FR-08 | 포크 시 포크하는 사용자에게 허용되지 않은 도구는 복제본에서 제외하고, 제외된 tool_id·이름 목록을 응답에 담는다. | Medium | Pending |
| FR-09 | 실행 시점 필터: 그래프 컴파일 전에 실행자 `AuthContext` 기준으로 허용되지 않은 도구를 바인딩 목록에서 뺀다. 메인 에이전트, 서브에이전트 워커, 카테고리 워커(search/collect/analysis/action) 모두 적용한다. 에이전트 실행은 계속된다. | High | Pending |
| FR-10 | 실행 주체: 채팅은 채팅 사용자, 스케줄·백그라운드 잡은 등록한 사용자, 웹훅은 현재 코드가 넘기는 소유자 `auth_ctx`를 기준으로 판정한다. `auth_ctx` 없이 `RunAgentUseCase`를 호출하는 경로를 Design에서 전수 확인한다. | High | Pending |
| FR-11 | 실행 중 제외된 도구가 있으면 사용자에게 알린다. 응답(REST·WS)에 optional 필드로 제외 목록을 추가하고, 모델 지시문에 "권한이 없어 사용할 수 없는 도구"를 넣어 답변에서 안내하게 한다. 실행 기록에도 제외 사실을 남긴다. | Medium | Pending |
| FR-12 | MCP 서버 단위 레거시 참조(`mcp_{server}`)는 서버 도구 중 허용된 도구만 바인딩한다. 허용된 도구가 없으면 참조 전체를 뺀다. | High | Pending |
| FR-13 | 에이전트 조회 응답의 도구 항목에 현재 사용자 기준 허용 여부(optional)를 추가하고, 빌더는 허용되지 않은 도구를 "권한 없음"으로 표시한다. 도구 선택 모달(`ToolPickerModal`)은 필터된 카탈로그만 보여 준다. | Medium | Pending |
| FR-14 | 관리자 화면(부서·사용자 중심): `/admin` 하위에 "도구 권한" 메뉴를 추가하고 기본 세트 / 부서 / 사용자 탭을 둔다. 부서·사용자 탭은 대상 선택 → 전체 도구 체크리스트를 표시한다. 기본 세트 도구는 체크·잠금("기본"), 사용자 탭에서 부서 상속 도구는 체크·잠금("부서: 이름")으로 표시한다. MCP 서버별 일괄 선택 버튼을 제공한다. | High | Pending |
| FR-15 | 기본 세트 탭에서 빌트인이지만 기본 세트가 아닌 도구, 기본 세트가 아닌 승인 필요 도구 등 상태를 표시해 관리자가 의도치 않은 차단을 알 수 있게 한다. 신규 sync 도구는 "미지정(차단)" 표시. | Low | Pending |
| FR-16 | MCP 레지스트리 API 인증: 6개 엔드포인트 전부 `require_role("admin")` (라우터 단위). 무인증 401, 비관리자 403. 조회도 admin 전용인 이유: 응답에 사내 서버 주소(`endpoint`)·`server_config`가 실리고 프론트 소비처가 `/admin/mcp-servers` 하나뿐이다 (v0.2, Do 단계 사용자 결정). | High | Pending |
| FR-17 | 도구가 카탈로그에서 삭제되면(MCP 서버 삭제 CASCADE 포함) 해당 허용 규칙도 함께 삭제된다. 부서·사용자 삭제 시 해당 대상 규칙도 정리된다. | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Security | 권한 없는 도구가 목록·저장·포크·실행(5개 실행 경로) 어디서도 바인딩되지 않음. 서버 측 판정이 화면 필터와 독립적으로 동작 | 경로별 API 테스트 + 컴파일 그래프 실행 테스트(AsyncMock 단독 금지) |
| Security | MCP 레지스트리 무인증 401, 비관리자 쓰기 403 | API 테스트 |
| Compatibility | 배포 직후 기존 에이전트의 바인딩 도구 목록 변화 0건 | 시드 후 판정 결과 비교 테스트 |
| Compatibility | 기존 API 응답 스키마는 optional 필드 추가만 | 기존 프론트 테스트 회귀 0건 |
| Performance | 실행당 권한 조회 DB round-trip 추가 1~2회 이내 (요청당 1회 조회 후 메모리 판정) | 로그·테스트에서 쿼리 횟수 확인 |
| Regression | 회귀는 정렬된 `FAILED` 목록 diff로 증명 (master 상시 실패 목록 대비 신규 0건) | pytest / vitest 실행 결과 비교 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-17 구현, 각 FR에 대응하는 테스트 존재
- [ ] 실행 경로 5종(채팅 REST, 채팅 WS, 스케줄, 백그라운드 잡, 웹훅) + 서브에이전트 워커에서 권한 없는 도구 미바인딩을 컴파일 그래프 기준으로 검증
- [ ] 시드 마이그레이션 후 기존 에이전트 도구 바인딩 변화 0건 확인
- [ ] 백엔드 스키마 변경과 프론트 `src/types/`·`services`·`hooks` 동기화 (`/api-contract-sync`)
- [ ] `docs/wiki/ops/migration-deploy-deps.md` 반영 대상 기록 (위키 갱신은 `/wiki update` 호출 시)
- [ ] 관리자 화면에서 부서 허용 → 해당 부서원 도구 선택 화면에 노출, 허용 해제 → 실행 시 제외 안내까지 수동 E2E 1회

### 4.2 Quality Criteria

- [ ] 신규 코드 테스트 커버리지 80% 이상
- [ ] 백엔드 신규 실패 0건(FAILED diff), 프론트 `tsc -b`·lint·vitest 신규 실패 0건
- [ ] DDL 검사 통과 (FK collation 규칙, COMMENT 내 콤마 금지)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 기본 차단 전환으로 기존 에이전트 도구가 일제히 막힘 | High | High | FR-03 시드로 현재 도구 전부를 기본 세트에 넣는다. 시드 전후 판정 비교 테스트를 둔다. |
| 실행 경로 중 판정이 빠진 우회로(서브에이전트, 카테고리 워커, 빌트인 주입, `mcp_{server}` 참조, 포크, 자동 생성 경로) | High | Medium | 판정을 `ToolFactory` 바인딩 단계 한 곳에 두고, 경로별 배선 계약 테스트를 작성한다. Design에서 `RunAgentUseCase`·`ToolFactory` 호출자를 전수 표로 작성한다. |
| 도구 ID 이중 네임스페이스(`internal:xxx` vs 저장된 bare id, `mcp:{uuid}:{tool}` vs `mcp_{server}`)로 규칙과 실제 바인딩 id가 어긋남 | High | Medium | 규칙 키는 카탈로그 `tool_id`로 고정하고, 판정 전에 정규화 함수 하나를 거친다. 정규화 테스트를 표 형태로 고정한다. |
| `auth_ctx` 없이 실행되는 호출자가 Fail-Closed로 모든 도구를 잃음 | Medium | Medium | Design에서 호출자를 전수 조사한다. 누락 호출자는 `auth_ctx`를 넘기도록 고치고, 의도적 시스템 실행이 있으면 명시적으로 분리한다. |
| `tool_catalog` 컬럼 추가는 ORM 매핑이라 마이그레이션 미적용 시 카탈로그 조회 자체가 실패 | Medium | Medium | 기본 세트를 별도 테이블로 둘지 컬럼으로 둘지 Design에서 결정하고, 배포 의존성 문서에 기록한다. |
| 관리자가 MCP sync 후 새 도구를 열어 주지 않아 "도구가 안 보인다" 문의 | Low | High | FR-15 "미지정(차단)" 표시, sync 결과 응답에 신규 도구 수 표시. |
| 실행 중 도구 제외를 사용자가 오류로 오해 | Low | Medium | FR-11 안내 문구와 응답 필드. 빌더에서는 FR-13 "권한 없음" 표시. |
| MCP 레지스트리 인증 추가로 기존 호출자 깨짐 | Low | Low | 프론트 소비처는 `/admin/mcp-servers` 하나(확인함). 백엔드 내부 호출은 UseCase 직접 호출이라 영향 없음을 Design에서 재확인. |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| 도구 허용 규칙 (신규) | DB 테이블 / Flyway V082~ | 기본 세트·부서·사용자 허용 규칙. 기본 세트 표현 방식(별도 대상 행 vs `tool_catalog` 컬럼)은 Design에서 결정 |
| `ToolAccessPolicy` (신규) | Domain | 판정 단일 지점 |
| `ListToolCatalogUseCase` | Application | 실행자 기준 필터 |
| 에이전트 생성·수정·포크·자동 생성 UseCase | Application | 저장 시 신규 도구 검증, 포크 시 제외 |
| `ToolFactory.create_all_async` 및 서브에이전트 워커 빌더 | Infrastructure | 바인딩 전 필터, 제외 목록 수집 |
| `RunAgentUseCase` 응답 / WS 이벤트 | API 계약 | optional 제외 목록 필드 추가 |
| `mcp_registry_router.py` | API | 인증 의존성 추가 |
| 관리자 도구 권한 라우터 (신규) | API | 기본 세트·부서·사용자 조회/PUT |
| `idt_front` 관리자 도구 권한 페이지 (신규), `adminNav.ts`, `ToolPickerModal`, 빌더 도구 목록 | Frontend | 신규 화면, 권한 없음 표시 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `GET /tool-catalog` | READ | `idt_front/src/hooks/useToolCatalog.ts` → `ToolPickerModal`, `LeftConfigPanel`, `StudioLayout`, `visual/buildGraph` | 비관리자 결과가 줄어듦. 빌더가 카탈로그에 없는 기존 도구 이름을 못 찾는 경우 확인 필요 |
| `GET /tool-catalog` | READ | `AdminToolsPage` | 관리자라 전체 유지 — 영향 없음 |
| 에이전트 저장 | CREATE/UPDATE | `create_agent_use_case.py`, `update_agent_use_case.py`, auto_agent_builder, agent_create_pipeline, agent_composer | 403 경로 추가 |
| 포크 | CREATE | `fork_agent_use_case.py` | 도구 제외 + 응답 필드 추가 |
| 도구 바인딩 | READ | `tool_factory.py`, `sub_agent_worker_builder.py`, 카테고리 워커 노드 | 필터 추가 |
| 실행 | EXECUTE | 채팅 REST/WS(`agent_builder_router`, `ws_router`), `agent_schedule`, `background_job/worker.py`, `invoke_webhook_agent_use_case.py` | 실행자 기준 필터 |
| MCP 레지스트리 | CRUD | `idt_front/src/services/mcpServerService.ts` → `/admin/mcp-servers` | 관리자 토큰으로 호출 중이라 영향 없음 (Design에서 확인) |
| `tool_catalog` sync | UPDATE | `sync_mcp_tools_use_case.py`, `sync_internal_tools_use_case.py` | 기본 세트 보존 규칙 추가 |

### 6.3 Verification

- [ ] 위 소비처 전부에 대해 Design에서 변경 여부 표 작성
- [ ] 권한 추가가 관리자 기존 동작을 깨지 않음 (admin 전부 허용)
- [ ] 응답 필드 추가가 기존 쿼리·뮤테이션을 깨지 않음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | Complex architectures | ☑ |

기존 프로젝트 구조(`domain/application/infrastructure/interfaces`, `main.py` DI 단일 집중)를 따른다.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 권한 단위 | 부서만 / 부서+사용자 / +차단 / 역할 그룹 | 부서 + 사용자 (합집합) | 사용자 결정. 기존 `PermissionResolver` 합집합 정책과 일치 |
| 미지정 도구 | 전체 허용 / 기본 차단 / 도구별 | 기본 차단 + 살아있는 기본 세트 | 사용자 결정. 기본 세트는 전원에게 항상 적용, 변경 즉시 반영, 신규 가입자 포함 |
| 전환 | 전부 시드 / 빌트인만 / 시드 없음 | 현재 도구 전부 기본 세트 시드 | 배포 직후 동작 변화 0 |
| 확인 시점 | 목록 / 저장 / 실행 | 세 지점 모두 | 화면 필터만으로는 API 직접 호출·공개 에이전트로 우회 가능 |
| 권한 없는 실행 | 도구 제외 / 실행 차단 / 소유자 위임 | 도구 제외 후 실행 + 안내 | 기존 RAG 거부 메시지 방식과 같은 계열. 위임은 이번 문제를 해결하지 못함 |
| MCP 단위 | 도구 / 서버 / 서버+재정의 | 개별 도구 | 조회·쓰기 도구를 다르게 열 수 있음. 서버 일괄 선택은 화면 편의 기능 |
| 관리 주체 | 시스템 관리자 / 부서 관리자 / +MCP 등록자 | 시스템 관리자만 | 역할 체계 변경 없이 시작 |
| 저장 검증 | 신규만 / 전체 거부 / 자동 제거 | 새로 추가한 도구만 검증 | 다른 부서원이 쓰던 도구가 소유자 저장으로 사라지는 문제 방지 |
| 포크 | 제외 복제 / 그대로 / 거부 | 권한 없는 도구 제외 후 복제 | 복제본 소유자 기준 정합 |
| 비대화 실행 주체 | 트리거 생성자 / 에이전트 소유자 | 트리거 생성자 | 현재 각 경로가 넘기는 `auth_ctx` 그대로 사용 |
| 판정 위치 | 라우터 / UseCase / ToolFactory | Design에서 결정 (후보: 도메인 정책 + ToolFactory 바인딩 단계 필터 + UseCase 저장 검증) | 실행 경로가 많아 바인딩 단계 단일 지점이 우회로를 줄임 |
| 프론트 | React 19 + Zustand + TanStack Query, Vitest + RTL + MSW | 기존 유지 | |

### 7.3 Clean Architecture Approach

```
idt/
  src/domain/tool_access/          ToolAccessPolicy, 규칙 엔티티, Repository 인터페이스
  src/application/tool_access/     관리자 조회·교체 UseCase, 실행자 허용 목록 조회
  src/infrastructure/tool_access/  SQLAlchemy 모델·Repository
  src/api/routes/admin_tool_access_router.py
  db/migration/V082__... (테이블 생성), V083__... (기본 세트 시드)  ← 번호는 Do 시점 최신 기준

idt_front/
  src/pages/AdminToolAccessPage/   기본 세트 / 부서 / 사용자 탭
  src/services/toolAccessService.ts, src/hooks/useToolAccess.ts, src/types/toolAccess.ts
  src/constants/api.ts, adminNav.ts
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 3종(루트·`idt/`·`idt_front/`) 코딩 규칙
- [x] `idt/docs/rules/` 세부 규칙
- [x] ESLint / TypeScript 설정 (`idt_front`)
- [x] TDD: pytest / Vitest + RTL + MSW, 테스트 먼저 작성

### 8.2 Conventions to Verify

| Category | Current State | To Verify | Priority |
|----------|---------------|-----------|:--------:|
| 마이그레이션 | Flyway, 최신 V081 | FK collation 규칙, COMMENT 콤마 금지 | High |
| 계약 확장 | additive 원칙 | 응답 optional 필드만 추가 | High |
| 관리자 메뉴 | `adminNav.ts` 단일 소스 | 탭 개수 하드코딩 단언 금지 | Medium |
| 뮤테이션 버튼 | `LoadingButton` | 권한 저장 버튼에 적용 | Medium |
| 컴포넌트 상수 | 컴포넌트 파일 런타임 export 금지 | 탭·라벨 상수는 `src/types/` 또는 `constants/` | Medium |

### 8.3 Environment Variables Needed

신규 환경변수 없음.

---

## 9. Next Steps

1. [ ] `/pdca design tool-access-control` — 판정 위치, 기본 세트 저장 방식, `auth_ctx` 누락 호출자 전수표, 도구 ID 정규화 규칙, API 계약 확정
2. [ ] 별도 보고: `USE_WEB_SEARCH` 권한 코드가 정의만 있고 확인 코드가 없음 (이번 범위 밖)
3. [ ] 작업 공간: worktree `wt/tool-access-control`, 브랜치 `feature/tool-access-control`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-03 | 초안 — 사용자 질의응답 3회 반영 (권한 단위·기본 차단·기본 세트·확인 시점·실행 동작·MCP 단위·관리 주체·저장 검증·포크·비대화 실행·MCP 인증) | 배상규 |
| 0.2 | 2026-11-04 | FR-16 변경 — MCP 레지스트리 조회도 admin 전용 (Do 단계 사용자 결정) | 배상규 |
