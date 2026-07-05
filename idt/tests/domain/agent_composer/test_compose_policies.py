"""ComposePolicy 단위 테스트 — 순수 도메인 규칙."""
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.agent_composer.policies import ComposePolicy
from src.domain.agent_composer.schemas import MissingCapability


def _worker(tool_id: str, sort_order: int = 0) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id,
        worker_id=f"{tool_id}_worker",
        description="테스트",
        sort_order=sort_order,
    )


class TestDropUnknownTools:
    def test_drops_hallucinated_tool_ids(self):
        workers = [_worker("tavily_search", 0), _worker("fake_tool", 1)]
        kept, dropped = ComposePolicy.drop_unknown_tools(
            workers, {"tavily_search"}
        )
        assert [w.tool_id for w in kept] == ["tavily_search"]
        assert dropped == ["fake_tool"]

    def test_all_valid_keeps_everything(self):
        workers = [_worker("a", 0), _worker("b", 1)]
        kept, dropped = ComposePolicy.drop_unknown_tools(workers, {"a", "b"})
        assert len(kept) == 2
        assert dropped == []

    def test_all_hallucinated_returns_empty(self):
        workers = [_worker("x", 0)]
        kept, dropped = ComposePolicy.drop_unknown_tools(workers, {"a"})
        assert kept == []
        assert dropped == ["x"]


class TestClampToolCount:
    def test_over_limit_truncates_by_sort_order(self):
        workers = [_worker(f"t{i}", sort_order=i) for i in range(7)]
        kept, cut = ComposePolicy.clamp_tool_count(workers, max_tools=5)
        assert [w.tool_id for w in kept] == ["t0", "t1", "t2", "t3", "t4"]
        assert cut == ["t5", "t6"]

    def test_under_limit_passes_through(self):
        workers = [_worker("a", 0), _worker("b", 1)]
        kept, cut = ComposePolicy.clamp_tool_count(workers, max_tools=5)
        assert len(kept) == 2
        assert cut == []

    def test_unsorted_input_keeps_lowest_sort_order(self):
        workers = [_worker("late", 9), _worker("early", 0)]
        kept, cut = ComposePolicy.clamp_tool_count(workers, max_tools=1)
        assert [w.tool_id for w in kept] == ["early"]
        assert cut == ["late"]


class TestClampSystemPrompt:
    def test_over_limit_truncates(self):
        prompt, truncated = ComposePolicy.clamp_system_prompt("가" * 4001, 4000)
        assert len(prompt) == 4000
        assert truncated is True

    def test_under_limit_untouched(self):
        prompt, truncated = ComposePolicy.clamp_system_prompt("짧은 프롬프트", 4000)
        assert prompt == "짧은 프롬프트"
        assert truncated is False


class TestClampHistory:
    """fix-agent-composer B3: 최근 6턴·턴당 500자 절단."""

    class _Turn:
        def __init__(self, role: str, content: str):
            self.role = role
            self.content = content

    def test_keeps_recent_turns_only(self):
        turns = [self._Turn("user", f"메시지{i}") for i in range(8)]
        clamped = ComposePolicy.clamp_history(turns)
        assert len(clamped) == ComposePolicy.MAX_HISTORY_TURNS
        assert clamped[0]["content"] == "메시지2"
        assert clamped[-1]["content"] == "메시지7"

    def test_truncates_turn_content(self):
        turns = [self._Turn("assistant", "가" * 700)]
        clamped = ComposePolicy.clamp_history(turns)
        assert len(clamped[0]["content"]) == ComposePolicy.MAX_HISTORY_TURN_CHARS
        assert clamped[0]["role"] == "assistant"

    def test_empty_returns_empty(self):
        assert ComposePolicy.clamp_history([]) == []


class TestDeriveCoverage:
    def test_zero_workers_is_none(self):
        missing = [MissingCapability(capability="ERP 조회", reason="도구 없음")]
        assert ComposePolicy.derive_coverage(0, missing) == "none"
        assert ComposePolicy.derive_coverage(0, []) == "none"

    def test_missing_capabilities_is_partial(self):
        missing = [MissingCapability(capability="ERP 조회", reason="도구 없음")]
        assert ComposePolicy.derive_coverage(2, missing) == "partial"

    def test_no_missing_is_full(self):
        assert ComposePolicy.derive_coverage(2, []) == "full"
