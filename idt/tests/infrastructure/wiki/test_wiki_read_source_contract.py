"""wiki_read 렌더링 형식 ↔ RunSourcePolicy 제목 추출 계약.

agent-run-source-citations Design §3.3: 정책은 도구 결과 머리글에서 제목을 읽는다.
렌더러 형식이 바뀌면 위키 칩이 조용히 사라지므로 왕복을 고정한다.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

from src.domain.agent_run.entities import ToolCall
from src.domain.agent_run.source_policy import RunEvidence, RunSourcePolicy
from src.domain.agent_run.value_objects import RunId
from src.infrastructure.wiki.wiki_read_tool import FAIL_TEXT, _render_article


def _call(summary: str) -> ToolCall:
    return ToolCall(
        id="t1", run_id=RunId("11111111-1111-1111-1111-111111111111"), step_id=None,
        tool_name="wiki_read", llm_model_id=None,
        arguments_json={"article_id": "a-1"}, result_summary=summary, result_json=None,
        token_usage=None, total_cost_usd=None, latency_ms=None, status="SUCCESS",
        error_text=None, created_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )


def _build(summary: str):
    evidence = RunEvidence([], [_call(summary)], {}, {})
    return RunSourcePolicy.build(evidence, max_items=6)


def test_rendered_article_title_round_trips() -> None:
    article = SimpleNamespace(
        title="배포 [승인] 절차", path="배포", content="본문",
        updated_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
        source_type=SimpleNamespace(value="human"),
    )
    assert _build(_render_article(article))[0].label == "배포 [승인] 절차"


def test_fail_text_is_not_a_source() -> None:
    assert _build(FAIL_TEXT) == []
