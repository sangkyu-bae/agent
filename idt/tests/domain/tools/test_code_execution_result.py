"""Tests for CodeExecutionResult ValueObject.

코드 실행 결과를 나타내는 ValueObject 테스트입니다.
"""

import pytest

from src.domain.tools.code_execution_result import (
    CodeExecutionResult,
    ExecutionStatus,
)


class TestExecutionStatus:
    """ExecutionStatus enum 테스트."""

    def test_success_value(self):
        """SUCCESS 상태값 확인."""
        assert ExecutionStatus.SUCCESS.value == "success"

    def test_error_value(self):
        """ERROR 상태값 확인."""
        assert ExecutionStatus.ERROR.value == "error"

    def test_timeout_value(self):
        """TIMEOUT 상태값 확인."""
        assert ExecutionStatus.TIMEOUT.value == "timeout"

    def test_forbidden_module_value(self):
        """FORBIDDEN_MODULE 상태값 확인."""
        assert ExecutionStatus.FORBIDDEN_MODULE.value == "forbidden_module"

    def test_forbidden_builtin_value(self):
        """FORBIDDEN_BUILTIN 상태값 확인."""
        assert ExecutionStatus.FORBIDDEN_BUILTIN.value == "forbidden_builtin"

    def test_code_too_long_value(self):
        """CODE_TOO_LONG 상태값 확인."""
        assert ExecutionStatus.CODE_TOO_LONG.value == "code_too_long"

    def test_syntax_error_value(self):
        """SYNTAX_ERROR 상태값 확인."""
        assert ExecutionStatus.SYNTAX_ERROR.value == "syntax_error"


class TestCodeExecutionResultCreation:
    """CodeExecutionResult 생성 테스트."""

    def test_create_success_result(self):
        """성공 결과 생성."""
        result = CodeExecutionResult(
            status=ExecutionStatus.SUCCESS,
            output="42",
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert result.output == "42"
        assert result.error_message is None

    def test_create_error_result(self):
        """에러 결과 생성."""
        result = CodeExecutionResult(
            status=ExecutionStatus.ERROR,
            output="",
            error_message="ZeroDivisionError: division by zero",
        )
        assert result.status == ExecutionStatus.ERROR
        assert result.output == ""
        assert result.error_message == "ZeroDivisionError: division by zero"

    def test_create_timeout_result(self):
        """타임아웃 결과 생성."""
        result = CodeExecutionResult(
            status=ExecutionStatus.TIMEOUT,
            output="",
            error_message="Execution timed out after 5 seconds",
        )
        assert result.status == ExecutionStatus.TIMEOUT
        assert "timed out" in result.error_message

    def test_create_forbidden_module_result(self):
        """금지된 모듈 결과 생성."""
        result = CodeExecutionResult(
            status=ExecutionStatus.FORBIDDEN_MODULE,
            output="",
            error_message="Module 'os' is not allowed",
        )
        assert result.status == ExecutionStatus.FORBIDDEN_MODULE
        assert "os" in result.error_message

    def test_create_forbidden_builtin_result(self):
        """금지된 빌트인 결과 생성."""
        result = CodeExecutionResult(
            status=ExecutionStatus.FORBIDDEN_BUILTIN,
            output="",
            error_message="Builtin 'eval' is not allowed",
        )
        assert result.status == ExecutionStatus.FORBIDDEN_BUILTIN
        assert "eval" in result.error_message

    def test_create_code_too_long_result(self):
        """코드 길이 초과 결과 생성."""
        result = CodeExecutionResult(
            status=ExecutionStatus.CODE_TOO_LONG,
            output="",
            error_message="Code exceeds maximum length of 5000 characters",
        )
        assert result.status == ExecutionStatus.CODE_TOO_LONG
        assert "5000" in result.error_message

    def test_create_syntax_error_result(self):
        """문법 에러 결과 생성."""
        result = CodeExecutionResult(
            status=ExecutionStatus.SYNTAX_ERROR,
            output="",
            error_message="SyntaxError: invalid syntax",
        )
        assert result.status == ExecutionStatus.SYNTAX_ERROR
        assert "SyntaxError" in result.error_message


class TestCodeExecutionResultIsSuccess:
    """is_success 프로퍼티 테스트."""

    def test_success_is_success(self):
        """SUCCESS 상태는 성공이다."""
        result = CodeExecutionResult(
            status=ExecutionStatus.SUCCESS,
            output="result",
        )
        assert result.is_success is True

    def test_error_is_not_success(self):
        """ERROR 상태는 성공이 아니다."""
        result = CodeExecutionResult(
            status=ExecutionStatus.ERROR,
            output="",
            error_message="error",
        )
        assert result.is_success is False

    def test_timeout_is_not_success(self):
        """TIMEOUT 상태는 성공이 아니다."""
        result = CodeExecutionResult(
            status=ExecutionStatus.TIMEOUT,
            output="",
            error_message="timeout",
        )
        assert result.is_success is False

    def test_forbidden_module_is_not_success(self):
        """FORBIDDEN_MODULE 상태는 성공이 아니다."""
        result = CodeExecutionResult(
            status=ExecutionStatus.FORBIDDEN_MODULE,
            output="",
            error_message="forbidden",
        )
        assert result.is_success is False


class TestCodeExecutionResultToToolOutput:
    """to_tool_output 메서드 테스트."""

    def test_success_output(self):
        """성공 시 출력 포맷."""
        result = CodeExecutionResult(
            status=ExecutionStatus.SUCCESS,
            output="Hello, World!",
        )
        output = result.to_tool_output()
        assert "success" in output.lower()
        assert "Hello, World!" in output

    def test_error_output(self):
        """에러 시 출력 포맷."""
        result = CodeExecutionResult(
            status=ExecutionStatus.ERROR,
            output="",
            error_message="NameError: name 'x' is not defined",
        )
        output = result.to_tool_output()
        assert "error" in output.lower()
        assert "NameError" in output

    def test_timeout_output(self):
        """타임아웃 시 출력 포맷."""
        result = CodeExecutionResult(
            status=ExecutionStatus.TIMEOUT,
            output="",
            error_message="Execution timed out after 5 seconds",
        )
        output = result.to_tool_output()
        assert "timeout" in output.lower()
        assert "5 seconds" in output

    def test_forbidden_module_output(self):
        """금지된 모듈 시 출력 포맷."""
        result = CodeExecutionResult(
            status=ExecutionStatus.FORBIDDEN_MODULE,
            output="",
            error_message="Module 'subprocess' is not allowed",
        )
        output = result.to_tool_output()
        assert "forbidden" in output.lower() or "not allowed" in output.lower()
        assert "subprocess" in output

    def test_success_with_partial_output(self):
        """성공 + 부분 출력 시 포맷."""
        result = CodeExecutionResult(
            status=ExecutionStatus.SUCCESS,
            output="Line 1\nLine 2\nLine 3",
        )
        output = result.to_tool_output()
        assert "Line 1" in output
        assert "Line 2" in output
        assert "Line 3" in output

    def test_empty_output_on_success(self):
        """성공했지만 출력이 없을 때."""
        result = CodeExecutionResult(
            status=ExecutionStatus.SUCCESS,
            output="",
        )
        output = result.to_tool_output()
        assert "success" in output.lower()


class TestCodeExecutionResultFactoryMethods:
    """팩토리 메서드 테스트."""

    def test_success_factory(self):
        """success 팩토리 메서드."""
        result = CodeExecutionResult.success("42")
        assert result.status == ExecutionStatus.SUCCESS
        assert result.output == "42"
        assert result.error_message is None

    def test_error_factory(self):
        """error 팩토리 메서드."""
        result = CodeExecutionResult.error("ZeroDivisionError")
        assert result.status == ExecutionStatus.ERROR
        assert result.error_message == "ZeroDivisionError"

    def test_timeout_factory(self):
        """timeout 팩토리 메서드."""
        result = CodeExecutionResult.timeout(5)
        assert result.status == ExecutionStatus.TIMEOUT
        assert "5" in result.error_message

    def test_forbidden_module_factory(self):
        """forbidden_module 팩토리 메서드."""
        result = CodeExecutionResult.forbidden_module("os")
        assert result.status == ExecutionStatus.FORBIDDEN_MODULE
        assert "os" in result.error_message

    def test_forbidden_builtin_factory(self):
        """forbidden_builtin 팩토리 메서드."""
        result = CodeExecutionResult.forbidden_builtin("eval")
        assert result.status == ExecutionStatus.FORBIDDEN_BUILTIN
        assert "eval" in result.error_message

    def test_code_too_long_factory(self):
        """code_too_long 팩토리 메서드."""
        result = CodeExecutionResult.code_too_long(5000, 6000)
        assert result.status == ExecutionStatus.CODE_TOO_LONG
        assert "5000" in result.error_message
        assert "6000" in result.error_message

    def test_syntax_error_factory(self):
        """syntax_error 팩토리 메서드."""
        result = CodeExecutionResult.syntax_error("invalid syntax at line 1")
        assert result.status == ExecutionStatus.SYNTAX_ERROR
        assert "invalid syntax" in result.error_message
