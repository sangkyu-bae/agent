# agent-skill-toggle Design Document

> **Feature**: agent-skill-toggle
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-07-01
> **Status**: Design
> **Plan**: `docs/01-plan/features/agent-skill-toggle.plan.md`

---

## 0. Design 결정 요약 (Plan Open Questions 해소)

| # | 항목 | 확정 | 근거 |
|---|------|------|------|
| D1 | UI 배치 | 좌측 섹션 + 우측 탭, **동일 `form.skills` 공유** | 사용자 확정 |
| D2 | 최대 개수 | **3개 유지**, 백엔드·프론트 각 단일 상수로 변경 용이 | 사용자 확정 |
| D3 | 저장 시점 | **staged** — 토글=로컬 상태, 저장 버튼으로 일괄 diff 동기화 | 사용자 확정 |
| Q1 | 실패 처리 | **all-or-nothing** — 하나라도 무효면 4xx + 요청 트랜잭션 전체 롤백 | 사용자 확정 |
| Q2 | 좌/우 편집 중복 | 둘 다 편집 가능(동일 상태 공유라 비용 0) | 설계 결정 |
| Q3 | 후보 scope | `useSkills({scope:'all'})` = `list_accessible`(RBAC) → **후보는 이미 접근가능분만** | 코드 확인 |

**핵심 불변식**: 스킬 부착 상태의 유일한 진실원은 create/update 시점 `agent_skill` 링크 테이블. UI 토글은 `form.skills`(string[])에만 반영되고, 저장 시 서버가 **desired-set 재조정(reconcile)**.

---

## 1. 아키텍처 개요

```
[Frontend]
 AgentBuilderPage (form.skills: string[])         ← single source of truth
   ├─ onSkillToggle(skillId)  (max 3 가드)
   ├─ StudioLayout
   │    ├─ LeftConfigPanel ─ "스킬" 섹션 ─ SkillPickerModal (토글 리스트)
   │    └─ AgentTestPanel ─ "스킬" 탭 ─ AgentSkillPanel (토글 리스트, staged)
   └─ handleSave → skill_ids = form.skills
        ├─ create: POST /agents          { ..., skill_ids }
        └─ update: PATCH /agents/{id}     { ..., skill_ids }

[Backend]  (단일 세션 = 단일 트랜잭션)
 CreateAgentUseCase ─┐
 UpdateAgentUseCase ─┴─▶ SyncAgentSkillsUseCase.sync(agent, desired_ids, viewer)
                              1) 검증(존재·접근권한·개수)  ← 실패 시 ValueError (전체 롤백)
                              2) reconcile(현재 링크 vs desired) → detach/attach
 GetAgentUseCase ──▶ list_attached_skills → GetAgentResponse.skill_ids  (edit 프라임)
```

DDD 준수: agent_builder ↔ skill_builder 도메인 조합은 **application 계층(SyncAgentSkillsUseCase)** 에서만. 도메인 간 직접 import 없음. 기존 정책(`SkillAttachPolicy`, `SkillVisibilityPolicy`) 재사용, 신규 규칙 없음.

---

## 2. 데이터 모델

**DB 변경 없음.** `agent_skill` 테이블 + `AgentSkillModel`(`infrastructure/persistence/models/agent_skill/models.py`) 이미 존재. 링크는 `(agent_id, skill_id, sort_order, created_at)`.

- `sort_order` = desired 리스트 인덱스 → 주입 순서(`SkillInjectionPolicy.merge`가 sort_order ASC prepend).
- 마이그레이션 파일 신규 생성 불필요.

---

## 3. Backend 상세 설계

### 3-1. 계약 (`application/agent_builder/schemas.py`)

```python
class CreateAgentRequest(BaseModel):
    ...
    skill_ids: list[str] | None = None      # None/[] = 부착 없음

class UpdateAgentRequest(BaseModel):
    ...
    skill_ids: list[str] | None = None      # None = 변경 안 함, [] = 전부 해제, [...] = desired set

class GetAgentResponse(BaseModel):
    ...
    skill_ids: list[str] = []               # 부착 순서(sort_order ASC)
```
> `sub_agent_configs`의 `None=무변경 / []=전체제거` 관례와 동일하게 맞춘다.

### 3-2. 신규 `application/agent_skill/sync_agent_skills_use_case.py`

`AttachSkillUseCase`에 흩어진 검증(접근권한·중복·개수)을 재사용/추출해 desired-set 재조정을 캡슐화한다.

```python
class SyncAgentSkillsUseCase:
    def __init__(self, agent_skill_repo, skill_repo, dept_repo, logger): ...

    async def sync(
        self, agent, desired_skill_ids: list[str], request_id: str,
        *, viewer_user_id: str, viewer_role: str,
    ) -> list[str]:
        # 0) 정규화: 순서 보존 dedupe
        desired = _dedupe_keep_order(desired_skill_ids)

        # 1) 검증 (all-or-nothing — 하나라도 실패 시 ValueError, 아무 것도 바꾸지 않음)
        SkillAttachPolicy.validate_count(desired)          # len > MAX_ATTACHED → ValueError("최대 …")
        dept_ids = await self._viewer_dept_ids(viewer_user_id, request_id)
        for sid in desired:
            skill = await self._skills.find_by_id(sid, request_id)
            if skill is None or skill.status == "deleted":
                raise ValueError(f"스킬을 찾을 수 없습니다: {sid}")
            if not SkillVisibilityPolicy.can_access(SkillAccessInput(...)):
                raise PermissionError("이 스킬에 접근할 권한이 없습니다")

        # 2) reconcile: 현재 링크(순서포함) == desired 면 no-op
        current = [l.skill_id for l in await self._links.list_links(agent.id, request_id)]
        if current == desired:
            return desired
        for sid in current:                                # 순서/구성 변경 시 전체 교체 (max 3, 저비용)
            await self._links.detach(agent.id, sid, request_id)
        for idx, sid in enumerate(desired):
            await self._links.attach(AgentSkillLink(agent.id, sid, idx, now), request_id)
        return desired
```

설계 근거:
- **검증 먼저, 적용 나중** → sync 내부에서도 all-or-nothing 성립(무효 발견 시 detach/attach 전에 raise).
- **순서/구성이 다르면 전체 교체**(detach all → attach desired). max 3라 row churn 무시 가능하고, `sort_order`를 desired 인덱스로 정확히 재부여. repo에 `update` 신규 메서드 불필요(기존 `attach`/`detach`/`list_links` 재사용).
- `SkillAttachPolicy`에 `validate_count(ids)` 헬퍼 추가(기존 `validate_attach`는 단건용 유지). `MAX_ATTACHED` 단일 상수 그대로 → **D2(변경 용이)**.

### 3-3. Create/Update UseCase 연결

**CreateAgentUseCase** (`create_agent_use_case.py`): `save()` 직후
```python
if request.skill_ids:
    await self._skill_sync.sync(
        saved, request.skill_ids, request_id,
        viewer_user_id=request.user_id, viewer_role=request.viewer_role or "user",
    )
```
- 무효 skill → 예외 전파 → 라우터 4xx → **요청 트랜잭션 롤백**으로 에이전트도 미저장(Q1 all-or-nothing).
- create 라우터가 `viewer_role`을 전달하도록 소폭 보강(부서공개 스킬 접근 판정용). `CreateAgentRequest`에 `viewer_role` 추가 대신 `execute(body, request_id, viewer_role=...)` 인자로 주입.

**UpdateAgentUseCase** (`update_agent_use_case.py`): 서브에이전트 처리와 동일 위치
```python
if request.skill_ids is not None:
    await self._skill_sync.sync(
        agent, request.skill_ids, request_id,
        viewer_user_id=viewer_user_id or agent.user_id, viewer_role="user",
    )
```

**GetAgentUseCase** (`get_agent_use_case.py`): 응답에 `skill_ids` 채움
```python
attached = await self._links.list_attached_skills(agent_id, request_id)
... GetAgentResponse(..., skill_ids=[s.id for s in attached])
```
- `GetAgentUseCase`에 `agent_skill_repo` 주입 추가.

### 3-4. 라우터 에러 매핑 (`agent_builder_router.py`)

기존 `_attach_skill_http_error`와 동일 규칙을 create/update에도 적용:
- `create_agent`: 현재 try/except 없음 → 추가. `PermissionError→403`, `"찾을 수 없"→404`, `"최대"/"이미"→409`, else→422.
- `update_agent`: 기존 매핑에 `"최대"/"이미"→409` 분기 추가.

### 3-5. DI 배선 (`api/main.py`)

`create_uc_factory`/`update_uc_factory`/`get_uc_factory`가 **같은 session**으로 `SyncAgentSkillsUseCase`(또는 필요한 repo)를 구성:
```python
def _make_skill_repo(session): return SkillRepository(session=session, logger=app_logger)
def _make_skill_sync(session):
    return SyncAgentSkillsUseCase(
        agent_skill_repo=_make_agent_skill_repo(session),
        skill_repo=_make_skill_repo(session),
        dept_repo=DepartmentRepository(session=session, logger=app_logger),
        logger=app_logger,
    )
# create_uc_factory / update_uc_factory: skill_sync=_make_skill_sync(session)
# get_uc_factory: agent_skill_repo=_make_agent_skill_repo(session)
```
> 단일 세션 규칙(CLAUDE.md §6) 준수 — UseCase 내 repo 전부 동일 session.

---

## 4. Frontend 상세 설계

### 4-1. 타입/상수
```ts
// types/agentBuilder.ts
interface AgentBuilderFormData { ...; skills: string[]; }            // 신규
interface CreateBuilderAgentRequest { ...; skill_ids?: string[]; }
interface UpdateBuilderAgentRequest { ...; skill_ids?: string[]; }
// types/agentStore.ts
interface AgentDetail { ...; skill_ids: string[]; }                  // edit 프라임
// constants/agentSkill.ts (신규)
export const MAX_ATTACHED_SKILLS = 3; // 백엔드 SkillAttachPolicy.MAX_ATTACHED 와 동기화
```

### 4-2. 컨테이너 (`AgentBuilderPage/index.tsx`)
- `DEFAULT_FORM.skills = []`.
- edit 프라임(`useEffect [editDetail]`): `skills: editDetail.skill_ids ?? []` 추가.
- 토글 핸들러:
```ts
const handleSkillToggle = (skillId: string) => setForm((prev) => {
  const on = prev.skills.includes(skillId);
  if (!on && prev.skills.length >= MAX_ATTACHED_SKILLS) return prev; // 가드
  return { ...prev, skills: on ? prev.skills.filter(s => s!==skillId) : [...prev.skills, skillId] };
});
```
- `handleSave`:
  - create payload: `skill_ids: form.skills.length ? form.skills : undefined`.
  - update payload: `skill_ids: form.skills` (빈 배열도 명시 전송 → 전체 해제 의미).
- `handleSkillToggle`를 `StudioLayout → LeftConfigPanel / AgentTestPanel` 로 prop 관통, `form.skills`도 함께 전달.

### 4-3. 우측 탭 — `AgentSkillPanel.tsx` (리팩터)
- **입력 변경**: `agentId` 대신 `selectedIds: string[]` + `onToggle` prop 수신(상위 form 상태 기반).
- 드롭다운+부착 버튼·`useAttachSkill`/`useDetachSkill` **제거**(staged). `useSkills({scope:'all', size:100})`로 후보 로드.
- **토글 카드 리스트**(스크린샷 형태): 카드마다 이름·설명 + 우측 스위치. 선택됨 = 스위치 on.
- 개수 가드: `selectedIds.length >= MAX` 이고 미선택인 카드는 스위치 `disabled` + 툴팁. 헤더에 `n/3` 카운터.
- 하단 안내 유지: "부착한 Skill의 instruction만 프롬프트에 합쳐집니다. script는 실행되지 않습니다."

### 4-4. 우측 탭 활성화 — `AgentTestPanel.tsx`
```ts
{ id: 'skill', label: '스킬', enabled: true },   // isEdit → true (create 모드도 활성)
```
- 콘텐츠 분기: `tab === 'skill'` 이면 `<AgentSkillPanel selectedIds={form.skills} onToggle={onSkillToggle} />` (agentId 불요).

### 4-5. 좌측 섹션 — `LeftConfigPanel.tsx` + 신규 `SkillPickerModal.tsx`
- `ToolPickerModal`을 복제해 `SkillPickerModal`: 제목 "스킬 추가", `useSkills` 후보, 카드 토글, 개수 가드(초과 시 미선택 disabled), 스크린샷과 동일한 토글 리스트.
- `LeftConfigPanel`에 "도구함"과 같은 형태의 **"스킬" `CollapsibleSection`**: 선택 요약 리스트(각 항목 "제거") + 헤더 "스킬" 버튼 → `SkillPickerModal` 오픈.
- 좌/우 모두 동일 `form.skills` + `onSkillToggle` 사용 → 자동 동기화.

### 4-6. API 계약 동기화 체크 (CLAUDE.md §4-1)
`skill_ids` 3곳(Create/Update Request, Get Response) 백엔드↔프론트 동시 반영. 엔드포인트 상수 변경 없음(기존 create/update/detail 재사용).

---

## 5. 시퀀스

**등록(create)**
```
사용자: 스킬 토글 on → form.skills=[s1,s2] → [저장]
POST /agents { name, ..., skill_ids:[s1,s2] }
 → CreateAgentUseCase: save(agent) → skill_sync.sync(agent,[s1,s2])
     → 검증 OK → attach s1(0), s2(1)  → 커밋
 → 201 {agent_id, ...}
(무효 s2 예: PermissionError → 403 → 트랜잭션 롤백 → 에이전트 미생성)
```

**수정(edit)**
```
편집 진입: GET /agents/{id} → skill_ids:[s1,s2] → form.skills 프라임
사용자: s2 off, s3 on → form.skills=[s1,s3] → [저장]
PATCH /agents/{id} { skill_ids:[s1,s3] }
 → UpdateAgentUseCase: skill_sync.sync → current[s1,s2]≠[s1,s3]
     → detach s1,s2 → attach s1(0),s3(1) → 커밋
```

---

## 6. 에러 처리 / 관측

| 상황 | 도메인 신호 | HTTP | 프론트 |
|------|-------------|------|--------|
| 스킬 4개 이상 | `ValueError("최대 3개…")` | 409 | 저장 실패 다이얼로그(카운터 가드로 사실상 선차단) |
| 스킬 삭제/미존재 | `ValueError("찾을 수 없…")` | 404 | 실패 다이얼로그 |
| 접근권한 없음 | `PermissionError` | 403 | 실패 다이얼로그 |
| 정상 | — | 201/200 | 성공 다이얼로그 → 목록 |

- 로깅: `SyncAgentSkillsUseCase` start/done + 실패 시 `logger.error(exception=e)` (LOG-001, 스택트레이스 보존).

---

## 7. TDD 계획 (테스트 먼저)

### Backend (pytest — 격리 실행 권장: Windows 이벤트루프 flakiness)
1. `SyncAgentSkillsUseCase`: (a) 신규 부착 (b) 부분 diff(추가+제거) (c) 순서 변경 → sort_order 재부여 (d) 동일 set no-op (멱등) (e) 4개 → 최대초과 raise, **아무 것도 변경 안 함** (f) 접근불가 → raise (g) 미존재 → raise.
2. `CreateAgentUseCase`: `skill_ids` 부착 성공 / 무효 skill 시 예외(에이전트 저장 여부는 트랜잭션 경계라 UseCase는 raise만 검증).
3. `UpdateAgentUseCase`: `None` 무변경 / `[]` 전체해제 / 부분 diff.
4. `GetAgentUseCase`: `skill_ids` 순서 반영.
5. 라우터: create/update 4xx 매핑(409/404/403).

### Frontend (Vitest + RTL + MSW — `--pool=threads`)
1. 토글 on/off → `form.skills` 반영 + save payload `skill_ids` 포함.
2. 3개 도달 → 미선택 스위치 `disabled` + `n/3` 카운터.
3. create 모드에서 스킬 탭/섹션 활성.
4. edit 프라임 → 기존 부착 스킬 on.
5. 좌측 섹션·우측 탭 동시 반영(동일 상태 공유).

---

## 8. 구현 순서 (Do 단계 체크리스트)

**Backend**
1. `SkillAttachPolicy.validate_count` 헬퍼 + 테스트(Red→Green).
2. `SyncAgentSkillsUseCase` + 테스트.
3. `schemas.py` `skill_ids` 3곳 추가.
4. Create/Update/Get UseCase 연결 + 테스트.
5. 라우터 에러 매핑 + `main.py` DI 배선.

**Frontend**
6. 타입/상수(`skills`, `skill_ids`, `MAX_ATTACHED_SKILLS`).
7. 컨테이너 `handleSkillToggle`·프라임·save payload.
8. `AgentSkillPanel` 토글 리팩터 + `AgentTestPanel` 활성화.
9. `SkillPickerModal` + `LeftConfigPanel` "스킬" 섹션 + `StudioLayout` prop 관통.
10. 기존 테스트 갱신(`AgentSkillPanel.test.tsx`) + 신규 테스트.

**검증**
11. `verify-architecture` / `verify-tdd` / `api-contract-sync` 스킬 → `/pdca analyze`.

---

## 9. 영향 범위 / 하위호환

- 부착 3종 API(`POST/DELETE/GET /{id}/skills`) **유지**(하위호환) — 외부/자동화 호출 보호. 프론트 패널만 staged로 전환(유일 사용처).
- `RunAgentUseCase`의 instruction 주입 경로 불변(`agent_skill_repo` 그대로) → 실행 동작 영향 없음.
- edit에서 스킬만 변경 시 `system_prompt` 재생성 없음(주입은 실행 시점) → 부작용 없음.
```
/pdca do agent-skill-toggle
```
