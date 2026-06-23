"""Infrastructure 테스트: Smithery Streamable HTTP URL 빌더."""
import base64
import json
from urllib.parse import parse_qs, urlsplit

from src.infrastructure.mcp_registry.smithery_url import build_streamable_http


class TestBuildStreamableHttp:

    def test_appends_mcp_path_when_missing(self):
        url, _ = build_streamable_http(
            "https://server.smithery.ai/@isnow890/naver-search-mcp", None, None
        )
        assert urlsplit(url).path.endswith("/mcp")

    def test_keeps_existing_mcp_path(self):
        url, _ = build_streamable_http(
            "https://server.smithery.ai/@x/y/mcp", None, None
        )
        assert urlsplit(url).path.count("/mcp") == 1

    def test_api_key_and_profile_in_query(self):
        url, _ = build_streamable_http(
            "https://server.smithery.ai/@x/y/mcp",
            {"api_key": "K", "profile": "P"},
            None,
        )
        q = parse_qs(urlsplit(url).query)
        assert q["api_key"] == ["K"]
        assert q["profile"] == ["P"]

    def test_server_config_encoded_as_base64_json(self):
        server_config = {"NAVER_CLIENT_ID": "id", "NAVER_CLIENT_SECRET": "sec"}
        url, _ = build_streamable_http(
            "https://server.smithery.ai/@x/y/mcp",
            {"api_key": "K"},
            server_config,
        )
        q = parse_qs(urlsplit(url).query)
        decoded = json.loads(base64.b64decode(q["config"][0]).decode("utf-8"))
        assert decoded == server_config

    def test_headers_from_auth_config(self):
        _, headers = build_streamable_http(
            "https://server.smithery.ai/@x/y/mcp",
            {"api_key": "K", "headers": {"Authorization": "Bearer t"}},
            None,
        )
        assert headers == {"Authorization": "Bearer t"}

    def test_no_secrets_no_query(self):
        url, headers = build_streamable_http(
            "https://server.smithery.ai/@x/y/mcp", None, None
        )
        assert urlsplit(url).query == ""
        assert headers == {}
