## 🎯 In Progress

### PIPELINE-001: PDF 문서 처리 파이프라인 (LangGraph 에이전트)

- **상태**: 대기 중
- **목적**: PDF 업로드 → LLM 분류 → 카테고리별 청킹 → Qdrant 저장 파이프라인
- **기술 스택**: FastAPI, LangGraph, OpenAI, Qdrant
- **의존성**: 
  - VEC-001 (task-qdrant.md) - Qdrant 벡터 저장소
  - DOC-001 (task-pdfparser.md) - PDF 파서
  - CHUNK-001 (task-chunk.md) - 청킹 모듈

---

#### 🏗️ 1. 전체 아키텍처
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PDF Upload API (FastAPI)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LangGraph Document Processing Agent                     │
│  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐          │
│  │   Parse   │───▶│ Classify  │───▶│   Chunk   │───▶│   Store   │          │
│  │   Node    │    │   Node    │    │   Node    │    │   Node    │          │
│  └───────────┘    └───────────┘    └───────────┘    └───────────┘          │
│       │                │                │                │                  │
│       ▼                ▼                ▼                ▼                  │
│  PDF Parser       LLM (OpenAI)    Chunking Strategy   Qdrant               │
│  (DOC-001)        카테고리 분류    (CHUNK-001)        (VEC-001)            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

#### 📦 2. 문서 카테고리 정의 (Domain Layer)

##### 2-1. DocumentCategory Enum
- **파일**: `src/domain/pipeline/enums/document_category.py`
- **카테고리**:
  - [ ] LOAN_FINANCE: 대출, 금융, 투자, 보험, 예금, 신용카드 등
  - [ ] IT_SYSTEM: IT 시스템, 소프트웨어, 하드웨어, 네트워크, 개발 등
  - [ ] SECURITY_ACCESS: 보안, 접근 권한, 인증, 암호화, 개인정보보호 등
  - [ ] HR: 인사, 채용, 평가, 급여, 복리후생, 조직 등
  - [ ] ACCOUNTING_LEGAL: 회계, 법무, 세무, 계약, 규정, 정책 등
  - [ ] GENERAL: 위 카테고리에 해당하지 않는 일반 문서
```python
from enum import Enum

class DocumentCategory(str, Enum):
    LOAN_FINANCE = "loan_finance"
    IT_SYSTEM = "it_system"
    SECURITY_ACCESS = "security_access"
    HR = "hr"
    ACCOUNTING_LEGAL = "accounting_legal"
    GENERAL = "general"
    
    @property
    def description(self) -> str:
        descriptions = {
            self.LOAN_FINANCE: "대출, 금융, 투자, 보험, 예금, 신용카드 등 금융 관련 문서",
            self.IT_SYSTEM: "IT 시스템, 소프트웨어, 하드웨어, 네트워크, 데이터베이스, 개발 등 IT 관련 문서",
            self.SECURITY_ACCESS: "보안, 접근 권한, 인증, 암호화, 개인정보보호 등 보안 관련 문서",
            self.HR: "인사, 채용, 평가, 급여, 복리후생, 조직 등 인사 관련 문서",
            self.ACCOUNTING_LEGAL: "회계, 법무, 세무, 계약, 규정, 정책 등 회계/법무 관련 문서",
            self.GENERAL: "위 카테고리에 해당하지 않는 일반 문서",
        }
        return descriptions[self]
```

##### 2-2. CategoryChunkingConfig 매핑
- **파일**: `src/domain/pipeline/config/chunking_strategy_config.py`
- **목적**: 카테고리별 청킹 전략 매핑
```python
from src.domain.chunking.value_objects import ChunkingConfig

CATEGORY_CHUNKING_CONFIG: Dict[DocumentCategory, ChunkingConfig] = {
    DocumentCategory.IT_SYSTEM: ChunkingConfig(
        chunk_size=2000,
        chunk_overlap=200,
        strategy="full_token",
    ),
    DocumentCategory.HR: ChunkingConfig(
        chunk_size=400,
        chunk_overlap=100,
        strategy="full_token",
    ),
    DocumentCategory.LOAN_FINANCE: ChunkingConfig(
        chunk_size=800,
        chunk_overlap=100,
        strategy="full_token",
    ),
    DocumentCategory.SECURITY_ACCESS: ChunkingConfig(
        chunk_size=600,
        chunk_overlap=100,
        strategy="full_token",
    ),
    DocumentCategory.ACCOUNTING_LEGAL: ChunkingConfig(
        chunk_size=1000,
        chunk_overlap=150,
        strategy="full_token",
    ),
    DocumentCategory.GENERAL: ChunkingConfig(
        chunk_size=1000,
        chunk_overlap=100,
        strategy="full_token",
    ),
}
```

---

#### 📄 3. LangGraph State 정의

##### 3-1. PipelineState
- **파일**: `src/domain/pipeline/state/pipeline_state.py`
- **목적**: LangGraph 노드 간 공유 상태
```python
from typing import TypedDict, List, Optional
from langchain_core.documents import Document

class PipelineState(TypedDict):
    # 입력
    file_path: str
    file_bytes: Optional[bytes]
    filename: str
    user_id: str
    
    # Parse Node 결과
    parsed_documents: List[Document]
    total_pages: int
    document_id: str
    
    # Classify Node 결과
    category: DocumentCategory
    category_confidence: float
    classification_reasoning: str
    sample_pages: List[str]  # 분류에 사용된 페이지 내용
    
    # Chunk Node 결과
    chunked_documents: List[Document]
    chunk_count: int
    chunking_config_used: dict
    
    # Store Node 결과
    stored_ids: List[str]
    collection_name: str
    
    # 메타데이터
    processing_time_ms: int
    errors: List[str]
    status: str  # pending, parsing, classifying, chunking, storing, completed, failed
```

---

#### 🔧 4. LangGraph 노드 구현 (Infrastructure Layer)

##### 4-1. ParseNode (PDF 파싱)
- **파일**: `src/infrastructure/pipeline/nodes/parse_node.py`
- **의존성**: DOC-001 (PDFParserInterface)
- **기능**:
  - [ ] PDF 파일 → List[Document] 변환
  - [ ] document_id 생성
  - [ ] 메타데이터 추가 (user_id, filename 등)
- **세부 태스크**:
  - [ ] PDFParserInterface 주입받아 사용
  - [ ] 에러 핸들링 (파싱 실패 시 상태 업데이트)
```python
async def parse_node(state: PipelineState) -> PipelineState:
    """PDF 파싱 노드"""
    parser = get_pdf_parser()  # DI로 주입
    
    try:
        if state["file_bytes"]:
            documents = await parser.parse_bytes(
                state["file_bytes"], 
                state["filename"],
                state["user_id"],
            )
        else:
            documents = await parser.parse(
                state["file_path"],
                state["user_id"],
            )
        
        return {
            **state,
            "parsed_documents": documents,
            "total_pages": len(documents),
            "document_id": documents[0].metadata.get("document_id"),
            "status": "classifying",
        }
    except Exception as e:
        return {
            **state,
            "errors": state.get("errors", []) + [str(e)],
            "status": "failed",
        }
```

##### 4-2. ClassifyNode (LLM 카테고리 분류)
- **파일**: `src/infrastructure/pipeline/nodes/classify_node.py`
- **의존성**: LLMProviderInterface (COMP-001)
- **기능**:
  - [ ] 첫 페이지 + 중간 페이지 + 마지막 페이지 추출
  - [ ] LLM으로 카테고리 분류
  - [ ] confidence score 및 reasoning 반환
- **세부 태스크**:
  - [ ] 샘플 페이지 추출 로직
  - [ ] 분류 프롬프트 작성
  - [ ] 구조화 응답 파싱
```python
async def classify_node(state: PipelineState) -> PipelineState:
    """문서 카테고리 분류 노드"""
    documents = state["parsed_documents"]
    
    # 샘플 페이지 추출 (첫, 중간, 마지막)
    sample_pages = extract_sample_pages(documents)
    
    # LLM 분류
    llm = get_llm_provider()
    prompt = build_classification_prompt(sample_pages)
    result = await llm.generate_structured(prompt, ClassificationResult)
    
    return {
        **state,
        "category": result.category,
        "category_confidence": result.confidence,
        "classification_reasoning": result.reasoning,
        "sample_pages": sample_pages,
        "status": "chunking",
    }

def extract_sample_pages(documents: List[Document]) -> List[str]:
    """첫 페이지, 중간 페이지, 마지막 페이지 추출"""
    if len(documents) == 0:
        return []
    if len(documents) == 1:
        return [documents[0].page_content]
    if len(documents) == 2:
        return [documents[0].page_content, documents[1].page_content]
    
    first = documents[0].page_content
    middle = documents[len(documents) // 2].page_content
    last = documents[-1].page_content
    
    return [first, middle, last]
```

##### 4-3. 분류 프롬프트
- **파일**: `src/infrastructure/pipeline/prompts/classification_prompt.py`
```python
CLASSIFICATION_PROMPT = """
당신은 문서 분류 전문가입니다. 주어진 문서 샘플을 보고 카테고리를 분류하세요.

## 카테고리 목록
1. LOAN_FINANCE: 대출, 금융, 투자, 보험, 예금, 신용카드 등 금융 관련 문서
2. IT_SYSTEM: IT 시스템, 소프트웨어, 하드웨어, 네트워크, 데이터베이스, 개발 등 IT 관련 문서
3. SECURITY_ACCESS: 보안, 접근 권한, 인증, 암호화, 개인정보보호 등 보안 관련 문서
4. HR: 인사, 채용, 평가, 급여, 복리후생, 조직 등 인사 관련 문서
5. ACCOUNTING_LEGAL: 회계, 법무, 세무, 계약, 규정, 정책 등 회계/법무 관련 문서
6. GENERAL: 위 카테고리에 해당하지 않는 일반 문서

## 문서 샘플

### 첫 페이지
{first_page}

### 중간 페이지
{middle_page}

### 마지막 페이지
{last_page}

## 지시사항
문서의 주요 내용, 용어, 형식을 분석하여 가장 적합한 카테고리를 선택하세요.

다음 JSON 형식으로만 응답하세요:
{{
    "category": "카테고리명 (LOAN_FINANCE, IT_SYSTEM, SECURITY_ACCESS, HR, ACCOUNTING_LEGAL, GENERAL 중 하나)",
    "confidence": 0.0~1.0 사이의 확신도,
    "reasoning": "분류 근거를 간단히 설명"
}}
"""
```

##### 4-4. ChunkNode (카테고리별 청킹)
- **파일**: `src/infrastructure/pipeline/nodes/chunk_node.py`
- **의존성**: CHUNK-001 (ChunkingStrategyInterface)
- **기능**:
  - [ ] 카테고리에 따른 청킹 설정 적용
  - [ ] IT_SYSTEM → 2000 토큰
  - [ ] HR → 400 토큰, 100 오버랩
  - [ ] 기타 카테고리별 설정 적용
- **세부 태스크**:
  - [ ] CATEGORY_CHUNKING_CONFIG 매핑 사용
  - [ ] ChunkingStrategy 주입받아 실행
  - [ ] 청크 메타데이터에 category 추가
```python
async def chunk_node(state: PipelineState) -> PipelineState:
    """카테고리별 청킹 노드"""
    category = state["category"]
    documents = state["parsed_documents"]
    
    # 카테고리별 청킹 설정 가져오기
    chunking_config = CATEGORY_CHUNKING_CONFIG.get(
        category, 
        CATEGORY_CHUNKING_CONFIG[DocumentCategory.GENERAL]
    )
    
    # 청킹 전략 실행
    chunker = get_chunking_strategy(chunking_config.strategy)
    chunked_docs = await chunker.chunk(documents, chunking_config)
    
    # 메타데이터에 카테고리 추가
    for doc in chunked_docs:
        doc.metadata["category"] = category.value
        doc.metadata["chunking_strategy"] = chunking_config.strategy
        doc.metadata["chunk_size"] = chunking_config.chunk_size
    
    return {
        **state,
        "chunked_documents": chunked_docs,
        "chunk_count": len(chunked_docs),
        "chunking_config_used": chunking_config.to_dict(),
        "status": "storing",
    }
```

##### 4-5. StoreNode (Qdrant 저장)
- **파일**: `src/infrastructure/pipeline/nodes/store_node.py`
- **의존성**: VEC-001 (VectorStoreInterface)
- **기능**:
  - [ ] 청크된 문서 임베딩
  - [ ] Qdrant에 저장
  - [ ] 저장된 ID 반환
- **세부 태스크**:
  - [ ] EmbeddingInterface 주입받아 임베딩
  - [ ] QdrantVectorStore 주입받아 저장
  - [ ] 배치 저장 (대량 문서 최적화)
```python
async def store_node(state: PipelineState) -> PipelineState:
    """Qdrant 벡터 저장 노드"""
    documents = state["chunked_documents"]
    
    # 임베딩 & 저장
    vectorstore = get_vectorstore()  # DI로 주입
    
    stored_ids = await vectorstore.add_documents(
        documents=documents,
        metadatas=[doc.metadata for doc in documents],
    )
    
    return {
        **state,
        "stored_ids": stored_ids,
        "collection_name": vectorstore.collection_name,
        "status": "completed",
    }
```

---

#### 🔗 5. LangGraph 워크플로우 정의

##### 5-1. DocumentProcessingGraph
- **파일**: `src/infrastructure/pipeline/graph/document_processing_graph.py`
```python
from langgraph.graph import StateGraph, END
from src.domain.pipeline.state import PipelineState

def create_document_processing_graph() -> StateGraph:
    """문서 처리 LangGraph 워크플로우 생성"""
    
    # 그래프 초기화
    workflow = StateGraph(PipelineState)
    
    # 노드 추가
    workflow.add_node("parse", parse_node)
    workflow.add_node("classify", classify_node)
    workflow.add_node("chunk", chunk_node)
    workflow.add_node("store", store_node)
    workflow.add_node("handle_error", error_handler_node)
    
    # 엣지 정의 (조건부 라우팅)
    workflow.add_edge("parse", "classify")
    workflow.add_conditional_edges(
        "parse",
        should_continue,
        {
            "continue": "classify",
            "error": "handle_error",
        }
    )
    workflow.add_conditional_edges(
        "classify",
        should_continue,
        {
            "continue": "chunk",
            "error": "handle_error",
        }
    )
    workflow.add_conditional_edges(
        "chunk",
        should_continue,
        {
            "continue": "store",
            "error": "handle_error",
        }
    )
    workflow.add_edge("store", END)
    workflow.add_edge("handle_error", END)
    
    # 시작점 설정
    workflow.set_entry_point("parse")
    
    return workflow.compile()

def should_continue(state: PipelineState) -> str:
    """에러 발생 시 분기"""
    if state.get("status") == "failed":
        return "error"
    return "continue"

async def error_handler_node(state: PipelineState) -> PipelineState:
    """에러 처리 노드"""
    # 로깅, 알림 등
    return {
        **state,
        "status": "failed",
    }
```

##### 5-2. 그래프 시각화
```
                    ┌─────────────┐
                    │    START    │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │    Parse    │
                    │    Node     │
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │  success?   │
                    └──────┬──────┘
               yes ◀───────┴───────▶ no
                │                    │
                ▼                    ▼
         ┌─────────────┐      ┌─────────────┐
         │  Classify   │      │   Error     │
         │    Node     │      │  Handler    │
         └──────┬──────┘      └──────┬──────┘
                │                    │
                ▼                    │
         ┌─────────────┐             │
         │   Chunk     │             │
         │    Node     │             │
         └──────┬──────┘             │
                │                    │
                ▼                    │
         ┌─────────────┐             │
         │   Store     │             │
         │    Node     │             │
         └──────┬──────┘             │
                │                    │
                ▼                    ▼
                    ┌─────────────┐
                    │     END     │
                    └─────────────┘
```

---

#### 🌐 6. FastAPI 엔드포인트

##### 6-1. PDF Upload API
- **파일**: `src/api/routes/document_upload.py`
```python
from fastapi import APIRouter, UploadFile, File, Depends, BackgroundTasks
from src.infrastructure.pipeline.graph import create_document_processing_graph
from src.domain.pipeline.state import PipelineState

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    background_tasks: BackgroundTasks,
):
    """PDF 문서 업로드 및 처리 파이프라인 실행"""
    
    # 파일 읽기
    file_bytes = await file.read()
    filename = file.filename
    
    # 초기 상태 생성
    initial_state: PipelineState = {
        "file_path": "",
        "file_bytes": file_bytes,
        "filename": filename,
        "user_id": user_id,
        "parsed_documents": [],
        "total_pages": 0,
        "document_id": "",
        "category": None,
        "category_confidence": 0.0,
        "classification_reasoning": "",
        "sample_pages": [],
        "chunked_documents": [],
        "chunk_count": 0,
        "chunking_config_used": {},
        "stored_ids": [],
        "collection_name": "",
        "processing_time_ms": 0,
        "errors": [],
        "status": "pending",
    }
    
    # LangGraph 실행 (비동기)
    graph = create_document_processing_graph()
    result = await graph.ainvoke(initial_state)
    
    return DocumentUploadResponse(
        document_id=result["document_id"],
        filename=filename,
        category=result["category"],
        category_confidence=result["category_confidence"],
        chunk_count=result["chunk_count"],
        stored_ids=result["stored_ids"],
        status=result["status"],
        errors=result["errors"],
    )

@router.post("/upload/async")
async def upload_document_async(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    background_tasks: BackgroundTasks,
):
    """비동기 PDF 처리 (백그라운드 태스크)"""
    
    file_bytes = await file.read()
    task_id = generate_task_id()
    
    # 백그라운드에서 처리
    background_tasks.add_task(
        process_document_background,
        task_id=task_id,
        file_bytes=file_bytes,
        filename=file.filename,
        user_id=user_id,
    )
    
    return {"task_id": task_id, "status": "processing"}

@router.get("/upload/status/{task_id}")
async def get_upload_status(task_id: str):
    """업로드 처리 상태 조회"""
    status = await get_task_status(task_id)
    return status
```

---

#### 📄 7. DTO / Schemas

##### 7-1. DocumentUploadRequest DTO
- **파일**: `src/domain/pipeline/schemas/upload_schema.py`
```python
class DocumentUploadRequest(BaseModel):
    user_id: str
    custom_category: Optional[DocumentCategory] = None  # 수동 분류 시
    chunking_override: Optional[ChunkingConfig] = None  # 청킹 설정 오버라이드
```

##### 7-2. DocumentUploadResponse DTO
- **파일**: `src/domain/pipeline/schemas/upload_schema.py`
```python
class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    category: DocumentCategory
    category_confidence: float
    classification_reasoning: str
    total_pages: int
    chunk_count: int
    chunking_config_used: dict
    stored_ids: List[str]
    collection_name: str
    status: str
    processing_time_ms: int
    errors: List[str]
```

##### 7-3. ClassificationResult DTO
- **파일**: `src/domain/pipeline/schemas/classification_schema.py`
```python
class ClassificationResult(BaseModel):
    category: DocumentCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
```

---

#### 📁 예상 폴더 구조
```
src/
├── domain/
│   └── pipeline/
│       ├── __init__.py
│       ├── enums/
│       │   ├── __init__.py
│       │   └── document_category.py
│       ├── config/
│       │   ├── __init__.py
│       │   └── chunking_strategy_config.py
│       ├── state/
│       │   ├── __init__.py
│       │   └── pipeline_state.py
│       └── schemas/
│           ├── __init__.py
│           ├── upload_schema.py
│           └── classification_schema.py
│
├── infrastructure/
│   └── pipeline/
│       ├── __init__.py
│       ├── nodes/
│       │   ├── __init__.py
│       │   ├── parse_node.py
│       │   ├── classify_node.py
│       │   ├── chunk_node.py
│       │   └── store_node.py
│       ├── graph/
│       │   ├── __init__.py
│       │   └── document_processing_graph.py
│       └── prompts/
│           ├── __init__.py
│           └── classification_prompt.py
│
└── api/
    └── routes/
        └── document_upload.py
```

---

#### 🔗 8. 의존성 연결 (기존 모듈 활용)
```python
# DI Container 설정 예시
from src.infrastructure.parser import PyMuPDFParser  # DOC-001
from src.infrastructure.chunking import FullTokenStrategy  # CHUNK-001
from src.infrastructure.vectorstore import QdrantVectorStore  # VEC-001
from src.infrastructure.embeddings import OpenAIEmbedding  # VEC-001
from src.infrastructure.compressor.providers import OpenAIProvider  # COMP-001

class PipelineContainer:
    def __init__(self):
        # PDF 파서 (DOC-001)
        self.pdf_parser = PyMuPDFParser()
        
        # LLM 프로바이더 (COMP-001)
        self.llm_provider = OpenAIProvider(LLMConfig(
            model_name="gpt-4o-mini",
            temperature=0.0,
        ))
        
        # 임베딩 (VEC-001)
        self.embedding = OpenAIEmbedding(model_name="text-embedding-3-small")
        
        # 벡터 저장소 (VEC-001)
        self.vectorstore = QdrantVectorStore(
            client=QdrantClient(...),
            collection_name="documents",
            embedding=self.embedding,
        )
        
        # 청킹 전략 (CHUNK-001)
        self.chunking_strategies = {
            "full_token": FullTokenStrategy(),
            "parent_child": ParentChildStrategy(),
        }
```

---

#### ✅ 완료 조건

- [ ] DocumentCategory enum 정의 및 description 테스트
- [ ] 카테고리별 청킹 설정 매핑 테스트
- [ ] ParseNode - DOC-001 PDF 파서 연동 테스트
- [ ] ClassifyNode - 샘플 페이지 추출 (첫/중간/마지막) 테스트
- [ ] ClassifyNode - LLM 분류 프롬프트 테스트
- [ ] ChunkNode - 카테고리별 청킹 설정 적용 테스트
  - [ ] IT_SYSTEM → 2000 토큰
  - [ ] HR → 400 토큰, 100 오버랩
- [ ] StoreNode - VEC-001 Qdrant 저장 테스트
- [ ] LangGraph 워크플로우 전체 흐름 테스트
- [ ] FastAPI 업로드 API 테스트
- [ ] 에러 핸들링 (파싱 실패, 분류 실패 등) 테스트
- [ ] 비동기 백그라운드 처리 테스트

---

#### 📝 메모

- langgraph>=0.0.40 의존성 추가
- DOC-001, CHUNK-001, VEC-001, COMP-001 모듈 연동 필수
- 분류 프롬프트는 실제 데이터로 튜닝 필요
- 대용량 파일 처리 시 백그라운드 태스크 권장
- 카테고리별 청킹 설정은 CATEGORY_CHUNKING_CONFIG에서 확장 가능

---

#### 🧪 테스트 시나리오
```python
# 테스트 케이스
1. IT 문서 업로드 → IT_SYSTEM 분류 → 2000 토큰 청킹
2. HR 문서 업로드 → HR 분류 → 400 토큰, 100 오버랩 청킹
3. 금융 문서 업로드 → LOAN_FINANCE 분류
4. 1페이지 문서 (샘플 추출 엣지케이스)
5. 2페이지 문서 (샘플 추출 엣지케이스)
6. 파싱 실패 문서 → 에러 핸들링
7. 분류 실패 → GENERAL 폴백
8. 대용량 문서 (100+ 페이지) 처리
9. 동시 다중 업로드 처리
10. 메타데이터 (category, document_id, user_id) 저장 확인
```
```

---
