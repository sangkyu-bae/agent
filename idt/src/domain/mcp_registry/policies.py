"""MCP Registry 도메인 정책."""
from urllib.parse import urlparse


class MCPRegistrationPolicy:
    """MCP 서버 등록 유효성 정책."""

    MAX_NAME_LENGTH = 255
    MAX_DESCRIPTION_LENGTH = 2000
    MAX_ENDPOINT_LENGTH = 512
    ALLOWED_SCHEMES = {"http", "https"}
    ALLOWED_TRANSPORTS = {"sse", "streamable_http"}

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

    @staticmethod
    def validate_transport(transport: str) -> bool:
        """허용된 transport인지 검증한다."""
        return transport in MCPRegistrationPolicy.ALLOWED_TRANSPORTS

    @staticmethod
    def requires_secret_storage(transport: str) -> bool:
        """해당 transport가 시크릿(api_key 등) 암호화 저장을 요구하는지 판단한다.

        streamable_http(Smithery)는 api_key가 필수이므로 암호화 키 없이는
        시크릿을 안전하게 저장할 수 없어 등록을 허용하면 안 된다.
        """
        return transport == "streamable_http"

    @staticmethod
    def validate_auth(transport: str, auth_config: dict | None) -> bool:
        """transport별 필수 인증 필드를 검증한다.

        streamable_http(Smithery)는 플랫폼 인증을 위해 api_key가 필수다.
        sse는 별도 인증 요건이 없어 항상 통과한다.
        """
        if transport != "streamable_http":
            return True
        if not auth_config:
            return False
        api_key = auth_config.get("api_key")
        return bool(api_key and str(api_key).strip())
