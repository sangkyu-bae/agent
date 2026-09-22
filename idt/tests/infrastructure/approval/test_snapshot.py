"""SnapshotSerializer 단위 테스트.

Design Ref: §3.1 ResumeSnapshot, §8.3 L0 #12·#13.
SupervisorState 는 평면 TypedDict(messages + 스칼라/리스트)라 checkpointer
없이 직접 직렬화할 수 있다 — Option A(+Protocol)가 성립하는 근거.
"""
from langchain_core.messages import AIMessage, HumanMessage

from src.domain.approval.policies import ApprovalPolicy
from src.infrastructure.approval.snapshot import SnapshotSerializer


def _state(messages=None, **over) -> dict:
    base = {
        "messages": messages if messages is not None else [
            HumanMessage(content="금리를 내려줘"),
            AIMessage(content="확인했습니다", name="w1"),
        ],
        "iteration_count": 2,
        "max_iterations": 10,
        "token_usage": 120,
        "token_limit": 10000,
        "next_worker": "w1",
        "last_worker_id": "w0",
        "available_workers": ["w0", "w1"],
        "quality_gate_enabled": False,
        "retry_counts": {"w1": 1},
        "max_retries_per_worker": 2,
        "forced_worker": "",
        "skipped_workers": [],
        "worker_task": "금리 변경",
        "limit_reached": False,
        "last_worker_error": "",
        "last_worker_empty": "",
        "finish_challenge_pending": False,
        "quality_gate_result": "",
        "attachments": [],
        "viz_decision": "",
        "charts": [],
        "visualization_done": False,
        "analysis_source": [],
    }
    base.update(over)
    return base


class TestRoundTrip:
    def test_스칼라_필드가_보존된다(self):
        restored = SnapshotSerializer.loads(SnapshotSerializer.dumps(_state()))
        assert restored["iteration_count"] == 2
        assert restored["token_usage"] == 120
        assert restored["worker_task"] == "금리 변경"
        assert restored["available_workers"] == ["w0", "w1"]
        assert restored["retry_counts"] == {"w1": 1}

    def test_messages_가_복원된다(self):
        restored = SnapshotSerializer.loads(SnapshotSerializer.dumps(_state()))
        msgs = restored["messages"]
        assert [m.content for m in msgs] == ["금리를 내려줘", "확인했습니다"]

    def test_AIMessage_의_name_이_보존된다(self):
        """워커 산출물 규약(AIMessage(name) 1건)이 깨지면 재개가 틀어진다."""
        restored = SnapshotSerializer.loads(SnapshotSerializer.dumps(_state()))
        assert restored["messages"][-1].name == "w1"

    def test_한글이_보존된다(self):
        restored = SnapshotSerializer.loads(SnapshotSerializer.dumps(_state()))
        assert restored["messages"][0].content == "금리를 내려줘"

    def test_빈_messages_도_왕복한다(self):
        restored = SnapshotSerializer.loads(
            SnapshotSerializer.dumps(_state(messages=[]))
        )
        assert restored["messages"] == []

    def test_불리언_플래그가_타입까지_보존된다(self):
        restored = SnapshotSerializer.loads(
            SnapshotSerializer.dumps(_state(finish_challenge_pending=True))
        )
        assert restored["finish_challenge_pending"] is True


class TestSizeLimit:
    def test_상한_이하는_절단하지_않는다(self):
        payload, truncated = SnapshotSerializer.dumps_with_limit(_state())
        assert truncated is False
        assert SnapshotSerializer.loads(payload)["messages"]

    def test_상한_초과시_messages_를_절단한다(self):
        huge = [HumanMessage(content="가" * 40_000) for _ in range(10)]
        payload, truncated = SnapshotSerializer.dumps_with_limit(_state(messages=huge))
        assert truncated is True
        assert len(payload.encode("utf-8")) <= ApprovalPolicy.MAX_SNAPSHOT_BYTES

    def test_절단해도_최신_메시지를_남긴다(self):
        """맥락을 버릴 때 앞이 아니라 뒤를 살려야 재개가 이어진다."""
        huge = [HumanMessage(content="가" * 40_000) for _ in range(9)]
        huge.append(AIMessage(content="마지막", name="w1"))
        payload, _ = SnapshotSerializer.dumps_with_limit(_state(messages=huge))
        restored = SnapshotSerializer.loads(payload)
        assert restored["messages"][-1].content == "마지막"

    def test_절단_후에도_스칼라_필드는_남는다(self):
        huge = [HumanMessage(content="가" * 40_000) for _ in range(10)]
        payload, _ = SnapshotSerializer.dumps_with_limit(_state(messages=huge))
        assert SnapshotSerializer.loads(payload)["iteration_count"] == 2

    def test_단일_거대_메시지도_상한을_지킨다(self):
        """메시지 1건만으로 상한을 넘으면 더 버릴 게 없다 — 본문을 자른다."""
        payload, truncated = SnapshotSerializer.dumps_with_limit(
            _state(messages=[HumanMessage(content="가" * 300_000)])
        )
        assert truncated is True
        assert len(payload.encode("utf-8")) <= ApprovalPolicy.MAX_SNAPSHOT_BYTES


class TestSchemaVersion:
    def test_버전이_기록된다(self):
        assert SnapshotSerializer.SCHEMA_VERSION == 1

    def test_지원_버전은_복원된다(self):
        assert SnapshotSerializer.is_supported(1) is True

    def test_미래_버전은_거부된다(self):
        """포맷이 바뀐 낡은 스냅샷으로 재개하면 이상 동작한다."""
        assert SnapshotSerializer.is_supported(99) is False
