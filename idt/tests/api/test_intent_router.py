"""POST /api/v1/intent/analyze 통합 테스트 (Design §8.3 L1 1~7).

핵심 계약 검증: LLM 실패는 5xx 가 아니라 **200 + degraded=true** 다 (Design §4.2).
호출자가 에러 핸들링 없이 '의도 모름'으로 진행할 수 있어야 하기 때문이다.
"""
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.intent_router import get_analyze_intent_use_case, router
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.intent.schemas import IntentResult, IntentSpec, Turn
from src.interfaces.dependencies.auth import get_current_user

_SPEC_BODY: dict[str, Any] = {
    "labels": [
        {"name": "search", "description": "근거 문서를 찾아야 하는 질문"},
        {"name": "analysis", "description": "데이터를 계산·비교하는 질문"},
    ],
    "slots": ["기간"],
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
            label="search", confidence=0.82, entities={"기간": "작년"}
        )
        self.calls: list[dict[str, Any]] = []

    async def execute(
        self,
        message: str,
        spec: IntentSpec,
        history: list[Turn] | None = None,
        request_id: str = "",
    ) -> IntentResult:
        self.calls.append({"message": message, "spec": spec, "history": history})
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


# --- L1 #1: 정상 판정 --------------------------------------------------------


class TestAnalyzeHappy:
    def test_returns_200_with_intent_result(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        res = _post(client)

        assert res.status_code == 200
        body = res.json()
        assert body["label"] == "search"
        assert body["confidence"] == 0.82
        assert body["entities"] == {"기간": "작년"}
        assert body["degraded"] is False

    def test_response_contains_every_contract_field(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        body = _post(client).json()

        assert set(body) == {
            "label",
            "confidence",
            "entities",
            "ambiguous",
            "missing_slots",
            "reason",
            "degraded",
        }

    def test_spec_is_forwarded_to_use_case(self) -> None:
        use_case = StubUseCase()
        client = TestClient(_make_app(use_case))

        _post(client)

        spec = use_case.calls[0]["spec"]
        assert [label.name for label in spec.labels] == ["search", "analysis"]
        assert spec.slots == ["기간"]

    # --- L1 #7: history 생략 -------------------------------------------------

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


# --- L1 #6: LLM 실패은 200 + degraded (5xx 아님) ★ --------------------------


class TestDegradedIsNotAnError:
    def test_degraded_result_returns_200(self) -> None:
        client = TestClient(_make_app(StubUseCase(result=IntentResult(degraded=True))))

        res = _post(client)

        assert res.status_code == 200, "LLM 실패는 에러가 아니라 '의도 모름'이다"

    def test_degraded_body_signals_unknown_intent(self) -> None:
        client = TestClient(_make_app(StubUseCase(result=IntentResult(degraded=True))))

        body = _post(client).json()

        assert body["degraded"] is True
        assert body["label"] is None
        assert body["confidence"] == 0.0


# --- L1 #2: 인증 -------------------------------------------------------------


class TestAuth:
    def test_unauthenticated_request_is_rejected(self) -> None:
        client = TestClient(_make_app(StubUseCase(), authenticated=False))

        res = _post(client)

        assert res.status_code in (401, 403)


# --- L1 #3~5: 입력 검증 (422) ------------------------------------------------


class TestValidation:
    def test_single_label_is_rejected(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        res = _post(
            client,
            spec={"labels": [{"name": "search", "description": "설명"}]},
        )

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

    def test_empty_message_is_rejected(self) -> None:
        client = TestClient(_make_app(StubUseCase()))

        res = _post(client, message="")

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
