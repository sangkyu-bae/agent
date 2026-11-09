"""GetAgentDocumentTemplateUseCase 단위 테스트.

extractor-template-preview Design §8.2 B3–B8.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.agent_builder.get_agent_document_template_use_case import (
    AgentDocumentTemplateNotFoundError,
    AgentNotFoundError,
    GetAgentDocumentTemplateUseCase,
)
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.document_extractor.schemas import DocumentTemplate, TemplateSlot

NOW = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)


def _agent(
    agent_id: str = "agent-1",
    user_id: str = "owner-1",
    template_id: str | None = "tpl-1",
    with_extractor: bool = True,
) -> AgentDefinition:
    workers = [WorkerDefinition("tavily_search", "search_worker", "검색", 0)]
    if with_extractor:
        tool_config = {"template_id": template_id} if template_id else {}
        workers.append(
            WorkerDefinition(
                "document_extractor", "extractor_worker", "양식 채움", 1,
                tool_config=tool_config,
            )
        )
    return AgentDefinition(
        id=agent_id,
        user_id=user_id,
        name="여신 에이전트",
        description="",
        system_prompt="",
        flow_hint="",
        workers=workers,
        llm_model_id="model-1",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )


def _template(agent_id: str = "agent-1", status: str = "active") -> DocumentTemplate:
    return DocumentTemplate(
        id="tpl-1",
        agent_id=agent_id,
        worker_id="extractor_worker",
        name="여신 승인 신청서",
        html_skeleton="<p>차주: {{borrower_name}}</p><p>{{opinion}}</p>",
        slots=[
            TemplateSlot(
                key="borrower_name", label="차주명", slot_type="value",
                description="차주 이름", fill_hint="내부 지침", sample_value="홍길동",
            ),
            TemplateSlot(
                key="opinion", label="심사의견", slot_type="generated",
                sample_value="상환 능력 양호",
            ),
        ],
        source_file_ref="/data/templates/secret.docx",
        source_format="docx",
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def _use_case(agents: dict, template: DocumentTemplate | None):
    agent_repo = MagicMock()
    agent_repo.find_by_id = AsyncMock(side_effect=lambda aid, rid: agents.get(aid))
    template_repo = MagicMock()
    template_repo.find_by_id = AsyncMock(return_value=template)
    use_case = GetAgentDocumentTemplateUseCase(
        agent_repository=agent_repo,
        template_repository=template_repo,
        logger=MagicMock(),
    )
    return use_case, agent_repo, template_repo


class TestGetAgentDocumentTemplateUseCase:
    @pytest.mark.asyncio
    async def test_owner_gets_own_template_with_samples(self):
        use_case, _, template_repo = _use_case({"agent-1": _agent()}, _template())

        result = await use_case.execute("agent-1", "req-1", viewer_user_id="owner-1")

        template_repo.find_by_id.assert_awaited_once_with("tpl-1", "req-1")
        assert result.template_id == "tpl-1"
        assert result.name == "여신 승인 신청서"
        assert result.source_format == "docx"
        assert "{{borrower_name}}" in result.html_skeleton
        assert [s.key for s in result.slots] == ["borrower_name", "opinion"]
        assert result.slots[0].sample_value == "홍길동"
        assert result.slots[0].label == "차주명"
        assert result.slots[0].slot_type == "value"
        assert result.slots[0].description == "차주 이름"
        assert result.samples_hidden is False
        assert result.is_inherited is False

    @pytest.mark.asyncio
    async def test_fork_owner_gets_inherited_template_without_samples(self):
        forked = _agent(agent_id="fork-1", user_id="forker-1")
        origin = _agent(agent_id="agent-1", user_id="owner-1")
        use_case, _, _ = _use_case(
            {"fork-1": forked, "agent-1": origin}, _template(agent_id="agent-1")
        )

        result = await use_case.execute("fork-1", "req-1", viewer_user_id="forker-1")

        assert result.is_inherited is True
        assert result.samples_hidden is True
        assert all(s.sample_value == "" for s in result.slots)
        # 라벨·뼈대는 그대로 보인다
        assert result.slots[0].label == "차주명"
        assert "{{borrower_name}}" in result.html_skeleton

    @pytest.mark.asyncio
    async def test_fork_with_deleted_origin_hides_samples(self):
        forked = _agent(agent_id="fork-1", user_id="forker-1")
        use_case, _, _ = _use_case({"fork-1": forked}, _template(agent_id="agent-1"))

        result = await use_case.execute("fork-1", "req-1", viewer_user_id="forker-1")

        assert result.samples_hidden is True
        assert all(s.sample_value == "" for s in result.slots)

    @pytest.mark.asyncio
    async def test_non_owner_is_rejected(self):
        use_case, _, template_repo = _use_case({"agent-1": _agent()}, _template())

        with pytest.raises(PermissionError):
            await use_case.execute("agent-1", "req-1", viewer_user_id="someone-else")
        template_repo.find_by_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_admin_who_is_not_owner_is_rejected(self):
        use_case, _, _ = _use_case({"agent-1": _agent()}, _template())

        with pytest.raises(PermissionError):
            await use_case.execute(
                "agent-1", "req-1", viewer_user_id="admin-9", viewer_role="admin"
            )

    @pytest.mark.asyncio
    async def test_missing_agent_raises_agent_not_found(self):
        use_case, _, _ = _use_case({}, _template())

        with pytest.raises(AgentNotFoundError):
            await use_case.execute("agent-x", "req-1", viewer_user_id="owner-1")

    @pytest.mark.asyncio
    async def test_agent_without_extractor_worker_raises_template_not_found(self):
        use_case, _, _ = _use_case(
            {"agent-1": _agent(with_extractor=False)}, _template()
        )

        with pytest.raises(AgentDocumentTemplateNotFoundError):
            await use_case.execute("agent-1", "req-1", viewer_user_id="owner-1")

    @pytest.mark.asyncio
    async def test_extractor_without_template_id_raises_template_not_found(self):
        use_case, _, template_repo = _use_case(
            {"agent-1": _agent(template_id=None)}, _template()
        )

        with pytest.raises(AgentDocumentTemplateNotFoundError):
            await use_case.execute("agent-1", "req-1", viewer_user_id="owner-1")
        template_repo.find_by_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_template_row_raises_template_not_found(self):
        use_case, _, _ = _use_case({"agent-1": _agent()}, None)

        with pytest.raises(AgentDocumentTemplateNotFoundError):
            await use_case.execute("agent-1", "req-1", viewer_user_id="owner-1")

    @pytest.mark.asyncio
    async def test_deleted_template_raises_template_not_found(self):
        use_case, _, _ = _use_case({"agent-1": _agent()}, _template(status="deleted"))

        with pytest.raises(AgentDocumentTemplateNotFoundError):
            await use_case.execute("agent-1", "req-1", viewer_user_id="owner-1")

    @pytest.mark.asyncio
    async def test_response_excludes_internal_fields(self):
        use_case, _, _ = _use_case({"agent-1": _agent()}, _template())

        result = await use_case.execute("agent-1", "req-1", viewer_user_id="owner-1")
        dumped = result.model_dump()

        assert "source_file_ref" not in dumped
        assert all("fill_hint" not in s for s in dumped["slots"])
        assert "/data/templates/secret.docx" not in result.model_dump_json()
