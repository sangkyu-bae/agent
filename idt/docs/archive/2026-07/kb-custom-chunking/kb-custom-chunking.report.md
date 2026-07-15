# kb-custom-chunking Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Author**: 배상규
> **Completion Date**: 2026-07-15
> **PDCA Cycle**: #1 (Plan 2026-07-14 → Report 2026-07-15)

---

## 1. Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | kb-custom-chunking — KB 단위 커스텀 청킹(전략·사이즈·오버랩·경계 정규식) |
| Start Date | 2026-07-14 (Plan) |
| End Date | 2026-07-15 (Check 98% + Gap 보강) |
| Duration | 2일 (Plan→Design→Do→Check→Act 단일 사이클) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Design Match Rate: 98% (Check 96% → 보강)   │
├─────────────────────────────────────────────┤
│  ✅ FR 완료:        10 / 10 items            │
│  ✅ 설계 결정 구현:  D1~D12 (12/12)           │
│  ✅ 검증 규칙 구현:  V-01~V-07 (7/7)          │
│  ⏳ 이월:           E2E 수동 검증 (환경 의존)  │
└─────────────────────────────────────────────┘
```

- 신규/확장 테스트: 백엔드 154건(도메인 40+정책 3+유스케이스 11+resolver 5+라우터 6+repo 7 신규, 나머지 기존 유지) 통과, 프론트 21건 통과, `tsc --noEmit` 무오류
- 신규 파일: 백엔드 3(도메인 모듈·마이그레이션·repo 테스트), 프론트 4(폼 유틸·컴포넌트 3) + 테스트 3

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 청킹 전략 5종이 구현돼 있음에도 사용자는 조항 ON/OFF 토글만 제어 가능했고, 비조항 KB는 parent_child 2000/500/50 하드코딩에 고정 — 문서 특성별 청킹 조정 불가 |
| **Solution** | 독립 opt-in(`use_custom_chunking` + JSON config)으로 전략 5종·사이즈/오버랩·경계 정규식을 KB 단위 설정. 신규 청킹 엔진 없이 기존 factory kwargs 통로만 개방, 조항/legacy 경로 무변경 보존 |
| **Function/UX Effect** | KB 생성 모달 radio 3택(기본/조항/커스텀) + 전략별 동적 폼 + 정규식 규칙 편집기, 상세 페이지 설정 카드 + PATCH 수정(신규 업로드부터 적용 안내 고정). 검증 실패는 필드·패턴 원문 포함 422로 즉시 피드백 |
| **Core Value** | 문서 유형별 검색 품질 최적화를 관리자 개입 없이 사용자 셀프서비스로 수행 — 이전에 KB update 경로 자체가 없던 플랫폼에 설정 수정 API가 처음 도입됨 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [kb-custom-chunking.plan.md](../01-plan/features/kb-custom-chunking.plan.md) | ✅ Finalized |
| Design | [kb-custom-chunking.design.md](../02-design/features/kb-custom-chunking.design.md) | ✅ Finalized (D1~D12, V-01~V-07) |
| Check | [kb-custom-chunking.analysis.md](../03-analysis/kb-custom-chunking.analysis.md) | ✅ Complete (96%→98%) |
| Act | 본 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements (Plan FR-01~FR-10)

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 독립 opt-in 필드 신설 (`use_custom_chunking`+JSON), 기존 경로 무변경 | ✅ Complete | V048 마이그레이션 |
| FR-02 | 전략 5종 선택 (`boundary_pattern`→clause_aware 재사용) | ✅ Complete | 신규 전략 구현 0 |
| FR-03 | 파라미터 범위 검증 (100~4000 / 0~500 / 100~8000 / 50~2000) | ✅ Complete | 기존 정책 상수 재사용 |
| FR-04 | 경계 정규식 정의 + 컴파일 검증 + 실패 패턴 원문 응답 | ✅ Complete | ≤200자/≤50개 ReDoS 완화 |
| FR-05 | 조항↔커스텀 상호배타 (422 + 프론트 radio 원천 차단) | ✅ Complete | 백·프론트 이중 |
| FR-06 | resolver 해석 + display 이력 기록 | ✅ Complete | `custom: true` 마킹 |
| FR-07 | 손상 config → legacy 폴백 + warning (업로드 항상 성공) | ✅ Complete | |
| FR-08 | 신규 업로드부터 적용 + UI 안내 문구 | ✅ Complete | 재인덱싱 없음 |
| FR-09 | 생성/수정/상세 UI (전략 폼 + 규칙 편집 + 인라인 정규식 에러) | ✅ Complete | |
| FR-10 | 프론트-백엔드 타입 계약 동기화 | ✅ Complete | types/service/hook/constants |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 하위 호환 | 양쪽 토글 OFF·조항 KB 동작 무변경 | 기존 테스트 전건 통과 (resolver 기존 7건 포함) | ✅ |
| ReDoS 완화 | 패턴 길이/개수 상한 + 컴파일 검증 | ≤200자, ≤50개, `re.compile` (기존 정책 재사용) | ✅ |
| 아키텍처 | Thin DDD 레이어 준수 | 검증=domain, 해석=application, 전략 생성=infra factory | ✅ |
| TDD | 테스트 선행 | 전 모듈 테스트 우선 작성 (Red→Green) | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 마이그레이션 | `db/migration/V048__alter_knowledge_base_add_custom_chunking.sql` | ✅ (**DB 적용은 배포 시**) |
| 도메인 모듈 | `src/domain/knowledge_base/custom_chunking.py` (config+policy+factory 매핑) | ✅ |
| 설정 수정 API | `PATCH /api/v1/knowledge-bases/{kb_id}/chunking` (router+use_case+repo `update_chunking`) | ✅ |
| resolver 분기 | `src/application/knowledge_base/chunking_resolver.py::_resolve_custom` | ✅ |
| 프론트 UI | `ChunkingModeSelector` / `CustomChunkingFields` / `KbChunkingSettingsCard` + 모달·상세 통합 | ✅ |
| 프론트 계약 | `types/knowledgeBase.ts`, `constants/api.ts`, service, hook | ✅ |
| 테스트 | 백엔드 6개 파일(신규 2·확장 4) + 프론트 3개 파일 | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority |
|------|--------|----------|
| E2E 수동 검증 3종 (커스텀 청킹 실측 / 회귀 / 기존 문서 불변) | Qdrant/ES 기동 필요 — 프로젝트 공통 E2E 이월 체크리스트에 합류 ([[kb-pipeline-e2e-pending]] 계열) | High (배포 전) |
| V048 DB 적용 | 배포/로컬 기동 시 Flyway 실행 | High (배포 전) |
| 커스텀 설정 기반 청킹 프리뷰 | Plan Out of Scope — `/api/v1/preview` 재사용 후속 후보 | Medium |
| 재인덱싱 (`kb-rechunk-reindex`) | Plan Out of Scope | Low |

### 4.2 Cancelled/On Hold

없음.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | 비고 |
|--------|--------|-------|------|
| Design Match Rate | ≥ 90% | **98%** | Check 96% → 🔴 repo 테스트 보강으로 상승 |
| 백엔드 테스트 | 신규 전건 통과 | 통과 | 산발 setup ERROR는 알려진 WinError 10014 환경 이슈 (assertion 실패 0) |
| 프론트 테스트 | 신규 전건 통과 | 21/21 | `--pool=threads --no-file-parallelism` |
| 타입 체크 | 무오류 | `tsc --noEmit` 통과 | |

### 5.2 Check에서 발견된 Gap과 처리

| Gap | 심각도 | 처리 |
|------|--------|------|
| repository JSON 왕복/화이트리스트 테스트 부재 | 🔴 | **즉시 보강** — `tests/infrastructure/knowledge_base/test_repository.py` 7건 신설 |
| 403 문구 (설계 한글 vs 구현 영문 관례) | 🟡 | 잔존 — 기존 라우터 영문 `PermissionError` 관례와 일관, 설계 개정 권장으로 종결 |
| policy 테스트 파일명 상이 | 🟡 | 잔존(내용 충족) — 문서상 기록으로 종결 |
| onChange 검증 / 폼 유틸 분리 / 상수명 관례 | 🟢 | 정당한 편차 — 조치 불필요 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **재사용 우선 설계가 구현 비용을 크게 낮춤** — 청킹 전략 5종·정규식 검증 정책·resolver 구조가 이미 있어, 이번 기능은 사실상 "설정 통로 개방"으로 축소됨 (신규 청킹 엔진 0줄)
- **독립 opt-in 원칙** (이전 피드백 반영) — 조항 경로를 교차검증 기준선으로 보존해 회귀 테스트가 그대로 안전망 역할
- **Plan 단계 사용자 질의 4건**(범위/단위/기존 문서/필드 설계)이 설계 방향을 조기 확정 — 이후 단계에서 방향 재논의 0회

### 6.2 What Needs Improvement (Problem)

- 설계 단계에서 **KB update 경로 부재를 조사 후에야 발견** — Plan 시점의 코드 조사 깊이가 UI("수정 화면")와 백엔드 현실의 간극을 놓침
- 설계 문서의 UI 세부(검증 시점 blur, 상수명)가 기존 프론트 관례와 어긋나 사소한 편차 발생 — 설계 시 관례 파일 확인 필요
- Windows 테스트 환경 악화: 단일 파일 실행에서도 setup ERROR 산발(WinError 10014), vitest는 `--no-file-parallelism`까지 필요

### 6.3 What to Try Next (Try)

- 신규 엔드포인트 설계 시 **대상 리소스의 CRUD 커버리지 표**를 먼저 그려 부재 경로를 설계 입력으로 명시
- 에러 메시지 문구는 설계에 "표시 문구"가 아닌 "표시 규칙(서버 detail 그대로/폴백)"으로 기술해 문구 편차 자체를 제거

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement |
|-------|---------|-------------|
| Design | UI 문구를 리터럴로 명세 | 표시 규칙(서버 detail 위임) 중심으로 명세 |
| Check | gap-detector가 Write 불가로 문서 저장 실패 | 분석 문서 저장은 메인 세션 책임으로 고정 (이번 사이클 방식 유지) |
| 테스트 | 산발 환경 에러와 회귀를 수동 판별 | "N회 실행 합집합 + assertion 0건" 판별법을 표준화 (메모리 기록 완료) |

---

## 8. Next Steps

### 8.1 Immediate (배포 전 필수)

- [ ] V048 마이그레이션 적용
- [ ] E2E 수동 검증 3종 (Qdrant/ES 기동 시 — 공통 이월 체크리스트와 일괄)
- [ ] 브랜치/커밋/PR (git-workflow)

### 8.2 Next PDCA Cycle 후보

| Item | Priority |
|------|----------|
| kb-chunking-preview (커스텀 설정 기반 업로드 전 미리보기 — preview API 재사용) | Medium |
| kb-rechunk-reindex (설정 변경 시 기존 문서 재청킹) | Low |
| 403 문구 정합 (설계 개정 or 프론트 한글 문구) | Low |

---

## 9. Changelog

### v1.0.0 (2026-07-15)

**Added:**
- KB 커스텀 청킹: 전략 5종(full_token/parent_child/semantic/section_aware/boundary_pattern) + chunk_size/overlap/parent_size/min_size + 경계 정규식 규칙을 KB 단위 설정
- `PATCH /api/v1/knowledge-bases/{kb_id}/chunking` — KB 최초의 설정 수정 API (owner/ADMIN, 전체 교체)
- KB 생성 모달 청킹 radio 3택, 상세 페이지 청킹 설정 카드
- `knowledge_base` 테이블 `use_custom_chunking`/`custom_chunking_config` 컬럼 (V048)

**Changed:**
- `ChunkingSettingsResolver` — custom→clause→legacy 해석 순서, 손상 config legacy 폴백
- 업로드 쿼리 파라미터 무시 경고 문구 clause→"KB chunking settings" 일반화

**Fixed:**
- 해당 없음 (신규 기능)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-15 | 완료 보고서 작성 (Match 98%) | 배상규 |
