# hwp-parser Planning Document

> **Summary**: 한글 문서(.hwp / .hwpx)에서 본문과 표 텍스트를 뽑아 KB 업로드·doc_chunk 파이프라인에 태운다
>
> **Project**: sangplusbot (idt / idt_front)
> **Author**: 배상규
> **Date**: 2026-10-08
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 공공·금융 문서는 한글(.hwp/.hwpx) 비중이 큰데, 지금 KB 업로드는 pdf/xlsx/xls만 받아서 운영자가 PDF로 변환해 올려야 한다. |
| **Solution** | 순수 Python 파서를 추가한다. HWP 5.0은 olefile과 zlib으로 BodyText 레코드를 직접 읽고, HWPX는 ZIP 안의 XML을 읽는다. kb-excel-upload 때 만든 `ExtensionRoutingParser`/`supported_formats` 구조에 추가만 하는 방식으로 붙인다. |
| **Function/UX Effect** | KB 업로드 모달과 `/doc-chunk`에서 .hwp/.hwpx를 바로 올릴 수 있다. 결과는 기존 청킹·임베딩·ES 색인 경로를 그대로 탄다. |
| **Core Value** | 운영자(P2)가 원본 포맷 그대로 지식을 넣을 수 있다. 특정 도메인 하드코딩 없이 포맷 지원만 넓히는 일반화 작업이다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 한글 문서를 PDF로 바꾸지 않고 바로 KB에 넣기 위해 |
| **WHO** | P2 KB 운영자·에이전트 소유자 (KB 업로드, doc_chunk API 사용자) |
| **RISK** | HWP 5.0 레코드 구조(컨트롤 문자, 표 중첩) 해석 오류로 텍스트가 깨지거나 누락됨. 암호화·배포용 문서는 읽을 수 없음 |
| **SUCCESS** | 실제 .hwp/.hwpx 샘플에서 본문과 표 텍스트가 순서대로 추출되고, KB 업로드가 200, 미지원·손상 파일은 422. PDF/엑셀 경로 회귀 0건(FAILED 목록 diff) |
| **SCOPE** | M1 도메인 포맷 등록 → M2 HWP 5.0 파서 → M3 HWPX 파서 → M4 라우팅·DI 연결 → M5 doc_chunk 분기 → M6 프론트 accept |

---

## 1. Overview

### 1.1 Purpose

`.hwp`(HWP 5.0 바이너리)와 `.hwpx`(OWPML, ZIP+XML) 파일에서 문단과 표 셀 텍스트를 문서 순서대로 추출해 LangChain `Document` 리스트로 돌려주는 파서를 만든다.

### 1.2 Background

- 현재 KB 업로드 포맷 판정은 `src/domain/parser/supported_formats.py` 한 곳에서 하며 `.pdf/.xlsx/.xls`만 등록돼 있다.
- 확장자별 분기는 `src/infrastructure/parser/extension_routing_parser.py`가 맡고, `src/api/main.py:4084`에서 PDF 파서와 엑셀 어댑터를 주입한다.
- 엑셀은 `PDFParserInterface`를 구현한 어댑터(`ExcelDocumentParserAdapter`)로 붙였고, metadata는 `DocumentMetadata`(page/total_pages/parser/document_id) 계약을 따른다. HWP도 같은 방식으로 붙이면 청킹·ES·콘텐츠 브라우저를 수정하지 않아도 된다.
- `olefile`과 `pyhwp`(hwp5)는 설치돼 있지 않다. pyhwp는 AGPL-3.0이고 유지보수가 멈춰 있어 쓰지 않는다.

### 1.3 Related Documents

- 선례: `docs/archive/*/kb-excel-upload/kb-excel-upload.{plan,design}.md`
- 위키: `docs/wiki/conventions/additive-contract-extension.md`, `docs/wiki/conventions/false-green-quality-gates.md`
- 포맷 명세: 한컴 공개 「한글 문서 파일 형식 5.0」, OWPML(KS X 6101)

---

## 2. Scope

### 2.1 In Scope

- [ ] `supported_formats`에 `FORMAT_HWP`(.hwp, .hwpx) 등록
- [ ] HWP 5.0 파서: olefile로 `FileHeader` 확인(압축·암호·배포용 플래그), `BodyText/SectionN` zlib 해제, `HWPTAG_PARA_TEXT` 디코딩(UTF-16LE + 컨트롤 문자 처리), 표 셀 문단 추출
- [ ] HWPX 파서: `Contents/section*.xml`을 순서대로 읽고 `hp:p`/`hp:t` 문단과 `hp:tbl` 셀 텍스트 추출 (표준 `zipfile` + `xml.etree`)
- [ ] `PDFParserInterface`를 구현한 HWP 어댑터. 섹션 1개 = Document 1개, `DocumentMetadata` 계약 준수
- [ ] `ExtensionRoutingParser`에 hwp 파서 주입, `main.py` DI 연결
- [ ] `/doc-chunk` `SUPPORTED_EXTENSIONS`와 `_extract_documents`에 hwp/hwpx 분기 추가
- [ ] 프론트 `KbUploadDocumentModal` accept와 안내 문구에 `.hwp,.hwpx` 추가 (테스트 포함)
- [ ] `pyproject.toml`에 `olefile` 의존성 추가

### 2.2 Out of Scope

- 이미지·도형·수식의 서식, 각주·미주·머리말/꼬리말의 내용 (본문 흐름 밖 텍스트)
  - 단, 글상자(도형) 안의 글자는 본문으로 보고 **포함**한다 (v0.2, Check 단계 결정)
- 표를 마크다운 행·열 구조로 복원하는 것 (셀 텍스트를 구분자로 이어 붙이는 수준만)
- 암호화 문서, 배포용 문서 복호화 → 422로 명확하게 거부
- HWP 3.x 이하 구버전 포맷
- 컬렉션 업로드(`UploadDocumentModal`, accept=.pdf), document_extractor(.pdf/.docx), 에이전트 첨부 등 다른 업로드 진입점
- OCR

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `resolve_format("x.hwp")`와 `resolve_format("x.HWPX")`가 `FORMAT_HWP`를 반환하고, `supported_formats_display()`에 hwp, hwpx가 포함된다 | High | Pending |
| FR-02 | HWP 5.0 파일에서 각 섹션의 문단 텍스트를 문서 순서대로 추출한다. 압축/비압축 둘 다 처리한다 | High | Pending |
| FR-03 | HWP 5.0 표 셀 안의 문단 텍스트를 표 위치에 맞춰 순서대로 포함한다 | High | Pending |
| FR-04 | PARA_TEXT의 컨트롤 문자(인라인/확장 컨트롤 등)는 텍스트로 새지 않게 건너뛰고, 탭은 `\t`, 줄바꿈은 개행으로 바꾼다 | High | Pending |
| FR-05 | HWPX 파일에서 section XML 순서대로 문단과 표 셀 텍스트를 추출한다 | High | Pending |
| FR-06 | 섹션 1개 = `Document` 1개. metadata는 `DocumentMetadata` 계약(빈 섹션을 뺀 뒤 page=1..n, total_pages=n, parser="hwp"/"hwpx", document_id)을 따른다. 빈 섹션은 제외한다 | High | Pending |
| FR-07 | 암호화·배포용·손상·텍스트 없는 파일은 `ValueError` 계열 예외로 거부해 기존 422 매핑을 탄다. 원인 예외는 스택 트레이스와 함께 로그로 남긴다 | High | Pending |
| FR-08 | KB 업로드(`/knowledge-bases/{id}/documents` 경로)에서 .hwp/.hwpx가 기존 파이프라인으로 처리된다. PDF·엑셀 동작은 변하지 않는다 | High | Pending |
| FR-09 | `/doc-chunk`에서 .hwp/.hwpx를 받아 청킹 결과를 돌려준다 | Medium | Pending |
| FR-10 | 프론트 KB 업로드 모달이 .hwp/.hwpx 파일을 선택할 수 있고 안내 문구에 표시한다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 의존성 | 신규 런타임 의존성은 `olefile`(BSD) 1개. AGPL·외부 바이너리 금지 | pyproject diff |
| 안전 | zlib 해제와 ZIP 해제에 크기 상한을 둬 압축 폭탄 방지, XML 파싱 시 외부 엔티티 미해석 | 단위 테스트 |
| 성능 | 수십 페이지 문서 파싱이 1초 내외 (임베딩 대비 무시할 수준) | 샘플 측정 |
| 아키텍처 | domain에는 포맷 상수만, 바이너리·XML 파싱은 infrastructure에 둔다 | `/verify-architecture` |
| 로깅 | print 금지, 실패 경로는 `logger.error(..., exception=e)` | `/verify-logging` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-10 구현, TDD(Red→Green) 순서로 테스트 선작성
- [ ] 실제 한글 프로그램으로 만든 .hwp/.hwpx 샘플(본문+표 포함)을 테스트 픽스처로 두고 기대 텍스트를 단언. 합성 바이트로만 테스트하고 끝내지 않는다
- [ ] KB 업로드를 실서버(또는 TestClient 인프로세스)로 1회 이상 돌려 hwp 업로드 성공 확인
- [ ] 회귀 0건: 변경 전후 `uv run python -m pytest` 정렬된 FAILED 목록 diff가 동일
- [ ] 프론트 `KbUploadDocumentModal.test.tsx` accept 단언 갱신, `npm run test`·`tsc -b` 통과

### 4.2 Quality Criteria

- [ ] 신규 모듈 테스트 커버리지 80% 이상
- [ ] ruff 위반 0
- [ ] 함수 40줄 이하, if 중첩 2단계 이하 (CLAUDE.md §3)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| PARA_TEXT 컨트롤 문자 해석 오류로 글자 깨짐·누락 | High | Medium | 명세의 컨트롤 문자 분류(char/inline/extended)를 표로 고정하고 단위 테스트. 실제 샘플 기대 텍스트로 검증 |
| 표 셀 텍스트 순서가 원문과 다름 (중첩 표, 병합 셀) | Medium | Medium | 셀 문단을 레코드 순서대로 읽고, 표 경계에만 구분자를 넣는다. 구조 복원은 스코프 밖 |
| 암호화·배포용 문서 | Medium | Medium | FileHeader 플래그로 사전 판별해 명확한 422 메시지 |
| 압축 폭탄·악성 XML | High | Low | 해제 크기 상한, `xml.etree` 외부 엔티티 미사용 확인 |
| 픽스처 샘플 확보 어려움 | Medium | Medium | 저작권 없는 직접 작성 샘플 2~3개(본문만/표 포함/hwpx)를 `tests/fixtures/`에 커밋 |
| 섹션 단위 Document가 너무 커서 섹션 요약 등 후속 기능에 영향 | Low | Low | 청킹은 기존 child chunk 설정을 따름. 엑셀처럼 별도 청킹 분기가 필요한지 Design에서 판단 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/domain/parser/supported_formats.py` | Domain 상수 | `FORMAT_HWP`, `.hwp/.hwpx` 매핑 추가 |
| `src/infrastructure/parser/extension_routing_parser.py` | Infra | 생성자에 hwp 파서 인자 추가 (optional로 두어 기존 호출부 호환 여부는 Design에서 결정) |
| `src/infrastructure/parser/hwp/` (신규) | Infra | HWP 5.0·HWPX 파서와 어댑터 |
| `src/api/main.py` | DI | `ExtensionRoutingParser` 생성 시 hwp 파서 주입 |
| `src/domain/doc_chunk/schemas.py`, `src/application/doc_chunk/use_case.py` | Domain/App | 확장자 집합과 추출 분기 추가 |
| `pyproject.toml` | Config | `olefile` 추가 |
| `idt_front/src/components/knowledge-base/KbUploadDocumentModal.tsx` (+test) | Front | accept·안내 문구 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `resolve_format` | READ | `application/knowledge_base/upload_use_case.py:74` (`is_excel` 판정) | None — hwp는 엑셀이 아니므로 기존 청킹 분기 유지 |
| `supported_formats_display` | READ | `domain/parser/exceptions.py` (422 메시지) | 메시지에 hwp, hwpx 추가됨. 메시지 문자열을 단언하는 테스트 확인 필요 |
| `ExtensionRoutingParser` | CREATE | `api/main.py:4084` | 인자 추가에 맞춰 수정 |
| `ExtensionRoutingParser` | CREATE | 관련 테스트 (`tests/infrastructure/parser/`) | Needs verification |
| `SUPPORTED_EXTENSIONS`(doc_chunk) | READ | `api/routes/doc_chunk_router.py` 검증·문구 | 문구 갱신 |
| KB 업로드 accept | READ | `KbUploadDocumentModal.test.tsx:41` | 단언 갱신 필요 |

### 6.3 Verification

- [ ] 위 소비자 전부 변경 후 동작 확인
- [ ] 422 메시지 문자열을 고정 단언하는 테스트 전수 검색
- [ ] PDF·엑셀 업로드 회귀 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter | ☐ |
| Dynamic | ☐ |
| **Enterprise** (Thin DDD: domain → application → infrastructure) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 지원 포맷 | HWP만 / HWPX만 / 둘 다 | 둘 다 | 실제 문서에 두 포맷이 섞여 있음 (사용자 결정) |
| HWP 5.0 엔진 | olefile+자체 / pyhwp / LibreOffice 변환 | olefile+자체 레코드 파서 | 라이선스(BSD)·경량·서버 바이너리 불필요 (사용자 결정) |
| HWPX 엔진 | 표준 zipfile+xml.etree / lxml | 표준 라이브러리 | 의존성 추가 없음 |
| 충실도 | 본문만 / 본문+표 텍스트 / 표 마크다운 | 본문+표 텍스트 | RAG에 필요한 글자는 확보하면서 범위를 통제 (사용자 결정) |
| 연결 방식 | 별도 엔드포인트 / 기존 라우팅에 추가 | `ExtensionRoutingParser`에 추가 | kb-excel-upload 선례, 기존 소비자 무변경 |
| Document 단위 | 파일 1개 / 섹션 1개 | 섹션 1개 | 엑셀 시트=Document와 같은 수준, `page` 메타 의미 유지 |
| Testing | pytest / Vitest | pytest + Vitest(RTL) | 프로젝트 표준 |

### 7.3 Clean Architecture Approach

```
domain/parser/supported_formats.py          ← FORMAT_HWP 상수만 (외부 의존 없음)
infrastructure/parser/hwp/
  ├─ hwp5_reader.py      ← OLE·zlib·레코드 → 섹션별 텍스트 블록
  ├─ hwpx_reader.py      ← ZIP·XML → 섹션별 텍스트 블록
  └─ hwp_document_parser.py ← PDFParserInterface 구현, 확장자로 reader 선택, Document 변환
infrastructure/parser/extension_routing_parser.py ← FORMAT_HWP → hwp_document_parser
application/doc_chunk/use_case.py           ← hwp 분기 (파서 주입)
api/main.py                                 ← DI
```

(정확한 파일 분할은 Design 단계 3안 비교에서 확정)

---

## 8. Convention Prerequisites

- TDD 필수: 테스트 먼저 작성 → 실패 확인 → 구현 (`idt/docs/rules/testing.md`)
- 로깅: `idt/docs/rules/logging.md`, 예외 삼킴 금지
- 테스트 실행은 `uv run python -m pytest`
- API 계약 동기화: 백엔드 지원 포맷 변경과 같은 작업 안에서 프론트 accept 수정

---

## 9. Next Steps

1. [ ] `/pdca design hwp-parser` — 3가지 설계안 비교 후 선택
2. [ ] 픽스처용 .hwp/.hwpx 샘플 준비 (본문만, 표 포함, 암호화 1개씩)
3. [ ] `/pdca do hwp-parser`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-08 | Initial draft | 배상규 |
| 0.2 | 2026-10-09 | Check 반영: 글상자 포함, FR-04 탭 표기, FR-06 page 번호 규칙 | 배상규 |
