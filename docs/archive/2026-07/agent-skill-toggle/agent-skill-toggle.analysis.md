# agent-skill-toggle Gap Analysis (Check)

> **Feature**: agent-skill-toggle
> **Project**: sangplusbot (idt + idt_front)
> **Date**: 2026-07-01
> **Analyzer**: bkit:gap-detector
> **Design**: `docs/02-design/features/agent-skill-toggle.design.md`

---

## Match Rate: **98%**

Design(§3 Backend, §4 Frontend, §8 체크리스트)이 사양대로 구현됨. 6개 명시 보증 모두 충족. 기능 갭 없음 — 남은 2%는 의도적/개선성 편차뿐.

---

## Implemented (✅)

| Design § | 항목 | 근거 |
|---|---|---|
| §3-1 | `skill_ids` 3개 스키마 | `schemas.py:48`(Create), `:77`(Update), `:94`(Get, 기본 `[]`) — None/[]/[...] 시맨틱 정확 |
| §3-2 | `SkillAttachPolicy.validate_count` | `policies.py:26-34` — 단일 `MAX_ATTACHED` 상수, dedupe는 호출부 위임 |
| §3-2 | `SyncAgentSkillsUseCase` | dedupe-keep-order(`:110`), **변경 전** count+존재+접근 검증(`:58-76`), `current==desired` noop(`:82`), 그 외 detach-all + `sort_order=idx` attach(`:90-102`) |
| §3-3 | Create: save 후 sync + `viewer_role` | `create_agent_use_case.py:141-145`, 라우터 실제 role 전달 |
| §3-3 | Update: `skill_ids is not None` 시 sync | `update_agent_use_case.py:90-95` |
| §3-3 | Get: 부착 `skill_ids` 반환 | `get_agent_use_case.py:79-84` via `list_links` |
| §3-4 | 라우터 409/404/403 매핑 | create → `_attach_skill_http_error`; update inline |
| §3-5 | 단일 세션 DI | `main.py` `_make_skill_sync`가 한 session으로 전 repo 구성 → create/update/get 주입 |
| §4-1 | `MAX_ATTACHED_SKILLS=3`, form `skills`, req `skill_ids`, `AgentDetail.skill_ids` | 상수/타입 4곳 |
| §4-2 | `handleSkillToggle` max 가드·edit 프라임·save payload | create 빈배열=undefined, update 항상 배열 |
| §4-3 | `AgentSkillPanel` staged 토글 | attach/detach 훅 미사용, `n/3` 카운터, max 도달 disabled |
| §4-4 | 스킬 탭 `enabled: true` | `AgentTestPanel.tsx:39` |
| §4-5 | `SkillPickerModal` + 좌측 "스킬" 섹션 + prop 관통 | 3개 컴포넌트 |

### 명시 보증 6종
1. **D2 양측 단일 상수** ✅ — 하드코딩 `3` 없음(패널/모달/페이지 모두 상수 참조)
2. **D3 staged save** ✅ — 토글은 `form.skills`만 변경, API 미호출
3. **Q1 all-or-nothing** ✅ — 첫 detach 이전에 전체 검증 완료
4. **Q3 접근가능 후보** ✅ — `useSkills({scope:'all'})`
5. **DDD** ✅ — 신규 application/domain 파일에 infrastructure import 0
6. **API 계약 동기화** ✅ — `skill_ids` 백엔드·프론트 3쌍 모두 존재

> 보너스: `list_links`가 `sort_order` ASC 정렬 → edit 프라임 순서·noop 비교 모두 정확.

---

## Gaps / Deviations (전부 low, 의도적)

| 항목 | Design 기대 | 구현 | 심각도 | 평가 |
|---|---|---|---|---|
| `sync()` 시그니처 | `sync(agent, ...)` (객체) | `agent_id: str`, 호출부가 `.id` 전달 | low | 동작 동일, 더 단순 — 허용 |
| Get 읽기 메서드 | `list_attached_skills` 예시 | `list_links` 사용(`get:81-84`) | low | 개선 — 전체 엔티티 미로딩, 여전히 정렬 유지 |
| Update `viewer_role` | 예시엔 `"user"` 하드코딩 | 라우터 실제 role 전달 | low | 개선 — RBAC 더 정확 |

---

## Notes / 후속 확인 권장

- **Create all-or-nothing**: `save()` 후 sync 예외 시 세션 미들웨어의 요청 트랜잭션 롤백에 의존(§3-3, §6 설계 승인). UseCase는 commit/rollback 직접 호출 안 함(CLAUDE.md §6 준수). 미들웨어가 예외 시 롤백하는지 1회 실측 확인 권장 — 코드 갭 아님.
- **Silent-skip 가드**: sync 호출이 `and self._skill_sync is not None`로 가드됨. 프로덕션 DI는 항상 배선(`main.py:1997/2006`)이라 무영향. DI 오구성 시에만 `skill_ids` 무시.
- 레거시 attach/detach API(`POST/DELETE/GET /{id}/skills`)는 하위호환 유지(§9) — 라우터 존치 확인.

---

## 결론

**98% ≥ 90% 게이트 통과.** iterate 불필요. 남은 편차는 설계 예시 대비 개선/단순화로 수용. 
후속: 코드 정리(`/simplify`) → 완료 보고서(`/pdca report agent-skill-toggle`).

> 실측 검증 잔여: (1) 세션 미들웨어 예외-롤백 1회 확인, (2) `uvicorn`+`npm run dev` 실 DB에서 등록/수정 시 토글 반영 확인.
