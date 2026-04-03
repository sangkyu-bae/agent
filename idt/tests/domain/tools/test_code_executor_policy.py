"""Tests for CodeExecutorPolicy.

이 테스트는 코드 실행 정책을 검증합니다.
- 허용된 모듈 검증
- 금지된 빌트인 검증
- 코드 길이 검증
"""

import pytest

from src.domain.tools.code_executor_policy import CodeExecutorPolicy


class TestCodeExecutorPolicyConstants:
    """정책 상수 테스트."""

    def test_allowed_modules_is_frozenset(self):
        """ALLOWED_MODULES는 frozenset이어야 한다."""
        assert isinstance(CodeExecutorPolicy.ALLOWED_MODULES, frozenset)

    def test_allowed_modules_contains_math(self):
        """math 모듈은 허용되어야 한다."""
        assert "math" in CodeExecutorPolicy.ALLOWED_MODULES

    def test_allowed_modules_contains_statistics(self):
        """statistics 모듈은 허용되어야 한다."""
        assert "statistics" in CodeExecutorPolicy.ALLOWED_MODULES

    def test_allowed_modules_contains_decimal(self):
        """decimal 모듈은 허용되어야 한다."""
        assert "decimal" in CodeExecutorPolicy.ALLOWED_MODULES

    def test_allowed_modules_contains_fractions(self):
        """fractions 모듈은 허용되어야 한다."""
        assert "fractions" in CodeExecutorPolicy.ALLOWED_MODULES

    def test_allowed_modules_contains_datetime(self):
        """datetime 모듈은 허용되어야 한다."""
        assert "datetime" in CodeExecutorPolicy.ALLOWED_MODULES

    def test_allowed_modules_contains_json(self):
        """json 모듈은 허용되어야 한다."""
        assert "json" in CodeExecutorPolicy.ALLOWED_MODULES

    def test_allowed_modules_contains_re(self):
        """re 모듈은 허용되어야 한다."""
        assert "re" in CodeExecutorPolicy.ALLOWED_MODULES

    def test_allowed_modules_contains_collections(self):
        """collections 모듈은 허용되어야 한다."""
        assert "collections" in CodeExecutorPolicy.ALLOWED_MODULES

    def test_allowed_modules_contains_itertools(self):
        """itertools 모듈은 허용되어야 한다."""
        assert "itertools" in CodeExecutorPolicy.ALLOWED_MODULES

    def test_allowed_modules_contains_functools(self):
        """functools 모듈은 허용되어야 한다."""
        assert "functools" in CodeExecutorPolicy.ALLOWED_MODULES

    def test_forbidden_builtins_is_frozenset(self):
        """FORBIDDEN_BUILTINS는 frozenset이어야 한다."""
        assert isinstance(CodeExecutorPolicy.FORBIDDEN_BUILTINS, frozenset)

    def test_forbidden_builtins_contains_eval(self):
        """eval은 금지되어야 한다."""
        assert "eval" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_exec(self):
        """exec는 금지되어야 한다."""
        assert "exec" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_compile(self):
        """compile은 금지되어야 한다."""
        assert "compile" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_open(self):
        """open은 금지되어야 한다."""
        assert "open" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_input(self):
        """input은 금지되어야 한다."""
        assert "input" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_import(self):
        """__import__는 금지되어야 한다."""
        assert "__import__" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_globals(self):
        """globals는 금지되어야 한다."""
        assert "globals" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_locals(self):
        """locals는 금지되어야 한다."""
        assert "locals" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_vars(self):
        """vars는 금지되어야 한다."""
        assert "vars" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_dir(self):
        """dir은 금지되어야 한다."""
        assert "dir" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_getattr(self):
        """getattr은 금지되어야 한다."""
        assert "getattr" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_setattr(self):
        """setattr은 금지되어야 한다."""
        assert "setattr" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_delattr(self):
        """delattr은 금지되어야 한다."""
        assert "delattr" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_forbidden_builtins_contains_hasattr(self):
        """hasattr은 금지되어야 한다."""
        assert "hasattr" in CodeExecutorPolicy.FORBIDDEN_BUILTINS

    def test_max_execution_time_seconds(self):
        """MAX_EXECUTION_TIME_SECONDS는 5초여야 한다."""
        assert CodeExecutorPolicy.MAX_EXECUTION_TIME_SECONDS == 5

    def test_max_code_length(self):
        """MAX_CODE_LENGTH는 5000자여야 한다."""
        assert CodeExecutorPolicy.MAX_CODE_LENGTH == 5000

    def test_max_output_length(self):
        """MAX_OUTPUT_LENGTH는 10000자여야 한다."""
        assert CodeExecutorPolicy.MAX_OUTPUT_LENGTH == 10000


class TestIsModuleAllowed:
    """is_module_allowed 메서드 테스트."""

    def test_math_is_allowed(self):
        """math 모듈은 허용된다."""
        assert CodeExecutorPolicy.is_module_allowed("math") is True

    def test_statistics_is_allowed(self):
        """statistics 모듈은 허용된다."""
        assert CodeExecutorPolicy.is_module_allowed("statistics") is True

    def test_datetime_is_allowed(self):
        """datetime 모듈은 허용된다."""
        assert CodeExecutorPolicy.is_module_allowed("datetime") is True

    def test_json_is_allowed(self):
        """json 모듈은 허용된다."""
        assert CodeExecutorPolicy.is_module_allowed("json") is True

    def test_re_is_allowed(self):
        """re 모듈은 허용된다."""
        assert CodeExecutorPolicy.is_module_allowed("re") is True

    def test_collections_is_allowed(self):
        """collections 모듈은 허용된다."""
        assert CodeExecutorPolicy.is_module_allowed("collections") is True

    def test_os_is_not_allowed(self):
        """os 모듈은 허용되지 않는다."""
        assert CodeExecutorPolicy.is_module_allowed("os") is False

    def test_subprocess_is_not_allowed(self):
        """subprocess 모듈은 허용되지 않는다."""
        assert CodeExecutorPolicy.is_module_allowed("subprocess") is False

    def test_sys_is_not_allowed(self):
        """sys 모듈은 허용되지 않는다."""
        assert CodeExecutorPolicy.is_module_allowed("sys") is False

    def test_socket_is_not_allowed(self):
        """socket 모듈은 허용되지 않는다."""
        assert CodeExecutorPolicy.is_module_allowed("socket") is False

    def test_requests_is_not_allowed(self):
        """requests 모듈은 허용되지 않는다."""
        assert CodeExecutorPolicy.is_module_allowed("requests") is False

    def test_shutil_is_not_allowed(self):
        """shutil 모듈은 허용되지 않는다."""
        assert CodeExecutorPolicy.is_module_allowed("shutil") is False

    def test_pickle_is_not_allowed(self):
        """pickle 모듈은 허용되지 않는다."""
        assert CodeExecutorPolicy.is_module_allowed("pickle") is False


class TestIsBuiltinAllowed:
    """is_builtin_allowed 메서드 테스트."""

    def test_print_is_allowed(self):
        """print는 허용된다."""
        assert CodeExecutorPolicy.is_builtin_allowed("print") is True

    def test_len_is_allowed(self):
        """len은 허용된다."""
        assert CodeExecutorPolicy.is_builtin_allowed("len") is True

    def test_range_is_allowed(self):
        """range는 허용된다."""
        assert CodeExecutorPolicy.is_builtin_allowed("range") is True

    def test_sum_is_allowed(self):
        """sum은 허용된다."""
        assert CodeExecutorPolicy.is_builtin_allowed("sum") is True

    def test_min_is_allowed(self):
        """min은 허용된다."""
        assert CodeExecutorPolicy.is_builtin_allowed("min") is True

    def test_max_is_allowed(self):
        """max는 허용된다."""
        assert CodeExecutorPolicy.is_builtin_allowed("max") is True

    def test_eval_is_not_allowed(self):
        """eval은 허용되지 않는다."""
        assert CodeExecutorPolicy.is_builtin_allowed("eval") is False

    def test_exec_is_not_allowed(self):
        """exec는 허용되지 않는다."""
        assert CodeExecutorPolicy.is_builtin_allowed("exec") is False

    def test_open_is_not_allowed(self):
        """open은 허용되지 않는다."""
        assert CodeExecutorPolicy.is_builtin_allowed("open") is False

    def test_compile_is_not_allowed(self):
        """compile은 허용되지 않는다."""
        assert CodeExecutorPolicy.is_builtin_allowed("compile") is False

    def test_input_is_not_allowed(self):
        """input은 허용되지 않는다."""
        assert CodeExecutorPolicy.is_builtin_allowed("input") is False

    def test_import_is_not_allowed(self):
        """__import__는 허용되지 않는다."""
        assert CodeExecutorPolicy.is_builtin_allowed("__import__") is False


class TestValidateCodeLength:
    """validate_code_length 메서드 테스트."""

    def test_empty_code_is_valid(self):
        """빈 코드는 유효하다."""
        assert CodeExecutorPolicy.validate_code_length("") is True

    def test_short_code_is_valid(self):
        """짧은 코드는 유효하다."""
        code = "print('hello')"
        assert CodeExecutorPolicy.validate_code_length(code) is True

    def test_max_length_code_is_valid(self):
        """최대 길이 코드는 유효하다."""
        code = "x" * CodeExecutorPolicy.MAX_CODE_LENGTH
        assert CodeExecutorPolicy.validate_code_length(code) is True

    def test_exceeded_length_code_is_invalid(self):
        """최대 길이를 초과한 코드는 유효하지 않다."""
        code = "x" * (CodeExecutorPolicy.MAX_CODE_LENGTH + 1)
        assert CodeExecutorPolicy.validate_code_length(code) is False

    def test_large_exceeded_length_code_is_invalid(self):
        """크게 초과한 코드는 유효하지 않다."""
        code = "x" * 10000
        assert CodeExecutorPolicy.validate_code_length(code) is False


class TestTruncateOutput:
    """truncate_output 메서드 테스트."""

    def test_short_output_not_truncated(self):
        """짧은 출력은 자르지 않는다."""
        output = "hello"
        assert CodeExecutorPolicy.truncate_output(output) == "hello"

    def test_max_length_output_not_truncated(self):
        """최대 길이 출력은 자르지 않는다."""
        output = "x" * CodeExecutorPolicy.MAX_OUTPUT_LENGTH
        result = CodeExecutorPolicy.truncate_output(output)
        assert result == output

    def test_exceeded_length_output_truncated(self):
        """최대 길이를 초과한 출력은 잘린다."""
        output = "x" * (CodeExecutorPolicy.MAX_OUTPUT_LENGTH + 100)
        result = CodeExecutorPolicy.truncate_output(output)
        assert len(result) <= CodeExecutorPolicy.MAX_OUTPUT_LENGTH + 50
        assert "... [truncated]" in result

    def test_empty_output_not_truncated(self):
        """빈 출력은 자르지 않는다."""
        assert CodeExecutorPolicy.truncate_output("") == ""
