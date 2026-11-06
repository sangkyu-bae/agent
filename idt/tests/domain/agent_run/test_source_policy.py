"""RunSourcePolicy — 실행 기록을 표시용 근거로 변환하는 순수 정책.

agent-run-source-citations Design §3.3. 입력 형태는 로컬 DB 실측값을 따른다.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.domain.agent_run.entities import RetrievalSource, ToolCall
from src.domain.agent_run.source_policy import (
    McpToolInfo,
    RunEvidence,
    RunSourceItem,
    RunSourcePolicy,
    SourceKind,
    unwrap_tool_summary,
)
from src.domain.agent_run.value_objects import RunId

RUN_ID = RunId("11111111-1111-1111-1111-111111111111")
T0 = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)
MCP_NAME = "mcp_081c6fe7_e0bd_4aad_9a42_29b8bf073167_scrape_url"
MCP_TOOL_ID = "mcp:081c6fe7-e0bd-4aad-9a42-29b8bf073167:scrape_url"
MCP_INFO = McpToolInfo(
    "scrape_url", requires_approval=False, category=None, tool_id=MCP_TOOL_ID,
)


def _retrieval(
    id_: str = "r1",
    *,
    collection: str = "kb",
    document_id: Optional[str] = "doc-1",
    chunk_id: Optional[str] = "c1",
    rank: Optional[int] = 1,
    preview: Optional[str] = "발췌",
    metadata: Optional[dict[str, Any]] = None,
    created_at: datetime = T0,
) -> RetrievalSource:
    return RetrievalSource(
        id=id_, run_id=RUN_ID, tool_call_id=None, collection_name=collection,
        document_id=document_id, chunk_id=chunk_id, score=None, rank_index=rank,
        content_preview=preview, metadata_json=metadata, created_at=created_at,
    )


def _web(id_: str, url: str, title: Optional[str] = "제목", **kwargs) -> RetrievalSource:
    return _retrieval(
        id_, collection="tavily_web", document_id=url[:150], chunk_id=None,
        metadata={"title": title, "url_full": url}, **kwargs,
    )


def _tool_call(
    id_: str = "t1",
    *,
    tool_name: str = MCP_NAME,
    summary: Optional[str] = '{"content": "결과"}',
    status: str = "SUCCESS",
    arguments: Optional[dict[str, Any]] = None,
    created_at: datetime = T0,
) -> ToolCall:
    return ToolCall(
        id=id_, run_id=RUN_ID, step_id=None, tool_name=tool_name, llm_model_id=None,
        arguments_json=arguments, result_summary=summary, result_json=None,
        token_usage=None, total_cost_usd=None, latency_ms=None, status=status,
        error_text=None, created_at=created_at,
    )


def _wiki(id_: str = "w1", article_id: str = "a-1", title: str = "배포 승인 절차") -> ToolCall:
    return _tool_call(
        id_, tool_name="wiki_read", arguments={"article_id": article_id},
        summary=f"[위키 문서: {title}]\n경로: 배포 | 갱신: 2026-07-28\n\n본문",
    )


def _build(
    retrievals: Optional[list[RetrievalSource]] = None,
    tool_calls: Optional[list[ToolCall]] = None,
    *,
    filenames: Optional[dict[str, str]] = None,
    mcp_tools: Optional[dict[str, McpToolInfo]] = None,
    max_items: int = 6,
) -> list[RunSourceItem]:
    evidence = RunEvidence(
        retrievals=retrievals or [],
        tool_calls=tool_calls or [],
        filenames=filenames or {},
        mcp_tools={MCP_NAME: MCP_INFO} if mcp_tools is None else mcp_tools,
    )
    return RunSourcePolicy.build(evidence, max_items=max_items)


class TestDocumentLabel:
    def test_metadata_filename_wins(self) -> None:
        items = _build(
            [_retrieval(metadata={"filename": "a.pdf"})],
            filenames={"doc-1": "b.pdf"},
        )
        assert items[0].label == "a.pdf"

    def test_falls_back_to_document_metadata_filename(self) -> None:
        items = _build(
            [_retrieval(metadata={"kb_name": "KB"})],
            filenames={"doc-1": "b.pdf"},
        )
        assert items[0].label == "b.pdf"

    def test_falls_back_to_clause_then_kb_name_then_fixed_text(self) -> None:
        assert _build([_retrieval(metadata={"clause_title": "제3조", "kb_name": "KB"})])[0].label == "제3조"
        assert _build([_retrieval(metadata={"kb_name": "KB"})])[0].label == "KB"
        assert _build([_retrieval(metadata=None)])[0].label == "문서"

    def test_document_item_shape(self) -> None:
        item = _build([_retrieval(metadata={"filename": "a.pdf"}, preview="본문")])[0]
        assert (item.kind, item.excerpt, item.key, item.url) == (
            SourceKind.DOCUMENT, "본문", "doc-1", None,
        )


class TestDocumentDedupe:
    def test_same_document_is_one_chip_with_best_ranked_excerpt(self) -> None:
        items = _build([
            _retrieval("r2", chunk_id="c2", rank=2, preview="둘째"),
            _retrieval("r1", chunk_id="c1", rank=1, preview="첫째"),
        ])
        assert [i.excerpt for i in items] == ["첫째"]

    def test_same_filename_across_document_ids_is_one_chip(self) -> None:
        # 실측: 같은 파일 재업로드로 document_id 만 다른 문서가 칩 3개로 중복됐다.
        items = _build(
            [
                _retrieval("r1", document_id="d1", metadata={"filename": "a.pdf"}),
                _retrieval("r2", document_id="d2"),
                _retrieval("r3", document_id="d3", metadata={"filename": "a.pdf"}),
                _retrieval("r4", document_id="d4", metadata={"filename": "b.pdf"}),
            ],
            filenames={"d2": "a.pdf"},
        )
        assert [(i.label, i.key) for i in items] == [("a.pdf", "d1"), ("b.pdf", "d4")]

    def test_documents_without_filename_stay_separate(self) -> None:
        items = _build([
            _retrieval("r1", document_id="d1", metadata={"kb_name": "KB"}),
            _retrieval("r2", document_id="d2", metadata={"kb_name": "KB"}),
        ])
        assert [i.key for i in items] == ["d1", "d2"]

    def test_chunk_id_is_key_when_document_id_missing(self) -> None:
        items = _build([
            _retrieval("r1", document_id=None, chunk_id="c1"),
            _retrieval("r2", document_id=None, chunk_id="c2"),
        ])
        assert [i.key for i in items] == ["c1", "c2"]


class TestWeb:
    def test_label_and_url(self) -> None:
        item = _build([_web("r1", "https://a.example/x", title="금리")])[0]
        assert (item.kind, item.label, item.url, item.key) == (
            SourceKind.WEB, "금리", "https://a.example/x", "https://a.example/x",
        )

    def test_label_falls_back_to_host(self) -> None:
        assert _build([_web("r1", "https://a.example/x", title=None)])[0].label == "a.example"

    def test_same_url_is_deduped(self) -> None:
        items = _build([_web("r1", "https://a.example/x"), _web("r2", "https://a.example/x")])
        assert len(items) == 1

    def test_unsafe_scheme_keeps_chip_without_link(self) -> None:
        item = _build([_web("r1", "javascript:alert(1)", title="악성")])[0]
        assert (item.label, item.url) == ("악성", None)


class TestWiki:
    def test_title_and_article_id(self) -> None:
        item = _build(tool_calls=[_wiki()])[0]
        assert (item.kind, item.label, item.key, item.url) == (
            SourceKind.WIKI, "배포 승인 절차", "a-1", None,
        )

    def test_failed_read_without_header_is_excluded(self) -> None:
        call = _tool_call(
            tool_name="wiki_read", arguments={"article_id": "a-1"},
            summary="문서를 찾을 수 없습니다.",
        )
        assert _build(tool_calls=[call]) == []

    def test_wrapped_summary_is_understood(self) -> None:
        call = _tool_call(
            tool_name="wiki_read", arguments={"article_id": "a-1"},
            summary='{"content": "[위키 문서: 제목]\\n경로: - | 갱신: -\\n\\n본문"}',
        )
        assert _build(tool_calls=[call])[0].label == "제목"

    def test_same_article_is_deduped(self) -> None:
        assert len(_build(tool_calls=[_wiki("w1"), _wiki("w2")])) == 1

    def test_missing_article_id_is_excluded(self) -> None:
        call = _wiki()
        call.arguments_json = {}
        assert _build(tool_calls=[call]) == []


class TestMcp:
    def test_label_uses_catalog_name_not_uuid(self) -> None:
        item = _build(tool_calls=[_tool_call(summary='{"content": "본문"}')])[0]
        # Design §3.1 — key 는 카탈로그 tool_id (런타임 합성 이름 아님)
        assert (item.kind, item.label, item.excerpt, item.key) == (
            SourceKind.MCP, "scrape_url", "본문", MCP_TOOL_ID,
        )

    def test_same_tool_is_one_chip(self) -> None:
        assert len(_build(tool_calls=[_tool_call("t1"), _tool_call("t2")])) == 1

    def test_unknown_tool_is_excluded(self) -> None:
        assert _build(tool_calls=[_tool_call()], mcp_tools={}) == []

    def test_requires_approval_is_excluded(self) -> None:
        info = McpToolInfo("send_mail", requires_approval=True, category=None)
        assert _build(tool_calls=[_tool_call()], mcp_tools={MCP_NAME: info}) == []

    def test_action_category_is_excluded(self) -> None:
        info = McpToolInfo("browser_click", requires_approval=False, category="action")
        assert _build(tool_calls=[_tool_call()], mcp_tools={MCP_NAME: info}) == []

    def test_failed_status_is_excluded(self) -> None:
        assert _build(tool_calls=[_tool_call(status="FAILED")]) == []
        assert _build(tool_calls=[_tool_call(status="STARTED")]) == []

    def test_empty_result_is_excluded(self) -> None:
        assert _build(tool_calls=[_tool_call(summary=None)]) == []
        assert _build(tool_calls=[_tool_call(summary='{"content": ""}')]) == []

    def test_error_text_with_success_status_is_excluded(self) -> None:
        raw = "Error executing tool scrape_url: 1 validation error"
        wrapped = '{"content": "Error executing tool scrape_url: 1 validation'
        assert _build(tool_calls=[_tool_call(summary=raw)]) == []
        assert _build(tool_calls=[_tool_call(summary=wrapped)]) == []

    def test_error_call_does_not_hide_later_success(self) -> None:
        items = _build(tool_calls=[
            _tool_call("t1", summary="Error executing tool scrape_url: x"),
            _tool_call("t2", summary='{"content": "성공"}'),
        ])
        assert [i.excerpt for i in items] == ["성공"]

    def test_non_mcp_tool_is_ignored(self) -> None:
        assert _build(tool_calls=[_tool_call(tool_name="tavily_search")]) == []


class TestSelection:
    def test_empty_evidence(self) -> None:
        assert _build() == []

    def test_output_is_grouped_in_kind_order(self) -> None:
        items = _build(
            [_web("r1", "https://a.example"), _retrieval("r2")],
            [_tool_call(), _wiki()],
        )
        assert [i.kind for i in items] == [
            SourceKind.DOCUMENT, SourceKind.WIKI, SourceKind.WEB, SourceKind.MCP,
        ]

    def test_one_kind_cannot_take_every_slot(self) -> None:
        documents = [_retrieval(f"r{n}", document_id=f"d{n}") for n in range(5)]
        items = _build(documents + [_web("w", "https://a.example")], max_items=2)
        assert [i.kind for i in items] == [SourceKind.DOCUMENT, SourceKind.WEB]

    def test_remaining_slots_go_to_kinds_with_items_left(self) -> None:
        documents = [_retrieval(f"r{n}", document_id=f"d{n}") for n in range(5)]
        items = _build(documents + [_web("w", "https://a.example")], max_items=4)
        assert [i.kind for i in items].count(SourceKind.DOCUMENT) == 3

    def test_order_is_first_retrieved_then_rank_then_id(self) -> None:
        later = T0 + timedelta(seconds=1)
        items = _build([
            _retrieval("r3", document_id="d3", created_at=later, rank=1),
            _retrieval("r2", document_id="d2", rank=2),
            _retrieval("r1", document_id="d1", rank=None),
            _retrieval("r0", document_id="d0", rank=2),
        ])
        assert [i.key for i in items] == ["d0", "d2", "d1", "d3"]


class TestUnwrapToolSummary:
    def test_complete_wrapper(self) -> None:
        assert unwrap_tool_summary('{"content": "본문", "type": "tool"}') == "본문"

    def test_truncated_wrapper_restores_escapes(self) -> None:
        text = '{"content": "{\\n  \\"url\\": \\"https://a\\",\\n  \\"path\\": \\"c:\\\\d'
        assert unwrap_tool_summary(text) == '{\n  "url": "https://a",\n  "path": "c:\\d'

    def test_plain_text_is_kept(self) -> None:
        assert unwrap_tool_summary("[출처: a]\n본문") == "[출처: a]\n본문"

    def test_none_is_empty(self) -> None:
        assert unwrap_tool_summary(None) == ""

    def test_non_string_content_keeps_original(self) -> None:
        text = '{"content": "a", "x": 1}'
        assert unwrap_tool_summary(text) == "a"
        assert unwrap_tool_summary('{"content": [1]}') == '{"content": [1]}'


class TestPayload:
    def test_web_payload_matches_frontend_shape(self) -> None:
        item = RunSourceItem(SourceKind.WEB, "제목", "발췌", "https://a", "https://a")
        assert item.to_payload() == {
            "kind": "web", "source": "제목", "content": "발췌",
            "chunk_id": "https://a", "url": "https://a",
        }

    def test_url_key_absent_for_non_web(self) -> None:
        item = RunSourceItem(SourceKind.DOCUMENT, "a.pdf", "발췌", "doc-1")
        assert "url" not in item.to_payload()
        assert "score" not in item.to_payload()
