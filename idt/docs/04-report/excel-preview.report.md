# excel-preview Completion Report

> **Status**: Complete (수동 E2E 4종만 사용자 확인 대기)
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 0.1
> **Author**: 배상규
> **Completion Date**: 2026-10-12
> **PDCA Cycle**: #1 (iteration 1/5)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | excel-preview — 에이전트 산출 .xlsx 다운로드 전 모달 미리보기 |
| Start Date | 2026-10-12 (Plan CP1·2 확정) |
| End Date | 2026-10-12 |
| Duration | 1일 (단일 세션: Design → Do(모듈 3개) → Check → Act-1 → Report) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: FR 14/14 (100%)            │
├─────────────────────────────────────────────┤
│  Match Rate 99.5% (게이트 90% 통과)          │
│  신규 테스트 98건 (백엔드 63 + 프론트 35)    │
│  회귀: pytest·vitest·tsc·eslint 전부 diff 0  │
│  ⏳ 수동 E2E 4종 — 실서버 확인 대기          │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 산출 .xlsx가 링크로만 와서 내용 확인에 "다운로드 → 엑셀 실행" 왕복이 강제됐다 |
| **Solution** | 프리뷰 API(`GET /files/{id}/preview`, openpyxl read_only 상위 100×50 문자열 JSON) + 링크 옆 "미리보기" 버튼 → 시트 탭 모달. 모달 안에서 기존 다운로드 재사용 |
| **Function/UX Effect** | 다운로드 없이 전 시트 구성·헤더·상위 100행 즉시 확인. 잘림 안내("전체 N행×M열 중 …"), 만료·권한·손상 사유를 모달 안에서 안내. 2만 행 파일 파싱 0.1초대(상한 테스트 기준) |
| **Core Value** | P2(에이전트 소유자)·부서 사용자의 산출물 검증 왕복 제거. 기존 다운로드 계약·에이전트 노드 무수정(additive), 진입 방식(상수 1곳)·그리드 구현(컴포넌트 1개)이 교체 가능한 경계로 고정 |

---

## 1.4 Success Criteria Final Status

| # | Criteria (Plan §4.1) | Status | Evidence |
|---|---------------------|:------:|----------|
| SC-1 | FR-01~14 구현 + RED→GREEN 테스트 | ✅ Met | 세션 내 RED 확인 후 GREEN — 백엔드 63·프론트 35건 |
| SC-2 | 백엔드 라우터·유스케이스·리더 테스트 (오류 계약·상한·직렬화·실 픽스처) | ✅ Met | 200/401/403/404/415/422, 직렬화 테이블 20케이스, 픽스처 7종(다중 시트·빈 시트·2만 행·메타 없음·수식·손상·ragged) |
| SC-3 | 프론트 테스트 (버튼 조건·두 트리거 모드·모달 상태·그리드·훅 MSW) | ✅ Met | 6개 파일 35건 — link 모드는 `vi.mock` 고정, 오류 5종·다운로드 실패 포함 |
| SC-4 | 수동 E2E (생성→미리보기→바이트 동일) | ⏳ Pending | 실서버·실에이전트 필요 — §8.1 체크리스트 |
| SC-5 | tsc·lint 신규 0, pytest FAILED diff 0 | ✅ Met | tsc 210=기존, eslint 신규 파일 0, pytest 상시 53건 외 0 |
| SC-6 | 10MB·2만 행 프리뷰 2초 이내 | ✅ Met (테스트) | `test_read_elapsed_under_2s` — 실측 0.1초대. 실서버 측정은 SC-4와 함께 |

**Success Rate**: 5/6 Met (SC-4는 자동 검증 범위 밖 — 수동 체크리스트로 이관)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 파싱=백엔드 API (owner 검증·상한 서버 보장) | ✅ | 프론트 번들 증가 0, 후속 접점(첨부·KB) 스키마 재사용 가능 |
| [Plan] | openpyxl read_only + data_only | ✅ | 상한 조기 중단으로 2만 행 0.1초대. **발견**: dimensions 없는 파일은 load 시 전체 스캔 — 메타 캡처·폴백으로 방어 |
| [Design] | 설계안 C — domain 순수 규칙 / application 스키마 / infra duck-typing | ✅ | 레이어 위반 0 (gap-detector 확인), ReaderInterface 미도입으로 과도한 추상화 회피 |
| [Design] | 모달 상태 = Zustand 스토어, ChatPage 1회 마운트 | ✅ | react-markdown `memo` 리렌더 리스크 구조적 제거, 기존 MarkdownRenderer 테스트 무수정 |
| [Design] | 트리거 상수 직접 import + vi.mock 테스트 | ✅ | 'button'↔'link' 전환 = 상수 1곳, 두 모드 모두 테스트 고정 |
| [Design] | total_rows = max_row 메타 | ✅+보강 | 메타 lazy 갱신 발견 → iter 전 캡처 + `_resolve_total_rows` 신뢰성 검증 (Design v0.2 반영) |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [excel-preview.plan.md](../01-plan/features/excel-preview.plan.md) | ✅ v0.1 |
| Design | [excel-preview.design.md](../02-design/features/excel-preview.design.md) | ✅ v0.2 (Check 피드백 반영) |
| Check | [excel-preview.analysis.md](../03-analysis/excel-preview.analysis.md) | ✅ v0.2 (Act-1 반영) |
| Report | 본 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements — 14/14

| ID | Requirement | Status |
|----|-------------|--------|
| FR-01 | 프리뷰 라우트 + 다운로드 동일 검증 | ✅ |
| FR-02 | 전 시트 포함 응답 스키마 | ✅ |
| FR-03 | 상한 100×50 + truncated + config 키 | ✅ |
| FR-04 | 헤더/행 분리, 빈 시트 처리 | ✅ |
| FR-05 | 셀 문자열 통일 (domain Policy 테이블 테스트) | ✅ |
| FR-06 | 오류 계약 404/403/415/422 | ✅ |
| FR-07 | to_thread + read_only 비차단 | ✅ |
| FR-08 | .xlsx 링크 옆 미리보기 버튼 | ✅ |
| FR-09 | `EXCEL_PREVIEW_TRIGGER` 두 모드 + 테스트 | ✅ |
| FR-10 | 모달 열릴 때만 조회 (enabled) | ✅ |
| FR-11 | 모달 상태 5종 (로딩/404/403/415·422/빈 시트) + 다운로드 실패 안내(Act-1) | ✅ |
| FR-12 | `ExcelPreviewGrid` 교체 경계 | ✅ |
| FR-13 | `downloadGeneratedFile` 재사용 | ✅ |
| FR-14 | 엔드포인트 상수·타입 계약 동기화 | ✅ |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 2만 행 파싱 | 2초 이내 | 0.1초대 (메타 정상 파일) | ✅ |
| 이벤트 루프 비차단 | to_thread | 유스케이스 테스트로 고정 | ✅ |
| XSS | 텍스트 렌더만 | `<script>` 셀 테스트 | ✅ |
| 호환성 | 기존 FAILED diff 0 | pytest 53건·vitest 9건/4파일 = 기존과 일치 | ✅ |
| 접근성 | dialog·ESC·table 시맨틱 | common Modal + RTL 테스트 | ✅ (탭 화살표 키는 백로그 G-11) |
| 응답 1MB 이하 | 상한 강제 | **미강제** — 100×50 상한으로 사실상 충족, 강제는 백로그 G-02 | ⚠️ |

### 3.3 Deliverables

| Deliverable | Location |
|-------------|----------|
| 백엔드 (7신규/3수정) | `src/domain/excel_preview/`, `src/application/excel_preview/`, `src/infrastructure/excel/preview_reader.py`, 라우터·main.py·config.py |
| 프론트 (8신규/4수정) | `types/excelPreview.ts`, `services/excelPreviewService.ts`, `store/excelPreviewStore.ts`, `hooks/useExcelPreview.ts`, `components/chat/ExcelPreview{Grid,Modal}.tsx`, MarkdownRenderer·ChatPage·api.ts·queryKeys |
| 테스트 (11파일 98건) | 백엔드 5파일 63건, 프론트 6파일 35건 + MSW 핸들러 |
| 문서 | Plan v0.1 / Design v0.2 / Analysis v0.2 / Report |

---

## 4. Incomplete Items

### 4.1 Carried Over (백로그)

| Item | Reason | Priority |
|------|--------|----------|
| 수동 E2E 4종 (§8.1) | 실서버·실에이전트 필요 | High — 배포 전 1회 |
| G-02: 응답 1MB 상한 강제 (시트 수·셀 길이 상한) | NFR 명시였으나 100×50 상한으로 실질 충족, 강제 로직은 별도 | Medium |
| G-10: 첫 행 전부 빈 셀 → 빈 헤더 그리드 | 산출 노드 파일에서 비발생 | Low |
| G-11: 시트 탭 화살표 키 이동·aria-controls, 그리드 sticky 헤더 | 설계 필수 아님 | Low |
| 후속 사이클: 채팅 첨부·KB 업로드·분석 스냅샷 프리뷰 | Plan Out of Scope — 본 응답 스키마·모달 재사용 설계됨 | 후속 |

### 4.2 Cancelled — 없음

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final |
|--------|--------|-------|
| Match Rate (Structural/Functional/Contract/Runtime) | 90% | **99.5%** (100/98/100/100) |
| Critical·Important gap | 0 | 0 |
| 신규 테스트 | FR 전수 | 98건 전부 GREEN |
| 회귀 | diff 0 | pytest·vitest·tsc·eslint 모두 0 |
| 레이어 규칙 위반 | 0 | 0 (gap-detector 독립 확인) |

### 5.2 Resolved Issues (Act-1, Minor 11건 중 8건 처리)

| Issue | Resolution |
|-------|------------|
| G-01 모달 다운로드 실패 무안내 | `.catch` + 안내 문구 + 테스트 |
| G-03 `_read_sheet` 43줄 | `_stream_rows` 분리 |
| G-04·05 테스트 공백 7건 | 백엔드 +3, 프론트 +5 보강 |
| G-09 MSW mock 타입 미표기 | `ExcelPreviewResponse` 표기 |
| G-06~08 설계 문서 오기 | Design v0.2 갱신 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **설계 단계에서 미결 3건(모달 상태·total_rows·트리거 주입)을 명시적으로 Design에 넘기고 코드 조사로 확정** — Do 단계에서 설계 변경이 한 번도 없었다.
- **교체 경계 2개(트리거 상수, Grid 컴포넌트)를 테스트로 고정** — 'link' 모드 전환이 상수 1곳 + 이미 있는 테스트로 보증된다.
- **gap-detector 독립 검증** — 구현자 자신의 검증 맹점(테스트 공백 7건, 문서 오기 3건)을 제3자 시선으로 잡아냈다.

### 6.2 What Needs Improvement (Problem)

- **openpyxl의 실제 동작 2건(iter_rows None 패딩, dimensions 없는 파일의 load 전체 스캔)을 설계가 몰랐다** — 리더 테스트가 두 번 깨지고 나서야 발견. 외부 라이브러리의 성능 특성은 설계 단계 스파이크(소형 실험)로 먼저 확인할 것.
- **픽스처 생성 방식(write_only)이 프로덕션(pandas 일반 모드)과 메타 특성이 달랐다** — "테스트 픽스처는 프로덕션 생성 경로와 같은 특성을 갖는가"를 픽스처 설계 시 질문해야 한다.

### 6.3 What to Try Next (Try)

- 후속 프리뷰 접점(첨부·KB) 사이클에서 본 응답 스키마·모달 재사용이 실제로 "컴포넌트 교체 없이" 되는지 검증 — 경계 설계의 실효성 측정.
- 외부 라이브러리 의존 신규 모듈은 Design §2 작성 전에 10분 스파이크 스크립트를 먼저 돌리는 관행.

---

## 8. Next Steps

### 8.1 Immediate — 수동 E2E 체크리스트 (배포 전 1회)

- [ ] 엑셀 생성 에이전트로 .xlsx 산출 → 미리보기 → 전 시트 탭·데이터 일치 확인
- [ ] 모달 다운로드 vs 링크 다운로드 바이트 동일 (`fc /b` 비교)
- [ ] TTL(1h) 만료 후 미리보기 → "만료" 문구, 모달 열린 채 만료 후 다운로드 → 실패 안내(G-01)
- [ ] 10MB·5시트·2만 행 파일 응답 2초 이내, 채팅 UI 비차단

### 8.2 Next PDCA Cycle 후보

| Item | Priority |
|------|----------|
| 채팅 첨부 엑셀 프리뷰 (전송 전) — 스키마·모달 재사용 | Medium |
| KB 업로드 엑셀 프리뷰 (인제스트 전) | Medium |
| G-02 응답 상한 강제 + G-11 탭 키보드 내비게이션 | Low |

---

## 9. Changelog

### v0.1 (2026-10-12)

**Added:**
- `GET /api/v1/document-extractor/files/{file_id}/preview` — .xlsx 시트별 상위 100×50 프리뷰 JSON (owner-only, 404/403/415/422)
- `EXCEL_PREVIEW_MAX_ROWS/COLS` 환경변수 (기본 100/50)
- 채팅 .xlsx 산출 링크 옆 "미리보기" 버튼 + 시트 탭 모달 (`ExcelPreviewModal`/`ExcelPreviewGrid`)
- `EXCEL_PREVIEW_TRIGGER` 상수 — 'link' 모드 전환 지원

**Changed:**
- `MarkdownRenderer` a 컴포넌트 — .xlsx 분기 추가 (기존 링크 다운로드 동작 불변)
- `ChatPage` — 프리뷰 모달 1회 마운트

**Fixed:** (신규 기능이므로 해당 없음 — Act-1 수정은 본 사이클 내 처리)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-10-12 | Completion report — Match Rate 99.5%, FR 14/14, SC 5/6(+수동 E2E 대기) | 배상규 |
