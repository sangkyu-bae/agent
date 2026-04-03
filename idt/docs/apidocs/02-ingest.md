# PDF 인제스트 API

> **태그**: `ingest`
> **Base Path**: `/api/v1/ingest`
> **권장**: 새로운 PDF 처리에는 이 API를 사용하세요.

---

## 개요

PDF 파일을 업로드하면 서버가:
1. 선택한 파서로 PDF 텍스트 추출
2. 선택한 청킹 전략으로 텍스트 분할
3. OpenAI 임베딩으로 벡터화
4. Qdrant 벡터 DB에 저장

레거시 문서 업로드 API와 달리 **파서 종류**와 **청킹 전략**을 호출 시 직접 선택할 수 있습니다.

---

## 엔드포인트

### PDF 인제스트

**`POST /api/v1/ingest/pdf`**

#### 요청

| 위치 | 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|------|---------|------|------|--------|------|
| form-data | `file` | File | ✅ | - | 업로드할 PDF 파일 |
| query | `user_id` | string | ✅ | - | 문서 소유자 ID |
| query | `parser_type` | string | ❌ | `pymupdf` | PDF 파서 선택 |
| query | `chunking_strategy` | string | ❌ | `full_token` | 청킹 전략 선택 |
| query | `chunk_size` | int | ❌ | 1000 | 청크당 토큰 수 (100~8000) |
| query | `chunk_overlap` | int | ❌ | 100 | 청크 간 겹침 토큰 수 (0~500) |

#### 파서 종류 (`parser_type`)

| 값 | 설명 | 적합한 상황 |
|----|------|------------|
| `pymupdf` | 빠른 로컬 파서 | 일반 텍스트 PDF, 속도 우선 |
| `llamaparser` | AI 기반 파서 (LlamaParse) | 복잡한 레이아웃, OCR 필요, 표·이미지 포함 PDF |

#### 청킹 전략 (`chunking_strategy`)

| 값 | 설명 |
|----|------|
| `full_token` | 고정 토큰 크기로 순차 분할 |
| `parent_child` | 큰 parent 청크 + 작은 child 청크 계층 구조 |
| `semantic` | 의미 단위로 분할 |

#### 응답 (200 OK)

```json
{
  "document_id": "doc_abc123",
  "filename": "annual_report.pdf",
  "user_id": "user_001",
  "total_pages": 20,
  "chunk_count": 85,
  "stored_ids": ["vec_001", "vec_002", "..."],
  "parser_used": "pymupdf",
  "chunking_strategy": "parent_child",
  "status": "completed",
  "errors": [],
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| 필드 | 설명 |
|------|------|
| `document_id` | 생성된 문서 고유 ID |
| `chunk_count` | 생성된 벡터 청크 수 |
| `stored_ids` | Qdrant에 저장된 벡터 ID 목록 |
| `parser_used` | 실제 사용된 파서 |
| `chunking_strategy` | 실제 사용된 청킹 전략 |
| `status` | `completed` 또는 `failed` |

#### 예제

```bash
# 기본 업로드 (pymupdf + full_token)
curl -X POST "http://localhost:8000/api/v1/ingest/pdf?user_id=user_001" \
  -F "file=@document.pdf"

# 고품질 파싱 + parent_child 청킹
curl -X POST "http://localhost:8000/api/v1/ingest/pdf" \
  -F "file=@complex_report.pdf" \
  -G -d "user_id=user_001" \
     -d "parser_type=llamaparser" \
     -d "chunking_strategy=parent_child" \
     -d "chunk_size=500" \
     -d "chunk_overlap=50"
```

---

## 파서 선택 가이드

```
단순 텍스트 PDF → pymupdf (빠름, 무료)
표/이미지 포함  → llamaparser (느림, API 비용 발생)
금융/정책 문서  → llamaparser 권장
```

## 청킹 전략 선택 가이드

```
일반 검색용            → full_token
RAG 질의응답 정확도 ↑  → parent_child (권장)
주제 단위 분리 필요    → semantic
```
