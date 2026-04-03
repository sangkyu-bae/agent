# Task: 쿼리 재작성기 (Query Rewriter)

> Task ID: QUERY-001  
> 의존성: LOG-001  
> 최종 수정: 2025-01-31

---

## 1. 목적

- 사용자의 원본 질문을 벡터 검색/웹 검색에 최적화된 형태로 재작성
- 모호하거나 불완전한 질문을 명확하고 구체적인 쿼리로 변환
- 검색 품질 향상을 통한 RAG 성능 개선

---

## 2. 설계 원칙

### 2.1 아키텍처 레이어 배치

| 레이어 | 구성요소 | 역할 |
|--------|----------|------|
| domain | `QueryRewritePolicy`, `RewrittenQuery` | 재작성 규칙, 결과 VO 정의 |
| application | `QueryRewriterUseCase` | LangChain 호출 오케스트레이션 |
| infrastructure | `QueryRewriterAdapter` | LLM 호출, 프롬프트 실행 |

### 2.2 의존성

- LOG-001 (로깅 필수)
- LangChain (`ChatPromptTemplate`, `with_structured_output`)
- LangChain OpenAI (`ChatOpenAI`)

---

## 3. 도메인 설계

### 3.1 RewrittenQuery (Value Object)

```python
# domain/query_rewrite/value_objects.py
from pydantic import BaseModel, Field


class RewrittenQuery(BaseModel):
    """재작성된 쿼리 결과 VO"""
    
    original_query: str = Field(
        description="Original user query"
    )
    rewritten_query: str = Field(
        description="Rewritten query optimized for search"
    )
```

### 3.2 QueryRewritePolicy (Domain Policy)

```python
# domain/query_rewrite/policy.py

class QueryRewritePolicy:
    """쿼리 재작성 정책"""
    
    MIN_QUERY_LENGTH = 2
    MAX_QUERY_LENGTH = 1000
    
    @staticmethod
    def requires_rewrite(query: str) -> bool:
        """재작성이 필요한지 판단"""
        if not query or not query.strip():
            return False
        
        stripped = query.strip()
        if len(stripped) < QueryRewritePolicy.MIN_QUERY_LENGTH:
            return False
        if len(stripped) > QueryRewritePolicy.MAX_QUERY_LENGTH:
            return False
        
        return True
    
    @staticmethod
    def validate_rewritten_query(rewritten: str) -> bool:
        """재작성된 쿼리 유효성 검증"""
        if not rewritten or not rewritten.strip():
            return False
        return True
```

---

## 4. 인프라스트럭처 설계

### 4.1 System Prompt

```python
# infrastructure/query_rewrite/prompts.py

QUERY_REWRITE_SYSTEM_PROMPT = """You are a query rewriting specialist. Your task is to transform user questions into optimized search queries for vector database and web search.

## Objectives
1. Clarify ambiguous or vague questions
2. Expand abbreviations and acronyms when context is clear
3. Add relevant keywords that improve search recall
4. Remove unnecessary words (filler words, politeness phrases)
5. Preserve the original intent and meaning

## Guidelines
- Keep the rewritten query concise but comprehensive
- Use specific terminology when the intent is clear
- For Korean queries, maintain Korean language unless technical terms are better in English
- Do NOT add information that wasn't implied in the original query
- Do NOT change the fundamental meaning or scope of the question

## Examples
- "이거 어떻게 해?" → "방법 절차 단계별 가이드"
- "작년 실적 알려줘" → "2024년 연간 실적 매출 영업이익 재무제표"
- "금리 영향" → "금리 인상 인하 경제 영향 분석"
- "애플 주가" → "Apple AAPL 주가 현재가 시세"
"""


QUERY_REWRITE_HUMAN_TEMPLATE = """## Original Query
{query}

Rewrite this query to optimize for vector database and web search."""
```

### 4.2 LLM Output Schema

```python
# infrastructure/query_rewrite/schemas.py
from pydantic import BaseModel, Field


class QueryRewriteOutput(BaseModel):
    """LLM structured output 스키마"""
    
    rewritten_query: str = Field(
        description="Rewritten query optimized for search"
    )
```

### 4.3 Adapter 구현

```python
# infrastructure/query_rewrite/adapter.py
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from domain.query_rewrite.value_objects import RewrittenQuery
from infrastructure.query_rewrite.prompts import (
    QUERY_REWRITE_SYSTEM_PROMPT,
    QUERY_REWRITE_HUMAN_TEMPLATE,
)
from infrastructure.query_rewrite.schemas import QueryRewriteOutput
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class QueryRewriterAdapter:
    """쿼리 재작성 LLM Adapter"""
    
    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ):
        self._llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
        )
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", QUERY_REWRITE_SYSTEM_PROMPT),
            ("human", QUERY_REWRITE_HUMAN_TEMPLATE),
        ])
        self._chain = self._prompt | self._llm.with_structured_output(QueryRewriteOutput)
    
    async def rewrite(
        self,
        query: str,
        request_id: str,
    ) -> RewrittenQuery:
        """
        쿼리 재작성 수행
        
        Args:
            query: 사용자 원본 질문
            request_id: 요청 추적 ID
            
        Returns:
            RewrittenQuery
        """
        logger.info(
            "Query rewrite started",
            extra={
                "request_id": request_id,
                "original_query_length": len(query),
            }
        )
        
        try:
            result: QueryRewriteOutput = await self._chain.ainvoke({
                "query": query,
            })
            
            logger.info(
                "Query rewrite completed",
                extra={
                    "request_id": request_id,
                    "rewritten_query_length": len(result.rewritten_query),
                }
            )
            
            return RewrittenQuery(
                original_query=query,
                rewritten_query=result.rewritten_query,
            )
            
        except Exception as e:
            logger.error(
                "Query rewrite failed",
                extra={"request_id": request_id},
                exc_info=True,
            )
            raise
```

---

## 5. Application 설계

### 5.1 UseCase

```python
# application/query_rewrite/use_case.py
from domain.query_rewrite.policy import QueryRewritePolicy
from domain.query_rewrite.value_objects import RewrittenQuery
from infrastructure.query_rewrite.adapter import QueryRewriterAdapter
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class QueryRewriterUseCase:
    """쿼리 재작성 유스케이스"""
    
    def __init__(self, rewriter_adapter: QueryRewriterAdapter):
        self._rewriter = rewriter_adapter
    
    async def rewrite(
        self,
        query: str,
        request_id: str,
    ) -> RewrittenQuery:
        """
        쿼리 재작성 실행
        
        Args:
            query: 사용자 원본 질문
            request_id: 요청 추적 ID
            
        Returns:
            RewrittenQuery
            
        Raises:
            ValueError: 재작성 불가능한 입력
        """
        if not QueryRewritePolicy.requires_rewrite(query):
            logger.warning(
                "Query rewrite skipped: invalid input",
                extra={
                    "request_id": request_id,
                    "query_length": len(query) if query else 0,
                }
            )
            raise ValueError(
                f"Query must be between {QueryRewritePolicy.MIN_QUERY_LENGTH} "
                f"and {QueryRewritePolicy.MAX_QUERY_LENGTH} characters"
            )
        
        result = await self._rewriter.rewrite(
            query=query.strip(),
            request_id=request_id,
        )
        
        if not QueryRewritePolicy.validate_rewritten_query(result.rewritten_query):
            logger.error(
                "Query rewrite produced invalid result",
                extra={
                    "request_id": request_id,
                    "original_query": query,
                }
            )
            raise RuntimeError("Query rewrite produced empty result")
        
        return result
```

---

## 6. 파일 구조

```
src/
├── domain/
│   └── query_rewrite/
│       ├── __init__.py
│       ├── policy.py              # QueryRewritePolicy
│       └── value_objects.py       # RewrittenQuery
├── application/
│   └── query_rewrite/
│       ├── __init__.py
│       └── use_case.py            # QueryRewriterUseCase
└── infrastructure/
    └── query_rewrite/
        ├── __init__.py
        ├── prompts.py             # System/Human prompts
        ├── schemas.py             # QueryRewriteOutput (LLM 출력 스키마)
        └── adapter.py             # QueryRewriterAdapter
```

---

## 7. 테스트 요구사항

### 7.1 Domain 테스트 (Mock 금지)

```python
# tests/domain/query_rewrite/test_policy.py
import pytest
from domain.query_rewrite.policy import QueryRewritePolicy


class TestQueryRewritePolicy:
    
    class TestRequiresRewrite:
        
        def test_returns_true_with_valid_query(self):
            # Given
            query = "회사 실적 알려줘"
            
            # When
            result = QueryRewritePolicy.requires_rewrite(query)
            
            # Then
            assert result is True
        
        def test_returns_false_with_empty_query(self):
            # Given
            query = ""
            
            # When
            result = QueryRewritePolicy.requires_rewrite(query)
            
            # Then
            assert result is False
        
        def test_returns_false_with_none_query(self):
            # Given
            query = None
            
            # When
            result = QueryRewritePolicy.requires_rewrite(query)
            
            # Then
            assert result is False
        
        def test_returns_false_with_whitespace_only_query(self):
            # Given
            query = "   "
            
            # When
            result = QueryRewritePolicy.requires_rewrite(query)
            
            # Then
            assert result is False
        
        def test_returns_false_with_too_short_query(self):
            # Given
            query = "a"  # 1 character < MIN_QUERY_LENGTH
            
            # When
            result = QueryRewritePolicy.requires_rewrite(query)
            
            # Then
            assert result is False
        
        def test_returns_false_with_too_long_query(self):
            # Given
            query = "a" * 1001  # > MAX_QUERY_LENGTH
            
            # When
            result = QueryRewritePolicy.requires_rewrite(query)
            
            # Then
            assert result is False
        
        def test_returns_true_with_min_length_query(self):
            # Given
            query = "ab"  # exactly MIN_QUERY_LENGTH
            
            # When
            result = QueryRewritePolicy.requires_rewrite(query)
            
            # Then
            assert result is True
        
        def test_returns_true_with_max_length_query(self):
            # Given
            query = "a" * 1000  # exactly MAX_QUERY_LENGTH
            
            # When
            result = QueryRewritePolicy.requires_rewrite(query)
            
            # Then
            assert result is True
    
    class TestValidateRewrittenQuery:
        
        def test_returns_true_with_valid_rewritten_query(self):
            # Given
            rewritten = "2024년 회사 연간 실적 매출 영업이익"
            
            # When
            result = QueryRewritePolicy.validate_rewritten_query(rewritten)
            
            # Then
            assert result is True
        
        def test_returns_false_with_empty_rewritten_query(self):
            # Given
            rewritten = ""
            
            # When
            result = QueryRewritePolicy.validate_rewritten_query(rewritten)
            
            # Then
            assert result is False
        
        def test_returns_false_with_none_rewritten_query(self):
            # Given
            rewritten = None
            
            # When
            result = QueryRewritePolicy.validate_rewritten_query(rewritten)
            
            # Then
            assert result is False
        
        def test_returns_false_with_whitespace_only_rewritten_query(self):
            # Given
            rewritten = "   "
            
            # When
            result = QueryRewritePolicy.validate_rewritten_query(rewritten)
            
            # Then
            assert result is False
```

### 7.2 Infrastructure 테스트 (Mock 사용)

```python
# tests/infrastructure/query_rewrite/test_adapter.py
import pytest
from unittest.mock import AsyncMock, patch

from infrastructure.query_rewrite.adapter import QueryRewriterAdapter
from infrastructure.query_rewrite.schemas import QueryRewriteOutput


class TestQueryRewriterAdapter:
    
    @pytest.fixture
    def mock_chain(self):
        return AsyncMock()
    
    @pytest.fixture
    def adapter(self, mock_chain):
        adapter = QueryRewriterAdapter()
        adapter._chain = mock_chain
        return adapter
    
    @pytest.mark.asyncio
    async def test_rewrite_returns_rewritten_query(self, adapter, mock_chain):
        # Given
        query = "회사 실적 알려줘"
        mock_chain.ainvoke.return_value = QueryRewriteOutput(
            rewritten_query="2024년 회사 연간 실적 매출 영업이익 재무제표"
        )
        
        # When
        result = await adapter.rewrite(query, "req-123")
        
        # Then
        assert result.original_query == query
        assert result.rewritten_query == "2024년 회사 연간 실적 매출 영업이익 재무제표"
    
    @pytest.mark.asyncio
    async def test_rewrite_passes_query_to_chain(self, adapter, mock_chain):
        # Given
        query = "금리 영향"
        mock_chain.ainvoke.return_value = QueryRewriteOutput(
            rewritten_query="금리 인상 인하 경제 영향 분석"
        )
        
        # When
        await adapter.rewrite(query, "req-123")
        
        # Then
        call_args = mock_chain.ainvoke.call_args[0][0]
        assert call_args["query"] == query
    
    @pytest.mark.asyncio
    async def test_rewrite_raises_exception_on_llm_error(self, adapter, mock_chain):
        # Given
        query = "테스트 쿼리"
        mock_chain.ainvoke.side_effect = Exception("LLM API Error")
        
        # When & Then
        with pytest.raises(Exception, match="LLM API Error"):
            await adapter.rewrite(query, "req-123")
```

### 7.3 Application 테스트

```python
# tests/application/query_rewrite/test_use_case.py
import pytest
from unittest.mock import AsyncMock

from application.query_rewrite.use_case import QueryRewriterUseCase
from domain.query_rewrite.value_objects import RewrittenQuery


class TestQueryRewriterUseCase:
    
    @pytest.fixture
    def mock_adapter(self):
        return AsyncMock()
    
    @pytest.fixture
    def use_case(self, mock_adapter):
        return QueryRewriterUseCase(rewriter_adapter=mock_adapter)
    
    @pytest.mark.asyncio
    async def test_rewrite_calls_adapter_with_stripped_query(self, use_case, mock_adapter):
        # Given
        query = "  회사 실적 알려줘  "
        mock_adapter.rewrite.return_value = RewrittenQuery(
            original_query="회사 실적 알려줘",
            rewritten_query="2024년 회사 연간 실적"
        )
        
        # When
        result = await use_case.rewrite(query, "req-123")
        
        # Then
        mock_adapter.rewrite.assert_called_once_with(
            query="회사 실적 알려줘",
            request_id="req-123",
        )
        assert result.rewritten_query == "2024년 회사 연간 실적"
    
    @pytest.mark.asyncio
    async def test_rewrite_raises_value_error_with_empty_query(self, use_case):
        # Given
        query = ""
        
        # When & Then
        with pytest.raises(ValueError):
            await use_case.rewrite(query, "req-123")
    
    @pytest.mark.asyncio
    async def test_rewrite_raises_value_error_with_too_short_query(self, use_case):
        # Given
        query = "a"
        
        # When & Then
        with pytest.raises(ValueError):
            await use_case.rewrite(query, "req-123")
    
    @pytest.mark.asyncio
    async def test_rewrite_raises_value_error_with_too_long_query(self, use_case):
        # Given
        query = "a" * 1001
        
        # When & Then
        with pytest.raises(ValueError):
            await use_case.rewrite(query, "req-123")
    
    @pytest.mark.asyncio
    async def test_rewrite_raises_runtime_error_when_result_is_empty(
        self, use_case, mock_adapter
    ):
        # Given
        query = "회사 실적"
        mock_adapter.rewrite.return_value = RewrittenQuery(
            original_query=query,
            rewritten_query=""
        )
        
        # When & Then
        with pytest.raises(RuntimeError, match="empty result"):
            await use_case.rewrite(query, "req-123")
```

---

## 8. 사용 예시

```python
from application.query_rewrite.use_case import QueryRewriterUseCase
from infrastructure.query_rewrite.adapter import QueryRewriterAdapter


# Adapter 생성
adapter = QueryRewriterAdapter(
    model_name="gpt-4o-mini",
    temperature=0.0,
)

# UseCase 생성
use_case = QueryRewriterUseCase(rewriter_adapter=adapter)

# 쿼리 재작성 실행
original_query = "작년 실적 어때?"

result = await use_case.rewrite(
    query=original_query,
    request_id="req-abc-123",
)

print(f"Original: {result.original_query}")
print(f"Rewritten: {result.rewritten_query}")
# Original: 작년 실적 어때?
# Rewritten: 2024년 연간 실적 매출 영업이익 재무제표
```

---

## 9. 설정값

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `model_name` | `gpt-4o-mini` | 쿼리 재작성용 LLM 모델 |
| `temperature` | `0.0` | 일관된 출력을 위해 0 고정 |
| `MIN_QUERY_LENGTH` | `2` | 최소 쿼리 길이 |
| `MAX_QUERY_LENGTH` | `1000` | 최대 쿼리 길이 |

---

## 10. 로깅 체크리스트 (LOG-001 준수)

- [x] `get_logger(__name__)` 사용
- [x] 주요 처리 시작/완료 INFO 로그
- [x] 예외 발생 시 ERROR 로그 + `exc_info=True` (스택 트레이스)
- [x] `request_id` 컨텍스트 전파 (`extra` dict 사용)
- [x] 민감 정보 마스킹 해당 없음

---

## 11. 금지 사항

- ❌ `temperature > 0` 사용 금지 (일관된 재작성 필요)
- ❌ 원본 쿼리 의미 변경 금지
- ❌ 프롬프트에서 텍스트 파싱 금지 (`with_structured_output` 사용)
- ❌ 빈 쿼리 재작성 시도 금지
- ❌ `print()` 사용 금지 (LOG-001 준수)
- ❌ 스택 트레이스 없는 에러 로그 금지
- ❌ `request_id` 없는 로그 금지

---

## 12. 의존성 패키지

```txt
langchain-core>=0.1.0
langchain-openai>=0.1.0
pydantic>=2.0.0
```
