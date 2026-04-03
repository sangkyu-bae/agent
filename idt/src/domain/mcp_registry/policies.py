"""MCP Registry 도메인 정책."""
from urllib.parse import urlparse


class MCPRegistrationPolicy:
    """MCP 서버 등록 유효성 정책."""

    MAX_NAME_LENGTH = 255
    MAX_DESCRIPTION_LENGTH = 2000
    MAX_ENDPOINT_LENGTH = 512
    ALLOWED_SCHEMES = {"http", "https"}

    @staticmethod
    def validate_name(name: str) -> bool:
        return (
            bool(name and name.strip())
            and len(name) <= MCPRegistrationPolicy.MAX_NAME_LENGTH
        )

    @staticmethod
    def validate_description(description: str) -> bool:
        return (
            bool(description and description.strip())
            and len(description) <= MCPRegistrationPolicy.MAX_DESCRIPTION_LENGTH
        )

    @staticmethod
    def validate_endpoint(endpoint: str) -> bool:
        """http/https URL 형식 검증."""
        if not endpoint or len(endpoint) > MCPRegistrationPolicy.MAX_ENDPOINT_LENGTH:
            return False
        parsed = urlparse(endpoint)
        return (
            parsed.scheme in MCPRegistrationPolicy.ALLOWED_SCHEMES
            and bool(parsed.netloc)
        )
