"""수정 후 승인 — DecideApprovalUseCase / ExecuteDueApprovalsUseCase / 미들웨어.

Design Ref: approval-edit-before-approve §2.2, §6.1, §8.2 (B12~B19, B22).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.approval.decide_use_case import ApprovalDetailView
from src.application.approval.errors import (
    ApprovalConflictError,
    ApprovalEditInvalidError,
    ApprovalNotEditableError,
)
from src.application.approval.gate_middleware import ApprovalGateMiddleware
from src.domain.approval.policies import ApprovalSignalPolicy
from tests.application.approval.test_decide_use_case import _NOW, _request, _uc
from tests.application.approval.test_execute_scheduler import _due
from tests.application.approval.test_execute_scheduler import _uc as _tick_uc

_ARGS = {"to": "a@b.c", "subject": "제목", "body": "원본 본문", "priority": 1}


def _editable(**over):
    return _request(tool_args=dict(_ARGS), draft="원본 본문", **over)


def _with_resumer(uc) -> MagicMock:
    resumer = MagicMock()
    resumer.resume_from_snapshot = AsyncMock(return_value="답변")
    uc._resumer = resumer
    return resumer


class TestApproveWithEdit:
    @pytest.mark.asyncio
    async def test_즉시_집행은_수정본으로_호출된다(self):
        """B12 / SC-1"""
        uc, _, executor = _uc(approval=_editable())
        await uc.approve(
            "ap1", user_id="u1", request_id="r",
            edited_args={"body": "수정 본문", "to": "z@b.c"},
        )
        sent = executor.execute.await_args.kwargs["tool_args"]
        assert sent == {**_ARGS, "body": "수정 본문", "to": "z@b.c"}

    @pytest.mark.asyncio
    async def test_승인_전이에_수정본과_원본이_함께_실린다(self):
        """B12 / SC-3 — 단일 CAS."""
        uc, repo, _ = _uc(approval=_editable())
        await uc.approve(
            "ap1", user_id="u1", request_id="r", edited_args={"body": "수정"}
        )
        first = repo.compare_and_set_status.await_args_list[0].kwargs
        assert first["expected"] == "pending"
        assert first["new_status"] == "approved"
        assert first["tool_args"]["body"] == "수정"
        assert first["draft"] == "수정"
        assert first["original_tool_args"] == _ARGS
        assert first["edited_by"] == "u1"
        assert first["edited_at"] == _NOW

    @pytest.mark.asyncio
    async def test_재개_outcome에_수정_사실이_실린다(self):
        """B12 / SC-4"""
        uc, _, _ = _uc(approval=_editable())
        resumer = _with_resumer(uc)
        await uc.approve(
            "ap1", user_id="u1", request_id="r", edited_args={"body": "수정"}
        )
        outcome = resumer.resume_from_snapshot.await_args.kwargs["outcome"]
        assert outcome.startswith("[담당자가 초안을 수정해 집행했습니다")
        assert "수정" in outcome and outcome.endswith("[mock] 집행 완료")

    @pytest.mark.asyncio
    async def test_예약건도_수정본이_확정된다(self):
        """B13 / SC-2 전반부 — 스케줄러는 DB 의 tool_args 를 다시 읽는다."""
        uc, repo, executor = _uc(
            approval=_editable(), gate_config={"execute_after": "0 9 * * *"}
        )
        result = await uc.approve(
            "ap1", user_id="u1", request_id="r", edited_args={"body": "수정"}
        )
        assert result.status == "scheduled"
        executor.execute.assert_not_awaited()
        assert repo.compare_and_set_status.await_args_list[0].kwargs["draft"] == "수정"

    @pytest.mark.asyncio
    async def test_반환값에_수정이_반영된다(self):
        uc, _, _ = _uc(approval=_editable())
        result = await uc.approve(
            "ap1", user_id="u1", request_id="r", edited_args={"body": "수정"}
        )
        assert result.is_edited
        assert result.draft == "수정"
        assert result.original_tool_args == _ARGS

    @pytest.mark.asyncio
    async def test_수정_로그에는_값이_없고_키만_있다(self):
        """B22 — 본문·수신자는 PII 일 수 있다."""
        uc, _, _ = _uc(approval=_editable())
        logger = MagicMock()
        uc._logger = logger
        await uc.approve(
            "ap1", user_id="u1", request_id="r",
            edited_args={"body": "비밀본문", "to": "secret@x.com"},
        )
        edited_calls = [
            c for c in logger.info.call_args_list if c.args[0] == "approval edited"
        ]
        assert len(edited_calls) == 1
        assert edited_calls[0].kwargs["changed_keys"] == ["body", "to"]
        dumped = repr(logger.info.call_args_list)
        assert "비밀본문" not in dumped and "secret@x.com" not in dumped


class TestApproveEditRejected:
    @pytest.mark.asyncio
    async def test_본문_키가_없으면_NotEditable_이고_전이하지_않는다(self):
        """B15 / SC-5"""
        uc, repo, executor = _uc(
            approval=_request(tool_args={"rate": 3.25}, draft='{"rate": 3.25}')
        )
        with pytest.raises(ApprovalNotEditableError):
            await uc.approve(
                "ap1", user_id="u1", request_id="r", edited_args={"rate": "4"}
            )
        repo.compare_and_set_status.assert_not_awaited()
        executor.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_불허_키는_EditInvalid(self):
        uc, repo, _ = _uc(approval=_editable())
        with pytest.raises(ApprovalEditInvalidError):
            await uc.approve(
                "ap1", user_id="u1", request_id="r", edited_args={"bcc": "x"}
            )
        repo.compare_and_set_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_길이_상한은_주입값을_따른다(self):
        uc, _, _ = _uc(approval=_editable())
        uc._edit_max_field_chars = 5
        with pytest.raises(ApprovalEditInvalidError):
            await uc.approve(
                "ap1", user_id="u1", request_id="r", edited_args={"body": "123456"}
            )

    @pytest.mark.asyncio
    async def test_동시_결정으로_CAS가_실패하면_집행하지_않는다(self):
        """B17"""
        uc, _, executor = _uc(approval=_editable(), cas=False)
        with pytest.raises(ApprovalConflictError):
            await uc.approve(
                "ap1", user_id="u1", request_id="r", edited_args={"body": "수정"}
            )
        executor.execute.assert_not_awaited()


class TestApproveWithoutEdit:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("edited_args", [None, {}, {"body": "원본 본문"}])
    async def test_변경이_없으면_편집_필드를_보내지_않는다(self, edited_args):
        """B16 / SC-3 — 기존 호출과 동일."""
        uc, repo, _ = _uc(approval=_editable())
        resumer = _with_resumer(uc)
        await uc.approve(
            "ap1", user_id="u1", request_id="r", edited_args=edited_args
        )
        first = repo.compare_and_set_status.await_args_list[0].kwargs
        for key in ("tool_args", "draft", "original_tool_args", "edited_by", "edited_at"):
            assert key not in first
        assert resumer.resume_from_snapshot.await_args.kwargs["outcome"] == "[mock] 집행 완료"


class TestDetailView:
    @pytest.mark.asyncio
    async def test_상세는_편집_가능_정보를_계산한다(self):
        """B18"""
        uc, _, _ = _uc(approval=_request(
            tool_args={"arguments": {"to": "a", "body": "본문", "n": 1}}, draft="본문",
        ))
        view = await uc.get("ap1", user_id="u1", request_id="r")
        assert isinstance(view, ApprovalDetailView)
        assert view.body_key == "body"
        assert view.editable_keys == ["to", "body"]
        assert view.display_args == {"to": "a", "body": "본문", "n": 1}

    @pytest.mark.asyncio
    async def test_편집_불가_건은_빈_목록(self):
        uc, _, _ = _uc(approval=_request(tool_args={"n": 1}, draft='{"n": 1}'))
        view = await uc.get("ap1", user_id="u1", request_id="r")
        assert view.body_key is None
        assert view.editable_keys == []


class TestScheduledEdited:
    @pytest.mark.asyncio
    async def test_예약_집행은_DB_수정본과_수정_outcome을_쓴다(self):
        """B14 / SC-2, SC-4"""
        due = _due()
        due.tool_args = {"rate": "3.50"}
        due.draft = "3.50"
        due.original_tool_args = {"rate": "3.25"}
        due.edited_by = "u1"
        due.edited_at = _NOW
        uc, _, executor = _tick_uc(due=[due])
        resumer = _with_resumer(uc)
        await uc.run("req1")
        assert executor.execute.await_args.kwargs["tool_args"] == {"rate": "3.50"}
        outcome = resumer.resume_from_snapshot.await_args.kwargs["outcome"]
        assert outcome.startswith("[담당자가 초안을 수정해 집행했습니다")

    @pytest.mark.asyncio
    async def test_무수정_예약건_outcome은_그대로(self):
        uc, _, _ = _tick_uc()
        resumer = _with_resumer(uc)
        await uc.run("req1")
        assert resumer.resume_from_snapshot.await_args.kwargs["outcome"] == "[mock] 집행 완료"


class TestMiddlewareDraft:
    def test_react_경로_MCP_래퍼_안의_본문을_초안으로_쓴다(self):
        """B19 / D-02"""

        class _Req:
            tool_call = {
                "name": "x", "id": "tc1",
                "args": {"arguments": {"to": "a", "body": "본문"}},
            }

        gate = ApprovalGateMiddleware(tool_id="mcp:m:send", worker_id="w1")
        result = gate.wrap_tool_call(_Req(), lambda _r: None)
        signal = ApprovalSignalPolicy.extract([result])
        assert signal.draft == "본문"
        assert signal.tool_args == {"arguments": {"to": "a", "body": "본문"}}
