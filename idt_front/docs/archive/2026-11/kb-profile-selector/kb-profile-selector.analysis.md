# kb-profile-selector Analysis Report

> **Analysis Type**: Gap Analysis
>
> **Project**: sangplusbot (idt_front)
> **Version**: 0.0.0
> **Analyst**: 배상규
> **Date**: 2026-11-03
> **Design Doc**: [kb-profile-selector.design.md](kb-profile-selector.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 조항 청킹의 프로파일을 KB 단위로 선택·확인할 수 없고, 삭제된 프로파일을 참조하면 설정 저장이 실패한다 |
| **WHO** | P2 (KB 운영자·에이전트 소유자) — S1 지식베이스 구축·검증 폐루프의 "청킹 전략 선택" 단계 |
| **RISK** | 기존 `useChunkingProfiles`는 관리자 API를 호출해 일반 사용자에게 403이 난다. 목록 조회 실패를 "프로파일 삭제"로 오판하면 KB의 프로파일 지정이 지워질 수 있다 |
| **SUCCESS** | 일반 사용자가 생성·수정 모달에서 프로파일을 저장하고 카드에서 이름을 확인한다. 삭제된 프로파일을 참조한 KB도 저장에 성공한다. 기존 관리자 화면 회귀 0건 |
| **SCOPE** | 프론트 단일 사이클: 조회 계층 → 선택 컴포넌트 → 생성·수정 모달 → 카드 요약. 백엔드·DB 변경 없음 |

---

## Strategic Alignment Check

PRD는 없다. Plan의 WHY 기준으로 판정한다.

| 항목 | 판정 | 근거 |
|------|:----:|------|
| 프로파일 선택·확인 불가 | ✅ | 생성·수정 모달 드롭다운, 카드 이름 표시 |
| 삭제 프로파일 참조 시 저장 실패 | ✅ | 실서버: 기존 동작(stale ID) 404 → 변경 후 `null` 저장 200 |
| Plan RISK 2건 | ✅ 미발생 | KB 화면은 관리자 API를 호출하지 않음(C8, 실서버 403 확인), 조회 실패 시 삭제로 판단하지 않음(U1, C5, K5) |

### Success Criteria Status (Plan §4.1)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | FR-01~FR-13 구현 | ⚠️ | FR-11 생성 모달 경로 부분 충족 (G2) |
| SC-2 | 일반 사용자 권한에서 조회·저장 실서버 확인 | ⚠️ | 조회: 일반 사용자 200·관리자 API 403. 저장: 일반 사용자에게 접근 가능한 컬렉션이 없어 관리자 소유 KB로 확인 |
| SC-3 | 삭제 프로파일 참조 KB 저장 성공, 응답 `null` | ✅ | 실서버 PATCH 200, `chunking_profile_id: null` |
| SC-4 | 목록 조회 실패 중 저장 시 기존 지정 유지 | ✅ | K5 |
| SC-5 | 기본·커스텀 모드 KB에서 목록 미조회 | ✅ | K1, M4, H2 |
| SC-6 | 관리자 프로파일 화면 회귀 0건 | ✅ | `AdminChunkingProfilesPage` 테스트 통과, 전체 FAILED diff 신규 0건 |

**Success Rate**: 4/6 충족, 2/6 부분 충족

### Quality Criteria (Plan §4.2)

| 기준 | Status | Evidence |
|------|:------:|----------|
| 정렬된 `FAILED` 목록 diff 0건 | ✅ | 기준선 14건(5초) / 변경 후 9건(30초), 신규 0건 |
| 변경 파일 lint 신규 오류 0건 | ✅ | ESLint exit 0 |
| `npx tsc -b` 통과 | ❌ | 기존 오류 212건으로 실패. 변경 코드 오류 0건 |
| `npm run build` 성공 | ❌ | `tsc -b` 단계에서 실패. `vite build`는 성공 |
| MSW 응답 = 실제 응답 구조 | ✅ | 실서버 응답 키 11개와 핸들러 키 일치 |
| 커버리지 (훅 80%, 컴포넌트 60%) | ❌ 미측정 | `@vitest/coverage-v8` 미설치 |

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | 생성+수정 모달 적용 | ✅ | - |
| [Plan] | 미선택 = `null` (late-binding) | ✅ | - |
| [Plan] | 삭제 프로파일 경고 후 기본 전환 | ✅ | - |
| [Plan] | 모달 상세 + 카드 이름 | ✅ | - |
| [Design] | Option C (판단 함수 + 선택 컴포넌트) | ✅ | - |
| [Design] | 상태는 부모 모달 소유 | ✅ | 생성 모달 state 이름이 `profileId` (Design은 `chunkingProfileId`) |
| [Design] | §6.1 생성 경로 404 처리 | ❌ | 백엔드 생성 라우터는 422를 반환한다. Design 전제가 틀렸다 (G1) |

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design 대비 구현 일치도와 Plan 성공 기준 충족 여부를 판정한다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/kb-profile-selector.design.md`
- **Implementation Path**: `src/components/knowledge-base/`, `src/hooks/useChunkingProfiles.ts`, `src/services/chunkingProfileService.ts`, `src/constants/api.ts`, `src/lib/queryKeys.ts`, `src/types/knowledgeBase.ts`, `src/__tests__/mocks/handlers.ts`
- **Method**: 정적 분석은 gap-detector 에이전트가 독립 수행(Read 전용). 런타임 검증은 직접 수행.
- **Analysis Date**: 2026-11-03

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints

| Design | Implementation | Status |
|--------|---------------|--------|
| GET `/api/v1/chunking/profiles` | `CHUNKING_PROFILES`, `getActiveChunkingProfiles` | ✅ |
| PATCH `/knowledge-bases/{id}/chunking` | 카드 저장 body | ✅ |
| POST `/knowledge-bases` + `chunking_profile_id` | 생성 모달 body | ✅ (오류 처리는 G1) |

### 2.2 Data Model

| Field | Design | Impl | Status |
|-------|--------|------|--------|
| `CreateKnowledgeBaseRequest.chunking_profile_id` | `string \| null` optional | 동일 | ✅ |
| `KbProfileSelection` 6필드 | §3 | `kbProfileSelection.ts` | ✅ |

### 2.3 Component Structure

| Design Component | Implementation File | Status |
|------------------|---------------------|--------|
| `KbProfileSelect` | `src/components/knowledge-base/KbProfileSelect.tsx` | ✅ |
| 판단 함수 3종 | `src/components/knowledge-base/kbProfileSelection.ts` | ✅ |
| `ChunkingModeSelector` props 4개 | 동일 파일 | ✅ |
| `useActiveChunkingProfiles({ enabled })` | `src/hooks/useChunkingProfiles.ts` | ✅ |

### 2.4 Functional Depth Analysis

placeholder나 mock 데이터를 쓰는 구현 파일은 없다. Shallow 파일 0/7.

### 2.5 Page UI Checklist Verification

| 영역 | Design Elements | Implemented | Rate |
|------|:--------------:|:-----------:|:----:|
| 프로파일 선택 영역 | 9 | 9 | 100% |
| 청킹 설정 카드 문구 | 5 | 5 | 100% |

### 2.6 API Contract Verification

| # | Check | Result |
|---|-------|:------:|
| 1~3 | 목록 URL·응답 구조·로그인 필요 | PASS |
| 4~6 | PATCH body, 비조항 `null`, 조항 오버라이드 유지 | PASS |
| 7~8 | POST 조항 `effectiveId`, 비조항 필드 생략 | PASS |
| 9~10 | 크기 우선순위(`or`/`is not None`), 폴백 순서 | PASS |
| 11 | PATCH 삭제 프로파일 404 | PASS |
| 12 | POST 삭제 프로파일 404 | **FAIL (G1)**: 실제 422 |
| 13 | 422 서버 메시지 표시 | PASS |

**Contract Match Rate**: 12/13 = 92%

### 2.7 Runtime Verification Results

#### L1: 실서버 API (localhost:8000)

| # | Test | Expected | Actual | Pass |
|---|------|----------|--------|:----:|
| 1 | 일반 사용자 목록 조회 | 200, `is_default` 포함 | 200, 키 11개 | ✅ |
| 2 | 일반 사용자의 관리자 API 호출 | 403 | 403 | ✅ |
| 3 | 토큰 없음 | 401 | 401 | ✅ |
| 4 | 조항 KB 생성 + 프로파일 지정 | 201, ID 저장 | 201, 저장됨 | ✅ |
| 5 | 프로파일 삭제 후 일반 목록 | 목록에서 빠짐 | 빠짐 | ✅ |
| 6 | 삭제 ID 그대로 PATCH (기존 동작) | 404 | 404 | ✅ |
| 7 | `null` PATCH (변경 동작) | 200, `null` | 200, `null` | ✅ |
| 8 | 비조항 모드 + 프로파일 ID | 422 | 422 | ✅ |

#4~#8은 관리자 소유 KB로 수행했다. 일반 사용자에게 접근 가능한 컬렉션이 없다.

**L1 Score**: 8/8

#### L2: UI Action (Vitest + RTL + MSW)

| 대상 | 테스트 | Pass |
|------|--------|:----:|
| U1~U10, S1, H1~H3, C1~C8, K1~K9, M1~M5 | 36건 | 36/36 |

K1·M4·H2의 "호출 0건" 검증은 20ms 대기에 의존한다(G8).

#### L3: E2E (브라우저)

미실행. 로그인 계정이 없어 브라우저 저장 흐름, 업로드 반영, 모달 실제 높이를 확인하지 못했다.

### 2.8 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  97%                 │
│  Functional Match Rate:  98%                 │
│  Contract Match Rate:    92%                 │
│  Runtime:                L1 8/8, L2 36/36, L3 미실행 │
│  ─────────────────────────────────────────── │
│  Overall Match Rate:     95%                 │
│  = (Structural × 0.2) + (Functional × 0.4)  │
│    + (Contract × 0.4)                        │
└─────────────────────────────────────────────┘
```

L3를 실행하지 않아 런타임 포함 공식 대신 정적 공식을 사용했다.

---

## 3. Code Quality Analysis

### 3.1 Gap List

| ID | Severity | Confidence | Gap | Evidence | Fix |
|----|----------|:-:|-----|----------|-----|
| G1 | Important | 95% (코드 확인) | 생성 중 프로파일이 삭제되면 백엔드는 422를 반환하고, 페이지는 "입력값을 확인해주세요 (부서/컬렉션)"을 표시해 엉뚱한 항목을 가리킨다. 생성 경로는 목록을 다시 조회하지 않아 같은 실패가 반복될 수 있다 | `idt/src/api/routes/knowledge_base_router.py:338-345`, `src/pages/KnowledgeBasesPage/index.tsx:17,80` | 422 메시지에 프로파일 문구가 있으면 전용 한국어 메시지를 표시하고 `chunkingProfiles.all`을 무효화한다. Design §6.1을 422로 정정한다 |
| G2 | Important | 90% (코드 확인) | 생성 성공 후 `setCreateOpen(false)`만 호출되어 `handleClose`를 거치지 않는다. 다시 열면 이전 조항 모드와 프로파일 선택이 남는다 (FR-11). 이름·컬렉션이 남는 것은 기존 결함 | `src/pages/KnowledgeBasesPage/index.tsx:76`, `CreateKnowledgeBaseModal.tsx:56` | `isOpen`이 false→true로 바뀔 때 폼을 초기화한다. M5에 성공 후 재오픈 경로를 추가한다 |
| G3 | Minor | 70% | 5분 캐시 목록으로 삭제를 판단해, 다른 곳에서 막 만든 프로파일을 삭제로 표시하고 저장 시 `null`로 바꿀 수 있다 | `hooks/useChunkingProfiles.ts:25` | 삭제 판단 시 1회 재조회 |
| G4 | Minor | 85% | 캐시가 있는 상태에서 재조회가 실패하면 드롭다운까지 숨긴다 | `KbProfileSelect.tsx:55-72` | 안내는 위에 표시하고 캐시로 옵션 유지 |
| G5 | Minor | 90% | 로딩 중 `label htmlFor`가 가리킬 요소가 없고, 안내 문구에 `role="status"`가 없다 | `KbProfileSelect.tsx:83-109` | `role="status"` 추가 |
| G6 | Minor | 95% | 수정 모달 404에서 영문 서버 메시지를 그대로 표시한다 | `KbChunkingSettingsCard.tsx:132-136` | 404 전용 한국어 메시지 |
| G7 | Minor | 100% | 생성 모달 state 이름, 테스트 ID `S1-1`이 Design과 다름 | `CreateKnowledgeBaseModal.tsx:45` | Design 정정 |
| G8 | Minor | 60% | "호출 0건" 테스트가 20ms 대기에 의존 | K1, M4 | `fetchStatus === 'idle'` 단언 추가 |
| G9 | Minor | 90% | M5가 취소 경로만 검증해 G2를 못 잡음 | `CreateKnowledgeBaseModal.test.tsx:193-204` | G2 수정과 함께 보강 |
| G10 | Minor | 80% | `// Design Ref: §N` 주석 대신 파일 헤더 docblock 사용 | `KbProfileSelect.tsx:1-6` | 선택 사항 |

### 3.2 Security Issues

없음. 경계 규칙 정규식 원문은 표시하지 않고, KB 화면에서 관리자 API를 호출하지 않는다.

---

## 4. Performance Analysis

조항 모드 KB 상세 진입 시 목록 요청 1건이 추가된다(Plan 예상과 동일). 카드·모달·선택 컴포넌트가 같은 쿼리 키를 써서 중복 요청은 없다.

---

## 5. Test Coverage

### 5.1 Coverage Status

미측정. `@vitest/coverage-v8`이 설치되어 있지 않으며, 의존성 추가는 승인 대상이라 설치하지 않았다.

### 5.2 Regression

| 실행 | 전체 | 실패 | 신규 실패 |
|------|:---:|:---:|:---:|
| 기준선 (변경 전, 5초) | 1,516 | 14 | - |
| 변경 후 (5초, maxWorkers=3) | 1,552 | 19 | 8 (부하 타임아웃, 단독 재실행 시 통과) |
| 변경 후 (30초, maxWorkers=3) | 1,552 | 9 | **0** |

기본 5초 타임아웃에서는 node 프로세스가 45개 떠 있는 부하 때문에 실패 목록이 실행마다 달라졌다. 30초 실행의 실패 9건은 모두 기준선 목록에 있다. 백엔드 KB·프로파일 계약 테스트 46건도 통과했다.

---

## 6. Clean Architecture Compliance

| Layer | Expected | Actual | Status |
|-------|----------|--------|:------:|
| 컴포넌트 | 훅, 판단 함수, 타입 | 동일 | ✅ |
| 훅 | 서비스, 쿼리 키 | 동일 | ✅ |
| 판단 함수 | 타입만 | `import type`만 사용 | ✅ |

---

## 7. Convention Compliance

- 신규 코드는 디자인 토큰만 사용하고 hex 값과 `text-[Npx]`는 쓰지 않았다. 기존 파일 스타일은 변경하지 않았다.
- 컴포넌트 파일은 default export만 하고, 런타임 함수는 `kbProfileSelection.ts`에 있다.
- `ApiError`는 `instanceof`와 `.status`로 사용하고 `err.response`는 읽지 않는다.
- `KbChunkingSettingsCard.tsx`가 207줄로 200줄 분리 검토 기준을 조금 넘는다.

---

## 8. Overall Score

| 항목 | 결과 |
|------|------|
| Match Rate | 95% |
| Important gap | 2건 (G1, G2) |
| Minor gap | 8건 |
| 미충족 품질 기준 | `tsc -b`·`npm run build`(기존 오류), 커버리지 미측정 |

---

## 9. Recommended Actions

### 9.1 Immediate

| Priority | Item | File |
|----------|------|------|
| 1 | G2 생성 성공 후 재오픈 초기화 + 테스트 | `CreateKnowledgeBaseModal.tsx` |
| 2 | G1 생성 경로 프로파일 오류 메시지·재조회 | `KnowledgeBasesPage/index.tsx` 또는 모달 |

### 9.2 Short-term

| Item | File |
|------|------|
| G6 404 한국어 메시지, G5 `role="status"` | `KbChunkingSettingsCard.tsx`, `KbProfileSelect.tsx` |
| G4 재조회 실패 시 드롭다운 유지 | `KbProfileSelect.tsx` |

### 9.3 Carry-over

| Item | Notes |
|------|-------|
| L3 E2E (Design §8.4 #1~5) | 일반 사용자 계정·컬렉션 필요 |
| 커버리지 측정 | `@vitest/coverage-v8` 설치 여부 결정 필요 |
| G3 캐시 기반 삭제 판단 | 발생 조건이 좁음 |

---

## 10. Design Document Updates

- [x] §6.1 생성 경로 오류를 404에서 422로 정정 (Design v0.2)
- [x] §5.3 생성 모달 state 이름을 `profileId`로 정정, 재오픈 초기화 명시
- [x] §8.3 테스트 M5-1, 페이지 G1·G2 추가

---

## 11. Act-1 (2026-11-03)

Checkpoint 5 결정: **Important만 수정**.

| Gap | 수정 | 테스트 (Red 확인 후 Green) |
|-----|------|------|
| G1 | `KnowledgeBasesPage`가 `Chunking profile … not found` 422를 구분해 전용 안내를 표시하고 `chunkingProfiles.all`을 무효화 | 페이지 G1 |
| G2 | `CreateKnowledgeBaseModal`이 `isOpen` false→true 전환 시 폼 전체 초기화 (렌더 중 이전 값 비교, effect 미사용). 이름·컬렉션이 남던 기존 결함도 함께 해소 | 페이지 G2, M5-1 |
| G9 | G2와 함께 해소 | M5-1 |

검증:
- 관련 17개 파일 116건 통과, 변경 파일 ESLint 0건, 변경 파일 타입 오류 0건
- 전체 1,555건 중 실패 9건, 모두 기준선 목록, 신규 0건 (30초 타임아웃)
- `vite build` 성공

재계산 (Design v0.2 기준, 본인 재판정이며 gap-detector 재실행 아님):

| 축 | Before | After |
|----|:-:|:-:|
| Structural | 97% | 100% |
| Functional | 98% | 100% |
| Contract | 92% | 100% |
| **Overall (정적 공식)** | **95%** | **100%** |

Design 축 기준 일치율이다. Design 범위 밖 Minor gap G3·G4·G5·G6·G8·G10과 L3 E2E는 남아 있다.

### 이월 항목

| 항목 | 사유 |
|------|------|
| G3 캐시 기반 삭제 판단 | 발생 조건이 좁음 |
| G4 재조회 실패 시 드롭다운 숨김 | 안전 측 동작 (지정 유지) |
| G5 `role="status"`·로딩 중 label 연결 | 접근성 개선 |
| G6 수정 모달 404 영문 메시지 | 문구 개선 |
| G8 "호출 0건" 테스트의 20ms 대기 | 테스트 견고성 |
| G10 Design Ref 주석 형식 | 선택 사항 |
| L3 E2E (Design §8.4 #1~5) | 일반 사용자 계정·컬렉션 필요 |
| 커버리지 측정 | `@vitest/coverage-v8` 설치 여부 결정 필요 |

---

## 12. Next Steps

- [ ] `/pdca report kb-profile-selector`
- [ ] 로컬 DB 잔여물: soft-deleted 상태의 `[L3] kb-profile-selector` 프로파일 3행과 KB 1행

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-03 | Initial analysis | 배상규 |
