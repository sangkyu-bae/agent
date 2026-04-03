"""Code Execution Result ValueObject.

코드 실행 결과를 나타내는 불변 객체입니다.
"""

from dataclasses import dataclass
from enum import Enum


class ExecutionStatus(Enum):
    """코드 실행 상태."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    FORBIDDEN_MODULE = "forbidden_module"
    FORBIDDEN_BUILTIN = "forbidden_builtin"
    CODE_TOO_LONG = "code_too_long"
    SYNTAX_ERROR = "syntax_error"


@dataclass(frozen=True)
class CodeExecutionResult:
    """코드 실행 결과 ValueObject.

    Attributes:
        status: 실행 상태
        output: 실행 출력 (stdout)
        error_message: 에러 메시지 (실패 시)
    """

    status: ExecutionStatus
    output: str
    error_message: str | None = None

    @property
    def is_success(self) -> bool:
        """실행 성공 여부."""
        return self.status == ExecutionStatus.SUCCESS

    def to_tool_output(self) -> str:
        """LangGraph 도구 출력 형식으로 변환.

        Returns:
            도구 출력 문자열
        """
        if self.is_success:
            if self.output:
                return f"[Execution Success]\n{self.output}"
            return "[Execution Success] (no output)"

        status_messages = {
            ExecutionStatus.ERROR: "Runtime Error",
            ExecutionStatus.TIMEOUT: "Timeout",
            ExecutionStatus.FORBIDDEN_MODULE: "Forbidden Module",
            ExecutionStatus.FORBIDDEN_BUILTIN: "Forbidden Builtin",
            ExecutionStatus.CODE_TOO_LONG: "Code Too Long",
            ExecutionStatus.SYNTAX_ERROR: "Syntax Error",
        }
        status_msg = status_messages.get(self.status, "Error")
        return f"[Execution {status_msg}]\n{self.error_message or 'Unknown error'}"

    @classmethod
    def success(cls, output: str) -> "CodeExecutionResult":
        """성공 결과 생성.

        Args:
            output: 실행 출력

        Returns:
            성공 결과
        """
        return cls(status=ExecutionStatus.SUCCESS, output=output)

    @classmethod
    def error(cls, error_message: str) -> "CodeExecutionResult":
        """에러 결과 생성.

        Args:
            error_message: 에러 메시지

        Returns:
            에러 결과
        """
        return cls(
            status=ExecutionStatus.ERROR,
            output="",
            error_message=error_message,
        )

    @classmethod
    def timeout(cls, seconds: int) -> "CodeExecutionResult":
        """타임아웃 결과 생성.

        Args:
            seconds: 타임아웃 시간(초)

        Returns:
            타임아웃 결과
        """
        return cls(
            status=ExecutionStatus.TIMEOUT,
            output="",
            error_message=f"Execution timed out after {seconds} seconds",
        )

    @classmethod
    def forbidden_module(cls, module_name: str) -> "CodeExecutionResult":
        """금지된 모듈 결과 생성.

        Args:
            module_name: 금지된 모듈 이름

        Returns:
            금지된 모듈 결과
        """
        return cls(
            status=ExecutionStatus.FORBIDDEN_MODULE,
            output="",
            error_message=f"Module '{module_name}' is not allowed",
        )

    @classmethod
    def forbidden_builtin(cls, builtin_name: str) -> "CodeExecutionResult":
        """금지된 빌트인 결과 생성.

        Args:
            builtin_name: 금지된 빌트인 이름

        Returns:
            금지된 빌트인 결과
        """
        return cls(
            status=ExecutionStatus.FORBIDDEN_BUILTIN,
            output="",
            error_message=f"Builtin '{builtin_name}' is not allowed",
        )

    @classmethod
    def code_too_long(cls, max_length: int, actual_length: int) -> "CodeExecutionResult":
        """코드 길이 초과 결과 생성.

        Args:
            max_length: 최대 허용 길이
            actual_length: 실제 코드 길이

        Returns:
            코드 길이 초과 결과
        """
        return cls(
            status=ExecutionStatus.CODE_TOO_LONG,
            output="",
            error_message=f"Code length {actual_length} exceeds maximum {max_length} characters",
        )

    @classmethod
    def syntax_error(cls, error_message: str) -> "CodeExecutionResult":
        """문법 에러 결과 생성.

        Args:
            error_message: 문법 에러 메시지

        Returns:
            문법 에러 결과
        """
        return cls(
            status=ExecutionStatus.SYNTAX_ERROR,
            output="",
            error_message=error_message,
        )
