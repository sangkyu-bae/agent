# chunking-profile-admin-ui Planning Document

> **Summary**: 청킹 프로파일(조항 경계 규칙·사이즈·섹션 요약 LLM)을 관리하는 관리자 화면 — 백엔드 CRUD API는 완성돼 있으나 프론트 UI가 전무한 상태를 해소
>
> **Project**: sangplusbot (idt_front 프론트엔드 중심, idt 백엔드 변경 없음)
> **Author**: 배상규
> **Date**: 2026-07-15
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 조항(clause) 청킹의 경계 규칙과 **문서 조항 단위 요약·키워드 추출에 쓸 LLM**(`summary_llm_model_id`)은 청킹 프로파일에 저장되는데, 이를 관리하는 화면이 없다. 백엔드 admin CRUD API(`/api/v1/admin/chunking/profiles`)는 완성돼 있으나 프론트에서 호출하는 곳이 0곳 — 현재는 Swagger/curl 또는 DB 직접 수정으로만 운영 가능하다. |
| **Solution** | `/admin/chunking-profiles` 관리자 페이지를 신설한다. 프로파일 목록 + 생성/수정 폼(경계 규칙 정규식 편집, 사이즈 3종, 요약 LLM 셀렉트) + 기본 지정 + 삭제를 기존 admin API에 그대로 배선한다. 백엔드는 손대지 않는다. |
| **Function/UX Effect** | 관리자가 화면에서 조항 청킹 규칙과 요약 LLM을 직접 제어. 특히 admin/llm-models에 등록된 활성 모델 중 하나를 드롭다운으로 골라 섹션 요약 파이프라인에 연결할 수 있게 된다(현재는 불가능). |
| **Core Value** | 조항 청킹→섹션 요약→라우팅 검색으로 이어지는 파이프라인의 마지막 수동 운영 구간을 셀프서비스화 — API만 있고 UI가 없는 반쪽 기능을 완성한다. |

---

## 1. Overview

### 1.1 Purpose

청킹 프로파일 CRUD를 관리자 화면에서 수행할 수 있게 한다.
핵심 동기: KB 업로드 시 조항 단위 요약·키워드 추출에 사용할 LLM은
프로파일의 `summary_llm_model_id`로 결정되는데(기본모델 아님), 이 값을 바꿀 UI가 없다.

### 1.2 Background (현재 구조 분석 — 2026-07-15 확인)

| 항목 | 현재 상태 | 근거 코드 |
|------|-----------|----------|
| 백엔드 admin API | 풀 CRUD + default 지정 + 삭제, `require_role("admin")` 가드 완비 | `idt/src/api/routes/admin_chunking_router.py` (POST/GET/PUT/DELETE `/api/v1/admin/chunking/profiles`, PUT `.../{id}/default`) |
| 요약 LLM 필드 | `summary_llm_model_id`(nullable, None=요약 비활성) 요청/응답에 포함 | `admin_chunking_router.py:42,54` |
| 프리필용 읽기 API | `/api/v1/chunking/profiles` (비-admin 목록) 존재하나 프론트 미사용 | `chunking_profile_router.py:19-22` |
| DB | `chunking_profile` 테이블 + summary 컬럼 마이그레이션 완료 | `V041__create_chunking_profile.sql`, `V043__alter_chunking_profile_add_summary_model.sql` |
| 프론트 라우트 | admin 라우트에 청킹 프로파일 없음 (users/departments/mcp-servers/llm-models/skills/ragas/agent-runs/wiki만) | `idt_front/src/App.tsx:69-77` |
| 프론트 API 상수/서비스 | admin chunking 엔드포인트 상수·서비스·훅 전무, `summary_llm_model_id` 검색 결과 0건 | `idt_front/src/constants/api.ts` |
| KB 폼 접점 | `KbChunkingSettingsCard`는 기존 `chunking_profile_id`를 보존만 함(선택 UI 없음) | `KbChunkingSettingsCard.tsx:82-83` |
| 참조 패턴 | LLM 모델 관리 페이지가 동일 성격(admin CRUD 단일 페이지)으로 존재 | `idt_front/src/pages/AdminLlmModelsPage/index.tsx` |

### 1.3 Related Documents

- 선행 기능: `clause-aware-chunking`(프로파일 CRUD API 원형), `card-section-summary`(summary_llm_model_id 도입, D2), `kb-custom-chunking`(정규식 편집 UI 선례) — 모두 `docs/archive/2026-07/`
- 규칙: `idt_front/CLAUDE.md`, 루트 `CLAUDE.md` §4-1(API 계약 동기화), `idt/docs/rules/testing.md`

---

## 2. Scope

### 2.1 In Scope

**프론트엔드 (idt_front/) — 이번 기능의 전부**
- [ ] `/admin/chunking-profiles` 라우트 + `AdminChunkingProfilesPage` 신설 (`AdminLlmModelsPage` 패턴 준용)
- [ ] 프로파일 목록 테이블: 이름, 설명, 사이즈 3종(parent/chunk/overlap), 경계 규칙 개수, 요약 LLM(모델명 표시, 없으면 "요약 비활성"), 기본 뱃지
- [ ] 생성/수정 폼: name, description, parent_chunk_size, chunk_size, chunk_overlap, boundary_rules 리스트 편집(pattern 정규식 + priority + level(parent/child) — kb-custom-chunking 정규식 편집 UX 준용), is_default 토글, **summary_llm_model_id 드롭다운**(활성 LLM 모델 목록 + "사용 안 함" 옵션)
- [ ] 기본 프로파일 지정 액션 (PUT `/profiles/{id}/default`)
- [ ] 삭제 액션 + 확인 다이얼로그 (soft delete — 목록은 active만 반환됨을 안내)
- [ ] API 상수(`constants/api.ts`) + 타입(`types/`) + 서비스(`services/chunkingProfileService.ts`) + TanStack Query 훅 신설
- [ ] `adminNav.ts` 메뉴 등록 + `adminNav.test.ts` 갱신
- [ ] Vitest + RTL + MSW 테스트 선행 작성 (TDD)

### 2.2 Out of Scope

- **백엔드 변경 일체 없음** — API·스키마·DB 현행 그대로 사용 (PATCH 부분수정 미지원도 수용, PUT 전체 교체로 처리)
- KB 생성/수정 폼에서 프로파일 선택 드롭다운 (`/api/v1/chunking/profiles` 프리필 배선) → 후속 `kb-profile-selector`
- 프로파일 변경 시 기존 문서 재요약/재인덱싱 (변경은 이후 업로드부터 적용)
- 요약 잡 모니터링/재시도 UI (section_summary_job 조회) → 후속 후보
- 청킹 프리뷰(정규식 테스트) UI → 후속 후보

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 관리자는 `/admin/chunking-profiles`에서 활성 프로파일 목록을 조회할 수 있다 | High | Pending |
| FR-02 | 관리자는 프로파일을 생성할 수 있다 (이름 중복 시 409 에러 메시지 표시) | High | Pending |
| FR-03 | 관리자는 프로파일 전체 필드를 수정할 수 있다 (수정 폼은 기존 값 프리필 — PUT 전체 교체이므로 필수) | High | Pending |
| FR-04 | 관리자는 `summary_llm_model_id`를 활성 LLM 모델 드롭다운에서 선택하거나 "사용 안 함"(null)으로 지정할 수 있다 | High | Pending |
| FR-05 | 요약 LLM 드롭다운 옆에 동작 안내를 표시한다: "조항 청킹 KB 업로드 시 섹션 요약·키워드 추출에 사용. 미지정 시 요약 비활성" | Medium | Pending |
| FR-06 | 관리자는 특정 프로파일을 기본으로 지정할 수 있다 (기존 기본은 자동 해제됨을 UI에 반영) | High | Pending |
| FR-07 | 관리자는 프로파일을 삭제할 수 있다 (확인 다이얼로그 필수) | Medium | Pending |
| FR-08 | boundary_rules는 행 추가/삭제/수정 가능한 리스트 편집기로 제공한다 (pattern·priority·level) | High | Pending |
| FR-09 | admin 사이드바 내비게이션에 "청킹 프로파일" 메뉴가 노출된다 | High | Pending |
| FR-10 | API 실패(401/404/409/422) 시 사용자에게 서버 detail 메시지를 표시한다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 접근 제어 | 서버측 `require_role("admin")`이 최종 가드 — 프론트는 admin 메뉴 노출 제어만 담당(기존 admin 페이지와 동일 수준) | 기존 adminNav 패턴 준수 확인 |
| 테스트 | 신규 서비스/훅/페이지 Vitest+MSW 테스트, `--pool=threads` 실행 기준 통과 | `npm test -- --pool=threads` |
| 계약 동기화 | 타입이 `admin_chunking_router.py` 스키마와 1:1 일치 | api-contract-sync 체크리스트 |
| 일관성 | 페이지 구조·스타일이 `AdminLlmModelsPage`와 동일 패턴 | 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR 전체 구현 + 화면에서 프로파일 생성→요약 LLM 지정→수정→기본 지정→삭제 플로우 동작
- [ ] Vitest 테스트 선행 작성(Red→Green) 및 통과
- [ ] adminNav 테스트 갱신 통과
- [ ] Gap 분석(Check) ≥ 90%

### 4.2 Quality Criteria

- [ ] 신규 파일 lint/型 에러 0
- [ ] 빌드 성공
- [ ] 기존 테스트 회귀 없음 (사전 실패 8건은 기존 이슈 — 신규 회귀로 오인 금지)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| PUT 전체 교체 방식이라 수정 폼이 일부 필드를 누락하면 데이터 소실 | High | Medium | 수정 폼은 GET 상세로 전체 프리필 후 전체 바디 전송, 누락 필드 없는지 테스트로 고정 |
| 정규식 편집 UX 난이도 (잘못된 패턴 저장) | Medium | Medium | 서버 422 검증 메시지 그대로 표시 + kb-custom-chunking에서 검증된 편집 UI 패턴 재사용 |
| jsdom 폼 제약 검증이 submit 차단 (min/required) | Low | High | 커스텀 인라인 검증 폼은 `noValidate` + 음수 입력은 fireEvent (프로젝트 선례) |
| 요약 LLM 드롭다운의 모델 목록 API 의존 | Low | Low | 기존 `llmModelService` 재사용, 로딩/빈 목록 상태 처리 |
| 프로파일 삭제가 KB에 참조 중일 수 있음 | Medium | Medium | 백엔드가 default 폴백 처리함(`chunking_resolver._load_profile`) — UI 확인 다이얼로그에 "참조 KB는 기본 프로파일로 폴백" 안내 문구 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

기존 프로젝트에 편입 — 신규 레벨 선택 없음. idt_front의 기존 구조(React 19 + TS + Zustand + TanStack Query)를 그대로 따른다.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 페이지 구조 | 신규 패턴 / AdminLlmModelsPage 패턴 | `pages/AdminChunkingProfilesPage/index.tsx` 단일 진입 + 서비스 분리 | 동일 성격 admin CRUD 페이지의 검증된 선례 |
| 서버 상태 | 신규 스토어 / TanStack Query | TanStack Query (list invalidate 방식) | 프로젝트 표준 |
| 요약 LLM 목록 | 신규 API / 기존 재사용 | 기존 `llmModelService`의 활성 모델 목록 재사용 | 중복 제거 |
| 정규식 편집기 | 신규 / kb-custom-chunking UI 준용 | 준용(행 단위 리스트 편집) | UX 일관성, 구현 리스크 절감 |

### 6.3 Clean Architecture Approach

프론트 전용 작업 — idt 백엔드 레이어 규칙 영향 없음.
`constants/api.ts` → `types/chunkingProfile.ts` → `services/chunkingProfileService.ts` → `hooks/` → `pages/AdminChunkingProfilesPage/` 순 배선.

---

## 7. Convention Prerequisites

- [x] `idt_front/CLAUDE.md` 컨벤션 존재 — 준수
- [x] API 상수는 `constants/api.ts` 집중 관리
- [x] 테스트: MSW는 파일별 `server.listen` 3종 훅 직접 선언 (전역 setup 없음)
- [x] `npm install` 필요 시 `--legacy-peer-deps`

신규 환경변수 없음.

---

## 8. Next Steps

1. [ ] `/pdca design chunking-profile-admin-ui` — 화면 레이아웃·컴포넌트 분해·타입 정의·MSW 핸들러 설계
2. [ ] 구현 (TDD: 서비스 → 훅 → 페이지)
3. [ ] `/pdca analyze chunking-profile-admin-ui`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-15 | Initial draft — 백엔드 API 기존재 확인, 프론트 전용 스코프 확정 | 배상규 |
