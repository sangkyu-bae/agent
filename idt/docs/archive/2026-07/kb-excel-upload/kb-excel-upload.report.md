# kb-excel-upload Completion Report

> **Feature**: KB(지식베이스) 문서 업로드 파이프라인 엑셀(.xlsx/.xls) 지원
> **Period**: 2026-07-17 (Plan → Design → Do → Check → Report, 1일)
> **Author**: 배상규
> **Match Rate**: **97.6%** (보수 산정 / 구조 기준 100%), Act 반복 0회

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | kb-excel-upload |
| 기간 | 2026-07-17 (1일 사이클) |
| Match Rate | 97.6% (구조 100%) — 90% 게이트 통과, iterate 불필요 |
| 산출 문서 | Plan / Design(D1~D12) / Analysis / Report 4종 |
| 코드 규모 | 신규 11파일 604줄(테스트 6파일 포함) + 수정 8파일(+151/-16) |
| 테스트 | 신규 백엔드 35건 + 프론트 3건 전부 통과, PDF 경로 회귀 0 |

### 1.3 Value Delivered (4-Perspective)

| Perspective | Delivered |
|-------------|-----------|
| **Problem (해결한 문제)** | KB 업로드 파서가 `fitz.open(filetype="pdf")` 하드코딩이라 엑셀 업로드가 불가능했고, 별도 엑셀 경로는 기본 컬렉션 고정으로 KB 권한·메타데이터·ES 색인·콘텐츠 브라우저와 단절되어 있었다. 미지원 파일은 명시적 거부 없이 파싱 500 에러였다. |
| **Solution (구현한 해법)** | 확장자 라우팅 파서(`ExtensionRoutingParser`) + 엑셀 어댑터(`ExcelDocumentParserAdapter`)를 infrastructure에 additive로 추가 — domain/application 인터페이스 무변경, 기존 PDF 파서 인스턴스 그대로 위임. `UnsupportedFileFormatError(ValueError)` 설계로 **라우터 수정 0줄**로 422 매핑 확보. |
| **Function/UX Effect (기능·UX 효과)** | 사용자는 KB 업로드 모달에서 엑셀을 그대로 올리면 시트 단위로 Qdrant+ES 이중 저장되어 PDF와 동일하게 검색·조회된다. 미지원 확장자·행 수 초과(시트당 2만 행)·손상/빈 엑셀은 전부 원인이 담긴 422 메시지로 즉시 표시된다. 조항/커스텀 청킹 KB에서도 엑셀은 안전하게 기본 전략으로 우회(로그 가시화)되고 섹션 요약 오동작이 차단된다. |
| **Core Value (핵심 가치)** | 금융 실무 비중이 큰 엑셀 자료(요율표·한도표·코드표)가 KB 지식원으로 편입되어 벡터 검색의 지식 공백이 제거됐다. 기존 PDF 경로 무변경(additive) 원칙으로 회귀 리스크 0을 유지하면서 포맷 확장의 표준 패턴(단일 진실원 + 위임 라우팅)을 확립 — docx 등 후속 포맷 추가 시 1곳 수정으로 확장 가능하다. |

---

## 1. PDCA 사이클 요약

| Phase | 산출물 | 핵심 결과 |
|-------|--------|----------|
| Plan | `docs/01-plan/features/kb-excel-upload.plan.md` | 현행 구조 실코드 근거 분석(9항목), FR-01~09, additive 방향 확정 |
| Design | `docs/02-design/features/kb-excel-upload.design.md` | D1~D12 — 라우팅 파서, 도메인 순수 함수 공용화, ValueError 편승 422, 청킹 우회/요약 스킵 |
| Do | 코드 + 테스트 (TDD Red→Green) | 신규 5모듈/변경 6파일(백), 모달 1파일(프), 테스트 38건 |
| Check | `docs/03-analysis/kb-excel-upload.analysis.md` | 21항목 전부 Match, 코드 조치 gap 0건 |

## 2. 구현 내역

### 2.1 신규 (백엔드 5모듈 + 테스트 6파일)

| 파일 | 역할 |
|------|------|
| `src/domain/parser/supported_formats.py` | 확장자→포맷 판정 단일 진실원 (D1) |
| `src/domain/parser/exceptions.py` | `UnsupportedFileFormatError(ValueError)` (D2) |
| `src/domain/excel/services/sheet_text_serializer.py` | 시트 직렬화 순수 함수 — 기존 유스케이스와 공용 (D5) |
| `src/infrastructure/parser/extension_routing_parser.py` | pdf/excel 위임 라우팅 (D3) |
| `src/infrastructure/excel/excel_document_parser_adapter.py` | ExcelData→Document, DocumentMetadata 계약 유지, 행 상한·빈 시트 검증 (D4/D6) |

### 2.2 변경

- `upload_use_case.py` — 엑셀 청킹 설정 우회(D7) + 섹션 요약 스킵(D8), warning/info 로그
- `excel_upload_use_case.py` — 직렬화 공용 함수 위임 (동작 불변)
- `config.py` — `kb_excel_max_rows_per_sheet=20000` (하드코딩 금지 준수)
- `main.py` — UnifiedUpload DI만 라우팅 파서로 조립 (D9)
- `knowledge_base_router.py` — total_pages 의미 주석 (D11)
- `KbUploadDocumentModal.tsx` — accept `.pdf,.xlsx,.xls` 정합화 + 안내 문구 (D10, 기존 accept의 미동작 docx/txt/md 잠재 버그 동시 해소)

### 2.3 테스트 (전부 선행 작성)

| 범위 | 건수 | 결과 |
|------|------|------|
| domain/infra 단위 (포맷·예외·직렬화·어댑터·라우팅) | 31 | 통과 |
| KB 업로드 유스케이스 엑셀 분기 | 4 | 통과 |
| KB 라우터 422 | 1 | 통과 |
| 프론트 모달 (accept·문구·422 표시) | 3 | 통과 |
| 회귀 (파서·엑셀·설정·unified·라우터) | 405+ | 통과 |

기존 이슈 확인 2건(신규 회귀 아님): 교차 실행 이벤트 루프 산발 1건(격리 통과), `test_pymupdf4llm_parser.py` 21건(스태시로 변경 전 동일 실패 검증).

## 3. 배운 점 / 재사용 가능한 패턴

1. **ValueError 서브클래스 편승 패턴**: 도메인 예외를 `ValueError` 서브클래스로 설계하면 기존 라우터의 폴백 매핑(422)에 무수정 편승 — interfaces 레이어 변경 0줄.
2. **위임 라우팅(additive) 패턴**: 기존 구현체를 감싸는 라우터 구현체 + 기존 인스턴스 그대로 위임 → 회귀 표면적 0. `PDFParserInterface.parse_bytes`가 filename을 이미 받고 있어 가능했다 (인터페이스 설계 시 컨텍스트 파라미터의 가치).
3. **jsdom userEvent.upload는 accept 필터를 적용**: accept에 안 맞는 파일은 조용히 무시됨 — 거부 시나리오 테스트는 accept에 맞는 파일 + 서버 422로 구성해야 한다.
4. **domain 순수 함수 추출로 레이어 합법 공유**: LangChain 무관 변환 로직을 domain으로 내리면 application·infrastructure 양쪽에서 규칙 위반 없이 재사용 가능.

## 4. 이월 항목

| 항목 | 조건 | 비고 |
|------|------|------|
| 수동 E2E: 실 xlsx 업로드→Qdrant payload `sheet_name`→KB 검색 히트→콘텐츠 브라우저 조회 | Qdrant/ES 기동 | 기존 "KB 파이프라인 E2E pending" 공통 체크리스트에 병합 (V047·V048 선행) |
| FR-09 런타임 동등성 | 상동 | Match Rate 보수 산정의 유일한 Partial 사유 |

**후속 후보** (Plan Out of Scope): 표 구조 인지 청킹, `kb-multi-format-upload`(docx/txt/md 실지원), 기존 `/api/v1/excel/upload` 경로 정리(deprecation 판단).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-17 | 완료 보고서 — 97.6%, Act 0회, 이월 2건 | 배상규 |
