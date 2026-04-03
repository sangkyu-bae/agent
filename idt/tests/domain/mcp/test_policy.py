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
