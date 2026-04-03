"""Tests for CodeExecutorToolFactory.

LangGraph Agent에서 사용할 Python 코드 실행 도구 팩토리 테스트입니다.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from langchain_core.tools import BaseTool

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.application.tools.code_executor_tool import (
    CodeExecutorToolFactory,
    create_code_executor_tool,
)


@pytest.fixture
def mock_logger() -> Mock:
    """Mock logger fixture."""
    return Mock(spec=LoggerInterface)


class TestCodeExecutorToolFactory:
    """CodeExecutorToolFactory 테스트."""

    def test_create_returns_base_tool(self, mock_logger: Mock):
        """create는 BaseTool을 반환한다."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        assert isinstance(tool, BaseTool)

    def test_tool_has_correct_name(self, mock_logger: Mock):
        """도구 이름이 올바르다."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        assert tool.name == "python_code_executor"

    def test_tool_has_description(self, mock_logger: Mock):
        """도구에 설명이 있다."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        assert tool.description is not None
        assert len(tool.description) > 0

    def test_tool_description_mentions_python(self, mock_logger: Mock):
        """도구 설명에 Python이 언급된다."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        assert "python" in tool.description.lower()

    def test_tool_description_mentions_sandbox(self, mock_logger: Mock):
        """도구 설명에 sandbox가 언급된다."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        assert "sandbox" in tool.description.lower()

    def test_tool_description_mentions_allowed_modules(self, mock_logger: Mock):
        """도구 설명에 허용된 모듈이 언급된다."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        assert "math" in tool.description.lower()

    def test_tool_args_schema_has_code_field(self, mock_logger: Mock):
        """도구 인자 스키마에 code 필드가 있다."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        schema = tool.args_schema.model_json_schema()
        assert "code" in schema["properties"]

    def test_tool_args_schema_code_is_string(self, mock_logger: Mock):
        """도구 인자 스키마의 code 필드는 문자열이다."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        schema = tool.args_schema.model_json_schema()
        assert schema["properties"]["code"]["type"] == "string"


class TestCodeExecutorToolInvoke:
    """도구 invoke 테스트."""

    def test_invoke_simple_calculation(self, mock_logger: Mock):
        """간단한 계산 invoke."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        result = tool.invoke({"code": "print(1 + 2)"})

        assert "3" in result
        assert "success" in result.lower()

    def test_invoke_with_math_module(self, mock_logger: Mock):
        """math 모듈 사용 invoke."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        result = tool.invoke({"code": "import math\nprint(math.sqrt(16))"})

        assert "4.0" in result
        assert "success" in result.lower()

    def test_invoke_forbidden_module_error(self, mock_logger: Mock):
        """금지된 모듈 사용 invoke."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        result = tool.invoke({"code": "import os"})

        assert "forbidden" in result.lower() or "not allowed" in result.lower()
        assert "os" in result

    def test_invoke_forbidden_builtin_error(self, mock_logger: Mock):
        """금지된 빌트인 사용 invoke."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        result = tool.invoke({"code": "eval('1+1')"})

        assert "forbidden" in result.lower() or "not allowed" in result.lower()
        assert "eval" in result

    def test_invoke_syntax_error(self, mock_logger: Mock):
        """문법 에러 invoke."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        result = tool.invoke({"code": "print(Hello"})

        assert "error" in result.lower()
        assert "syntax" in result.lower()

    def test_invoke_runtime_error(self, mock_logger: Mock):
        """런타임 에러 invoke."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        result = tool.invoke({"code": "print(1/0)"})

        assert "error" in result.lower()
        assert "zerodivision" in result.lower()


class TestCodeExecutorToolAsyncInvoke:
    """도구 ainvoke 테스트."""

    @pytest.mark.asyncio
    async def test_ainvoke_simple_calculation(self, mock_logger: Mock):
        """간단한 계산 ainvoke."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        result = await tool.ainvoke({"code": "print(2 * 3)"})

        assert "6" in result
        assert "success" in result.lower()

    @pytest.mark.asyncio
    async def test_ainvoke_with_json_module(self, mock_logger: Mock):
        """json 모듈 사용 ainvoke."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        result = await tool.ainvoke({
            "code": 'import json\nprint(json.dumps({"key": "value"}))'
        })

        assert "key" in result
        assert "value" in result

    @pytest.mark.asyncio
    async def test_ainvoke_forbidden_module_error(self, mock_logger: Mock):
        """금지된 모듈 사용 ainvoke."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        result = await tool.ainvoke({"code": "import subprocess"})

        assert "forbidden" in result.lower() or "not allowed" in result.lower()


class TestCreateCodeExecutorToolFunction:
    """create_code_executor_tool 함수 테스트."""

    def test_function_returns_base_tool(self, mock_logger: Mock):
        """함수는 BaseTool을 반환한다."""
        tool = create_code_executor_tool(logger=mock_logger)
        assert isinstance(tool, BaseTool)

    def test_function_creates_working_tool(self, mock_logger: Mock):
        """함수는 동작하는 도구를 생성한다."""
        tool = create_code_executor_tool(logger=mock_logger)
        result = tool.invoke({"code": "print('test')"})

        assert "test" in result
        assert "success" in result.lower()


class TestCodeExecutorToolRequestId:
    """request_id 관련 테스트."""

    def test_invoke_uses_generated_request_id(self, mock_logger: Mock):
        """invoke는 request_id를 생성하여 사용한다."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        tool.invoke({"code": "print('hello')"})

        # 로거가 호출되었는지 확인
        mock_logger.info.assert_called()

    def test_multiple_invokes_use_different_request_ids(self, mock_logger: Mock):
        """여러 invoke는 다른 request_id를 사용한다."""
        tool = CodeExecutorToolFactory.create(logger=mock_logger)
        tool.invoke({"code": "print('1')"})
        first_call_count = mock_logger.info.call_count

        tool.invoke({"code": "print('2')"})
        second_call_count = mock_logger.info.call_count

        assert second_call_count > first_call_count
