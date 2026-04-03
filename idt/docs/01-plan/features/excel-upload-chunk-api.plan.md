# Plan: Excel Upload Chunk API

> Feature: excel-upload-chunk-api
> Created: 2026-03-03
> Status: Plan

---

## 1. 목표

사용자가 Excel 파일(.xlsx/.xls)을 업로드하면:
1. **파싱**: PandasExcelParser → ExcelData (시트별 행 데이터)
2. **변환**: ExcelData → List[LangChain Document] (시트 텍스트 변환)
3. **청킹**: ChunkingStrategy 적용 (full_token / parent_child / semantic)
4. **저장**: Qdrant VectorStore에 청크 저장

결과: RAG 질의 응답에 활용 가능한 Excel 문서 인덱싱

---

## 2. API 스펙

```
POST /api/v1/excel/upload
Content-Type: multipart/form-data

Parameters:
  - file: UploadFile (.xlsx, .xls)
  - user_id: str (query param)
  - strategy_type: str = "full_token" (query param, optional)

Response: ExcelUploadResponse
  - document_id: str
  - filename: str
  - sheet_count: int
  - chunk_count: int
  - stored_ids: List[str]
  - status: str
  - errors: List[str]
```

---

## 3. 아키텍처 (Thin DDD)

```
interfaces/api
  └── excel_upload.py             # FastAPI router (신규)

application/use_cases
  └── excel_upload_use_case.py   # ExcelUploadUseCase (신규)

domain/pipeline/schemas
  └── excel_upload_schema.py      # ExcelUploadResponse (신규)

infrastructure (기존 활용)
  ├── excel/pandas_excel_parser   # Excel 파싱
  ├── chunking/chunking_factory   # 청킹 전략
  └── vector/qdrant_vectorstore   # 벡터 저장
```

---

## 4. 구현 순서 (TDD)

### 4-1. Domain Schema (테스트 → 구현)
- `tests/domain/pipeline/test_excel_upload_schema.py`
- `src/domain/pipeline/schemas/excel_upload_schema.py`

### 4-2. Application UseCase (테스트 → 구현)
- `tests/application/use_cases/test_excel_upload_use_case.py`
- `src/application/use_cases/excel_upload_use_case.py`
  - ExcelData → List[Document] 변환 로직
  - ChunkingStrategy 적용
  - VectorStore 저장

### 4-3. API Route (테스트 → 구현)
- `tests/api/test_excel_upload.py`
- `src/api/routes/excel_upload.py`

### 4-4. Main 통합
- `src/api/main.py` 업데이트 (router 등록, DI 설정)

---

## 5. 핵심 설계 결정

- **ExcelData → Document 변환**: 시트별 전체 텍스트 하나의 Document
  - format: "컬럼1: 값1 | 컬럼2: 값2\n컬럼1: 값3 | ..." (행별 key-value)
  - metadata: file_id, filename, sheet_name, user_id
- **청킹 전략**: strategy_type 파라미터로 선택 (기본: full_token)
- **로깅**: LOG-001 규칙 준수 (request_id 전파, LoggerInterface 사용)

---

## 6. 의존성

| 기존 모듈 | 용도 |
|-----------|------|
| PandasExcelParser | Excel 파싱 |
| ChunkingStrategyFactory | 청킹 전략 생성 |
| VectorStoreInterface | Qdrant 저장 |
| EmbeddingInterface | 텍스트 임베딩 |
| LoggerInterface | 로깅 |
