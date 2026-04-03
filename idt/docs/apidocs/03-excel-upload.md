# 엑셀 업로드 API

> **태그**: `excel`
> **Base Path**: `/api/v1/excel`

---

## 개요

엑셀 파일(`.xlsx`, `.xls`)을 업로드하면:
1. pandas로 엑셀 내용 파싱
2. 선택한 청킹 전략으로 텍스트 분할
3. OpenAI 임베딩으로 벡터화
4. Qdrant 벡터 DB에 저장

업로드 후 [문서 검색 API](./05-retrieval.md)나 [RAG 에이전트 API](./09-rag-agent.md)로 내용을 질의할 수 있습니다.

> **엑셀 데이터 분석**이 목적이라면 [엑셀 분석 API](./04-analysis.md)를 사용하세요.
> 이 API는 저장 전용이고, 분석 API는 Claude AI로 질의응답까지 수행합니다.

---

## 엔드포인트

### 엑셀 파일 업로드

**`POST /api/v1/excel/upload`**

#### 요청

| 위치 | 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|------|---------|------|------|--------|------|
| form-data | `file` | File | ✅ | - | `.xlsx` 또는 `.xls` 파일 |
| query | `user_id` | string | ✅ | - | 문서 소유자 ID |
| query | `strategy_type` | string | ❌ | `full_token` | 청킹 전략 |

#### 청킹 전략 (`strategy_type`)

| 값 | 설명 |
|----|------|
| `full_token` | 고정 토큰 크기로 분할 (기본값, 표 형식 데이터에 적합) |
| `parent_child` | 계층 구조 청킹 |
| `semantic` | 의미 단위 분할 |

#### 응답 (200 OK)

```json
{
  "document_id": "excel_doc_xyz",
  "filename": "sales_data_2024.xlsx",
  "user_id": "user_001",
  "chunk_count": 32,
  "stored_ids": ["id1", "id2", "..."],
  "status": "completed",
  "errors": []
}
```

#### 오류 응답 (500)

```json
{
  "message": "Excel processing failed",
  "errors": ["Sheet parsing error: ..."]
}
```

#### 예제

```bash
curl -X POST "http://localhost:8000/api/v1/excel/upload?user_id=user_001&strategy_type=full_token" \
  -F "file=@sales_report.xlsx"
```

---

## 엑셀 vs. 분석 API 비교

| 기능 | 엑셀 업로드 API | 엑셀 분석 API |
|------|--------------|-------------|
| 파일 저장 (Qdrant) | ✅ | ❌ |
| 나중에 검색 가능 | ✅ | ❌ |
| 즉시 AI 질의응답 | ❌ | ✅ |
| 코드 실행 (계산) | ❌ | ✅ |
| 웹 검색 보완 | ❌ | ✅ |
