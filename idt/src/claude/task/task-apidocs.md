# APIDOCS-001: API 문서 로드 가이드

- **상태**: 완료
- **목적**: AI가 API 작업 시 참조할 문서 경로 및 로드 규칙 정의
- **위치**: `docs/apidocs/`
- **의존성**: LOG-001 (모든 API 모듈은 로깅 규칙 준수)

---

## 문서 구조

```
docs/apidocs/
├── README.md              — 전체 API 목록 + Base URL + 빠른 시작
├── 01-document-upload.md  — PDF 업로드 (레거시: /api/v1/documents)
├── 02-ingest.md           — PDF 인제스트 (권장: /api/v1/ingest/pdf)
├── 03-excel-upload.md     — 엑셀 벡터 저장 (/api/v1/excel/upload)
├── 04-analysis.md         — 엑셀 AI 분석 (/api/v1/analysis/excel)
├── 05-retrieval.md        — 벡터 검색 (/api/v1/retrieval/search)
├── 06-hybrid-search.md    — 하이브리드 검색 (/api/v1/hybrid-search/search)
├── 07-chunk-index.md      — 청킹 + ES 색인 (/api/v1/chunk-index/upload)
├── 08-morph-index.md      — 형태소 이중 색인 (/api/v1/morph-index/upload)
├── 09-rag-agent.md        — RAG 에이전트 (/api/v1/rag-agent/query)
└── 10-conversation.md     — 대화 메모리 (/api/v1/conversation/chat)
```

---

## API → Task 파일 매핑

AI가 특정 API를 수정하거나 분석할 때 아래 task 파일을 함께 로드한다.

| API 경로 | 문서 파일 | 관련 Task ID |
|---------|----------|------------|
| `POST /api/v1/documents/upload` | `01-document-upload.md` | PIPELINE-001, VEC-001 |
| `POST /api/v1/ingest/pdf` | `02-ingest.md` | INGEST-001, PARSE-001 |
| `POST /api/v1/excel/upload` | `03-excel-upload.md` | EXCEL-001 |
| `POST /api/v1/analysis/excel` | `04-analysis.md` | AGENT-002, LLM-001 |
| `POST /api/v1/retrieval/search` | `05-retrieval.md` | RETRIEVAL-001, COMP-001, RET-001 |
| `POST /api/v1/hybrid-search/search` | `06-hybrid-search.md` | HYBRID-001, ES-001 |
| `POST /api/v1/chunk-index/upload` | `07-chunk-index.md` | CHUNK-IDX-001 |
| `POST /api/v1/morph-index/upload` | `08-morph-index.md` | MORPH-IDX-001, KIWI-001 |
| `POST /api/v1/rag-agent/query` | `09-rag-agent.md` | RAG-001, HYBRID-001 |
| `POST /api/v1/conversation/chat` | `10-conversation.md` | CONV-001, MYSQL-001 |

---

## 문서 로드 규칙

### 규칙 1: API 작업 전 문서 선로드

API 관련 작업을 시작하기 전, 반드시 아래 순서로 문서를 확인한다:

```
1. docs/apidocs/README.md          → 전체 API 목록 및 흐름 파악
2. docs/apidocs/{해당 API 파일}.md → 해당 API 스펙 확인
3. src/claude/task/{관련 task}.md  → 구현 세부사항 확인
```

### 규칙 2: 신규 API 추가 시

신규 API 엔드포인트를 추가할 때:

1. `src/claude/task/task-{기능명}.md` 생성 (구현 스펙)
2. `docs/apidocs/{번호}-{기능명}.md` 생성 (사용자용 문서)
3. `docs/apidocs/README.md` 목록 테이블에 추가
4. `CLAUDE.md` Section 12 Task Files Reference 테이블에 추가
5. 본 파일(`task-apidocs.md`) API → Task 매핑 테이블에 추가

### 규칙 3: API 스펙 변경 시

파라미터, 응답 구조, 엔드포인트가 변경되면:

1. `docs/apidocs/{해당 파일}.md` 스펙 업데이트
2. `src/claude/task/{관련 task}.md` API 섹션 업데이트
3. 테스트 파일에서 변경된 스펙 반영 확인

---

## 구현 파일 목록 (라우터)

| 레이어 | 파일 |
|--------|------|
| API (레거시) | `src/api/routes/document_upload.py` |
| API | `src/api/routes/ingest_router.py` |
| API | `src/api/routes/excel_upload.py` |
| API | `src/api/routes/analysis_router.py` |
| API | `src/api/routes/retrieval_router.py` |
| API | `src/api/routes/hybrid_search_router.py` |
| API | `src/api/routes/chunk_index_router.py` |
| API | `src/api/routes/morph_index_router.py` |
| API | `src/api/routes/rag_agent_router.py` |
| API | `src/api/routes/conversation_router.py` |
| 앱 진입점 | `src/api/main.py` |

---

## 공통 패턴

모든 API는 다음 패턴을 따른다:

```python
# 1. DI placeholder (create_app()에서 override)
def get_xxx_use_case() -> XxxUseCase:
    raise NotImplementedError("...")

# 2. 라우터 정의
router = APIRouter(prefix="/api/v1/{path}", tags=["tag"])

# 3. 엔드포인트
@router.post("/{action}", response_model=XxxResponse)
async def xxx_endpoint(
    request: XxxRequest,
    use_case: XxxUseCase = Depends(get_xxx_use_case),
) -> XxxResponse:
    request_id = str(uuid.uuid4())
    ...
```

---

## LOG-001 준수 체크리스트

- [x] 모든 API 요청은 RequestLoggingMiddleware에서 자동 로깅
- [x] 에러 시 ExceptionHandlerMiddleware가 스택 트레이스 포함 로깅
- [x] request_id는 uuid4로 각 요청마다 생성
- [x] 민감 정보(api_key, token) 라우터 레벨에서 로깅 안 함
