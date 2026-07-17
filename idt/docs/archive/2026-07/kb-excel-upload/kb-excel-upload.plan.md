# kb-excel-upload Planning Document

> **Summary**: KB(지식베이스) 문서 업로드 파이프라인에 엑셀(.xlsx/.xls) 지원 추가 — 현재 PDF 하드코딩된 파서를 확장자 기반 라우팅으로 확장하고, 미지원 확장자는 명시적 에러로 차단
>
> **Project**: sangplusbot (idt 백엔드 중심 + idt_front 업로드 모달 소폭)
> **Author**: 배상규
> **Date**: 2026-07-17
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | KB 업로드(`POST /knowledge-bases/{kb_id}/documents`)는 파서가 `fitz.open(filetype="pdf")`로 **PDF 하드코딩**되어 엑셀을 넣을 수 없다. 별도 엑셀 업로드 경로(`/api/v1/excel/upload`)는 존재하지만 기본 컬렉션 고정 + kb_id 메타데이터·ES 이중 저장·권한 검사 등 KB 파이프라인 기능을 전혀 타지 않는다. 라우터에 확장자 검증도 없어 엑셀을 올리면 명시적 거부가 아니라 파싱 단계 500 에러가 난다. |
| **Solution** | `UnifiedUploadUseCase`에 주입되는 파서를 **확장자 기반 라우팅 파서**(infrastructure 신설)로 교체한다: pdf→기존 파서 그대로, xlsx/xls→`PandasExcelParser` 결과(`ExcelData`)를 `List[Document]`로 변환하는 어댑터. 미지원 확장자는 라우터/유스케이스에서 422로 조기 거부. 기존 PDF 경로는 바이트 하나 바꾸지 않는 additive 확장. |
| **Function/UX Effect** | 사용자가 KB 업로드 모달에서 엑셀 파일을 그대로 올리면 시트 단위로 파싱→청킹→Qdrant+ES 이중 저장되어, PDF와 동일하게 KB 검색(RAG)·콘텐츠 브라우저에서 조회된다. 미지원 파일은 "지원하지 않는 형식" 에러가 즉시 표시된다. |
| **Core Value** | 금융/정책 문서 실무에서 비중이 큰 엑셀(요율표·한도표·코드표)을 KB 지식원으로 편입 — 엑셀만 벡터 검색에서 빠지는 지식 공백을 제거하고, 이원화된 업로드 경로를 KB 파이프라인으로 일원화할 기반을 만든다. |

---

## 1. Overview

### 1.1 Purpose

KB 문서 업로드 → Qdrant/ES 저장 파이프라인이 엑셀 파일을 1급 시민으로 처리하게 한다.
핵심 동기: 현재 엑셀→벡터 저장 경로는 KB 시스템 밖(`/api/v1/excel/upload`, 기본 컬렉션 고정)에만 존재해
KB 권한·메타데이터·하이브리드 검색(ES)·콘텐츠 브라우저와 단절되어 있다.

### 1.2 Background (현재 구조 분석 — 2026-07-17 확인)

| 항목 | 현재 상태 | 근거 코드 |
|------|-----------|----------|
| KB 업로드 라우터 | 확장자 검증 없음, filename 폴백도 `"unknown.pdf"` | `src/api/routes/knowledge_base_router.py:474-494` |
| 파서 주입 | `settings.parser_type`(기본 `"pymupdf"`) 단일 파서를 `UnifiedUploadUseCase`에 주입 | `src/api/main.py:2623`, `src/config.py:34` |
| 파서 구현 | `PyMuPDFParser.parse_bytes`가 `fitz.open(stream=..., filetype="pdf")` **하드코딩** | `src/infrastructure/parser/pymupdf_parser.py:84` |
| 파서 인터페이스 | `PDFParserInterface.parse_bytes(bytes, filename, user_id) -> List[Document]` — filename을 이미 받고 있어 확장자 라우팅에 시그니처 변경 불필요 | `src/domain/parser/interfaces.py` |
| 엑셀 파서 | `PandasExcelParser.parse_bytes -> ExcelData` (Document 리스트 아님, `ExcelParserInterface`) | `src/infrastructure/excel/pandas_excel_parser.py:41-43` |
| 기존 엑셀 업로드 | `POST /api/v1/excel/upload` → `ExcelUploadUseCase`: 파싱→full_token 청킹→Qdrant **기본 컬렉션 고정** 저장. ES 저장·kb_id 메타데이터·권한 검사 없음 | `src/api/routes/excel_upload.py`, `src/api/main.py:1245-1251` |
| ExcelData→청크 변환 | `ExcelUploadUseCase` 내부에 시트→텍스트→청킹 변환 로직 존재 (재사용 후보) | `src/application/use_cases/excel_upload_use_case.py:143-161` |
| KB 청킹 설정 | clause/custom 청킹은 KB 레코드/프로파일에서 해석 (`ChunkingSettingsResolver`) — 조항 정규식 등 **텍스트 문서 전제** | `src/application/knowledge_base/chunking_resolver.py` |
| 섹션 요약 | 업로드 성공 시 섹션 요약 잡 킥오프 — 조항 청킹 전제 | `src/application/knowledge_base/upload_use_case.py:97-129` |
| 프론트 업로드 모달 | `accept=".pdf,.docx,.txt,.md"` — 백엔드 실지원(PDF)보다 이미 넓게 선언된 상태(잠재 버그) | `idt_front/src/components/knowledge-base/KbUploadDocumentModal.tsx:92` |

### 1.3 Related Documents

- 선행 기능: `kb-custom-chunking`(청킹 설정 해석기·전략 5종), `kb-content-browser`(업로드 결과 검증 화면), `unified-pdf-upload-api`(UnifiedUploadUseCase 원형) — `docs/archive/2026-07/` 등
- 규칙: `idt/CLAUDE.md`(레이어 책임·금지사항), `docs/rules/testing.md`(TDD), 루트 `CLAUDE.md` §4-1(API 계약 동기화)

---

## 2. Scope

### 2.1 In Scope

**백엔드 (idt/) — 이번 기능의 중심**
- [ ] 확장자 기반 파서 라우팅: infrastructure에 `PDFParserInterface` 구현체(가칭 `ExtensionRoutingParser`) 신설 — pdf→기존 주입 파서 위임, xlsx/xls→엑셀 어댑터 위임. **기존 파서 코드 수정 없음(additive)**
- [ ] 엑셀 어댑터: `PandasExcelParser`의 `ExcelData`를 시트 단위 `List[Document]`로 변환 (metadata: `sheet_name`, `page`=시트 순번 등). `ExcelUploadUseCase` 내부 변환 로직과 중복되지 않게 공용화 검토
- [ ] 미지원 확장자 조기 거부: 지원 목록(pdf/xlsx/xls) 외는 422 + detail 메시지 (파싱 500 대신)
- [ ] 청킹 정책: clause/custom 청킹이 켜진 KB에 엑셀 업로드 시 동작 정의 — 엑셀은 KB 청킹 설정을 우회하고 기본 전략 적용 + 응답 `chunking_strategy`로 표시 (세부는 Design에서 확정)
- [ ] 섹션 요약 정책: 엑셀 문서는 섹션 요약 잡 킥오프 **스킵** (조항 청킹 전제 기능)
- [ ] Qdrant+ES 이중 저장·kb_id 메타데이터·문서 메타데이터 기록은 기존 `UnifiedUploadUseCase` 흐름 그대로 통과 확인
- [ ] pytest 선행 작성 (TDD: 라우팅 파서 단위, 어댑터 단위, 유스케이스 통합, 라우터 422)

**프론트엔드 (idt_front/) — 소폭**
- [ ] `KbUploadDocumentModal` accept에 `.xlsx,.xls` 추가 + 실지원 목록과 정합 (`.docx,.txt,.md`의 처리 방침은 Design에서 결정: 유지 시 백엔드 거부 메시지 표시로 방어)
- [ ] 업로드 응답 표시(청킹 전략·시트 수) 및 422 에러 메시지 표시 확인, 관련 테스트 갱신

### 2.2 Out of Scope

- 기존 `/api/v1/excel/upload` 경로의 개편·폐기 (deprecation은 후속 판단)
- `.docx`, `.txt`, `.md`, `.hwp` 등 **엑셀 외 신규 포맷의 실제 파싱 지원** → 후속 `kb-multi-format-upload` 후보
- 엑셀 전용 청킹 전략 신설(행 그룹·표 구조 인지 청킹) — 이번엔 기존 전략으로 텍스트화된 시트를 청킹
- 엑셀 문서 섹션 요약/키워드 추출 지원
- 채팅 첨부 엑셀 분석 워크플로우(별도 시스템) 변경
- KB 콘텐츠 브라우저의 엑셀 전용 렌더링(시트 미리보기 등)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | KB 문서 업로드 엔드포인트가 `.xlsx`/`.xls` 파일을 수용해 파싱한다 | High | Pending |
| FR-02 | 파서 선택은 파일 확장자 기준으로 라우팅된다 (pdf→기존 파서, xlsx/xls→엑셀 어댑터). 기존 PDF 업로드 동작은 변화 없다 | High | Pending |
| FR-03 | 지원 외 확장자는 파싱 시도 전에 422 + 명시적 detail("지원 형식: pdf, xlsx, xls")로 거부된다 | High | Pending |
| FR-04 | 엑셀은 시트 단위 Document로 변환되며 metadata에 `sheet_name`이 포함된다. 응답 `total_pages`는 시트 수를 의미한다 | High | Pending |
| FR-05 | 엑셀 문서도 PDF와 동일하게 Qdrant+ES 이중 저장되고 `kb_id`/`kb_name` 메타데이터가 주입된다 | High | Pending |
| FR-06 | clause/custom 청킹이 활성인 KB에 엑셀 업로드 시 텍스트 전제 청킹 설정을 우회하고 기본 전략을 적용하며, 적용 전략을 응답 `chunking_strategy`와 로그로 드러낸다 | High | Pending |
| FR-07 | 엑셀 업로드는 섹션 요약 잡을 킥오프하지 않는다 (업로드 성공 응답에는 영향 없음) | Medium | Pending |
| FR-08 | 프론트 KB 업로드 모달이 엑셀 파일 선택을 허용하고, 백엔드 422 detail을 사용자에게 표시한다 | High | Pending |
| FR-09 | 업로드된 엑셀 문서가 KB 문서 목록·콘텐츠 브라우저에서 기존과 동일하게 조회된다 (전용 렌더링 없이 청크 텍스트 표시) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | 파서 라우팅·어댑터는 infrastructure 레이어, 유스케이스는 `PDFParserInterface`만 의존(레이어 규칙 불변). 아키텍처 변경·인터페이스 개명 금지 | `/verify-architecture` |
| 호환성 | 기존 PDF 업로드 pytest 전부 통과(회귀 0). `settings.parser_type` 의미 보존 | pytest (격리 실행 기준 — Windows 이벤트 루프 flaky 주의) |
| TDD | 신규 모듈 테스트 선행 작성 (Red→Green) | `/verify-tdd` |
| 로깅 | 파서 라우팅 결정·엑셀 파싱 실패를 request_id 포함 구조화 로그로 기록, print 금지 | `/verify-logging` |
| 성능 | 대형 엑셀(수만 행) 파싱·임베딩 비용 상한 정책(행/셀 수 제한 or 경고) — Design에서 수치 확정 | 통합 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR 전체 구현 + 실제 xlsx 업로드→Qdrant/ES 저장→KB 검색 히트 플로우 동작
- [ ] pytest 선행 작성(Red→Green) 및 통과, 기존 PDF 업로드 회귀 0
- [ ] 프론트 accept·에러 표시 갱신 + Vitest 통과 (`--pool=threads`)
- [ ] Gap 분석(Check) ≥ 90%

### 4.2 Quality Criteria

- [ ] 레이어 의존성 규칙 위반 0 (`/verify-architecture`)
- [ ] 신규 함수 40줄 이하, if 중첩 2단계 이하
- [ ] 사전 실패 테스트(백엔드 api 28건·infra 30건, 프론트 8건)는 기존 이슈 — 신규 회귀로 오인 금지

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 파서 교체가 기존 PDF 경로에 회귀 유발 | High | Low | 기존 파서를 감싸는 additive 라우팅(위임) 구조 — PDF 경로는 기존 인스턴스 그대로 위임. 회귀 테스트 고정 |
| 시트→텍스트 변환 품질이 낮아 검색 recall 저하 (병합셀·수식·넓은 표) | Medium | High | 1차는 `ExcelUploadUseCase` 검증된 변환 재사용, 표 구조 인지 청킹은 명시적 후속 과제로 분리. 실데이터 샘플로 E2E 확인 |
| 대형 엑셀 임베딩 비용/시간 폭증 | Medium | Medium | 행·셀 수 상한 또는 청크 수 상한 정책 도입(Design 확정), 초과 시 명시적 에러 |
| clause/custom 청킹 KB와의 상호작용 미정의 → 조항 정규식이 엑셀 텍스트에 오적용 | High | Medium | FR-06으로 우회 정책 명문화 + 응답/로그로 가시화. 기존 설정 필드는 건드리지 않음(additive 원칙) |
| `ExcelData→Document` 변환 로직이 `ExcelUploadUseCase`와 이중화 | Medium | Medium | 공용 변환기를 한 곳에 두고 양쪽에서 사용 (레이어 규칙 내에서 — Design에서 위치 확정) |
| 섹션 요약 런처가 엑셀 문서에 잡 생성 → 실패 잡 누적 | Medium | Medium | FR-07 스킵 분기 + 테스트 고정 |
| 프론트 accept 확장 후 `.docx` 등 미지원 파일 혼선 | Low | Medium | 백엔드 422 detail을 그대로 표시 (FR-03/08), accept 목록 정합화 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

기존 프로젝트 편입 — Thin DDD(Domain→Application→Infrastructure) 현행 유지.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 파서 확장 방식 | ① 유스케이스에 if 분기 ② 파서 인터페이스 교체 ③ 라우팅 파서(위임 컴포지트) | ③ infrastructure `ExtensionRoutingParser` | 유스케이스·domain 무변경, `PDFParserInterface.parse_bytes`가 이미 filename을 받아 시그니처 변경 불필요. additive 원칙 |
| 엑셀→Document 변환 위치 | application 헬퍼 / infrastructure 어댑터 | infrastructure 어댑터 (`PDFParserInterface` 구현) | 파싱은 외부 라이브러리(pandas) 의존 — infrastructure 책임 |
| 확장자 검증 위치 | 라우터만 / 유스케이스만 / 양쪽 | Design에서 확정 (최소 1곳에서 조기 422) | 라우터 비즈니스 로직 금지 규칙과의 균형 필요 |
| 기존 엑셀 경로 | 즉시 통합 / 현행 유지 | 현행 유지 (Out of Scope) | 이번 스코프 최소화, 사용처 조사 후 후속 판단 |

### 6.3 Clean Architecture Approach

`domain/parser/interfaces.py`는 **무변경**. infrastructure에 라우팅 파서 + 엑셀 어댑터 추가,
`main.py` DI에서 라우팅 파서로 조립. application은 파서 인터페이스만 계속 의존.

---

## 7. Convention Prerequisites

- [x] `idt/CLAUDE.md` + `docs/rules/testing.md` 준수 (TDD 필수)
- [x] 로깅: LoggerInterface + request_id (print 금지)
- [x] 프론트: API 상수 `constants/api.ts` 집중, MSW 파일별 3종 훅
- [x] pytest는 Windows에서 파일 격리 실행 기준으로 판정

신규 환경변수 없음 (엑셀 상한 정책을 config로 둘 경우 `settings`에 추가 — 하드코딩 금지).

---

## 8. Next Steps

1. [ ] `/pdca design kb-excel-upload` — 라우팅 파서/어댑터 시그니처, 시트→텍스트 변환 규칙, 청킹 우회 정책, 상한 수치, 프론트 accept 방침 확정
2. [ ] 구현 (TDD: 어댑터 → 라우팅 파서 → 유스케이스 통합 → 라우터 → 프론트)
3. [ ] `/pdca analyze kb-excel-upload`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-17 | Initial draft — KB 업로드 PDF 하드코딩 및 엑셀 별도 경로 단절 확인, additive 라우팅 파서 방향 확정 | 배상규 |
