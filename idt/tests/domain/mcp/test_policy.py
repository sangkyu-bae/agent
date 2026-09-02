"""Domain Policy 테스트 - Mock 금지."""
import pytest


class TestMCPConnectionPolicy:

    class TestValidateServerConfig:
        def test_returns_true_with_valid_stdio_config(self):
            from src.domain.mcp.policy import MCPConnectionPolicy
            from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
            config = MCPServerConfig(
                name="filesystem",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(command="npx", args=[]),
            )
            assert MCPConnectionPolicy.validate_server_config(config) is True

        def test_returns_false_with_empty_name(self):
            from src.domain.mcp.policy import MCPConnectionPolicy
            from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
            config = MCPServerConfig(
                name="  ",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(command="npx", args=[]),
            )
            assert MCPConnectionPolicy.validate_server_config(config) is False

    class TestSanitizeToolName:
        def test_replaces_hyphens_with_underscores(self):
            from src.domain.mcp.policy import MCPConnectionPolicy
            assert MCPConnectionPolicy.sanitize_tool_name("read-file") == "read_file"

        def test_replaces_spaces_with_underscores(self):
            from src.domain.mcp.policy import MCPConnectionPolicy
            assert MCPConnectionPolicy.sanitize_tool_name("read file") == "read_file"

        def test_lowercases_name(self):
            from src.domain.mcp.policy import MCPConnectionPolicy
            assert MCPConnectionPolicy.sanitize_tool_name("ReadFile") == "readfile"

        def test_truncates_name_exceeding_max_length(self):
            from src.domain.mcp.policy import MCPConnectionPolicy
            long_name = "a" * 200
            result = MCPConnectionPolicy.sanitize_tool_name(long_name)
            assert len(result) <= MCPConnectionPolicy.MAX_TOOL_NAME_LENGTH

        def test_preserves_name_within_max_length(self):
            from src.domain.mcp.policy import MCPConnectionPolicy
            name = "valid_tool_name"
            assert MCPConnectionPolicy.sanitize_tool_name(name) == "valid_tool_name"

    class TestValidateServerCount:
        def test_returns_true_within_limit(self):
            from src.domain.mcp.policy import MCPConnectionPolicy
            assert MCPConnectionPolicy.validate_server_count(1) is True
            assert MCPConnectionPolicy.validate_server_count(20) is True

        def test_returns_false_when_exceeds_limit(self):
            from src.domain.mcp.policy import MCPConnectionPolicy
            assert MCPConnectionPolicy.validate_server_count(21) is False

        def test_returns_true_at_exact_limit(self):
            from src.domain.mcp.policy import MCPConnectionPolicy
            assert MCPConnectionPolicy.validate_server_count(
                MCPConnectionPolicy.MAX_SERVERS
            ) is True


class TestMCPRetryPolicy:

    class TestDefaults:
        def test_default_values(self):
            from src.domain.mcp.policy import MCPRetryPolicy
            policy = MCPRetryPolicy()
            assert policy.max_retries == 2
            assert policy.base_backoff == 0.5
            assert policy.factor == 2.0
            assert policy.max_backoff == 8.0
            assert policy.retry_tool_execution is False

    class TestValidation:
        def test_rejects_negative_max_retries(self):
            from pydantic import ValidationError
            from src.domain.mcp.policy import MCPRetryPolicy
            with pytest.raises(ValidationError):
                MCPRetryPolicy(max_retries=-1)

        def test_rejects_non_positive_base_backoff(self):
            from pydantic import ValidationError
            from src.domain.mcp.policy import MCPRetryPolicy
            with pytest.raises(ValidationError):
                MCPRetryPolicy(base_backoff=0)

        def test_rejects_factor_below_one(self):
            from pydantic import ValidationError
            from src.domain.mcp.policy import MCPRetryPolicy
            with pytest.raises(ValidationError):
                MCPRetryPolicy(factor=0.5)

    class TestComputeBackoff:
        def test_monotonic_increase(self):
            from src.domain.mcp.policy import MCPRetryPolicy
            policy = MCPRetryPolicy(base_backoff=0.5, factor=2.0, max_backoff=100.0)
            assert policy.compute_backoff(0) == 0.5
            assert policy.compute_backoff(1) == 1.0
            assert policy.compute_backoff(2) == 2.0
            assert policy.compute_backoff(3) == 4.0

        def test_respects_max_backoff_cap(self):
            from src.domain.mcp.policy import MCPRetryPolicy
            policy = MCPRetryPolicy(base_backoff=1.0, factor=10.0, max_backoff=5.0)
            assert policy.compute_backoff(0) == 1.0
            assert policy.compute_backoff(5) == 5.0

        def test_factor_one_is_constant(self):
            from src.domain.mcp.policy import MCPRetryPolicy
            policy = MCPRetryPolicy(base_backoff=2.0, factor=1.0, max_backoff=100.0)
            assert policy.compute_backoff(0) == 2.0
            assert policy.compute_backoff(3) == 2.0

    class TestIsRetryable:
        def test_connection_error_is_retryable(self):
            from src.domain.mcp.policy import MCPRetryPolicy
            assert MCPRetryPolicy.is_retryable(ConnectionError("boom")) is True

        def test_timeout_error_is_retryable(self):
            from src.domain.mcp.policy import MCPRetryPolicy
            assert MCPRetryPolicy.is_retryable(TimeoutError()) is True

        def test_os_error_is_retryable(self):
            from src.domain.mcp.policy import MCPRetryPolicy
            assert MCPRetryPolicy.is_retryable(OSError("net down")) is True

        def test_value_error_is_not_retryable(self):
            from src.domain.mcp.policy import MCPRetryPolicy
            assert MCPRetryPolicy.is_retryable(ValueError("bad")) is False


class TestBuildToolName:
    """U1-U5 — OpenAI function name 상한(64자) 정합.

    Design Ref: fix-mcp-tool-call-not-reaching-server §3.2
    """

    def test_max_tool_name_length_matches_openai_limit(self):
        from src.domain.mcp.policy import MCPConnectionPolicy
        assert MCPConnectionPolicy.MAX_TOOL_NAME_LENGTH == 64

    def test_short_name_returned_unchanged(self):
        """U1 — 64자 이하면 해시 접미사를 붙이지 않는다."""
        from src.domain.mcp.policy import MCPConnectionPolicy
        assert MCPConnectionPolicy.build_tool_name("srv_read_file") == "srv_read_file"

    def test_name_at_exactly_limit_returned_unchanged(self):
        from src.domain.mcp.policy import MCPConnectionPolicy
        name = "a" * 64
        assert MCPConnectionPolicy.build_tool_name(name) == name

    def test_long_name_truncated_to_exactly_limit(self):
        """U2 — 초과 시 정확히 64자, [:59] + "_" + hash4."""
        from src.domain.mcp.policy import MCPConnectionPolicy
        result = MCPConnectionPolicy.build_tool_name("mcp_" + "b" * 90)
        assert len(result) == 64
        assert result[59] == "_"

    def test_long_names_sharing_prefix_do_not_collide(self):
        """U3 — 앞 59자가 같아도 결과가 갈린다 (도구 가려짐 방지)."""
        from src.domain.mcp.policy import MCPConnectionPolicy
        prefix = "mcp_" + "c" * 60
        a = MCPConnectionPolicy.build_tool_name(prefix + "_create_issue")
        b = MCPConnectionPolicy.build_tool_name(prefix + "_delete_issue")
        assert a != b
        assert len(a) == len(b) == 64

    def test_build_tool_name_is_deterministic(self):
        """U4 — 같은 입력은 항상 같은 출력 (관측 기록 대조 가능)."""
        from src.domain.mcp.policy import MCPConnectionPolicy
        name = "mcp_" + "d" * 90
        assert (
            MCPConnectionPolicy.build_tool_name(name)
            == MCPConnectionPolicy.build_tool_name(name)
        )

    def test_build_tool_name_sanitizes_first(self):
        """U5 — 하이픈/공백/대문자 정규화는 기존 동작을 보존한다."""
        from src.domain.mcp.policy import MCPConnectionPolicy
        assert MCPConnectionPolicy.build_tool_name("Srv-Read File") == "srv_read_file"

    def test_result_matches_openai_name_pattern(self):
        from src.domain.mcp.policy import MCPConnectionPolicy
        import re
        result = MCPConnectionPolicy.build_tool_name("mcp_" + "e" * 90)
        assert re.fullmatch(r"[a-zA-Z0-9_-]+", result)
