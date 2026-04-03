# IDT Document Processing API — 전체 API 문서

> **Base URL**: `http://localhost:8000`
> **버전**: 1.0.0
> **인증**: 현재 인증 없음 (user_id 파라미터로 소유권 구분)

---

## 서비스 개요

이 서비스는 PDF/엑셀 문서를 처리하고 AI 기반 검색·질의응답을 제공하는 백엔드 API입니다.

### 전체 처리 흐름

```
[문서 업로드] → [청킹(분할)] → [임베딩(벡터화)] → [저장(Qdrant/ES)]
                                                          ↓
[사용자 질의] → [하이브리드 검색] → [LLM 압축·답변 생성] → [응답 반환]
```

---

## API 목록

| 그룹 | 엔드포인트 | 설명 |
|------|-----------|------|
| [문서 업로드](#) | `POST /api/v1/documents/upload` | PDF 업로드 → 파싱 → 청킹 → 벡터 저장 (레거시) |
| [PDF 인제스트](#) | `POST /api/v1/ingest/pdf` | PDF 업로드 → 파서·청킹 전략 선택 가능 (권장) |
| [엑셀 업로드](#) | `POST /api/v1/excel/upload` | 엑셀 업로드 → 청킹 → 벡터 저장 |
| [엑셀 분석](#) | `POST /api/v1/analysis/excel` | 엑셀 질의 → Claude AI 분석 + 할루시네이션 검증 |
| [문서 검색](#) | `POST /api/v1/retrieval/search` | 벡터 유사도 검색 + LLM 압축 |
| [하이브리드 검색](#) | `POST /api/v1/hybrid-search/search` | BM25 + 벡터 RRF 병합 검색 |
| [청킹 색인](#) | `POST /api/v1/chunk-index/upload` | 텍스트 → 청킹 → 키워드 추출 → ES 색인 |
| [형태소 이중 색인](#) | `POST /api/v1/morph-index/upload` | Kiwi 형태소 분석 → Qdrant + ES 이중 색인 |
| [RAG 에이전트](#) | `POST /api/v1/rag-agent/query` | LangGraph ReAct 에이전트 내부 문서 질의응답 |
| [대화 메모리](#) | `POST /api/v1/conversation/chat` | 멀티턴 대화 (6턴 초과 시 자동 요약) |
| [헬스체크](#) | `GET /health` | 서버 상태 확인 |

---

## 세부 문서

| 파일 | 내용 |
|------|------|
| [01-document-upload.md](./01-document-upload.md) | PDF 문서 업로드 (레거시 + 비동기) |
| [02-ingest.md](./02-ingest.md) | PDF 인제스트 (권장, 파서 선택 가능) |
| [03-excel-upload.md](./03-excel-upload.md) | 엑셀 파일 업로드 및 벡터 저장 |
| [04-analysis.md](./04-analysis.md) | 엑셀 AI 분석 (Self-Corrective Agent) |
| [05-retrieval.md](./05-retrieval.md) | 문서 벡터 검색 (RAG Retrieval) |
| [06-hybrid-search.md](./06-hybrid-search.md) | BM25 + 벡터 하이브리드 검색 |
| [07-chunk-index.md](./07-chunk-index.md) | 텍스트 청킹 + ES 키워드 색인 |
| [08-morph-index.md](./08-morph-index.md) | Kiwi 형태소 분석 + 이중 색인 |
| [09-rag-agent.md](./09-rag-agent.md) | ReAct RAG 에이전트 질의응답 |
| [10-conversation.md](./10-conversation.md) | 멀티턴 대화 메모리 관리 |

---

## 공통 규칙

### 공통 응답 코드

| 코드 | 의미 |
|------|------|
| `200` | 성공 |
| `422` | 요청 파라미터 오류 |
| `500` | 서버 내부 오류 |

### request_id

모든 API는 내부적으로 `request_id`(UUID)를 생성하여 로그 추적에 사용합니다. 응답에 포함되어 반환됩니다.

### 청킹 전략 (strategy_type)

| 값 | 설명 |
|----|------|
| `full_token` | 전체 텍스트를 고정 토큰 단위로 분할 |
| `parent_child` | 큰 청크(parent)와 작은 청크(child)를 계층으로 분할 |
| `semantic` | 의미 단위로 분할 |

---

## 빠른 시작

### 1. 서버 실행 확인

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### 2. PDF 업로드 (권장 방식)

```bash
curl -X POST "http://localhost:8000/api/v1/ingest/pdf" \
  -F "file=@your_document.pdf" \
  -G -d "user_id=user_001" \
     -d "parser_type=pymupdf" \
     -d "chunking_strategy=parent_child"
```

### 3. 문서 질의응답

```bash
curl -X POST "http://localhost:8000/api/v1/rag-agent/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "금리 정책 요약해줘", "user_id": "user_001", "top_k": 5}'
```
