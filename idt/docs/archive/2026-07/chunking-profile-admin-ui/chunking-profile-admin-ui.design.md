# chunking-profile-admin-ui Design Document

> **Summary**: `/admin/chunking-profiles` 관리자 페이지 — 청킹 프로파일 CRUD + 기본 지정 + 조항 요약 LLM 배정 UI (프론트 전용, 백엔드 변경 없음)
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규
> **Date**: 2026-07-15
> **Status**: Draft
> **Plan**: `docs/01-plan/features/chunking-profile-admin-ui.plan.md`

---

## 1. Overview

### 1.1 Design Goals

1. 기존 백엔드 admin API(`admin_chunking_router.py`)를 **있는 그대로** 소비 — 계약 변경 0건
2. `AdminLlmModelsPage`의 검증된 페이지 패턴(테이블 + 폼 모달 + ConfirmDialog + TanStack Query)을 그대로 준용해 리뷰·유지보수 비용 최소화
3. PUT 전체 교체 API의 데이터 소실 리스크를 폼 설계로 원천 차단 (전체 필드 프리필 → 전체 바디 전송)
4. 요약 LLM 지정이 "무엇에 쓰이는지" 화면에서 이해되도록 안내 문구 내장

### 1.2 Design Principles

- 신규 UI 패턴 발명 금지 — 스타일 토큰(`inputCls`/`labelCls`), 모달 초기화 패턴, 에러 표면화 모두 AdminLlmModelsPage에서 복제
- 클라이언트 검증은 최소(필수값·정규식 컴파일) — 값 범위 검증은 서버 422가 진실, detail을 그대로 표시
- TDD: 서비스 → 훅 → 컴포넌트 → 페이지 순으로 테스트 선행

---

## 2. Design Decisions (D1–D10)

| ID | 결정 | 근거 |
|----|------|------|
| D1 | 페이지는 `pages/AdminChunkingProfilesPage/index.tsx` 단일 파일 + 내부 서브컴포넌트(폼 모달) 구성. 규칙 편집기만 별도 파일 | AdminLlmModelsPage 선례(751줄 단일 파일) — 규칙 편집기는 복잡도가 높아 분리·단위 테스트 |
| D2 | 수정 모달은 **목록 응답의 프로파일 객체 전체로 프리필** — 별도 GET 상세 호출 없음. submit 시 전체 필드를 PUT 바디로 전송 | list 응답(`ProfileResponse`)이 전체 필드를 포함, PUT은 전체 교체이므로 누락 필드 = 소실 (Plan Risk-1) |
| D3 | LLM 모델 데이터는 `useLlmModels(true)`(비활성 포함) 1회 조회로 통일. 드롭다운 옵션은 active만 필터, 단 수정 대상 프로파일이 비활성 모델을 참조 중이면 해당 모델을 "(비활성)" 라벨로 옵션에 추가 유지. 테이블 표시는 id→display_name 매핑, 매핑 실패 시 id 원문 표시 | 기존 훅 재사용(중복 API 없음), 비활성 모델 참조 프로파일의 수정 시 값이 조용히 사라지는 것 방지 |
| D4 | `summary_llm_model_id` 드롭다운 첫 옵션은 `"사용 안 함 (요약 비활성)"`(value="") → 전송 시 `null` 변환. 필드 아래 고정 안내: "조항 청킹 KB 업로드 시 섹션 요약·키워드 추출에 사용됩니다. 미지정 시 요약이 실행되지 않습니다." | FR-04/FR-05. None=비활성이 백엔드 계약 (`admin_chunking_router.py:41-42`) |
| D5 | 경계 규칙 편집기는 신규 `BoundaryRulesEditor` 컴포넌트 — 행 단위 추가/삭제, 각 행 = pattern(text) + priority(number) + level(select: parent/child). `customChunkingForm.ts`의 `isValidRegex`를 import 재사용 | KB 커스텀 청킹의 규칙 편집 UX 준용하되, admin 프로파일 규칙은 `level` 필드가 있어 폼 스키마가 다름 — 컴포넌트 재사용 불가, 검증 유틸만 재사용 |
| D6 | 클라이언트 검증: ① name 필수 ② 규칙 최소 1건 + 각 pattern 비어있지 않음 + `isValidRegex` 통과 ③ 사이즈 3종은 양의 정수. 그 외(chunk_overlap < chunk_size 등 도메인 규칙)는 서버 422 detail 표시 | 서버 `ChunkingProfilePolicy`가 최종 검증자 — 중복 구현 금지 |
| D7 | 기본 지정은 목록 행의 "기본 지정" 액션 버튼(PUT `/profiles/{id}/default`) + 생성/수정 폼의 `is_default` 체크박스 병행 | 전용 엔드포인트 활용(1클릭 UX) + 생성 시점 지정도 지원. 서버가 기존 기본 자동 해제 |
| D8 | 삭제는 ConfirmDialog(variant=danger) 필수. 설명 문구: "이 프로파일을 참조 중인 KB는 다음 업로드부터 기본 프로파일로 폴백됩니다." | `chunking_resolver._load_profile`의 default 폴백 동작을 사용자에게 고지 (Plan Risk-5) |
| D9 | `queryKeys.chunkingProfiles = { all, list }` 신설. 모든 뮤테이션 성공 시 `all` invalidate, 404 시에도 invalidate(타 관리자 선삭제 재동기화) | `useLlmModels`의 `invalidateOn404` 선례 |
| D10 | adminNav에 "청킹 프로파일" 항목을 'LLM 모델' 다음 순서로 추가 (요약 LLM 연계 인접 배치), `ADMIN_ENTRY_PATH` 불변 | 메뉴 논리 그룹핑 (모델 → 모델을 소비하는 프로파일) |

---

## 3. Architecture

### 3.1 Data Flow

```
AdminChunkingProfilesPage
  ├─ useChunkingProfiles() ──── GET /api/v1/admin/chunking/profiles ──▶ 목록 테이블
  ├─ useLlmModels(true) ─────── GET /api/v1/llm-models?include_inactive=true
  │                              └▶ id→display_name 매핑 + 폼 드롭다운 옵션
  ├─ ProfileFormModal (생성/수정 겸용, D2 프리필)
  │    ├─ BoundaryRulesEditor (D5)
  │    └─ submit ─▶ useCreateChunkingProfile ── POST /profiles
  │               └▶ useUpdateChunkingProfile ── PUT  /profiles/{id}
  ├─ "기본 지정" 액션 ─▶ useSetDefaultChunkingProfile ── PUT /profiles/{id}/default
  └─ ConfirmDialog ─▶ useDeleteChunkingProfile ── DELETE /profiles/{id}
       (뮤테이션 성공 → queryKeys.chunkingProfiles.all invalidate)
```

### 3.2 신규/변경 파일

| 파일 | 신규/변경 | 내용 |
|------|:---:|------|
| `src/constants/api.ts` | 변경 | `ADMIN_CHUNKING_PROFILES`, `ADMIN_CHUNKING_PROFILE_DETAIL(id)`, `ADMIN_CHUNKING_PROFILE_DEFAULT(id)` |
| `src/types/chunkingProfile.ts` | 신규 | §4 타입 전체 |
| `src/services/chunkingProfileService.ts` | 신규 | list/create/update/setDefault/remove (authApiClient) |
| `src/lib/queryKeys.ts` | 변경 | `chunkingProfiles` 키 그룹 |
| `src/hooks/useChunkingProfiles.ts` | 신규 | 쿼리 1 + 뮤테이션 4 |
| `src/pages/AdminChunkingProfilesPage/index.tsx` | 신규 | 페이지 + ProfileFormModal |
| `src/pages/AdminChunkingProfilesPage/BoundaryRulesEditor.tsx` | 신규 | 규칙 리스트 편집기 |
| `src/constants/adminNav.ts` | 변경 | "청킹 프로파일" 항목 (D10) |
| `src/App.tsx` | 변경 | `/admin/chunking-profiles` 라우트 |
| 테스트 4종 | 신규 | §8 참조 |

---

## 4. Data Model (TypeScript — 백엔드 계약 1:1)

```typescript
// src/types/chunkingProfile.ts
// 계약 원본: idt/src/api/routes/admin_chunking_router.py

export type BoundaryRuleLevel = 'parent' | 'child';

export interface BoundaryRule {
  pattern: string;
  priority: number;
  level: BoundaryRuleLevel;
}

/** ProfileResponse (admin_chunking_router.py:45) */
export interface ChunkingProfile {
  profile_id: string;
  name: string;
  description: string | null;
  boundary_rules: BoundaryRule[];
  parent_chunk_size: number;
  chunk_size: number;
  chunk_overlap: number;
  is_default: boolean;
  summary_llm_model_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** ChunkingProfileBody (admin_chunking_router.py:33) — 생성/수정 공용(PUT 전체 교체) */
export interface ChunkingProfileRequest {
  name: string;
  description: string | null;
  boundary_rules: BoundaryRule[];
  parent_chunk_size: number;
  chunk_size: number;
  chunk_overlap: number;
  is_default: boolean;
  summary_llm_model_id: string | null;
}

export interface ChunkingProfileListResponse {
  profiles: ChunkingProfile[];
  total: number;
}

export interface ChunkingProfileMessageResponse {
  profile_id: string;
  message: string;
}
```

---

## 5. API Specification (기존 백엔드 — 변경 없음)

| Method | Path | 용도 | 프론트 함수 |
|--------|------|------|------------|
| GET | `/api/v1/admin/chunking/profiles` | active 목록 | `getChunkingProfiles` |
| POST | `/api/v1/admin/chunking/profiles` | 생성 (201) | `createChunkingProfile` |
| PUT | `/api/v1/admin/chunking/profiles/{id}` | **전체 교체** 수정 | `updateChunkingProfile` |
| PUT | `/api/v1/admin/chunking/profiles/{id}/default` | 기본 지정 | `setDefaultChunkingProfile` |
| DELETE | `/api/v1/admin/chunking/profiles/{id}` | soft delete | `deleteChunkingProfile` |

- 인증: 전부 `require_role("admin")` — 401/403은 기존 authApiClient 처리 경로
- GET `/profiles/{id}` 상세는 존재하나 **미사용** (D2 — 목록 데이터로 충분)
- 비-admin `/api/v1/chunking/profiles`는 이번 스코프 미사용 (후속 kb-profile-selector)

---

## 6. UI/UX Design

### 6.1 페이지 레이아웃

헤더: `Admin / 청킹 프로파일` + 설명("조항 청킹 경계 규칙과 섹션 요약 LLM을 프로파일 단위로 관리합니다.") + 우측 "프로파일 등록" 버튼.

테이블 컬럼:

| 컬럼 | 내용 |
|------|------|
| 이름 | name + `기본` 뱃지(violet) + description 보조 텍스트 |
| 사이즈 | `parent 2000 · chunk 500 · overlap 50` 형식 |
| 경계 규칙 | `N개` (툴팁: 패턴 목록) |
| 요약 LLM | display_name 매핑 / null → `요약 비활성`(zinc 뱃지) / 매핑 실패 → id 원문 |
| 수정일 | `formatDate(updated_at)` |
| 액션(우측) | 수정 · 기본 지정(is_default면 숨김) · 삭제 |

상태: 로딩("로딩 중...") / 에러(재시도 버튼) / 빈 목록("+ 첫 번째 프로파일 등록하기") — AdminLlmModelsPage와 동일 3분기.

### 6.2 ProfileFormModal (생성/수정 겸용)

```
┌─ 청킹 프로파일 등록/수정 ────────────────────── size=lg ─┐
│ 이름* [________________]  설명 [___________________]     │
│                                                          │
│ Parent 크기 [2000]  Chunk 크기 [500]  Overlap [50]       │
│                                                          │
│ 경계 규칙* ──────────────────── [+ 규칙 추가]            │
│ ┌ pattern [^제\s*\d+\s*장] priority [1] level [parent ▼] ✕│
│ └ pattern [^제\s*\d+\s*조] priority [1] level [child  ▼] ✕│
│                                                          │
│ 요약 LLM  [사용 안 함 (요약 비활성)          ▼]          │
│  └ 조항 청킹 KB 업로드 시 섹션 요약·키워드 추출에        │
│    사용됩니다. 미지정 시 요약이 실행되지 않습니다.       │
│                                                          │
│ ☐ 기본 프로파일  (지정 시 기존 기본은 자동 해제)         │
│ [에러 메시지 영역]                    [취소] [저장]      │
└──────────────────────────────────────────────────────────┘
```

- `noValidate` 폼 + 커스텀 인라인 에러 (jsdom 제약·프로젝트 선례)
- 모달 열림 1회 초기화 패턴(`initialized` 플래그) 준용
- 수정 모드: 전체 필드 프리필(D2), profile_id는 표시 전용

### 6.3 BoundaryRulesEditor

- props: `{ rules: BoundaryRule[]; onChange: (rules: BoundaryRule[]) => void }`
- 행 추가 기본값: `{ pattern: '', priority: 1, level: 'child' }`
- pattern 입력이 `isValidRegex` 실패 시 해당 행에 빨간 테두리 + "유효하지 않은 정규식" 인라인 표시 (submit 차단은 폼 레벨 검증에서)
- 마지막 행 삭제 가능(0건 상태 허용) — 단 submit 시 "경계 규칙을 1개 이상 추가하세요" 에러

---

## 7. Error Handling

| 상황 | HTTP | 처리 |
|------|------|------|
| 이름 중복 | 409 | 폼 에러 영역에 서버 detail 표시 |
| 프로파일 없음 (타 관리자 선삭제) | 404 | 에러 표시 + `chunkingProfiles.all` invalidate (D9) |
| 값 범위/도메인 규칙 위반 | 422 | 폼 에러 영역에 서버 detail 표시 |
| 인증 만료/권한 없음 | 401/403 | 기존 authApiClient 전역 처리 |
| 목록 조회 실패 | any | 에러 상태 + 재시도 버튼 |

에러 메시지 추출은 `getErrorMessage(err, fallback)` 패턴 복제 (authClient가 ApiError로 정규화).

---

## 8. Test Plan (TDD — 테스트 선행, `--pool=threads`)

MSW는 파일별 `server.listen/resetHandlers/close` 3종 훅 직접 선언 (전역 setup 없음).

### 8.1 `chunkingProfileService.test.ts`

- [ ] list: GET 호출 + `profiles` 배열 반환
- [ ] create: POST 바디에 `summary_llm_model_id: null` 포함 확인
- [ ] update: PUT 바디에 **전체 필드** 포함 확인 (D2 회귀 가드)
- [ ] setDefault / remove: 경로 확인

### 8.2 `BoundaryRulesEditor.test.tsx`

- [ ] 행 추가/삭제 시 onChange 호출값 검증
- [ ] 잘못된 정규식 입력 시 인라인 에러 렌더
- [ ] level select 변경 반영

### 8.3 `AdminChunkingProfilesPage/index.test.tsx`

- [ ] 목록 렌더: 이름·기본 뱃지·요약 LLM display_name 매핑·"요약 비활성" 표시
- [ ] 생성 플로우: 폼 입력 → POST → 목록 invalidate
- [ ] 수정 프리필: 기존 값 전체가 폼에 로드되고, 이름만 바꿔 저장해도 PUT 바디에 나머지 필드 보존 (핵심 시나리오)
- [ ] 비활성 LLM 참조 프로파일 수정 시 "(비활성)" 옵션 유지 (D3)
- [ ] 필수값 누락/정규식 오류 시 인라인 에러 + 요청 미발생
- [ ] 기본 지정 액션 → PUT /default 호출
- [ ] 삭제: ConfirmDialog 확인 후 DELETE, 폴백 안내 문구 렌더
- [ ] 409/422 서버 detail 표시

### 8.4 `adminNav.test.ts` (기존 파일 갱신)

- [ ] `/admin/chunking-profiles` 경로 포함

### 8.5 수동 검증 (E2E — 백엔드 기동 시)

- [ ] 프로파일에 요약 LLM 지정 → 조항 청킹 KB 업로드 → section_summary_job이 해당 llm_model_id로 생성되는지 확인

---

## 9. Clean Architecture — Layer Assignment

프론트 전용. idt 백엔드 레이어 영향 없음.

| 계약 (idt) | 프론트 (idt_front) | 상태 |
|------------|-------------------|------|
| `admin_chunking_router.py` 스키마 | `types/chunkingProfile.ts` | 신규 1:1 매핑 |
| 엔드포인트 5종 | `constants/api.ts` + `services/chunkingProfileService.ts` | 신규 |

---

## 10. Implementation Order

1. `types/chunkingProfile.ts` + `constants/api.ts` 상수 (계약 고정)
2. `chunkingProfileService.test.ts` → `chunkingProfileService.ts` (Red→Green)
3. `lib/queryKeys.ts` + `useChunkingProfiles.ts` (훅은 페이지 테스트로 커버)
4. `BoundaryRulesEditor.test.tsx` → `BoundaryRulesEditor.tsx`
5. `index.test.tsx` → `AdminChunkingProfilesPage/index.tsx`
6. `adminNav.ts` + `adminNav.test.ts` + `App.tsx` 라우트
7. 전체 테스트 + lint + build

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-15 | Initial draft — D1~D10, 프론트 전용 설계 | 배상규 |
