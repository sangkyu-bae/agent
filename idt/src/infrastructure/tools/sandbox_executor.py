"""Sandbox Executor.

샌드박스 환경에서 Python 코드를 안전하게 실행합니다.
AST 기반 정적 분석과 제한된 빌트인을 사용합니다.
"""

import ast
import builtins
import io
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import redirect_stdout, redirect_stderr
from typing import Any

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tools.code_execution_result import CodeExecutionResult
from src.domain.tools.code_executor_policy import CodeExecutorPolicy


class SandboxExecutor:
    """샌드박스 코드 실행기.

    AST 기반 정적 분석과 제한된 빌트인을 사용하여
    안전한 환경에서 Python 코드를 실행합니다.
    """

    def __init__(self, logger: LoggerInterface) -> None:
        """초기화.

        Args:
            logger: 로거 인터페이스
        """
        self._logger = logger
        self._safe_builtins = self._create_safe_builtins()

    def _create_safe_builtins(self) -> dict[str, Any]:
        """안전한 빌트인 딕셔너리 생성.

        Returns:
            금지된 빌트인이 제거된 딕셔너리
        """
        safe = {}
        for name in dir(builtins):
            if not name.startswith("_"):
                if CodeExecutorPolicy.is_builtin_allowed(name):
                    safe[name] = getattr(builtins, name)

        safe["__builtins__"] = safe
        safe["__name__"] = "__main__"
        safe["__doc__"] = None
        safe["__build_class__"] = builtins.__build_class__
        safe["__import__"] = self._safe_import
        return safe

    def _safe_import(
        self,
        name: str,
        globals_dict: dict | None = None,
        locals_dict: dict | None = None,
        fromlist: tuple = (),
        level: int = 0,
    ) -> Any:
        """안전한 import 함수.

        허용된 모듈만 import 가능.

        Args:
            name: 모듈 이름
            globals_dict: globals
            locals_dict: locals
            fromlist: from import 리스트
            level: 상대 import 레벨

        Returns:
            import된 모듈

        Raises:
            ImportError: 금지된 모듈인 경우
        """
        base_module = name.split(".")[0]
        if not CodeExecutorPolicy.is_module_allowed(base_module):
            raise ImportError(f"Module '{base_module}' is not allowed")
        return __builtins__["__import__"](name, globals_dict, locals_dict, fromlist, level)

    def execute(self, code: str, request_id: str) -> CodeExecutionResult:
        """코드 실행.

        Args:
            code: 실행할 Python 코드
            request_id: 요청 ID (로깅용)

        Returns:
            실행 결과
        """
        self._logger.info(
            "Code execution started",
            request_id=request_id,
            code_length=len(code),
        )

        if not CodeExecutorPolicy.validate_code_length(code):
            self._logger.warning(
                "Code length exceeded",
                request_id=request_id,
                code_length=len(code),
                max_length=CodeExecutorPolicy.MAX_CODE_LENGTH,
            )
            return CodeExecutionResult.code_too_long(
                CodeExecutorPolicy.MAX_CODE_LENGTH, len(code)
            )

        code = code.strip()
        if not code:
            self._logger.info(
                "Code execution completed (empty code)",
                request_id=request_id,
            )
            return CodeExecutionResult.success("")

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            self._logger.error(
                "Syntax error in code",
                exception=e,
                request_id=request_id,
            )
            return CodeExecutionResult.syntax_error(f"SyntaxError: {e}")

        validation_result = self._validate_ast(tree, request_id)
        if validation_result is not None:
            return validation_result

        return self._execute_code(code, request_id)

    def _validate_ast(
        self, tree: ast.AST, request_id: str
    ) -> CodeExecutionResult | None:
        """AST 검증.

        Args:
            tree: 파싱된 AST
            request_id: 요청 ID

        Returns:
            검증 실패 시 에러 결과, 성공 시 None
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split(".")[0]
                    if not CodeExecutorPolicy.is_module_allowed(module_name):
                        self._logger.warning(
                            "Forbidden module import attempted",
                            request_id=request_id,
                            module=module_name,
                        )
                        return CodeExecutionResult.forbidden_module(module_name)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split(".")[0]
                    if not CodeExecutorPolicy.is_module_allowed(module_name):
                        self._logger.warning(
                            "Forbidden module from-import attempted",
                            request_id=request_id,
                            module=module_name,
                        )
                        return CodeExecutionResult.forbidden_module(module_name)

            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    if not CodeExecutorPolicy.is_builtin_allowed(func_name):
                        self._logger.warning(
                            "Forbidden builtin call attempted",
                            request_id=request_id,
                            builtin=func_name,
                        )
                        return CodeExecutionResult.forbidden_builtin(func_name)

        return None

    def _execute_code(self, code: str, request_id: str) -> CodeExecutionResult:
        """코드 실행.

        Args:
            code: 실행할 코드
            request_id: 요청 ID

        Returns:
            실행 결과
        """
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        allowed_modules = self._get_allowed_modules()
        exec_globals = {**self._safe_builtins, **allowed_modules}

        def run_code():
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(code, exec_globals)

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_code)
                future.result(timeout=CodeExecutorPolicy.MAX_EXECUTION_TIME_SECONDS)

            output = stdout_capture.getvalue()
            output = CodeExecutorPolicy.truncate_output(output)

            self._logger.info(
                "Code execution completed successfully",
                request_id=request_id,
                output_length=len(output),
            )
            return CodeExecutionResult.success(output)

        except FuturesTimeoutError:
            self._logger.error(
                "Code execution timed out",
                request_id=request_id,
                timeout_seconds=CodeExecutorPolicy.MAX_EXECUTION_TIME_SECONDS,
            )
            return CodeExecutionResult.timeout(
                CodeExecutorPolicy.MAX_EXECUTION_TIME_SECONDS
            )

        except Exception as e:
            error_message = f"{type(e).__name__}: {e}"
            self._logger.error(
                "Code execution failed",
                exception=e,
                request_id=request_id,
            )
            return CodeExecutionResult.error(error_message)

    def _get_allowed_modules(self) -> dict[str, Any]:
        """허용된 모듈 가져오기.

        Returns:
            허용된 모듈 딕셔너리
        """
        modules = {}
        for module_name in CodeExecutorPolicy.ALLOWED_MODULES:
            try:
                modules[module_name] = __import__(module_name)
            except ImportError:
                pass
        return modules
