"""신원 설정 수정 규칙 + 정적 헤더 충돌 검사 — mock 금지.

Design Ref: mcp-identity-header §4.2 (PUT 규칙, validate_identity), Plan R-6.
"""
import pytest

from src.domain.mcp_registry.identity import IdentityHeaderConfig
from src.domain.mcp_registry.policies import MCPRegistrationPolicy

_OLD = "o" * 32
_NEW = "n" * 32


def _existing() -> IdentityHeaderConfig:
    return IdentityHeaderConfig.from_dict(
        {"audience": "old-aud", "secret": _OLD, "ttl_seconds": 100}
    )


class TestMergeUpdate:
    def test_비밀이_없으면_기존_비밀을_유지하고_나머지만_바꾼다(self):
        merged = IdentityHeaderConfig.merge_update(
            _existing(), {"audience": "new-aud", "claim_source": "email"}
        )
        assert merged.secret == _OLD
        assert merged.audience == "new-aud"
        assert merged.claim_source.value == "email"
        # 요청에 없는 필드는 기존 값이 아니라 기본값 — PUT 객체는 '전체 설정'이다.
        assert merged.ttl_seconds == 300

    @pytest.mark.parametrize("blank", ["", "   ", None])
    def test_빈_비밀도_기존_유지로_본다(self, blank):
        merged = IdentityHeaderConfig.merge_update(
            _existing(), {"audience": "a", "secret": blank}
        )
        assert merged.secret == _OLD

    def test_비밀이_있으면_전체_교체(self):
        merged = IdentityHeaderConfig.merge_update(
            _existing(), {"audience": "a", "secret": _NEW}
        )
        assert merged.secret == _NEW

    def test_기존_설정이_없는데_비밀도_없으면_거부(self):
        with pytest.raises(ValueError):
            IdentityHeaderConfig.merge_update(None, {"audience": "a"})

    def test_기존_설정이_없으면_새로_만든다(self):
        merged = IdentityHeaderConfig.merge_update(None, {"audience": "a", "secret": _NEW})
        assert merged.secret == _NEW

    def test_병합_결과도_규칙을_검사한다(self):
        with pytest.raises(ValueError):
            IdentityHeaderConfig.merge_update(_existing(), {"audience": "a", "ttl_seconds": 999})


class TestHeaderConflict:
    def _cfg(self) -> IdentityHeaderConfig:
        return IdentityHeaderConfig.from_dict({"audience": "a", "secret": _NEW})

    def test_정적_헤더에_같은_이름이_있으면_충돌(self):
        """대소문자 무시 — HTTP 헤더 이름 규칙."""
        auth = {"headers": {"x-mcp-identity": "static"}}
        assert MCPRegistrationPolicy.validate_identity_headers(self._cfg(), auth) is False

    @pytest.mark.parametrize(
        "auth", [None, {}, {"headers": {}}, {"headers": {"X-Other": "v"}}, {"api_key": "k"}]
    )
    def test_겹치지_않으면_통과(self, auth):
        assert MCPRegistrationPolicy.validate_identity_headers(self._cfg(), auth) is True

    def test_신원_미설정이면_항상_통과(self):
        auth = {"headers": {"X-MCP-Identity": "v"}}
        assert MCPRegistrationPolicy.validate_identity_headers(None, auth) is True
