# agent-memory-org-scope Design Document (메모리 Phase 3)

> **Plan**: `docs/01-plan/features/agent-memory-org-scope.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **소스 기준**: master 실코드 (V050 스키마·memory entity/repository/policies·context_assembler·general_chat use_case.py:352 주입부·AuthContext.department_ids)

---

## 1. Plan 이월 결정 5건 — 확정

| # | 결정 대상 | 확정안 | 근거 |
|---|-----------|--------|------|
| ① | 부서 식별 저장 | **`user_id` 컬럼 재사용** — scope=user면 사용자 id, scope=org면 부서 id. 쿼리는 **항상 scope 명시** → 혼용 오염 차단. **마이그레이션 0** | V050 `user_id VARCHAR(255)` 주석 "scope=user일 때 소유자" — 소유 키의 일반 슬롯. 인덱스 `idx_memory_user_status(user_id,status)`가 org 조회도 커버 |
| ② | 승격 원본 처리 | **복사(원본 유지)** — 개인 메모리는 그대로 두고 org 신규 생성 | 개인 맥락 유지 + 부서 반출은 명시적 행위. 이동(삭제)은 실수 시 복구 불가 |
| ③ | 병합 정렬·캡 | **개인 우선 → 부서, 그 다음 타입 우선순위. 단일 합산 캡**(기존 `memory_inject_token_cap` 공유) | 개인 맥락이 부서 일반론보다 우선. 합산 캡으로 폭주 구조 차단(FR-02) |
| ④ | 부서 관리 권한 | **전역 admin** (부서장 롤 부재 실측 — department_router가 require_role("admin")) | 부서장 개념 도입은 별도 기능. admin 기준선 재사용 |
| ⑤ | 조회 API | **`GET /memories?scope=org`** — 소속 부서 org 메모리, 기존 status 쿼리와 직교. 승격은 `POST /memories/{id}/promote` | additive, Phase 1/2 라우터 확장 |

## 2. Architecture (마이그레이션 0)

```
[저장] agent_memory (V050, 무변경)
  scope='user', user_id=<사용자id>   ← Phase 1/2
  scope='org',  user_id=<부서id>     ← Phase 3 (신규 행, user_id 슬롯 재사용)

[주입 — MemoryContextAssembler.build_block(user_id, dept_ids, request_id)]
  개인:   repo.find_active_by_user(user_id)
  부서:   repo.find_active_by_departments(dept_ids)   ← scope='org' AND user_id IN dept_ids
  병합:   dedup(개인∪부서) → sort(개인 우선→타입) → truncate(단일 캡) → render(출처 라벨)

[general_chat] stream():
  memory_block = await assembler.build_block(
      request.user_id, _dept_ids(auth_ctx), request_id)   ← auth_ctx.department_ids 전달

[승격] POST /memories/{id}/promote  (admin)
  개인 active 메모리 → 부서 org 메모리 복사 (dedup: 부서에 동일 content 있으면 409/무시)
```

## 3. Detailed Design

### 3-1. Domain (additive)

```python
# entity.py — MemoryScope.ORG 이미 존재 (Phase 1 정의). 변경 없음.

# policies.py
TYPE_PRIORITY_WITH_SCOPE  # 정렬은 (scope: user=0/org=1, type_priority) 튜플
@staticmethod
def sort_for_injection_scoped(memories) -> list[Memory]:
    """개인(user) 우선 → 부서(org), 그 안에서 TYPE_PRIORITY → 최신순."""
```

`dedup_candidates`(Phase 2)는 content 기준이라 승격 중복 검사에 그대로 재사용.

### 3-2. Repository (additive — interface + 구현)

```python
async def find_active_by_departments(
    self, dept_ids: list[str], request_id: str) -> list[Memory]:
    """scope='org' AND user_id IN dept_ids AND status='active'.
    dept_ids 빈 리스트면 즉시 [] (쿼리 스킵)."""

async def count_active_by_department(
    self, dept_id: str, request_id: str) -> int:   # 부서 상한 검증
```

기존 `find_active_by_user`는 **무변경** — scope='user'만 반환하도록 `scope` 조건 추가 확인(현재 user_id만 필터 → org 행의 user_id에 부서id가 들어가면 오염 가능 → **`find_active_by_user`에 `scope='user'` 조건 추가**가 FR-07의 핵심 안전장치. 회귀 테스트로 고정).

### 3-3. Application

**`MemoryContextAssembler.build_block` 시그니처 확장** (하위호환 — dept_ids 기본 빈 리스트):

```python
async def build_block(self, user_id, request_id, dept_ids: list[str] | None = None) -> str:
    personal = repo.find_active_by_user(user_id, request_id)
    org = repo.find_active_by_departments(dept_ids or [], request_id)
    merged = dedup_by_content(personal + org)         # 개인이 부서와 겹치면 개인 유지
    ordered = MemoryPolicy.sort_for_injection_scoped(merged)
    included, truncated = truncate_to_budget(ordered, cap)   # 단일 합산 캡
    return render(included)   # 출처 라벨: 개인은 무표시, 부서는 "(부서 공유)" (FR-06)
```

**`MemoryCrudUseCase` 확장**:
```python
async def list_org(self, dept_ids, request_id) -> list[Memory]      # scope=org 조회
async def create_org(self, dept_id, mem_type, content, request_id)  # admin 부서 작성 (부서 상한 검증)
async def promote(self, user_id, memory_id, dept_id, request_id)    # 개인→org 복사, 중복 시 ValueError
```

### 3-4. Interfaces (additive)

```python
GET   /memories?scope=org        → 소속 부서 org 메모리 (dept_ids = auth_ctx 기반, 라우터에서 주입)
POST  /memories/org              → 부서 메모리 작성 (admin, body: {dept_id, mem_type, content})
POST  /memories/{id}/promote     → 개인 메모리 부서 승격 (admin, body: {dept_id})
```

- 부서 관리 엔드포인트는 `require_role("admin")`, dept_id는 사용자 소속 검증(auth_ctx.department_ids 포함 여부 → 아니면 403)
- **general_chat 주입부**(`use_case.py:352`): `build_block(request.user_id, request_id, _dept_ids(auth_ctx))` — auth_ctx None이면 빈 리스트(개인만, 회귀 0)
- **config**: `memory_max_active_per_department: int = 50`
- **DI**: assembler는 이미 싱글톤 — dept_ids는 호출 인자라 배선 변경 없음. build_block에 auth_ctx 부서 전달만.

### 3-5. Frontend

- 계약: `MEMORY_ORG`(`?scope=org`)·`MEMORY_ORG_CREATE`·`MEMORY_PROMOTE(id)`, service·hook(`useOrgMemories`·`useCreateOrgMemory`·`usePromoteMemory`)
- SettingsPage: "부서 공유 메모리" 섹션(전원 열람, admin만 작성/삭제) + 개인 메모리 카드에 "부서로 승격"(admin) 버튼
- MSW: org 목록·작성·승격 핸들러

## 4. Test Plan (TDD)

| 파일 | 케이스 |
|------|--------|
| `test_policies.py` 확장 | sort_for_injection_scoped(개인 우선→org→타입) |
| `test_memory_repository.py` 확장 | find_active_by_departments(scope=org·IN·빈 리스트) · **find_active_by_user가 scope=user만**(org 행 배제 회귀 가드) · count_by_department |
| `test_crud_use_case.py` 확장 | list_org · create_org(부서 상한) · promote(정상·중복 거부·소속외 부서 403 경로) |
| `test_context_assembler.py` 확장 | 개인+부서 병합·개인 우선 정렬·합산 캡·부서 라벨·dept_ids 빈 리스트면 개인만(회귀) |
| `test_memory_router.py` 확장 | GET ?scope=org · POST /org(admin 401/403) · promote 200/409 |
| `test_memory_injection.py` 확장 | build_block에 dept_ids 전달 · auth_ctx None이면 개인만 |
| 프론트 | useOrgMemories·promote 훅 + SettingsPage 부서 섹션·승격 버튼 |

## 5. Implementation Order

1. policies(scoped 정렬) + repo 2메서드 + **find_active_by_user에 scope=user 가드** — 정책·repo 테스트 먼저(회귀 가드 우선)
2. assembler build_block 확장(dept_ids) — 병합·정렬·캡 테스트
3. CrudUseCase list_org/create_org/promote + 라우터 3종 + config + dept 소속 검증
4. general_chat 주입부 dept_ids 전달 — 회귀 0 확인
5. 프론트 계약 + SettingsPage 부서 섹션·승격 버튼
6. verify 3종 → analyze

## 6. Plan 리스크 해소 매핑

| Plan 리스크 | 해소 |
|-------------|------|
| 부서 메모리가 개인 밀어냄 | 개인 우선 정렬(결정 ③) + 합산 캡 |
| user_id 부서 혼용 오염 | **find_active_by_user에 scope='user' 조건 추가**(FR-07 핵심) + 항상 scope 명시 쿼리 |
| 승격 중복 | dedup_by_content(Phase 2 재사용) — 부서 동일 content 시 거부 |
| 다부서 주입 폭증 | 부서 상한(50) + 합산 캡 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-20 | 이월 5건 확정 — user_id 슬롯 재사용(마이그레이션 0)·승격 복사·개인 우선+합산 캡·admin 권한·scope 쿼리. FR-07 안전장치(find_active_by_user scope 가드) 명시 | 배상규 |
