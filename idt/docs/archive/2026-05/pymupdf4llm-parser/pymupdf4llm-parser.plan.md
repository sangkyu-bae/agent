# pymupdf4llm-parser Planning Document

> **Summary**: pymupdf4llm 기반 Markdown PDF 파서 추가 — 테이블/구조 보존 파싱
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-12
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 PyMuPDFParser는 `page.get_text()`로 단순 텍스트만 추출하여 테이블·헤딩·리스트 등 문서 구조가 손실됨. 금융/정책 문서에서 표 형식 데이터가 깨져 RAG 품질이 저하됨 |
| **Solution** | `pymupdf4llm` 라이브러리를 활용한 별도 파서(`PyMuPDF4LLMParser`) 추가. 전체 문서를 Markdown으로 변환 후 단일 Document로 출력하여 하위 chunking에 위임 |
| **Function/UX Effect** | API에서 `parser_type="pymupdf4llm"` 선택 시 Markdown 형태의 구조화된 텍스트 추출. 테이블 포함/제외 옵션 제공. 기존 파서와 라우팅으로 선택 |
| **Core Value** | LLM이 이해하기 쉬운 Markdown 포맷으로 RAG 검색 품질 향상. 금융 문서의 표·약관 구조 보존 |

---

## 1. Overview

### 1.1 Purpose

`pymupdf4llm` 라이브러리를 활용한 새로운 PDF 파서 구현체를 추가하여, PDF 문서의 구조(테이블, 헤딩, 리스트)를 Markdown 형태로 보존한 텍스트 추출을 제공한다.

### 1.2 Background

- 현재 `PyMuPDFParser`는 `fitz.open()` + `page.get_text()`로 단순 텍스트만 추출
- 금융/정책 문서에는 표(금리, 수수료, 약관 조항 등)가 빈번하나, 현재 파서에서는 테이블 구조가 완전히 손실됨
- `pymupdf4llm`은 PyMuPDF 위에 LLM 최적화 Markdown 변환 레이어를 제공 (`to_markdown()`)
- 기존 파서를 유지하면서 별도 파서로 추가하여 라우팅에 따라 선택 가능하게 구성

### 1.3 Related Documents

- 기존 파서 구현: `src/infrastructure/parser/pymupdf_parser.py`
- 파서 인터페이스: `src/domain/parser/interfaces.py`
- 파서 팩토리: `src/infrastructure/parser/parser_factory.py`
- Ingest 파이프라인: `src/application/ingest/ingest_use_case.py`

---

## 2. Scope

### 2.1 In Scope

- [x] `PyMuPDF4LLMParser` 신규 구현체 작성 (`PDFParserInterface` 구현)
- [x] Markdown 변환 모드 지원 (전체 문서 → 단일 Markdown Document 출력)
- [x] 테이블 추출 On/Off 옵션 (`ParserConfig.extract_tables` 활용)
- [x] `ParserType.PYMUPDF4LLM` 추가 및 `ParserFactory` 확장
- [x] Ingest 파이프라인 파서 레지스트리에 `"pymupdf4llm"` 등록
- [x] API 라우터에서 `parser_type="pymupdf4llm"` 선택 가능
- [x] 단위 테스트 작성

### 2.2 Out of Scope

- 이미지 추출 (Base64 임베딩) — 별도 과제로 분리
- OCR 기능 — `pymupdf4llm`의 OCR 옵션은 이번 스코프에서 제외
- 기존 `PyMuPDFParser` 수정 또는 제거
- Markdown 전용 chunking 전략 추가 (기존 chunking 전략 활용)
- 프론트엔드 파서 선택 UI 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `PyMuPDF4LLMParser`가 `PDFParserInterface`를 구현하여 `parse()`, `parse_bytes()` 메서드 제공 | High | Pending |
| FR-02 | `pymupdf4llm.to_markdown()`를 사용하여 전체 PDF를 Markdown 문자열로 변환 | High | Pending |
| FR-03 | 변환된 Markdown을 단일 `Document` 객체로 반환 (페이지 단위가 아닌 전체 문서 단위) | High | Pending |
| FR-04 | `ParserConfig.extract_tables` 옵션에 따라 테이블 포함/제외 전환 | Medium | Pending |
| FR-05 | `ParserFactory`에 `ParserType.PYMUPDF4LLM` enum 값 추가 | High | Pending |
| FR-06 | Ingest API에서 `parser_type="pymupdf4llm"` 선택 시 해당 파서 사용 | High | Pending |
| FR-07 | `get_parser_name()` → `"pymupdf4llm"` 반환 | Low | Pending |
| FR-08 | `supports_ocr()` → `False` 반환 (이번 스코프) | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 10MB PDF 파싱 시간 30초 이내 | pytest benchmark |
| 호환성 | 기존 chunking 전략(full_token, parent_child, semantic)과 정상 동작 | 통합 테스트 |
| 안정성 | 깨진 PDF, 빈 PDF에서 에러 없이 빈 리스트 반환 또는 명확한 에러 | 엣지 케이스 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `PyMuPDF4LLMParser` 구현 완료 및 `PDFParserInterface` 계약 충족
- [ ] `ParserFactory`에서 `"pymupdf4llm"` 타입으로 생성 가능
- [ ] Ingest API에서 `parser_type="pymupdf4llm"` 요청 시 정상 동작
- [ ] 단위 테스트 작성 및 통과
- [ ] 기존 `pymupdf`, `llamaparser` 파서 동작에 영향 없음

### 4.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상
- [ ] 린트 에러 없음
- [ ] LOG-001 규칙 준수 (INFO on start/complete, ERROR with exception=)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `pymupdf4llm` 패키지 호환성 이슈 (pymupdf 버전 충돌) | High | Low | pyproject.toml에서 pymupdf 버전과 pymupdf4llm 호환 버전 확인 |
| 대용량 PDF에서 전체 문서 단일 Markdown 변환 시 메모리 부족 | Medium | Medium | 파일 크기 상한 검증, 로깅으로 모니터링 |
| Markdown 출력이 단일 Document일 때 기존 chunking과 메타데이터 호환성 | Medium | Medium | `total_pages=1`, `page=1`로 설정하고 chunking에서 분할 |
| `pymupdf4llm`의 테이블 변환 품질이 복잡한 금융 문서에서 불완전 | Low | Medium | 실제 금융 문서로 수동 검증, 필요 시 후처리 로직 추가 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic systems | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 구현 방식 | 기존 파서 교체 / 별도 파서 추가 | 별도 파서 추가 | 기존 pymupdf 파서 유지, 라우팅으로 선택 |
| 출력 단위 | 페이지 단위 / 전체 문서 단일 | 전체 문서 단일 | pymupdf4llm의 to_markdown()이 전체 문서 대상, chunking에 위임 |
| 테이블 처리 | 항상 포함 / 옵션으로 선택 | 옵션으로 선택 | ParserConfig.extract_tables로 제어 |
| 이미지 처리 | 포함 / 제외 | 제외 | 이번 스코프 외, 별도 과제 |
| 의존성 | pymupdf4llm PyPI 패키지 | pymupdf4llm | pymupdf 위에 동작하는 공식 확장 |

### 6.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

영향 범위:
┌─────────────────────────────────────────────────────┐
│ domain/parser/                                      │
│   - interfaces.py  (변경 없음, 기존 인터페이스 재사용)│
│   - value_objects.py (변경 없음)                     │
├─────────────────────────────────────────────────────┤
│ infrastructure/parser/                              │
│   - pymupdf4llm_parser.py  ← 신규 파일              │
│   - parser_factory.py      ← ParserType 추가        │
├─────────────────────────────────────────────────────┤
│ application/ingest/                                 │
│   - ingest_use_case.py     (변경 없음, 레지스트리 활용)│
├─────────────────────────────────────────────────────┤
│ api/                                                │
│   - main.py                ← 파서 레지스트리에 등록   │
│   - routes/ingest_router.py ← parser_type 설명 업데이트│
└─────────────────────────────────────────────────────┘
```

---

## 7. Implementation Guide

### 7.1 파일 변경 목록

| 파일 | 작업 | 설명 |
|------|------|------|
| `src/infrastructure/parser/pymupdf4llm_parser.py` | 신규 | `PyMuPDF4LLMParser` 클래스 구현 |
| `src/infrastructure/parser/parser_factory.py` | 수정 | `ParserType.PYMUPDF4LLM` 추가, `create()` 분기 추가 |
| `src/api/main.py` | 수정 | Ingest 파서 레지스트리에 `"pymupdf4llm"` 등록 |
| `src/api/routes/ingest_router.py` | 수정 | `parser_type` 설명에 `"pymupdf4llm"` 추가 |
| `pyproject.toml` | 수정 | `pymupdf4llm` 의존성 추가 |
| `tests/infrastructure/parser/test_pymupdf4llm_parser.py` | 신규 | 단위 테스트 |

### 7.2 구현 순서

1. **pyproject.toml** — `pymupdf4llm` 의존성 추가
2. **테스트 작성** — `test_pymupdf4llm_parser.py` (TDD Red)
3. **PyMuPDF4LLMParser** — `pymupdf4llm_parser.py` 구현 (TDD Green)
4. **ParserFactory 확장** — `ParserType.PYMUPDF4LLM` 추가
5. **API 등록** — `main.py` 파서 레지스트리에 등록
6. **라우터 업데이트** — `ingest_router.py` 설명 갱신
7. **통합 테스트** — Ingest 파이프라인 e2e 검증

### 7.3 핵심 구현 설계

```python
# PyMuPDF4LLMParser 핵심 로직 (개념 스케치)

class PyMuPDF4LLMParser(PDFParserInterface):

    def parse(self, file_path, user_id, config=None):
        config = config or ParserConfig()
        md_text = pymupdf4llm.to_markdown(
            file_path,
            write_images=False,           # 이미지 제외
            show_progress=False,
        )
        # config.extract_tables=False 일 경우 테이블 제거 후처리
        if not config.extract_tables:
            md_text = self._strip_tables(md_text)

        # 전체 문서를 단일 Document로 반환
        metadata = DocumentMetadata(
            filename=os.path.basename(file_path),
            user_id=user_id,
            page=1,
            total_pages=1,
            parser=self.get_parser_name(),
        )
        return [Document(page_content=md_text, metadata=metadata.to_dict())]

    def parse_bytes(self, file_bytes, filename, user_id, config=None):
        # fitz.open(stream=file_bytes)으로 doc 생성 후 pymupdf4llm 활용
        ...

    def get_parser_name(self):
        return "pymupdf4llm"

    def supports_ocr(self):
        return False
```

---

## 8. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section
- [x] `docs/rules/testing.md` TDD 규칙 존재
- [x] `docs/rules/logging.md` LOG-001 규칙 존재
- [x] 타입 힌트 필수 (pydantic / typing)

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Naming** | exists | `PyMuPDF4LLMParser` — 기존 파서 네이밍 패턴 따름 | High |
| **Folder structure** | exists | `infrastructure/parser/` 하위에 추가 | High |
| **Import order** | exists | 기존 규칙 그대로 | Low |
| **Error handling** | exists | logger.error with exception= | Medium |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (없음) | pymupdf4llm은 로컬 라이브러리, API 키 불필요 | - | - |

---

## 8. Next Steps

1. [ ] Design 문서 작성 (`pymupdf4llm-parser.design.md`)
2. [ ] 팀 리뷰 및 승인
3. [ ] 구현 시작 (TDD)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-12 | Initial draft | 배상규 |
