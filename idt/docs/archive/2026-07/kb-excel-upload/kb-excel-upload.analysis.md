# kb-excel-upload Gap Analysis (Check)

> **Design**: `docs/02-design/features/kb-excel-upload.design.md`
> **Plan**: `docs/01-plan/features/kb-excel-upload.plan.md`
> **Analyzer**: gap-detector agent
> **Date**: 2026-07-17
> **Match Rate**: **97.6%** (보수 산정 — FR-09 런타임 검증 이월을 Partial 처리. 구조 기준 100%)

---

## 1. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Decisions (D1–D12) | 12/12 Match | ✅ |
| Functional Requirements (FR-01–FR-09) | 9/9 Match (FR-09는 구조 기준) | ✅ |
| §3.2 신규/변경 파일 목록 | 11/11 반영 | ✅ |
| §4 Error Handling 시나리오 | 4/4 구현 | ✅ |
| §5 Test Plan (5.1–5.3) | 전부 존재 (+보너스 test_exceptions) | ✅ |
| 레이어 규칙 / PDF 회귀 안전성 | 위반 0 | ✅ |

**산식**: 판정 항목 21개(D 12 + FR 9), Match 21 → 100%.
보수 산정: FR-09(런타임 미검증)를 Partial(0.5) 처리 시 (20+0.5)/21 = **97.6%**.
어느 쪽이든 ≥90% — Act 반복 불필요, Report 진행 가능.

---

## 2. D1–D12 판정 요약

| ID | 판정 | 근거 |
|----|:----:|------|
| D1 supported_formats | Match | `SUPPORTED_EXTENSIONS` + `resolve_format` (basename·소문자 suffix, Windows/POSIX 안전) |
| D2 UnsupportedFileFormatError | Match | ValueError 서브클래스, §4 메시지 리터럴 일치 |
| D3 ExtensionRoutingParser | Match | 위임 라우팅, `supports_ocr` pdf 위임 (`extension_routing_parser.py:57`) |
| D4 엑셀 어댑터 | Match | 시트=Document, DocumentMetadata 계약 + sheet_name/row_count (`excel_document_parser_adapter.py:95-96`) |
| D5 sheet_to_text 공용화 | Match | domain 순수 함수 + `ExcelUploadUseCase` 위임 (이중화 해소) |
| D6 행 수 상한 | Match | `config.py:36` + `_validate_row_limits` (메시지에 filename 추가 — 개선) |
| D7 청킹 우회 | Match | excel→None + clause/custom 경고 로그 (`upload_use_case.py:160-167`) |
| D8 요약 스킵 | Match | resolver 호출 전 스킵 + info 로그 (`upload_use_case.py:116-122`) |
| D9 DI 조립 | Match | `create_unified_upload_factories`만 변경, 타 DI 불변 |
| D10 프론트 accept | Match | `.pdf,.xlsx,.xls` + 안내 문구 + 422 detail 표시 |
| D11 total_pages 의미 | Match | 스키마 주석 + `len(parsed_docs)` 자동 성립 |
| D12 기존 엑셀 경로 불변 | Match | D5 위임 외 무변경 |

## 3. FR 판정 요약

FR-01~FR-08 전부 Match (근거·테스트 존재). FR-09(KB 목록·콘텐츠 브라우저 조회 동등성)는
필요 메타데이터 키(`page`/`document_id`/`sheet_name`)가 구조적으로 충족되나
**런타임 확인은 §5.4 수동 E2E로 이월** — 보수 산정에서 Partial 처리.

---

## 4. Gap / Observations (조치 불필요 3건)

| # | 항목 | 심각도 | 처리 |
|---|------|:------:|------|
| 1 | 손상 엑셀 로그에 request_id 부재 — `PDFParserInterface.parse_bytes` 시그니처에 request_id가 없어 어댑터 단에서 불가. ValueError 표면화 시 미들웨어가 request_id를 부착하므로 실효 커버 | Low | 코드 변경 불필요. Design §4 문구 해석 명확화만 |
| 2 | D6 에러 문자열이 리터럴보다 확장(`in '{filename}'` 추가) | Info | 개선 사항 — 프론트 테스트와 정합 |
| 3 | FR-09/§5.4 런타임 동등성 미검증 | 이월 | Qdrant/ES 기동 시 공통 KB E2E 체크리스트에 병합 (프로젝트 공통 이월 항목과 일치) |

## 5. 테스트 실행 결과 (Do 단계 실측)

- 신규 단위 31 + 유스케이스 15 + 라우터/unified 통과, 프론트 모달 3 통과 (`--pool=threads`)
- 기존 이슈 2건은 무관 확인: 교차 실행 이벤트 루프 산발 1건(격리 통과), pymupdf4llm 21건(변경 전 동일 실패 — 스태시 검증)

## 6. 이월 항목 (Report에 반영)

1. **수동 E2E** (Qdrant/ES 기동 필요): 실 xlsx 업로드 → Qdrant payload `sheet_name` → KB 검색 히트 → 콘텐츠 브라우저 청크 조회 — 기존 "KB 파이프라인 E2E pending" 체크리스트에 병합
2. 후속 후보 (Plan Out of Scope): 표 구조 인지 청킹, docx/txt/md 실지원(`kb-multi-format-upload`), 기존 `/api/v1/excel/upload` 경로 정리

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-17 | gap-detector 분석 — 97.6% (구조 100%), Act 불필요 판정 | 배상규 |
