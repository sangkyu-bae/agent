"""WorkerRunCapHooks 단위 테스트.

Design Ref: mcp-tool-category-routing §5 D-07 (FR-11, module-3 개정)

  supervisor가 이미 결과를 낸 collect 워커를 다시 라우팅하지 못하게 막는다.
  기존 skip_workers 확장점(visualization_done 선례)을 그대로 쓰므로
  supervisor 코어는 수정하지 않는다.

  module-3 개정: 상한 대상은 collect 워커 **한정**이다. search 워커는
  TOOL_REGISTRY로 이미 분류돼 있어 관리자 지정 없이도 상한이 걸리는데,
  그러면 category NULL 무변화 계약(FR-14)의 취지가 기존 검색 에이전트에서
  깨진다. 관찰된 문제(스크랩 4~5회)도 collect로 해소되므로 범위를 좁혔다.
"""
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.search_pipeline import format_search_result
from src.application.agent_builder.worker_run_cap_hooks import WorkerRunCapHooks


class StubHooks:
    def __init__(self, forced=None, skipped=None):
        self._forced = forced
        self._skipped = skipped or []
        self.force_calls = 0
        self.skip_calls = 0

    def force_worker(self, state):
        self.force_calls += 1
        return self._forced

    def skip_workers(self, state):
        self.skip_calls += 1
        return list(self._skipped)


def _collect_result(worker_id: str, body: str = "수집 본문") -> AIMessage:
    return AIMessage(content=format_search_result(worker_id, body), name=worker_id)


def _state(messages):
    return {"messages": messages, "last_worker_id": "", "visualization_done": False}


class TestWorkerRunCapSkip:
    def test_no_result_yet_returns_inner_skip_only(self):
        inner = StubHooks(skipped=["analysis_worker"])
        hooks = WorkerRunCapHooks(inner, ["scrape_worker"], logger=MagicMock())

        skipped = hooks.skip_workers(_state([HumanMessage(content="수집해줘")]))

        assert skipped == ["analysis_worker"]

    def test_collect_worker_is_skipped_after_producing_result(self):
        """FR-11: 결과를 낸 collect 워커는 재라우팅 대상에서 빠진다."""
        inner = StubHooks()
        hooks = WorkerRunCapHooks(inner, ["scrape_worker"], logger=MagicMock())
        state = _state([
            HumanMessage(content="수집해줘"),
            _collect_result("scrape_worker"),
        ])

        assert hooks.skip_workers(state) == ["scrape_worker"]

    def test_only_capped_workers_are_skipped(self):
        """상한 대상이 아닌 워커(search 등)는 결과를 내도 막지 않는다."""
        inner = StubHooks()
        hooks = WorkerRunCapHooks(inner, ["scrape_worker"], logger=MagicMock())
        state = _state([
            HumanMessage(content="검색해줘"),
            _collect_result("tavily_search_worker"),
        ])

        assert hooks.skip_workers(state) == []

    def test_inner_skip_is_preserved_and_not_duplicated(self):
        inner = StubHooks(skipped=["scrape_worker", "analysis_worker"])
        hooks = WorkerRunCapHooks(inner, ["scrape_worker"], logger=MagicMock())
        state = _state([
            HumanMessage(content="수집해줘"),
            _collect_result("scrape_worker"),
        ])

        skipped = hooks.skip_workers(state)

        assert sorted(skipped) == ["analysis_worker", "scrape_worker"]
        assert skipped.count("scrape_worker") == 1

    def test_multiple_capped_workers_tracked_independently(self):
        inner = StubHooks()
        hooks = WorkerRunCapHooks(
            inner, ["scrape_worker", "fetch_worker"], logger=MagicMock()
        )
        state = _state([
            HumanMessage(content="수집해줘"),
            _collect_result("scrape_worker"),
        ])

        assert hooks.skip_workers(state) == ["scrape_worker"]

    def test_reinjected_snapshot_does_not_count_as_current_turn(self):
        """이전 턴 스냅샷 재주입은 '이번 턴 실행'이 아니다.

        data-inventory-requery D2와 같은 판정 기준을 쓴다 — 재주입분만 있는
        상태에서 워커를 막으면 이번 턴에 수집을 못 하게 된다.
        """
        from src.domain.conversation.analysis_snapshot_policy import (
            REINJECTED_MARKER,
            AnalysisSnapshotPolicy,
        )

        inner = StubHooks()
        hooks = WorkerRunCapHooks(inner, ["scrape_worker"], logger=MagicMock())
        reinjected = AIMessage(
            content=format_search_result(
                "scrape_worker", f"{REINJECTED_MARKER} (질문: 이전)\n이전 턴 본문",
            ),
            name="scrape_worker",
        )
        # 전제 확인: 이 메시지가 실제로 재주입분으로 판정되어야 한다
        assert AnalysisSnapshotPolicy.is_reinjected(reinjected.content)

        state = _state([HumanMessage(content="다시 수집해줘"), reinjected])

        assert hooks.skip_workers(state) == []

    def test_empty_capped_list_is_transparent(self):
        """collect 워커가 없으면 내부 훅과 완전히 동일하게 동작한다."""
        inner = StubHooks(skipped=["analysis_worker"])
        hooks = WorkerRunCapHooks(inner, [], logger=MagicMock())
        state = _state([
            HumanMessage(content="q"),
            _collect_result("scrape_worker"),
        ])

        assert hooks.skip_workers(state) == ["analysis_worker"]


class TestWorkerRunCapDelegation:
    def test_force_worker_delegates_to_inner(self):
        """강제 라우팅 판단은 건드리지 않는다 — 그대로 위임."""
        inner = StubHooks(forced="analysis_worker")
        hooks = WorkerRunCapHooks(inner, ["scrape_worker"], logger=MagicMock())

        assert hooks.force_worker(_state([])) == "analysis_worker"
        assert inner.force_calls == 1

    def test_force_worker_none_passes_through(self):
        inner = StubHooks(forced=None)
        hooks = WorkerRunCapHooks(inner, ["scrape_worker"], logger=MagicMock())

        assert hooks.force_worker(_state([])) is None

    def test_inner_skip_is_always_consulted(self):
        inner = StubHooks()
        hooks = WorkerRunCapHooks(inner, ["scrape_worker"], logger=MagicMock())

        hooks.skip_workers(_state([]))

        assert inner.skip_calls == 1


# ── action-category-compose-node D-11 ────────────────────────────


from src.application.agent_builder.search_pipeline import format_draft_output  # noqa: E402


class TestActionWorkerRunCap:
    def test_action_worker_is_skipped_after_draft_output(self):
        """초안 규약 메시지도 '이번 턴에 실행됨'으로 센다 — 재개 런 이중 발송 방지 (SC-8)."""
        inner = StubHooks()
        hooks = WorkerRunCapHooks(inner, ["mailer"], logger=MagicMock())
        state = _state([
            HumanMessage(content="회신 보내줘"),
            AIMessage(content=format_draft_output("mailer", "초안", "승인 대기"), name="mailer"),
        ])

        assert "mailer" in hooks.skip_workers(state)

    def test_resumed_outcome_message_alone_does_not_count(self):
        """재개 시 주입되는 평문 산출(AIMessage name=w)만으로는 실행으로 보지 않는다 —
        판정 근거는 규약 메시지다. 초안 메시지는 스냅샷에 남아 있으므로 함께 복원된다."""
        inner = StubHooks()
        hooks = WorkerRunCapHooks(inner, ["mailer"], logger=MagicMock())
        state = _state([
            HumanMessage(content="회신 보내줘"),
            AIMessage(content="메일 발송 성공", name="mailer"),
        ])

        assert "mailer" not in hooks.skip_workers(state)
