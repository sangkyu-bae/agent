"""추천 후보 필터 — 파이프라인 셀렉터 후보·자연어 컴포저 후보 (tool-access-control module-3 추가 범위).

결정(Do module-3): 추천과 저장 기준을 맞춘다 — 권한 없는 도구는 LLM 후보에 넣지 않는다.
"""
from unittest.mock import AsyncMock, MagicMock

from src.application.agent_create_pipeline.use_case import AgentCreatePipelineUseCase
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.tool_access.value_objects import ToolAccessSet
from src.domain.tool_selection.schemas import ToolCandidate
from tests.application.agent_create_pipeline.test_use_case import (
    FakeComposeUC,
    FakeCreateUC,
    FakeIntentUC,
    FakeLogger,
    FakeSelector,
    FakeCandidateReader,
    _agent_response,
    _compose_result,
    _drain,
    _intent_ok,
    _selection,
)

A = "internal:excel_export"
B = "internal:python_code_executor"
CANDIDATES = (ToolCandidate(tool_id=A, name="엑셀"), ToolCandidate(tool_id=B, name="코드"))


def _resolver(access=None, error=None):
    r = MagicMock()
    r.for_user_id = AsyncMock(return_value=access, side_effect=error)
    r.for_user = AsyncMock(return_value=access, side_effect=error)
    return r


def _pipeline(resolver):
    selector = FakeSelector(_selection(final=(A,), selected=(A,)))
    logger = FakeLogger()
    uc = AgentCreatePipelineUseCase(
        intent_use_case=FakeIntentUC(_intent_ok()),
        candidate_reader=FakeCandidateReader(CANDIDATES),
        tool_selector=selector,
        compose_use_case=FakeComposeUC(_compose_result()),
        create_agent_use_case=FakeCreateUC(_agent_response()),
        logger=logger,
        tool_access_resolver=resolver,
    )
    return uc, selector, logger


class TestPipelineCandidates:
    async def test_selector_sees_only_allowed_candidates(self):
        access = ToolAccessSet(is_admin=False, allowed=frozenset({A}))
        resolver = _resolver(access)
        uc, selector, _ = _pipeline(resolver)
        await _drain(uc, user_id="u7")
        assert [c.tool_id for c in selector.calls[0]["candidates"]] == [A]
        resolver.for_user_id.assert_awaited_once_with("u7", "req1")

    async def test_without_resolver_all_candidates(self):
        uc, selector, _ = _pipeline(None)
        await _drain(uc)
        assert len(selector.calls[0]["candidates"]) == 2

    async def test_resolver_failure_degrades_to_no_candidates(self):
        uc, selector, logger = _pipeline(_resolver(error=RuntimeError("db")))
        await _drain(uc)
        # 후보 0건 → 셀렉터 미호출(기존 empty_candidate 강하 경로)
        assert selector.calls == []
        assert any("tool access" in m for m, _ in logger.warnings)


class TestComposerCandidates:
    def _uc(self, resolver):
        from src.application.agent_composer.compose_agent_use_case import ComposeAgentUseCase

        catalog = MagicMock()
        catalog.list_active = AsyncMock(return_value=[])
        mcp = MagicMock()
        mcp.find_all_active = AsyncMock(return_value=[])
        return ComposeAgentUseCase(
            composer=MagicMock(), tool_catalog_repo=catalog, mcp_server_repo=mcp,
            llm_model_repository=MagicMock(), logger=MagicMock(),
            tool_access_resolver=resolver,
        )

    VIEWER = User(email="u@x", password_hash="h", role=UserRole.USER, status=UserStatus.APPROVED, id=3)

    async def test_filters_registry_candidates(self):
        access = ToolAccessSet(is_admin=False, allowed=frozenset({A}))
        uc = self._uc(_resolver(access))
        candidates, _ = await uc._collect_candidates("rid", viewer=self.VIEWER)
        assert [c.tool_id for c in candidates] == ["excel_export"]

    async def test_without_resolver_unfiltered(self):
        uc = self._uc(None)
        candidates, _ = await uc._collect_candidates("rid", viewer=self.VIEWER)
        assert len(candidates) > 1

    async def test_resolver_without_viewer_is_empty(self):
        uc = self._uc(_resolver(ToolAccessSet.admin()))
        candidates, _ = await uc._collect_candidates("rid")
        assert candidates == []
