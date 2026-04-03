## 🎯 In Progress

### COMP-001: 문서 압축기 모듈 (LLM 기반 필터링)

- **상태**: 대기 중
- **목적**: LLM을 통해 질문과 관련 없는 문서 필터링, 병렬 처리 지원
- **기술 스택**: LangChain, OpenAI (확장 가능), asyncio
- **의존성**: RET-001 (리트리버에서 Document 리스트 받음)

---

#### 📦 1. 문서 압축기 추상화 (Domain Layer)

##### 1-1. DocumentCompressorInterface
- **목적**: LLM 기반 문서 압축기 교체 가능한 추상화
- **파일**: `src/domain/compressor/interfaces/document_compressor_interface.py`
- **메서드**:
  - [ ] compress(documents: List[Document], query: str) → List[Document]
  - [ ] compress_with_scores(documents: List[Document], query: str) → List[CompressedDocument]
  - [ ] get_compressor_name() → str
- **세부 태스크**:
  - [ ] ABC 추상 클래스 정의
  - [ ] 입출력 LangChain Document 타입
  - [ ] 비동기 메서드 정의

##### 1-2. LLMProviderInterface
- **목적**: LLM 프로바이더 교체 가능한 추상화 (OpenAI, Anthropic, Local 등)
- **파일**: `src/domain/compressor/interfaces/llm_provider_interface.py`
- **메서드**:
  - [ ] generate(prompt: str) → str
  - [ ] generate_batch(prompts: List[str]) → List[str]
  - [ ] generate_structured(prompt: str, schema: Type[BaseModel]) → BaseModel
  - [ ] get_provider_name() → str
  - [ ] get_model_name() → str
- **세부 태스크**:
  - [ ] ABC 추상 클래스 정의
  - [ ] 비동기 메서드 정의

---

#### 📄 2. Value Objects & Entities

##### 2-1. CompressedDocument Entity
- **목적**: 압축 결과 문서 표현 (관련성 점수 포함)
- **파일**: `src/domain/compressor/entities/compressed_document.py`
- **필드**:
  - [ ] document: Document (원본)
  - [ ] is_relevant: bool
  - [ ] relevance_score: float (0.0 ~ 1.0)
  - [ ] reasoning: Optional[str] (LLM 판단 이유)
  - [ ] compressed_content: Optional[str] (요약된 내용, 선택)
- **메서드**:
  - [ ] to_document() → Document (메타데이터에 점수 추가)
  - [ ] to_dict() → Dict[str, Any]

##### 2-2. CompressorConfig Value Object
- **파일**: `src/domain/compressor/value_objects/compressor_config.py`
- **필드**:
  - [ ] relevance_threshold: float (기본값: 0.5, 이 이상만 통과)
  - [ ] max_concurrency: int (병렬 처리 수, 기본값: 10)
  - [ ] timeout_seconds: float (개별 요청 타임아웃)
  - [ ] include_reasoning: bool (판단 이유 포함 여부)
  - [ ] compress_content: bool (내용 요약 여부)
  - [ ] retry_count: int (실패 시 재시도 횟수)

##### 2-3. LLMConfig Value Object
- **파일**: `src/domain/compressor/value_objects/llm_config.py`
- **필드**:
  - [ ] provider: str (openai, anthropic, local 등)
  - [ ] model_name: str (gpt-4o-mini, gpt-4o 등)
  - [ ] temperature: float (기본값: 0.0, 일관성 위해)
  - [ ] max_tokens: int
  - [ ] api_key: Optional[str] (환경변수 우선)

##### 2-4. RelevanceResult Value Object
- **목적**: LLM 응답 파싱 결과
- **파일**: `src/domain/compressor/value_objects/relevance_result.py`
- **필드**:
  - [ ] is_relevant: bool
  - [ ] score: float
  - [ ] reasoning: str
```python
# LLM 응답 스키마 (Pydantic)
class RelevanceResult(BaseModel):
    is_relevant: bool
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str
```

---

#### 🔧 3. LLM 프로바이더 구현체 (Infrastructure Layer)

##### 3-1. OpenAIProvider 구현체
- **목적**: OpenAI API 기반 LLM 호출
- **파일**: `src/infrastructure/compressor/providers/openai_provider.py`
- **세부 태스크**:
  - [ ] LLMProviderInterface 구현
  - [ ] AsyncOpenAI 클라이언트 사용
  - [ ] generate() 구현
  - [ ] generate_batch() 병렬 구현 (asyncio.gather)
  - [ ] generate_structured() 구현 (JSON mode / function calling)
  - [ ] 에러 핸들링 (rate limit, timeout)
  - [ ] 재시도 로직 (exponential backoff)
```python
# OpenAIProvider 예시
class OpenAIProvider(LLMProviderInterface):
    def __init__(self, config: LLMConfig):
        self._client = AsyncOpenAI(api_key=config.api_key)
        self._model = config.model_name
        self._temperature = config.temperature
    
    async def generate(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._temperature,
        )
        return response.choices[0].message.content
    
    async def generate_structured(
        self, 
        prompt: str, 
        schema: Type[BaseModel]
    ) -> BaseModel:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return schema.model_validate_json(response.choices[0].message.content)
```

##### 3-2. AnthropicProvider 구현체 (확장용)
- **파일**: `src/infrastructure/compressor/providers/anthropic_provider.py`
- **세부 태스크**:
  - [ ] LLMProviderInterface 구현
  - [ ] AsyncAnthropic 클라이언트 사용
  - [ ] (선택) 추후 구현

##### 3-3. LLMProviderFactory
- **파일**: `src/infrastructure/compressor/providers/llm_factory.py`
- **세부 태스크**:
  - [ ] ProviderType enum (OPENAI, ANTHROPIC, LOCAL)
  - [ ] create_provider(config: LLMConfig) → LLMProviderInterface
  - [ ] 환경변수 기반 기본 프로바이더 설정

---

#### 🎯 4. 문서 압축기 구현체 (Infrastructure Layer)

##### 4-1. LLMDocumentCompressor 구현체
- **목적**: LLM 기반 문서 관련성 필터링 (병렬 처리)
- **파일**: `src/infrastructure/compressor/llm_document_compressor.py`
- **주입받는 의존성**:
  - LLMProviderInterface
- **메서드 구현**:
  - [ ] compress(documents, query) → List[Document]
    - 병렬로 각 문서 관련성 판단
    - threshold 이상만 반환
  - [ ] compress_with_scores(documents, query) → List[CompressedDocument]
    - 점수 및 reasoning 포함 반환
  - [ ] _evaluate_relevance(document, query) → RelevanceResult
    - 단일 문서 관련성 평가
  - [ ] _build_prompt(document, query) → str
    - 관련성 판단 프롬프트 생성
```python
# LLMDocumentCompressor 핵심 로직
class LLMDocumentCompressor(DocumentCompressorInterface):
    def __init__(
        self,
        llm_provider: LLMProviderInterface,  # 주입
        config: CompressorConfig,
    ):
        self._llm = llm_provider
        self._config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
    
    async def compress(
        self,
        documents: List[Document],
        query: str,
    ) -> List[Document]:
        # 병렬 처리
        tasks = [
            self._evaluate_with_semaphore(doc, query)
            for doc in documents
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 관련 문서만 필터링
        relevant_docs = []
        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                continue  # 에러 시 스킵 또는 로깅
            if result.score >= self._config.relevance_threshold:
                relevant_docs.append(doc)
        
        return relevant_docs
    
    async def _evaluate_with_semaphore(
        self,
        document: Document,
        query: str,
    ) -> RelevanceResult:
        async with self._semaphore:  # 동시성 제한
            return await self._evaluate_relevance(document, query)
    
    async def _evaluate_relevance(
        self,
        document: Document,
        query: str,
    ) -> RelevanceResult:
        prompt = self._build_prompt(document, query)
        return await self._llm.generate_structured(prompt, RelevanceResult)
```

##### 4-2. 관련성 판단 프롬프트
- **파일**: `src/infrastructure/compressor/prompts/relevance_prompt.py`
- **세부 태스크**:
  - [ ] 프롬프트 템플릿 정의
  - [ ] 다국어 지원 (한국어/영어)
```python
RELEVANCE_PROMPT_TEMPLATE = """
당신은 문서 관련성을 판단하는 전문가입니다.

## 질문
{query}

## 문서
{document_content}

## 지시사항
위 문서가 질문에 답하는 데 관련이 있는지 판단하세요.

다음 JSON 형식으로만 응답하세요:
{{
    "is_relevant": true/false,
    "score": 0.0~1.0 사이의 관련성 점수,
    "reasoning": "판단 이유를 간단히 설명"
}}

## 판단 기준
- 1.0: 질문에 직접적으로 답할 수 있는 핵심 정보 포함
- 0.7~0.9: 질문과 관련된 유용한 정보 포함
- 0.4~0.6: 간접적으로 관련있으나 핵심 정보 부족
- 0.1~0.3: 거의 관련 없음
- 0.0: 전혀 관련 없음
"""
```

##### 4-3. BatchDocumentCompressor (대량 처리 최적화)
- **목적**: 대량 문서 배치 처리 최적화
- **파일**: `src/infrastructure/compressor/batch_document_compressor.py`
- **세부 태스크**:
  - [ ] 문서를 배치로 묶어 처리
  - [ ] 토큰 제한 고려한 배치 크기 조절
  - [ ] 프로그레스 콜백 지원

---

#### 🏭 5. Factory & Service

##### 5-1. DocumentCompressorFactory
- **파일**: `src/infrastructure/compressor/compressor_factory.py`
- **세부 태스크**:
  - [ ] CompressorType enum (LLM, BATCH)
  - [ ] create_compressor(compressor_type, llm_config, compressor_config) → DocumentCompressorInterface
  - [ ] 환경변수 기반 기본 설정

##### 5-2. CompressionService (Facade)
- **파일**: `src/domain/compressor/services/compression_service.py`
- **메서드**:
  - [ ] compress_documents(documents: List[Document], query: str, config: CompressorConfig) → CompressionResponse
  - [ ] compress_with_details(documents: List[Document], query: str) → DetailedCompressionResponse
  - [ ] get_relevance_scores(documents: List[Document], query: str) → List[float]
- **세부 태스크**:
  - [ ] 압축기 주입받아 실행
  - [ ] 로깅 및 통계 (필터링 전/후 문서 수, 소요 시간)

---

#### 📄 6. DTO / Schemas

##### 6-1. CompressionRequest DTO
- **파일**: `src/domain/compressor/schemas/compression_schema.py`
- **필드**:
  - [ ] documents: List[Document]
  - [ ] query: str
  - [ ] config: Optional[CompressorConfig]
  - [ ] llm_config: Optional[LLMConfig]

##### 6-2. CompressionResponse DTO
- **파일**: `src/domain/compressor/schemas/compression_schema.py`
- **필드**:
  - [ ] compressed_documents: List[Document]
  - [ ] original_count: int
  - [ ] filtered_count: int
  - [ ] compression_ratio: float (filtered / original)
  - [ ] processing_time_ms: int
  - [ ] llm_provider: str
  - [ ] model_used: str

##### 6-3. DetailedCompressionResponse DTO
- **파일**: `src/domain/compressor/schemas/compression_schema.py`
- **필드**:
  - [ ] results: List[CompressedDocument]
  - [ ] relevant_documents: List[Document]
  - [ ] irrelevant_documents: List[Document]
  - [ ] average_score: float
  - [ ] score_distribution: Dict[str, int] (0.0-0.2: N개, 0.2-0.4: N개, ...)

---

#### 📁 예상 폴더 구조
```
src/
├── domain/
│   └── compressor/
│       ├── __init__.py
│       ├── interfaces/
│       │   ├── __init__.py
│       │   ├── document_compressor_interface.py
│       │   └── llm_provider_interface.py
│       ├── entities/
│       │   ├── __init__.py
│       │   └── compressed_document.py
│       ├── value_objects/
│       │   ├── __init__.py
│       │   ├── compressor_config.py
│       │   ├── llm_config.py
│       │   └── relevance_result.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── compression_schema.py
│       └── services/
│           ├── __init__.py
│           └── compression_service.py
│
└── infrastructure/
    └── compressor/
        ├── __init__.py
        ├── llm_document_compressor.py
        ├── batch_document_compressor.py
        ├── compressor_factory.py
        ├── providers/
        │   ├── __init__.py
        │   ├── openai_provider.py
        │   ├── anthropic_provider.py
        │   └── llm_factory.py
        └── prompts/
            ├── __init__.py
            └── relevance_prompt.py
```

---

#### 🔗 7. 병렬 처리 다이어그램
```
┌─────────────────────────────────────────────────────────────────┐
│                    compress(documents, query)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Semaphore (max_concurrency=10)                   │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   Doc 1       │     │   Doc 2       │     │   Doc 3       │
│   evaluate()  │     │   evaluate()  │     │   evaluate()  │
│      ↓        │     │      ↓        │     │      ↓        │
│   LLM Call    │     │   LLM Call    │     │   LLM Call    │
│   (async)     │     │   (async)     │     │   (async)     │
└───────────────┘     └───────────────┘     └───────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              asyncio.gather(*tasks)                              │
│              → [Result1, Result2, Result3, ...]                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│         Filter by threshold (score >= 0.5)                       │
│         → [Doc1, Doc3] (relevant only)                           │
└─────────────────────────────────────────────────────────────────┘
```

---

#### 🔗 8. 사용 예시
```python
# 1. 기본 사용
llm_config = LLMConfig(
    provider="openai",
    model_name="gpt-4o-mini",
    temperature=0.0,
)
compressor_config = CompressorConfig(
    relevance_threshold=0.5,
    max_concurrency=10,
)

llm_provider = OpenAIProvider(llm_config)
compressor = LLMDocumentCompressor(llm_provider, compressor_config)

# 리트리버에서 받은 문서들
documents = await retriever.retrieve("매출 현황", top_k=20)

# 압축 (관련 문서만 필터링)
relevant_docs = await compressor.compress(
    documents=documents,
    query="2024년 1분기 매출은 얼마인가요?",
)
# 20개 → 5개로 압축

# 2. 상세 결과 포함
results = await compressor.compress_with_scores(
    documents=documents,
    query="2024년 1분기 매출은 얼마인가요?",
)

for result in results:
    print(f"Score: {result.relevance_score}")
    print(f"Relevant: {result.is_relevant}")
    print(f"Reason: {result.reasoning}")
    print(f"Content: {result.document.page_content[:100]}...")

# 3. Service 통해 사용
compression_service = CompressionService(compressor)
response = await compression_service.compress_documents(
    documents=documents,
    query="매출 현황",
    config=compressor_config,
)
print(f"원본: {response.original_count}개")
print(f"필터링 후: {response.filtered_count}개")
print(f"압축률: {response.compression_ratio:.1%}")
print(f"소요 시간: {response.processing_time_ms}ms")
```

---

#### ✅ 완료 조건

- [ ] OpenAIProvider 단일 호출 테스트
- [ ] OpenAIProvider 구조화 응답 (JSON) 테스트
- [ ] LLMDocumentCompressor 병렬 처리 테스트
- [ ] Semaphore 동시성 제한 테스트 (max_concurrency)
- [ ] relevance_threshold 필터링 테스트
- [ ] 에러 핸들링 테스트 (timeout, rate limit)
- [ ] 재시도 로직 테스트
- [ ] RET-001 리트리버 연동 통합 테스트
- [ ] 대량 문서 (50개+) 병렬 처리 성능 테스트

---

#### 📝 메모

- openai>=1.0.0, anthropic>=0.18.0 의존성 추가
- 병렬 처리 시 OpenAI rate limit 주의 (max_concurrency 조절)
- gpt-4o-mini 권장 (비용 효율 + 충분한 성능)
- 추후 COMP-002에서 내용 요약 기능 추가 가능
- Reranker (Cohere, Cross-Encoder)와 조합하여 사용 가능

---

#### 🧪 테스트 시나리오
```python
# 테스트 케이스
1. 단일 문서 관련성 평가 (관련 있음)
2. 단일 문서 관련성 평가 (관련 없음)
3. 다중 문서 병렬 처리 (5개)
4. 대량 문서 병렬 처리 (50개)
5. threshold 경계값 테스트 (0.5 정확히)
6. max_concurrency 제한 테스트
7. timeout 발생 시 처리
8. API 에러 시 재시도
9. 모든 문서 관련 없음 → 빈 리스트 반환
10. 빈 문서 리스트 입력 처리
11. LLM 프로바이더 교체 테스트 (OpenAI → Anthropic)
```
```
