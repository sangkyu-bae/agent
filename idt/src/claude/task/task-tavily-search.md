# Task: Tavily 웹 검색 도구 (Tavily Web Search Tool)

> Task ID: SEARCH-001  
> 의존성: LOG-001  
> 최종 수정: 2025-01-31

---

## 1. 목적

- LangChain BaseTool 기반 웹 검색 도구 제공
- Tavily API를 활용한 실시간 웹 검색 수행
- RAG 파이프라인 및 Agent에서 외부 정보 조회 지원
- 검색 결과 포맷팅 및 컨텍스트 추출

---

## 2. 설계 원칙

### 2.1 아키텍처 레이어 배치

| 레이어 | 구성요소 | 역할 |
|--------|----------|------|
| domain | `WebSearchPolicy`, `SearchResult` | 검색 규칙, 결과 VO 정의 |
| application | `WebSearchUseCase` | 검색 오케스트레이션 |
| infrastructure | `TavilySearchTool` | Tavily API 연동, LangChain Tool |

### 2.2 의존성

- LOG-001 (로깅 필수)
- LangChain (`BaseTool`)
- Tavily Python SDK (`tavily-python`)

---

## 3. 도메인 설계

### 3.1 SearchResult (Value Object)

```python
# domain/web_search/value_objects.py
from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    """개별 검색 결과 VO"""
    
    title: str = Field(description="검색 결과 제목")
    url: str = Field(description="검색 결과 URL")
    content: str = Field(description="검색 결과 요약 내용")
    raw_content: str | None = Field(default=None, description="원본 콘텐츠")


class SearchResult(BaseModel):
    """검색 결과 집합 VO"""
    
    query: str = Field(description="검색 쿼리")
    results: list[SearchResultItem] = Field(default_factory=list)
    
    @property
    def result_count(self) -> int:
        return len(self.results)
    
    @property
    def is_empty(self) -> bool:
        return len(self.results) == 0
```

### 3.2 WebSearchPolicy (Domain Policy)

```python
# domain/web_search/policy.py

class WebSearchPolicy:
    """웹 검색 정책"""
    
    MIN_QUERY_LENGTH = 5
    MAX_QUERY_LENGTH = 500
    DEFAULT_MAX_RESULTS = 3
    MAX_RESULTS_LIMIT = 10
    
    @staticmethod
    def validate_query(query: str) -> bool:
        """검색 쿼리 유효성 검증"""
        if not query or not query.strip():
            return False
        
        stripped = query.strip()
        if len(stripped) < WebSearchPolicy.MIN_QUERY_LENGTH:
            return False
        if len(stripped) > WebSearchPolicy.MAX_QUERY_LENGTH:
            return False
        
        return True
    
    @staticmethod
    def validate_max_results(max_results: int) -> int:
        """최대 결과 수 검증 및 보정"""
        if max_results < 1:
            return WebSearchPolicy.DEFAULT_MAX_RESULTS
        if max_results > WebSearchPolicy.MAX_RESULTS_LIMIT:
            return WebSearchPolicy.MAX_RESULTS_LIMIT
        return max_results
```

---

## 4. 인프라스트럭처 설계

### 4.1 검색 결과 포맷터

```python
# infrastructure/web_search/formatter.py
import json


def format_search_result_to_xml(
    result: dict,
    include_raw_content: bool = False,
) -> str:
    """
    검색 결과를 XML 형식으로 포맷팅
    
    Args:
        result: 원본 검색 결과 dict
        include_raw_content: 원본 콘텐츠 포함 여부
        
    Returns:
        XML 형식 문자열
    """
    title = json.dumps(result["title"], ensure_ascii=False)[1:-1]
    content = json.dumps(result["content"], ensure_ascii=False)[1:-1]
    
    raw_content_xml = ""
    if (
        include_raw_content
        and "raw_content" in result
        and result["raw_content"] is not None
        and len(result["raw_content"].strip()) > 0
    ):
        raw_content_xml = f"<raw>{result['raw_content']}</raw>"
    
    return (
        f"<document>"
        f"<title>{title}</title>"
        f"<url>{result['url']}</url>"
        f"<content>{content}</content>"
        f"{raw_content_xml}"
        f"</document>"
    )
```

### 4.2 Input Schema

```python
# infrastructure/web_search/schemas.py
from pydantic import BaseModel, Field


class TavilySearchInput(BaseModel):
    """Tavily 검색 도구 입력 스키마"""
    
    query: str = Field(description="검색 쿼리")
```

### 4.3 TavilySearchTool 구현

```python
# infrastructure/web_search/tavily_tool.py
import json
import os
from typing import Literal, Sequence

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from tavily import TavilyClient

from domain.web_search.policy import WebSearchPolicy
from domain.web_search.value_objects import SearchResult, SearchResultItem
from infrastructure.web_search.formatter import format_search_result_to_xml
from infrastructure.web_search.schemas import TavilySearchInput
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class TavilySearchTool(BaseTool):
    """
    Tavily Search API 기반 웹 검색 도구
    
    LangChain BaseTool을 상속하여 Agent에서 사용 가능
    """
    
    name: str = "tavily_web_search"
    description: str = (
        "A search engine optimized for comprehensive, accurate, and trusted results. "
        "Useful for when you need to answer questions about current events. "
        "Input should be a search query. [IMPORTANT] Input(query) should be over 5 characters."
    )
    args_schema: type[BaseModel] = TavilySearchInput
    
    # Tavily 설정
    client: TavilyClient = None
    include_domains: list[str] = []
    exclude_domains: list[str] = []
    max_results: int = 3
    topic: Literal["general", "news"] = "general"
    days: int = 3
    search_depth: Literal["basic", "advanced"] = "basic"
    include_answer: bool = False
    include_raw_content: bool = True
    include_images: bool = False
    format_output: bool = False
    
    def __init__(
        self,
        api_key: str | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        max_results: int = 3,
        topic: Literal["general", "news"] = "general",
        days: int = 3,
        search_depth: Literal["basic", "advanced"] = "basic",
        include_answer: bool = False,
        include_raw_content: bool = True,
        include_images: bool = False,
        format_output: bool = False,
    ):
        """
        TavilySearchTool 초기화
        
        Args:
            api_key: Tavily API 키 (없으면 환경변수에서 조회)
            include_domains: 검색에 포함할 도메인 목록
            exclude_domains: 검색에서 제외할 도메인 목록
            max_results: 최대 검색 결과 수
            topic: 검색 주제 ("general" 또는 "news")
            days: 검색할 날짜 범위 (news 토픽에서만 유효)
            search_depth: 검색 깊이 ("basic" 또는 "advanced")
            include_answer: 답변 포함 여부
            include_raw_content: 원본 콘텐츠 포함 여부
            include_images: 이미지 포함 여부
            format_output: XML 포맷 출력 여부
            
        Raises:
            ValueError: API 키가 설정되지 않은 경우
        """
        super().__init__()
        
        resolved_api_key = api_key or os.environ.get("TAVILY_API_KEY")
        if not resolved_api_key:
            logger.error("Tavily API key is not configured")
            raise ValueError("Tavily API key is not set. Set TAVILY_API_KEY environment variable.")
        
        self.client = TavilyClient(api_key=resolved_api_key)
        self.include_domains = include_domains or []
        self.exclude_domains = exclude_domains or []
        self.max_results = WebSearchPolicy.validate_max_results(max_results)
        self.topic = topic
        self.days = days
        self.search_depth = search_depth
        self.include_answer = include_answer
        self.include_raw_content = include_raw_content
        self.include_images = include_images
        self.format_output = format_output
        
        logger.info(
            "TavilySearchTool initialized",
            extra={
                "max_results": self.max_results,
                "topic": self.topic,
                "search_depth": self.search_depth,
            }
        )
    
    def _run(self, query: str) -> str:
        """
        BaseTool의 동기 실행 메서드
        
        Args:
            query: 검색 쿼리
            
        Returns:
            검색 결과 (format_output에 따라 XML 또는 JSON)
        """
        results = self.search(query)
        return results
    
    async def _arun(self, query: str) -> str:
        """
        BaseTool의 비동기 실행 메서드
        
        Args:
            query: 검색 쿼리
            
        Returns:
            검색 결과
        """
        # Tavily SDK가 동기만 지원하므로 동기 메서드 호출
        return self._run(query)
    
    def search(
        self,
        query: str,
        request_id: str | None = None,
        search_depth: Literal["basic", "advanced"] | None = None,
        topic: Literal["general", "news"] | None = None,
        days: int | None = None,
        max_results: int | None = None,
        include_domains: Sequence[str] | None = None,
        exclude_domains: Sequence[str] | None = None,
        include_answer: bool | None = None,
        include_raw_content: bool | None = None,
        include_images: bool | None = None,
        format_output: bool | None = None,
    ) -> list[dict] | list[str]:
        """
        웹 검색 수행
        
        Args:
            query: 검색 쿼리
            request_id: 요청 추적 ID
            search_depth: 검색 깊이 ("basic" 또는 "advanced")
            topic: 검색 주제 ("general" 또는 "news")
            days: 검색할 날짜 범위
            max_results: 최대 검색 결과 수
            include_domains: 검색에 포함할 도메인 목록
            exclude_domains: 검색에서 제외할 도메인 목록
            include_answer: 답변 포함 여부
            include_raw_content: 원본 콘텐츠 포함 여부
            include_images: 이미지 포함 여부
            format_output: XML 포맷 출력 여부
            
        Returns:
            검색 결과 리스트
        """
        log_extra = {"request_id": request_id} if request_id else {}
        
        logger.info(
            "Web search started",
            extra={
                **log_extra,
                "query": query[:100],  # 쿼리 앞 100자만 로깅
                "query_length": len(query),
            }
        )
        
        # 파라미터 기본값 설정
        params = {
            "query": query,
            "search_depth": search_depth or self.search_depth,
            "topic": topic or self.topic,
            "max_results": WebSearchPolicy.validate_max_results(
                max_results or self.max_results
            ),
            "include_domains": list(include_domains or self.include_domains),
            "exclude_domains": list(exclude_domains or self.exclude_domains),
            "include_answer": (
                include_answer if include_answer is not None else self.include_answer
            ),
            "include_raw_content": (
                include_raw_content
                if include_raw_content is not None
                else self.include_raw_content
            ),
            "include_images": (
                include_images if include_images is not None else self.include_images
            ),
        }
        
        # days 파라미터 처리 (news 토픽에서만 유효)
        effective_days = days if days is not None else self.days
        if params["topic"] == "news":
            params["days"] = effective_days
        elif days is not None:
            logger.warning(
                "days parameter ignored for 'general' topic",
                extra=log_extra,
            )
        
        try:
            response = self.client.search(**params)
            results = response.get("results", [])
            
            logger.info(
                "Web search completed",
                extra={
                    **log_extra,
                    "result_count": len(results),
                }
            )
            
            # 포맷팅 여부 결정
            should_format = (
                format_output if format_output is not None else self.format_output
            )
            
            if should_format:
                return [
                    format_search_result_to_xml(r, params["include_raw_content"])
                    for r in results
                ]
            else:
                return results
                
        except Exception as e:
            logger.error(
                "Web search failed",
                extra=log_extra,
                exc_info=True,
            )
            raise
    
    def search_as_value_object(
        self,
        query: str,
        request_id: str | None = None,
        **kwargs,
    ) -> SearchResult:
        """
        검색 수행 후 VO로 반환
        
        Args:
            query: 검색 쿼리
            request_id: 요청 추적 ID
            **kwargs: search() 메서드에 전달할 추가 파라미터
            
        Returns:
            SearchResult VO
        """
        # format_output=False로 강제하여 dict 리스트 받기
        results = self.search(
            query=query,
            request_id=request_id,
            format_output=False,
            **kwargs,
        )
        
        items = [
            SearchResultItem(
                title=r["title"],
                url=r["url"],
                content=r["content"],
                raw_content=r.get("raw_content"),
            )
            for r in results
        ]
        
        return SearchResult(query=query, results=items)
    
    def get_search_context(
        self,
        query: str,
        request_id: str | None = None,
        search_depth: Literal["basic", "advanced"] = "basic",
        topic: Literal["general", "news"] = "general",
        days: int = 3,
        max_results: int = 5,
        include_domains: Sequence[str] | None = None,
        exclude_domains: Sequence[str] | None = None,
        max_tokens: int = 4000,
        format_output: bool = True,
    ) -> str:
        """
        RAG 컨텍스트용 검색 수행
        
        웹사이트에서 관련 콘텐츠만 추출하여 컨텍스트로 반환
        
        Args:
            query: 검색 쿼리
            request_id: 요청 추적 ID
            search_depth: 검색 깊이
            topic: 검색 주제
            days: 검색할 날짜 범위
            max_results: 최대 검색 결과 수
            include_domains: 검색에 포함할 도메인 목록
            exclude_domains: 검색에서 제외할 도메인 목록
            max_tokens: 반환할 최대 토큰 수 (예약, 현재 미구현)
            format_output: XML 포맷 출력 여부
            
        Returns:
            JSON 문자열 형태의 검색 컨텍스트
        """
        log_extra = {"request_id": request_id} if request_id else {}
        
        logger.info(
            "Search context retrieval started",
            extra={
                **log_extra,
                "query": query[:100],
                "max_results": max_results,
            }
        )
        
        try:
            response = self.client.search(
                query,
                search_depth=search_depth,
                topic=topic,
                days=days if topic == "news" else None,
                max_results=max_results,
                include_domains=list(include_domains or []),
                exclude_domains=list(exclude_domains or []),
                include_answer=False,
                include_raw_content=False,
                include_images=False,
            )
            
            sources = response.get("results", [])
            
            if format_output:
                context = [
                    format_search_result_to_xml(source, include_raw_content=False)
                    for source in sources
                ]
            else:
                context = [
                    {
                        "url": source["url"],
                        "content": json.dumps(
                            {"title": source["title"], "content": source["content"]},
                            ensure_ascii=False,
                        ),
                    }
                    for source in sources
                ]
            
            logger.info(
                "Search context retrieval completed",
                extra={
                    **log_extra,
                    "source_count": len(sources),
                }
            )
            
            # TODO: max_tokens 기반 truncation 구현
            return json.dumps(context, ensure_ascii=False)
            
        except Exception as e:
            logger.error(
                "Search context retrieval failed",
                extra=log_extra,
                exc_info=True,
            )
            raise
```

---

## 5. Application 설계

### 5.1 UseCase

```python
# application/web_search/use_case.py
from domain.web_search.policy import WebSearchPolicy
from domain.web_search.value_objects import SearchResult
from infrastructure.web_search.tavily_tool import TavilySearchTool
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class WebSearchUseCase:
    """웹 검색 유스케이스"""
    
    def __init__(self, search_tool: TavilySearchTool):
        self._search_tool = search_tool
    
    def search(
        self,
        query: str,
        request_id: str,
        max_results: int | None = None,
    ) -> SearchResult:
        """
        웹 검색 실행
        
        Args:
            query: 검색 쿼리
            request_id: 요청 추적 ID
            max_results: 최대 검색 결과 수
            
        Returns:
            SearchResult VO
            
        Raises:
            ValueError: 유효하지 않은 쿼리
        """
        if not WebSearchPolicy.validate_query(query):
            logger.warning(
                "Web search skipped: invalid query",
                extra={
                    "request_id": request_id,
                    "query_length": len(query) if query else 0,
                }
            )
            raise ValueError(
                f"Query must be between {WebSearchPolicy.MIN_QUERY_LENGTH} "
                f"and {WebSearchPolicy.MAX_QUERY_LENGTH} characters"
            )
        
        return self._search_tool.search_as_value_object(
            query=query.strip(),
            request_id=request_id,
            max_results=max_results,
        )
    
    def get_context(
        self,
        query: str,
        request_id: str,
        max_results: int = 5,
    ) -> str:
        """
        RAG 컨텍스트용 검색 실행
        
        Args:
            query: 검색 쿼리
            request_id: 요청 추적 ID
            max_results: 최대 검색 결과 수
            
        Returns:
            JSON 문자열 형태의 검색 컨텍스트
            
        Raises:
            ValueError: 유효하지 않은 쿼리
        """
        if not WebSearchPolicy.validate_query(query):
            logger.warning(
                "Context search skipped: invalid query",
                extra={
                    "request_id": request_id,
                    "query_length": len(query) if query else 0,
                }
            )
            raise ValueError(
                f"Query must be between {WebSearchPolicy.MIN_QUERY_LENGTH} "
                f"and {WebSearchPolicy.MAX_QUERY_LENGTH} characters"
            )
        
        return self._search_tool.get_search_context(
            query=query.strip(),
            request_id=request_id,
            max_results=max_results,
        )
```

---

## 6. 파일 구조

```
src/
├── domain/
│   └── web_search/
│       ├── __init__.py
│       ├── policy.py              # WebSearchPolicy
│       └── value_objects.py       # SearchResult, SearchResultItem
├── application/
│   └── web_search/
│       ├── __init__.py
│       └── use_case.py            # WebSearchUseCase
└── infrastructure/
    └── web_search/
        ├── __init__.py
        ├── formatter.py           # format_search_result_to_xml
        ├── schemas.py             # TavilySearchInput
        └── tavily_tool.py         # TavilySearchTool
```

---

## 7. 테스트 요구사항

### 7.1 Domain 테스트 (Mock 금지)

```python
# tests/domain/web_search/test_policy.py
import pytest
from domain.web_search.policy import WebSearchPolicy


class TestWebSearchPolicy:
    
    class TestValidateQuery:
        
        def test_returns_true_with_valid_query(self):
            # Given
            query = "최신 AI 기술 동향"
            
            # When
            result = WebSearchPolicy.validate_query(query)
            
            # Then
            assert result is True
        
        def test_returns_false_with_empty_query(self):
            # Given
            query = ""
            
            # When
            result = WebSearchPolicy.validate_query(query)
            
            # Then
            assert result is False
        
        def test_returns_false_with_none_query(self):
            # Given
            query = None
            
            # When
            result = WebSearchPolicy.validate_query(query)
            
            # Then
            assert result is False
        
        def test_returns_false_with_too_short_query(self):
            # Given
            query = "abcd"  # 4 characters < MIN_QUERY_LENGTH(5)
            
            # When
            result = WebSearchPolicy.validate_query(query)
            
            # Then
            assert result is False
        
        def test_returns_true_with_min_length_query(self):
            # Given
            query = "abcde"  # exactly MIN_QUERY_LENGTH
            
            # When
            result = WebSearchPolicy.validate_query(query)
            
            # Then
            assert result is True
        
        def test_returns_false_with_too_long_query(self):
            # Given
            query = "a" * 501  # > MAX_QUERY_LENGTH
            
            # When
            result = WebSearchPolicy.validate_query(query)
            
            # Then
            assert result is False
    
    class TestValidateMaxResults:
        
        def test_returns_same_value_when_valid(self):
            # Given
            max_results = 5
            
            # When
            result = WebSearchPolicy.validate_max_results(max_results)
            
            # Then
            assert result == 5
        
        def test_returns_default_when_less_than_one(self):
            # Given
            max_results = 0
            
            # When
            result = WebSearchPolicy.validate_max_results(max_results)
            
            # Then
            assert result == WebSearchPolicy.DEFAULT_MAX_RESULTS
        
        def test_returns_max_limit_when_exceeds(self):
            # Given
            max_results = 100
            
            # When
            result = WebSearchPolicy.validate_max_results(max_results)
            
            # Then
            assert result == WebSearchPolicy.MAX_RESULTS_LIMIT
```

### 7.2 Domain Value Object 테스트

```python
# tests/domain/web_search/test_value_objects.py
import pytest
from domain.web_search.value_objects import SearchResult, SearchResultItem


class TestSearchResult:
    
    def test_result_count_returns_correct_count(self):
        # Given
        items = [
            SearchResultItem(title="t1", url="u1", content="c1"),
            SearchResultItem(title="t2", url="u2", content="c2"),
        ]
        result = SearchResult(query="test", results=items)
        
        # When & Then
        assert result.result_count == 2
    
    def test_is_empty_returns_true_when_no_results(self):
        # Given
        result = SearchResult(query="test", results=[])
        
        # When & Then
        assert result.is_empty is True
    
    def test_is_empty_returns_false_when_has_results(self):
        # Given
        items = [SearchResultItem(title="t1", url="u1", content="c1")]
        result = SearchResult(query="test", results=items)
        
        # When & Then
        assert result.is_empty is False
```

### 7.3 Infrastructure 테스트 (Mock 사용)

```python
# tests/infrastructure/web_search/test_tavily_tool.py
import pytest
from unittest.mock import MagicMock, patch

from infrastructure.web_search.tavily_tool import TavilySearchTool


class TestTavilySearchTool:
    
    @pytest.fixture
    def mock_client(self):
        return MagicMock()
    
    @pytest.fixture
    def tool(self, mock_client):
        with patch("infrastructure.web_search.tavily_tool.TavilyClient") as mock_cls:
            mock_cls.return_value = mock_client
            tool = TavilySearchTool(api_key="test-api-key")
            return tool
    
    def test_init_raises_error_without_api_key(self):
        # Given & When & Then
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="API key is not set"):
                TavilySearchTool(api_key=None)
    
    def test_search_returns_results(self, tool, mock_client):
        # Given
        mock_client.search.return_value = {
            "results": [
                {"title": "Test", "url": "http://test.com", "content": "Content"}
            ]
        }
        
        # When
        results = tool.search("test query", request_id="req-123")
        
        # Then
        assert len(results) == 1
        assert results[0]["title"] == "Test"
    
    def test_search_with_format_output_returns_xml(self, tool, mock_client):
        # Given
        mock_client.search.return_value = {
            "results": [
                {"title": "Test", "url": "http://test.com", "content": "Content"}
            ]
        }
        
        # When
        results = tool.search("test query", request_id="req-123", format_output=True)
        
        # Then
        assert len(results) == 1
        assert "<document>" in results[0]
        assert "<title>Test</title>" in results[0]
    
    def test_search_as_value_object_returns_search_result(self, tool, mock_client):
        # Given
        mock_client.search.return_value = {
            "results": [
                {"title": "Test", "url": "http://test.com", "content": "Content"}
            ]
        }
        
        # When
        result = tool.search_as_value_object("test query", request_id="req-123")
        
        # Then
        assert result.query == "test query"
        assert result.result_count == 1
        assert result.results[0].title == "Test"
    
    def test_search_logs_warning_for_days_with_general_topic(self, tool, mock_client, caplog):
        # Given
        mock_client.search.return_value = {"results": []}
        
        # When
        tool.search("test query", topic="general", days=7)
        
        # Then
        # 로그에 warning이 기록되었는지 확인
        assert any("days parameter ignored" in record.message for record in caplog.records)
```

### 7.4 Application 테스트

```python
# tests/application/web_search/test_use_case.py
import pytest
from unittest.mock import MagicMock

from application.web_search.use_case import WebSearchUseCase
from domain.web_search.value_objects import SearchResult, SearchResultItem


class TestWebSearchUseCase:
    
    @pytest.fixture
    def mock_tool(self):
        return MagicMock()
    
    @pytest.fixture
    def use_case(self, mock_tool):
        return WebSearchUseCase(search_tool=mock_tool)
    
    def test_search_calls_tool_with_stripped_query(self, use_case, mock_tool):
        # Given
        query = "  테스트 쿼리입니다  "
        mock_tool.search_as_value_object.return_value = SearchResult(
            query="테스트 쿼리입니다",
            results=[SearchResultItem(title="t", url="u", content="c")]
        )
        
        # When
        result = use_case.search(query, "req-123")
        
        # Then
        mock_tool.search_as_value_object.assert_called_once_with(
            query="테스트 쿼리입니다",
            request_id="req-123",
            max_results=None,
        )
    
    def test_search_raises_value_error_with_short_query(self, use_case):
        # Given
        query = "abcd"  # < MIN_QUERY_LENGTH
        
        # When & Then
        with pytest.raises(ValueError):
            use_case.search(query, "req-123")
    
    def test_search_raises_value_error_with_empty_query(self, use_case):
        # Given
        query = ""
        
        # When & Then
        with pytest.raises(ValueError):
            use_case.search(query, "req-123")
    
    def test_get_context_returns_json_string(self, use_case, mock_tool):
        # Given
        mock_tool.get_search_context.return_value = '[{"url": "http://test.com"}]'
        
        # When
        result = use_case.get_context("테스트 쿼리입니다", "req-123")
        
        # Then
        assert '"url"' in result
```

---

## 8. 사용 예시

### 8.1 기본 사용

```python
from infrastructure.web_search.tavily_tool import TavilySearchTool

# Tool 생성
tool = TavilySearchTool(
    api_key="your-api-key",  # 또는 TAVILY_API_KEY 환경변수 사용
    max_results=5,
    topic="general",
)

# 검색 실행
results = tool.search(
    query="2024년 한국 경제 전망",
    request_id="req-123",
)

for r in results:
    print(f"Title: {r['title']}")
    print(f"URL: {r['url']}")
    print(f"Content: {r['content'][:100]}...")
    print("---")
```

### 8.2 UseCase를 통한 사용

```python
from application.web_search.use_case import WebSearchUseCase
from infrastructure.web_search.tavily_tool import TavilySearchTool

# 의존성 생성
tool = TavilySearchTool(max_results=5)
use_case = WebSearchUseCase(search_tool=tool)

# 검색 실행 (VO 반환)
result = use_case.search(
    query="최신 AI 기술 동향",
    request_id="req-abc-123",
)

print(f"Query: {result.query}")
print(f"Result count: {result.result_count}")

for item in result.results:
    print(f"- {item.title}: {item.url}")
```

### 8.3 LangChain Agent에서 사용

```python
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_openai import ChatOpenAI

from infrastructure.web_search.tavily_tool import TavilySearchTool

# Tool 생성
tavily_tool = TavilySearchTool(max_results=3)

# Agent 생성
llm = ChatOpenAI(model="gpt-4o-mini")
tools = [tavily_tool]

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools)

# 실행
response = agent_executor.invoke({
    "input": "오늘 주요 뉴스를 알려줘"
})
```

---

## 9. 설정값

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `api_key` | 환경변수 `TAVILY_API_KEY` | Tavily API 키 |
| `max_results` | `3` | 최대 검색 결과 수 |
| `topic` | `"general"` | 검색 주제 (`general` / `news`) |
| `search_depth` | `"basic"` | 검색 깊이 (`basic` / `advanced`) |
| `days` | `3` | 뉴스 검색 시 날짜 범위 |
| `include_raw_content` | `True` | 원본 콘텐츠 포함 여부 |
| `format_output` | `False` | XML 포맷 출력 여부 |

### Policy 상수

| 상수 | 값 | 설명 |
|------|-----|------|
| `MIN_QUERY_LENGTH` | `5` | 최소 쿼리 길이 |
| `MAX_QUERY_LENGTH` | `500` | 최대 쿼리 길이 |
| `DEFAULT_MAX_RESULTS` | `3` | 기본 검색 결과 수 |
| `MAX_RESULTS_LIMIT` | `10` | 최대 검색 결과 수 제한 |

---

## 10. 로깅 체크리스트 (LOG-001 준수)

- [x] `get_logger(__name__)` 사용
- [x] 주요 처리 시작/완료 INFO 로그
- [x] 예외 발생 시 ERROR 로그 + `exc_info=True` (스택 트레이스)
- [x] `request_id` 컨텍스트 전파 (`extra` dict 사용)
- [x] 민감 정보 마스킹 (API 키 로깅 안함)
- [x] 쿼리 로깅 시 길이 제한 (앞 100자만)

---

## 11. 금지 사항

- ❌ API 키 하드코딩 금지 (환경변수 또는 주입 사용)
- ❌ `print()` 사용 금지 (LOG-001 준수)
- ❌ 스택 트레이스 없는 에러 로그 금지
- ❌ `request_id` 없는 로그 금지 (API 컨텍스트 내)
- ❌ 검색 쿼리 전체 로깅 금지 (길이 제한 필요)

---

## 12. 의존성 패키지

```txt
langchain-core>=0.1.0
tavily-python>=0.3.0
pydantic>=2.0.0
```

---

## 13. CLAUDE.md Task Files Reference 추가

```markdown
| SEARCH-001 | task-tavily-search.md | Tavily 웹 검색 도구 |
```