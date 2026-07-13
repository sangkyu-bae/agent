"""AnalysisSnapshotPolicy 단위 테스트 (analysis-data-continuity Design §3.1, T1/T2)."""
from datetime import datetime

import pytest

from src.domain.conversation.analysis_snapshot_policy import (
    REINJECTED_MARKER,
    AnalysisSnapshotPolicy,
)
from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.value_objects import (
    AgentId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)


def _msg(turn: int, role: MessageRole, analysis_data: dict | None = None):
    return ConversationMessage(
        id=None,
        user_id=UserId("u1"),
        session_id=SessionId("s1"),
        agent_id=AgentId.super(),
        role=role,
        content=f"msg-{turn}",
        turn_index=TurnIndex(turn),
        created_at=datetime(2026, 7, 6),
        analysis_data=analysis_data,
    )


def _snapshot(question: str = "q", contents: list[str] | None = None) -> dict:
    return {
        "version": 1,
        "question": question,
        "items": [
            {"origin": "w1", "kind": "search", "content": c, "truncated": False}
            for c in (contents or ["data"])
        ],
    }


class TestBuildSnapshot:
    def test_유효_항목으로_스냅샷_생성(self):
        policy = AnalysisSnapshotPolicy()
        snap = policy.build_snapshot(
            "나의 휴가데이터",
            [{"origin": "w1", "kind": "search", "content": "휴가 15일"}],
        )
        assert snap == {
            "version": 1,
            "question": "나의 휴가데이터",
            "items": [
                {
                    "origin": "w1",
                    "kind": "search",
                    "content": "휴가 15일",
                    "truncated": False,
                }
            ],
        }

    def test_항목_content가_상한_초과하면_절단하고_truncated_표기(self):
        policy = AnalysisSnapshotPolicy(item_max_chars=10)
        snap = policy.build_snapshot(
            "q", [{"origin": "w1", "kind": "search", "content": "a" * 20}]
        )
        assert snap["items"][0]["content"] == "a" * 10
        assert snap["items"][0]["truncated"] is True

    def test_빈_content_항목은_제거(self):
        policy = AnalysisSnapshotPolicy()
        snap = policy.build_snapshot(
            "q",
            [
                {"origin": "w1", "kind": "search", "content": "  "},
                {"origin": "w2", "kind": "search", "content": "ok"},
            ],
        )
        assert len(snap["items"]) == 1
        assert snap["items"][0]["origin"] == "w2"

    def test_유효_항목이_없으면_None(self):
        policy = AnalysisSnapshotPolicy()
        assert policy.build_snapshot("q", []) is None
        assert (
            policy.build_snapshot(
                "q", [{"origin": "w1", "kind": "search", "content": ""}]
            )
            is None
        )

    def test_총량_상한_도달_시_이후_항목_드롭(self):
        policy = AnalysisSnapshotPolicy(item_max_chars=100, total_max_chars=150)
        snap = policy.build_snapshot(
            "q",
            [
                {"origin": "w1", "kind": "search", "content": "a" * 100},
                {"origin": "w2", "kind": "search", "content": "b" * 100},
            ],
        )
        assert len(snap["items"]) == 1
        assert snap["items"][0]["origin"] == "w1"

    def test_question은_200자로_절단(self):
        policy = AnalysisSnapshotPolicy()
        snap = policy.build_snapshot(
            "q" * 300, [{"origin": "w1", "kind": "search", "content": "d"}]
        )
        assert len(snap["question"]) == 200


class TestReinjection:
    def test_render_reinjection_body는_마커와_질문과_원문_포함(self):
        policy = AnalysisSnapshotPolicy()
        snap = _snapshot(question="나의 휴가데이터", contents=["휴가 15일"])
        body = policy.render_reinjection_body(snap, snap["items"][0])
        assert REINJECTED_MARKER in body
        assert "나의 휴가데이터" in body
        assert "휴가 15일" in body

    def test_is_reinjected_판정(self):
        policy = AnalysisSnapshotPolicy()
        assert policy.is_reinjected(f"[w1 검색결과]\n{REINJECTED_MARKER} x") is True
        assert policy.is_reinjected("[w1 검색결과]\n신규 데이터") is False


class TestSelectRecent:
    def test_최신_retention개를_오름차순으로_반환(self):
        policy = AnalysisSnapshotPolicy(retention=2)
        messages = [
            _msg(2, MessageRole.ASSISTANT, _snapshot("q1")),
            _msg(4, MessageRole.ASSISTANT, _snapshot("q2")),
            _msg(6, MessageRole.ASSISTANT, _snapshot("q3")),
            _msg(7, MessageRole.USER),
        ]
        selected = policy.select_recent(messages)
        assert [s["question"] for s in selected] == ["q2", "q3"]

    def test_스냅샷_없는_세션은_빈_리스트(self):
        policy = AnalysisSnapshotPolicy()
        messages = [_msg(1, MessageRole.USER), _msg(2, MessageRole.ASSISTANT)]
        assert policy.select_recent(messages) == []

    def test_누적_총량_초과하는_오래된_스냅샷은_드롭(self):
        policy = AnalysisSnapshotPolicy(retention=2, total_max_chars=100)
        messages = [
            _msg(2, MessageRole.ASSISTANT, _snapshot("old", ["a" * 60])),
            _msg(4, MessageRole.ASSISTANT, _snapshot("new", ["b" * 60])),
        ]
        selected = policy.select_recent(messages)
        assert [s["question"] for s in selected] == ["new"]


class TestRenderContextBlock:
    def test_스냅샷_없으면_빈_문자열(self):
        assert AnalysisSnapshotPolicy().render_context_block([]) == ""

    def test_헤더_질문_원문_포함(self):
        policy = AnalysisSnapshotPolicy()
        block = policy.render_context_block(
            [_snapshot("나의 휴가데이터", ["휴가 15일"])]
        )
        assert block.startswith("[이전 분석 데이터]")
        assert "나의 휴가데이터" in block
        assert "휴가 15일" in block


class TestEntityAnalysisData:
    def test_analysis_data_None_허용(self):
        assert _msg(1, MessageRole.ASSISTANT, None).analysis_data is None

    def test_analysis_data_유효_dict_허용(self):
        snap = _snapshot()
        assert _msg(1, MessageRole.ASSISTANT, snap).analysis_data == snap

    def test_items_비어있으면_거부(self):
        with pytest.raises(ValueError):
            _msg(1, MessageRole.ASSISTANT, {"version": 1, "items": []})
