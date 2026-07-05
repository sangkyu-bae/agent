"""Application 테스트: SyncAgentSkillsUseCase (desired-set reconcile)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_skill.sync_agent_skills_use_case import (
    SyncAgentSkillsUseCase,
)
from src.domain.agent_skill.schemas import AgentSkillLink
from src.domain.skill_builder.schemas import (
    SkillDefinition,
    SkillScriptType,
    SkillVisibility,
)


def _skill(sid, owner="1", status="active", visibility=SkillVisibility.PRIVATE,
           dept=None):
    return SkillDefinition(
        id=sid, user_id=owner, name=sid, description="d",
        instruction="지시문", trigger=None, script_type=SkillScriptType.NONE,
        script_content=None, status=status, visibility=visibility,
        department_id=dept, forked_from=None, forked_at=None,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


def _deps(current_ids=None, skills_by_id=None):
    links = MagicMock()
    links.list_links = AsyncMock(return_value=[
        AgentSkillLink(agent_id="agent-1", skill_id=s, sort_order=i)
        for i, s in enumerate(current_ids or [])
    ])
    links.attach = AsyncMock(side_effect=lambda link, rid: link)
    links.detach = AsyncMock()
    skills = MagicMock()
    table = skills_by_id if skills_by_id is not None else {}
    skills.find_by_id = AsyncMock(side_effect=lambda sid, rid: table.get(sid))
    dept = MagicMock()
    dept.find_departments_by_user = AsyncMock(return_value=[])
    return links, skills, dept


def _uc(links, skills, dept):
    return SyncAgentSkillsUseCase(links, skills, dept, MagicMock())


class TestSync:
    @pytest.mark.asyncio
    async def test_attach_new_from_empty(self):
        links, skills, dept = _deps([], {"a": _skill("a"), "b": _skill("b")})
        res = await _uc(links, skills, dept).sync(
            "agent-1", ["a", "b"], "req",
            viewer_user_id="1", viewer_role="user",
        )
        assert res == ["a", "b"]
        assert links.attach.await_count == 2
        links.detach.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_noop_when_same_order(self):
        links, skills, dept = _deps(["a", "b"], {"a": _skill("a"), "b": _skill("b")})
        res = await _uc(links, skills, dept).sync(
            "agent-1", ["a", "b"], "req",
            viewer_user_id="1", viewer_role="user",
        )
        assert res == ["a", "b"]
        links.attach.assert_not_awaited()
        links.detach.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_partial_diff_replaces_all(self):
        # current [a,b] → desired [a,c]: 전체 교체(detach 2, attach 2)
        links, skills, dept = _deps(
            ["a", "b"], {"a": _skill("a"), "c": _skill("c")}
        )
        res = await _uc(links, skills, dept).sync(
            "agent-1", ["a", "c"], "req",
            viewer_user_id="1", viewer_role="user",
        )
        assert res == ["a", "c"]
        assert links.detach.await_count == 2
        assert links.attach.await_count == 2

    @pytest.mark.asyncio
    async def test_reorder_reassigns_sort_order(self):
        links, skills, dept = _deps(["a", "b"], {"a": _skill("a"), "b": _skill("b")})
        res = await _uc(links, skills, dept).sync(
            "agent-1", ["b", "a"], "req",
            viewer_user_id="1", viewer_role="user",
        )
        assert res == ["b", "a"]
        # attach 순서대로 sort_order 0,1 재부여
        attached = [c.args[0] for c in links.attach.await_args_list]
        assert (attached[0].skill_id, attached[0].sort_order) == ("b", 0)
        assert (attached[1].skill_id, attached[1].sort_order) == ("a", 1)

    @pytest.mark.asyncio
    async def test_empty_desired_detaches_all(self):
        links, skills, dept = _deps(["a", "b"], {})
        res = await _uc(links, skills, dept).sync(
            "agent-1", [], "req",
            viewer_user_id="1", viewer_role="user",
        )
        assert res == []
        assert links.detach.await_count == 2
        links.attach.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dedupe_keeps_order(self):
        links, skills, dept = _deps([], {"a": _skill("a"), "b": _skill("b")})
        res = await _uc(links, skills, dept).sync(
            "agent-1", ["a", "b", "a"], "req",
            viewer_user_id="1", viewer_role="user",
        )
        assert res == ["a", "b"]

    @pytest.mark.asyncio
    async def test_over_max_raises_before_change(self):
        links, skills, dept = _deps(["a"], {})
        with pytest.raises(ValueError, match="최대"):
            await _uc(links, skills, dept).sync(
                "agent-1", ["a", "b", "c", "d"], "req",
                viewer_user_id="1", viewer_role="user",
            )
        links.detach.assert_not_awaited()
        links.attach.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_skill_raises_before_change(self):
        links, skills, dept = _deps(["a"], {"a": _skill("a")})  # 'x' 없음
        with pytest.raises(ValueError, match="찾을 수 없"):
            await _uc(links, skills, dept).sync(
                "agent-1", ["a", "x"], "req",
                viewer_user_id="1", viewer_role="user",
            )
        links.detach.assert_not_awaited()
        links.attach.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inaccessible_skill_raises(self):
        # 타인 소유 private → 접근 불가
        links, skills, dept = _deps(
            [], {"a": _skill("a", owner="2", visibility=SkillVisibility.PRIVATE)}
        )
        with pytest.raises(PermissionError, match="접근"):
            await _uc(links, skills, dept).sync(
                "agent-1", ["a"], "req",
                viewer_user_id="1", viewer_role="user",
            )
        links.attach.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_public_skill_of_other_is_accessible(self):
        links, skills, dept = _deps(
            [], {"a": _skill("a", owner="2", visibility=SkillVisibility.PUBLIC)}
        )
        res = await _uc(links, skills, dept).sync(
            "agent-1", ["a"], "req",
            viewer_user_id="1", viewer_role="user",
        )
        assert res == ["a"]
        links.attach.assert_awaited_once()
