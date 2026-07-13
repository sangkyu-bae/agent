"""AnalysisSnapshotPolicy 원천 데이터 확장 테스트 (analysis-source-preservation T1)."""
from datetime import datetime

from src.domain.conversation.analysis_snapshot_policy import AnalysisSnapshotPolicy
from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.value_objects import (
    AgentId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)


def _excel(rows: int = 3) -> dict:
    return {
        "file_id": "f1",
        "filename": "vac.xlsx",
        "sheets": {
            "Sheet1": {
                "sheet_name": "Sheet1",
                "columns": ["월", "사용일수", "잔여"],
                "data": [
                    {"월": f"{i}월", "사용일수": i * 0.5, "잔여": 15 - i}
                    for i in range(1, rows + 1)
                ],
                "dtypes": {"월": "object", "사용일수": "float64", "잔여": "float64"},
                "row_count": rows,
                "column_count": 3,
            }
        },
        "metadata": {},
    }


class TestRenderRawSource:
    def test_헤더와_행을_압축_표_텍스트로_직렬화(self):
        policy = AnalysisSnapshotPolicy()
        body = policy.render_raw_source(_excel(3))
        assert body is not None
        assert "vac.xlsx" in body
        assert "월,사용일수,잔여" in body  # 헤더
        assert "1월" in body and "3월" in body  # 행 값
        assert "Sheet1" in body

    def test_행_초과시_샘플링하고_총행수_표기(self):
        policy = AnalysisSnapshotPolicy(raw_source_max_rows=2)
        body = policy.render_raw_source(_excel(10))
        assert "1월" in body  # 앞 행 샘플
        assert "총 10행" in body  # 총행수 표기
        # 샘플 상한(2행)만 노출 — 마지막 행(10월)은 미포함
        assert "10월" not in body

    def test_문자_상한_초과시_절단(self):
        policy = AnalysisSnapshotPolicy(raw_source_max_chars=50)
        body = policy.render_raw_source(_excel(100))
        assert len(body) <= 50

    def test_빈_또는_무효_dict는_None(self):
        policy = AnalysisSnapshotPolicy()
        assert policy.render_raw_source({}) is None
        assert policy.render_raw_source({"sheets": {}}) is None


class TestRawSourceBudget:
    def test_raw_source는_비raw와_독립_budget(self):
        """raw_source가 커도 비-raw 항목 budget(total_max_chars)을 잠식하지 않음."""
        policy = AnalysisSnapshotPolicy(
            item_max_chars=100, total_max_chars=200,
            raw_source_max_chars=5000, raw_source_total_max_chars=8000,
        )
        snap = policy.build_snapshot(
            "q",
            [
                {"origin": "w1", "kind": "search", "content": "a" * 100},
                {"origin": "w2", "kind": "raw_source", "content": "b" * 3000},
                {"origin": "w3", "kind": "analysis_output", "content": "c" * 100},
            ],
        )
        kinds = [it["kind"] for it in snap["items"]]
        # 비-raw 2건(각 100자, total 200 이내) + raw 1건(별도 budget) 모두 생존
        assert kinds.count("search") == 1
        assert kinds.count("analysis_output") == 1
        assert kinds.count("raw_source") == 1
        raw = next(it for it in snap["items"] if it["kind"] == "raw_source")
        assert len(raw["content"]) == 3000  # raw budget(5000) 이내라 무절단

    def test_raw_source_전용_상한_절단(self):
        policy = AnalysisSnapshotPolicy(raw_source_max_chars=500)
        snap = policy.build_snapshot(
            "q", [{"origin": "w", "kind": "raw_source", "content": "x" * 2000}]
        )
        raw = snap["items"][0]
        assert len(raw["content"]) == 500
        assert raw["truncated"] is True

    def test_raw_source_total_budget_초과시_드롭(self):
        policy = AnalysisSnapshotPolicy(
            raw_source_max_chars=1000, raw_source_total_max_chars=1500,
        )
        snap = policy.build_snapshot(
            "q",
            [
                {"origin": "a", "kind": "raw_source", "content": "x" * 1000},
                {"origin": "b", "kind": "raw_source", "content": "y" * 1000},
            ],
        )
        raws = [it for it in snap["items"] if it["kind"] == "raw_source"]
        assert len(raws) == 1  # 1000 + 1000 > 1500 → 두 번째 드롭

    def test_비raw_동작_불변_회귀(self):
        """raw budget 추가가 기존 non-raw 동작에 영향 없음."""
        policy = AnalysisSnapshotPolicy(item_max_chars=10, total_max_chars=15)
        snap = policy.build_snapshot(
            "q",
            [
                {"origin": "a", "kind": "search", "content": "z" * 10},
                {"origin": "b", "kind": "search", "content": "w" * 10},
            ],
        )
        # 10 + 10 > 15 → 두 번째 드롭 (기존 total_max_chars 동작)
        assert len([it for it in snap["items"] if it["kind"] == "search"]) == 1


def _msg_with(turn: int, snapshot: dict) -> ConversationMessage:
    return ConversationMessage(
        id=None, user_id=UserId("u1"), session_id=SessionId("s1"),
        agent_id=AgentId.super(), role=MessageRole.ASSISTANT, content=f"a{turn}",
        turn_index=TurnIndex(turn), created_at=datetime(2026, 7, 7),
        analysis_data=snapshot,
    )


def _snap(non_raw: int, raw: int) -> dict:
    items = []
    if non_raw:
        items.append({"origin": "w", "kind": "search",
                      "content": "n" * non_raw, "truncated": False})
    if raw:
        items.append({"origin": "w", "kind": "raw_source",
                      "content": "r" * raw, "truncated": False})
    return {"version": 1, "question": "q", "items": items}


class TestSelectRecentKindBudget:
    """select_recent이 raw/non-raw budget을 분리 적용 (Design §3.3, G1)."""

    def test_raw는_non_raw_선별_budget을_잠식하지_않는다(self):
        policy = AnalysisSnapshotPolicy(
            retention=2, total_max_chars=8000,
            raw_source_total_max_chars=20000,
        )
        # 각 스냅샷: non-raw 3000 + raw 6000. 단일 budget이면 두 번째가 total 초과로 드롭.
        messages = [
            _msg_with(2, _snap(non_raw=3000, raw=6000)),
            _msg_with(4, _snap(non_raw=3000, raw=6000)),
        ]
        selected = policy.select_recent(messages)
        # non-raw 3000+3000=6000 ≤ 8000, raw 6000+6000=12000 ≤ 20000 → 둘 다 생존
        assert len(selected) == 2

    def test_raw_전용_budget_초과시_컷(self):
        policy = AnalysisSnapshotPolicy(
            retention=3, total_max_chars=99999,
            raw_source_total_max_chars=10000,
        )
        messages = [
            _msg_with(2, _snap(non_raw=100, raw=6000)),
            _msg_with(4, _snap(non_raw=100, raw=6000)),
        ]
        selected = policy.select_recent(messages)
        # raw 6000+6000=12000 > 10000 → 두 번째(오래된) 드롭
        assert len(selected) == 1
