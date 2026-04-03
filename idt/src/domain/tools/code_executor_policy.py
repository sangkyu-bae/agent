"""Code Executor Policy.

Python 코드 실행 도구의 보안 정책을 정의합니다.
허용된 모듈, 금지된 빌트인, 실행 제한을 관리합니다.
"""


class CodeExecutorPolicy:
    """코드 실행 정책.

    샌드박스 환경에서 안전하게 Python 코드를 실행하기 위한
    보안 정책을 정의합니다.
    """

    ALLOWED_MODULES: frozenset[str] = frozenset({
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

    FORBIDDEN_BUILTINS: frozenset[str] = frozenset({
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

    MAX_EXECUTION_TIME_SECONDS: int = 5
    MAX_CODE_LENGTH: int = 5000
    MAX_OUTPUT_LENGTH: int = 10000

    @classmethod
    def is_module_allowed(cls, module_name: str) -> bool:
        """모듈이 허용되었는지 확인.

        Args:
            module_name: 확인할 모듈 이름

        Returns:
            허용된 모듈이면 True, 아니면 False
        """
        return module_name in cls.ALLOWED_MODULES

    @classmethod
    def is_builtin_allowed(cls, builtin_name: str) -> bool:
        """빌트인이 허용되었는지 확인.

        Args:
            builtin_name: 확인할 빌트인 이름

        Returns:
            허용된 빌트인이면 True, 아니면 False
        """
        return builtin_name not in cls.FORBIDDEN_BUILTINS

    @classmethod
    def validate_code_length(cls, code: str) -> bool:
        """코드 길이가 유효한지 확인.

        Args:
            code: 검증할 코드

        Returns:
            유효한 길이면 True, 아니면 False
        """
        return len(code) <= cls.MAX_CODE_LENGTH

    @classmethod
    def truncate_output(cls, output: str) -> str:
        """출력을 최대 길이로 자름.

        Args:
            output: 자를 출력

        Returns:
            잘린 출력 (필요한 경우 truncated 표시 포함)
        """
        if len(output) <= cls.MAX_OUTPUT_LENGTH:
            return output
        return output[:cls.MAX_OUTPUT_LENGTH] + "\n... [truncated]"
