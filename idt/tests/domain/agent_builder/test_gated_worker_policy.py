"""GatedWorkerPolicy 단위 테스트 — 단독 워커 제약 (Plan FR-05).

Design Ref: §2.0 / §7.2 재개 단위.

승인 도구를 다른 도구와 같은 워커에 두면, react 루프 중간에 게이트가 걸려
앞선 도구 호출 결과가 재개 시 유실된다. 제약으로 그 상황 자체를 없앤다 —
게이트는 항상 워커의 유일한 도구다.
"""
import pytest

from src.domain.agent_builder.policies import GatedWorkerPolicy
from src.domain.agent_builder.schemas import WorkerDefinition


def _worker(tool_id: str, worker_id: str = "w1") -> WorkerDefinition:
    return WorkerDefinition(tool_id=tool_id, worker_id=worker_id, description="")


def _sub_agent(worker_id: str = "s1") -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="", worker_id=worker_id, description="",
        worker_type="sub_agent", ref_agent_id="ag2",
    )


class TestValidate:
    def test_게이트_도구가_없으면_통과(self):
        GatedWorkerPolicy.validate(
            [_worker("tavily_search"), _worker("excel_export", "w2")],
            gated_tool_ids=set(),
        )

    def test_게이트_도구가_단독_워커면_통과(self):
        GatedWorkerPolicy.validate(
            [_worker("tavily_search"), _worker("email_send", "w2")],
            gated_tool_ids={"email_send"},
        )

    def test_같은_워커id에_게이트_도구와_다른_도구가_섞이면_거부(self):
        with pytest.raises(ValueError, match="email_send"):
            GatedWorkerPolicy.validate(
                [_worker("tavily_search", "w1"), _worker("email_send", "w1")],
                gated_tool_ids={"email_send"},
            )

    def test_게이트_도구_둘이_같은_워커여도_거부(self):
        """둘 다 승인 대상이어도 한 워커에 있으면 재개 단위가 깨진다."""
        with pytest.raises(ValueError):
            GatedWorkerPolicy.validate(
                [_worker("email_send", "w1"), _worker("rate_update", "w1")],
                gated_tool_ids={"email_send", "rate_update"},
            )

    def test_게이트_도구가_여러_워커에_각각_단독이면_통과(self):
        GatedWorkerPolicy.validate(
            [_worker("email_send", "w1"), _worker("rate_update", "w2")],
            gated_tool_ids={"email_send", "rate_update"},
        )

    def test_sub_agent는_제약_대상이_아니다(self):
        """서브에이전트는 도구가 아니라 중첩 그래프다 — 자체 게이트를 가진다."""
        GatedWorkerPolicy.validate(
            [_worker("email_send", "w1"), _sub_agent("w2")],
            gated_tool_ids={"email_send"},
        )

    def test_빈_워커_목록은_통과(self):
        GatedWorkerPolicy.validate([], gated_tool_ids={"email_send"})

    def test_에러_메시지가_해결_방법을_알려준다(self):
        """제약이 아니라 권장 구조임을 안내해야 사용자가 막히지 않는다."""
        with pytest.raises(ValueError) as e:
            GatedWorkerPolicy.validate(
                [_worker("tavily_search", "w1"), _worker("email_send", "w1")],
                gated_tool_ids={"email_send"},
            )
        assert "분리" in str(e.value)


class TestCollectGatedToolIds:
    def test_카탈로그에서_승인_대상_도구만_모은다(self):
        catalog = {
            "email_send": _entry(requires_approval=True),
            "tavily_search": _entry(requires_approval=False),
        }
        assert GatedWorkerPolicy.collect_gated_tool_ids(catalog) == {"email_send"}

    def test_빈_카탈로그는_빈_집합(self):
        assert GatedWorkerPolicy.collect_gated_tool_ids({}) == set()

    def test_None_카탈로그도_빈_집합(self):
        """카탈로그 미주입·조회 실패 시 기존 동작으로 낮춘다 (FR-14 취지)."""
        assert GatedWorkerPolicy.collect_gated_tool_ids(None) == set()


class _Entry:
    def __init__(self, requires_approval: bool) -> None:
        self.requires_approval = requires_approval


def _entry(*, requires_approval: bool) -> _Entry:
    return _Entry(requires_approval)
