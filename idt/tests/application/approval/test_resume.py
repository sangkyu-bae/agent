"""RunAgentUseCase.resume_from_snapshot 단위 테스트.

Design Ref: §2.1 (재개), §7.3(v0.2). 컴파일러·에이전트 리포지토리를 대역으로
두고 "스냅샷 복원 → 결과 주입 → supervisor 재진입" 계약만 검증한다.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.domain.approval.entity import ApprovalRequest, ResumeSnapshot
from src.infrastructure.approval.snapshot import SnapshotSerializer

_NOW = datetime(2026, 9, 21, 9, 0, 0)


def _state_json(**over) -> str:
    base = {
        "messages": [
            HumanMessage(content="금리를 내려줘"),
            AIMessage(content="승인 대기 등록됨", name="w1"),
        ],
        "iteration_count": 2,
        "max_iterations": 25,
        "next_worker": "__end__",
        "approval_pending": {"tool_id": "rate_update"},
        "last_worker_id": "w1",
    }
    base.update(over)
    return SnapshotSerializer.dumps(base)


def _approval(*, schema_version=1, state_json=None, agent_updated=_NOW,
              session_id="sess-1", requested_by="u1"):
    return ApprovalRequest(
        id="ap1", run_id="r1", agent_id="ag1", requested_by=requested_by,
        worker_id="w1", tool_id="rate_update", tool_args={"rate": 3.25},
        draft="기준금리 3.25%", status="executed", idempotency_key="r1:w1:tc1",
        snapshot=ResumeSnapshot(
            schema_version=schema_version, agent_updated_at=agent_updated,
            worker_id="w1", state_json=state_json or _state_json(),
        ),
        expires_at=_NOW + timedelta(hours=24),
        request_id="req1", created_at=_NOW, updated_at=_NOW,
        session_id=session_id,
    )


def _uc(*, agent_found=True, agent_updated=_NOW, final_answer="완료했습니다"):
    uc = RunAgentUseCase.__new__(RunAgentUseCase)
    uc._logger = MagicMock()

    agent = MagicMock(id="ag1", updated_at=agent_updated, max_iterations=25)
    agent.to_workflow_definition.return_value = MagicMock(workers=[])
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=agent if agent_found else None)
    uc._repository = repo

    captured = {}

    async def _fake_compile_and_run(state, agent_, request_id):
        captured["state"] = state
        return final_answer

    uc._resume_graph = _fake_compile_and_run
    # G1 교훈: _save_assistant_message 를 모킹하면 그 안의 SessionId("")
    # 예외가 가려진다. 실제 메서드를 돌리고 저장소만 스텁한다.
    saved = []
    msg_repo = MagicMock()
    msg_repo.find_by_session = AsyncMock(return_value=[])

    async def _save(msg):
        saved.append(msg)

    msg_repo.save = _save
    uc._message_repo = msg_repo
    captured["saved"] = saved
    return uc, captured


class TestGuards:
    @pytest.mark.asyncio
    async def test_에이전트가_없으면_빈_문자열(self):
        uc, _ = _uc(agent_found=False)
        answer = await uc.resume_from_snapshot(
            _approval(), outcome="집행 완료", request_id="req1"
        )
        assert answer == ""

    @pytest.mark.asyncio
    async def test_스키마_버전이_다르면_재개하지_않는다(self):
        """포맷이 바뀐 낡은 스냅샷으로 돌리면 이상 동작한다."""
        uc, captured = _uc()
        answer = await uc.resume_from_snapshot(
            _approval(schema_version=99), outcome="집행 완료", request_id="req1"
        )
        assert answer == ""
        assert "state" not in captured
        assert uc._logger.warning.called

    @pytest.mark.asyncio
    async def test_에이전트_정의가_바뀌었으면_재개하지_않는다(self):
        """FR-14 — 승인 시점뿐 아니라 집행 시점에도 재검증한다."""
        uc, captured = _uc(agent_updated=_NOW + timedelta(days=1))
        answer = await uc.resume_from_snapshot(
            _approval(), outcome="집행 완료", request_id="req1"
        )
        assert answer == ""
        assert "state" not in captured

    @pytest.mark.asyncio
    async def test_깨진_스냅샷은_예외를_올리지_않는다(self):
        """집행은 이미 끝났다 — 재개 실패가 집행을 무효로 만들면 안 된다."""
        uc, _ = _uc()
        answer = await uc.resume_from_snapshot(
            _approval(state_json="{깨진 json"), outcome="완료", request_id="req1"
        )
        assert answer == ""
        assert uc._logger.error.called


class TestRestore:
    @pytest.mark.asyncio
    async def test_스냅샷_스칼라가_복원된다(self):
        uc, captured = _uc()
        await uc.resume_from_snapshot(
            _approval(), outcome="집행 완료", request_id="req1"
        )
        assert captured["state"]["iteration_count"] == 2

    @pytest.mark.asyncio
    async def test_결과가_워커_AIMessage로_주입된다(self):
        uc, captured = _uc()
        await uc.resume_from_snapshot(
            _approval(), outcome="기준금리를 3.25%로 변경 완료", request_id="req1"
        )
        last = captured["state"]["messages"][-1]
        assert isinstance(last, AIMessage)
        assert last.name == "w1"
        assert "3.25%" in last.content

    @pytest.mark.asyncio
    async def test_기존_대화가_보존된다(self):
        uc, captured = _uc()
        await uc.resume_from_snapshot(
            _approval(), outcome="완료", request_id="req1"
        )
        contents = [m.content for m in captured["state"]["messages"]]
        assert "금리를 내려줘" in contents

    @pytest.mark.asyncio
    async def test_approval_pending이_비워진다(self):
        """남겨 두면 재진입 즉시 라우팅이 다시 __end__ 로 빠져 무한 대기."""
        uc, captured = _uc()
        await uc.resume_from_snapshot(
            _approval(), outcome="완료", request_id="req1"
        )
        assert not captured["state"]["approval_pending"]

    @pytest.mark.asyncio
    async def test_종료_라우팅_신호가_초기화된다(self):
        """next_worker 가 __end__ 인 채로 재진입하면 supervisor 가 다시 끝낸다."""
        uc, captured = _uc()
        await uc.resume_from_snapshot(
            _approval(), outcome="완료", request_id="req1"
        )
        assert captured["state"]["next_worker"] == ""


class TestOutcome:
    @pytest.mark.asyncio
    async def test_최종_답변을_돌려준다(self):
        uc, _ = _uc(final_answer="금리 변경을 마쳤습니다")
        answer = await uc.resume_from_snapshot(
            _approval(), outcome="완료", request_id="req1"
        )
        assert answer == "금리 변경을 마쳤습니다"

    @pytest.mark.asyncio
    async def test_거절_사유도_같은_경로로_주입된다(self):
        """승인·거절이 같은 메커니즘 — supervisor 관점엔 둘 다 워커 산출물."""
        uc, captured = _uc()
        await uc.resume_from_snapshot(
            _approval(), outcome="이 작업은 거절됨(사유: 한도 초과)",
            request_id="req1",
        )
        assert "거절" in captured["state"]["messages"][-1].content

    @pytest.mark.asyncio
    async def test_재개_답변이_원래_세션에_저장된다(self):
        """G1 — 실제 _save_assistant_message 를 태워 SessionId 생성까지 검증."""
        uc, captured = _uc(final_answer="금리 변경을 마쳤습니다")
        await uc.resume_from_snapshot(
            _approval(session_id="sess-1"), outcome="완료", request_id="req1"
        )
        assert len(captured["saved"]) == 1
        msg = captured["saved"][0]
        assert msg.session_id.value == "sess-1"
        assert msg.content == "금리 변경을 마쳤습니다"

    @pytest.mark.asyncio
    async def test_세션이_없으면_저장을_건너뛰고_답변은_돌려준다(self):
        """구버전 행(session_id NULL) — 예외로 답변을 잃지 않는다."""
        uc, captured = _uc(final_answer="완료했습니다")
        answer = await uc.resume_from_snapshot(
            _approval(session_id=None), outcome="완료", request_id="req1"
        )
        assert answer == "완료했습니다"
        assert captured["saved"] == []
        assert uc._logger.warning.called

    @pytest.mark.asyncio
    async def test_요청자가_비어도_답변은_돌려준다(self):
        """웹훅·스케줄 런은 신원이 비어 있을 수 있다 (UserId 도 빈 값 거부)."""
        uc, captured = _uc(final_answer="완료")
        answer = await uc.resume_from_snapshot(
            _approval(requested_by=""), outcome="완료", request_id="req1"
        )
        assert answer == "완료"
        assert captured["saved"] == []
