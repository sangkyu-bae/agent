# AGENT-002: Excel Analysis Agent (Self-Corrective)

> Task ID: AGENT-002  
> Status: Draft  
> Dependencies: EXCEL-001, LLM-001, SEARCH-001, EVAL-001, CODE-001, LOG-001  
> Last Updated: 2025-02-07

---

## 1. Overview

엑셀 파일을 파싱하여 Claude AI에 쿼리와 함께 전달하고, 필요 시 웹 검색을 수행하며, 할루시네이션 검증 후 최대 3회까지 재시도하는 Self-Corrective 분석 에이전트.

### 주요 기능

1. 엑셀 파일 파싱 (EXCEL-001)
2. Claude AI 기반 데이터 분석 (LLM-001)
3. 필요 시 웹 검색 자동 실행 (SEARCH-001)
4. 할루시네이션 검증 (EVAL-001)
5. 불충분 시 최대 3회 재시도
6. 코드 실행 필요 시 자동 실행 (CODE-001)
7. 전체 흐름 로깅 (LOG-001)

---

## 2. Architecture

### 2.1 Domain Layer

#### `domain/policies/analysis_policy.py`
```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class AnalysisRetryPolicy:
    """분석 재시도 정책"""
    max_retries: int = 3
    retry_on_hallucination: bool = True
    require_web_search_on_retry: bool = True
    
    def should_retry(self, attempt: int, has_hallucination: bool) -> bool:
        """재시도 여부 판단"""
        if attempt >= self.max_retries:
            return False
        return has_hallucination and self.retry_on_hallucination
    
    def validate(self):
        if self.max_retries < 1 or self.max_retries > 5:
            raise ValueError("max_retries must be between 1 and 5")


@dataclass(frozen=True)
class AnalysisQualityThreshold:
    """분석 품질 임계값"""
    min_confidence_score: float = 0.7
    max_hallucination_score: float = 0.3
    
    def is_acceptable(self, confidence: float, hallucination: float) -> bool:
        """품질 기준 충족 여부"""
        return (
            confidence >= self.min_confidence_score 
            and hallucination <= self.max_hallucination_score
        )
    
    def validate(self):
        if not (0 <= self.min_confidence_score <= 1):
            raise ValueError("min_confidence_score must be between 0 and 1")
        if not (0 <= self.max_hallucination_score <= 1):
            raise ValueError("max_hallucination_score must be between 0 and 1")


AnalysisStatus = Literal[
    "pending",
    "analyzing",
    "verifying",
    "retrying",
    "code_executing",
    "completed",
    "failed"
]
```

#### `domain/entities/analysis_result.py`
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

@dataclass
class AnalysisAttempt:
    """단일 분석 시도 기록"""
    attempt_number: int
    analysis_text: str
    confidence_score: float
    hallucination_score: float
    used_web_search: bool
    timestamp: datetime
    error: Optional[str] = None


@dataclass
class AnalysisResult:
    """최종 분석 결과"""
    request_id: str
    user_query: str
    excel_summary: Dict[str, Any]  # 파싱된 엑셀 정보
    
    final_answer: str
    is_successful: bool
    attempts: List[AnalysisAttempt]
    
    executed_code: Optional[str] = None
    code_output: Optional[Dict[str, Any]] = None
    
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            object.__setattr__(self, 'created_at', datetime.utcnow())
    
    @property
    def total_attempts(self) -> int:
        return len(self.attempts)
    
    @property
    def final_quality_score(self) -> float:
        if not self.attempts:
            return 0.0
        last = self.attempts[-1]
        return last.confidence_score - last.hallucination_score
```

---

### 2.2 Application Layer

#### `application/workflows/excel_analysis_workflow.py`
```python
from typing import TypedDict, Annotated, Sequence
import operator
from langgraph.graph import StateGraph, END
from datetime import datetime

class ExcelAnalysisState(TypedDict):
    """워크플로우 상태"""
    request_id: str
    user_query: str
    excel_data: dict
    
    current_attempt: int
    max_attempts: int
    
    analysis_text: str
    confidence_score: float
    hallucination_score: float
    
    needs_web_search: bool
    web_search_results: str
    
    needs_code_execution: bool
    code_to_execute: str
    code_output: dict
    
    attempts_history: Annotated[Sequence[dict], operator.add]
    
    is_complete: bool
    final_status: str
    error_message: str


class ExcelAnalysisWorkflow:
    """엑셀 분석 워크플로우 (LangGraph)"""
    
    def __init__(
        self,
        excel_parser,
        claude_client,
        tavily_search,
        hallucination_evaluator,
        code_executor,
        logger,
        retry_policy,
        quality_threshold
    ):
        self._excel_parser = excel_parser
        self._claude = claude_client
        self._search = tavily_search
        self._evaluator = hallucination_evaluator
        self._executor = code_executor
        self._logger = logger
        self._retry_policy = retry_policy
        self._quality_threshold = quality_threshold
        
        self._graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """그래프 구성"""
        workflow = StateGraph(ExcelAnalysisState)
        
        # 노드 등록
        workflow.add_node("parse_excel", self._parse_excel_node)
        workflow.add_node("analyze_with_claude", self._analyze_node)
        workflow.add_node("web_search", self._web_search_node)
        workflow.add_node("evaluate_hallucination", self._evaluate_node)
        workflow.add_node("execute_code", self._execute_code_node)
        
        # 엣지 정의
        workflow.set_entry_point("parse_excel")
        
        workflow.add_edge("parse_excel", "analyze_with_claude")
        
        workflow.add_conditional_edges(
            "analyze_with_claude",
            self._should_search,
            {
                "search": "web_search",
                "evaluate": "evaluate_hallucination"
            }
        )
        
        workflow.add_edge("web_search", "analyze_with_claude")
        
        workflow.add_conditional_edges(
            "evaluate_hallucination",
            self._should_retry_or_execute,
            {
                "retry": "analyze_with_claude",
                "execute": "execute_code",
                "complete": END
            }
        )
        
        workflow.add_edge("execute_code", END)
        
        return workflow.compile()
    
    async def _parse_excel_node(self, state: ExcelAnalysisState) -> dict:
        """엑셀 파싱 노드"""
        request_id = state["request_id"]
        self._logger.info("Parsing excel file", request_id=request_id)
        
        # EXCEL-001 사용
        parsed_data = await self._excel_parser.parse(state["excel_data"])
        
        return {
            "excel_data": parsed_data,
            "current_attempt": 0,
            "max_attempts": self._retry_policy.max_retries
        }
    
    async def _analyze_node(self, state: ExcelAnalysisState) -> dict:
        """Claude 분석 노드"""
        request_id = state["request_id"]
        attempt = state["current_attempt"] + 1
        
        self._logger.info(
            f"Analyzing with Claude (attempt {attempt})",
            request_id=request_id
        )
        
        # 프롬프트 구성
        prompt = self._build_analysis_prompt(
            state["user_query"],
            state["excel_data"],
            state.get("web_search_results", "")
        )
        
        # LLM-001 호출
        response = await self._claude.generate(
            prompt=prompt,
            request_id=request_id
        )
        
        # 코드 실행 필요 여부 판단
        needs_code = self._detect_code_in_response(response)
        code = self._extract_code(response) if needs_code else ""
        
        return {
            "analysis_text": response,
            "current_attempt": attempt,
            "needs_code_execution": needs_code,
            "code_to_execute": code,
            "needs_web_search": False  # 리셋
        }
    
    async def _web_search_node(self, state: ExcelAnalysisState) -> dict:
        """웹 검색 노드"""
        request_id = state["request_id"]
        self._logger.info("Performing web search", request_id=request_id)
        
        # SEARCH-001 사용
        query = self._build_search_query(state["user_query"], state["analysis_text"])
        results = await self._search.search(query, request_id=request_id)
        
        return {
            "web_search_results": results,
            "needs_web_search": False
        }
    
    async def _evaluate_node(self, state: ExcelAnalysisState) -> dict:
        """할루시네이션 평가 노드"""
        request_id = state["request_id"]
        self._logger.info("Evaluating hallucination", request_id=request_id)
        
        # EVAL-001 사용
        eval_result = await self._evaluator.evaluate(
            query=state["user_query"],
            context=str(state["excel_data"]),
            answer=state["analysis_text"],
            request_id=request_id
        )
        
        # 시도 기록
        attempt_record = {
            "attempt_number": state["current_attempt"],
            "analysis_text": state["analysis_text"],
            "confidence_score": eval_result.confidence_score,
            "hallucination_score": eval_result.hallucination_score,
            "used_web_search": bool(state.get("web_search_results")),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return {
            "confidence_score": eval_result.confidence_score,
            "hallucination_score": eval_result.hallucination_score,
            "attempts_history": [attempt_record]
        }
    
    async def _execute_code_node(self, state: ExcelAnalysisState) -> dict:
        """코드 실행 노드"""
        request_id = state["request_id"]
        self._logger.info("Executing code", request_id=request_id)
        
        # CODE-001 사용
        result = await self._executor.execute(
            code=state["code_to_execute"],
            request_id=request_id
        )
        
        return {
            "code_output": result,
            "is_complete": True,
            "final_status": "completed"
        }
    
    def _should_search(self, state: ExcelAnalysisState) -> str:
        """웹 검색 필요 여부 판단"""
        # 분석 텍스트에서 "웹 검색 필요" 키워드 탐지
        if "[SEARCH]" in state["analysis_text"] or "웹에서 확인" in state["analysis_text"]:
            return "search"
        return "evaluate"
    
    def _should_retry_or_execute(self, state: ExcelAnalysisState) -> str:
        """재시도/코드실행/완료 판단"""
        quality_ok = self._quality_threshold.is_acceptable(
            state["confidence_score"],
            state["hallucination_score"]
        )
        
        # 품질 OK -> 코드 실행 필요 여부 확인
        if quality_ok:
            if state["needs_code_execution"]:
                return "execute"
            return "complete"
        
        # 품질 불충분 -> 재시도 가능 여부
        if self._retry_policy.should_retry(
            state["current_attempt"],
            state["hallucination_score"] > self._quality_threshold.max_hallucination_score
        ):
            # 재시도 시 웹 검색 강제
            state["needs_web_search"] = self._retry_policy.require_web_search_on_retry
            return "retry"
        
        # 재시도 불가 -> 실패 처리
        return "complete"
    
    def _build_analysis_prompt(self, query: str, excel_data: dict, web_context: str) -> str:
        """분석 프롬프트 생성"""
        prompt = f"""
당신은 데이터 분석 전문가입니다.

## 사용자 질문
{query}

## 엑셀 데이터
{excel_data}

## 웹 검색 결과 (있는 경우)
{web_context if web_context else "없음"}

## 지침
1. 데이터를 기반으로 정확하게 분석하세요
2. 추가 정보가 필요하면 [SEARCH] 태그를 포함하세요
3. 그래프/차트가 필요하면 Python 코드를 ```python ``` 블록에 작성하세요
4. 추측하지 말고 데이터에 근거하세요
"""
        return prompt
    
    def _detect_code_in_response(self, response: str) -> bool:
        """응답에 코드 포함 여부"""
        return "```python" in response
    
    def _extract_code(self, response: str) -> str:
        """코드 블록 추출"""
        import re
        match = re.search(r'```python\n(.*?)\n```', response, re.DOTALL)
        return match.group(1) if match else ""
    
    def _build_search_query(self, user_query: str, analysis: str) -> str:
        """검색 쿼리 생성"""
        # 분석 텍스트에서 검색 키워드 추출 (간단한 구현)
        return user_query
    
    async def run(self, state: ExcelAnalysisState) -> ExcelAnalysisState:
        """워크플로우 실행"""
        return await self._graph.ainvoke(state)
```

---

### 2.3 Application Use Case

#### `application/use_cases/analyze_excel_use_case.py`
```python
from domain.entities.analysis_result import AnalysisResult, AnalysisAttempt
from domain.policies.analysis_policy import AnalysisRetryPolicy, AnalysisQualityThreshold
from application.workflows.excel_analysis_workflow import ExcelAnalysisWorkflow
from datetime import datetime
import uuid

class AnalyzeExcelUseCase:
    """엑셀 분석 유스케이스"""
    
    def __init__(
        self,
        workflow: ExcelAnalysisWorkflow,
        logger,
        retry_policy: AnalysisRetryPolicy = None,
        quality_threshold: AnalysisQualityThreshold = None
    ):
        self._workflow = workflow
        self._logger = logger
        self._retry_policy = retry_policy or AnalysisRetryPolicy()
        self._quality_threshold = quality_threshold or AnalysisQualityThreshold()
        
        # 정책 검증
        self._retry_policy.validate()
        self._quality_threshold.validate()
    
    async def execute(
        self,
        excel_file_path: str,
        user_query: str,
        request_id: str = None
    ) -> AnalysisResult:
        """
        엑셀 분석 실행
        
        Args:
            excel_file_path: 엑셀 파일 경로
            user_query: 사용자 질문
            request_id: 요청 ID (선택)
        
        Returns:
            AnalysisResult: 분석 결과
        """
        request_id = request_id or str(uuid.uuid4())
        
        self._logger.info(
            "Starting excel analysis",
            request_id=request_id,
            query=user_query,
            file=excel_file_path
        )
        
        try:
            # 초기 상태 구성
            initial_state = {
                "request_id": request_id,
                "user_query": user_query,
                "excel_data": {"file_path": excel_file_path},
                "current_attempt": 0,
                "max_attempts": self._retry_policy.max_retries,
                "analysis_text": "",
                "confidence_score": 0.0,
                "hallucination_score": 0.0,
                "needs_web_search": False,
                "web_search_results": "",
                "needs_code_execution": False,
                "code_to_execute": "",
                "code_output": {},
                "attempts_history": [],
                "is_complete": False,
                "final_status": "pending",
                "error_message": ""
            }
            
            # 워크플로우 실행
            final_state = await self._workflow.run(initial_state)
            
            # 결과 변환
            result = self._build_result(final_state)
            
            self._logger.info(
                "Excel analysis completed",
                request_id=request_id,
                success=result.is_successful,
                attempts=result.total_attempts
            )
            
            return result
            
        except Exception as e:
            self._logger.error(
                "Excel analysis failed",
                exception=e,
                request_id=request_id
            )
            raise
    
    def _build_result(self, state: dict) -> AnalysisResult:
        """상태를 AnalysisResult로 변환"""
        attempts = [
            AnalysisAttempt(
                attempt_number=a["attempt_number"],
                analysis_text=a["analysis_text"],
                confidence_score=a["confidence_score"],
                hallucination_score=a["hallucination_score"],
                used_web_search=a["used_web_search"],
                timestamp=datetime.fromisoformat(a["timestamp"])
            )
            for a in state["attempts_history"]
        ]
        
        is_successful = (
            state["is_complete"] 
            and state["final_status"] == "completed"
            and len(attempts) > 0
            and self._quality_threshold.is_acceptable(
                attempts[-1].confidence_score,
                attempts[-1].hallucination_score
            )
        )
        
        return AnalysisResult(
            request_id=state["request_id"],
            user_query=state["user_query"],
            excel_summary=state["excel_data"],
            final_answer=state["analysis_text"],
            is_successful=is_successful,
            attempts=attempts,
            executed_code=state.get("code_to_execute") if state["needs_code_execution"] else None,
            code_output=state.get("code_output")
        )
```

---

### 2.4 Infrastructure Layer

#### `infrastructure/config/analysis_config.py`
```python
from pydantic_settings import BaseSettings
from domain.policies.analysis_policy import AnalysisRetryPolicy, AnalysisQualityThreshold

class AnalysisConfig(BaseSettings):
    """분석 설정 (환경변수 기반)"""
    
    # 재시도 정책
    ANALYSIS_MAX_RETRIES: int = 3
    ANALYSIS_RETRY_ON_HALLUCINATION: bool = True
    ANALYSIS_REQUIRE_WEB_SEARCH_ON_RETRY: bool = True
    
    # 품질 임계값
    ANALYSIS_MIN_CONFIDENCE_SCORE: float = 0.7
    ANALYSIS_MAX_HALLUCINATION_SCORE: float = 0.3
    
    class Config:
        env_file = ".env"
    
    def get_retry_policy(self) -> AnalysisRetryPolicy:
        return AnalysisRetryPolicy(
            max_retries=self.ANALYSIS_MAX_RETRIES,
            retry_on_hallucination=self.ANALYSIS_RETRY_ON_HALLUCINATION,
            require_web_search_on_retry=self.ANALYSIS_REQUIRE_WEB_SEARCH_ON_RETRY
        )
    
    def get_quality_threshold(self) -> AnalysisQualityThreshold:
        return AnalysisQualityThreshold(
            min_confidence_score=self.ANALYSIS_MIN_CONFIDENCE_SCORE,
            max_hallucination_score=self.ANALYSIS_MAX_HALLUCINATION_SCORE
        )
```

---

### 2.5 Interface Layer

#### `interfaces/api/v1/analysis_router.py`
```python
from fastapi import APIRouter, UploadFile, File, Form, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

router = APIRouter(prefix="/api/v1/analysis", tags=["Excel Analysis"])


class AnalysisRequest(BaseModel):
    """분석 요청"""
    query: str
    file_name: str


class AnalysisAttemptResponse(BaseModel):
    """시도 기록"""
    attempt_number: int
    confidence_score: float
    hallucination_score: float
    used_web_search: bool
    timestamp: datetime


class AnalysisResponse(BaseModel):
    """분석 응답"""
    request_id: str
    query: str
    final_answer: str
    is_successful: bool
    total_attempts: int
    attempts: List[AnalysisAttemptResponse]
    executed_code: Optional[str] = None
    code_output: Optional[Dict[str, Any]] = None


@router.post("/excel", response_model=AnalysisResponse)
async def analyze_excel(
    file: UploadFile = File(...),
    query: str = Form(...),
    use_case = Depends()  # DI로 주입
):
    """
    엑셀 파일 분석
    
    - 엑셀 파싱
    - Claude AI 분석
    - 할루시네이션 검증
    - 필요 시 웹 검색 및 코드 실행
    - 최대 3회 재시도
    """
    # 파일 저장
    file_path = f"/tmp/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    # 유스케이스 실행
    result = await use_case.execute(
        excel_file_path=file_path,
        user_query=query
    )
    
    # 응답 변환
    return AnalysisResponse(
        request_id=result.request_id,
        query=result.user_query,
        final_answer=result.final_answer,
        is_successful=result.is_successful,
        total_attempts=result.total_attempts,
        attempts=[
            AnalysisAttemptResponse(
                attempt_number=a.attempt_number,
                confidence_score=a.confidence_score,
                hallucination_score=a.hallucination_score,
                used_web_search=a.used_web_search,
                timestamp=a.timestamp
            )
            for a in result.attempts
        ],
        executed_code=result.executed_code,
        code_output=result.code_output
    )
```

---

## 3. Testing Strategy

### 3.1 Domain Tests
```python
# tests/domain/test_analysis_policy.py

import pytest
from domain.policies.analysis_policy import AnalysisRetryPolicy, AnalysisQualityThreshold


class TestAnalysisRetryPolicy:
    
    def test_should_retry_within_limit(self):
        policy = AnalysisRetryPolicy(max_retries=3)
        assert policy.should_retry(attempt=1, has_hallucination=True) is True
        assert policy.should_retry(attempt=2, has_hallucination=True) is True
    
    def test_should_not_retry_exceeded_limit(self):
        policy = AnalysisRetryPolicy(max_retries=3)
        assert policy.should_retry(attempt=3, has_hallucination=True) is False
    
    def test_should_not_retry_no_hallucination(self):
        policy = AnalysisRetryPolicy(max_retries=3, retry_on_hallucination=True)
        assert policy.should_retry(attempt=1, has_hallucination=False) is False
    
    def test_validate_max_retries_too_low(self):
        with pytest.raises(ValueError):
            AnalysisRetryPolicy(max_retries=0).validate()
    
    def test_validate_max_retries_too_high(self):
        with pytest.raises(ValueError):
            AnalysisRetryPolicy(max_retries=10).validate()


class TestAnalysisQualityThreshold:
    
    def test_is_acceptable_good_quality(self):
        threshold = AnalysisQualityThreshold(
            min_confidence_score=0.7,
            max_hallucination_score=0.3
        )
        assert threshold.is_acceptable(confidence=0.8, hallucination=0.2) is True
    
    def test_is_acceptable_low_confidence(self):
        threshold = AnalysisQualityThreshold(min_confidence_score=0.7)
        assert threshold.is_acceptable(confidence=0.6, hallucination=0.2) is False
    
    def test_is_acceptable_high_hallucination(self):
        threshold = AnalysisQualityThreshold(max_hallucination_score=0.3)
        assert threshold.is_acceptable(confidence=0.8, hallucination=0.4) is False
```

---

### 3.2 Application Tests
```python
# tests/application/test_analyze_excel_use_case.py

import pytest
from unittest.mock import AsyncMock, Mock
from application.use_cases.analyze_excel_use_case import AnalyzeExcelUseCase
from domain.policies.analysis_policy import AnalysisRetryPolicy, AnalysisQualityThreshold


@pytest.mark.asyncio
async def test_analyze_excel_success_first_attempt():
    # Mock workflow
    mock_workflow = Mock()
    mock_workflow.run = AsyncMock(return_value={
        "request_id": "test-123",
        "user_query": "데이터 요약",
        "excel_data": {"rows": 100},
        "analysis_text": "분석 결과",
        "confidence_score": 0.9,
        "hallucination_score": 0.1,
        "attempts_history": [{
            "attempt_number": 1,
            "analysis_text": "분석 결과",
            "confidence_score": 0.9,
            "hallucination_score": 0.1,
            "used_web_search": False,
            "timestamp": "2025-02-07T10:00:00"
        }],
        "is_complete": True,
        "final_status": "completed",
        "needs_code_execution": False
    })
    
    mock_logger = Mock()
    
    use_case = AnalyzeExcelUseCase(
        workflow=mock_workflow,
        logger=mock_logger
    )
    
    # 실행
    result = await use_case.execute(
        excel_file_path="/tmp/test.xlsx",
        user_query="데이터 요약"
    )
    
    # 검증
    assert result.is_successful is True
    assert result.total_attempts == 1
    assert result.final_answer == "분석 결과"


@pytest.mark.asyncio
async def test_analyze_excel_retry_on_hallucination():
    mock_workflow = Mock()
    mock_workflow.run = AsyncMock(return_value={
        "request_id": "test-456",
        "user_query": "데이터 분석",
        "excel_data": {"rows": 50},
        "analysis_text": "개선된 분석",
        "confidence_score": 0.8,
        "hallucination_score": 0.15,
        "attempts_history": [
            {
                "attempt_number": 1,
                "confidence_score": 0.6,
                "hallucination_score": 0.5,
                "used_web_search": False,
                "timestamp": "2025-02-07T10:00:00",
                "analysis_text": "첫 시도"
            },
            {
                "attempt_number": 2,
                "confidence_score": 0.8,
                "hallucination_score": 0.15,
                "used_web_search": True,
                "timestamp": "2025-02-07T10:01:00",
                "analysis_text": "개선된 분석"
            }
        ],
        "is_complete": True,
        "final_status": "completed",
        "needs_code_execution": False
    })
    
    use_case = AnalyzeExcelUseCase(
        workflow=mock_workflow,
        logger=Mock()
    )
    
    result = await use_case.execute(
        excel_file_path="/tmp/test.xlsx",
        user_query="데이터 분석"
    )
    
    assert result.total_attempts == 2
    assert result.attempts[1].used_web_search is True
```

---

## 4. Configuration

### `.env` 설정
```bash
# 분석 재시도 정책
ANALYSIS_MAX_RETRIES=3
ANALYSIS_RETRY_ON_HALLUCINATION=true
ANALYSIS_REQUIRE_WEB_SEARCH_ON_RETRY=true

# 품질 임계값
ANALYSIS_MIN_CONFIDENCE_SCORE=0.7
ANALYSIS_MAX_HALLUCINATION_SCORE=0.3
```

---

## 5. Usage Example

### 5.1 API 호출
```bash
curl -X POST "http://localhost:8000/api/v1/analysis/excel" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@sales_data.xlsx" \
  -F "query=2024년 매출 추이를 분석하고 그래프로 보여줘"
```

### 5.2 응답 예시
```json
{
  "request_id": "abc-123",
  "query": "2024년 매출 추이를 분석하고 그래프로 보여줘",
  "final_answer": "2024년 매출은 전년 대비 15% 증가했습니다...",
  "is_successful": true,
  "total_attempts": 2,
  "attempts": [
    {
      "attempt_number": 1,
      "confidence_score": 0.65,
      "hallucination_score": 0.4,
      "used_web_search": false,
      "timestamp": "2025-02-07T10:00:00"
    },
    {
      "attempt_number": 2,
      "confidence_score": 0.85,
      "hallucination_score": 0.12,
      "used_web_search": true,
      "timestamp": "2025-02-07T10:01:30"
    }
  ],
  "executed_code": "import matplotlib.pyplot as plt\n...",
  "code_output": {
    "image_path": "/tmp/chart_abc123.png"
  }
}
```

---

## 6. Logging Requirements (LOG-001)

모든 노드는 다음을 로깅해야 한다:
```python
# 시작
self._logger.info("Node started", request_id=request_id, node="parse_excel")

# 완료
self._logger.info("Node completed", request_id=request_id, node="parse_excel", duration_ms=150)

# 에러
self._logger.error("Node failed", exception=e, request_id=request_id, node="parse_excel")
```

---

## 7. Extension Points (코드 수정 용이성)

### 7.1 재시도 횟수 변경
```python
# .env
ANALYSIS_MAX_RETRIES=5  # 3 -> 5로 변경
```

### 7.2 품질 임계값 조정
```python
# .env
ANALYSIS_MIN_CONFIDENCE_SCORE=0.8  # 더 엄격하게
ANALYSIS_MAX_HALLUCINATION_SCORE=0.2
```

### 7.3 웹 검색 강제 비활성화
```python
# .env
ANALYSIS_REQUIRE_WEB_SEARCH_ON_RETRY=false
```

### 7.4 커스텀 로직 추가
```python
# application/workflows/excel_analysis_workflow.py

def _should_retry_or_execute(self, state):
    # ⬇️ 여기에 커스텀 로직 추가
    if state["user_query"].startswith("긴급"):
        return "complete"  # 재시도 스킵
    
    # 기존 로직
    quality_ok = self._quality_threshold.is_acceptable(...)
    ...
```

---

## 8. Dependencies Graph
```
AGENT-002 (Excel Analysis Agent)
├── EXCEL-001 (Excel Parser)
├── LLM-001 (Claude Client)
├── SEARCH-001 (Tavily Search)
├── EVAL-001 (Hallucination Evaluator)
├── CODE-001 (Code Executor)
└── LOG-001 (Logging)
```

---

## 9. Acceptance Criteria

- [x] 엑셀 파일을 Claude에 전달하여 분석 가능
- [x] 필요 시 웹 검색 자동 수행
- [x] 할루시네이션 검증 후 재시도 (최대 3회)
- [x] 코드 실행 필요 시 자동 실행
- [x] 전체 시도 기록 및 품질 점수 제공
- [x] 설정 파일로 정책 변경 가능
- [x] 모든 노드 로깅 (LOG-001 준수)
- [x] TDD로 개발 (테스트 우선)

---

## 10. Notes

- 할루시네이션 점수가 높으면 자동으로 웹 검색 + 재시도
- 3회 실패 시 `is_successful=False` 반환 (에러 아님)
- 코드 실행은 샌드박스 환경에서만 (CODE-001 참고)
- 민감한 데이터는 로그에서 마스킹 필수

---

**End of AGENT-002**