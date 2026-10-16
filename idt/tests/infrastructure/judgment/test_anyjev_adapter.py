"""AnyJev 어댑터·매핑 계약 테스트 — Design §8.2 #13~20 (httpx.MockTransport)."""

import json
from pathlib import Path

import httpx
import pytest
from src.domain.judgment.exceptions import (
    JudgmentProtocolError,
    JudgmentTimeoutError,
    JudgmentUnavailableError,
)
from src.domain.judgment.value_objects import (
    ChoiceQuestion,
    JudgmentBackendKind,
    JudgmentRequest,
    NoulQuestion,
)
from src.infrastructure.judgment.anyjev.adapter import AnyJevJudgmentAdapter
from src.infrastructure.judgment.anyjev.mapping import (
    fold_choice_question,
    serialize_state,
    to_items,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "judgment"
BASE_URL = "http://anyjev.internal:8100"
KEY = "sk-should-never-appear"


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


def _adapter(handler, timeout: float = 3.0, model_name=None) -> AnyJevJudgmentAdapter:
    return AnyJevJudgmentAdapter(
        base_url=BASE_URL + "/",
        timeout_seconds=timeout,
        model_name=model_name,
        transport=httpx.MockTransport(handler),
    )


def _json_handler(payload: dict, status: int = 200, capture: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(status, json=payload)

    return handler


class TestMapping:
    def test_serialize_mapping_state_order_and_format(self):
        s = serialize_state({"question": "q", "analysis_text": "a\nb"})
        assert s == "[question]\nq\n\n[analysis_text]\na\nb"

    def test_serialize_string_state_passthrough(self):
        assert serialize_state("raw") == "raw"

    def test_fold_choice_question(self):
        q = ChoiceQuestion("차트 유형은?", (("bar", "막대"), ("line", None)))
        assert fold_choice_question(q) == "차트 유형은?\n선택지:\n- bar: 막대\n- line"

    def test_to_items_noul_has_no_options(self):
        items = to_items(_noul_request())
        assert items == [
            {
                "state": "[question]\n환율 전망은?\n\n[analysis_text]\n엑셀 요약",
                "question": "외부 정보가 필요한가?",
                "kind": "noul",
            }
        ]

    def test_to_items_choice_has_options(self):
        items = to_items(_mixed_request())
        assert items[1]["kind"] == "choice"
        assert items[1]["options"] == ["bar", "line"]


class TestAdapter:
    async def test_noul_success(self):
        captured: list[httpx.Request] = []
        adapter = _adapter(
            _json_handler(_fixture("anyjev_decide_noul.json"), capture=captured),
            model_name="Tacit-9B",
        )
        resp = await adapter.judge(_noul_request())
        assert resp.noul("needs_web_search").probability == pytest.approx(0.73)
        assert resp.backend is JudgmentBackendKind.ANYJEV
        assert resp.model == "Tacit-9B"
        assert resp.latency_ms >= 0
        assert resp.extra["decisions"][0]["margin"] == pytest.approx(0.99)
        req = captured[0]
        assert req.url == httpx.URL(BASE_URL + "/v1/decide")
        assert json.loads(req.content)["items"][0]["kind"] == "noul"

    async def test_model_defaults_to_anyjev(self):
        adapter = _adapter(_json_handler(_fixture("anyjev_decide_noul.json")))
        resp = await adapter.judge(_noul_request())
        assert resp.model == "anyjev"

    async def test_lowercase_yes_label_accepted(self):
        payload = {"decisions": [{"answer": "yes", "probs": {"yes": 0.6, "no": 0.4}}]}
        resp = await _adapter(_json_handler(payload)).judge(_noul_request())
        assert resp.noul("needs_web_search").probability == pytest.approx(0.6)

    async def test_mixed_request_answers_match_question_ids(self):
        resp = await _adapter(
            _json_handler(_fixture("anyjev_decide_mixed.json"))
        ).judge(_mixed_request())
        assert set(resp.answers) == {"needs_web_search", "chart"}
        choice = resp.choice("chart")
        assert choice.choice == "bar"
        assert choice.confidence == pytest.approx(0.8)
        assert choice.probabilities["line"] == pytest.approx(0.2)

    @pytest.mark.parametrize(
        "payload",
        [
            {
                "decisions": [{"answer": "Yes", "probs": {"True": 0.7, "False": 0.3}}]
            },  # Yes 없음
            {"decisions": []},  # 길이 불일치
            {
                "decisions": [{"answer": "Yes", "probs": {"Yes": 1.2, "No": -0.2}}]
            },  # 범위 밖
            {"decisions": [{"answer": "Yes"}]},  # probs 누락
            {"nope": 1},  # decisions 누락
            [1, 2],  # 객체 아님
        ],
    )
    async def test_protocol_violations(self, payload):
        with pytest.raises(JudgmentProtocolError):
            await _adapter(_json_handler(payload)).judge(_noul_request())

    async def test_choice_probs_label_mismatch_is_protocol_error(self):
        payload = {
            "decisions": [
                {"answer": "Yes", "probs": {"Yes": 0.7, "No": 0.3}},
                {"answer": "bar", "probs": {"bar": 0.8, "pie": 0.2}},
            ]
        }
        with pytest.raises(JudgmentProtocolError):
            await _adapter(_json_handler(payload)).judge(_mixed_request())

    async def test_non_json_body_is_protocol_error(self):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>")

        with pytest.raises(JudgmentProtocolError):
            await _adapter(handler).judge(_noul_request())

    @pytest.mark.parametrize("status", [400, 404, 502])
    async def test_http_errors_are_unavailable(self, status):
        with pytest.raises(JudgmentUnavailableError) as info:
            await _adapter(_json_handler({"error": "x"}, status=status)).judge(
                _noul_request()
            )
        assert info.value.status == status

    async def test_connection_refused_is_unavailable(self):
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        with pytest.raises(JudgmentUnavailableError) as info:
            await _adapter(handler).judge(_noul_request())
        assert info.value.status is None

    async def test_timeout_is_timeout_error(self):
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow")

        with pytest.raises(JudgmentTimeoutError) as info:
            await _adapter(handler, timeout=1.5).judge(_noul_request())
        assert info.value.timeout_seconds == 1.5

    async def test_error_messages_do_not_leak_state(self):
        req = JudgmentRequest(state=KEY, questions={"q": NoulQuestion("i")})
        with pytest.raises(JudgmentProtocolError) as info:
            await _adapter(_json_handler({"decisions": [{"probs": {"a": 1.0}}]})).judge(
                req
            )
        assert KEY not in str(info.value)

    async def test_aclose(self):
        adapter = _adapter(_json_handler(_fixture("anyjev_decide_noul.json")))
        await adapter.aclose()


class TestActOneExceptionNormalization:
    """Check G1 — RequestError 전체·TypeError 도 JudgmentError 로 정규화된다."""

    async def test_decoding_error_is_unavailable(self):
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.DecodingError("bad content-encoding")

        with pytest.raises(JudgmentUnavailableError):
            await _adapter(handler).judge(_noul_request())

    @pytest.mark.parametrize(
        "choice_decision",
        [
            {
                "answer": ["bar"],
                "probs": {"bar": 0.8, "line": 0.2},
            },  # unhashable answer
            {"answer": "bar", "probs": {"bar": "0.8", "line": 0.2}},  # 타입 혼합
        ],
    )
    async def test_type_errors_are_protocol_errors(self, choice_decision):
        payload = {
            "decisions": [
                {"answer": "Yes", "probs": {"Yes": 0.7, "No": 0.3}},
                choice_decision,
            ]
        }
        with pytest.raises(JudgmentProtocolError):
            await _adapter(_json_handler(payload)).judge(_mixed_request())

    async def test_reasoning_tokens_preserved(self):
        resp = await _adapter(
            _json_handler(_fixture("anyjev_decide_mixed.json"))
        ).judge(_mixed_request())
        assert resp.extra["decisions"][1]["reasoning_tokens"] == 311
        assert resp.extra["decisions"][0]["reasoning_tokens"] is None
