"""API 테스트: 웹훅 공개 inbound 라우터 — 무JWT 접근·상태코드 매핑 (Design §6).

핵심 단언: 인증 의존성 없이 서명 검증만으로 동작하고, raw body가 그대로
use case에 전달된다 (유니코드 body 포함).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.webhook_public_router import (
    get_invoke_webhook_use_case,
    router,
)
from src.application.agent_builder.schemas import RunAgentResponse
from src.application.agent_webhook.invoke_webhook_agent_use_case import (
    WebhookAuthError,
    WebhookBadRequestError,
    WebhookNotFoundError,
)

AGENT_ID = "a1"
URL = f"/api/v1/webhooks/agents/{AGENT_ID}"


def _run_response() -> RunAgentResponse:
    return RunAgentResponse(
        agent_id=AGENT_ID,
        query="안녕",
        answer="안녕하세요",
        tools_used=[],
        request_id="req-1",
        session_id="sess-1",
        run_id="run-1",
    )


@pytest.fixture
def mock_uc():
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=_run_response())
    return uc


@pytest.fixture
def client(mock_uc):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_invoke_webhook_use_case] = lambda: mock_uc
    return TestClient(app)


class TestPublicInvoke:
    def test_no_jwt_required_returns_200(self, client):
        """Authorization 헤더 없이 접근 가능 — 인증 의존성 부재 실측."""
        res = client.post(
            URL,
            content=b'{"query":"\xec\x95\x88\xeb\x85\x95"}',
            headers={
                "X-Webhook-Timestamp": "1754500000",
                "X-Webhook-Signature": "sha256=abc",
                "Content-Type": "application/json",
            },
        )
        assert res.status_code == 200
        assert res.json()["answer"] == "안녕하세요"

    def test_raw_body_and_headers_passed_verbatim(self, client, mock_uc):
        raw = b'{"query":"\xec\x95\x88\xeb\x85\x95 unicode"}'
        client.post(
            URL,
            content=raw,
            headers={
                "X-Webhook-Timestamp": "123",
                "X-Webhook-Signature": "sha256=sig",
            },
        )
        args = mock_uc.execute.await_args.args
        assert args[0] == AGENT_ID
        assert args[1] == raw          # raw bytes 그대로 (재직렬화 금지)
        assert args[2] == "123"
        assert args[3] == "sha256=sig"

    def test_auth_error_returns_401(self, client, mock_uc):
        mock_uc.execute = AsyncMock(side_effect=WebhookAuthError())
        res = client.post(URL, content=b"{}")
        assert res.status_code == 401
        assert res.json()["detail"] == "서명 검증 실패"

    def test_not_found_returns_404(self, client, mock_uc):
        mock_uc.execute = AsyncMock(side_effect=WebhookNotFoundError())
        res = client.post(URL, content=b"{}")
        assert res.status_code == 404
        assert res.json()["detail"] == "웹훅을 찾을 수 없습니다"

    def test_bad_request_returns_422(self, client, mock_uc):
        mock_uc.execute = AsyncMock(
            side_effect=WebhookBadRequestError("query 필수")
        )
        res = client.post(URL, content=b'{"no_query":1}')
        assert res.status_code == 422

    def test_missing_headers_still_reach_use_case(self, client, mock_uc):
        """헤더 결측 판정은 use case 책임 — 라우터는 None을 그대로 전달."""
        client.post(URL, content=b"{}")
        args = mock_uc.execute.await_args.args
        assert args[2] is None
        assert args[3] is None
