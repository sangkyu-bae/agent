---
title: openpyxl read_only 리더 함정 — max_col 패딩·dimensions 없는 파일의 전체 스캔·lazy max_row
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/infrastructure/excel/preview_reader.py (_read_sheet: 메타 iter 전 캡처, max_col_arg=min(상한, 메타), _resolve_total_rows)
  - idt/src/application/excel_preview/preview_use_case.py (검증 순서 404→403→415→422, asyncio.to_thread)
  - idt/src/api/routes/document_extractor_router.py (GET /files/{file_id}/preview)
  - idt/src/config.py (excel_preview_max_rows=100, excel_preview_max_cols=50)
  - idt_front/src/types/excelPreview.ts (EXCEL_PREVIEW_TRIGGER 상수), idt_front/src/store/excelPreviewStore.ts
  - idt/docs/archive/2026-10/excel-preview/excel-preview.report.md (§1.5 결정 기록, §6.2 Problem)
  - idt/docs/archive/2026-10/excel-preview/excel-preview.design.md (§3.4 total_rows 규칙, v0.2)
  - 커밋 d7695f3 (feat(excel-preview))
confidence: 0.85
version: 1
created: 2026-10-13
updated: 2026-10-13
verified_at: 3b6353b
---

# openpyxl read_only 리더 함정 — max_col 패딩·dimensions 없는 파일의 전체 스캔·lazy max_row

> 읽는 시점: **openpyxl로 .xlsx를 읽는 코드(프리뷰·첨부 분석·KB 업로드)를 쓰거나 고칠 때**,
> `write_only`로 테스트 픽스처를 만들 때, 그리고 "작은 상한인데 큰 파일에서 느리다"를 만났을 때.

## 문제

산출 .xlsx 모달 미리보기(`GET /api/v1/document-extractor/files/{id}/preview`, 시트별 상위 100×50)를
`load_workbook(read_only=True, data_only=True)` 스트리밍으로 구현했는데, 설계가 몰랐던 openpyxl의
실제 동작 2건 때문에 리더 테스트가 두 번 깨졌다. 둘 다 문서만 읽어서는 보이지 않는다.

## 검증된 사실

### 1. `iter_rows(max_col=N)`은 모든 행을 N 폭까지 `None`으로 패딩한다

상한 50을 그대로 넘기면 3열짜리 시트도 행마다 50칸이 되어 직렬화·`truncated` 판정이 틀어진다.
해법: `max_col_arg = min(max_cols, ws.max_column)`로 **실제 폭과 상한의 min**을 요청하고,
메타(`max_column`)가 None이면 `max_col=None`으로 받아 수동 슬라이스(`raw[:max_cols]`)한다.

### 2. `dimensions` 메타가 없는 파일은 `load_workbook`이 시트 XML을 전체 스캔한다

read_only 모드는 `<dimension ref="A1:…">`로 `max_row/max_column`을 얻는다. 이 태그가 없는 파일
(openpyxl `write_only` 산출 등)은 **열기 단계에서** 전체 시트를 훑어 43MB 파일이 7.5초 걸렸다 —
"상위 100행만 읽으니 빠르다"는 가정이 열기 비용에서 무너진다.
또 이런 파일의 `ws.max_row`는 **읽은 만큼 갱신되는 lazy 값**이라 iter 후에는 신뢰할 수 없다.

방어 3종(`_read_sheet`):
- 메타(`max_row`·`max_column`)는 **iter 전에 캡처**한다.
- `_resolve_total_rows`: 상한 전에 끝까지 읽었으면 `seen_rows`가 정답. 상한에서 끊었으면 메타를 쓰되,
  메타가 None이거나 읽은 수보다 작으면(신뢰 불가) 읽은 수를 **하한값**으로 쓴다.
- 프로덕션 산출 경로(pandas 일반 모드)는 dimensions를 쓴다. 테스트 픽스처를 `write_only`로 만들면
  **프로덕션과 메타 특성이 달라** 없는 문제를 재현하거나 있는 문제를 놓친다 → 픽스처에 dimension을
  주입해 일치시켰다. "픽스처는 프로덕션 생성 경로와 같은 특성을 갖는가"를 픽스처 설계 시 물을 것.

### 3. 프리뷰 엔드포인트 계약 (다른 프리뷰 접점이 재사용할 것)

- 검증 순서 고정: store.load **404**(만료 포함) → owner **403** → 확장자 **415** → 파싱 **422**.
  다운로드(`GET /files/{id}`)와 동일한 owner/만료 검증을 공유한다.
- 리더는 동기, 유스케이스가 `asyncio.to_thread`로 감싼다. 응답은 시트별 `columns/rows(문자열)/total_rows/
  total_cols/truncated`. 2만 행 파일 0.1초대(메타 정상일 때).
- 프론트는 링크 옆 버튼 → Zustand `useExcelPreviewStore.open()` → `ChatPage`에 **1회 마운트**된
  `ExcelPreviewModal`(memo된 react-markdown 트리 밖에서 상태 소유 — 리렌더 회피). 진입 방식은
  `EXCEL_PREVIEW_TRIGGER`('button'|'link') 상수 1곳, 두 모드 모두 테스트 고정(`vi.mock`).
- 미강제 항목: 응답 1MB 상한(100×50으로 사실상 충족, 백로그 G-02).

## 다음에 적용하는 법

1. openpyxl read_only로 "상위 N행"을 읽는 코드는 위 3종 방어를 그대로 복제한다(`_read_sheet` 참조).
2. 외부 라이브러리의 성능 특성은 Design §2 전에 **10분 스파이크 스크립트**로 먼저 확인한다 —
   이번엔 Do에서 테스트가 깨진 뒤에야 알았다.
3. 채팅 첨부·KB 업로드 엑셀 프리뷰를 추가할 때는 응답 스키마(`ExcelPreviewResponse`)와 모달을
   재사용하고, 그리드 교체는 `ExcelPreviewGrid` 경계 하나만 바꾼다.
4. 수동 E2E 4종(생성→미리보기 일치·바이트 동일·TTL 만료 문구·10MB 2초)은 [[e2e-carryover-checklist]]에서 소화.

## 관련 문서

- 거짓 초록·픽스처 특성: `conventions/false-green-quality-gates.md`
- additive 엔드포인트 추가: `conventions/additive-contract-extension.md`
- 라우터 위치: `backend/api/router-map.md` (document_extractor_router)
