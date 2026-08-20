"""POST /api/v1/intent/analyze 통합 테스트 (Design §8.3 S33~S41).

핵심 계약 검증: LLM 실패는 5xx 가 아니라 **200 + degraded=true** 다 (Design §4.2).
호출자가 에러 핸들링 없이 '의도 모름'으로 진행할 수 있어야 하기 때문이다.
"""
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.intent_router import get_analyze_intent_use_case, router
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.intent.schemas import (
    IntentResult,
    IntentSpec,
    SlotAnswer,
    SlotQuestion,
    Turn,
)
from src.interfaces.dependencies.auth import get_current_user

_SPEC_BODY: dict[str, Any] = {
    "labels": [
        {"name": "search", "description": "근거 문서를 찾아야 하는 질문"},
        {"name": "analysis", "description": "데이터를 계산·비교하는 질문"},
    ],
    "slots": ["기간"],
}

_SLOT_SPEC_BODY: dict[str, Any] = {
    "labels": [],
    "slots": [
        {
            "key": "data_source",
            "description": "분석할 데이터가 어디에 있는지",
            "options": ["엑셀 업로드", "지식베이스"],
            "required": True,
        }
    ],
}


def _user(uid: int = 7) -> User:
    return User(
        email="t@t.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=uid,
    )


class StubUseCase:
    """AnalyzeIntentUseCase 대역."""

    def __init__(self, result: IntentResult | None = None) -> None:
        self.result = result or IntentResult(
            label="search", confidence=0.82, filled_slots={"기간": "작년"}
        )
        self.calls: list[dict[str, Any]] = []

    async def execute(
        self,
        message: str,
        spec: IntentSpec,
        history: list[Turn] | None = None,
        answers: list[SlotAnswer] | None = None,
        round_: int = 0,
        request_id: str = "",
    ) -> IntentResult:
        self.calls.append(
            {
                "message": message,
                "spec": spec,
                "history": history,
                "answers": answers,
                "round_": round_,
                "request_id": request_id,
            }
        )
        return self.result


def _make_app(use_case: StubUseCase, authenticated: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_analyze_intent_use_case] = lambda: use_case
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: _user()
    return app


def _post(client: TestClient, **overrides: Any) -> Any:
    body: dict[str, Any] = {"message": "작년 여신 한도 기준", "spec": _SPEC_BODY}
    body.update(overrides)
    return client.post("/api/v1/intent/analyze", json=body)


# --- S33: 정상 판정 ----------------------------------------------------------


class TestAnalyzeHappy:
    def test_returns_200_with_intent_result(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        res = _post(client)

        assert res.status_code == 200
        body = res.json()
        assert body["label"] == "search"
        assert body["confidence"] == 0.82
        assert body["filled_slots"] == {"기간": "작년"}
        assert body["degraded"] is False

    def test_response_contains_every_contract_field(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        body = _post(client).json()

        assert set(body) == {
            "label",
            "confidence",
            "ambiguous",
            "reason",
            "filled_slots",
            "suggestions",
            "questions",
            "missing_slots",
            "complete",
            "degraded",
        }

    def test_s41_entities_field_is_gone(self) -> None:
        """Plan D9 — entities 는 filled_slots 로 대체되었다. 별칭을 두지 않는다."""
        client = TestClient(_make_app(StubUseCase()))

        assert "entities" not in _post(client).json()

    def test_spec_is_forwarded_to_use_case(self) -> None:
        use_case = StubUseCase()
        client = TestClient(_make_app(use_case))

        _post(client)

        spec = use_case.calls[0]["spec"]
        assert [label.name for label in spec.labels] == ["search", "analysis"]
        assert [slot.key for slot in spec.slots] == ["기간"]

    def test_str_slots_are_promoted_at_the_boundary(self) -> None:
        """구형 요청(slots=["기간"])도 그대로 받는다 (FR-02 하위호환)."""
        use_case = StubUseCase()
        client = TestClient(_make_app(use_case))

        res = _post(client)

        assert res.status_code == 200
        slot = use_case.calls[0]["spec"].slots[0]
        assert slot.key == "기간"
        assert slot.description == "기간"

    def test_request_id_is_the_caller_user_id(self) -> None:
        use_case = StubUseCase()
        client = TestClient(_make_app(use_case))

        _post(client)

        assert use_case.calls[0]["request_id"] == "7"

    # --- history --------------------------------------------------------

    def test_history_is_optional(self) -> None:
        use_case = StubUseCase()
        client = TestClient(_make_app(use_case))

        res = _post(client)

        assert res.status_code == 200
        assert use_case.calls[0]["history"] is None

    def test_history_is_forwarded_when_present(self) -> None:
        use_case = StubUseCase()
        client = TestClient(_make_app(use_case))

        _post(
            client,
            history=[
                {"role": "user", "content": "여신 규정 알려줘"},
                {"role": "assistant", "content": "어떤 부분을 찾아드릴까요?"},
            ],
        )

        history = use_case.calls[0]["history"]
        assert history is not None
        assert len(history) == 2
        assert history[0].role == "user"


# --- S33: 슬롯 전용 spec (FR-16) ---------------------------------------------


class TestSlotsOnlySpec:
    def test_slots_only_spec_is_accepted(self) -> None:
        """에이전트 생성은 분류 라벨 없이 슬롯만 쓴다."""
        use_case = StubUseCase()
        client = TestClient(_make_app(use_case))

        res = _post(
            client, message="데이터 분석 에이전트 만들어줘", spec=_SLOT_SPEC_BODY
        )

        assert res.status_code == 200
        spec = use_case.calls[0]["spec"]
        assert spec.labels == []
        assert spec.slots[0].required is True
        assert spec.slots[0].options == ["엑셀 업로드", "지식베이스"]

    def test_questions_are_serialized_for_the_client(self) -> None:
        result = IntentResult(
            missing_slots=["data_source"],
            suggestions={"data_source": ["엑셀 업로드", "지식베이스"]},
            questions=[
                SlotQuestion(
                    slot_key="data_source",
                    question="분석할 데이터는 어디에 있나요?",
                    options=["엑셀 업로드", "지식베이스"],
                )
            ],
        )
        client = TestClient(_make_app(StubUseCase(result=result)))

        body = _post(client, spec=_SLOT_SPEC_BODY).json()

        assert body["complete"] is False
        assert body["questions"][0]["slot_key"] == "data_source"
        assert body["questions"][0]["allow_free_text"] is True
        assert body["suggestions"]["data_source"] == ["엑셀 업로드", "지식베이스"]


# --- S34: answers / round 왕복 -----------------------------------------------


class TestClarificationRoundTrip:
    def test_answers_default_to_none(self) -> None:
        use_case = StubUseCase()
        client = TestClient(_make_app(use_case))

        _post(client)

        assert use_case.calls[0]["answers"] is None
        assert use_case.calls[0]["round_"] == 0

    def test_s34_answers_and_round_are_forwarded(self) -> None:
        use_case = StubUseCase()
        client = TestClient(_make_app(use_case))

        res = _post(
            client,
            spec=_SLOT_SPEC_BODY,
            answers=[{"slot_key": "data_source", "value": "엑셀 업로드"}],
            round=1,
        )

        assert res.status_code == 200
        answers = use_case.calls[0]["answers"]
        assert answers is not None
        assert answers[0].slot_key == "data_source"
        assert answers[0].value == "엑셀 업로드"
        assert use_case.calls[0]["round_"] == 1

    def test_complete_result_carries_no_questions(self) -> None:
        result = IntentResult(
            filled_slots={"data_source": "엑셀 업로드"}, complete=True
        )
        client = TestClient(_make_app(StubUseCase(result=result)))

        body = _post(client, spec=_SLOT_SPEC_BODY, round=1).json()

        assert body["complete"] is True
        assert body["questions"] == []


# --- S40: LLM 실패은 200 + degraded (5xx 아님) ★ -----------------------------


class TestDegradedIsNotAnError:
    def test_s40_degraded_result_returns_200(self) -> None:
        client = TestClient(_make_app(StubUseCase(result=IntentResult(degraded=True))))

        res = _post(client)

        assert res.status_code == 200, "LLM 실패는 에러가 아니라 '의도 모름'이다"

    def test_degraded_body_signals_unknown_intent(self) -> None:
        client = TestClient(_make_app(StubUseCase(result=IntentResult(degraded=True))))

        body = _post(client).json()

        assert body["degraded"] is True
        assert body["label"] is None
        assert body["confidence"] == 0.0
        assert body["complete"] is False
        assert body["questions"] == []


# --- S35: 인증 ---------------------------------------------------------------


class TestAuth:
    def test_s35_unauthenticated_request_is_rejected(self) -> None:
        client = TestClient(_make_app(StubUseCase(), authenticated=False))

        res = _post(client)

        assert res.status_code in (401, 403)


# --- S36~S39: 입력 검증 (422) ------------------------------------------------


class TestValidation:
    def test_s36_single_label_is_rejected(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        res = _post(
            client,
            spec={"labels": [{"name": "search", "description": "설명"}]},
        )

        assert res.status_code == 422

    def test_s37_empty_labels_and_slots_is_rejected(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        res = _post(client, spec={"labels": [], "slots": []})

        assert res.status_code == 422

    def test_missing_description_is_rejected(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        res = _post(
            client,
            spec={
                "labels": [
                    {"name": "search", "description": ""},
                    {"name": "analysis", "description": "설명"},
                ]
            },
        )

        assert res.status_code == 422

    def test_slot_without_description_is_rejected(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        res = _post(
            client, spec={"labels": [], "slots": [{"key": "tone", "description": ""}]}
        )

        assert res.status_code == 422

    def test_s38_empty_message_is_rejected(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        res = _post(client, message="")

        assert res.status_code == 422

    def test_s39_negative_round_is_rejected(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        res = _post(client, round=-1)

        assert res.status_code == 422

    def test_empty_answer_value_is_rejected(self) -> None:
        """빈 답변은 '답하지 않음'이므로 애초에 보내지 않는다."""
        client = TestClient(_make_app(StubUseCase()))

        res = _post(client, answers=[{"slot_key": "기간", "value": ""}])

        assert res.status_code == 422

    def test_missing_spec_is_rejected(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        res = client.post("/api/v1/intent/analyze", json={"message": "여신 규정"})

        assert res.status_code == 422

    def test_use_case_not_called_on_validation_failure(self) -> None:
        use_case = StubUseCase()
        client = TestClient(_make_app(use_case))

        _post(client, message="")

        assert use_case.calls == [], "검증 실패 시 LLM 비용이 발생하면 안 된다"
