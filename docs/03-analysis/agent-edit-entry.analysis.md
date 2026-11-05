# agent-edit-entry Gap Analysis

> **Feature**: agent-edit-entry (idt_front)
> **Date**: 2026-11-05
> **Design**: [agent-edit-entry.design.md](../02-design/features/agent-edit-entry.design.md)
> **Worktree**: `wt/agent-edit-entry` (branch `feature/agent-edit-entry`, 미커밋)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 수정 진입점이 빌더 목록 하나뿐이라, 채팅·워크스페이스에서 고치려면 목록을 거쳐 다시 찾아야 하고 저장 후 복귀도 수동이다. |
| **WHO** | P2 — 자기 에이전트(owned·forked)를 운영하며 채팅으로 결과를 확인하는 소유자. 구독자(subscribed)는 대상이 아니다. |
| **RISK** | 빌더의 기존 진입 흐름(위저드 intent 소비, edit 프라임 1회 가드)과 `?edit` 소비가 경합해 폼이 덮어써지거나 빈 폼이 뜰 수 있다. |
| **SUCCESS** | 워크스페이스·채팅에서 클릭 1번으로 해당 에이전트 편집 스튜디오가 열리고, 저장·취소 후 들어온 화면으로 돌아간다. 권한 없는 id는 안내 후 목록. |
| **SCOPE** | 프론트 단일. ① 빌더 `?edit` 진입 ② 워크스페이스 링크 수정 ③ 채팅 헤더 수정 아이콘 ④ 복귀 처리 ⑤ 권한 없음 처리. 백엔드 무변경. |

---

## 1. 점수

| 축 | 점수 | 근거 |
|----|:----:|------|
| Structural | 100% | Design §11.1 파일 12개 전부 생성·수정. 테스트 파일 2개(`agentSubscriptionService.test.ts`, `useAgentBuilder.test.ts`) 추가 |
| Functional | 94% | FR 10건 중 9건 Met, FR-09 화면 확인으로 Met 전환. 감점은 §4 갭 #1·#2 |
| Contract | 100% | API·엔드포인트 변경 없음. `toAgentSummary` 매퍼만 변경 |
| Runtime | 75% | 화면 확인 6건 중 통과 4, 부분 1(E4), 실패 1(E5) — §3 |
| **Overall** | **90%** | S×0.15 + F×0.25 + C×0.25 + R×0.35 = 15 + 23.5 + 25 + 26.25 |

---

## 2. Success Criteria

| SC | 결과 | 근거 |
|----|:----:|------|
| SC-1 워크스페이스 [수정하기] → 편집 스튜디오 직행 | ✅ | `AgentWorkspacePage/index.tsx:209`, 화면 E2 |
| SC-2 owned·forked만 ✏️, 구독·SUPER 미노출 | ✅ | `ChatHeader.tsx:32-41`, C1·C2·U5, 화면에서 SUPER 미노출 확인. 구독 에이전트는 로컬 데이터가 없어 화면 미확인 |
| SC-3 채팅 진입 → 저장·확인 → 같은 에이전트로 복귀 | ✅ | 화면 E1: `/chatpage` 복귀, 같은 에이전트 선택 유지, 헤더·사이드바 이름 즉시 반영 |
| SC-4 워크스페이스 진입 → 취소 → 워크스페이스 복귀 | ✅ | 화면 E2, C8 |
| SC-5 권한 없음·없는 id → 안내 후 목록 | ✅ | C6·C7, 화면에서 `?edit=no-such-agent` → 배너 + URL 정리 확인 |
| SC-6 외부 `returnTo` 무시 | ✅ | U4, C11 |
| SC-7 기존 빌더 흐름 회귀 0 | ✅ | 빌더 테스트 39건 통과(기존 30건 포함). C6은 간헐 실패 — 갭 #5 |

---

## 3. 화면 확인 (worktree vite 5175 + 로컬 백엔드)

| # | 시나리오 | 결과 |
|---|----------|:----:|
| E1 | 채팅 ✏️ → 이름 수정 → 저장 → [확인] | ✅ `/chatpage` 복귀, 같은 에이전트, 헤더·사이드바 이름 갱신 |
| E2 | 워크스페이스 [수정하기] → [뒤로] | ✅ 워크스페이스 복귀 |
| E3 | 구독 에이전트에서 ✏️ 미노출 | — 로컬에 구독 데이터 없음 (단위 테스트로 대체) |
| E4 | 편집 중 새로고침 | ⚠️ 같은 편집 화면 복원. 단 목록이 약 0.3초 먼저 보임 (갭 #2) |
| E5 | 375px 채팅 헤더 | ❌ 헤더 행이 263px 영역에 301px로 넘침. [대화 삭제] 버튼이 화면 밖(x=377)으로 밀림 (갭 #3) |
| — | `?edit=없는id` 직접 진입 | ✅ 배너 표시, URL에서 `edit`·`returnTo` 제거 |

확인용으로 로컬 DB에 테스트 에이전트 1개("QA 편집진입 수정됨", id `d4df66a2-…`)를 만들었다.

---

## 4. Gap 목록

| # | 심각도 | 확신 | 위치 | 내용 | 수정안 |
|---|--------|:----:|------|------|--------|
| 1 | Important | 75% | `AgentBuilderPage/index.tsx:268` | denied 판정이 데이터가 있어도 `isEditDetailError`를 본다. 저장 후 상세 쿼리가 재조회되다 실패하면(TanStack v5는 데이터를 남긴 채 `isError=true`) 편집 중이던 사용자가 "권한 없음" 배너와 함께 목록으로 튕기고 `returnTo`도 사라진다 | `(isEditDetailError && !editDetail) \|\| (editDetail && !editDetail.can_edit)` |
| 2 | Minor | 90% | `:145`, `:224-226` | `?edit` 직접 진입·새로고침 시 카탈로그·모델 로딩 동안 목록 화면이 보이고 [새 에이전트]도 눌린다 (화면 확인 ~0.3초) | `searchParams.has('edit')`이고 배너가 없으면 목록 대신 로딩 화면 |
| 3 | Important | 90% | `ChatHeader.tsx` | 375px에서 헤더 행이 넘쳐 우측 버튼이 잘린다. ✏️ 추가 전에도 2px 넘쳤고(기존 문제), ✏️로 44px가 더 늘었다 | 좁은 폭에서 RAG 배지 숨김(`hidden sm:inline-flex`) 또는 제목 `min-w-0 truncate` + 아이콘 그룹 `shrink-0` |
| 4 | Minor | 70% | `:756-760` | 로딩 화면에 빠져나갈 수단이 없다. 상세 요청이 멈추면 갇힌다 | [뒤로] 버튼(`handleCancel`) |
| 5 | Minor | 90% | `index.test.tsx:1303` | C6이 배너 표시 직후 URL을 바로 단언해 간헐 실패(전체 실행 1회 실패, 단독 3회 통과). URL 정리는 실제로 이루어짐 | `await waitFor(() => expect(location()).toBe('/agent-builder'))` (C7도 동일) |
| 6 | Minor | 90% | `index.test.tsx:1374` | C12가 intent 우선 시 URL에서 `edit` 제거를 단언하지 않는다 | `location()` 단언 추가 |

설계와 다른 구현 3건(`clearEditParams` useCallback+deps, 로딩 조건 `!editDetail?.can_edit`, 취소 버튼 라벨 '뒤로')은 동작이 같거나 더 낫다고 판정했다.

---

## 5. Decision Record 확인

| 결정 | 준수 | 비고 |
|------|:----:|------|
| [Plan] 진입 = 쿼리 `?edit` | ✅ | |
| [Plan] 복귀 = `returnTo` | ✅ | `navigate`가 history를 쌓아 채팅에서 브라우저 뒤로가기 시 편집 화면이 다시 열림(설계대로, 후속 검토 가능) |
| [Plan] 채팅 노출 = `source_type ∈ {owned, forked}` | ✅ | |
| [Design] Option C — 유틸 1개 + 기존 소비 effect 확장 | ✅ | 경합 없음 확인 |

---

## 6. Act-1 결과 (2026-11-05)

갭 6건 전부 수정. 테스트 선작성 후 구현(C14는 수정 전 실패·수정 후 통과 확인).

| # | 수정 | 검증 |
|---|------|------|
| 1 | denied 조건 `(isEditDetailError && !editDetail) \|\| (editDetail && !editDetail.can_edit)` | C14 (포커스 복귀로 배경 재조회 500 재현) |
| 2 | `isEditEntryPending`: 목록 뷰 + `?edit` 있음 + 배너 없음이면 로딩 화면 | C15, 화면: 새로고침 순서 `loading → studio` (목록 없음) |
| 3 | RAG 배지 숨김을 감싸는 `<span className="hidden sm:inline-flex">`로 이동. 원인: `cn`이 클래스를 병합하지 않아 Badge 기본 `inline-flex`가 `hidden`을 이김 (기존 버그) | C2b, 화면 375px: 헤더 263/263 넘침 없음, [대화 삭제] 우측 359px. 1440px: 배지 표시 |
| 4 | 로딩 화면 [뒤로] (`handleCancel`). 소비 전에는 `returnTo`를 URL에서 직접 읽음 | C16 |
| 5 | C6 URL 단언 `waitFor` | 반복 실행 통과 |
| 6 | C12 URL 정리 단언 추가 | 통과 |

재검증: 관련 테스트 29파일 248건 통과(`--no-file-parallelism`), type-check 통과, lint는 master와 같은 기존 오류 2건뿐.

갱신 점수: Functional 100%, Runtime 100%(E3은 데이터 없어 단위 테스트로 대체) → **Overall 100%**.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-11-05 | 정적 분석 + 화면 확인 |
| 0.2 | 2026-11-05 | Act-1 — 갭 6건 수정, 화면 재확인 |
