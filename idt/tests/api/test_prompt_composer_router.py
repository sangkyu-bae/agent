"""/api/v1/prompt-composer 통합 테스트 (Design §8.3).

핵심 계약 3개:
- LLM 실패는 5xx 가 아니라 **200 + degraded=true** (Plan D6).
- **저장 실패는 500** — degraded 로 위장하지 않는다 (Design §6.2).
- 타인 세션은 403 이 아니라 **404** (SC-07, 존재 노출 방지).
"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.prompt_composer_router import (
    get_append_human_version_use_case,
    get_prompt_composer_use_case,
    router,
)
from src.application.prompt_composer.append_human_version_use_case import (
    HumanVersionResult,
)
from src.application.prompt_composer.compose_prompt_use_case import ComposeResult
from src.application.prompt_composer.errors import (
    AgentAlreadyBoundError,
    PromptSessionNotFoundError,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.prompt_composer.schemas import (
    ComposedPrompt,
    ContextSection,
    PromptSections,
    RoleSection,
    ToolGuide,
    WorkflowSection,
)
from src.interfaces.dependencies.auth import get_current_user
from src.interfaces.schemas.prompt_composer import (
    MAX_ASSEMBLED_CHARS,
    SectionsOut,
)


def _user(uid: int = 7) -> User:
    return User(
        email="t@t.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=uid,
    )


def _prompt(degraded: bool = False, reason: str | None = None) -> ComposedPrompt:
    sections = PromptSections(
        purpose="사내 문서를 검색해 답하는 에이전트입니다.",
        roles=(RoleSection(title="검색", detail="규정을 찾는다"),),
        tool_guides=(
            ToolGuide(
                tool_id="internal:excel_export",
                name="엑셀 내보내기",
                when="표 저장 요청 시",
                how="행 데이터를 전달한다",
                caution="수치를 지어내지 않는다",
            ),
        ),
        principles=("한국어로 답한다",),
        # prompt-depth §4.2 — 신규 3섹션이 응답에 실리는지 확인하기 위한 재료.
        identity="규정 전문가입니다.",
        context=ContextSection(
            constraints=("추측하지 않는다",), background=("2026 개정판 기준",)
        ),
        workflows=(
            WorkflowSection(situation="일반 요청", steps=("찾는다", "답한다")),
        ),
        style="격식체로 답한다.",
    )
    return ComposedPrompt(
        sections=sections,
        assembled=(
            "사내 문서를 검색해 답하는 에이전트입니다.\n\n"
            "## Core Responsibilities\n- 검색: 규정을 찾는다"
        ),
        degraded=degraded,
        reason=reason,
        dropped_tool_ids=("ghost",),
        unknown_tool_ids=("missing:tool",),
        elapsed_ms=2431,
    )


class StubUseCase:
    """ComposePromptUseCase 대역."""

    def __init__(self, result=None, error: Exception | None = None):
        self.result = result or ComposeResult("s1", "v1", 1, _prompt())
        self.error = error
        self.calls: list[dict] = []
        self.session = SimpleNamespace(
            id="s1",
            agent_id=None,
            user_request="사내 규정 봇",
            created_at=datetime(2026, 8, 17, 5, 0, 0),
        )
        self.versions = [
            SimpleNamespace(
                id="v1",
                version_no=1,
                degraded=False,
                reason=None,
                tool_ids=["internal:excel_export"],
                assembled="조립된 프롬프트",
                source="llm",
                created_at=datetime(2026, 8, 17, 5, 0, 0),
            )
        ]
        self.bind_error: Exception | None = None
        self.bound: list[tuple] = []

    async def compose(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result

    async def get_session(self, session_id, user_id):
        if self.error is not None:
            raise self.error
        return self.session, self.versions

    async def bind_agent(self, session_id, user_id, agent_id):
        if self.bind_error is not None:
            raise self.bind_error
        self.bound.append((session_id, user_id, agent_id))


class StubAppendUseCase:
    """AppendHumanVersionUseCase 대역 (agent-create-wizard §4.5)."""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[dict] = []

    async def append(self, session_id, user_id, assembled, tool_ids=()):
        self.calls.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "assembled": assembled,
                "tool_ids": tool_ids,
            }
        )
        if self.error is not None:
            raise self.error
        return HumanVersionResult(session_id, "v-h1", 2)


def _client(
    use_case: StubUseCase,
    user: User | None = None,
    append_use_case: "StubAppendUseCase | None" = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_prompt_composer_use_case] = lambda: use_case
    app.dependency_overrides[get_append_human_version_use_case] = (
        lambda: append_use_case or StubAppendUseCase()
    )
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    return TestClient(app)


def _body(**kw) -> dict:
    base = {"user_request": "사내 규정 문서를 찾아 답하는 봇"}
    base.update(kw)
    return base


# ── POST /compose 정상 ──────────────────────────────────────────────────────


def test_compose_returns_200_with_sections_and_assembled():
    client = _client(StubUseCase())
    res = client.post("/api/v1/prompt-composer/compose", json=_body())
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == "s1"
    assert data["version_no"] == 1
    assert data["sections"]["purpose"].startswith("사내 문서를")
    assert data["assembled"] != ""


def test_compose_response_carries_every_new_section():
    """prompt-depth §4.2 — 응답만 신규 섹션을 빠뜨리면 화면이 알 방법이 없다."""
    client = _client(StubUseCase())
    sections = client.post(
        "/api/v1/prompt-composer/compose", json=_body()
    ).json()["sections"]
    assert sections["identity"] == "규정 전문가입니다."
    assert sections["context"]["constraints"] == ["추측하지 않는다"]
    assert sections["context"]["background"] == ["2026 개정판 기준"]
    assert sections["workflows"][0]["situation"] == "일반 요청"
    assert sections["workflows"][0]["steps"] == ["찾는다", "답한다"]
    assert sections["style"] == "격식체로 답한다."


def test_sections_out_is_additive_for_old_producers():
    """신규 필드는 전부 기본값 — 구형 4섹션만 채워도 응답이 성립한다."""
    out = SectionsOut(purpose="목적", roles=[], tool_guides=[], principles=[])
    assert out.identity == ""
    assert out.context is None
    assert out.workflows == []
    assert out.style == ""


def test_compose_exposes_observability_fields():
    client = _client(StubUseCase())
    data = client.post("/api/v1/prompt-composer/compose", json=_body()).json()
    assert data["dropped_tool_ids"] == ["ghost"]
    assert data["unknown_tool_ids"] == ["missing:tool"]
    assert data["elapsed_ms"] == 2431


def test_compose_forwards_all_inputs_to_use_case():
    stub = StubUseCase()
    client = _client(stub)
    client.post(
        "/api/v1/prompt-composer/compose",
        json=_body(
            tool_ids=["internal:excel_export"],
            history=[{"role": "user", "content": "이전 질문"}],
            intent={"label": "document_qa", "degraded": False},
            session_id="s1",
            agent_id="a1",
        ),
    )
    call = stub.calls[0]
    assert call["tool_ids"] == ("internal:excel_export",)
    assert call["history"] == [{"role": "user", "content": "이전 질문"}]
    assert call["intent"]["label"] == "document_qa"
    assert call["session_id"] == "s1"
    assert call["agent_id"] == "a1"
    assert call["user_id"] == "7"


def test_compose_preserves_unknown_intent_fields():
    """의도 모듈 스키마가 자라도 라우터가 깎아내지 않는다 (Design §3.4)."""
    stub = StubUseCase()
    client = _client(stub)
    client.post(
        "/api/v1/prompt-composer/compose",
        json=_body(intent={"label": "qa", "filled_slots": {"기간": "작년"}}),
    )
    assert stub.calls[0]["intent"]["filled_slots"] == {"기간": "작년"}


def test_compose_generates_request_id_per_call():
    stub = StubUseCase()
    client = _client(stub)
    client.post("/api/v1/prompt-composer/compose", json=_body())
    client.post("/api/v1/prompt-composer/compose", json=_body())
    assert stub.calls[0]["request_id"] != stub.calls[1]["request_id"]


# ── LLM 실패는 200 + degraded (Plan D6 · SC-02) ─────────────────────────────


@pytest.mark.parametrize("reason", ["error", "timeout", "schema", "empty"])
def test_degraded_result_is_200_not_5xx(reason):
    result = ComposeResult("s1", "v1", 1, _prompt(degraded=True, reason=reason))
    client = _client(StubUseCase(result=result))
    res = client.post("/api/v1/prompt-composer/compose", json=_body())
    assert res.status_code == 200
    assert res.json()["degraded"] is True
    assert res.json()["reason"] == reason


# ── 저장 실패는 500 (Design §6.2 — degraded 로 위장하지 않는다) ─────────────


def test_storage_failure_returns_500():
    client = _client(StubUseCase(error=RuntimeError("db down")))
    with pytest.raises(RuntimeError):
        client.post("/api/v1/prompt-composer/compose", json=_body())


# ── 세션 소유권 (SC-07 · E9) ────────────────────────────────────────────────


def test_compose_with_unknown_session_returns_404():
    client = _client(StubUseCase(error=PromptSessionNotFoundError("nope")))
    res = client.post("/api/v1/prompt-composer/compose", json=_body(session_id="x"))
    assert res.status_code == 404


# ── 입력 검증 (FR-12) ───────────────────────────────────────────────────────


def test_empty_user_request_returns_422():
    client = _client(StubUseCase())
    res = client.post("/api/v1/prompt-composer/compose", json=_body(user_request=""))
    assert res.status_code == 422


def test_too_long_user_request_returns_422():
    client = _client(StubUseCase())
    res = client.post(
        "/api/v1/prompt-composer/compose", json=_body(user_request="가" * 1001)
    )
    assert res.status_code == 422


def test_too_many_tool_ids_returns_422():
    client = _client(StubUseCase())
    res = client.post(
        "/api/v1/prompt-composer/compose",
        json=_body(tool_ids=[f"t{i}" for i in range(51)]),
    )
    assert res.status_code == 422


def test_too_many_history_turns_returns_422():
    client = _client(StubUseCase())
    res = client.post(
        "/api/v1/prompt-composer/compose",
        json=_body(history=[{"role": "user", "content": "x"} for _ in range(21)]),
    )
    assert res.status_code == 422


def test_invalid_history_role_returns_422():
    client = _client(StubUseCase())
    res = client.post(
        "/api/v1/prompt-composer/compose",
        json=_body(history=[{"role": "system", "content": "x"}]),
    )
    assert res.status_code == 422


def test_missing_user_request_returns_422():
    client = _client(StubUseCase())
    res = client.post("/api/v1/prompt-composer/compose", json={})
    assert res.status_code == 422


def test_tool_ids_at_limit_is_accepted():
    client = _client(StubUseCase())
    res = client.post(
        "/api/v1/prompt-composer/compose",
        json=_body(tool_ids=[f"t{i}" for i in range(50)]),
    )
    assert res.status_code == 200


# ── GET /sessions/{id} (FR-09) ──────────────────────────────────────────────


def test_get_session_returns_versions():
    client = _client(StubUseCase())
    res = client.get("/api/v1/prompt-composer/sessions/s1")
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == "s1"
    assert data["versions"][0]["version_no"] == 1
    assert "sections" not in data["versions"][0]


def test_get_session_of_other_user_returns_404():
    client = _client(StubUseCase(error=PromptSessionNotFoundError("s1")))
    assert client.get("/api/v1/prompt-composer/sessions/s1").status_code == 404


# ── PATCH /sessions/{id} (FR-10) ────────────────────────────────────────────


def test_bind_agent_returns_200():
    stub = StubUseCase()
    client = _client(stub)
    res = client.patch(
        "/api/v1/prompt-composer/sessions/s1", json={"agent_id": "agent-1"}
    )
    assert res.status_code == 200
    assert stub.bound == [("s1", "7", "agent-1")]


def test_bind_agent_conflict_returns_409():
    stub = StubUseCase()
    stub.bind_error = AgentAlreadyBoundError("s1")
    client = _client(stub)
    res = client.patch(
        "/api/v1/prompt-composer/sessions/s1", json={"agent_id": "agent-2"}
    )
    assert res.status_code == 409


def test_bind_agent_unknown_session_returns_404():
    stub = StubUseCase()
    stub.bind_error = PromptSessionNotFoundError("s1")
    client = _client(stub)
    res = client.patch(
        "/api/v1/prompt-composer/sessions/s1", json={"agent_id": "a1"}
    )
    assert res.status_code == 404


def test_bind_agent_empty_id_returns_422():
    client = _client(StubUseCase())
    res = client.patch("/api/v1/prompt-composer/sessions/s1", json={"agent_id": ""})
    assert res.status_code == 422


# ── POST /sessions/{id}/versions — 사람 편집본 (agent-create-wizard §4.5) ───


def _versions_url(session_id: str = "s1") -> str:
    return f"/api/v1/prompt-composer/sessions/{session_id}/versions"


def test_append_human_version_returns_201():
    stub = StubAppendUseCase()
    client = _client(StubUseCase(), append_use_case=stub)
    res = client.post(
        _versions_url(), json={"assembled": "사람이 고친 프롬프트", "tool_ids": ["t1"]}
    )
    assert res.status_code == 201
    data = res.json()
    assert data["session_id"] == "s1"
    assert data["version_id"] == "v-h1"
    assert data["version_no"] == 2
    assert data["source"] == "human"


def test_append_human_version_forwards_inputs():
    stub = StubAppendUseCase()
    client = _client(StubUseCase(), append_use_case=stub)
    client.post(
        _versions_url("sess-9"),
        json={"assembled": "본문", "tool_ids": ["a", "b"]},
    )
    call = stub.calls[0]
    assert call["session_id"] == "sess-9"
    assert call["user_id"] == "7"
    assert call["assembled"] == "본문"
    assert call["tool_ids"] == ("a", "b")


def test_append_human_version_defaults_tool_ids_to_empty():
    stub = StubAppendUseCase()
    client = _client(StubUseCase(), append_use_case=stub)
    res = client.post(_versions_url(), json={"assembled": "본문"})
    assert res.status_code == 201
    assert stub.calls[0]["tool_ids"] == ()


def test_append_human_version_unknown_or_foreign_session_returns_404():
    """403 이 아니라 404 — 존재 여부를 노출하지 않는다 (기존 계약 승계)."""
    stub = StubAppendUseCase(error=PromptSessionNotFoundError("s1"))
    client = _client(StubUseCase(), append_use_case=stub)
    res = client.post(_versions_url(), json={"assembled": "본문"})
    assert res.status_code == 404


def test_append_human_version_storage_failure_propagates_500():
    """저장 실패를 201 로 위장하지 않는다 (Design §6.2)."""
    stub = StubAppendUseCase(error=RuntimeError("db down"))
    client = _client(StubUseCase(), append_use_case=stub)
    with pytest.raises(RuntimeError):
        client.post(_versions_url(), json={"assembled": "본문"})


@pytest.mark.parametrize(
    "assembled", ["", "x" * (MAX_ASSEMBLED_CHARS + 1)], ids=["empty", "over-limit"]
)
def test_append_human_version_invalid_assembled_returns_422(assembled):
    client = _client(StubUseCase())
    res = client.post(_versions_url(), json={"assembled": assembled})
    assert res.status_code == 422


def test_append_human_version_at_length_limit_is_accepted():
    """상한은 CreateAgentRequest.system_prompt 와 동일해야 한다.

    prompt-depth FR-22 — 4000 → 8000. 여기가 더 받아주면 저장 단계에서 422 가
    나 사용자가 마지막에 실패하고, 덜 받아주면 생성된 프롬프트를 저장할 수 없다.
    """
    client = _client(StubUseCase())
    res = client.post(_versions_url(), json={"assembled": "x" * MAX_ASSEMBLED_CHARS})
    assert res.status_code == 201
    assert MAX_ASSEMBLED_CHARS == 8000


def test_append_human_version_one_over_limit_is_rejected():
    """8000/8001 경계 (Plan R-08)."""
    client = _client(StubUseCase())
    res = client.post(
        _versions_url(), json={"assembled": "x" * (MAX_ASSEMBLED_CHARS + 1)}
    )
    assert res.status_code == 422


def test_append_human_version_too_many_tool_ids_returns_422():
    client = _client(StubUseCase())
    res = client.post(
        _versions_url(),
        json={"assembled": "본문", "tool_ids": [f"t{i}" for i in range(51)]},
    )
    assert res.status_code == 422


def test_append_human_version_missing_assembled_returns_422():
    client = _client(StubUseCase())
    assert client.post(_versions_url(), json={}).status_code == 422


def test_version_summary_exposes_source_field():
    """목록에서 LLM 생성본과 사람 편집본을 구분할 수 있어야 한다 (§3.4)."""
    client = _client(StubUseCase())
    data = client.get("/api/v1/prompt-composer/sessions/s1").json()
    assert data["versions"][0]["source"] == "llm"


# ── 인증 (FR-11) ────────────────────────────────────────────────────────────


def test_append_human_version_requires_authentication():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_append_human_version_use_case] = (
        lambda: StubAppendUseCase()
    )
    client = TestClient(app)
    res = client.post(_versions_url(), json={"assembled": "본문"})
    assert res.status_code == 401


def test_endpoints_require_authentication():
    """DI override 없이 호출하면 인증 의존이 살아 있어 200 이 아니다."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_prompt_composer_use_case] = lambda: StubUseCase()
    client = TestClient(app)
    res = client.post("/api/v1/prompt-composer/compose", json=_body())
    assert res.status_code != 200
