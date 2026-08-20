"""prompt-composer Design §8.4 — UseCase 통합 테스트 (대역 기반).

UseCase 는 흐름만 제어한다. 여기서 검증하는 것은 순서와 위임이지 규칙이 아니다:
조립 규칙은 domain 테스트가, 실패 흡수는 어댑터 테스트가 이미 덮는다.

핵심은 **UseCase 에 try/except 가 없다**는 계약(P5)의 결과다 — 어댑터가 흡수한
degraded 는 그대로 저장되고, DB 예외는 그대로 전파된다 (Design §6.2).
"""
import pytest
from src.application.prompt_composer.compose_prompt_use_case import (
    ComposePromptUseCase,
)
from src.application.prompt_composer.errors import (
    AgentAlreadyBoundError,
    PromptSessionNotFoundError,
)
from src.domain.prompt_composer.schemas import (
    PromptSections,
    RoleSection,
    ToolGuide,
    ToolMeta,
)

_USER = "user-1"


class _FakeLogger:
    def info(self, msg, **kw): ...
    def warning(self, msg, **kw): ...
    def error(self, msg, **kw): ...
    def debug(self, msg, **kw): ...


class _FakeReader:
    def __init__(self, metas=(), unknown=()):
        self._metas = metas
        self._unknown = unknown
        self.calls: list[tuple] = []

    async def fetch(self, tool_ids):
        self.calls.append(tool_ids)
        return self._metas, self._unknown


class _FakeGenerator:
    def __init__(self, sections=None, degraded=False, reason=None, elapsed=42):
        self._sections = sections or _sections()
        self._degraded = degraded
        self._reason = reason
        self._elapsed = elapsed
        self.calls: list[dict] = []

    async def generate(self, user_request, metas, intent, history, request_id):
        self.calls.append(
            {
                "user_request": user_request,
                "metas": metas,
                "intent": intent,
                "history": history,
                "request_id": request_id,
            }
        )
        return self._sections, self._degraded, self._reason, self._elapsed


class _FakeRepo:
    def __init__(self, sessions=None):
        self.sessions = sessions or {}
        self.versions: list[dict] = []
        self.created: list[tuple] = []
        self.raise_on_append: Exception | None = None

    async def create_session(self, user_id, user_request, agent_id):
        session_id = f"s{len(self.sessions) + 1}"
        self.created.append((user_id, user_request, agent_id))
        self.sessions[session_id] = {
            "user_id": user_id,
            "agent_id": agent_id,
            "user_request": user_request,
        }
        return session_id

    async def find_session(self, session_id, user_id):
        found = self.sessions.get(session_id)
        if found is None or found["user_id"] != user_id:
            return None
        return found

    async def append_version(self, session_id, prompt, intent_snapshot, tool_ids):
        if self.raise_on_append is not None:
            raise self.raise_on_append
        self.versions.append(
            {
                "session_id": session_id,
                "prompt": prompt,
                "intent_snapshot": intent_snapshot,
                "tool_ids": tool_ids,
            }
        )
        return f"v{len(self.versions)}", len(self.versions)

    async def list_versions(self, session_id):
        return [v for v in self.versions if v["session_id"] == session_id]

    async def bind_agent(self, session_id, user_id, agent_id):
        found = await self.find_session(session_id, user_id)
        if found is None:
            return None
        if found["agent_id"]:
            return "conflict"
        found["agent_id"] = agent_id
        return "ok"


def _meta(tool_id: str, name: str = "도구") -> ToolMeta:
    return ToolMeta(tool_id=tool_id, name=name, description="설명")


def _sections(guide_ids=("t1",)) -> PromptSections:
    return PromptSections(
        purpose="목적입니다.",
        roles=(RoleSection(title="검색", detail="찾는다"),),
        tool_guides=tuple(
            ToolGuide(tool_id=tid, name="도구", when="언제", how="어떻게")
            for tid in guide_ids
        ),
        principles=("한국어로 답한다",),
    )


def _use_case(reader=None, generator=None, repo=None) -> ComposePromptUseCase:
    return ComposePromptUseCase(
        generator=generator or _FakeGenerator(),
        tool_reader=reader or _FakeReader(),
        repository=repo or _FakeRepo(),
        logger=_FakeLogger(),
    )


# ── 정상 흐름 ───────────────────────────────────────────────────────────────


async def test_compose_creates_session_and_first_version():
    repo = _FakeRepo()
    uc = _use_case(reader=_FakeReader(metas=(_meta("t1"),)), repo=repo)
    result = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    assert result.version_no == 1
    assert result.session_id == "s1"
    assert repo.created == [(_USER, "요청", None)]


async def test_compose_assembles_prompt_string():
    uc = _use_case(reader=_FakeReader(metas=(_meta("t1"),)))
    result = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    assert result.prompt.assembled.startswith("목적입니다.")
    # prompt-depth §4.3 — 조립 표기가 대괄호에서 마크다운 헤딩으로 바뀌었다.
    assert "## Tool Guidelines" in result.prompt.assembled


async def test_compose_passes_tool_ids_to_reader():
    reader = _FakeReader(metas=(_meta("t1"),))
    uc = _use_case(reader=reader)
    await uc.compose(
        user_id=_USER, user_request="요청", request_id="r1", tool_ids=("t1", "t2")
    )
    assert reader.calls == [("t1", "t2")]


async def test_compose_forwards_metas_to_generator():
    generator = _FakeGenerator()
    uc = _use_case(reader=_FakeReader(metas=(_meta("t1"),)), generator=generator)
    await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    assert generator.calls[0]["metas"] == (_meta("t1"),)
    assert generator.calls[0]["request_id"] == "r1"


async def test_compose_clamps_history_before_generation():
    generator = _FakeGenerator()
    uc = _use_case(generator=generator)
    history = [{"role": "user", "content": "가" * 2000}] * 40
    await uc.compose(
        user_id=_USER, user_request="요청", request_id="r1", history=history
    )
    passed = generator.calls[0]["history"]
    assert len(passed) == 20
    assert len(passed[0]["content"]) == 1000


# ── 환각 폐기 / 미존재 도구 (E5 · E6) ───────────────────────────────────────


async def test_compose_drops_guides_outside_candidates():
    generator = _FakeGenerator(sections=_sections(guide_ids=("t1", "ghost")))
    uc = _use_case(reader=_FakeReader(metas=(_meta("t1"),)), generator=generator)
    result = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    assert result.prompt.dropped_tool_ids == ("ghost",)
    assert "ghost" not in result.prompt.assembled


async def test_compose_reports_unknown_tool_ids():
    reader = _FakeReader(metas=(_meta("t1"),), unknown=("ghost:tool",))
    uc = _use_case(reader=reader)
    result = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    assert result.prompt.unknown_tool_ids == ("ghost:tool",)


async def test_compose_saves_only_surviving_tool_ids():
    repo = _FakeRepo()
    generator = _FakeGenerator(sections=_sections(guide_ids=("t1", "ghost")))
    uc = _use_case(
        reader=_FakeReader(metas=(_meta("t1"),)), generator=generator, repo=repo
    )
    await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    assert repo.versions[0]["tool_ids"] == ("t1",)


# ── degraded 통과 저장 (SC-02 · P5) ─────────────────────────────────────────


async def test_compose_persists_degraded_result():
    repo = _FakeRepo()
    generator = _FakeGenerator(degraded=True, reason="timeout")
    uc = _use_case(generator=generator, repo=repo)
    result = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    assert result.prompt.degraded is True
    assert result.prompt.reason == "timeout"
    assert repo.versions[0]["prompt"].degraded is True


async def test_compose_records_elapsed_from_generator():
    uc = _use_case(generator=_FakeGenerator(elapsed=777))
    result = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    assert result.prompt.elapsed_ms == 777


# ── intent 스냅샷 (FR-13 · §3.4) ────────────────────────────────────────────


async def test_compose_stores_intent_snapshot_verbatim():
    repo = _FakeRepo()
    uc = _use_case(repo=repo)
    intent = {"label": "qa", "degraded": False, "unknown_future_key": [1]}
    await uc.compose(
        user_id=_USER, user_request="요청", request_id="r1", intent=intent
    )
    assert repo.versions[0]["intent_snapshot"] == intent


async def test_compose_stores_null_snapshot_when_intent_degraded():
    repo = _FakeRepo()
    uc = _use_case(repo=repo)
    await uc.compose(
        user_id=_USER,
        user_request="요청",
        request_id="r1",
        intent={"label": "qa", "degraded": True},
    )
    assert repo.versions[0]["intent_snapshot"] is None


async def test_compose_does_not_forward_degraded_intent_to_generator():
    generator = _FakeGenerator()
    uc = _use_case(generator=generator)
    await uc.compose(
        user_id=_USER,
        user_request="요청",
        request_id="r1",
        intent={"label": "qa", "degraded": True},
    )
    assert generator.calls[0]["intent"] is None


# ── 세션 재사용 / 소유권 (FR-08 · E9) ───────────────────────────────────────


async def test_compose_appends_to_existing_session():
    repo = _FakeRepo()
    uc = _use_case(repo=repo)
    first = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    second = await uc.compose(
        user_id=_USER,
        user_request="요청",
        request_id="r2",
        session_id=first.session_id,
    )
    assert second.session_id == first.session_id
    assert second.version_no == 2
    assert len(repo.created) == 1


async def test_compose_raises_for_other_users_session():
    repo = _FakeRepo()
    uc = _use_case(repo=repo)
    mine = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    with pytest.raises(PromptSessionNotFoundError):
        await uc.compose(
            user_id="intruder",
            user_request="요청",
            request_id="r2",
            session_id=mine.session_id,
        )


async def test_compose_raises_for_missing_session():
    uc = _use_case()
    with pytest.raises(PromptSessionNotFoundError):
        await uc.compose(
            user_id=_USER,
            user_request="요청",
            request_id="r1",
            session_id="nope",
        )


async def test_compose_does_not_save_when_session_lookup_fails():
    repo = _FakeRepo()
    uc = _use_case(repo=repo)
    with pytest.raises(PromptSessionNotFoundError):
        await uc.compose(
            user_id=_USER, user_request="요청", request_id="r1", session_id="nope"
        )
    assert repo.versions == []


# ── DB 예외는 전파된다 (Design §6.2 — degraded 로 위장하지 않는다) ───────────


async def test_storage_failure_propagates_instead_of_degrading():
    repo = _FakeRepo()
    repo.raise_on_append = RuntimeError("db down")
    uc = _use_case(repo=repo)
    with pytest.raises(RuntimeError):
        await uc.compose(user_id=_USER, user_request="요청", request_id="r1")


def test_use_case_source_has_no_try_except():
    """P5 — 어댑터가 모든 LLM 실패를 흡수하므로 UseCase 에 예외 처리가 없다.

    문자열 검색이 아니라 AST 로 본다 — 설계 근거를 적은 주석·독스트링에는
    'try/except' 라는 단어가 당연히 등장하기 때문이다.
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[3]
        / "src" / "application" / "prompt_composer" / "compose_prompt_use_case.py"
    ).read_text(encoding="utf-8")
    handlers = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Try, ast.ExceptHandler))
    ]
    assert handlers == []


def test_use_case_calls_only_declared_repository_methods():
    """Design §9.2 규칙 3 — application 은 포트에 선언된 것만 호출한다.

    Protocol 은 런타임·정적 검사 모두 미선언 호출을 잡아주지 않는다. UseCase 가
    `self._repository.X` 로 부르는 이름을 AST 로 모아 포트 선언과 대조한다.
    """
    import ast
    from pathlib import Path

    from src.domain.prompt_composer.interfaces import PromptRepositoryPort

    source = (
        Path(__file__).resolve().parents[3]
        / "src" / "application" / "prompt_composer" / "compose_prompt_use_case.py"
    ).read_text(encoding="utf-8")
    called = {
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "_repository"
    }
    declared = {n for n in dir(PromptRepositoryPort) if not n.startswith("_")}
    assert called and called <= declared, f"포트 미선언 호출: {called - declared}"


# ── 조회 / 백필 (FR-09 · FR-10) ─────────────────────────────────────────────


async def test_get_session_returns_session_and_versions():
    repo = _FakeRepo()
    uc = _use_case(repo=repo)
    created = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    session, versions = await uc.get_session(created.session_id, _USER)
    assert session is not None
    assert len(versions) == 1


async def test_get_session_raises_for_other_user():
    repo = _FakeRepo()
    uc = _use_case(repo=repo)
    created = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    with pytest.raises(PromptSessionNotFoundError):
        await uc.get_session(created.session_id, "intruder")


async def test_bind_agent_succeeds_once():
    repo = _FakeRepo()
    uc = _use_case(repo=repo)
    created = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    await uc.bind_agent(created.session_id, _USER, "agent-1")
    assert repo.sessions[created.session_id]["agent_id"] == "agent-1"


async def test_bind_agent_raises_conflict_when_already_bound():
    repo = _FakeRepo()
    uc = _use_case(repo=repo)
    created = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    await uc.bind_agent(created.session_id, _USER, "agent-1")
    with pytest.raises(AgentAlreadyBoundError):
        await uc.bind_agent(created.session_id, _USER, "agent-2")


async def test_bind_agent_raises_not_found_for_other_user():
    repo = _FakeRepo()
    uc = _use_case(repo=repo)
    created = await uc.compose(user_id=_USER, user_request="요청", request_id="r1")
    with pytest.raises(PromptSessionNotFoundError):
        await uc.bind_agent(created.session_id, "intruder", "agent-1")
