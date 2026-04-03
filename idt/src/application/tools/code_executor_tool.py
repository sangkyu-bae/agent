"""Code Executor Tool for LangGraph.

LangGraph Agent에서 사용할 Python 코드 실행 도구를 생성합니다.
"""

import uuid
from typing import Type

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tools.code_executor_policy import CodeExecutorPolicy
from src.infrastructure.tools.sandbox_executor import SandboxExecutor


class CodeExecutorInput(BaseModel):
    """코드 실행 도구 입력 스키마."""

    code: str = Field(
        description="The Python code to execute in the sandbox environment"
    )


class CodeExecutorToolFactory:
    """코드 실행 도구 팩토리.

    LangGraph Agent에서 사용할 Python 코드 실행 도구를 생성합니다.
    """

    TOOL_NAME = "python_code_executor"

    TOOL_DESCRIPTION = (
        "Execute Python code in a secure sandbox environment. "
        "Allowed modules: math, statistics, decimal, fractions, datetime, "
        "json, re, collections, itertools, functools. "
        "Forbidden operations: file I/O, network access, system commands, "
        "eval/exec/compile. "
        "Maximum execution time: 5 seconds. "
        "Use this tool for calculations, data processing, and algorithmic tasks."
    )

    @classmethod
    def create(cls, logger: LoggerInterface) -> BaseTool:
        """코드 실행 도구 생성.

        Args:
            logger: 로거 인터페이스

        Returns:
            LangGraph에서 사용할 수 있는 코드 실행 도구
        """
        executor = SandboxExecutor(logger=logger)

        def execute_code(code: str) -> str:
            """Python 코드를 샌드박스에서 실행합니다.

            Args:
                code: 실행할 Python 코드

            Returns:
                실행 결과 문자열
            """
            request_id = str(uuid.uuid4())
            result = executor.execute(code=code, request_id=request_id)
            return result.to_tool_output()

        tool = StructuredTool.from_function(
            func=execute_code,
            name=cls.TOOL_NAME,
            description=cls.TOOL_DESCRIPTION,
            args_schema=CodeExecutorInput,
        )

        return tool


def create_code_executor_tool(logger: LoggerInterface) -> BaseTool:
    """코드 실행 도구 생성 편의 함수.

    Args:
        logger: 로거 인터페이스

    Returns:
        LangGraph에서 사용할 수 있는 코드 실행 도구
    """
    return CodeExecutorToolFactory.create(logger=logger)
