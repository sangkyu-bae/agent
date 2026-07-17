# chunking-profile-admin-ui Gap Analysis

> **Summary**: Design D1~D10·타입 계약·엔드포인트 배선·UI·테스트 계획 대비 구현 검증 — Match Rate **95.0%**
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규 (gap-detector)
> **Date**: 2026-07-17
> **Design**: `docs/02-design/features/chunking-profile-admin-ui.design.md`
> **Plan**: `docs/01-plan/features/chunking-profile-admin-ui.plan.md`

---

## 1. Match Rate

| 분류 | 항목 수 | 완전일치 | 부분일치 |
|------|:---:|:---:|:---:|
| Design Decisions D1~D10 | 10 | 10 | 0 |
| §4 타입 ↔ 백엔드 스키마 | 5 | 5 | 0 |
| §5 엔드포인트 배선 (+상세 미사용 확인) | 6 | 6 | 0 |
| §6 UI 구성 | 3 | 3 | 0 |
| §8 테스트 계획 | 5 | 3 | 2 |
| Plan FR-01~FR-10 | 10 | 10 | 0 |
| §10 파일 산출물 존재 | 1 | 1 | 0 |
| **합계** | **40** | **38** | **2 (×0.5=1.0)** |

**Match Rate = (38 + 1.0) / 40 = 95.0%** — 기준(90%) 충족. 부분일치 2건은 모두 구현이 아닌 **테스트/검증 커버리지** 항목.

---

## 2. Design Decisions 검증 (D1~D10)

| 항목 | 상태 | 근거 |
|------|:---:|------|
| D1 단일 페이지 + 폼 모달, 규칙 편집기 분리 | ✅ | `AdminChunkingProfilesPage/index.tsx`, `BoundaryRulesEditor.tsx` |
| D2 전체 프리필 → 전체 PUT 바디 (GET 상세 미사용) | ✅ | `index.tsx` fromProfile/submit 전 필드 — P3 테스트 회귀 가드 |
| D3 useLlmModels(true) 통일 + 비활성 참조 옵션 유지 | ✅ | `index.tsx:103-112, 249-258` |
| D4 "사용 안 함(요약 비활성)" + 용도 안내 문구 | ✅ | `index.tsx:248, 263-266` |
| D5 BoundaryRulesEditor 신규 + isValidRegex 재사용 | ✅ | `BoundaryRulesEditor.tsx:1,29` |
| D6 클라이언트 검증 3단계 (name/규칙·정규식/사이즈) | ✅ | `index.tsx:118-143` |
| D7 기본 지정 액션 버튼 + 폼 체크박스 병행 | ✅ | `index.tsx:492-500, 269-282` |
| D8 삭제 ConfirmDialog + 기본 폴백 안내 | ✅ | `index.tsx:545-560` ("KB"→"지식베이스" 표현만 다름, 의미 동일) |
| D9 chunkingProfiles 쿼리키 + all invalidate + 404 재동기화 | ✅ | `queryKeys.ts`, `useChunkingProfiles.ts` |
| D10 adminNav 'LLM 모델' 다음 배치 | ✅ | `adminNav.ts:37-47` |

## 3. 계약·배선·UI·FR — 전 항목 일치

- 타입 5종 ↔ `admin_chunking_router.py` 스키마 1:1 일치 (level은 프론트에서 유니온으로 강화)
- 엔드포인트 5종 배선 완료, GET 상세는 설계대로 미사용
- 테이블 6컬럼·폼 필드·상태 3분기(로딩/에러/빈목록) 설계 일치
- Plan FR-01~FR-10 전부 충족
- 설계 §3.2 산출물 13개 파일 누락 0건

## 4. 테스트 현황

자동 테스트 **19건** (service 5 + editor 5 + page 8 + adminNav 1) 전부 통과 (`--pool=threads`).
전체 스위트 625 passed / 8 failed — 실패는 기존 사전 실패와 동일(신규 회귀 0).

## 5. Gap 목록

| # | Gap | 심각도 | 조치 |
|---|-----|:---:|------|
| G1 | §8.3 중 **422 서버 detail 테스트 미작성** (409는 P8로 커버, 구현 자체는 지원) | Low | `index.test.tsx`에 422 케이스 추가 권장 |
| G2 | §8.5 **수동 E2E 미수행** (요약 LLM 지정 → section_summary_job 생성 확인) | Low | 백엔드(Qdrant/ES) 기동 시 KB E2E 공통 체크리스트로 이월 — kb-pipeline-e2e-pending과 합류 |
| G3 | D8 문구 리워딩("KB"→"지식베이스") | None | 의미 동일 — 조치 불요 |

## 6. 설계 초과 구현 (긍정)

- 미등록 모델 id 참조 시 **"(등록 정보 없음)" 옵션 유지** (`index.tsx:259-261`) — D3의 비활성 케이스를 넘어 미상 id까지 값 소실 방어.

## 7. 결론

구현 관점 실질 100%, gap은 테스트 커버리지 2건(Low)뿐. **Match Rate 95% ≥ 90% → Report 단계 진행 가능.**

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-17 | gap-detector 분석 결과 정리 (95.0%) | 배상규 |
