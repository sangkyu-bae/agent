# Task: 할루시네이션 평가기 (Hallucination Evaluator)

> Task ID: EVAL-001  
> 의존성: LOG-001  
> 최종 수정: 2025-01-31

---

## 1. 목적

- LLM이 생성한 답변이 참조 문서에 근거한 것인지 검증
- 환각(문서에 없는 내용을 생성한 경우) 탐지
- Yes/No 이진 판정으로 명확한 결과 제공

---

## 2. 설계 원칙

### 2.1 아키텍처 레이어 배치

| 레이어 | 구성요소 | 역할 |
|--------|----------|------|
| domain | `HallucinationPolicy`, `HallucinationEvaluationResult` | 평가 규칙, 결과 VO 정의 |
| application | `HallucinationEvaluatorUseCase` | LangChain 호출 오케스트레이션 |
| infrastructure | `HallucinationEvaluatorAdapter` | LLM 호출, 프롬프트 실행 |

### 2.2 의존성

- LOG-001 (로깅 필수)
- LangChain (`ChatPromptTemplate`, `with_structured_output`)
- LangChain OpenAI (`ChatOpenAI`)

---

## 3. 도메인 설계

### 3.1 HallucinationEvaluationResult (Value Object)

```python
# domain/hallucination/value_objects.py
from pydantic import BaseModel, Field


class HallucinationEvaluationResult(BaseModel):
    """할루시네이션 평가 결과 VO"""
    
    is_hallucinated: bool = Field(
        description="True if the generation contains hallucination, False otherwise"
    )
```

### 3.2 HallucinationPolicy (Domain Policy)

```python
# domain/hallucination/policy.py

class HallucinationPolicy:
    """할루시네이션 판정 정책"""
    
    @staticmethod
    def requires_evaluation(generation: str, documents: list[str]) -> bool:
        """평가가 필요한지 판단"""
        if not generation or not generation.strip():
            return False
        if not documents:
            return False
        return True
```

---

## 4. 인프라스트럭처 설계

### 4.1 System Prompt

```python
# infrastructure/hallucination/prompts.py

HALLUCINATION_EVALUATION_SYSTEM_PROMPT = """You are a hallucination evaluator. Your task is to determine whether the given generation is grounded in the provided documents.

## Instructions
1. Carefully read all provided documents
2. Compare the generation against the documents
3. Determine if the generation contains any information NOT supported by the documents

## Evaluation Criteria
- If the generation contains ANY claim, fact, or detail that cannot be verified from the documents, it is a hallucination
- If the generation only contains information that is directly supported by or can be reasonably inferred from the documents, it is NOT a hallucination
- Be strict: when in doubt, consider it a hallucination

## Response
Answer with a single boolean:
- true: The generation contains hallucination (includes unsupported information)
- false: The generation is fully grounded in the documents (no hallucination)"""


HALLUCINATION_EVALUATION_HUMAN_TEMPLATE = """## Documents
{documents}

## Generation to Evaluate
{generation}

Is this generation hallucinated? (true/false)"""
```

### 4.2 LLM Output Schema

```python
# infrastructure/hallucination/schemas.py
from pydantic import BaseModel, Field


class HallucinationOutput(BaseModel):
    """LLM structured output 스키마"""
    
    is_hallucinated: bool = Field(
        description="True if hallucination detected, False if grounded"
    )
```

### 4.3 Adapter 구현

```python
# infrastructure/hallucination/adapter.py
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from domain.hallucination.value_objects import HallucinationEvaluationResult
from infrastructure.hallucination.prompts import (
    HALLUCINATION_EVALUATION_SYSTEM_PROMPT,
    HALLUCINATION_EVALUATION_HUMAN_TEMPLATE,
)
from infrastructure.hallucination.schemas import HallucinationOutput
from infrastructure.logging.logger import get_logger  # 프로젝트 로거 import

logger = get_logger(__name__)


class HallucinationEvaluatorAdapter:
    """할루시네이션 평가 LLM Adapter"""
    
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
            ("system", HALLUCINATION_EVALUATION_SYSTEM_PROMPT),
            ("human", HALLUCINATION_EVALUATION_HUMAN_TEMPLATE),
        ])
        self._chain = self._prompt | self._llm.with_structured_output(HallucinationOutput)
    
    async def evaluate(
        self,
        documents: list[str],
        generation: str,
        request_id: str,
    ) -> HallucinationEvaluationResult:
        """
        할루시네이션 평가 수행
        
        Args:
            documents: 참조 문서 리스트
            generation: LLM이 생성한 답변
            request_id: 요청 추적 ID
            
        Returns:
            HallucinationEvaluationResult
        """
        logger.info(
            "Hallucination evaluation started",
            extra={
                "request_id": request_id,
                "document_count": len(documents),
                "generation_length": len(generation),
            }
        )
        
        try:
            documents_text = "\n\n---\n\n".join(documents)
            
            result: HallucinationOutput = await self._chain.ainvoke({
                "documents": documents_text,
                "generation": generation,
            })
            
            logger.info(
                "Hallucination evaluation completed",
                extra={
                    "request_id": request_id,
                    "is_hallucinated": result.is_hallucinated,
                }
            )
            
            return HallucinationEvaluationResult(
                is_hallucinated=result.is_hallucinated
            )
            
        except Exception as e:
            logger.error(
                "Hallucination evaluation failed",
                extra={"request_id": request_id},
                exc_info=True,  # 스택 트레이스 포함
            )
            raise
```

---

## 5. Application 설계

### 5.1 UseCase

```python
# application/hallucination/use_case.py
from domain.hallucination.policy import HallucinationPolicy
from domain.hallucination.value_objects import HallucinationEvaluationResult
from infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class HallucinationEvaluatorUseCase:
    """할루시네이션 평가 유스케이스"""
    
    def __init__(self, evaluator_adapter: HallucinationEvaluatorAdapter):
        self._evaluator = evaluator_adapter
    
    async def evaluate(
        self,
        documents: list[str],
        generation: str,
        request_id: str,
    ) -> HallucinationEvaluationResult:
        """
        할루시네이션 평가 실행
        
        Args:
            documents: 참조 문서 리스트
            generation: 평가 대상 LLM 답변
            request_id: 요청 추적 ID
            
        Returns:
            HallucinationEvaluationResult
            
        Raises:
            ValueError: 평가 불가능한 입력
        """
        if not HallucinationPolicy.requires_evaluation(generation, documents):
            logger.warning(
                "Evaluation skipped: invalid input",
                extra={
                    "request_id": request_id,
                    "has_generation": bool(generation),
                    "has_documents": bool(documents),
                }
            )
            raise ValueError("Generation and documents are required for evaluation")
        
        return await self._evaluator.evaluate(
            documents=documents,
            generation=generation,
            request_id=request_id,
        )
```

---

## 6. 파일 구조

```
src/
├── domain/
│   └── hallucination/
│       ├── __init__.py
│       ├── policy.py              # HallucinationPolicy
│       └── value_objects.py       # HallucinationEvaluationResult
├── application/
│   └── hallucination/
│       ├── __init__.py
│       └── use_case.py            # HallucinationEvaluatorUseCase
└── infrastructure/
    └── hallucination/
        ├── __init__.py
        ├── prompts.py             # System/Human prompts
        ├── schemas.py             # HallucinationOutput (LLM 출력 스키마)
        └── adapter.py             # HallucinationEvaluatorAdapter
```

---

## 7. 테스트 요구사항

### 7.1 Domain 테스트 (Mock 금지)

```python
# tests/domain/hallucination/test_policy.py
import pytest
from domain.hallucination.policy import HallucinationPolicy


class TestHallucinationPolicy:
    
    def test_requires_evaluation_returns_true_with_valid_input(self):
        # Given
        generation = "Some answer"
        documents = ["doc1", "doc2"]
        
        # When
        result = HallucinationPolicy.requires_evaluation(generation, documents)
        
        # Then
        assert result is True
    
    def test_requires_evaluation_returns_false_with_empty_generation(self):
        # Given
        generation = ""
        documents = ["doc1"]
        
        # When
        result = HallucinationPolicy.requires_evaluation(generation, documents)
        
        # Then
        assert result is False
    
    def test_requires_evaluation_returns_false_with_whitespace_generation(self):
        # Given
        generation = "   "
        documents = ["doc1"]
        
        # When
        result = HallucinationPolicy.requires_evaluation(generation, documents)
        
        # Then
        assert result is False
    
    def test_requires_evaluation_returns_false_with_empty_documents(self):
        # Given
        generation = "Some answer"
        documents = []
        
        # When
        result = HallucinationPolicy.requires_evaluation(generation, documents)
        
        # Then
        assert result is False
    
    def test_requires_evaluation_returns_false_with_none_generation(self):
        # Given
        generation = None
        documents = ["doc1"]
        
        # When
        result = HallucinationPolicy.requires_evaluation(generation, documents)
        
        # Then
        assert result is False
```

### 7.2 Infrastructure 테스트 (Mock 사용)

```python
# tests/infrastructure/hallucination/test_adapter.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter
from infrastructure.hallucination.schemas import HallucinationOutput


class TestHallucinationEvaluatorAdapter:
    
    @pytest.fixture
    def mock_chain(self):
        return AsyncMock()
    
    @pytest.fixture
    def adapter(self, mock_chain):
        with patch.object(
            HallucinationEvaluatorAdapter,
            '_chain',
            mock_chain
        ):
            adapter = HallucinationEvaluatorAdapter()
            adapter._chain = mock_chain
            return adapter
    
    @pytest.mark.asyncio
    async def test_evaluate_returns_no_hallucination_when_grounded(self, adapter, mock_chain):
        # Given
        documents = ["The capital of France is Paris."]
        generation = "Paris is the capital of France."
        mock_chain.ainvoke.return_value = HallucinationOutput(is_hallucinated=False)
        
        # When
        result = await adapter.evaluate(documents, generation, "req-123")
        
        # Then
        assert result.is_hallucinated is False
        mock_chain.ainvoke.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_evaluate_detects_hallucination_when_not_grounded(self, adapter, mock_chain):
        # Given
        documents = ["The capital of France is Paris."]
        generation = "Paris is the capital of France. It has 10 million people."
        mock_chain.ainvoke.return_value = HallucinationOutput(is_hallucinated=True)
        
        # When
        result = await adapter.evaluate(documents, generation, "req-123")
        
        # Then
        assert result.is_hallucinated is True
    
    @pytest.mark.asyncio
    async def test_evaluate_joins_multiple_documents(self, adapter, mock_chain):
        # Given
        documents = ["Doc 1 content", "Doc 2 content", "Doc 3 content"]
        generation = "Some answer"
        mock_chain.ainvoke.return_value = HallucinationOutput(is_hallucinated=False)
        
        # When
        await adapter.evaluate(documents, generation, "req-123")
        
        # Then
        call_args = mock_chain.ainvoke.call_args[0][0]
        assert "Doc 1 content" in call_args["documents"]
        assert "Doc 2 content" in call_args["documents"]
        assert "Doc 3 content" in call_args["documents"]
        assert "---" in call_args["documents"]  # separator 확인
    
    @pytest.mark.asyncio
    async def test_evaluate_raises_exception_on_llm_error(self, adapter, mock_chain):
        # Given
        documents = ["Some doc"]
        generation = "Some answer"
        mock_chain.ainvoke.side_effect = Exception("LLM API Error")
        
        # When & Then
        with pytest.raises(Exception, match="LLM API Error"):
            await adapter.evaluate(documents, generation, "req-123")
```

### 7.3 Application 테스트

```python
# tests/application/hallucination/test_use_case.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from application.hallucination.use_case import HallucinationEvaluatorUseCase
from domain.hallucination.value_objects import HallucinationEvaluationResult


class TestHallucinationEvaluatorUseCase:
    
    @pytest.fixture
    def mock_adapter(self):
        return AsyncMock()
    
    @pytest.fixture
    def use_case(self, mock_adapter):
        return HallucinationEvaluatorUseCase(evaluator_adapter=mock_adapter)
    
    @pytest.mark.asyncio
    async def test_evaluate_calls_adapter_with_valid_input(self, use_case, mock_adapter):
        # Given
        documents = ["doc1", "doc2"]
        generation = "Some answer"
        mock_adapter.evaluate.return_value = HallucinationEvaluationResult(
            is_hallucinated=False
        )
        
        # When
        result = await use_case.evaluate(documents, generation, "req-123")
        
        # Then
        assert result.is_hallucinated is False
        mock_adapter.evaluate.assert_called_once_with(
            documents=documents,
            generation=generation,
            request_id="req-123",
        )
    
    @pytest.mark.asyncio
    async def test_evaluate_raises_value_error_with_empty_generation(self, use_case):
        # Given
        documents = ["doc1"]
        generation = ""
        
        # When & Then
        with pytest.raises(ValueError, match="Generation and documents are required"):
            await use_case.evaluate(documents, generation, "req-123")
    
    @pytest.mark.asyncio
    async def test_evaluate_raises_value_error_with_empty_documents(self, use_case):
        # Given
        documents = []
        generation = "Some answer"
        
        # When & Then
        with pytest.raises(ValueError, match="Generation and documents are required"):
            await use_case.evaluate(documents, generation, "req-123")
```

---

## 8. 사용 예시

```python
from application.hallucination.use_case import HallucinationEvaluatorUseCase
from infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter


# Adapter 생성
adapter = HallucinationEvaluatorAdapter(
    model_name="gpt-4o-mini",
    temperature=0.0,
)

# UseCase 생성
use_case = HallucinationEvaluatorUseCase(evaluator_adapter=adapter)

# 평가 실행
documents = [
    "회사의 2024년 매출은 100억원입니다.",
    "영업이익률은 15%입니다.",
]
generation = "회사의 2024년 매출은 100억원이며, 영업이익은 15억원입니다."

result = await use_case.evaluate(
    documents=documents,
    generation=generation,
    request_id="req-abc-123",
)

if result.is_hallucinated:
    print("⚠️ 환각 감지됨")
else:
    print("✅ 문서에 근거한 답변")
```

---

## 9. 설정값

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `model_name` | `gpt-4o-mini` | 평가용 LLM 모델 |
| `temperature` | `0.0` | 결정적 출력을 위해 0 고정 |

---

## 10. 로깅 체크리스트 (LOG-001 준수)

- [x] `get_logger(__name__)` 사용
- [x] 주요 처리 시작/완료 INFO 로그
- [x] 예외 발생 시 ERROR 로그 + `exc_info=True` (스택 트레이스)
- [x] `request_id` 컨텍스트 전파 (`extra` dict 사용)
- [x] 민감 정보 마스킹 해당 없음

---

## 11. 금지 사항

- ❌ `temperature > 0` 사용 금지 (일관된 평가 필요)
- ❌ 프롬프트에서 Yes/No 텍스트 파싱 금지 (`with_structured_output` 사용)
- ❌ 문서 없이 평가 시도 금지
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

---

## 13. CLAUDE.md Task Files Reference 추가

```markdown
| EVAL-001 | task-hallucination-evaluator.md | 할루시네이션 평가기 모듈 |
```