task-ollama-client.md

Task ID: OLLAMA-001
담당: Ollama LLM 클라이언트 모듈
의존성: LOG-001
최종 수정: 2026-03-23


1. 목적
LangChain을 통해 로컬 Ollama 모델에 대한 LLM 질의를 담당하는 Infrastructure 모듈을 구현한다.
핵심 책임:

ChatOllama(langchain-ollama)를 통한 로컬 Ollama 모델 호출
요청/응답 로깅 (LOG-001 준수)
에러 핸들링 (연결 실패, 타임아웃)
스트리밍 응답 지원
토큰 사용량 추적 (가능한 경우)


2. 아키텍처 위치
infrastructure/
└── llm/
    └── ollama/
        ├── __init__.py
        ├── ollama_client.py      # OllamaClient 구현
        ├── schemas.py            # Request/Response 스키마
        └── exceptions.py        # Ollama 관련 예외
레이어 규칙:

✅ infrastructure 레이어에 위치
✅ LoggerInterface 주입받아 사용
❌ domain 규칙 포함 금지 (순수 API 클라이언트)


3. 핵심 스펙
3.1 지원 모델
python
class OllamaModel(str, Enum):
    """지원하는 Ollama 모델 (로컬 설치 필요)"""
    LLAMA3_2 = "llama3.2"
    LLAMA3_1 = "llama3.1"
    MISTRAL = "mistral"
    GEMMA2 = "gemma2"
    QWEN2_5 = "qwen2.5"
    DEEPSEEK_R1 = "deepseek-r1"

3.2 요청 스키마
python
@dataclass
class OllamaRequest:
    """Ollama API 요청"""
    model: OllamaModel | str          # Enum 또는 임의 모델명(문자열) 허용
    messages: list[dict[str, str]]    # [{"role": "user", "content": "..."}]
    system: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    stream: bool = False

    # 추적용
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

3.3 응답 스키마
python
@dataclass
class OllamaResponse:
    """Ollama API 응답"""
    content: str
    model: str
    stop_reason: str       # "stop" | "length" | "unknown"

    # 토큰 사용량 (Ollama가 제공하는 경우)
    input_tokens: int
    output_tokens: int

    # 추적용
    request_id: str
    latency_ms: int


4. OllamaClient 구현
4.1 기본 구조
python
from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from src.domain.logging.interfaces.logger_interface import LoggerInterface

class OllamaClient:
    """Ollama LLM 클라이언트 (LangChain ChatOllama 기반)"""

    def __init__(
        self,
        base_url: str,
        logger: LoggerInterface,
        timeout: int = 120,
    ):
        self._base_url = base_url
        self._logger = logger
        self._timeout = timeout

    def _create_chat_model(self, request: OllamaRequest) -> ChatOllama:
        model_name = request.model.value if isinstance(request.model, OllamaModel) else request.model
        return ChatOllama(
            model=model_name,
            base_url=self._base_url,
            temperature=request.temperature,
            num_predict=request.max_tokens,
            timeout=self._timeout,
        )

    async def complete(self, request: OllamaRequest) -> OllamaResponse:
        """Ollama 모델 호출 (비스트리밍)"""
        pass

    async def stream_complete(self, request: OllamaRequest) -> AsyncIterator[str]:
        """Ollama 모델 호출 (스트리밍)"""
        pass

4.2 로깅 규칙 (LOG-001 준수)
요청 시작 로그 (INFO)
python
self._logger.info(
    "Ollama API request started",
    request_id=request.request_id,
    model=model_name,
    message_count=len(request.messages),
    max_tokens=request.max_tokens,
    stream=request.stream,
)

응답 완료 로그 (INFO)
python
self._logger.info(
    "Ollama API request completed",
    request_id=request.request_id,
    input_tokens=result.input_tokens,
    output_tokens=result.output_tokens,
    latency_ms=latency_ms,
    stop_reason=result.stop_reason,
)

에러 로그 (ERROR + 스택 트레이스 필수)
python
self._logger.error(
    "Ollama API request failed",
    exception=e,
    request_id=request.request_id,
    model=model_name,
)


5. 예외 처리
5.1 커스텀 예외
python
# infrastructure/llm/ollama/exceptions.py

class OllamaLLMError(Exception):
    """Ollama LLM 관련 에러 베이스"""
    pass

class OllamaConnectionError(OllamaLLMError):
    """Ollama 서버 연결 실패"""
    pass

class OllamaTimeoutError(OllamaLLMError):
    """요청 타임아웃"""
    pass

class OllamaModelNotFoundError(OllamaLLMError):
    """요청한 모델이 로컬에 없음"""
    pass

class OllamaInvalidRequestError(OllamaLLMError):
    """잘못된 요청"""
    pass

5.2 에러 매핑
python
import httpx

try:
    ai_message = await chat.ainvoke(messages)
except httpx.ConnectError as e:
    self._logger.error("Ollama server connection failed", exception=e, request_id=request.request_id)
    raise OllamaConnectionError(f"Cannot connect to Ollama at {self._base_url}") from e
except httpx.TimeoutException as e:
    self._logger.error("Ollama request timeout", exception=e, request_id=request.request_id)
    raise OllamaTimeoutError(str(e)) from e
except Exception as e:
    if "model" in str(e).lower() and "not found" in str(e).lower():
        self._logger.error("Ollama model not found", exception=e, request_id=request.request_id)
        raise OllamaModelNotFoundError(str(e)) from e
    self._logger.error("Ollama request failed", exception=e, request_id=request.request_id)
    raise OllamaLLMError(str(e)) from e


6. 설정 (Configuration)
6.1 환경변수
python
# config/settings.py 추가

class OllamaSettings(BaseSettings):
    """Ollama 설정"""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_DEFAULT_MODEL: str = "llama3.2"
    OLLAMA_MAX_TOKENS: int = 4096
    OLLAMA_TEMPERATURE: float = 0.7
    OLLAMA_TIMEOUT: int = 120  # 로컬 모델은 더 긴 타임아웃 필요

6.2 의존성 주입
python
def get_ollama_client() -> OllamaClient:
    """OllamaClient 팩토리"""
    settings = get_settings()
    logger = get_logger()
    return OllamaClient(
        base_url=settings.ollama_base_url,
        logger=logger,
        timeout=settings.ollama_timeout,
    )


7. 테스트 시나리오
7.1 단위 테스트 (Mock 사용)
python
# tests/infrastructure/llm/test_ollama_client.py

@pytest.fixture
def mock_logger():
    return Mock(spec=LoggerInterface)

@pytest.fixture
def ollama_client(mock_logger):
    return OllamaClient(base_url="http://localhost:11434", logger=mock_logger)

@pytest.mark.asyncio
async def test_complete_success(ollama_client, mock_logger):
    """정상 응답 테스트"""

@pytest.mark.asyncio
async def test_complete_connection_error(ollama_client, mock_logger):
    """연결 실패 테스트"""

@pytest.mark.asyncio
async def test_complete_model_not_found(ollama_client, mock_logger):
    """모델 없음 테스트"""

@pytest.mark.asyncio
async def test_stream_complete_success(ollama_client, mock_logger):
    """스트리밍 정상 응답 테스트"""

@pytest.mark.asyncio
async def test_complete_logs_request_start(ollama_client, mock_logger):
    """요청 시작 로그 검증"""

@pytest.mark.asyncio
async def test_complete_with_string_model(ollama_client, mock_logger):
    """임의 문자열 모델명 허용 테스트"""

7.2 통합 테스트 (실제 Ollama 서버)
python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_ollama_call():
    """실제 Ollama 서버 호출 (OLLAMA_BASE_URL 설정 시)"""
    import os
    base_url = os.getenv("OLLAMA_BASE_URL", "")
    if not base_url:
        pytest.skip("OLLAMA_BASE_URL not set")


8. 체크리스트
개발 전
 LOG-001 (task-logging.md) 읽기
 langchain-ollama 패키지 설치 확인
 Ollama 서버 로컬 실행 확인 (ollama serve)

구현 시
 OllamaClient 구현
 요청/응답 스키마 정의
 예외 클래스 정의
 로깅 적용 (INFO/ERROR)
 스트리밍 구현

테스트
 Mock 기반 단위 테스트
 연결 실패 에러 테스트
 타임아웃 테스트
 모델 없음 에러 테스트
 임의 문자열 모델명 테스트

문서화
 지원 모델 목록 명시
 환경변수 문서화
 에러 핸들링 가이드


9. 금지 사항

❌ domain 규칙 포함 금지 (순수 API 클라이언트)
❌ print() 사용 금지 (logger 필수)
❌ 스택 트레이스 없는 에러 로그 금지
❌ Ollama base_url 하드코딩 금지


10. 참고사항
10.1 Ollama vs Claude 비교

| 항목 | Claude (LLM-001) | Ollama (OLLAMA-001) |
|------|-----------------|---------------------|
| API 키 | 필수 | 불필요 (로컬) |
| 타임아웃 | 60s | 120s (모델 크기에 따라 더 길게) |
| 재시도 | tenacity 3회 | 연결 실패 시 즉시 실패 |
| 토큰 추적 | usage_metadata | response_metadata |

10.2 모델 설치 안내
bash
# Ollama 서버 실행
ollama serve

# 모델 다운로드
ollama pull llama3.2
ollama pull mistral
ollama pull gemma2

10.3 Application Layer 사용 예시
python
class ChatUseCase:
    def __init__(self, ollama_client: OllamaClient, logger: LoggerInterface):
        self._ollama = ollama_client
        self._logger = logger

    async def process_query(self, query: str, request_id: str) -> str:
        request = OllamaRequest(
            model=OllamaModel.LLAMA3_2,
            messages=[{"role": "user", "content": query}],
            temperature=0.3,
            request_id=request_id,
        )
        response = await self._ollama.complete(request)
        return response.content
