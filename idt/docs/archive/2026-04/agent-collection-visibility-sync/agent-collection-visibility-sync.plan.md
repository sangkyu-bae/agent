# Plan: agent-collection-visibility-sync

> Feature: 에이전트 생성 시 컬렉션 scope 기반 visibility 자동 상속
> Created: 2026-04-26
> Status: Plan
> Priority: High
> Related: `agent-builder`, `collection-permission`

---

## 1. 문제 분석 (Problem Statement)

### 현재 구조

에이전트와 컬렉션이 **각각 독립적인 공개여부**를 가진다:

| 대상 | 필드 | 값 | 저장 위치 |
|------|------|-----|----------|
| 에이전트 | `visibility` | private / department / public | `agent_definition` 테이블 |
| 컬렉션 | `scope` | PERSONAL / DEPARTMENT / PUBLIC | `collection_permissions` 테이블 |

### 이중 공개여부의 문제점

에이전트 생성 시 RAG 컬렉션을 선택하는데, **두 공개여부 간 정합성 검증이 없다.**

**모순 시나리오:**

```
CASE 1: PUBLIC 에이전트 + PERSONAL 컬렉션
→ 누구나 에이전트에 접근 가능
→ 하지만 RAG 실행 시 컬렉션 접근 거부 → 에이전트가 "문서를 찾을 수 없습니다" 응답
→ 사용자 혼란: "에이전트가 보이는데 왜 안 되지?"

CASE 2: DEPARTMENT 에이전트 + PERSONAL 컬렉션 (타 부서원 소유)
→ 같은 부서원은 에이전트 접근 가능
→ 하지만 컬렉션 소유자만 데이터 접근 가능 → 역시 빈 응답

CASE 3: PRIVATE 에이전트 + PUBLIC 컬렉션
→ 문제 없음 (제한적 에이전트, 공개 데이터)
```

**핵심 원칙**: 에이전트의 visibility는 참조하는 컬렉션의 scope보다 **넓을 수 없다.**

### 추가 발견: 컬렉션 목록 미필터링

`GET /api/v1/rag-tools/collections` 엔드포인트가 **모든 Qdrant 컬렉션을 권한 검증 없이 반환**한다.
→ 에이전트 생성 UI에서 접근 불가능한 컬렉션도 선택 가능한 상태.

---

## 2. 해결 방향: 컬렉션 scope 상속

### 핵심 규칙

> **에이전트의 최대 visibility는 참조하는 컬렉션 중 가장 제한적인 scope로 자동 제한된다.**

### Scope 제한 순서 (제한적 → 개방적)

```
PERSONAL (가장 제한적) < DEPARTMENT < PUBLIC (가장 개방적)
```

### 상속 규칙 매트릭스

| 컬렉션 scope | 에이전트 최대 visibility | 설명 |
|-------------|------------------------|------|
| PERSONAL | private | 소유자만 사용 가능 |
| DEPARTMENT | department | 같은 부서만 사용 가능 |
| PUBLIC | public | 누구나 사용 가능 |

### 복수 컬렉션 시

```
에이전트가 [PUBLIC 컬렉션A, DEPARTMENT 컬렉션B] 참조
→ 최소값 = DEPARTMENT
→ 에이전트 visibility 최대 = department
```

### 사용자 선택권

- 에이전트 visibility 선택 UI를 **제거하지 않는다**
- 대신 컬렉션 scope에 의해 선택 가능한 범위를 **자동 제한**한다
- 예: PERSONAL 컬렉션 선택 시 → visibility 드롭다운에 "private"만 활성화

---

## 3. 기능 범위 (Scope)

### In Scope

**A. 백엔드 — 에이전트 생성 시 visibility 검증**
- [ ] `CreateAgentUseCase`에서 선택된 컬렉션의 scope 조회
- [ ] 컬렉션 scope 기반 최대 visibility 계산
- [ ] 요청된 visibility가 최대값을 초과하면 자동으로 최대값으로 조정 (또는 에러)
- [ ] 검증 로직을 domain policy로 분리

**B. 백엔드 — 컬렉션 목록 권한 필터링**
- [ ] `GET /api/v1/rag-tools/collections` 엔드포인트에 사용자 권한 필터 적용
- [ ] 현재 사용자가 `can_read` 권한이 있는 컬렉션만 반환
- [ ] 각 컬렉션의 scope 정보를 응답에 포함

**C. 프론트엔드 — visibility 선택 UI 제한**
- [ ] 컬렉션 선택 시 해당 scope 정보를 함께 표시
- [ ] 선택된 컬렉션의 scope에 따라 visibility 드롭다운 옵션 자동 제한
- [ ] scope 불일치 시 안내 메시지 표시 ("이 컬렉션은 개인용이므로 에이전트도 비공개만 가능합니다")

**D. 에이전트 수정 시에도 동일 검증**
- [ ] `UpdateAgentUseCase`에서도 visibility 변경 시 컬렉션 scope 검증

### Out of Scope

- 기존 에이전트 일괄 마이그레이션 (수동 확인 후 처리)
- 컬렉션 scope 변경 시 연쇄적 에이전트 visibility 자동 변경 (향후 과제)
- RAG 런타임 권한 검증 강화 (이미 `CollectionPermissionPolicy.can_read`로 존재)

---

## 4. 현재 코드 분석 (As-Is)

### 4.1 에이전트 생성 흐름

```
CreateAgentRequest (visibility 포함)
  → CreateAgentUseCase._build_agent_definition()
    → AgentDefinition(visibility=request.visibility)  ← 검증 없이 그대로 저장
      → agent_definition_repository.save()
```

**관련 파일:**
- `src/application/agent_builder/schemas.py` — CreateAgentRequest에 visibility 필드
- `src/application/agent_builder/create_agent_use_case.py` — 생성 로직
- `src/domain/agent_builder/schemas.py` — AgentDefinition 도메인 객체
- `src/domain/agent_builder/policies.py` — VisibilityPolicy (접근 제어만, 생성 검증 없음)

### 4.2 컬렉션 목록 (에이전트 생성 시)

```
GET /api/v1/rag-tools/collections
  → qdrant_client.get_collections()  ← 권한 필터 없음, 모든 컬렉션 반환
  → 응답에 scope 정보 미포함
```

**관련 파일:**
- `src/api/routes/rag_tool_router.py:44-60` — 컬렉션 목록 API
- `src/infrastructure/collection/permission_models.py` — CollectionPermissionModel
- `src/domain/collection/permission_policy.py` — CollectionPermissionPolicy

### 4.3 프론트엔드 에이전트 생성

```
AgentBuilderPage → RagConfigPanel → useCollections()
  → ragToolService.getCollections()  ← scope 정보 없이 name만 표시
  → visibility 선택 드롭다운은 컬렉션과 독립적
```

**관련 파일:**
- `idt_front/src/components/agent-builder/RagConfigPanel.tsx`
- `idt_front/src/hooks/useRagToolConfig.ts`
- `idt_front/src/pages/AgentBuilderPage/index.tsx`

---

## 5. To-Be 설계 방향

### 5.1 Domain Policy 추가

```python
# src/domain/agent_builder/policies.py (신규 메서드)

class VisibilityPolicy:
    SCOPE_TO_MAX_VISIBILITY = {
        "PERSONAL": "private",
        "DEPARTMENT": "department",
        "PUBLIC": "public",
    }
    VISIBILITY_RANK = {"private": 0, "department": 1, "public": 2}

    @staticmethod
    def max_visibility_for_collections(collection_scopes: list[str]) -> str:
        """컬렉션 scope 목록에서 최대 허용 visibility 계산"""
        ...
    
    @staticmethod
    def validate_visibility(requested: str, collection_scopes: list[str]) -> str:
        """요청된 visibility가 허용 범위 내인지 검증, 초과 시 자동 조정"""
        ...
```

### 5.2 UseCase 검증 흐름

```
CreateAgentRequest
  → 선택된 컬렉션 이름 추출 (tool_configs에서 RAG 관련)
  → CollectionPermissionRepository로 각 컬렉션의 scope 조회
  → VisibilityPolicy.validate_visibility(request.visibility, scopes)
  → 조정된 visibility로 AgentDefinition 생성
```

### 5.3 컬렉션 목록 API 변경

```
GET /api/v1/rag-tools/collections?user_id={id}
  → Qdrant 컬렉션 목록 조회
  → CollectionPermissionPolicy.can_read() 필터 적용
  → 각 컬렉션에 scope 정보 포함하여 반환
```

### 5.4 프론트엔드 변경

```
RagConfigPanel
  └─ 컬렉션 옵션에 scope 뱃지 표시 (개인/부서/공개)
  └─ 컬렉션 선택 변경 시 → maxVisibility 재계산
      └─ visibility 드롭다운에서 초과 옵션 비활성화
      └─ 현재 선택된 visibility가 초과 시 자동 하향 조정
```

---

## 6. 기술 의존성

| 모듈 | 상태 | 비고 |
|------|------|------|
| `VisibilityPolicy` | ✅ 존재 | 접근 제어만 있음, 생성 검증 메서드 추가 필요 |
| `CollectionPermissionPolicy` | ✅ 존재 | `can_read()` 활용 가능 |
| `CollectionPermissionRepository` | ✅ 존재 | scope 조회 가능 |
| `CreateAgentUseCase` | ✅ 존재 | 검증 로직 삽입 지점 |
| `rag_tool_router` | ✅ 존재 | 권한 필터 + scope 정보 추가 필요 |
| `RagConfigPanel` (프론트) | ✅ 존재 | scope 표시 + visibility 연동 추가 필요 |

---

## 7. 파일 구조

### 수정 대상 (백엔드)

```
idt/src/
├── domain/agent_builder/
│   └── policies.py                              # max_visibility_for_collections, validate_visibility 추가
├── application/agent_builder/
│   ├── create_agent_use_case.py                 # 컬렉션 scope 조회 → visibility 검증 삽입
│   └── schemas.py                               # CreateAgentResponse에 adjusted_visibility 필드 (옵션)
├── api/routes/
│   └── rag_tool_router.py                       # 권한 필터 + scope 정보 추가
```

### 수정 대상 (프론트엔드)

```
idt_front/src/
├── components/agent-builder/
│   └── RagConfigPanel.tsx                       # scope 뱃지, visibility 연동
├── pages/AgentBuilderPage/
│   └── index.tsx                                # maxVisibility 상태 관리
├── types/
│   └── agent.ts                                 # 컬렉션 scope 타입 추가
├── services/
│   └── ragToolService.ts                        # 응답에 scope 포함 처리
```

---

## 8. TDD 계획

### 백엔드

| 테스트 파일 | 대상 |
|------------|------|
| `tests/domain/agent_builder/test_policies.py` | max_visibility_for_collections 로직 (단위) |
| `tests/application/agent_builder/test_create_agent_use_case.py` | scope 검증 통합 테스트 |
| `tests/api/routes/test_rag_tool_router.py` | 컬렉션 권한 필터링 테스트 |

### 프론트엔드

| 테스트 파일 | 대상 |
|------------|------|
| `src/__tests__/components/RagConfigPanel.test.tsx` | scope 뱃지 표시, visibility 연동 |
| `src/__tests__/pages/AgentBuilderPage.test.tsx` | maxVisibility 상태 변경 테스트 |

---

## 9. CLAUDE.md 규칙 체크

- [x] domain에 외부 의존성 없음 (VisibilityPolicy는 순수 도메인 규칙)
- [x] router에 비즈니스 로직 없음 (검증은 UseCase + Policy에서 처리)
- [x] TDD: 테스트 먼저 작성
- [x] API 계약 동기화: 컬렉션 목록 응답 변경 시 프론트 타입도 동시 수정
- [x] 함수 40줄 미만 유지
- [x] config 하드코딩 없음

---

## 10. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 기존 에이전트 중 scope 불일치 건 존재 가능 | 중 | 마이그레이션 스크립트로 불일치 건 리스트업 (Out of Scope, 수동 처리) |
| 컬렉션 scope 변경 시 기존 에이전트 visibility 불일치 | 중 | 향후 이벤트 기반 연쇄 업데이트 고려 (현재는 Out of Scope) |
| rag_tool_router 권한 필터 추가 시 기존 API 소비자 영향 | 낮 | 반환 필드 추가는 하위 호환, 필터는 기존에도 적용됐어야 할 로직 |

---

## 11. 구현 순서

| 순서 | 작업 | 예상 시간 |
|------|------|----------|
| 1 | `VisibilityPolicy` 도메인 규칙 + 단위 테스트 | 30분 |
| 2 | `CreateAgentUseCase` 검증 로직 삽입 + 통합 테스트 | 40분 |
| 3 | `rag_tool_router` 권한 필터 + scope 응답 추가 + 테스트 | 40분 |
| 4 | 프론트 타입/서비스 업데이트 | 20분 |
| 5 | `RagConfigPanel` scope 표시 + visibility 연동 + 테스트 | 40분 |
| 6 | 브라우저 통합 테스트 | 20분 |

**총 예상: ~3시간**

---

## 12. 완료 기준

- [ ] PERSONAL 컬렉션 선택 시 에이전트 visibility가 private으로 자동 제한됨
- [ ] DEPARTMENT 컬렉션 선택 시 department 이하만 선택 가능
- [ ] 복수 컬렉션 선택 시 가장 제한적인 scope 기준 적용
- [ ] 에이전트 생성 API에서 visibility 초과 시 자동 조정 또는 에러
- [ ] 컬렉션 목록 API가 접근 가능한 컬렉션만 반환
- [ ] 컬렉션 목록에 scope 정보 포함
- [ ] UI에서 컬렉션 scope 뱃지 표시
- [ ] UI에서 visibility 드롭다운 자동 제한
- [ ] 관련 테스트 전체 통과

---

## 13. 다음 단계

1. [ ] Design 문서 작성 (`/pdca design agent-collection-visibility-sync`)
2. [ ] 기존 에이전트 scope 불일치 현황 조사 (선택)
3. [ ] 구현 시작 (TDD)
