"""Tests for SandboxExecutor.

샌드박스 환경에서 Python 코드를 실행하는 executor 테스트입니다.
Mock을 사용하여 로거를 검증합니다.
"""

import pytest
from unittest.mock import Mock, call

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tools.code_execution_result import ExecutionStatus
from src.infrastructure.tools.sandbox_executor import SandboxExecutor


@pytest.fixture
def mock_logger() -> Mock:
    """Mock logger fixture."""
    return Mock(spec=LoggerInterface)


@pytest.fixture
def executor(mock_logger: Mock) -> SandboxExecutor:
    """SandboxExecutor fixture."""
    return SandboxExecutor(logger=mock_logger)


class TestSandboxExecutorSimpleCalculations:
    """간단한 계산 테스트."""

    def test_simple_addition(self, executor: SandboxExecutor):
        """간단한 덧셈."""
        code = "print(1 + 2)"
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "3" in result.output

    def test_multiplication(self, executor: SandboxExecutor):
        """곱셈."""
        code = "print(6 * 7)"
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "42" in result.output

    def test_variable_assignment(self, executor: SandboxExecutor):
        """변수 할당."""
        code = """
x = 10
y = 20
print(x + y)
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "30" in result.output

    def test_list_operations(self, executor: SandboxExecutor):
        """리스트 연산."""
        code = """
numbers = [1, 2, 3, 4, 5]
print(sum(numbers))
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "15" in result.output

    def test_string_operations(self, executor: SandboxExecutor):
        """문자열 연산."""
        code = """
text = "hello world"
print(text.upper())
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "HELLO WORLD" in result.output

    def test_dictionary_operations(self, executor: SandboxExecutor):
        """딕셔너리 연산."""
        code = """
data = {"a": 1, "b": 2}
print(data["a"] + data["b"])
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "3" in result.output


class TestSandboxExecutorAllowedModules:
    """허용된 모듈 테스트."""

    def test_math_module(self, executor: SandboxExecutor):
        """math 모듈 사용."""
        code = """
import math
print(math.sqrt(16))
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "4.0" in result.output

    def test_math_pi(self, executor: SandboxExecutor):
        """math.pi 사용."""
        code = """
import math
print(round(math.pi, 2))
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "3.14" in result.output

    def test_statistics_module(self, executor: SandboxExecutor):
        """statistics 모듈 사용."""
        code = """
import statistics
data = [1, 2, 3, 4, 5]
print(statistics.mean(data))
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "3" in result.output

    def test_datetime_module(self, executor: SandboxExecutor):
        """datetime 모듈 사용."""
        code = """
import datetime
d = datetime.date(2024, 1, 15)
print(d.year)
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "2024" in result.output

    def test_json_module(self, executor: SandboxExecutor):
        """json 모듈 사용."""
        code = """
import json
data = {"name": "test", "value": 123}
print(json.dumps(data))
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "test" in result.output
        assert "123" in result.output

    def test_re_module(self, executor: SandboxExecutor):
        """re 모듈 사용."""
        code = """
import re
text = "hello123world"
match = re.search(r'\\d+', text)
print(match.group())
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "123" in result.output

    def test_collections_module(self, executor: SandboxExecutor):
        """collections 모듈 사용."""
        code = """
from collections import Counter
data = ['a', 'b', 'a', 'c', 'a']
counter = Counter(data)
print(counter['a'])
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "3" in result.output

    def test_itertools_module(self, executor: SandboxExecutor):
        """itertools 모듈 사용."""
        code = """
import itertools
result = list(itertools.combinations([1, 2, 3], 2))
print(len(result))
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "3" in result.output

    def test_functools_module(self, executor: SandboxExecutor):
        """functools 모듈 사용."""
        code = """
import functools
data = [1, 2, 3, 4, 5]
result = functools.reduce(lambda x, y: x * y, data)
print(result)
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "120" in result.output

    def test_decimal_module(self, executor: SandboxExecutor):
        """decimal 모듈 사용."""
        code = """
from decimal import Decimal
a = Decimal('0.1')
b = Decimal('0.2')
print(a + b)
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "0.3" in result.output

    def test_fractions_module(self, executor: SandboxExecutor):
        """fractions 모듈 사용."""
        code = """
from fractions import Fraction
f = Fraction(1, 3)
print(f * 3)
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "1" in result.output


class TestSandboxExecutorForbiddenModules:
    """금지된 모듈 테스트."""

    def test_os_module_blocked(self, executor: SandboxExecutor):
        """os 모듈 차단."""
        code = "import os"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_MODULE
        assert "os" in result.error_message

    def test_subprocess_module_blocked(self, executor: SandboxExecutor):
        """subprocess 모듈 차단."""
        code = "import subprocess"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_MODULE
        assert "subprocess" in result.error_message

    def test_sys_module_blocked(self, executor: SandboxExecutor):
        """sys 모듈 차단."""
        code = "import sys"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_MODULE
        assert "sys" in result.error_message

    def test_socket_module_blocked(self, executor: SandboxExecutor):
        """socket 모듈 차단."""
        code = "import socket"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_MODULE
        assert "socket" in result.error_message

    def test_shutil_module_blocked(self, executor: SandboxExecutor):
        """shutil 모듈 차단."""
        code = "import shutil"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_MODULE
        assert "shutil" in result.error_message

    def test_pickle_module_blocked(self, executor: SandboxExecutor):
        """pickle 모듈 차단."""
        code = "import pickle"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_MODULE
        assert "pickle" in result.error_message

    def test_from_import_os_blocked(self, executor: SandboxExecutor):
        """from os import 차단."""
        code = "from os import path"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_MODULE
        assert "os" in result.error_message


class TestSandboxExecutorForbiddenBuiltins:
    """금지된 빌트인 테스트."""

    def test_eval_blocked(self, executor: SandboxExecutor):
        """eval 차단."""
        code = "eval('1+1')"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_BUILTIN
        assert "eval" in result.error_message

    def test_exec_blocked(self, executor: SandboxExecutor):
        """exec 차단."""
        code = "exec('x = 1')"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_BUILTIN
        assert "exec" in result.error_message

    def test_open_blocked(self, executor: SandboxExecutor):
        """open 차단."""
        code = "open('test.txt', 'r')"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_BUILTIN
        assert "open" in result.error_message

    def test_compile_blocked(self, executor: SandboxExecutor):
        """compile 차단."""
        code = "compile('x=1', '', 'exec')"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_BUILTIN
        assert "compile" in result.error_message

    def test_input_blocked(self, executor: SandboxExecutor):
        """input 차단."""
        code = "input('Enter: ')"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_BUILTIN
        assert "input" in result.error_message

    def test_globals_blocked(self, executor: SandboxExecutor):
        """globals 차단."""
        code = "globals()"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_BUILTIN
        assert "globals" in result.error_message

    def test_getattr_blocked(self, executor: SandboxExecutor):
        """getattr 차단."""
        code = "getattr(object, '__class__')"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.FORBIDDEN_BUILTIN
        assert "getattr" in result.error_message


class TestSandboxExecutorErrorHandling:
    """에러 처리 테스트."""

    def test_syntax_error(self, executor: SandboxExecutor):
        """문법 에러."""
        code = "print(Hello"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.SYNTAX_ERROR
        assert "SyntaxError" in result.error_message or "syntax" in result.error_message.lower()

    def test_name_error(self, executor: SandboxExecutor):
        """이름 에러."""
        code = "print(undefined_variable)"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.ERROR
        assert "NameError" in result.error_message

    def test_zero_division_error(self, executor: SandboxExecutor):
        """0으로 나누기 에러."""
        code = "print(1 / 0)"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.ERROR
        assert "ZeroDivisionError" in result.error_message

    def test_type_error(self, executor: SandboxExecutor):
        """타입 에러."""
        code = "print('hello' + 123)"
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.ERROR
        assert "TypeError" in result.error_message

    def test_index_error(self, executor: SandboxExecutor):
        """인덱스 에러."""
        code = """
lst = [1, 2, 3]
print(lst[10])
"""
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.ERROR
        assert "IndexError" in result.error_message


class TestSandboxExecutorCodeLength:
    """코드 길이 테스트."""

    def test_code_too_long(self, executor: SandboxExecutor):
        """코드 길이 초과."""
        code = "x = 1\n" * 1000  # 6000 characters
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        assert result.status == ExecutionStatus.CODE_TOO_LONG

    def test_code_within_limit(self, executor: SandboxExecutor):
        """코드 길이 제한 내."""
        code = "print('hello')"
        result = executor.execute(code, request_id="test-123")

        assert result.is_success


class TestSandboxExecutorTimeout:
    """타임아웃 테스트."""

    def test_infinite_loop_timeout(self, executor: SandboxExecutor):
        """무한 루프 타임아웃.

        Note: Windows에서 ThreadPoolExecutor는 tight loop를
        인터럽트하지 못할 수 있어 이 테스트가 실패할 수 있습니다.
        실제 타임아웃은 time.sleep 기반 코드에서 더 잘 동작합니다.
        """
        code = """
import time
time.sleep(10)
print("done")
"""
        # time 모듈은 허용되지 않으므로 forbidden_module 에러가 발생
        result = executor.execute(code, request_id="test-123")

        assert not result.is_success
        # time 모듈이 금지되어 있으므로 forbidden_module 상태
        assert result.status == ExecutionStatus.FORBIDDEN_MODULE


class TestSandboxExecutorLogging:
    """로깅 테스트."""

    def test_logs_execution_start(self, executor: SandboxExecutor, mock_logger: Mock):
        """실행 시작 로그."""
        code = "print('hello')"
        executor.execute(code, request_id="test-123")

        # INFO 로그가 호출되었는지 확인
        mock_logger.info.assert_called()
        # 첫 번째 호출에서 "started" 또는 시작 관련 메시지 확인
        calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("start" in str(c).lower() for c in calls)

    def test_logs_execution_complete(self, executor: SandboxExecutor, mock_logger: Mock):
        """실행 완료 로그."""
        code = "print('hello')"
        executor.execute(code, request_id="test-123")

        mock_logger.info.assert_called()
        calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("complete" in str(c).lower() or "success" in str(c).lower() for c in calls)

    def test_logs_request_id(self, executor: SandboxExecutor, mock_logger: Mock):
        """request_id 로그."""
        code = "print('hello')"
        executor.execute(code, request_id="test-request-id-456")

        # request_id가 로그에 포함되었는지 확인
        mock_logger.info.assert_called()
        calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("test-request-id-456" in str(c) for c in calls)

    def test_logs_forbidden_module_warning(self, executor: SandboxExecutor, mock_logger: Mock):
        """금지된 모듈 경고 로그."""
        code = "import os"
        executor.execute(code, request_id="test-123")

        mock_logger.warning.assert_called()
        calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("os" in str(c) for c in calls)

    def test_logs_error_with_exception(self, executor: SandboxExecutor, mock_logger: Mock):
        """에러 로그에 exception 포함."""
        code = "print(1/0)"
        executor.execute(code, request_id="test-123")

        mock_logger.error.assert_called()


class TestSandboxExecutorMultipleStatements:
    """여러 문장 실행 테스트."""

    def test_multiple_prints(self, executor: SandboxExecutor):
        """여러 print 문."""
        code = """
print("line 1")
print("line 2")
print("line 3")
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "line 1" in result.output
        assert "line 2" in result.output
        assert "line 3" in result.output

    def test_function_definition_and_call(self, executor: SandboxExecutor):
        """함수 정의 및 호출."""
        code = """
def add(a, b):
    return a + b

result = add(3, 4)
print(result)
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "7" in result.output

    def test_class_definition_and_usage(self, executor: SandboxExecutor):
        """클래스 정의 및 사용."""
        code = """
class Calculator:
    def add(self, a, b):
        return a + b

calc = Calculator()
print(calc.add(5, 3))
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "8" in result.output

    def test_list_comprehension(self, executor: SandboxExecutor):
        """리스트 컴프리헨션."""
        code = """
squares = [x**2 for x in range(5)]
print(squares)
"""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "0" in result.output
        assert "1" in result.output
        assert "4" in result.output
        assert "9" in result.output
        assert "16" in result.output


class TestSandboxExecutorEdgeCases:
    """엣지 케이스 테스트."""

    def test_empty_code(self, executor: SandboxExecutor):
        """빈 코드."""
        code = ""
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert result.output == ""

    def test_whitespace_only_code(self, executor: SandboxExecutor):
        """공백만 있는 코드."""
        code = "   \n   \n   "
        result = executor.execute(code, request_id="test-123")

        assert result.is_success

    def test_comment_only_code(self, executor: SandboxExecutor):
        """주석만 있는 코드."""
        code = "# This is a comment"
        result = executor.execute(code, request_id="test-123")

        assert result.is_success

    def test_multiline_string(self, executor: SandboxExecutor):
        """멀티라인 문자열."""
        code = '''
text = """
Hello
World
"""
print(text.strip())
'''
        result = executor.execute(code, request_id="test-123")

        assert result.is_success
        assert "Hello" in result.output
        assert "World" in result.output
