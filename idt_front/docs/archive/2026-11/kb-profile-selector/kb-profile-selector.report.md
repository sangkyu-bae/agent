# kb-profile-selector Completion Report

> **Status**: Complete (E2E 이월)
>
> **Project**: sangplusbot (idt_front)
> **Version**: 0.0.0
> **Author**: 배상규
> **Completion Date**: 2026-11-03
> **PDCA Cycle**: Plan → Design → Do → Check → Act-1 → Report

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | kb-profile-selector |
| Start Date | 2026-11-02 |
| End Date | 2026-11-03 |
| Duration | 2일 (Act 1회) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100% (FR 13/13)            │
├─────────────────────────────────────────────┤
│  ✅ Complete:     13 / 13 FR                 │
│  ⏳ Carried over:  Minor gap 6 + L3 E2E      │
│  ❌ Cancelled:     0                          │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 조항 단위 청킹 KB에서 프로파일을 고를 수 없어 기본 프로파일로만 동작했고, 참조 프로파일이 삭제된 KB는 청킹 설정 저장이 404로 실패했다. |
| **Solution** | 공용 `ChunkingModeSelector`의 조항 모드에 프로파일 선택을 추가해 생성·수정 모달에 함께 적용했다. 일반 사용자용 `GET /api/v1/chunking/profiles`를 연결했고 백엔드는 변경하지 않았다. |
| **Function/UX Effect** | 사용자는 기본 프로파일 따름 또는 특정 프로파일을 선택하고, 크기·경계 규칙 수·섹션 요약 사용 여부를 확인한다. KB 상세 카드에 적용 프로파일 이름이 표시된다. 실서버에서 삭제 프로파일 참조 KB의 저장이 404에서 200(`null`)으로 바뀐 것을 확인했다. |
| **Core Value** | P2가 관리자 개입 없이 KB별로 청킹 프로파일을 지정하고 결과를 화면에서 확인할 수 있다. S1의 "청킹 전략 선택" 단계가 화면 안에서 끝난다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | FR-01~FR-13 구현 | ✅ Met | Act-1에서 FR-11 생성 경로 보완 (페이지 G2, M5-1) |
| SC-2 | 일반 사용자 권한에서 조회·저장 실서버 확인 | ⚠️ Partial | 조회: 일반 사용자 200, 관리자 API 403. 저장: 일반 사용자에게 접근 가능한 컬렉션이 없어 관리자 소유 KB로 확인 |
| SC-3 | 삭제 프로파일 참조 KB 저장 성공, 응답 `null` | ✅ Met | 실서버 PATCH 200, `chunking_profile_id: null` |
| SC-4 | 목록 조회 실패 중 저장 시 기존 지정 유지 | ✅ Met | K5, U1, C5 |
| SC-5 | 기본·커스텀 모드 KB에서 목록 미조회 | ✅ Met | K1, M4, H2 |
| SC-6 | 관리자 프로파일 화면 회귀 0건 | ✅ Met | `AdminChunkingProfilesPage` 테스트 통과, 전체 FAILED diff 신규 0건 |

**Success Rate**: 5/6 criteria met (83%), 1건 부분 충족

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 생성+수정 모달 모두 적용 | ✅ | 공용 selector 한 곳 수정으로 두 모달에 반영 |
| [Plan] | 미선택 = `null` (late-binding 유지) | ✅ | 관리자가 기본 프로파일을 바꾸면 KB도 따라간다 |
| [Plan] | 삭제 프로파일은 경고 후 기본 따름으로 전환 | ✅ | 실서버 저장 404 → 200 |
| [Plan] | 모달 상세 + 카드 이름 표시 | ✅ | 카드 문구 5종 |
| [Plan] | 관리자 API 대신 일반 조회 API 연결 | ✅ | KB 화면 관리자 API 호출 0건 (C8, 실서버 403 확인) |
| [Design] | Option C: 판단 함수 1개 + 선택 컴포넌트 1개 | ✅ | 모달·카드·저장이 같은 판단을 사용 |
| [Design] | 조회 성공 시에만 삭제 판단 | ✅ | Plan RISK(지정 소실) 미발생 |
| [Design] | §6.1 생성 경로 404 처리 | ❌ → 정정 | 실제는 422. Check에서 발견해 Act-1에서 수정, Design v0.2 반영 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [kb-profile-selector.plan.md](kb-profile-selector.plan.md) | ✅ Finalized |
| Design | [kb-profile-selector.design.md](kb-profile-selector.design.md) | ✅ v0.2 |
| Check | [kb-profile-selector.analysis.md](kb-profile-selector.analysis.md) | ✅ Complete (Act-1 포함) |
| Act | Current document | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 일반 목록 상수·서비스·훅, `chunkingProfiles.all` 하위 키 | ✅ | |
| FR-02 | 조항 모드에서만 렌더링·조회 | ✅ | |
| FR-03 | "기본 프로파일 따름" = `null` | ✅ | |
| FR-04 | 선택 프로파일 상세 표시 | ✅ | |
| FR-05 | KB 오버라이드 반영 크기 | ✅ | resolver와 같은 우선순위 (`or` / `is not None`) |
| FR-06 | 수정 모달 프리필·저장, 비조항 `null` | ✅ | |
| FR-07 | 생성 모달 조항 모드에서만 전송 | ✅ | |
| FR-08 | 삭제 프로파일 경고 후 기본 전환 | ✅ | |
| FR-09 | 조회 로딩·실패 시 기존 지정 보존 | ✅ | |
| FR-10 | 프로파일·기본 프로파일 없음 안내 | ✅ | |
| FR-11 | 모드 전환 시 유지, 재오픈 시 초기화 | ✅ | Act-1에서 생성 성공 경로 보완 |
| FR-12 | 카드 적용 프로파일 표시 | ✅ | |
| FR-13 | 기존 안내·서버 오류 표시 유지 | ✅ | |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| Performance | 기본·커스텀 모드 목록 미조회, 5분 캐시 | K1·M4·H2 통과, 세 사용처가 같은 쿼리 키 | ✅ |
| Security | KB 화면에서 관리자 API 미호출 | C8 통과, 실서버 일반 사용자 403 | ✅ |
| Accessibility | `ariaLabel`, 색상+텍스트 병행 | 충족. `role="status"` 누락은 이월 (G5) | ⚠️ |
| Maintainability | 디자인 토큰, 컴포넌트 파일 런타임 export 금지 | 충족 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 판단 함수 | `src/components/knowledge-base/kbProfileSelection.ts` | ✅ |
| 선택 컴포넌트 | `src/components/knowledge-base/KbProfileSelect.tsx` | ✅ |
| 모달·카드 연결 | `ChunkingModeSelector.tsx`, `CreateKnowledgeBaseModal.tsx`, `KbChunkingSettingsCard.tsx` | ✅ |
| 조회 계층 | `constants/api.ts`, `lib/queryKeys.ts`, `services/chunkingProfileService.ts`, `hooks/useChunkingProfiles.ts` | ✅ |
| 생성 오류 처리 | `pages/KnowledgeBasesPage/index.tsx` | ✅ |
| 타입 | `types/knowledgeBase.ts` (`chunking_profile_id`) | ✅ |
| 테스트 | 신규 3파일 + 기존 4파일 보강, 39건 추가 | ✅ |
| 문서 | Plan, Design v0.2, Analysis, Report | ✅ |

신규 파일 5개(구현 2, 테스트 3), 수정 파일 15개.

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority |
|------|--------|----------|
| L3 E2E (Design §8.4 #1~5): 브라우저 저장 흐름, 업로드 청크 반영, 모달 실제 높이 | 일반 사용자 계정과 접근 가능한 컬렉션 없음 | High |
| G6 수정 모달 404 영문 메시지 | 문구 개선 | Medium |
| G5 안내 문구 `role="status"`, 로딩 중 label 연결 | 접근성 | Medium |
| G4 재조회 실패 시 드롭다운 숨김 | 안전 측 동작 (지정 유지) | Low |
| G3 5분 캐시 목록 기준 삭제 판단 | 발생 조건이 좁음 | Low |
| G8 "호출 0건" 테스트의 20ms 대기 | 테스트 견고성 | Low |
| G10 Design Ref 주석 형식 | 선택 사항 | Low |
| 커버리지 측정 | `@vitest/coverage-v8` 미설치, 의존성 추가 승인 필요 | Medium |

### 4.2 Cancelled/On Hold Items

| Item | Reason | Alternative |
|------|--------|-------------|
| - | - | - |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Notes |
|--------|--------|-------|-------|
| Design Match Rate | 90% | 100% (Check 95%) | Act-1 후 본인 재판정, 정적 공식 |
| 실서버 L1 | - | 8/8 | 4~8번은 관리자 소유 KB |
| 기능 테스트 | - | 39건 추가, 관련 116건 통과 | |
| 전체 회귀 | 신규 실패 0 | 1,555건 중 실패 9건, 모두 기준선 | 30초 타임아웃 |
| 변경 파일 lint | 0 | 0 | |
| `tsc -b` | 통과 | ❌ 실패 | 기존 오류 210건, 변경 코드 오류 0건 |
| `npm run build` | 성공 | ❌ 실패 | `tsc -b` 단계. `vite build`는 성공 |
| 커버리지 | 훅 80%, 컴포넌트 60% | 미측정 | 도구 미설치 |
| Security Issues | 0 Critical | 0 | |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| 삭제 프로파일 참조 KB 저장 404 (기존 결함) | 조회 성공 시 삭제로 판단해 `null` 저장 | ✅ 실서버 확인 |
| G1 생성 중 프로파일 삭제 시 "부서/컬렉션" 오류 문구 | 프로파일 누락 422 구분, 전용 안내 + 목록 재조회 | ✅ |
| G2 생성 성공 후 재오픈 시 이전 값 잔존 (이름·컬렉션은 기존 결함) | `isOpen` false→true 전환 시 폼 초기화 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- Plan 단계에서 코드를 직접 확인해 제안서의 "기존 서비스 재사용" 추정이 틀렸음을 구현 전에 발견했다. 기존 훅이 관리자 API를 호출해 일반 사용자에게 403이 나는 문제였다.
- 삭제 판단을 순수 함수 한 곳에 두고 조회 성공 시에만 판단하게 해, Plan이 지목한 최대 위험(프로파일 지정 소실)이 구현에서 나타나지 않았다.
- 실서버 시나리오로 변경 전 동작(404)과 변경 후 동작(200)을 같은 데이터에서 비교해, 단위 테스트만으로 할 수 없는 확인을 했다.
- gap-detector를 구현 판단 없이 경로만 주고 돌려 G1·G2를 찾았다. 두 건 모두 제 테스트가 통과하던 상태에서 남아 있던 결함이다.

### 6.2 What Needs Improvement (Problem)

- Design §6.1에서 생성 경로 오류를 백엔드 코드를 읽지 않고 404로 가정했다. PATCH 경로의 `_raise_http`를 확인한 뒤 생성 라우터도 같다고 추정한 것이 원인이다.
- M5 테스트가 취소 경로만 검증해, 부모가 `isOpen`만 내리는 성공 경로(G2)를 놓쳤다.
- 기본 5초 타임아웃에서는 머신 부하로 전체 테스트의 실패 목록이 실행마다 달라져, 회귀 판정에 실행이 추가로 필요했다.

### 6.3 What to Try Next (Try)

- Design에 상태 코드를 적을 때는 해당 라우터의 예외 매핑 줄을 근거로 함께 적는다.
- 모달 초기화 테스트는 닫는 경로(취소, 성공, 부모 상태 변경)마다 하나씩 둔다.
- 전체 회귀는 `--testTimeout=30000`으로 돌리고 기준선 FAILED 목록과 diff한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 제안서 추정을 코드로 재확인 | 유지 |
| Design | 오류 상태 코드를 추정으로 기재 | 라우터 예외 매핑 `파일:라인`을 근거로 기재 |
| Do | 기준선 실패 목록을 먼저 저장 | 유지 |
| Check | 독립 gap 분석 + 실서버 시나리오 | 유지 |

### 7.2 Tools/Environment

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| Testing | `@vitest/coverage-v8` 설치 여부 결정 | Plan 커버리지 기준 측정 가능 |
| Testing | L3용 일반 사용자 계정과 컬렉션 권한 준비 | 브라우저 E2E와 일반 사용자 저장 확인 가능 |
| Build | 기존 `tsc -b` 오류 210건 정리 | `npm run build` 기준 복구 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 커밋: 이번 기능 파일만 선택. 같은 작업 트리의 `useAgentRunStream*`, `ChatPage/index.tsx`는 다른 작업이라 제외
- [ ] L3 E2E 수동 확인 또는 E2E 이월 체크리스트 등록
- [ ] 로컬 DB 정리 여부 결정: soft-deleted `[L3] kb-profile-selector` 프로파일 3행, KB 1행

### 8.2 Next PDCA Cycle

| Item | Priority |
|------|----------|
| Minor gap G3~G6 소형 사이클 | Medium |
| `docs/proposals/2026-10-15.md` 나머지 후보 | - |

---

## 9. Changelog

### v1.0.0 (2026-11-03)

**Added:**
- KB 생성·수정 모달의 조항 모드 청킹 프로파일 선택과 상세 표시
- KB 상세 청킹 설정 카드의 적용 프로파일 이름 표시
- 일반 사용자용 프로파일 목록 조회 (`GET /api/v1/chunking/profiles`)

**Changed:**
- 생성 요청에 `chunking_profile_id` 추가
- 생성 모달은 다시 열릴 때마다 폼을 초기화
- 생성 모달 `scroll="content"` 적용

**Fixed:**
- 삭제된 프로파일을 참조한 KB의 청킹 설정 저장 실패 (404)
- 생성 중 프로파일 삭제 시 부서/컬렉션을 가리키던 오류 문구
- 생성 성공 후 재오픈 시 이전 입력이 남던 문제

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-03 | Completion report created | 배상규 |
