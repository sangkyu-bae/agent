"""/api/v1/agents/pipeline 정지 지점 계약 — agent-create-wizard §4.2~§4.4.

검증 대상은 **라우터의 계약**이다: 신규 요청 필드가 UseCase 인자로 정확히
번역되는가, 정지 응답이 스키마대로 직렬화되는가, 그리고 신규 필드를 안 주면
기존 호출이 글자 그대로 그대로인가(FR-B09).

단계 전이 규칙 자체는 domain/application 테스트가 이미 못박았다.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.agent_pipeline_router import (
    get_agent_pipeline_use_case,
    router,
)
from src.application.agent_create_pipeline.events import PipelineOutcome
from src.domain.agent_create_pipeline.stages import (
    STAGE_ORDER,
    PipelineStage,
    PipelineStop,
    StageRecord,
    StageStatus,
)
from src.domain.intent.schemas import IntentResult
from src.interfaces.dependencies.auth import get_current_user

from tests.api.test_agent_pipeline_router import (
    StubPipeline,
    _body,
    _parse_sse,
    _record,
    _stage_events,
    _user,
)

_URL = "/api/v1/agents/pipeline"
_STOPPED = "stopped_for_review"


def _client(stub: StubPipeline, authed: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent_pipeline_use_case] = lambda: stub
    if authed:
        app.dependency_overrides[get_current_user] = lambda: _user()
    return TestClient(app)


def _stopped_steps(reached: tuple[PipelineStage, ...]) -> tuple[StageRecord, ...]:
    """도달 단계는 ok, 나머지는 stopped_for_review 로 채운 5개 고정 steps."""
    done = {stage: _record(stage) for stage in reached}
    return tuple(
        done.get(stage, StageRecord(stage, StageStatus.SKIPPED, _STOPPED))
        for stage in STAGE_ORDER
    )


def _tools_proposed_items() -> list:
    reached = (PipelineStage.INTENT, PipelineStage.TOOLS)
    items: list = []
    for stage in reached:
        items.extend(_stage_events(_record(stage)))
    items.append(
        PipelineOutcome(
            status="tools_proposed",
            steps=_stopped_steps(reached),
            round=1,
            intent=IntentResult(
                label="agent_build",
                filled_slots={"purpose": "문서 Q&A"},
                complete=True,
            ),
            recommended_tool_ids=("internal:a", "internal:b"),
            final_tool_ids=("internal:a", "internal:b"),
            suggested_name="문서 Q&A",
        )
    )
    return items


def _prompt_ready_items(clamp_reason: str | None = None) -> list:
    reached = (PipelineStage.INTENT, PipelineStage.TOOLS, PipelineStage.PROMPT)
    items: list = []
    for stage in reached:
        items.extend(_stage_events(_record(stage)))
    items.append(
        PipelineOutcome(
            status="prompt_ready",
            steps=_stopped_steps(reached),
            round=1,
            recommended_tool_ids=("internal:a",),
            final_tool_ids=("internal:a",),
            unknown_tool_ids=("internal:nope",),
            session_id="ps1",
            version_id="pv1",
            assembled_prompt="조립된 프롬프트",
            prompt_clamp_reason=clamp_reason,
            suggested_name="문서 Q&A",
        )
    )
    return items


# ── 요청 필드 → UseCase 인자 번역 (§4.2) ────────────────────────────────────


def test_stop_after_is_translated_to_pipeline_stop_enum() -> None:
    stub = StubPipeline(_tools_proposed_items())
    _client(stub).post(_URL, json=_body(stop_after="tools"))
    assert stub.calls[0]["stop_after"] is PipelineStop.TOOLS


def test_stop_after_prompt_is_translated() -> None:
    stub = StubPipeline(_prompt_ready_items())
    _client(stub).post(_URL, json=_body(stop_after="prompt"))
    assert stub.calls[0]["stop_after"] is PipelineStop.PROMPT


def test_tools_confirmed_is_forwarded() -> None:
    stub = StubPipeline(_prompt_ready_items())
    _client(stub).post(
        _URL,
        json=_body(
            stop_after="prompt",
            tools_confirmed=True,
            tool_ids=["internal:a"],
        ),
    )
    assert stub.calls[0]["tools_confirmed"] is True
    assert stub.calls[0]["tool_ids"] == ("internal:a",)


def test_intent_echo_is_forwarded_as_intent_result() -> None:
    stub = StubPipeline(_prompt_ready_items())
    _client(stub).post(
        _URL,
        json=_body(
            stop_after="prompt",
            intent={
                "label": "agent_build",
                "filled_slots": {"purpose": "문서 Q&A"},
                "degraded": False,
            },
        ),
    )
    echo = stub.calls[0]["intent_echo"]
    assert isinstance(echo, IntentResult)
    assert echo.filled_slots == {"purpose": "문서 Q&A"}
    assert echo.label == "agent_build"


def test_intent_echo_computed_fields_are_not_accepted_from_client() -> None:
    """계산 필드를 실어 보내도 라우터가 통과시키지 않는다 (신뢰 경계 §7)."""
    stub = StubPipeline(_prompt_ready_items())
    _client(stub).post(
        _URL,
        json=_body(
            stop_after="prompt",
            intent={
                "filled_slots": {"tone": "격식체"},
                "complete": True,
                "missing_slots": [],
            },
        ),
    )
    echo = stub.calls[0]["intent_echo"]
    assert echo.complete is False
    assert echo.missing_slots == []


# ── 정지 응답 직렬화 (§4.3) ─────────────────────────────────────────────────


def test_tools_proposed_response_shape() -> None:
    response = _client(StubPipeline(_tools_proposed_items())).post(
        _URL, json=_body(stop_after="tools")
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "tools_proposed"
    assert data["recommended_tool_ids"] == ["internal:a", "internal:b"]
    assert data["suggested_name"] == "문서 Q&A"
    assert data["intent"]["filled_slots"] == {"purpose": "문서 Q&A"}
    assert data["agent_id"] is None


def test_stopped_response_still_has_five_steps() -> None:
    """정지해도 steps 는 5개다 — 화면이 단계 바를 고정 렌더한다 (§4.3)."""
    data = _client(StubPipeline(_tools_proposed_items())).post(
        _URL, json=_body(stop_after="tools")
    ).json()
    assert [s["stage"] for s in data["steps"]] == [
        "intent", "tools", "prompt", "create", "bind",
    ]
    skipped = [s for s in data["steps"] if s["status"] == "skipped"]
    assert len(skipped) == 3
    assert all(s["reason"] == _STOPPED for s in skipped)


def test_prompt_ready_response_shape() -> None:
    data = _client(StubPipeline(_prompt_ready_items())).post(
        _URL, json=_body(stop_after="prompt", tools_confirmed=True)
    ).json()
    assert data["status"] == "prompt_ready"
    assert data["session_id"] == "ps1"
    assert data["version_id"] == "pv1"
    assert data["assembled_prompt"] == "조립된 프롬프트"
    assert data["unknown_tool_ids"] == ["internal:nope"]
    assert data["prompt_clamp_reason"] is None
    assert data["agent_id"] is None


def test_prompt_clamp_reason_is_surfaced() -> None:
    """D3 — 절단 사실은 이 필드로만 알 수 있다."""
    items = _prompt_ready_items(clamp_reason="프롬프트 5000자 → 4000자 절단")
    data = _client(StubPipeline(items)).post(
        _URL, json=_body(stop_after="prompt")
    ).json()
    assert data["prompt_clamp_reason"] == "프롬프트 5000자 → 4000자 절단"


# ── 검증 (§4.2) ─────────────────────────────────────────────────────────────


def test_invalid_stop_after_returns_422() -> None:
    response = _client(StubPipeline(_tools_proposed_items())).post(
        _URL, json=_body(stop_after="bogus")
    )
    assert response.status_code == 422


@pytest.mark.parametrize("value", ["create", "bind", "intent"])
def test_non_stoppable_stages_are_rejected(value) -> None:
    """create/bind 는 정지 지점이 될 수 없다 — 생성 뒤엔 되돌릴 수 없다."""
    response = _client(StubPipeline(_tools_proposed_items())).post(
        _URL, json=_body(stop_after=value)
    )
    assert response.status_code == 422


# ── SSE (§4.4) ──────────────────────────────────────────────────────────────


def test_sse_stops_cleanly_with_single_pipeline_result() -> None:
    stub = StubPipeline(_tools_proposed_items())
    response = _client(stub).post(
        f"{_URL}/stream", json=_body(stop_after="tools")
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    kinds = [name for name, _, _ in events]
    assert kinds.count("pipeline_result") == 1
    assert kinds[-1] == "pipeline_result"
    assert [seq for _, seq, _ in events] == list(range(len(events)))


def test_sse_final_payload_equals_sync_response_when_stopped() -> None:
    """FR-15 를 정지 경로까지 확장 — 두 라우트의 결과 의미가 동일해야 한다."""
    sync = _client(StubPipeline(_prompt_ready_items())).post(
        _URL, json=_body(stop_after="prompt")
    ).json()
    stream = _client(StubPipeline(_prompt_ready_items())).post(
        f"{_URL}/stream", json=_body(stop_after="prompt")
    )
    final = [d for name, _, d in _parse_sse(stream.text)
             if name == "pipeline_result"][0]
    assert json.dumps(final, sort_keys=True, ensure_ascii=False) == json.dumps(
        sync, sort_keys=True, ensure_ascii=False
    )


# ── 인증 (§4.5) ─────────────────────────────────────────────────────────────


def test_stopped_request_requires_authentication() -> None:
    client = _client(StubPipeline(_tools_proposed_items()), authed=False)
    response = client.post(_URL, json=_body(stop_after="tools"))
    assert response.status_code == 401


# ── 회귀: 신규 필드 미지정 (FR-B09) ─────────────────────────────────────────


def test_legacy_request_passes_no_op_defaults() -> None:
    """기존 호출자는 신규 필드를 모른다 — 전부 no-op 로 내려가야 한다."""
    from tests.api.test_agent_pipeline_router import _created_items

    stub = StubPipeline(_created_items())
    _client(stub).post(_URL, json=_body())
    call = stub.calls[0]
    assert call["stop_after"] is None
    assert call["tools_confirmed"] is False
    assert call["intent_echo"] is None
