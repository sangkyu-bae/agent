"""Jev 어댑터·매핑 계약 테스트 — Design §8.2 #7~12, #19~20 (httpx2.MockTransport).

typesafe-sdk 는 optional extra 라 미설치 환경에서는 모듈 전체를 skip 한다.
"""

import json
from pathlib import Path

import pytest

httpx2 = pytest.importorskip("httpx2")
typesafe_sdk = pytest.importorskip("typesafe_sdk")

from src.domain.judgment.exceptions import (  # noqa: E402
    JudgmentProtocolError,
    JudgmentTimeoutError,
    JudgmentUnavailableError,
)
from src.domain.judgment.value_objects import (  # noqa: E402
    ChoiceQuestion,
    JudgmentBackendKind,
    JudgmentRequest,
    NoulQuestion,
)
from src.infrastructure.judgment.jev.adapter import JevJudgmentAdapter  # noqa: E402
from src.infrastructure.judgment.jev.mapping import to_sdk_questions  # noqa: E402

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "judgment"
API_KEY = "tsk-test-key-do-not-log"
BASE_URL = "https://jev.test"


def _fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _noul_request() -> JudgmentRequest:
    return JudgmentRequest(
        state={"question": "환율 전망은?", "analysis_text": "엑셀 요약"},
        questions={"needs_web_search": NoulQuestion("외부 정보가 필요한가?")},
    )


def _mixed_request() -> JudgmentRequest:
    return JudgmentRequest(
        state="본문",
        questions={
            "needs_web_search": NoulQuestion("외부 정보가 필요한가?"),
            "chart": ChoiceQuestion("차트 유형은?", (("bar", "막대"), ("line", None))),
        },
    )


def _adapter(
    handler, timeout: float = 3.0, model: str = "jev-latest"
) -> JevJudgmentAdapter:
    return JevJudgmentAdapter(
        api_key=API_KEY,
        model=model,
        timeout_seconds=timeout,
        base_url=BASE_URL,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )


def _json_handler(payload: dict, status: int = 200, capture: list | None = None):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if capture is not None:
            capture.append(request)
        return httpx2.Response(status, json=payload)

    return handler


class TestMapping:
    def test_to_sdk_questions(self):
        sdk = to_sdk_questions(_mixed_request())
        assert sdk["needs_web_search"].type == "noul"
        assert sdk["needs_web_search"].instructions == "외부 정보가 필요한가?"
        assert sdk["chart"].type == "choice"
        assert dict(sdk["chart"].criteria) == {"bar": "막대", "line": None}


class TestAdapter:
    async def test_noul_success(self):
        captured: list = []
        adapter = _adapter(
            _json_handler(_fixture("jev_systemone_noul.json"), capture=captured)
        )
        resp = await adapter.judge(_noul_request())
        assert resp.noul("needs_web_search").probability == pytest.approx(0.73)
        assert resp.model == "jev-1.13.0"
        assert resp.backend is JudgmentBackendKind.JEV
        assert resp.extra["usage"]["input_tokens"] == 120
        req = captured[0]
        assert req.url.path == "/v1/systemone"
        assert req.headers["authorization"] == f"Bearer {API_KEY}"
        body = json.loads(req.content)
        assert body["model"] == "jev-latest"
        assert body["state"] == {
            "question": "환율 전망은?",
            "analysis_text": "엑셀 요약",
        }
        assert body["questions"]["needs_web_search"]["type"] == "noul"

    async def test_mixed_request_answers_match_question_ids(self):
        resp = await _adapter(
            _json_handler(_fixture("jev_systemone_mixed.json"))
        ).judge(_mixed_request())
        assert set(resp.answers) == {"needs_web_search", "chart"}
        choice = resp.choice("chart")
        assert choice.choice == "bar" and choice.confidence == pytest.approx(0.82)

    @pytest.mark.parametrize("status", [401, 429, 500])
    async def test_api_errors_are_unavailable(self, status):
        with pytest.raises(JudgmentUnavailableError) as info:
            await _adapter(_json_handler({"error": "x"}, status=status)).judge(
                _noul_request()
            )
        assert info.value.status == status

    async def test_no_retry_on_server_error(self):
        captured: list = []
        with pytest.raises(JudgmentUnavailableError):
            await _adapter(_json_handler({"error": "x"}, 500, capture=captured)).judge(
                _noul_request()
            )
        assert len(captured) == 1

    async def test_timeout_is_timeout_error(self):
        def handler(_: httpx2.Request) -> httpx2.Response:
            raise httpx2.ReadTimeout("slow")

        with pytest.raises(JudgmentTimeoutError) as info:
            await _adapter(handler, timeout=1.5).judge(_noul_request())
        assert info.value.timeout_seconds == 1.5

    async def test_connection_error_is_unavailable(self):
        def handler(_: httpx2.Request) -> httpx2.Response:
            raise httpx2.ConnectError("refused")

        with pytest.raises(JudgmentUnavailableError) as info:
            await _adapter(handler).judge(_noul_request())
        assert info.value.status is None

    @pytest.mark.parametrize(
        "payload",
        [
            {"model": "m", "answers": {}, "usage": {}},  # 답 누락
            {
                "model": "m",
                "answers": {
                    "needs_web_search": {
                        "type": "choice",
                        "choice": "a",
                        "confidence": 1.0,
                        "probabilities": {"a": 1.0},
                    }
                },
            },  # 타입 불일치
            {
                "model": "m",
                "answers": {"needs_web_search": {"type": "noul", "noul": 1.7}},
            },  # 범위 밖
            {
                "model": "m",
                "answers": {"needs_web_search": {"type": "noul"}},
            },  # noul 필드 누락
        ],
    )
    async def test_protocol_violations(self, payload):
        with pytest.raises(JudgmentProtocolError):
            await _adapter(_json_handler(payload)).judge(_noul_request())

    async def test_choice_label_mismatch_is_protocol_error(self):
        payload = _fixture("jev_systemone_mixed.json")
        payload["answers"]["chart"]["probabilities"] = {"bar": 0.8, "pie": 0.2}
        with pytest.raises(JudgmentProtocolError):
            await _adapter(_json_handler(payload)).judge(_mixed_request())

    async def test_error_messages_do_not_leak_key_or_state(self):
        req = JudgmentRequest(
            state=API_KEY + "-state", questions={"q": NoulQuestion("i")}
        )
        with pytest.raises(JudgmentUnavailableError) as info:
            await _adapter(_json_handler({"error": "bad key"}, 401)).judge(req)
        assert API_KEY not in str(info.value)

    async def test_aclose(self):
        await _adapter(_json_handler(_fixture("jev_systemone_noul.json"))).aclose()
