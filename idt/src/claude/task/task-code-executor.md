# Task: Python Code Executor Tool

> Task ID: CODE-001  
> 작성일: 2025-02-04  
> 의존성: LOG-001 (로깅 필수)  
> 상태: Draft

---

## 1. 개요

### 1.1 목적

LangGraph Agent가 사용할 수 있는 Python 코드 실행 도구(Tool)를 구현한다.
사용자 질의에 대해 계산, 데이터 처리, 분석이 필요한 경우 Agent가 Python 코드를 생성하고 실행할 수 있도록 한다.

### 1.2 사용 시나리오

- 수치 계산 (금리 계산, 복리 계산, 통계 분석)
- 데이터 변환 (JSON 파싱, 날짜 계산, 단위 변환)
- 간단한 데이터 분석 (평균, 합계, 필터링)
- 문서에서 추출한 수치 기반 연산

### 1.3 범위

**포함:**
- 샌드박스 환경에서의 Python 코드 실행
- 실행 시간 제한 (timeout)
- 메모리 제한
- 허용된 모듈만 import 가능
- 실행 결과 반환

**제외:**
- 파일 시스템 접근
- 네트워크 접근
- 시스템 명령어 실행
- 외부 패키지 설치

---

## 2. 아키텍처 설계

### 2.1 레이어 배치

```
domain/
├── tools/
│   ├── code_executor_policy.py    # 실행 정책 (허용 모듈, 제한 규칙)
│   └── code_execution_result.py   # 실행 결과 ValueObject

application/
├── tools/
│   └── code_executor_tool.py      # LangGraph Tool 정의

infrastructure/
├── tools/
│   └── sandbox_executor.py        # 실제 샌드박스 실행 구현
```

### 2.2 의존성 방향

```
interfaces → application → domain
                ↓
          infrastructure
```

---

## 3. Domain Layer

### 3.1 코드 실행 정책 (CodeExecutorPolicy)

```python
# domain/tools/code_executor_policy.py
from dataclasses import dataclass
from typing import FrozenSet

@dataclass(frozen=True)
class CodeExecutorPolicy:
    """코드 실행 정책 - 불변 객체"""
    
    # 허용된 내장 모듈
    ALLOWED_MODULES: FrozenSet[str] = frozenset({
        "math",
        "statistics",
        "decimal",
        "fractions",
        "datetime",
        "json",
        "re",
        "collections",
        "itertools",
        "functools",
    })
    
    # 금지된 내장 함수
    FORBIDDEN_BUILTINS: FrozenSet[str] = frozenset({
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "__import__",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
    })
    
    # 실행 제한
    MAX_EXECUTION_TIME_SECONDS: int = 5
    MAX_MEMORY_MB: int = 50
    MAX_OUTPUT_LENGTH: int = 10000
    MAX_CODE_LENGTH: int = 5000
    
    def is_module_allowed(self, module_name: str) -> bool:
        """모듈 허용 여부 검사"""
        base_module = module_name.split(".")[0]
        return base_module in self.ALLOWED_MODULES
    
    def is_builtin_allowed(self, builtin_name: str) -> bool:
        """내장 함수 허용 여부 검사"""
        return builtin_name not in self.FORBIDDEN_BUILTINS
    
    def validate_code_length(self, code: str) -> bool:
        """코드 길이 검증"""
        return len(code) <= self.MAX_CODE_LENGTH
```

### 3.2 실행 결과 ValueObject

```python
# domain/tools/code_execution_result.py
from dataclasses import dataclass
from typing import Optional, Any
from enum import Enum

class ExecutionStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    SECURITY_VIOLATION = "security_violation"

@dataclass(frozen=True)
class CodeExecutionResult:
    """코드 실행 결과 - 불변 객체"""
    
    status: ExecutionStatus
    output: Optional[str] = None
    return_value: Optional[Any] = None
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
    
    @property
    def is_success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS
    
    def to_tool_output(self) -> str:
        """LangGraph Tool 출력 형식으로 변환"""
        if self.is_success:
            result_parts = []
            if self.output:
                result_parts.append(f"Output:\n{self.output}")
            if self.return_value is not None:
                result_parts.append(f"Return Value: {self.return_value}")
            return "\n".join(result_parts) if result_parts else "Code executed successfully (no output)"
        else:
            return f"Execution Failed [{self.status.value}]: {self.error_message}"
```

---

## 4. Infrastructure Layer

### 4.1 샌드박스 실행기

```python
# infrastructure/tools/sandbox_executor.py
import ast
import sys
import traceback
from io import StringIO
from typing import Dict, Any
from contextlib import redirect_stdout, redirect_stderr
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from domain.tools.code_executor_policy import CodeExecutorPolicy
from domain.tools.code_execution_result import CodeExecutionResult, ExecutionStatus
from domain.logging.logger_interface import LoggerInterface

class SandboxExecutor:
    """샌드박스 환경에서 Python 코드 실행"""
    
    def __init__(self, policy: CodeExecutorPolicy, logger: LoggerInterface):
        self._policy = policy
        self._logger = logger
    
    def execute(self, code: str, request_id: str) -> CodeExecutionResult:
        """코드 실행 메인 메서드"""
        self._logger.info(
            "Code execution started",
            request_id=request_id,
            code_length=len(code)
        )
        
        # 1. 코드 길이 검증
        if not self._policy.validate_code_length(code):
            self._logger.warning(
                "Code length exceeded",
                request_id=request_id,
                code_length=len(code),
                max_length=self._policy.MAX_CODE_LENGTH
            )
            return CodeExecutionResult(
                status=ExecutionStatus.SECURITY_VIOLATION,
                error_message=f"Code length exceeds maximum ({self._policy.MAX_CODE_LENGTH} chars)"
            )
        
        # 2. 정적 분석 (import 검사)
        validation_result = self._validate_code_safety(code, request_id)
        if validation_result is not None:
            return validation_result
        
        # 3. 샌드박스 실행
        return self._execute_in_sandbox(code, request_id)
    
    def _validate_code_safety(self, code: str, request_id: str) -> CodeExecutionResult | None:
        """AST 기반 정적 분석으로 보안 검사"""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            self._logger.warning(
                "Code syntax error",
                request_id=request_id,
                error=str(e)
            )
            return CodeExecutionResult(
                status=ExecutionStatus.ERROR,
                error_message=f"Syntax Error: {e}"
            )
        
        for node in ast.walk(tree):
            # import 검사
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not self._policy.is_module_allowed(alias.name):
                        self._logger.warning(
                            "Forbidden module import attempted",
                            request_id=request_id,
                            module=alias.name
                        )
                        return CodeExecutionResult(
                            status=ExecutionStatus.SECURITY_VIOLATION,
                            error_message=f"Module '{alias.name}' is not allowed"
                        )
            
            # from ... import 검사
            elif isinstance(node, ast.ImportFrom):
                if node.module and not self._policy.is_module_allowed(node.module):
                    self._logger.warning(
                        "Forbidden module import attempted",
                        request_id=request_id,
                        module=node.module
                    )
                    return CodeExecutionResult(
                        status=ExecutionStatus.SECURITY_VIOLATION,
                        error_message=f"Module '{node.module}' is not allowed"
                    )
        
        return None  # 검증 통과
    
    def _execute_in_sandbox(self, code: str, request_id: str) -> CodeExecutionResult:
        """제한된 환경에서 코드 실행"""
        import time
        start_time = time.time()
        
        # 안전한 내장 함수만 포함
        safe_builtins = {
            name: getattr(__builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__, name, None)
            for name in dir(__builtins__ if isinstance(__builtins__, dict) else __builtins__)
            if self._policy.is_builtin_allowed(name) and not name.startswith('_')
        }
        
        # 허용된 모듈 미리 import
        allowed_globals: Dict[str, Any] = {"__builtins__": safe_builtins}
        for module_name in self._policy.ALLOWED_MODULES:
            try:
                allowed_globals[module_name] = __import__(module_name)
            except ImportError:
                pass
        
        # 실행 결과 캡처용
        local_vars: Dict[str, Any] = {}
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        
        def run_code():
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(code, allowed_globals, local_vars)
        
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_code)
                future.result(timeout=self._policy.MAX_EXECUTION_TIME_SECONDS)
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            output = stdout_capture.getvalue()
            
            # 출력 길이 제한
            if len(output) > self._policy.MAX_OUTPUT_LENGTH:
                output = output[:self._policy.MAX_OUTPUT_LENGTH] + "\n... (output truncated)"
            
            # result 변수가 있으면 반환값으로 사용
            return_value = local_vars.get("result")
            
            self._logger.info(
                "Code execution completed",
                request_id=request_id,
                execution_time_ms=execution_time_ms,
                has_output=bool(output),
                has_return_value=return_value is not None
            )
            
            return CodeExecutionResult(
                status=ExecutionStatus.SUCCESS,
                output=output if output else None,
                return_value=return_value,
                execution_time_ms=execution_time_ms
            )
        
        except FuturesTimeoutError:
            self._logger.warning(
                "Code execution timeout",
                request_id=request_id,
                timeout_seconds=self._policy.MAX_EXECUTION_TIME_SECONDS
            )
            return CodeExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                error_message=f"Execution timed out after {self._policy.MAX_EXECUTION_TIME_SECONDS} seconds"
            )
        
        except Exception as e:
            self._logger.error(
                "Code execution failed",
                request_id=request_id,
                exception=e
            )
            return CodeExecutionResult(
                status=ExecutionStatus.ERROR,
                error_message=f"{type(e).__name__}: {str(e)}"
            )
```

---

## 5. Application Layer

### 5.1 LangGraph Tool 정의

```python
# application/tools/code_executor_tool.py
from langchain_core.tools import tool
from typing import Annotated

from domain.tools.code_executor_policy import CodeExecutorPolicy
from domain.tools.code_execution_result import CodeExecutionResult
from domain.logging.logger_interface import LoggerInterface
from infrastructure.tools.sandbox_executor import SandboxExecutor

class CodeExecutorToolFactory:
    """Code Executor Tool 팩토리"""
    
    def __init__(self, logger: LoggerInterface):
        self._policy = CodeExecutorPolicy()
        self._executor = SandboxExecutor(self._policy, logger)
        self._logger = logger
    
    def create_tool(self):
        """LangGraph에서 사용할 Tool 생성"""
        executor = self._executor
        
        @tool
        def execute_python_code(
            code: Annotated[str, "실행할 Python 코드. 결과를 반환하려면 'result' 변수에 할당하세요."],
            request_id: Annotated[str, "요청 추적 ID"] = "unknown"
        ) -> str:
            """
            Python 코드를 안전한 샌드박스 환경에서 실행합니다.
            
            사용 가능한 모듈: math, statistics, decimal, fractions, datetime, json, re, collections, itertools, functools
            
            제한 사항:
            - 파일 시스템 접근 불가
            - 네트워크 접근 불가
            - 실행 시간 5초 제한
            - 위험한 내장 함수 (eval, exec, open 등) 사용 불가
            
            예시:
            ```python
            import math
            result = math.sqrt(16) + 10
            ```
            
            Args:
                code: 실행할 Python 코드
                request_id: 요청 추적 ID
            
            Returns:
                실행 결과 또는 에러 메시지
            """
            execution_result: CodeExecutionResult = executor.execute(code, request_id)
            return execution_result.to_tool_output()
        
        return execute_python_code
```

### 5.2 Tool 등록 (Agent Graph에서 사용)

```python
# application/agents/tools_registry.py
from typing import List
from langchain_core.tools import BaseTool

from application.tools.code_executor_tool import CodeExecutorToolFactory
from domain.logging.logger_interface import LoggerInterface

class ToolsRegistry:
    """Agent에서 사용할 Tool 레지스트리"""
    
    def __init__(self, logger: LoggerInterface):
        self._logger = logger
    
    def get_all_tools(self) -> List[BaseTool]:
        """모든 Tool 반환"""
        tools = []
        
        # Code Executor Tool
        code_executor_factory = CodeExecutorToolFactory(self._logger)
        tools.append(code_executor_factory.create_tool())
        
        # 다른 Tool들 추가...
        
        return tools
```

---

## 6. 테스트 명세

### 6.1 Domain 테스트 (Mock 금지)

```python
# tests/domain/tools/test_code_executor_policy.py
import pytest
from domain.tools.code_executor_policy import CodeExecutorPolicy

class TestCodeExecutorPolicy:
    
    @pytest.fixture
    def policy(self):
        return CodeExecutorPolicy()
    
    def test_allowed_module_math(self, policy):
        assert policy.is_module_allowed("math") is True
    
    def test_allowed_module_statistics(self, policy):
        assert policy.is_module_allowed("statistics") is True
    
    def test_forbidden_module_os(self, policy):
        assert policy.is_module_allowed("os") is False
    
    def test_forbidden_module_subprocess(self, policy):
        assert policy.is_module_allowed("subprocess") is False
    
    def test_forbidden_module_sys(self, policy):
        assert policy.is_module_allowed("sys") is False
    
    def test_submodule_allowed(self, policy):
        # datetime.datetime 같은 서브모듈도 허용
        assert policy.is_module_allowed("datetime.datetime") is True
    
    def test_forbidden_builtin_eval(self, policy):
        assert policy.is_builtin_allowed("eval") is False
    
    def test_forbidden_builtin_exec(self, policy):
        assert policy.is_builtin_allowed("exec") is False
    
    def test_forbidden_builtin_open(self, policy):
        assert policy.is_builtin_allowed("open") is False
    
    def test_allowed_builtin_print(self, policy):
        assert policy.is_builtin_allowed("print") is True
    
    def test_allowed_builtin_len(self, policy):
        assert policy.is_builtin_allowed("len") is True
    
    def test_code_length_valid(self, policy):
        code = "x = 1"
        assert policy.validate_code_length(code) is True
    
    def test_code_length_exceeded(self, policy):
        code = "x" * 6000
        assert policy.validate_code_length(code) is False
```

### 6.2 Infrastructure 테스트 (Mock 사용)

```python
# tests/infrastructure/tools/test_sandbox_executor.py
import pytest
from unittest.mock import Mock

from domain.tools.code_executor_policy import CodeExecutorPolicy
from domain.tools.code_execution_result import ExecutionStatus
from infrastructure.tools.sandbox_executor import SandboxExecutor

class TestSandboxExecutor:
    
    @pytest.fixture
    def mock_logger(self):
        return Mock()
    
    @pytest.fixture
    def executor(self, mock_logger):
        policy = CodeExecutorPolicy()
        return SandboxExecutor(policy, mock_logger)
    
    def test_simple_calculation(self, executor):
        code = "result = 1 + 1"
        result = executor.execute(code, "test-request-1")
        
        assert result.status == ExecutionStatus.SUCCESS
        assert result.return_value == 2
    
    def test_math_module(self, executor):
        code = """
import math
result = math.sqrt(16)
"""
        result = executor.execute(code, "test-request-2")
        
        assert result.status == ExecutionStatus.SUCCESS
        assert result.return_value == 4.0
    
    def test_print_output(self, executor):
        code = 'print("Hello, World!")'
        result = executor.execute(code, "test-request-3")
        
        assert result.status == ExecutionStatus.SUCCESS
        assert "Hello, World!" in result.output
    
    def test_forbidden_module_os(self, executor):
        code = "import os"
        result = executor.execute(code, "test-request-4")
        
        assert result.status == ExecutionStatus.SECURITY_VIOLATION
        assert "os" in result.error_message
    
    def test_forbidden_module_subprocess(self, executor):
        code = "import subprocess"
        result = executor.execute(code, "test-request-5")
        
        assert result.status == ExecutionStatus.SECURITY_VIOLATION
    
    def test_forbidden_builtin_open(self, executor):
        code = 'open("/etc/passwd", "r")'
        result = executor.execute(code, "test-request-6")
        
        assert result.status == ExecutionStatus.ERROR
        # open이 safe_builtins에 없으므로 NameError 발생
    
    def test_syntax_error(self, executor):
        code = "def foo(:"
        result = executor.execute(code, "test-request-7")
        
        assert result.status == ExecutionStatus.ERROR
        assert "Syntax" in result.error_message
    
    def test_timeout(self, executor):
        code = """
import time
while True:
    pass
"""
        result = executor.execute(code, "test-request-8")
        
        assert result.status == ExecutionStatus.TIMEOUT
    
    def test_code_length_exceeded(self, executor):
        code = "x = 1\n" * 2000  # 매우 긴 코드
        result = executor.execute(code, "test-request-9")
        
        assert result.status == ExecutionStatus.SECURITY_VIOLATION
        assert "length" in result.error_message.lower()
    
    def test_statistics_module(self, executor):
        code = """
import statistics
data = [1, 2, 3, 4, 5]
result = statistics.mean(data)
"""
        result = executor.execute(code, "test-request-10")
        
        assert result.status == ExecutionStatus.SUCCESS
        assert result.return_value == 3.0
    
    def test_datetime_module(self, executor):
        code = """
import datetime
today = datetime.date.today()
result = today.year >= 2024
"""
        result = executor.execute(code, "test-request-11")
        
        assert result.status == ExecutionStatus.SUCCESS
        assert result.return_value is True
    
    def test_json_module(self, executor):
        code = """
import json
data = {"name": "test", "value": 123}
result = json.dumps(data)
"""
        result = executor.execute(code, "test-request-12")
        
        assert result.status == ExecutionStatus.SUCCESS
        assert "test" in result.return_value
```

### 6.3 Application 테스트 (통합)

```python
# tests/application/tools/test_code_executor_tool.py
import pytest
from unittest.mock import Mock

from application.tools.code_executor_tool import CodeExecutorToolFactory

class TestCodeExecutorTool:
    
    @pytest.fixture
    def mock_logger(self):
        return Mock()
    
    @pytest.fixture
    def tool(self, mock_logger):
        factory = CodeExecutorToolFactory(mock_logger)
        return factory.create_tool()
    
    def test_tool_has_correct_name(self, tool):
        assert tool.name == "execute_python_code"
    
    def test_tool_has_description(self, tool):
        assert "Python" in tool.description
        assert "샌드박스" in tool.description
    
    def test_tool_execution_success(self, tool):
        result = tool.invoke({"code": "result = 2 * 3", "request_id": "test-1"})
        assert "6" in result
    
    def test_tool_execution_with_output(self, tool):
        result = tool.invoke({"code": 'print("hello")', "request_id": "test-2"})
        assert "hello" in result
    
    def test_tool_execution_error(self, tool):
        result = tool.invoke({"code": "import os", "request_id": "test-3"})
        assert "not allowed" in result.lower() or "security" in result.lower()
```

---

## 7. 로깅 체크리스트 (LOG-001 준수)

- [x] LoggerInterface 주입 받아 사용
- [x] 주요 처리 시작/완료 INFO 로그
- [x] 예외 발생 시 ERROR 로그 + 스택 트레이스
- [x] request_id 컨텍스트 전파
- [x] 민감 정보 마스킹 (실행 코드는 length만 로깅)

---

## 8. 보안 고려사항

### 8.1 허용 목록 (Whitelist) 접근법

- 모듈: 명시적으로 허용된 모듈만 import 가능
- 내장 함수: 위험한 함수 제거한 safe_builtins 사용
- 코드 길이: 최대 5000자 제한

### 8.2 실행 환경 격리

- ThreadPoolExecutor로 타임아웃 강제
- stdout/stderr 리다이렉션으로 출력 캡처
- 별도 local_vars로 실행 컨텍스트 분리

### 8.3 추가 보안 강화 (향후)

- Docker 컨테이너 격리 (선택적)
- RestrictedPython 라이브러리 적용
- 리소스 제한 (ulimit 적용)

---

## 9. 설정값

```python
# config/tools.py
from pydantic_settings import BaseSettings

class CodeExecutorSettings(BaseSettings):
    max_execution_time_seconds: int = 5
    max_memory_mb: int = 50
    max_output_length: int = 10000
    max_code_length: int = 5000
    
    class Config:
        env_prefix = "CODE_EXECUTOR_"
```

---

## 10. 금지 사항

- ❌ os, sys, subprocess 등 시스템 모듈 허용
- ❌ 파일 시스템 접근 허용
- ❌ 네트워크 접근 허용
- ❌ eval, exec, compile 등 동적 실행 함수 허용
- ❌ 무제한 실행 시간 허용
- ❌ 실행 코드 전체를 로그에 기록 (보안상 length만)

---

## 11. 구현 순서

1. **domain 레이어**
   - [ ] CodeExecutorPolicy 구현
   - [ ] CodeExecutionResult 구현
   - [ ] 단위 테스트 작성 및 통과

2. **infrastructure 레이어**
   - [ ] SandboxExecutor 구현
   - [ ] 단위 테스트 작성 및 통과

3. **application 레이어**
   - [ ] CodeExecutorToolFactory 구현
   - [ ] 통합 테스트 작성 및 통과

4. **Agent 연동**
   - [ ] ToolsRegistry에 등록
   - [ ] Agent Graph에서 사용 가능 확인

---

## 12. 참고 자료

- LangChain Tools 문서: https://python.langchain.com/docs/modules/tools/
- Python ast 모듈: https://docs.python.org/3/library/ast.html
- RestrictedPython: https://restrictedpython.readthedocs.io/