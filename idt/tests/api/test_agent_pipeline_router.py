"""/api/v1/agents/pipeline 통합 테스트 — Design §4 / §8.2.

핵심 계약:
- 동기 POST 와 SSE 최종 이벤트의 **결과 의미 동일** (FR-15) — 같은 스텁이면
  payload 가 바이트 동일해야 한다.
- 저장 실패는 500 (FR-08), 검증 실패는 422, 타인 세션은 404.
- SSE 는 이벤트 순서·seq 단조 증가·실패 시 stage_failed 후 pipeline_result 종료.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.agent_pipeline_router import (
    get_agent_pipeline_use_case,
    router,
)
from src.application.agent_create_pipeline.events import (
    PipelineOutcome,
    StageEvent,
)
from src.application.prompt_composer.errors import PromptSessionNotFoundError
from src.domain.agent_create_pipeline.stages import (
    STAGE_ORDER,
    PipelineStage,
    StageRecord,
    StageStatus,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.intent.schemas import SlotQuestion
from src.interfaces.dependencies.auth import get_current_user

# ── 스텁·빌더 ───────────────────────────────────────────────────────────────


class StubPipeline:
    """스크립트된 이벤트를 재생하는 UseCase 대역. Exception 항목은 raise."""

    def __init__(self, items) -> None:
        self.items = list(items)
        self.calls: list[dict] = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        for item in self.items:
            if isinstance(item, Exception):
                raise item
            yield item


def _user(uid: int = 7) -> User:
    return User(
        email="t@t.com", password_hash="h", role=UserRole.USER,
        status=UserStatus.APPROVED, id=uid,
    )


def _record(stage: PipelineStage, status=StageStatus.OK,
            reason=None) -> StageRecord:
    return StageRecord(stage, status, reason, elapsed_ms=5)


def _stage_events(record: StageRecord) -> list[StageEvent]:
    return [
        StageEvent("stage_started", StageRecord(record.stage, StageStatus.OK)),
        StageEvent("stage_completed", record),
    ]


def _created_items(prompt_status=StageStatus.OK, prompt_reason=None) -> list:
    records = [
        _record(PipelineStage.INTENT),
        _record(PipelineStage.TOOLS),
        _record(PipelineStage.PROMPT, prompt_status, prompt_reason),
        _record(PipelineStage.CREATE),
        _record(PipelineStage.BIND),
    ]
    items: list = []
    for record in records:
        items.extend(_stage_events(record))
    items.append(PipelineOutcome(
        status="created", steps=tuple(records), round=0,
        recommended_tool_ids=("internal:a",), final_tool_ids=("internal:a",),
        session_id="ps1", version_id="pv1", agent_id="agt1",
        agent_name="문서 봇", assembled_prompt="프롬프트", bind_ok=True,
    ))
    return items


def _need_input_items() -> list:
    intent_record = _record(PipelineStage.INTENT)
    steps = (intent_record,) + tuple(
        StageRecord(stage, StageStatus.SKIPPED, reason="need_input")
        for stage in STAGE_ORDER[1:]
    )
    question = SlotQuestion(slot_key="purpose", question="핵심 용도는요?",
                            options=["문서 Q&A"], allow_free_text=True)
    return [
        *_stage_events(intent_record),
        PipelineOutcome(status="need_input", steps=steps,
                        questions=(question,), round=1),
    ]


def _client(stub: StubPipeline, authed: bool = True,
            raise_server_exceptions: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent_pipeline_use_case] = lambda: stub
    if authed:
        app.dependency_overrides[get_current_user] = lambda: _user()
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _body(**overrides) -> dict:
    return {"user_request": "검색 에이전트 만들어줘", **overrides}


def _parse_sse(text: str) -> list[tuple[str, int, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.split("\n") if ": " in line
        )
        events.append(
            (fields["event"], int(fields["id"]), json.loads(fields["data"]))
        )
    return events


# ── 동기 POST (§8.2 #1~#3, #10, #11) ────────────────────────────────────────


def test_created_response_contains_agent_and_five_steps() -> None:
    stub = StubPipeline(_created_items())
    response = _client(stub).post("/api/v1/agents/pipeline", json=_body())

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    assert data["agent_id"] == "agt1"
    assert data["session_id"] == "ps1"
    assert data["bind_ok"] is True
    assert [s["stage"] for s in data["steps"]] == [
        "intent", "tools", "prompt", "create", "bind",
    ]
    assert data["degraded_stages"] == []


def test_degraded_stage_is_surfaced_in_degraded_stages() -> None:
    stub = StubPipeline(
        _created_items(StageStatus.DEGRADED, "LLM 실패 — 폴백")
    )
    data = _client(stub).post("/api/v1/agents/pipeline", json=_body()).json()

    assert data["degraded_stages"] == ["prompt"]
    assert data["steps"][2]["status"] == "degraded"
    assert data["steps"][2]["reason"] == "LLM 실패 — 폴백"


def test_need_input_echoes_questions_and_next_round() -> None:
    stub = StubPipeline(_need_input_items())
    data = _client(stub).post("/api/v1/agents/pipeline", json=_body()).json()

    assert data["status"] == "need_input"
    assert data["round"] == 1
    assert data["questions"] == [{
        "slot_key": "purpose", "question": "핵심 용도는요?",
        "options": ["문서 Q&A"], "allow_free_text": True,
    }]
    assert data["agent_id"] is None
    assert [s["status"] for s in data["steps"]][1:] == ["skipped"] * 4


def test_request_fields_are_passed_to_use_case() -> None:
    stub = StubPipeline(_created_items())
    _client(stub).post("/api/v1/agents/pipeline", json=_body(
        history=[{"role": "user", "content": "이전 발화"}],
        answers=[{"slot_key": "purpose", "value": "문서 Q&A"}],
        round=1,
        tool_ids=["internal:a"],
        name="내 봇",
    ))

    call = stub.calls[0]
    assert call["user_id"] == "7"
    assert call["round_"] == 1
    assert call["tool_ids"] == ("internal:a",)
    assert call["name"] == "내 봇"
    assert call["history"][0].content == "이전 발화"
    assert call["answers"][0].slot_key == "purpose"


def test_unauthenticated_is_rejected_with_401() -> None:
    """무인증은 401 (Design §4.5 그대로 — 이 FastAPI 버전의 HTTPBearer 실측).

    느슨한 (401, 403) 단언은 계약을 못박지 못한다 (Analysis G-06) — 실측값
    하나로 고정한다. 프레임워크 업그레이드로 바뀌면 이 테스트가 알려준다.
    """
    stub = StubPipeline(_created_items())
    response = _client(stub, authed=False).post(
        "/api/v1/agents/pipeline", json=_body()
    )
    assert response.status_code == 401


@pytest.mark.parametrize("body", [
    {"user_request": "가" * 1001},
    {"user_request": "요청", "tool_ids": [f"t{i}" for i in range(51)]},
    {"user_request": "요청", "round": -1},
    {"user_request": ""},
])
def test_invalid_input_is_422(body: dict) -> None:
    stub = StubPipeline(_created_items())
    assert _client(stub).post(
        "/api/v1/agents/pipeline", json=body
    ).status_code == 422


# ── 실패 매트릭스 (§8.2 #7, #8) ─────────────────────────────────────────────


def test_storage_failure_is_500_not_disguised() -> None:
    stub = StubPipeline([
        *_stage_events(_record(PipelineStage.INTENT)),
        RuntimeError("db down"),
    ])
    response = _client(stub, raise_server_exceptions=False).post(
        "/api/v1/agents/pipeline", json=_body()
    )
    assert response.status_code == 500


def test_create_validation_error_is_422() -> None:
    stub = StubPipeline([ValueError("LLM 모델 없음")])
    response = _client(stub).post("/api/v1/agents/pipeline", json=_body())
    assert response.status_code == 422


def test_foreign_session_is_404() -> None:
    stub = StubPipeline([PromptSessionNotFoundError("s1")])
    response = _client(stub).post("/api/v1/agents/pipeline", json=_body())
    assert response.status_code == 404


# ── SSE (§8.2 #12, #13 + FR-15) ─────────────────────────────────────────────


def test_sse_emits_ordered_events_with_monotonic_seq() -> None:
    stub = StubPipeline(_created_items())
    response = _client(stub).post(
        "/api/v1/agents/pipeline/stream", json=_body()
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    kinds = [name for name, _, _ in events]
    assert kinds == (
        ["stage_started", "stage_completed"] * 5 + ["pipeline_result"]
    )
    assert [seq for _, seq, _ in events] == list(range(11))
    assert events[-1][2]["status"] == "created"


def test_sse_final_payload_equals_sync_response() -> None:
    """FR-15 — 같은 입력이면 두 전송 방식의 최종 payload 가 동일하다."""
    sync_data = _client(StubPipeline(_created_items())).post(
        "/api/v1/agents/pipeline", json=_body()
    ).json()
    sse_events = _parse_sse(_client(StubPipeline(_created_items())).post(
        "/api/v1/agents/pipeline/stream", json=_body()
    ).text)

    assert sse_events[-1][2] == sync_data


def test_sse_failure_emits_stage_failed_then_failed_result() -> None:
    stub = StubPipeline([
        *_stage_events(_record(PipelineStage.INTENT)),
        *_stage_events(_record(PipelineStage.TOOLS)),
        StageEvent(
            "stage_started",
            StageRecord(PipelineStage.PROMPT, StageStatus.OK),
        ),
        RuntimeError("version store down"),
    ])
    events = _parse_sse(_client(stub).post(
        "/api/v1/agents/pipeline/stream", json=_body()
    ).text)

    kinds = [name for name, _, _ in events]
    assert kinds[-2:] == ["stage_failed", "pipeline_result"]
    failed = events[-2][2]
    assert failed["stage"] == "prompt"
    assert failed["status"] == "failed"
    final = events[-1][2]
    assert final["status"] == "failed"
    assert [s["status"] for s in final["steps"]] == [
        "ok", "ok", "failed", "skipped", "skipped",
    ]


# ── 라우터 등록 순서 (§4.1 와일드카드 함정) ─────────────────────────────────


def test_pipeline_route_wins_over_agent_builder_wildcards() -> None:
    """main.py 와 동일한 상대 순서(파이프라인 먼저)에서 /pipeline 이
    /{agent_id} 계열에 삼켜지지 않는다."""
    from src.api.routes.agent_builder_router import router as builder_router

    stub = StubPipeline(_created_items())
    app = FastAPI()
    app.include_router(router)          # main.py: DI 섹션에서 먼저 등록
    app.include_router(builder_router)  # main.py: 5114줄 블록에서 나중 등록
    app.dependency_overrides[get_agent_pipeline_use_case] = lambda: stub
    app.dependency_overrides[get_current_user] = lambda: _user()
    client = TestClient(app)

    response = client.post("/api/v1/agents/pipeline", json=_body())

    assert response.status_code == 200
    assert response.json()["agent_id"] == "agt1"


# ── Act-1 보강 (Analysis G-01/G-04/G-05 + 시나리오 #9 API층) ────────────────


def test_sse_stage_started_payload_is_stage_only() -> None:
    """§4.4 계약 — started 는 `{"stage": ...}` 만 싣는다 (Analysis G-05).

    StageRecord 전문을 실으면 status:"ok" 가 '이미 성공'으로 오독된다.
    """
    stub = StubPipeline(_created_items())
    events = _parse_sse(_client(stub).post(
        "/api/v1/agents/pipeline/stream", json=_body()
    ).text)

    started = [data for name, _, data in events if name == "stage_started"]
    assert started[0] == {"stage": "intent"}
    assert all(set(data.keys()) == {"stage"} for data in started)


def test_sse_emits_heartbeat_while_stage_is_slow(monkeypatch) -> None:
    """느린 단계 대기 중 주석 라인 heartbeat 가 흐른다 (Analysis G-01 / Plan R2·R7)."""
    import asyncio

    from src.api.routes import agent_pipeline_router as module

    monkeypatch.setattr(module, "_HEARTBEAT_INTERVAL_SEC", 0.01)

    class SlowStub(StubPipeline):
        async def run(self, **kwargs):
            for item in self.items:
                await asyncio.sleep(0.05)
                yield item

    text = _client(SlowStub(_created_items())).post(
        "/api/v1/agents/pipeline/stream", json=_body()
    ).text

    assert ": heartbeat" in text
    data_events = _parse_sse(
        "\n\n".join(
            block for block in text.strip().split("\n\n")
            if not block.startswith(":")
        )
    )
    assert data_events[-1][2]["status"] == "created"  # 이벤트 무손실


def test_bind_failure_is_surfaced_in_created_response() -> None:
    """시나리오 #9 API층 — created 인데 bind_ok=false + steps.bind=failed."""
    records = [
        _record(PipelineStage.INTENT),
        _record(PipelineStage.TOOLS),
        _record(PipelineStage.PROMPT),
        _record(PipelineStage.CREATE),
        _record(PipelineStage.BIND, StageStatus.FAILED, "이미 바인딩된 세션"),
    ]
    items: list = []
    for record in records:
        items.extend(_stage_events(record))
    items.append(PipelineOutcome(
        status="created", steps=tuple(records), round=0,
        session_id="ps1", version_id="pv1", agent_id="agt1",
        agent_name="문서 봇", assembled_prompt="프롬프트", bind_ok=False,
    ))

    data = _client(StubPipeline(items)).post(
        "/api/v1/agents/pipeline", json=_body()
    ).json()

    assert data["status"] == "created"
    assert data["agent_id"] == "agt1"
    assert data["bind_ok"] is False
    assert data["steps"][4]["status"] == "failed"


def test_unknown_tool_ids_are_echoed() -> None:
    """Plan FR-03 — 카탈로그에 없는 tool_id 에코백 (Analysis G-04)."""
    items = _created_items()
    outcome = items[-1]
    from dataclasses import replace as dc_replace
    items[-1] = dc_replace(outcome, unknown_tool_ids=("missing:x",))

    data = _client(StubPipeline(items)).post(
        "/api/v1/agents/pipeline", json=_body()
    ).json()

    assert data["unknown_tool_ids"] == ["missing:x"]


def test_history_over_20_turns_is_422() -> None:
    """§4.2 — history 요청 상한 (Analysis G-08, prompt_composer 스키마와 동일)."""
    turns = [{"role": "user", "content": f"t{i}"} for i in range(21)]
    response = _client(StubPipeline(_created_items())).post(
        "/api/v1/agents/pipeline", json=_body(history=turns)
    )
    assert response.status_code == 422
