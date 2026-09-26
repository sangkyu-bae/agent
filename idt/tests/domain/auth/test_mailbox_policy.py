"""MailboxPolicy + User.mailbox_upn — mock 금지.

Design Ref: mcp-identity-header §3.1, §4.2 (PATCH mailbox 정규화 규칙).
"""
import pytest

from src.domain.auth.entities import User
from src.domain.auth.policies import MailboxPolicy


class TestUserMailboxField:
    def test_기본값은_None(self):
        assert User(email="a@b.com", password_hash="h").mailbox_upn is None

    def test_로그인_email과_독립적으로_보관한다(self):
        user = User(email="a@login.local", password_hash="h", mailbox_upn="kim@corp.com")
        assert user.email == "a@login.local"
        assert user.mailbox_upn == "kim@corp.com"


class TestMailboxPolicyNormalize:
    def test_소문자로_정규화하고_공백을_제거한다(self):
        assert MailboxPolicy.normalize("  Kim@Corp.COM ") == "kim@corp.com"

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_빈_값은_해제를_뜻하는_None(self, value):
        assert MailboxPolicy.normalize(value) is None

    @pytest.mark.parametrize(
        "value",
        ["kim", "kim@", "@corp.com", "kim@corp", "kim corp@corp.com", "a@b@c.com"],
    )
    def test_이메일_형식이_아니면_ValueError(self, value):
        with pytest.raises(ValueError):
            MailboxPolicy.normalize(value)

    def test_최대_길이를_넘으면_ValueError(self):
        local = "a" * (MailboxPolicy.MAX_LENGTH - len("@corp.com") + 1)
        with pytest.raises(ValueError):
            MailboxPolicy.normalize(f"{local}@corp.com")

    def test_최대_길이는_허용한다(self):
        local = "a" * (MailboxPolicy.MAX_LENGTH - len("@corp.com"))
        assert MailboxPolicy.normalize(f"{local}@corp.com") is not None
