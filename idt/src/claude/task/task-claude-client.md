task-claude-client.md

Task ID: LLM-001
담당: Claude LLM 클라이언트 모듈
의존성: LOG-001
최종 수정: 2025-02-06


1. 목적
Claude 모델에 대한 LLM 질의를 담당하는 Infrastructure 모듈을 구현한다.
핵심 책임:

Anthropic API를 통한 Claude 모델 호출
요청/응답 로깅 (LOG-001 준수)
에러 핸들링 및 재시도 로직
스트리밍 응답 지원
토큰 사용량 추적


2. 아키텍처 위치
infrastructure/
└── llm/
    ├── __init__.py
    ├── claude_client.py          # ClaudeClient 구현
    ├── schemas.py                # Request/Response 스키마
    └── exceptions.py             # LLM 관련 예외
레이어 규칙:

✅ infrastructure 레이어에 위치
✅ LoggerInterface 주입받아 사용
❌ domain 규칙 포함 금지 (순수 API 클라이언트)


3. 핵심 스펙
3.1 지원 모델
pythonclass ClaudeModel(str, Enum):
    """지원하는 Claude 모델"""
    OPUS_4_5 = "claude-opus-4-5-20251101"
    SONNET_4_5 = "claude-sonnet-4-5-20250929"
    HAIKU_4_5 = "claude-haiku-4-5-20251001"
3.2 요청 스키마
python@dataclass
class ClaudeRequest:
    """Claude API 요청"""
    model: ClaudeModel
    messages: list[dict[str, str]]  # [{"role": "user", "content": "..."}]
    system: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    stream: bool = False
    
    # 추적용
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
3.3 응답 스키마
python@dataclass
class ClaudeResponse:
    """Claude API 응답"""
    content: str
    model: str
    stop_reason: str  # "end_turn" | "max_tokens" | "stop_sequence"
    
    # 토큰 사용량
    input_tokens: int
    output_tokens: int
    
    # 추적용
    request_id: str
    latency_ms: int

4. ClaudeClient 구현
4.1 기본 구조
pythonfrom anthropic import Anthropic, AsyncAnthropic
from domain.logger import LoggerInterface

class ClaudeClient:
    """Claude LLM 클라이언트"""
    
    def __init__(
        self,
        api_key: str,
        logger: LoggerInterface,
        max_retries: int = 3,
        timeout: int = 60
    ):
        self._client = AsyncAnthropic(
            api_key=api_key,
            max_retries=max_retries,
            timeout=timeout
        )
        self._logger = logger
    
    async def complete(
        self, 
        request: ClaudeRequest
    ) -> ClaudeResponse:
        """
        Claude 모델 호출 (비스트리밍)
        
        Args:
            request: 요청 스키마
            
        Returns:
            ClaudeResponse
            
        Raises:
            ClaudeAPIError: API 호출 실패
            ClaudeRateLimitError: Rate limit 초과
        """
        pass
    
    async def stream_complete(
        self,
        request: ClaudeRequest
    ) -> AsyncIterator[str]:
        """
        Claude 모델 호출 (스트리밍)
        
        Yields:
            content chunk (str)
        """
        pass
4.2 로깅 규칙 (LOG-001 준수)
요청 시작 로그 (INFO)
pythonself._logger.info(
    "Claude API request started",
    request_id=request.request_id,
    model=request.model,
    message_count=len(request.messages),
    max_tokens=request.max_tokens,
    stream=request.stream
)
응답 완료 로그 (INFO)
pythonself._logger.info(
    "Claude API request completed",
    request_id=request.request_id,
    input_tokens=response.input_tokens,
    output_tokens=response.output_tokens,
    latency_ms=latency_ms,
    stop_reason=response.stop_reason
)
에러 로그 (ERROR + 스택 트레이스 필수)
pythonself._logger.error(
    "Claude API request failed",
    exception=e,  # 자동으로 스택 트레이스 포함
    request_id=request.request_id,
    model=request.model
)

5. 예외 처리
5.1 커스텀 예외
python# infrastructure/llm/exceptions.py

class ClaudeLLMError(Exception):
    """Claude LLM 관련 에러 베이스"""
    pass

class ClaudeAPIError(ClaudeLLMError):
    """API 호출 실패"""
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)

class ClaudeRateLimitError(ClaudeLLMError):
    """Rate limit 초과"""
    pass

class ClaudeTimeoutError(ClaudeLLMError):
    """타임아웃"""
    pass

class ClaudeInvalidRequestError(ClaudeLLMError):
    """잘못된 요청 (4xx)"""
    pass
5.2 에러 매핑
pythonfrom anthropic import (
    APIError,
    RateLimitError,
    APITimeoutError,
    BadRequestError
)

# complete() 메서드 내부
try:
    response = await self._client.messages.create(...)
except RateLimitError as e:
    self._logger.error("Rate limit exceeded", exception=e, request_id=request.request_id)
    raise ClaudeRateLimitError(str(e)) from e
except APITimeoutError as e:
    self._logger.error("API timeout", exception=e, request_id=request.request_id)
    raise ClaudeTimeoutError(str(e)) from e
except BadRequestError as e:
    self._logger.error("Invalid request", exception=e, request_id=request.request_id)
    raise ClaudeInvalidRequestError(str(e)) from e
except APIError as e:
    self._logger.error("API error", exception=e, request_id=request.request_id)
    raise ClaudeAPIError(str(e), getattr(e, 'status_code', None)) from e

6. 재시도 로직
6.1 재시도 대상

✅ 네트워크 에러 (연결 실패, 타임아웃)
✅ 5xx 서버 에러
✅ Rate limit (429) - exponential backoff
❌ 4xx 클라이언트 에러 (재시도 불가)

6.2 구현
pythonfrom tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

class ClaudeClient:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ClaudeAPIError, ClaudeTimeoutError)),
        reraise=True
    )
    async def _call_api(self, request: ClaudeRequest) -> dict:
        """재시도 로직이 적용된 내부 API 호출"""
        self._logger.debug(
            "Calling Claude API",
            request_id=request.request_id,
            attempt=self._call_api.retry.statistics.get("attempt_number", 1)
        )
        
        response = await self._client.messages.create(
            model=request.model,
            messages=request.messages,
            system=request.system,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stream=request.stream
        )
        
        return response

7. 테스트 시나리오
7.1 단위 테스트 (Mock 사용)
python# tests/infrastructure/llm/test_claude_client.py

import pytest
from unittest.mock import AsyncMock, patch
from infrastructure.llm.claude_client import ClaudeClient
from infrastructure.llm.schemas import ClaudeRequest, ClaudeModel

@pytest.fixture
def mock_logger():
    """Mock LoggerInterface"""
    return Mock(spec=LoggerInterface)

@pytest.fixture
def claude_client(mock_logger):
    return ClaudeClient(
        api_key="test-key",
        logger=mock_logger
    )

@pytest.mark.asyncio
async def test_complete_success(claude_client, mock_logger):
    """정상 응답 테스트"""
    request = ClaudeRequest(
        model=ClaudeModel.SONNET_4_5,
        messages=[{"role": "user", "content": "Hello"}]
    )
    
    with patch.object(claude_client._client.messages, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = Mock(
            content=[Mock(text="Hi there!")],
            model="claude-sonnet-4-5-20250929",
            stop_reason="end_turn",
            usage=Mock(input_tokens=10, output_tokens=5)
        )
        
        response = await claude_client.complete(request)
        
        assert response.content == "Hi there!"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        
        # 로그 검증
        assert mock_logger.info.call_count == 2  # start + complete
        assert "Claude API request started" in mock_logger.info.call_args_list[0][0][0]

@pytest.mark.asyncio
async def test_complete_rate_limit_error(claude_client, mock_logger):
    """Rate limit 에러 처리 테스트"""
    from anthropic import RateLimitError
    
    request = ClaudeRequest(
        model=ClaudeModel.SONNET_4_5,
        messages=[{"role": "user", "content": "Hello"}]
    )
    
    with patch.object(claude_client._client.messages, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = RateLimitError("Rate limit exceeded")
        
        with pytest.raises(ClaudeRateLimitError):
            await claude_client.complete(request)
        
        # 에러 로그 검증
        mock_logger.error.assert_called_once()
        assert "Rate limit exceeded" in str(mock_logger.error.call_args)
7.2 통합 테스트 (실제 API 호출)
python@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_api_call():
    """실제 Claude API 호출 테스트 (CI에서는 스킵)"""
    import os
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    
    logger = StructuredLogger()
    client = ClaudeClient(api_key=api_key, logger=logger)
    
    request = ClaudeRequest(
        model=ClaudeModel.HAIKU_4_5,  # 가장 빠른 모델
        messages=[{"role": "user", "content": "Say 'test' in one word"}],
        max_tokens=10
    )
    
    response = await client.complete(request)
    
    assert response.content
    assert response.input_tokens > 0
    assert response.output_tokens > 0

8. 설정 (Configuration)
8.1 환경변수
python# config/settings.py

class LLMSettings(BaseSettings):
    """LLM 설정"""
    ANTHROPIC_API_KEY: str
    
    # Claude 기본 설정
    CLAUDE_DEFAULT_MODEL: str = ClaudeModel.SONNET_4_5
    CLAUDE_MAX_TOKENS: int = 4096
    CLAUDE_TEMPERATURE: float = 0.7
    CLAUDE_TIMEOUT: int = 60
    CLAUDE_MAX_RETRIES: int = 3
    
    class Config:
        env_file = ".env"
8.2 의존성 주입
python# infrastructure/dependencies.py

from functools import lru_cache

@lru_cache()
def get_claude_client() -> ClaudeClient:
    """ClaudeClient 싱글톤 팩토리"""
    settings = get_settings()
    logger = get_logger()
    
    return ClaudeClient(
        api_key=settings.ANTHROPIC_API_KEY,
        logger=logger,
        max_retries=settings.CLAUDE_MAX_RETRIES,
        timeout=settings.CLAUDE_TIMEOUT
    )

9. 사용 예시
9.1 Application Layer에서 사용
python# application/usecases/chat_usecase.py

class ChatUseCase:
    def __init__(
        self,
        claude_client: ClaudeClient,
        logger: LoggerInterface
    ):
        self._claude = claude_client
        self._logger = logger
    
    async def process_query(
        self,
        user_id: str,
        session_id: str,
        query: str,
        context: str | None = None
    ) -> str:
        """사용자 질의 처리"""
        
        messages = [{"role": "user", "content": query}]
        
        request = ClaudeRequest(
            model=ClaudeModel.SONNET_4_5,
            messages=messages,
            system=context,
            max_tokens=2048,
            temperature=0.3
        )
        
        try:
            response = await self._claude.complete(request)
            
            self._logger.info(
                "Chat completed",
                user_id=user_id,
                session_id=session_id,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens
            )
            
            return response.content
            
        except ClaudeRateLimitError:
            self._logger.warning("Rate limit hit", user_id=user_id)
            raise ApplicationError("서비스가 일시적으로 혼잡합니다. 잠시 후 다시 시도해주세요.")
9.2 FastAPI Endpoint
python# interfaces/api/v1/chat.py

from fastapi import APIRouter, Depends

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("/query")
async def chat_query(
    request: ChatQueryRequest,
    claude_client: ClaudeClient = Depends(get_claude_client)
):
    """채팅 질의"""
    # Use case 호출 (생략)
    pass

10. 체크리스트
개발 전

 LOG-001 (task-logging.md) 읽기
 Anthropic SDK 문서 확인
 환경변수 설정 (ANTHROPIC_API_KEY)

구현 시

 ClaudeClient 구현
 요청/응답 스키마 정의
 예외 클래스 정의
 로깅 적용 (INFO/ERROR/DEBUG)
 재시도 로직 구현

테스트

 Mock 기반 단위 테스트
 Rate limit 에러 테스트
 타임아웃 테스트
 실제 API 호출 통합 테스트 (선택)

문서화

 지원 모델 목록 명시
 환경변수 문서화
 에러 핸들링 가이드


11. 금지 사항

❌ domain 규칙 포함 금지 (순수 API 클라이언트)
❌ print() 사용 금지 (logger 필수)
❌ 스택 트레이스 없는 에러 로그 금지
❌ API 키 하드코딩 금지
❌ 4xx 에러에 대한 재시도 금지


12. 참고사항
12.1 토큰 사용량 추적
프로덕션 환경에서는 토큰 사용량을 별도 저장하여 비용 모니터링에 활용:
python# 별도 로깅 또는 DB 저장
self._logger.info(
    "Token usage",
    user_id=user_id,
    model=request.model,
    input_tokens=response.input_tokens,
    output_tokens=response.output_tokens,
    total_tokens=response.input_tokens + response.output_tokens
)
12.2 Context Caching (향후 확장)
Claude API의 Prompt Caching 기능 사용 시:

system 프롬프트를 캐싱하여 비용 절감
대화 히스토리를 캐싱하여 latency 개선

