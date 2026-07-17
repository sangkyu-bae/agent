# kb-excel-upload Design Document

> **Summary**: KB 문서 업로드 파이프라인에 엑셀(.xlsx/.xls) 지원 — 확장자 라우팅 파서(additive) + 엑셀→Document 어댑터 + 텍스트 전제 청킹 설정 우회 + 섹션 요약 스킵
>
> **Plan**: `docs/01-plan/features/kb-excel-upload.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-17
> **Status**: Draft

---

## 1. Overview

### 1.1 Design Goals

- 기존 PDF 업로드 경로 **무변경**(위임 구조) — 회귀 0
- domain/application 레이어는 `PDFParserInterface` 의존 유지, 신규 파싱 로직은 infrastructure에만 추가
- 엑셀은 KB의 텍스트 전제 기능(clause/custom 청킹, 섹션 요약)을 명시적으로 우회하고, 우회 사실을 응답·로그로 드러낸다
- 미지원 확장자는 파싱 전에 422로 조기 거부

### 1.2 Design Principles

- 확장자→포맷 판정의 단일 진실원(domain 순수 함수)을 두고 파서 라우팅·정책 분기·에러 메시지가 공유
- 시트→텍스트 직렬화 로직은 기존 `ExcelUploadUseCase`와 이중화하지 않는다 (domain 순수 함수로 추출·공유)
- 하드코딩 금지: 행 수 상한은 `settings`로

---

## 2. Design Decisions (D1–D12)

| ID | Decision | Rationale |
|----|----------|-----------|
| D1 | **포맷 판정 단일 진실원**: `src/domain/parser/supported_formats.py` 신설 — `SUPPORTED_EXTENSIONS = {".pdf": "pdf", ".xlsx": "excel", ".xls": "excel"}`, `resolve_format(filename) -> str \| None` (suffix 소문자 비교, 미지원 시 None). 순수 함수라 domain 허용 | 라우팅 파서·KB 유스케이스 분기·에러 메시지가 같은 목록을 참조 — 포맷 추가 시 1곳 수정 |
| D2 | **미지원 확장자 예외**: `src/domain/parser/exceptions.py`에 `UnsupportedFileFormatError(ValueError)` 신설. 메시지: `"Unsupported file format '{ext}'. Supported: pdf, xlsx, xls"` | `ValueError` 서브클래스라 KB 라우터 `_raise_http`(fallback 422, `knowledge_base_router.py:275-286`)와 unified 라우터의 `except ValueError → 422`(`unified_upload_router.py:75-76`)에 **라우터 수정 없이** 매핑됨 |
| D3 | **라우팅 파서**: `src/infrastructure/parser/extension_routing_parser.py`의 `ExtensionRoutingParser(PDFParserInterface)` — ctor `(pdf_parser: PDFParserInterface, excel_parser: PDFParserInterface)`. `parse`/`parse_bytes`에서 `resolve_format()`으로 위임 대상 결정, None이면 D2 예외. `get_parser_name()="extension_routing"`, `supports_ocr()`는 pdf 위임 | 기존 `PDFParserInterface.parse_bytes`가 이미 `filename`을 받으므로 시그니처 변경 불필요. 유스케이스·DI 시그니처 불변 |
| D4 | **엑셀 어댑터**: `src/infrastructure/excel/excel_document_parser_adapter.py`의 `ExcelDocumentParserAdapter(PDFParserInterface)` — `PandasExcelParser`를 감싸 `ExcelData → List[Document]` 변환. 시트 1개 = Document 1개. metadata는 PDF와 동일한 `DocumentMetadata`(filename, user_id, page=시트 순번(1-base), total_pages=시트 수, parser="pandas_excel", document_id) + `sheet_name`, `row_count` 추가 키 | `page` 키는 다운스트림(청킹·ES 색인·콘텐츠 브라우저)이 의존하는 계약(fix-pymupdf4llm-page-key 선례) — PDF와 동일 구조 유지가 안전 |
| D5 | **시트→텍스트 직렬화 공용화**: `src/domain/excel/services/sheet_text_serializer.py`에 순수 함수 `sheet_to_text(sheet: SheetData) -> str` 추출 (형식 불변: 행마다 `"col1: val1 \| col2: val2"`, 개행 결합). `ExcelUploadUseCase._sheet_to_text`는 이 함수 위임으로 리팩토링, 어댑터(D4)도 동일 함수 사용 | Plan Risk-5(이중화) 해소. LangChain 미사용 순수 로직이라 domain 배치 가능, application·infrastructure 양쪽에서 import 허용 방향 |
| D6 | **행 수 상한**: `settings.kb_excel_max_rows_per_sheet: int = 20000` 신설. 어댑터가 파싱 직후 시트별 `row_count` 검사, 초과 시 `ValueError("Sheet '{name}' has {n} rows, exceeds limit {limit}. Split the file and retry")` → 422 | 임베딩 비용 폭증 방어(Plan Risk-3). 조용한 절단은 검색 완전성을 해쳐 배제 — 명시적 에러 + 분할 안내 |
| D7 | **청킹 설정 우회**: `KnowledgeBaseUploadUseCase._resolve_chunking`에 포맷 분기 — `resolve_format(filename)=="excel"`이면 resolver 호출 없이 `None` 반환(→ UnifiedUpload 기본 `parent_child` 경로, `use_case.py:202-214`). 이때 KB에 clause/custom이 켜져 있으면 warning 로그("Excel bypasses KB chunking settings"). 응답 `chunking_strategy`는 자연히 `"parent_child"` | FR-06. `None` 폴백은 resolver의 기존 계약(폴백 시 legacy)과 동일 패턴 — 신규 상태 없음 |
| D8 | **섹션 요약 스킵**: `_launch_summary`에 동일 포맷 분기 — excel이면 `resolve_summary_spec` 호출 전에 `None` 반환 + info 로그. 업로드 응답 `section_summary=null` | FR-07. 조항 청킹 전제 기능이 엑셀 텍스트에 오동작·실패 잡을 만드는 것 방지 |
| D9 | **DI 조립**: `main.py create_unified_upload_factories`(line 2623)에서 `parser = ExtensionRoutingParser(pdf_parser=ParserFactory.create_from_string(settings.parser_type), excel_parser=ExcelDocumentParserAdapter(PandasExcelParser(), max_rows=settings.kb_excel_max_rows_per_sheet))`. 다른 파서 DI 지점(ingest 등)은 불변 | `settings.parser_type`의 의미(PDF 파서 선택) 보존. UnifiedUpload를 쓰는 두 라우트(KB·unified)만 엑셀 수용 |
| D10 | **프론트 accept 정합화**: `KbUploadDocumentModal` accept를 `".pdf,.xlsx,.xls"`로 변경(백엔드 실지원과 1:1). `.docx/.txt/.md`는 애초에 백엔드에서 파싱 불가(500)였으므로 제거가 동작 보존. 안내 문구에 지원 형식 명시 | Plan에서 발견한 accept–실지원 불일치(잠재 버그)를 이번에 정합화. 서버 422 detail은 기존 `err.message` 표시 경로로 노출됨 |
| D11 | **응답 스키마 형태 불변**: `KbUploadResponse.total_pages`는 엑셀일 때 시트 수를 의미 — 필드 description만 갱신("PDF 페이지 수 또는 엑셀 시트 수"). 신규 필드 없음 | 프론트 타입 변경 최소화(계약 동기화는 주석 수준). D4에서 `total_pages=len(sheets)`가 자동 성립 |
| D12 | **기존 엑셀 경로 불변**: `/api/v1/excel/upload`·`ExcelUploadUseCase`는 D5 위임 리팩토링 외 무변경 | Plan Out of Scope 준수 |

---

## 3. Architecture

### 3.1 Data Flow (엑셀 업로드)

```
POST /knowledge-bases/{kb_id}/documents (file=*.xlsx)
  → KnowledgeBaseUploadUseCase.execute
      ├─ 권한 검사 (기존)
      ├─ _resolve_chunking: resolve_format=="excel" → None (D7, 우회 로그)
      └─ UnifiedUploadUseCase.execute
          ├─ ExtensionRoutingParser.parse_bytes (D3)
          │    └─ ExcelDocumentParserAdapter (D4)
          │         ├─ PandasExcelParser.parse_bytes → ExcelData
          │         ├─ 행 수 상한 검사 (D6)
          │         └─ sheet_to_text (D5, domain) → List[Document]
          ├─ _build_strategy: config=None → parent_child 기본 (기존)
          ├─ Qdrant + ES 이중 저장, kb_id/kb_name 메타데이터 주입 (기존)
          └─ document_metadata 기록 (기존)
      └─ _launch_summary: excel → None (D8, 스킵 로그)
```

미지원 확장자(.docx 등): `ExtensionRoutingParser`가 `UnsupportedFileFormatError` → 라우터 기존 매핑으로 422.

### 3.2 신규/변경 파일

| 구분 | 파일 | 내용 |
|------|------|------|
| 신규 | `src/domain/parser/supported_formats.py` | D1 포맷 판정 |
| 신규 | `src/domain/parser/exceptions.py` | D2 예외 |
| 신규 | `src/domain/excel/services/sheet_text_serializer.py` | D5 순수 직렬화 |
| 신규 | `src/infrastructure/parser/extension_routing_parser.py` | D3 라우팅 파서 |
| 신규 | `src/infrastructure/excel/excel_document_parser_adapter.py` | D4 어댑터 |
| 변경 | `src/config.py` | D6 `kb_excel_max_rows_per_sheet` |
| 변경 | `src/application/knowledge_base/upload_use_case.py` | D7/D8 포맷 분기 |
| 변경 | `src/application/use_cases/excel_upload_use_case.py` | D5 위임 (동작 불변) |
| 변경 | `src/api/main.py` | D9 DI 조립 |
| 변경 | `src/interfaces` KB 업로드 응답 스키마 description | D11 |
| 변경 | `idt_front/src/components/knowledge-base/KbUploadDocumentModal.tsx` | D10 accept·문구 |
| 신규/변경 | 각 테스트 파일 | §5 |

---

## 4. Error Handling

| 상황 | 발생 지점 | HTTP | detail |
|------|-----------|------|--------|
| 미지원 확장자 | ExtensionRoutingParser | 422 | `Unsupported file format '.docx'. Supported: pdf, xlsx, xls` |
| 시트 행 수 초과 | ExcelDocumentParserAdapter | 422 | 시트명·행 수·상한 + 분할 안내 |
| 손상 엑셀 (pandas 파싱 실패) | PandasExcelParser 예외 전파 | 422 | pandas 에러 메시지 요약 (어댑터가 ValueError로 래핑, request_id 로그) |
| 빈 엑셀 (시트 0개/전부 빈 행) | 어댑터 | 422 | `"No parsable sheet in excel file"` (빈 Document 리스트로 조용히 성공하지 않음) |

모든 에러는 LoggerInterface로 request_id 포함 구조화 로깅 (스택 트레이스 포함, print 금지).

---

## 5. Test Plan (TDD — 테스트 선행)

### 5.1 단위 (신규)

- `tests/domain/parser/test_supported_formats.py`: pdf/xlsx/xls/대문자/미지원/확장자 없음
- `tests/domain/excel/test_sheet_text_serializer.py`: 직렬화 형식 고정 (기존 `_sheet_to_text` 출력과 동일함을 핀ning)
- `tests/infrastructure/parser/test_extension_routing_parser.py`: pdf→pdf 파서 위임, xlsx→엑셀 어댑터 위임, 미지원→`UnsupportedFileFormatError`
- `tests/infrastructure/excel/test_excel_document_parser_adapter.py`: ExcelData→Document 매핑(메타데이터 키 전수), 행 상한 초과 에러, 빈 엑셀 에러

### 5.2 통합 (변경)

- `KnowledgeBaseUploadUseCase`: xlsx 업로드 시 ① resolver 미호출(청킹 config None) ② summary launcher 미호출 ③ clause 활성 KB에서 warning 로그
- KB 라우터: `.docx` 업로드 → 422 + detail 검증
- 기존 PDF 업로드 테스트 전부 통과 (회귀 게이트)

### 5.3 프론트 (변경)

- `KbUploadDocumentModal.test.tsx`: accept 속성 갱신 검증, 422 detail 메시지 표시

### 5.4 수동 E2E (Qdrant/ES 기동 시 — 기존 KB E2E 체크리스트에 병합)

- 실 xlsx 업로드 → Qdrant payload `sheet_name` 확인 → KB 검색 히트 → 콘텐츠 브라우저 청크 조회

---

## 6. Clean Architecture — Layer Assignment

| Layer | 추가/변경 | 규칙 준수 |
|-------|-----------|----------|
| domain | supported_formats, exceptions, sheet_text_serializer | 순수 함수/예외만 — 외부 API·LangChain 미사용 |
| application | upload_use_case 포맷 분기 (domain 함수만 import) | 흐름 제어만, 비즈니스 규칙은 domain 함수에 위임 |
| infrastructure | 라우팅 파서, 엑셀 어댑터 (LangChain Document 생성 허용 레이어) | `PDFParserInterface` 구현 |
| interfaces | 라우터 무변경 (기존 예외 매핑 재사용), 스키마 description만 | 비즈니스 로직 없음 |

---

## 7. Implementation Order

1. domain: supported_formats + exceptions + sheet_text_serializer (테스트 선행)
2. infrastructure: ExcelDocumentParserAdapter (테스트 선행)
3. infrastructure: ExtensionRoutingParser (테스트 선행)
4. application: upload_use_case D7/D8 분기 + ExcelUploadUseCase D5 위임 (테스트 선행)
5. config + main.py DI 조립 + 스키마 description
6. 라우터 통합 테스트 (422) + 기존 PDF 회귀 확인
7. 프론트: accept·문구 + 테스트 갱신
8. `/verify-architecture`, `/verify-tdd`, `/verify-logging`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-17 | Initial draft — D1~D12 확정 (라우팅 파서 additive, 도메인 순수 함수 공용화, 422 기존 매핑 재사용) | 배상규 |
