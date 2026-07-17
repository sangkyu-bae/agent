# chunking-profile-admin-ui Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt_front 프론트 전용 — idt 백엔드 변경 0건)
> **Author**: 배상규
> **Completion Date**: 2026-07-17
> **PDCA Cycle**: #1 (Plan 2026-07-15 → Report 2026-07-17, 반복 0회)

---

## 1. Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | chunking-profile-admin-ui — 청킹 프로파일(조항 경계 규칙·섹션 요약 LLM) 관리자 화면 |
| Start Date | 2026-07-15 (Plan) |
| End Date | 2026-07-17 (Check 95%) |
| Duration | 3일 (Plan→Design→Do→Check 단일 사이클, iterate 불필요) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Design Match Rate: 95% (iterate 0회)        │
├─────────────────────────────────────────────┤
│  ✅ FR 완료:        10 / 10 items            │
│  ✅ 설계 결정 구현:  D1~D10 (10/10)           │
│  ✅ 타입-계약 동기화: 백엔드 스키마 5종 1:1     │
│  ⏳ 이월:           422 테스트 1건(Low),      │
│                    수동 E2E(환경 의존)        │
└─────────────────────────────────────────────┘
```

- 신규 테스트 19건 통과 (service 5 + 규칙 편집기 5 + 페이지 8 + adminNav 1, `--pool=threads`)
- 전체 스위트 625 passed / 8 failed — 실패 전건 기존 사전 실패, **신규 회귀 0**
- 신규 파일 7 + 변경 파일 5 (총 12 산출물, 설계 대비 누락 0)
- ESLint 0건, 신규 파일 타입 에러 0건

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 문서 조항 단위 요약·키워드 추출에 쓸 LLM(`summary_llm_model_id`)과 조항 청킹 경계 규칙은 청킹 프로파일에 저장되는데 관리 화면이 없었다. 백엔드 admin CRUD API는 완성돼 있었으나 프론트 호출처 0곳 — Swagger/DB 직접 수정으로만 운영 가능한 반쪽 기능 상태 |
| **Solution** | `/admin/chunking-profiles` 페이지 신설, 기존 API 5종을 그대로 배선(계약 변경 0). AdminLlmModelsPage 검증 패턴 복제로 목록·폼 모달·기본 지정·삭제를 구현하고, PUT 전체 교체의 데이터 소실 리스크는 전체 프리필 + 회귀 테스트로 차단 |
| **Function/UX Effect** | 관리자가 화면에서 정규식 경계 규칙을 행 단위로 편집(실시간 컴파일 검증)하고, admin/llm-models의 활성 모델 드롭다운에서 요약 LLM을 지정·해제. 비활성/미등록 모델 참조도 "(비활성)"·"(등록 정보 없음)" 옵션으로 값 소실 방어. 삭제 시 "참조 KB는 기본 프로파일로 폴백" 고지 |
| **Core Value** | 조항 청킹→섹션 요약→라우팅 검색 파이프라인의 마지막 수동 운영 구간(요약 LLM 배정)을 셀프서비스화 — API만 있고 UI가 없던 기능을 완성해 운영자가 DB에 손대지 않고 요약 파이프라인을 제어 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [chunking-profile-admin-ui.plan.md](../01-plan/features/chunking-profile-admin-ui.plan.md) | ✅ Finalized (FR-01~10) |
| Design | [chunking-profile-admin-ui.design.md](../02-design/features/chunking-profile-admin-ui.design.md) | ✅ Finalized (D1~D10) |
| Check | [chunking-profile-admin-ui.analysis.md](../03-analysis/chunking-profile-admin-ui.analysis.md) | ✅ Complete (95%) |
| Act | 본 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements (Plan FR-01~FR-10)

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 활성 프로파일 목록 조회 | ✅ Complete | 로딩/에러/빈목록 3분기 |
| FR-02 | 프로파일 생성 (409 detail 표시) | ✅ Complete | P8 테스트 |
| FR-03 | 전체 필드 수정 (전체 프리필) | ✅ Complete | D2 — P3 회귀 가드 테스트 |
| FR-04 | summary_llm_model_id 드롭다운/사용 안 함 | ✅ Complete | 활성 모델 + 비활성 참조 유지(D3) |
| FR-05 | 요약 LLM 용도 안내 문구 | ✅ Complete | "미지정 시 요약 미실행" 고정 표기 |
| FR-06 | 기본 프로파일 지정 | ✅ Complete | 전용 액션 버튼 + 폼 체크박스 병행(D7) |
| FR-07 | 삭제 + 확인 다이얼로그 | ✅ Complete | 기본 폴백 안내(D8) |
| FR-08 | boundary_rules 행 편집기 | ✅ Complete | BoundaryRulesEditor, isValidRegex 재사용(D5) |
| FR-09 | admin 사이드바 메뉴 노출 | ✅ Complete | 'LLM 모델' 다음 배치(D10) |
| FR-10 | API 실패 detail 표면화 | ✅ Complete | getErrorMessage 패턴 (422 테스트만 이월) |

### 3.2 Deliverables (신규 7 + 변경 5)

| 파일 | 구분 | 내용 |
|------|:---:|------|
| `types/chunkingProfile.ts` | 신규 | 백엔드 스키마 5종 1:1 타입 |
| `services/chunkingProfileService.ts` (+test 5건) | 신규 | list/create/update/setDefault/remove |
| `hooks/useChunkingProfiles.ts` | 신규 | 쿼리 1 + 뮤테이션 4, 404 재동기화(D9) |
| `pages/AdminChunkingProfilesPage/index.tsx` (+test 8건) | 신규 | 목록·폼 모달·삭제 확인 |
| `pages/AdminChunkingProfilesPage/BoundaryRulesEditor.tsx` (+test 5건) | 신규 | 정규식 규칙 행 편집기 |
| `constants/api.ts` | 변경 | ADMIN_CHUNKING_* 상수 3종 |
| `lib/queryKeys.ts` | 변경 | chunkingProfiles 키 그룹 |
| `constants/adminNav.ts` (+test 갱신) | 변경 | "청킹 프로파일" 메뉴 (8번째) |
| `App.tsx` | 변경 | `/admin/chunking-profiles` 라우트 |

---

## 4. Carried Over (이월)

| # | 항목 | 심각도 | 계획 |
|---|------|:---:|------|
| G1 | 422 서버 detail 표시 테스트 (구현은 완료, 테스트만 부재) | Low | 후속 테스트 보강 시 1케이스 추가 |
| G2 | 수동 E2E — 프로파일에 요약 LLM 지정 → 조항 청킹 KB 업로드 → `section_summary_job.llm_model_id` 확인 | Low | Qdrant/ES 기동 시 KB 파이프라인 공통 E2E 체크리스트(kb-pipeline-e2e-pending)와 일괄 수행 |
| — | `npm run build`(tsc -b) 실패는 워킹트리 사전 이슈(ChatPage·vite.config 등) — 본 기능 파일 관련 에러 0건 확인 | 참고 | 별도 정리 대상 |

### 후속 후보 (Out of Scope 재확인)

- `kb-profile-selector`: KB 생성/수정 폼에서 프로파일 선택 드롭다운 (`/api/v1/chunking/profiles` 프리필 배선)
- 요약 잡 모니터링/재시도 UI, 정규식 프리뷰(테스트 문자열 매칭 확인) UI

---

## 5. Lessons Learned

| 항목 | 내용 |
|------|------|
| PUT 전체 교체 API의 프론트 대응 | 부분 수정 API가 없을 때는 "목록 응답 전체 프리필 → 전체 바디 전송"을 설계 결정(D2)으로 고정하고, "이름만 바꿔도 나머지 보존" 테스트를 회귀 가드로 두는 패턴이 유효 |
| 참조 무결성의 UI 방어 | 드롭다운 값이 다른 리소스(LLM 모델)를 참조할 때, 비활성/삭제된 참조를 옵션에서 숨기면 저장 시 조용히 소실 — "(비활성)"/"(등록 정보 없음)" 옵션 유지가 안전 기본값 |
| userEvent 특수문자 | `[`는 userEvent.type의 키 디스크립터라 정규식 입력 테스트는 fireEvent.change 필요 (jsdom 선례에 추가) |
| 검증된 페이지 패턴 복제 | AdminLlmModelsPage 패턴(모달 1회 초기화 플래그, getErrorMessage, 3분기 상태) 재사용으로 설계~구현 3일 내 95% 달성 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-17 | 완료 보고서 (Match Rate 95%, iterate 0회) | 배상규 |
