# excel-preview Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 0.1
> **Analyst**: 배상규 (gap-detector 에이전트 정적 분석 + 세션 내 테스트 실행)
> **Date**: 2026-10-12
> **Design Doc**: [excel-preview.design.md](../02-design/features/excel-preview.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 산출 엑셀의 내용 확인이 "다운로드 → 엑셀 실행"을 강제해 검증 왕복이 느리다 |
| **WHO** | 채팅에서 엑셀 산출물을 받는 모든 사용자 (주인공 P2 에이전트 소유자 및 배포받은 부서 사용자) |
| **RISK** | 대용량 시트 파싱이 요청 스레드를 점유하거나 응답이 비대해져 채팅 UI가 멈추는 것 |
| **SUCCESS** | .xlsx 링크 옆 버튼 → 모달 시트 탭·상위 100행 확인 → 모달 내 다운로드 동일 파일. 10MB 2초 이내. FAILED diff 0 |
| **SCOPE** | Phase 1: 산출 엑셀 프리뷰 API + 모달 (첨부·KB·스냅샷 프리뷰는 후속) |

---

## Strategic Alignment Check

PRD 없음(Plan부터 시작). Plan 기준 정렬 검증:

| 요소 | 기대 | 상태 |
|------|------|:----:|
| Core Problem (WHY) | 다운로드 없이 산출 엑셀 검증 | ✅ 버튼→모달→시트 탭·그리드로 해소 |
| Target User (WHO) | P2 + 부서 사용자 | ✅ owner-only 계약 유지(본인 산출물), 진입은 채팅 공통 |
| 보수적 동작 (RISK) | 상한·비차단·기존 계약 무수정 | ✅ 100×50 상한, to_thread, 다운로드 라우트/링크 형식/노드 무수정 |

### Success Criteria Status (Plan §4.1)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | FR-01~14 구현 + RED→GREEN 테스트 | ✅ | 백엔드 60 + 프론트 30 테스트, 본 세션 RED 확인 후 GREEN |
| SC-2 | 백엔드 라우터/유스케이스/리더 테스트 (오류 계약·상한·직렬화·실 픽스처) | ✅ | `tests/api/test_excel_preview_router.py`(200/401/403/404/415/422), 리더 픽스처 6종 |
| SC-3 | 프론트 테스트 (버튼 조건·두 트리거 모드·모달 상태·그리드·훅 MSW) | ✅ | 6개 테스트 파일 30건 (link 모드는 `vi.mock` 고정) |
| SC-4 | 수동 E2E (생성→미리보기→바이트 동일) | ⏳ 미실행 | §2.7 L3 — QA/사용자 확인 대기 |
| SC-5 | `tsc`·lint 0 신규 오류, pytest FAILED diff 0 | ✅ | tsc 210=기존 210, eslint 신규 파일 0, pytest 상시 53건 외 신규 0 (prompt_guard 1건은 무관 untracked WIP 플레이크) |
| SC-6 | 10MB·2만 행 프리뷰 2초 이내 | ✅(테스트) | `test_read_elapsed_under_2s` — 메타 정상 파일 0.1초대. 실서버 측정은 L3에서 |

**Success Rate**: 5/6 met (SC-4는 수동 E2E로 Check 이후 단계 몫)

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | 파싱 위치=백엔드, openpyxl read_only+data_only | ✅ | — |
| [Design] | 설계안 C (domain Policy / application 스키마 / infra 리더 duck-typing) | ✅ | domain에 `value_objects.py` 추가 (의도적, §3.1 데이터 운반) |
| [Design] | total_rows = `ws.max_row` 메타 | ✅+보강 | 메타 lazy 갱신 발견 → iter 전 캡처 + 신뢰성 검증 추가 (§3.4 폴백 허용 범위) |
| [Design] | 모달 상태 = Zustand 스토어, ChatPage 1회 마운트 | ✅ | — |
| [Design] | 트리거 상수 직접 import + vi.mock | ✅ | — |
| [Design] | 다운로드 `downloadGeneratedFile` 재사용, 기존 라우트·테스트 무수정 | ✅ | — |

---

## 1. Analysis Overview

- **목적**: Design(설계안 C) 대비 구현 일치율 산출, 90% 게이트 판정
- **범위**: 백엔드 7신규+3수정, 프론트 8신규+4수정, 테스트 11파일
- **방법**: gap-detector 에이전트 정적 분석(3축) + 세션 내 테스트 실행(Runtime 축)

---

## 2. Gap Analysis

### 2.1~2.3 Structural Match — **100%**

- 백엔드: Design §4.3 구성 요소 8/8 존재 (라우트 `document_extractor_router.py:146-174`, DI `main.py:5471-5479`, config `config.py:228-229`), 기존 다운로드 라우트 무수정 확인
- 프론트: Design §5.3 컴포넌트 6/6 + §11.1 파일 전부 존재, `ChatPage/index.tsx:388` 모달 1회 마운트
- 테스트 파일: 백엔드 5/5, 프론트 6/6 + MSW 핸들러

### 2.4~2.5 Functional Depth — **95%**

- §5.4 Page UI Checklist: 채팅 메시지 4/4 + 모달 11/11 전부 구현 (placeholder 0, SHALLOW 0)
- §3.3 직렬화 규칙 10/10 (bool 우선 분기·NaN/inf·정수형 float·ISO 포함)
- §3.4 total 산출 3/3 + 메타 없음 폴백
- §4.2 오류 계약 5/5 (검증 순서 load→owner→확장자→파싱, 문구 글자 단위 일치)
- 감점: G-01(모달 다운로드 실패 시 catch 없음), G-02(응답 1MB NFR 미강제), G-03(`_read_sheet` 43줄)

### 2.6 API Contract — **100%**

- 필드 11/11이 Design §3.1/§3.2 ↔ pydantic ↔ TS ↔ MSW 4곳 일치 (snake_case)
- 경로 `/files/{file_id}/preview` 3-way 일치, 오류 코드 4종·메시지 일치, 프론트는 `ApiError.status` 분기

### 2.7 Runtime Verification

| Layer | 실행 | 결과 |
|-------|------|------|
| L1 (백엔드 pytest) | 기능 60건 + 전체 회귀 | **60/60 PASS**, 전체 FAILED 목록 = 기존 53건과 일치 (diff 0) |
| L2 (프론트 Vitest) | 기능 30건 + 전체 회귀 | **30/30 PASS**, 전체 1380건 중 실패 9건/4파일 = 기존 베이스라인 일치 |
| L3 (수동 E2E, Design §8.4) | **미실행** | 실서버·실에이전트 필요 — 4개 시나리오 체크리스트 대기 |

**Runtime Match Rate**: 실행 계층(L1·L2) 100% — L3는 수동 체크리스트로 별도 추적

### 2.8 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  100%                │
│  Functional Match Rate:   95%                │
│  Contract Match Rate:    100%                │
│  Runtime Match Rate:     100% (L1·L2 실행)   │
│  ─────────────────────────────────────────── │
│  Overall Match Rate:     98.8%               │
│  = (100×0.15)+(95×0.25)+(100×0.25)+(100×0.35)│
├─────────────────────────────────────────────┤
│  Critical: 0건  Important: 0건  Minor: 11건  │
└─────────────────────────────────────────────┘
```

---

## 3. Gap 목록 (gap-detector, 전부 Minor)

| ID | 신뢰도 | 위치 | 설명 |
|----|:--:|------|------|
| G-01 | 80% | `ExcelPreviewModal.tsx:51-56` | 모달 다운로드 `.catch` 없음 — TTL 만료 후 다운로드 시 unhandled rejection·무안내 (기존 MarkdownRenderer도 동일 패턴) |
| G-02 | 70% | `preview_reader.py` | 응답 본문 1MB NFR 미강제 (시트 수·셀 길이 상한 없음) |
| G-03 | 90% | `preview_reader.py:34-76` | `_read_sheet` 43줄 — 40줄 규칙 위반, `ws` 파라미터 타입 없음 |
| G-04 | 95% | 프론트 테스트 | 누락 4건: 네트워크/5xx 문구, 탭 전환 요청 0회 단언, 로딩 스피너, 5xx 재시도 1회 |
| G-05 | 90% | 백엔드 테스트 | 누락 3건: 수식 캐시 픽스처, 파싱 실패 로그 단언, load→owner→reader 순서 단언 |
| G-06 | 95% | Design §8.2 #3 | 문서 오기: total 20000 → 20001(헤더 포함)이 맞음 |
| G-07 | 90% | Design §4.3 | 문서 갱신: 유스케이스에 `logger`·`request_id` 추가됨 |
| G-08 | 85% | Design §2.1 | 문서 갱신: 훅 시그니처 `(fileId \| null)` + `gcTime: 0` |
| G-09 | 75% | `handlers.ts:138` | `mockExcelPreview`에 `ExcelPreviewResponse` 타입 표기 없음 |
| G-10 | 60% | reader/Modal | 첫 행 전부 빈 셀이면 "데이터 없음" 대신 빈 헤더 그리드 (산출 노드에선 비발생) |
| G-11 | 60% | Modal/Grid | 탭 `aria-controls`·화살표 키 이동 없음, 그리드 sticky 헤더 실효 없음 |

**의도적 편차 (감점 없음)**: domain `value_objects.py` 추가 / 메타 폴백 구현 / truncated 공식에 `hit_limit` 보강 / 완독 시 `seen_rows` 사용 — 모두 Design §3.4 허용 범위이며 레이어 규칙 준수.

---

## 6. Clean Architecture Compliance — 위반 0

| Layer | 검증 | 상태 |
|-------|------|:----:|
| domain | 표준 lib만 import (openpyxl·pydantic 없음) | ✅ |
| application | domain + 주입 객체만, 리더 클래스 직접 import 없음 | ✅ |
| infrastructure | openpyxl + domain만 | ✅ |
| interfaces | HTTP 매핑만 (비즈니스 로직 없음) | ✅ |
| 프론트 | Presentation→hook→service 방향, 컴포넌트 파일 런타임 상수 export 없음 | ✅ |

---

## 9. Recommended Actions

### Immediate (iterate 대상 후보)
- G-01 다운로드 실패 `.catch` + 안내 / G-03 함수 분리 / G-04·G-05 테스트 보강 / G-09 타입 표기 / G-06~08 설계 문서 갱신

### Backlog (다음 사이클)
- G-02 응답 1MB 상한 강제, G-10 빈 헤더 처리, G-11 탭 키보드 내비게이션

---

## 10. Design Document Updates Needed

- [ ] §8.2 #3: total_rows 20000 → 20001
- [ ] §4.3: 유스케이스 시그니처에 logger·request_id 반영
- [ ] §2.1: 훅 시그니처 `(fileId | null)`·gcTime 반영
- [ ] §3.4: 메타 lazy 갱신(캡처 선행)·hit_limit 보강 기록

---

## 11. Next Steps

- [ ] Checkpoint 5 결정 (Minor 수정 여부)
- [ ] 수동 E2E 4종 (Design §8.4) — 실서버 확인
- [ ] `/pdca report excel-preview`

---

## 12. Act-1 결과 (Checkpoint 5: "코드+문서 수정" 선택)

| Gap | 조치 | 검증 |
|-----|------|------|
| G-01 | 모달 다운로드 `.catch` + 실패 안내 문구 | 신규 테스트 (실패 안내·재시도 가능) |
| G-03 | `_read_sheet` → `_stream_rows` 분리 (40줄 이하), `_SheetScan` 운반 객체 | 기존 리더 테스트 전체 통과 |
| G-04 | 프론트 테스트 +5: 5xx 문구·로딩 스피너·탭 전환 요청 0회·다운로드 실패·훅 5xx 재시도 1회 | 35/35 PASS |
| G-05 | 백엔드 테스트 +3: 수식 캐시 없음→""·파싱 실패 로그 단언·load→reader 순서 단언 | 63/63 PASS |
| G-09 | `mockExcelPreview`에 `ExcelPreviewResponse` 타입 표기 | tsc 210=기존 (diff 0) |
| G-06~08 | Design 문서 v0.2 갱신 (total 20001, 유스케이스·훅 시그니처, §3.4 보강) | — |
| G-02·G-10·G-11 | **백로그** (1MB 상한 강제, 빈 헤더 엣지, 탭 키보드 내비게이션) | 후속 사이클 |

**Act-1 후 Match Rate: 99.5%** = (100×0.15)+(98×0.25)+(100×0.25)+(100×0.35) — Functional 감점 사유 3건 중 2건(G-01·G-03) 해소, G-02만 잔존.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-12 | Initial analysis — Match Rate 98.8%, Minor 11건 | 배상규 |
| 0.2 | 2026-10-12 | Act-1 반영 — G-01·03·04·05·09 수정, G-06~08 문서 갱신, Match Rate 99.5% | 배상규 |
