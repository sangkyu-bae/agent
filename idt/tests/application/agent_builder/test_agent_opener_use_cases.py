"""agent-opener Design §4.3 — 5개 use case 의 opener_repo 배선 테스트 (fake repo).

Plan FR-02/03/04/05/07. 미주입(None) 시 기존 동작 무변경도 함께 고정한다.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.fork_agent_use_case import ForkAgentUseCase
from src.application.agent_builder.get_agent_use_case import GetAgentUseCase
from src.application.agent_builder.list_my_agents_use_case import ListMyAgentsUseCase
from src.application.agent_builder.schemas import CreateAgentRequest, UpdateAgentRequest
from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.agent_opener.interfaces import AgentOpenerRepositoryInterface
from src.domain.llm_model.entity import LlmModel

PROMPT = "테스트 지침"


class FakeOpenerRepo(AgentOpenerRepositoryInterface):
    def __init__(self, store: dict[str, list[str]] | None = None):
        self.store: dict[str, list[str]] = dict(store or {})
        self.batch_calls = 0
        self.replace_calls: list[tuple[str, list[str]]] = []

    async def list_by_agent_id(self, agent_id, request_id):
        return list(self.store.get(agent_id, []))

    async def list_by_agent_ids(self, agent_ids, request_id):
        self.batch_calls += 1
        return {a: list(self.store[a]) for a in agent_ids if a in self.store}

    async def replace(self, agent_id, texts, request_id):
        self.replace_calls.append((agent_id, list(texts)))
        self.store[agent_id] = list(texts)
        return list(texts)


def _agent(
    agent_id: str | None = None,
    user_id: str = "user-1",
    visibility: str = "private",
    forked_from: str | None = None,
) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=agent_id or str(uuid.uuid4()),
        user_id=user_id,
        name="에이전트",
        description="설명",
        system_prompt=PROMPT,
        flow_hint="힌트",
        workers=[],
        llm_model_id="model-1",
        status="active",
        visibility=visibility,
        forked_from=forked_from,
        created_at=now,
        updated_at=now,
    )


def _llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


# ── Create ────────────────────────────────────────────────────────────


def _create_uc(opener_repo):
    repository = MagicMock()
    repository.save = AsyncMock(side_effect=lambda a, r: a)
    llm = MagicMock()
    llm.find_by_id = AsyncMock(return_value=_llm_model())
    llm.find_default = AsyncMock(return_value=_llm_model())
    perm = MagicMock()
    perm.find_by_collection_name = AsyncMock(return_value=None)
    return CreateAgentUseCase(
        repository=repository, llm_model_repository=llm, perm_repo=perm,
        logger=MagicMock(), opener_repo=opener_repo,
    ), repository


class TestCreate:
    @pytest.mark.asyncio
    async def test_saves_normalized_openers_and_echoes(self):
        repo = FakeOpenerRepo()
        uc, _ = _create_uc(repo)
        req = CreateAgentRequest(
            user_request="r", name="n", user_id="user-1", system_prompt=PROMPT,
            openers=[" 질문 A ", "질문 B"],
        )
        result = await uc.execute(req, "req-1")
        assert result.openers == ["질문 A", "질문 B"]
        assert repo.replace_calls == [(result.agent_id, ["질문 A", "질문 B"])]

    @pytest.mark.asyncio
    async def test_no_openers_means_no_replace(self):
        repo = FakeOpenerRepo()
        uc, _ = _create_uc(repo)
        req = CreateAgentRequest(
            user_request="r", name="n", user_id="user-1", system_prompt=PROMPT,
        )
        result = await uc.execute(req, "req-1")
        assert result.openers == []
        assert repo.replace_calls == []

    @pytest.mark.asyncio
    async def test_invalid_openers_rejected_before_save(self):
        repo = FakeOpenerRepo()
        uc, repository = _create_uc(repo)
        req = CreateAgentRequest(
            user_request="r", name="n", user_id="user-1", system_prompt=PROMPT,
            openers=["a", "a"],
        )
        with pytest.raises(ValueError, match="중복"):
            await uc.execute(req, "req-1")
        repository.save.assert_not_awaited()
        assert repo.replace_calls == []

    @pytest.mark.asyncio
    async def test_without_repo_injection_openers_ignored(self):
        uc, _ = _create_uc(None)
        req = CreateAgentRequest(
            user_request="r", name="n", user_id="user-1", system_prompt=PROMPT,
            openers=["q"],
        )
        result = await uc.execute(req, "req-1")
        assert result.openers == []


# ── Update ────────────────────────────────────────────────────────────


def _update_uc(agent: AgentDefinition, opener_repo):
    repository = MagicMock()
    repository.find_by_id = AsyncMock(return_value=agent)
    repository.update = AsyncMock(return_value=agent)
    perm = MagicMock()
    perm.find_by_collection_name = AsyncMock(return_value=None)
    return UpdateAgentUseCase(
        repository=repository, perm_repo=perm, logger=MagicMock(),
        opener_repo=opener_repo,
    )


class TestUpdate:
    @pytest.mark.asyncio
    async def test_none_means_unchanged(self):
        agent = _agent()
        repo = FakeOpenerRepo({agent.id: ["기존"]})
        uc = _update_uc(agent, repo)
        await uc.execute(agent.id, UpdateAgentRequest(name="새 이름"), "req-1")
        assert repo.replace_calls == []
        assert repo.store[agent.id] == ["기존"]

    @pytest.mark.asyncio
    async def test_empty_list_clears(self):
        agent = _agent()
        repo = FakeOpenerRepo({agent.id: ["기존"]})
        uc = _update_uc(agent, repo)
        await uc.execute(agent.id, UpdateAgentRequest(openers=[]), "req-1")
        assert repo.store[agent.id] == []

    @pytest.mark.asyncio
    async def test_list_replaces_whole(self):
        agent = _agent()
        repo = FakeOpenerRepo({agent.id: ["기존"]})
        uc = _update_uc(agent, repo)
        await uc.execute(
            agent.id, UpdateAgentRequest(openers=[" x ", "y"]), "req-1"
        )
        assert repo.store[agent.id] == ["x", "y"]

    @pytest.mark.asyncio
    async def test_duplicate_raises_value_error(self):
        agent = _agent()
        repo = FakeOpenerRepo()
        uc = _update_uc(agent, repo)
        with pytest.raises(ValueError, match="중복"):
            await uc.execute(
                agent.id, UpdateAgentRequest(openers=["a", " a"]), "req-1"
            )
        assert repo.replace_calls == []


# ── Get ───────────────────────────────────────────────────────────────


class TestGet:
    @pytest.mark.asyncio
    async def test_response_includes_openers(self):
        agent = _agent()
        repo = FakeOpenerRepo({agent.id: ["a", "b"]})
        repository = MagicMock()
        repository.find_by_id = AsyncMock(return_value=agent)
        dept = MagicMock()
        dept.find_by_id = AsyncMock(return_value=None)
        uc = GetAgentUseCase(
            repository=repository, dept_repository=dept, logger=MagicMock(),
            opener_repo=repo,
        )
        result = await uc.execute(agent.id, "req-1")
        assert result.openers == ["a", "b"]

    @pytest.mark.asyncio
    async def test_without_repo_is_empty(self):
        agent = _agent()
        repository = MagicMock()
        repository.find_by_id = AsyncMock(return_value=agent)
        dept = MagicMock()
        dept.find_by_id = AsyncMock(return_value=None)
        uc = GetAgentUseCase(
            repository=repository, dept_repository=dept, logger=MagicMock(),
        )
        result = await uc.execute(agent.id, "req-1")
        assert result.openers == []


# ── List my ───────────────────────────────────────────────────────────


class TestListMy:
    @pytest.mark.asyncio
    async def test_batch_once_for_paged_items_only(self):
        owned = [_agent(agent_id=f"a{i}") for i in range(3)]
        repo = FakeOpenerRepo({"a0": ["q0"], "a2": ["q2"]})
        agent_repo = MagicMock()
        agent_repo.list_by_user = AsyncMock(return_value=owned)
        sub_repo = MagicMock()
        sub_repo.list_by_user = AsyncMock(return_value=[])
        uc = ListMyAgentsUseCase(
            agent_repo=agent_repo, subscription_repo=sub_repo,
            logger=MagicMock(), opener_repo=repo,
        )
        result = await uc.execute(
            user_id="user-1", filter_type="owned", search=None,
            page=1, size=2, request_id="req-1",
        )
        assert repo.batch_calls == 1
        by_id = {a.agent_id: a.openers for a in result.agents}
        assert len(by_id) == 2
        for agent_id, openers in by_id.items():
            assert openers == repo.store.get(agent_id, [])

    @pytest.mark.asyncio
    async def test_without_repo_openers_empty(self):
        owned = [_agent(agent_id="a0")]
        agent_repo = MagicMock()
        agent_repo.list_by_user = AsyncMock(return_value=owned)
        sub_repo = MagicMock()
        sub_repo.list_by_user = AsyncMock(return_value=[])
        uc = ListMyAgentsUseCase(
            agent_repo=agent_repo, subscription_repo=sub_repo, logger=MagicMock(),
        )
        result = await uc.execute(
            user_id="user-1", filter_type="all", search=None,
            page=1, size=20, request_id="req-1",
        )
        assert result.agents[0].openers == []


# ── Fork ──────────────────────────────────────────────────────────────


class TestFork:
    @pytest.mark.asyncio
    async def test_copies_openers_to_fork(self):
        source = _agent(agent_id="src", user_id="owner", visibility="public")
        repo = FakeOpenerRepo({"src": ["a", "b"]})
        agent_repo = AsyncMock()
        agent_repo.find_by_id.return_value = source
        agent_repo.save.side_effect = lambda a, r: a
        uc = ForkAgentUseCase(
            agent_repo=agent_repo, logger=MagicMock(), opener_repo=repo
        )
        result = await uc.execute("src", "forker", None, [], "req-1")
        assert repo.store[result.agent_id] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_source_without_openers_no_replace(self):
        source = _agent(agent_id="src", user_id="owner", visibility="public")
        repo = FakeOpenerRepo()
        agent_repo = AsyncMock()
        agent_repo.find_by_id.return_value = source
        agent_repo.save.side_effect = lambda a, r: a
        uc = ForkAgentUseCase(
            agent_repo=agent_repo, logger=MagicMock(), opener_repo=repo
        )
        await uc.execute("src", "forker", None, [], "req-1")
        assert repo.replace_calls == []
