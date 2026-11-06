# kb-profile-selector Design Document

> **Summary**: 조항 모드 프로파일 선택을 KB 생성·수정 모달에 추가하고, 삭제 판단을 순수 함수 한 곳으로 모은다.
>
> **Project**: sangplusbot (idt_front)
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-02
> **Status**: Draft
> **Planning Doc**: [kb-profile-selector.plan.md](kb-profile-selector.plan.md)

### Pipeline References

9단계 Pipeline 문서를 사용하지 않는다 (N/A).

---

## Context Anchor

> Copied from Plan document. Ensures strategic context survives Design→Do handoff.

| Key | Value |
|-----|-------|
| **WHY** | 조항 청킹의 프로파일을 KB 단위로 선택·확인할 수 없고, 삭제된 프로파일을 참조하면 설정 저장이 실패한다 |
| **WHO** | P2 (KB 운영자·에이전트 소유자) — S1 지식베이스 구축·검증 폐루프의 "청킹 전략 선택" 단계 |
| **RISK** | 기존 `useChunkingProfiles`는 관리자 API를 호출해 일반 사용자에게 403이 난다. 목록 조회 실패를 "프로파일 삭제"로 오판하면 KB의 프로파일 지정이 지워질 수 있다 |
| **SUCCESS** | 일반 사용자가 생성·수정 모달에서 프로파일을 저장하고 카드에서 이름을 확인한다. 삭제된 프로파일을 참조한 KB도 저장에 성공한다. 기존 관리자 화면 회귀 0건 |
| **SCOPE** | 프론트 단일 사이클: 조회 계층 → 선택 컴포넌트 → 생성·수정 모달 → 카드 요약. 백엔드·DB 변경 없음 |

---

## 1. Overview

### 1.1 Design Goals

- 프로파일 선택 UI를 생성·수정 모달이 같은 컴포넌트로 공유한다.
- 화면 표시와 저장 값이 같은 판단 결과를 쓰게 한다.
- 조회 실패 상태에서 KB의 기존 프로파일 지정을 변경하지 않는다.

### 1.2 Design Principles

- **판단은 한 곳에**: 삭제 여부, 실제 적용 프로파일, 기본 청킹 폴백은 `resolveProfileSelection`만 계산한다.
- **백엔드 해석과 일치**: 표시 규칙은 `chunking_resolver.py`의 폴백 순서와 크기 우선순위를 따른다.
- **상태는 저장하는 쪽이 소유**: 선택값은 저장 body를 만드는 부모 모달이 가진다. 기존 `customForm`과 같은 구조다.
- **조회는 필요할 때만**: 조항 모드가 아니면 목록을 조회하지 않는다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 기존 파일에 직접 구현 | 판단·훅·선택·상세·경고 분리 | 판단 함수와 선택 컴포넌트만 분리 |
| **New Files (테스트 제외)** | 0 | 5 | 2 |
| **Modified Files** | 8 | 9 | 9 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 삭제 판단 중복 | 구조 과다 | Low |

**Selected**: Option C (사용자 확정) — **Rationale**: 모달·카드·저장이 같은 판단을 써야 하므로 판단 함수는 분리한다. 나머지 UI는 사용처가 하나이므로 더 나누지 않는다.

### 2.1 Component Diagram

```
KnowledgeBasesPage → CreateKnowledgeBaseModal ─┐ 선택값 state, 제출 body
KnowledgeBaseDetailPage → KbChunkingSettingsCard ┤ 선택값 state, PATCH body, 카드 요약
                                                 │
                                       ChunkingModeSelector
                                                 │ mode === 'clause'
                                          KbProfileSelect (신규)
                                                 │
        useActiveChunkingProfiles ──────────────┤ resolveProfileSelection (신규, 순수 함수)
                 │
   chunkingProfileService.getActiveChunkingProfiles
                 │
      GET /api/v1/chunking/profiles
```

### 2.2 Data Flow

```
수정 모달 열기 → profileId = kb.chunking_profile_id ?? null
조항 모드 선택 → 목록 조회 → resolveProfileSelection(profileId, 목록)
드롭다운 변경 → setProfileId(id | null)
저장 → effectiveId를 PATCH → knowledgeBases 무효화 → 카드 요약 갱신
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `KbProfileSelect` | `useActiveChunkingProfiles`, `resolveProfileSelection`, `Dropdown`, `Button` | 선택·상세·경고 표시 |
| `KbChunkingSettingsCard` | 위 훅과 함수 | 카드 요약, 저장값 계산 |
| `CreateKnowledgeBaseModal` | 위 훅과 함수 | 제출값 계산 |
| `ChunkingModeSelector` | `KbProfileSelect` | 조항 모드 영역 렌더링 |

---

## 3. Data Model

DB와 서버 엔티티 변경은 없다. 프론트 타입만 추가한다.

```typescript
// src/types/knowledgeBase.ts — additive
export interface CreateKnowledgeBaseRequest {
  // 기존 필드 유지
  chunking_profile_id?: string | null;
}

// src/components/knowledge-base/kbProfileSelection.ts
export interface KbProfileSelection {
  isListReady: boolean;                  // 목록 조회 성공 여부
  effectiveId: string | null;            // 저장할 값
  isStale: boolean;                      // 지정 ID가 active 목록에 없음
  defaultProfile: ChunkingProfile | null;
  appliedProfile: ChunkingProfile | null; // 지정 프로파일 또는 기본 프로파일
  usesLegacyFallback: boolean;           // 적용 프로파일 없음 → 업로드는 기본 청킹
}
```

`resolveProfileSelection(selectedId, profiles)` 결과:

| 입력 | isListReady | effectiveId | isStale | appliedProfile | usesLegacyFallback |
|------|:-:|:-:|:-:|---|:-:|
| 목록 없음 (로딩·실패) | false | `selectedId` | false | null | false |
| 지정 ID가 목록에 있음 | true | `selectedId` | false | 지정 프로파일 | false |
| `null`, 기본 있음 | true | null | false | 기본 프로파일 | false |
| 지정 ID가 목록에 없음, 기본 있음 | true | null | true | 기본 프로파일 | false |
| `null`, 기본 없음 | true | null | false | null | true |
| 지정 ID가 목록에 없음, 기본 없음 | true | null | true | null | true |

호출부는 `query.isSuccess ? query.data : undefined`를 넘긴다. 재조회 실패로 이전 데이터가 남아 있어도 삭제로 판단하지 않는다.

크기 표시는 `effectiveProfileSizes(profile, kbChunkSize, kbChunkOverlap)`가 계산한다.

```typescript
chunkSize = kbChunkSize || profile.chunk_size;      // resolver의 `or`와 동일
chunkOverlap = kbChunkOverlap ?? profile.chunk_overlap; // resolver의 `is not None`과 동일
parentChunkSize = profile.parent_chunk_size;
```

카드 문구는 `clauseProfileSummary(selection)`가 만든다.

---

## 4. API Specification

새 백엔드 API는 없다. 기존 계약을 프론트에 연결한다.

### 4.1 Endpoint List

| Method | Path | Description | Auth | 변경 |
|--------|------|-------------|------|------|
| GET | `/api/v1/chunking/profiles` | active 프로파일 목록 | 로그인 사용자 | 프론트 신규 연결 |
| PATCH | `/api/v1/knowledge-bases/{kbId}/chunking` | 청킹 설정 전체 교체 | 소유자·ADMIN | 호출 값만 변경 |
| POST | `/api/v1/knowledge-bases` | KB 생성 | 로그인 사용자 | `chunking_profile_id` 전송 |

### 4.2 Detailed Specification

#### `GET /api/v1/chunking/profiles`

```json
{
  "profiles": [{
    "profile_id": "string",
    "name": "string",
    "description": null,
    "boundary_rules": [{ "pattern": "string", "priority": 1, "level": "parent" }],
    "parent_chunk_size": 2000,
    "chunk_size": 500,
    "chunk_overlap": 50,
    "is_default": true,
    "summary_llm_model_id": null,
    "created_at": null,
    "updated_at": null
  }],
  "total": 1
}
```

관리자 목록과 응답 모델이 같으므로 `ChunkingProfileListResponse`를 재사용한다.

#### 저장 값

| 모드 | PATCH `chunking_profile_id` | POST `chunking_profile_id` |
|------|---|---|
| 조항 | `selection.effectiveId` | `selection.effectiveId` |
| 기본·커스텀 | `null` (백엔드는 값이 있으면 422) | 필드 생략 |

조항 모드의 `chunk_size`·`chunk_overlap`은 PATCH에서 기존 값을 그대로 보낸다.

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
( ) 기본 청킹
(•) 조항 단위 청킹
( ) 커스텀 청킹

청킹 프로파일
[ 기본 프로파일 따름 (여신 규정)            ▾ ]
┌─────────────────────────────────────────┐
│ 조·항 경계 기준으로 분할합니다             │
│ 부모 2000 · 청크 500 · 오버랩 50          │
│ 경계 규칙 3개 · 섹션 요약 사용             │
└─────────────────────────────────────────┘
```

### 5.2 User Flow

```
KB 생성·수정 모달 → 조항 단위 청킹 선택 → 프로파일 선택 → 상세 확인 → 저장
→ KB 상세 카드에서 적용 프로파일 이름 확인
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `KbProfileSelect` (신규) | `src/components/knowledge-base/` | 드롭다운, 상세, 상태 안내, 재시도 |
| `ChunkingModeSelector` | 동일 | 조항 모드에서 `KbProfileSelect` 렌더링, props 전달 |
| `CreateKnowledgeBaseModal` | 동일 | `profileId` state, 다시 열 때 초기화(`isOpen` false→true), 제출 |
| `KbChunkingSettingsCard` | 동일 | `profileId` state, 열기 초기화, 저장, 요약 |

`ChunkingModeSelector` 추가 props:

```typescript
profileId: string | null;
onProfileChange: (profileId: string | null) => void;
kbChunkSize?: number | null;
kbChunkOverlap?: number | null;
```

### 5.4 Page UI Checklist

#### 프로파일 선택 영역 (생성·수정 모달 공통)

- [ ] 조항 모드에서만 표시
- [ ] Label: "청킹 프로파일", Dropdown `ariaLabel="청킹 프로파일"`
- [ ] 첫 옵션: "기본 프로파일 따름 ({기본 프로파일 이름})", 기본 프로파일이 없으면 "기본 프로파일 따름"
- [ ] 이후 옵션: active 프로파일 이름, 기본 프로파일에 badge "기본"
- [ ] 상세: 설명(있을 때), 부모·청크·오버랩 크기, 경계 규칙 수, 섹션 요약 사용 여부
- [ ] 로딩: Dropdown 스켈레톤
- [ ] 실패: "프로파일 목록을 불러오지 못했습니다. 저장해도 현재 지정은 유지됩니다." + "다시 시도" 버튼 (`type="button"`)
- [ ] 삭제 경고: "지정한 프로파일이 삭제되어 기본 프로파일로 처리됩니다. 저장하면 기본 프로파일 따름으로 변경됩니다."
- [ ] 기본 청킹 안내: "적용할 기본 프로파일이 없어 업로드가 기본 청킹으로 처리됩니다."

#### 청킹 설정 카드 (조항 모드 KB)

| 상태 | 문구 |
|------|------|
| 목록 로딩·실패 | 조항 단위 청킹 (프로파일 기반) |
| 지정 프로파일 | 조항 단위 청킹 — {이름} |
| 기본 프로파일 따름 | 조항 단위 청킹 — 기본 프로파일 ({이름}) |
| 삭제, 기본 있음 | 조항 단위 청킹 — 삭제된 프로파일, 기본 프로파일 ({이름}) 적용 |
| 적용 프로파일 없음 | 조항 단위 청킹 — 프로파일 없음, 기본 청킹으로 처리 |

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | 발생 지점 | 처리 |
|------|----------|------|
| 401 | 목록·저장 | `authApiClient` 공통 처리 |
| 조회 실패 (4xx 일부·5xx·네트워크) | 목록 | FR-09 실패 안내와 재시도, 기존 지정 유지 |
| 404 | PATCH (선택 후 프로파일 삭제) | `ApiError.message` 표시, `chunkingProfiles.all` 무효화 |
| 422 | POST (선택 후 프로파일 삭제) | 생성 라우터는 `ValueError`를 모두 422로 바꾼다 (`knowledge_base_router.py:338-345`). 메시지가 `Chunking profile … not found`이면 `KnowledgeBasesPage`가 전용 안내를 표시하고 `chunkingProfiles.all`을 무효화한다 |
| 422 | PATCH·POST (그 외) | 기존 서버 메시지 표시 |

v0.1은 POST 경로를 404로 가정하고 재조회를 생략했다. Check(G1)에서 실제 상태 코드가 422이고 일반 문구("입력값을 확인해주세요 (부서/컬렉션)")가 표시되는 것을 확인해 v0.2에서 정정했다.

### 6.2 Error Response Format

서버는 `{ "detail": "message" }`를 반환하고 `authApiClient`가 `ApiError.message`로 변환한다. 컴포넌트는 `err.response`를 읽지 않는다.

---

## 7. Security Considerations

- [x] 입력 검증: 프로파일 ID는 서버가 active 여부를 검증 (`use_case.py:202`)
- [x] 권한: 일반 조회는 로그인 사용자, 저장은 기존 소유자·ADMIN 검사 유지
- [ ] KB 화면에서 관리자 API를 호출하지 않음을 테스트로 고정
- [x] 경계 규칙 정규식 원문은 화면에 표시하지 않음 (개수만 표시)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0: Unit | 판단 함수, 서비스, 훅 | Vitest | Do |
| L1: API | 일반 사용자 토큰의 목록 조회 | 기존 pytest + 실서버 curl | Check |
| L2: UI Action | 모달·카드 동작 | Vitest + RTL + MSW | Do |
| L3: E2E | 실제 화면 저장 흐름 | Chrome 수동 확인 | Check (불가 시 E2E 이월) |

프로젝트에 Playwright 테스트 체계가 없으므로 L2는 RTL로 작성한다.

### 8.2 L1: API Test Scenarios

| # | Endpoint | Method | Test Description | Expected Status | Expected Response |
|---|----------|--------|-----------------|:--------------:|-------------------|
| 1 | `/api/v1/chunking/profiles` | GET | 일반 사용자 조회 | 200 | `profiles[].is_default` 포함 |
| 2 | `/api/v1/chunking/profiles` | GET | 미인증 | 401 | - |
| 3 | `/knowledge-bases/{id}/chunking` | PATCH | 삭제 프로파일 참조 KB에 `null` 저장 | 200 | `chunking_profile_id: null` |

### 8.3 L2: UI Action Test Scenarios

**`kbProfileSelection.test.ts`**

| # | 대상 | 기대 결과 |
|---|------|----------|
| U1~U6 | §3 표의 6개 입력 | 표의 결과와 일치 |
| U7 | 오버라이드 없음 | 프로파일 크기 반환 |
| U8 | `chunk_size` 오버라이드 | KB 값 사용 |
| U9 | `chunk_overlap` 오버라이드 0 | 0 유지 |
| U10 | `clauseProfileSummary` | §5.4 카드 문구 5종 |

**`chunkingProfileService.test.ts`, 훅 테스트**

| # | 대상 | 기대 결과 |
|---|------|----------|
| S1 | `getActiveChunkingProfiles` | `/api/v1/chunking/profiles` 호출 |
| H1 | `useActiveChunkingProfiles` | `profiles` 배열 반환 |
| H2 | `enabled: false` | 호출 0건 |
| H3 | 관리자 프로파일 변경 후 무효화 | 목록 재조회 |

**`KbProfileSelect.test.tsx`**

| # | Action | Expected Result |
|---|--------|----------------|
| C1 | 렌더링 | 첫 옵션과 기본 badge 표시 |
| C2 | 프로파일 선택 | `onChange(id)` 호출, 상세 갱신 |
| C3 | 기본 따름 선택 | `onChange(null)` 호출 |
| C4 | 오버라이드 있음 | 실제 적용 크기 표시 |
| C5 | 조회 실패 후 재시도 | 안내 표시, 재시도 시 재호출 |
| C6 | 지정 ID 없음 | 삭제 경고 표시 |
| C7 | 프로파일 0건 | 기본 청킹 안내 표시 |
| C8 | 호출 URL | 관리자 경로 호출 0건 |

**`KbChunkingSettingsCard.test.tsx` 추가**

| # | Action | Expected Result |
|---|--------|----------------|
| K1 | 기본 모드 KB 렌더링 | 프로파일 호출 0건 |
| K2 | 조항 모드 KB 렌더링 | 카드에 프로파일 이름 |
| K3 | 프로파일 변경 후 저장 | PATCH에 새 ID, 오버라이드 유지 |
| K4 | 삭제 프로파일 KB 저장 | PATCH `chunking_profile_id: null` |
| K5 | 조회 실패 중 저장 | PATCH에 기존 ID 유지 |
| K6 | 조항→커스텀→조항 | 선택값 유지 |
| K7 | 변경 후 취소, 재오픈 | KB 저장값으로 초기화 |
| K8 | 조항→기본 저장 | 프로파일·오버라이드 `null` |
| K9 | PATCH 404 | 메시지 표시, 목록 재조회 |

**`CreateKnowledgeBaseModal.test.tsx` 추가**

| # | Action | Expected Result |
|---|--------|----------------|
| M1 | 조항 + 프로파일 선택 후 생성 | 선택 ID 전달 |
| M2 | 조항 + 기본 따름 | `null` 전달 |
| M3 | 커스텀으로 전환 후 생성 | `chunking_profile_id` 없음 |
| M4 | 고급 옵션 미사용 | 프로파일 호출 0건 |
| M5 | 닫은 뒤 재오픈 | 선택값 초기화 |
| M5-1 | `isOpen` false→true (생성 성공 경로) | 선택값 초기화 |

**`KnowledgeBasesPage/index.test.tsx` 추가 (v0.2)**

| # | Action | Expected Result |
|---|--------|----------------|
| G1 | 생성 POST가 프로파일 누락 422 | 전용 안내 표시, 프로파일 목록 재조회 |
| G2 | 생성 성공 후 재오픈 | 이름·청킹 선택 초기화 |

### 8.4 L3: E2E Scenario Test Scenarios

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | 수정 저장 | 일반 사용자 로그인 → KB 상세 → 프로파일 변경 → 저장 | 403 없음, 카드 이름 변경 |
| 2 | 생성 | 조항 + 프로파일 선택 → 생성 → 상세 진입 | 카드에 선택 프로파일 표시 |
| 3 | 업로드 반영 | 프로파일 지정 KB에 문서 업로드 | 청크가 해당 경계 규칙으로 생성 |
| 4 | 삭제 복구 | 관리자가 프로파일 삭제 → KB 저장 | 저장 성공, 카드 문구 변경 |
| 5 | 레이아웃 | 375·768·1440 폭에서 모달 확인 | 드롭다운과 저장 버튼 접근 가능 |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:------------:|---------------------|
| MSW 프로파일 | 2 | 기본 1건, 일반 1건 (`summary_llm_model_id` 지정·미지정 각 1건) |
| 로컬 DB 프로파일 | 2 | 기본 1건, 삭제 가능한 일반 1건 |
| 일반 사용자 | 1 | `role=user`, KB 소유자 |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Presentation** | 컴포넌트, 훅 | `src/components/knowledge-base/`, `src/hooks/` |
| **Application** | API 호출 | `src/services/` |
| **Domain** | 타입, 표시 판단 | `src/types/`, `kbProfileSelection.ts` |
| **Infrastructure** | 엔드포인트, 쿼리 키 | `src/constants/`, `src/lib/` |

### 9.2 Dependency Rules

`kbProfileSelection.ts`는 타입만 import하고 React·서비스에 의존하지 않는다. 컴포넌트는 서비스를 직접 호출하지 않고 훅을 사용한다.

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| 컴포넌트 | 훅, 판단 함수, 타입 | axios, `authApiClient` |
| 훅 | 서비스, 쿼리 키 | 컴포넌트 |
| 판단 함수 | 타입 | 훅, 서비스 |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `KbProfileSelect` | Presentation | `src/components/knowledge-base/KbProfileSelect.tsx` |
| `useActiveChunkingProfiles` | Presentation | `src/hooks/useChunkingProfiles.ts` |
| `getActiveChunkingProfiles` | Application | `src/services/chunkingProfileService.ts` |
| `resolveProfileSelection` 외 | Domain | `src/components/knowledge-base/kbProfileSelection.ts` |
| `CHUNKING_PROFILES`, `chunkingProfiles.active` | Infrastructure | `src/constants/api.ts`, `src/lib/queryKeys.ts` |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

프로젝트 규칙을 따른다. 컴포넌트 파일은 PascalCase, 유틸 파일은 camelCase다.

### 10.2 Import Order

인접 파일 순서를 유지한다.

### 10.3 Environment Variables

추가 없음.

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| Component naming | `KbProfileSelect` (`Kb*` 접두 유지) |
| File organization | 런타임 함수·상수는 `.ts`, 컴포넌트 파일은 default export만 |
| State management | 서버 상태 TanStack Query, 선택값 `useState` |
| Styling | 신규 컴포넌트는 디자인 토큰 사용, 기존 파일 스타일은 변경하지 않음 |
| Error handling | `ApiError.message` 사용 |
| Comment | `// Design Ref: §N` 형식, 주요 판단 지점에만 작성 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── constants/api.ts                                  # CHUNKING_PROFILES 추가
├── lib/queryKeys.ts                                  # chunkingProfiles.active 추가
├── services/chunkingProfileService.ts                # getActiveChunkingProfiles 추가
├── hooks/useChunkingProfiles.ts                      # useActiveChunkingProfiles 추가
├── types/knowledgeBase.ts                            # 생성 요청 필드 추가
├── __tests__/mocks/handlers.ts                       # 일반 목록 핸들러 추가
└── components/knowledge-base/
    ├── kbProfileSelection.ts            (신규)
    ├── KbProfileSelect.tsx              (신규)
    ├── ChunkingModeSelector.tsx
    ├── CreateKnowledgeBaseModal.tsx
    └── KbChunkingSettingsCard.tsx
```

훅 시그니처:

```typescript
export const useActiveChunkingProfiles = ({ enabled = true } = {}) =>
  useQuery({
    queryKey: queryKeys.chunkingProfiles.active(),
    queryFn: () => chunkingProfileService.getActiveChunkingProfiles(),
    staleTime: 5 * 60 * 1000,
    select: (data) => data.profiles,
    enabled,
  });
```

조회 조건:

| 위치 | `enabled` |
|------|-----------|
| `KbProfileSelect` | 기본값 (조항 모드에서만 마운트) |
| `KbChunkingSettingsCard` | `modeOf(kb) === 'clause' \|\| (editOpen && mode === 'clause')` |
| `CreateKnowledgeBaseModal` | `isOpen && chunkingMode === 'clause'` |

세 곳이 같은 쿼리 키를 쓰므로 요청은 한 건으로 합쳐진다.

드롭다운 값은 `selection.effectiveId ?? ''`이고, `onChange`는 `value || null`로 변환한다. `Dropdown`은 `''`를 일반 옵션 값으로 처리한다.

### 11.2 Implementation Order

1. [ ] 일반 목록 조회 계층과 MSW 핸들러 (S1, H1~H3)
2. [ ] `kbProfileSelection.ts` (U1~U10)
3. [ ] `KbProfileSelect` (C1~C8)
4. [ ] `ChunkingModeSelector` props 추가
5. [ ] `KbChunkingSettingsCard` (K1~K9)
6. [ ] `CreateKnowledgeBaseModal` + 타입 (M1~M5)
7. [ ] lint, `tsc -b`, build, 전체 테스트 `FAILED` 목록 diff
8. [ ] 모달 높이 확인. `Modal` 기본 `scroll="none"`이라 화면을 넘으면 생성 모달에 `scroll="content"` 적용

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 조회 계층 | `module-1` | 상수, 쿼리 키, 서비스, 훅, MSW | 5-8 |
| 판단·선택 | `module-2` | `kbProfileSelection`, `KbProfileSelect` | 10-15 |
| 모달 연결 | `module-3` | 공용 selector, 카드, 생성 모달, 타입 | 10-15 |

#### Recommended Session Plan

작업량이 작아 한 세션에서 전체를 구현한다. 나눌 경우 module 순서를 따른다.

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | 전체 | 25-35 |
| Session 2 | Check + Report | 전체 | 15-20 |

### 11.4 FR 추적

| FR | 설계 위치 | 테스트 |
|----|----------|--------|
| FR-01 | §4.2, §11.1 | S1, H1, H3 |
| FR-02 | §11.1 조회 조건 | K1, M4, H2 |
| FR-03 | §5.4, §11.1 | C1, C3, M2 |
| FR-04 | §5.4 | C2 |
| FR-05 | §3 | U7~U9, C4 |
| FR-06 | §4.2 | K3, K8 |
| FR-07 | §4.2 | M1, M3 |
| FR-08 | §3, §5.4 | U4, U6, C6, K4 |
| FR-09 | §3, §5.4 | U1, C5, K5 |
| FR-10 | §5.4 | U5, U6, C7 |
| FR-11 | §1.2, §5.3 | K6, K7, M5 |
| FR-12 | §5.4 | U10, K2 |
| FR-13 | §6.1 | 기존 카드 테스트 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | Initial draft (Option C) | 배상규 |
| 0.2 | 2026-11-03 | Check 반영: §6.1 생성 경로 422 정정, 생성 모달 재오픈 초기화, 테스트 M5-1·G1·G2 추가 | 배상규 |
