# kb-profile-selector Planning Document

> **Summary**: KB의 조항 단위 청킹 모드에서 P2가 청킹 프로파일을 직접 선택하고, 적용 중인 프로파일을 확인하게 한다.
>
> **Project**: sangplusbot (idt_front)
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-02
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 조항 단위 청킹을 켜도 KB 화면에서 프로파일을 고를 수 없어 기본 프로파일로만 동작하고, 어떤 프로파일이 적용 중인지도 보이지 않는다. 참조 프로파일이 삭제된 KB는 청킹 설정 저장이 404로 실패한다. |
| **Solution** | 공용 `ChunkingModeSelector`의 조항 모드에 프로파일 드롭다운을 추가해 KB 생성·수정 모달에 함께 적용한다. 일반 사용자용 `GET /api/v1/chunking/profiles`를 프론트에 연결하며 백엔드는 변경하지 않는다. |
| **Function/UX Effect** | 드롭다운에서 "기본 프로파일 따름" 또는 특정 프로파일을 고르고 설명·크기·경계 규칙 수·섹션 요약 사용 여부를 확인한다. 청킹 설정 카드에는 적용 프로파일 이름이 표시되고, 삭제된 프로파일은 경고 후 기본 프로파일로 전환된다. |
| **Core Value** | 문서 유형별 프로파일을 KB마다 선택하고 결과를 화면에서 확인할 수 있어, S1의 "청킹 전략 선택" 단계가 관리자 개입 없이 완결된다. |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | 조항 청킹의 프로파일을 KB 단위로 선택·확인할 수 없고, 삭제된 프로파일을 참조하면 설정 저장이 실패한다 |
| **WHO** | P2 (KB 운영자·에이전트 소유자) — S1 지식베이스 구축·검증 폐루프의 "청킹 전략 선택" 단계 |
| **RISK** | 기존 `useChunkingProfiles`는 관리자 API를 호출해 일반 사용자에게 403이 난다. 목록 조회 실패를 "프로파일 삭제"로 오판하면 KB의 프로파일 지정이 지워질 수 있다 |
| **SUCCESS** | 일반 사용자가 생성·수정 모달에서 프로파일을 저장하고 카드에서 이름을 확인한다. 삭제된 프로파일을 참조한 KB도 저장에 성공한다. 기존 관리자 화면 회귀 0건 |
| **SCOPE** | 프론트 단일 사이클: 조회 계층 → 선택 컴포넌트 → 생성·수정 모달 → 카드 요약. 백엔드·DB 변경 없음 |

---

## 1. Overview

### 1.1 Purpose

조항 단위 청킹을 쓰는 KB가 어떤 경계 규칙과 요약 설정으로 문서를 처리할지 P2가 직접 정하고 확인하게 한다.

### 1.2 Background

- `kb-management-ui` 당시에는 일반 사용자용 프로파일 목록 API가 없어 조항 청킹 토글만 제공하고, 프로파일은 업로드 시점에 기본값으로 해석(late-binding)했다.
- 이후 `GET /api/v1/chunking/profiles`가 생겼지만 KB 폼에 연결되지 않았다. `chunking-profile-admin-ui`는 이 작업을 후속 `kb-profile-selector`로 이월했다.
- `docs/proposals/2026-10-15.md` 후보 #5의 "훅 1(기존 서비스 재사용)" 추정은 코드와 다르다. 기존 서비스와 훅은 관리자 API(`/api/v1/admin/chunking/profiles`)를 호출하므로 일반 조회 경로를 새로 연결해야 한다. 백엔드 변경이 없다는 판단은 유효하다.

### 1.3 Related Documents

- 유저 시나리오: `docs/USER-SCENARIOS.md` (S1)
- 제안: `docs/proposals/2026-10-15.md` §2-5
- 선행 아카이브: `idt/docs/archive/2026-07/chunking-profile-admin-ui/`
- 위키: `docs/wiki/backend/db/erd-kb.md`, `docs/wiki/frontend/screens/kb-screens.md`, `docs/wiki/conventions/false-green-quality-gates.md`
- 근거 코드
  - `idt/src/api/routes/chunking_profile_router.py:22` — 인증 사용자용 active 프로파일 목록
  - `idt/src/application/knowledge_base/chunking_resolver.py:117` — 참조 프로파일 → 기본 → legacy 폴백
  - `idt/src/application/knowledge_base/use_case.py:176` — 프로파일 ID·오버라이드 검증
  - `src/components/knowledge-base/KbChunkingSettingsCard.tsx:82` — 현재 조항 모드 저장 로직

---

## 2. Scope

### 2.1 In Scope

- [ ] 일반 조회 API의 엔드포인트 상수, 서비스 메서드, 쿼리 키, TanStack Query 훅 추가
- [ ] 조항 모드 프로파일 선택 컴포넌트 추가 (기본 프로파일 따름 + active 프로파일 목록 + 상세 정보)
- [ ] KB 생성 모달과 청킹 설정 수정 모달에 공통 적용
- [ ] 생성 요청 타입에 `chunking_profile_id` 추가 (API 계약 동기화)
- [ ] 삭제된 프로파일 참조 시 경고 후 기본 프로파일 따름으로 전환
- [ ] 목록 로딩·실패, 프로파일 없음, 기본 프로파일 없음 상태 처리
- [ ] 청킹 설정 카드에 적용 프로파일 이름 표시
- [ ] 위 동작의 Vitest + RTL + MSW 테스트

### 2.2 Out of Scope

- 백엔드 API, 스키마, DB 변경
- 프로파일 생성·수정·삭제 UI (관리자 화면 유지)
- 경계 규칙 정규식 전문 표시와 청킹 프리뷰 (규칙 수만 표시)
- KB별 `chunk_size`·`chunk_overlap` 오버라이드 입력 UI (기존 값 보존만 수행)
- 프로파일 변경 시 기존 문서 재청킹·재요약 (D10 유지: 이후 업로드부터 적용)
- 요약 LLM 모델 이름 표시 (응답에 ID만 있으므로 사용 여부만 표시)
- 에이전트 빌더의 프로파일 프리필
- `KbChunkingSettingsCard`, `CreateKnowledgeBaseModal`의 기존 스타일 전면 교체

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `GET /api/v1/chunking/profiles`를 호출하는 상수·서비스·훅을 추가한다. 쿼리 키는 `chunkingProfiles.all` 하위에 두어 관리자 변경 시 함께 무효화한다. | High | Pending |
| FR-02 | 조항 모드에서만 프로파일 드롭다운을 렌더링하고, 이때만 목록을 조회한다. | High | Pending |
| FR-03 | 첫 항목은 "기본 프로파일 따름"이며 `chunking_profile_id: null`로 저장한다. 현재 기본 프로파일 이름을 함께 표시한다. | High | Pending |
| FR-04 | 선택 항목의 설명, parent/chunk 크기, 오버랩, 경계 규칙 수, 섹션 요약 사용 여부를 표시한다. "기본 프로파일 따름"은 기본 프로파일 기준으로 표시한다. | Medium | Pending |
| FR-05 | KB에 `chunk_size`·`chunk_overlap` 오버라이드가 있으면 FR-04의 크기 표시는 실제 적용값을 따른다 (`chunking_resolver.py:49-54`와 동일한 우선순위). | Medium | Pending |
| FR-06 | 수정 모달은 `kb.chunking_profile_id`로 프리필하고 선택값을 PATCH로 저장한다. 조항 모드의 오버라이드는 보존하고, 다른 모드에서는 프로파일 ID·오버라이드를 모두 `null`로 보낸다. | High | Pending |
| FR-07 | 생성 모달은 조항 모드일 때만 선택값을 `chunking_profile_id`로 보낸다. 다른 모드에서는 필드를 보내지 않는다. | High | Pending |
| FR-08 | 목록 조회 성공 후 `kb.chunking_profile_id`가 목록에 없으면 "삭제된 프로파일이며 기본 프로파일로 처리 중"이라는 경고를 표시하고, 선택값을 기본 프로파일 따름으로 둔다. 저장하면 `null`을 보낸다. | High | Pending |
| FR-09 | 목록 로딩·실패 상태에서는 삭제로 판단하지 않고 기존 `chunking_profile_id`를 보존한다. 실패 시 재시도 수단을 제공한다. | High | Pending |
| FR-10 | active 프로파일이 없거나 기본 프로파일이 없으면 "기본 프로파일을 선택하면 업로드가 기본 청킹으로 처리된다"는 안내를 표시한다. | Medium | Pending |
| FR-11 | 모드를 조항에서 다른 모드로 바꿨다가 돌아오면 모달을 닫기 전까지 선택값을 유지한다. 모달을 다시 열면 KB 저장값으로 초기화한다. | Medium | Pending |
| FR-12 | 청킹 설정 카드는 조항 모드 KB에서 지정 프로파일 이름, 기본 프로파일 이름, 삭제 경고를 구분해 표시한다. 목록 조회 전이나 실패 시에는 기존 문구를 유지한다. | Medium | Pending |
| FR-13 | 기존 "이후 업로드부터 적용" 안내와 서버 오류 표시 동작을 유지한다. | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 기본·커스텀 모드 KB는 프로파일 목록을 조회하지 않는다. 조항 모드 조회는 5분 캐시를 사용한다. | MSW 호출 횟수 테스트 |
| Security | 일반 KB 화면에서 `/api/v1/admin/chunking/*`를 호출하지 않는다. | 테스트에서 호출 URL 단언 |
| Accessibility | 드롭다운에 `ariaLabel`을 제공하고 경고·상태는 색상과 텍스트를 함께 사용한다. | RTL role 조회, 코드 리뷰 |
| Maintainability | 새 코드는 `idt_front/CLAUDE.md` 디자인 토큰을 따르고 컴포넌트 파일에서 런타임 상수·헬퍼를 export하지 않는다. | ESLint, 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-13 구현
- [ ] 일반 사용자 권한에서 프로파일 조회·저장이 실서버로 확인됨 (로컬 불가 시 E2E 이월 항목으로 기록)
- [ ] 삭제된 프로파일을 참조한 KB가 저장에 성공하고 응답의 `chunking_profile_id`가 `null`임
- [ ] 목록 조회 실패 상태에서 저장해도 기존 프로파일 지정이 유지됨
- [ ] 기본·커스텀 모드 KB에서 프로파일 목록을 조회하지 않음
- [ ] 관리자 프로파일 화면 테스트 회귀 0건

### 4.2 Quality Criteria

- [ ] 변경 전후의 정렬된 `FAILED` 목록 diff가 0건 (통과 개수 비교로 대체하지 않음)
- [ ] `npm run lint` 신규 오류 0건
- [ ] `npx tsc -b` 통과 (`tsc --noEmit`만으로 판단하지 않음)
- [ ] `npm run build` 성공
- [ ] MSW 핸들러 응답이 실제 `ProfileListResponse` 구조와 일치
- [ ] 신규 훅 80%, 신규 컴포넌트 60% 이상 커버리지

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 기존 관리자 훅을 재사용해 일반 사용자에게 403 발생 | High | Medium | 일반 조회 경로를 분리하고 호출 URL을 테스트로 고정 |
| 목록 조회 실패를 삭제로 오판해 프로파일 지정 소실 | High | Medium | `isSuccess`일 때만 삭제 판단, FR-09 전용 테스트 작성 |
| 모드 변경 시 `chunking_profile_id`를 함께 보내 백엔드 422 발생 | Medium | Medium | 비조항 모드 전송값을 테스트로 고정 |
| 관리자 프로파일 변경 후 KB 화면에 오래된 목록 노출 | Medium | Low | 쿼리 키를 `chunkingProfiles.all` 하위에 배치, 저장 시 서버 검증 오류 표시 |
| 선택과 저장 사이 프로파일 삭제로 404 발생 | Low | Low | 서버 메시지 표시 후 목록 재조회 |
| 카드의 목록 조회로 KB 상세 진입 시 요청 1건 증가 | Low | High | 조항 모드에서만 조회, 공유 캐시 사용, 실패해도 기존 문구 유지 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/constants/api.ts` | Config | 일반 프로파일 목록 엔드포인트 상수 추가 |
| `src/lib/queryKeys.ts` | Config | `chunkingProfiles.all` 하위 일반 목록 키 추가 |
| `src/services/chunkingProfileService.ts` | Service | 일반 목록 조회 메서드 추가 |
| `src/hooks/useChunkingProfiles.ts` | Hook | 일반 목록 조회 훅 추가, 기존 관리자 훅 유지 |
| `src/types/knowledgeBase.ts` | Type | `CreateKnowledgeBaseRequest.chunking_profile_id` optional 추가 |
| `src/components/knowledge-base/` 신규 선택 컴포넌트 | Component | 드롭다운·상세·경고 표시 |
| `src/components/knowledge-base/ChunkingModeSelector.tsx` | Component | 조항 모드 영역과 props 추가 |
| `src/components/knowledge-base/CreateKnowledgeBaseModal.tsx` | Component | 선택 상태와 제출 필드 추가 |
| `src/components/knowledge-base/KbChunkingSettingsCard.tsx` | Component | 선택 상태, 저장 필드, 카드 요약 변경 |
| `src/__tests__/mocks/handlers.ts` | Test | 일반 목록 기본 핸들러 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `useChunkingProfiles` | READ | `pages/AdminChunkingProfilesPage/index.tsx:312` | None (변경 없음) |
| `chunkingProfiles.all` | INVALIDATE | `hooks/useChunkingProfiles.ts` 관리자 뮤테이션 4종 | 의도된 변경 (일반 목록도 함께 갱신) |
| `ChunkingModeSelector` | RENDER | `CreateKnowledgeBaseModal.tsx:249` | Needs verification (props 추가) |
| `ChunkingModeSelector` | RENDER | `KbChunkingSettingsCard.tsx:121` | Needs verification (props 추가) |
| `CreateKnowledgeBaseRequest` | CREATE | `pages/KnowledgeBasesPage` → `POST /api/v1/knowledge-bases` | None (optional 추가, 백엔드 수용 중) |
| `UpdateKbChunkingRequest` | UPDATE | `KbChunkingSettingsCard.tsx:79` | None (기존 필드 사용) |
| `KbChunkingSettingsCard` | RENDER | `pages/KnowledgeBaseDetailPage/index.tsx:78` | Needs verification (조항 모드에서 조회 1건 추가) |
| 기존 모달 테스트 | READ | `CreateKnowledgeBaseModal.test.tsx:92` | Needs verification (조항 radio 선택 시 목록 조회 발생) |

### 6.3 Verification

- [ ] All consumers listed above verified to work with the proposed changes
- [ ] No auth/permission changes break existing operations
- [ ] No field additions/removals break existing queries or mutations

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure (`components/`, `lib/`, `types/`) | Static sites, portfolios, landing pages | ☐ |
| **Dynamic** | Feature-based modules, BaaS integration (bkend.ai) | Web apps with backend, SaaS MVPs, fullstack apps | ☑ |
| **Enterprise** | Strict layer separation, DI, microservices | High-traffic systems, complex architectures | ☐ |

기존 `idt_front` 구조(`components` → `hooks` → `services`)를 유지하며 BaaS는 사용하지 않는다.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 적용 위치 | 수정 모달만 / 생성+수정 | 생성+수정 | 공용 selector로 변경량이 작고 생성 후 재설정 단계가 사라짐 (사용자 확정) |
| 미선택 의미 | null 유지 / 기본 ID 고정 | null 유지 | 기존 late-binding 유지, 기본 변경이 KB에 반영됨 (사용자 확정) |
| 삭제 프로파일 | 경고 후 기본 전환 / 재선택 강제 | 경고 후 기본 전환 | 실제 업로드 폴백과 일치하고 저장 실패 해소 (사용자 확정) |
| 표시 범위 | 모달만 / 모달+카드 | 모달 상세+카드 이름 | 적용 프로파일을 모달을 열지 않고 확인 (사용자 확정) |
| 조회 경로 | 관리자 API 재사용 / 일반 API 연결 | 일반 API 연결 | 관리자 API는 일반 사용자에게 403 |
| 프로파일 상태 소유 | 공용 selector / 부모 모달 | 부모 모달 | 저장 body를 만드는 곳이 부모이고 기존 customForm과 같은 구조 |
| 서버 상태 | TanStack Query | TanStack Query | 프로젝트 규칙, 기존 키 팩토리 재사용 |
| 드롭다운 | 네이티브 select / `common/Dropdown` | `common/Dropdown` | 같은 모달에서 이미 사용 중 |
| 테스트 | Vitest + RTL + MSW | Vitest + RTL + MSW | 프로젝트 표준 |

### 7.3 Clean Architecture Approach

```
Selected Level: Dynamic (기존 idt_front 구조)

KbChunkingSettingsCard / CreateKnowledgeBaseModal   ← 선택값 상태, 저장 body 조립
  └─ ChunkingModeSelector                           ← 조항 모드 영역 추가
       └─ KB 프로파일 선택 컴포넌트 (신규)            ← 조항 모드에서만 마운트
            └─ 일반 목록 훅 → chunkingProfileService → GET /api/v1/chunking/profiles
```

프로파일 표시 판단(삭제 여부, 기본 프로파일, 실제 적용값)은 컴포넌트 밖 순수 함수로 분리할지 Design에서 확정한다. 모달과 카드가 같은 판단을 쓰므로 한 곳에 둔다.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section (`idt_front/CLAUDE.md`)
- [ ] `docs/01-plan/conventions.md` exists (Phase 2 output)
- [ ] `CONVENTIONS.md` exists at project root
- [x] ESLint configuration
- [ ] Prettier configuration (확인 불필요: 이번 범위에 설정 변경 없음)
- [x] TypeScript configuration (`tsconfig.json`)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Naming** | exists | 관리자 조회와 구분되는 일반 목록 훅·서비스 이름을 Design에서 확정 | High |
| **Folder structure** | exists | 신규 컴포넌트는 `components/knowledge-base/`, 런타임 헬퍼는 별도 `.ts` | High |
| **Import order** | exists | 인접 파일 유지 | Low |
| **Environment variables** | exists | 추가 없음 | Low |
| **Error handling** | exists | `authApiClient`의 `ApiError.message`를 사용 (`err.response` 미사용) | Medium |

### 8.3 Environment Variables Needed

추가 환경변수 없음.

### 8.4 Pipeline Integration

9단계 Development Pipeline을 사용하지 않는다. 단일 PDCA 사이클로 진행한다.

---

## 9. Next Steps

1. [ ] Design 문서 작성: `/pdca design kb-profile-selector`
2. [ ] Design에서 "기본 프로파일 따름"의 Dropdown 값 표현(`''` 또는 별도 상수)과 표시 판단 함수 위치 확정
3. [ ] Red 테스트부터 구현

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | Initial draft | 배상규 |
