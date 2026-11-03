"""실행 기록 → 표시용 근거 목록 변환 정책.

Design Ref: agent-run-source-citations §3.3 — 실시간과 재진입이 같은 정책을 지나
같은 칩 목록을 만든다. 외부 의존 없는 순수 함수이며 DB·LangChain을 모른다.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Iterable, Optional
from urllib.parse import urlsplit

from src.domain.agent_run.entities import RetrievalSource, ToolCall

WEB_COLLECTION = "tavily_web"
WIKI_TOOL_NAME = "wiki_read"
MCP_ACTION_CATEGORY = "action"
TOOL_SUCCESS_STATUS = "SUCCESS"
DOCUMENT_FALLBACK_LABEL = "문서"
WEB_FALLBACK_LABEL = "웹 문서"
# FastMCP 가 실패를 결과 본문으로 돌려주는 형식. MCPToolAdapter 가 isError 를 보지
# 않아 status 는 SUCCESS 로 남는다 (실측 170건 중 50건).
MCP_ERROR_PREFIX = "Error executing tool"

_SAFE_URL_SCHEMES = frozenset({"http", "https"})
_RANK_LAST = 1 << 31
# UsageCallback 이 ToolMessage 를 json.dumps 한 뒤 1KB 로 자른 요약의 접두.
_SUMMARY_WRAPPER_PREFIX = '{"content": "'
_JSON_ESCAPE = re.compile(r'\\(["\\nrt])')
_JSON_UNESCAPED = {'"': '"', "\\": "\\", "n": "\n", "r": "\r", "t": "\t"}
# wiki_read_tool._render_article 의 머리글. 형식 변경은 계약 테스트가 잡는다.
_WIKI_HEADER = re.compile(r"^\[위키 문서: (?P<title>.+?)\](?:\n|$)")


class SourceKind(StrEnum):
    """wire 값 — 변경은 프론트 계약 변경이다."""

    DOCUMENT = "document"
    WIKI = "wiki"
    WEB = "web"
    MCP = "mcp"


_KIND_ORDER = (SourceKind.DOCUMENT, SourceKind.WIKI, SourceKind.WEB, SourceKind.MCP)


@dataclass(frozen=True)
class RunSourceItem:
    kind: SourceKind
    label: str
    excerpt: str
    key: str
    url: Optional[str] = None

    def to_payload(self) -> dict:
        """프론트 `DocumentSource` 형태. metadata·인자는 내보내지 않는다 (Design §7)."""
        payload = {
            "kind": self.kind.value,
            "source": self.label,
            "content": self.excerpt,
            "chunk_id": self.key,
        }
        if self.url:
            payload["url"] = self.url
        return payload


@dataclass(frozen=True)
class McpToolInfo:
    display_name: str
    requires_approval: bool
    category: Optional[str]
    # Design §3.1 — 칩 key 는 카탈로그 표기 `mcp:{srv}:{tool}`. 없으면 런타임 이름.
    tool_id: Optional[str] = None


@dataclass(frozen=True)
class RunEvidence:
    retrievals: list[RetrievalSource]
    tool_calls: list[ToolCall]
    filenames: dict[str, str]
    mcp_tools: dict[str, McpToolInfo]


def unwrap_tool_summary(summary: Optional[str]) -> str:
    """`ai_tool_call.result_summary` 의 `{"content": "..."}` 래퍼를 벗긴다."""
    text = (summary or "").strip()
    if not text.startswith(_SUMMARY_WRAPPER_PREFIX):
        return text
    try:
        parsed = json.loads(text)
    except ValueError:
        return _unescape_truncated(text[len(_SUMMARY_WRAPPER_PREFIX):])
    content = parsed.get("content") if isinstance(parsed, dict) else None
    return content.strip() if isinstance(content, str) else text


def _unescape_truncated(body: str) -> str:
    """1KB 절단으로 JSON 파싱이 안 되는 본문의 이스케이프만 되돌린다."""
    return _JSON_ESCAPE.sub(lambda m: _JSON_UNESCAPED[m.group(1)], body)


def _text_field(metadata: Optional[dict], key: str) -> Optional[str]:
    value = (metadata or {}).get(key)
    return value if isinstance(value, str) and value.strip() else None


def _safe_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    return url if parts.scheme.lower() in _SAFE_URL_SCHEMES and parts.netloc else None


def _unique(items: Iterable[RunSourceItem]) -> list[RunSourceItem]:
    """키별 첫 항목만 남긴다 — 입력이 정렬돼 있으므로 첫 항목이 대표다."""
    seen: dict[str, RunSourceItem] = {}
    for item in items:
        seen.setdefault(item.key, item)
    return list(seen.values())


def _retrieval_order(r: RetrievalSource) -> tuple[datetime, int, str]:
    rank = r.rank_index if r.rank_index is not None else _RANK_LAST
    return (r.created_at, rank, r.id)


def _tool_order(call: ToolCall) -> tuple[datetime, str]:
    return (call.created_at, call.id)


class RunSourcePolicy:
    """Design §3.3 규칙. 검색 방식 간 점수는 스케일이 달라 비교하지 않는다."""

    @staticmethod
    def build(evidence: RunEvidence, *, max_items: int) -> list[RunSourceItem]:
        retrievals = sorted(evidence.retrievals, key=_retrieval_order)
        calls = sorted(evidence.tool_calls, key=_tool_order)
        groups = {
            SourceKind.DOCUMENT: _document_items(retrievals, evidence.filenames),
            SourceKind.WIKI: _unique(_present(_wiki_item(c) for c in calls)),
            SourceKind.WEB: _unique(
                _web_item(r) for r in retrievals if r.collection_name == WEB_COLLECTION
            ),
            SourceKind.MCP: _unique(
                _present(_mcp_item(c, evidence.mcp_tools) for c in calls)
            ),
        }
        return _round_robin(groups, max_items)


def _present(items: Iterable[Optional[RunSourceItem]]) -> Iterable[RunSourceItem]:
    return (item for item in items if item is not None)


def _round_robin(
    groups: dict[SourceKind, list[RunSourceItem]], max_items: int,
) -> list[RunSourceItem]:
    """종류를 번갈아 골라 한 종류가 상한을 독점하지 않게 하고, 종류 순서로 묶는다."""
    counts = dict.fromkeys(_KIND_ORDER, 0)
    remaining = min(max_items, sum(len(v) for v in groups.values()))
    while remaining > 0:
        for kind in _KIND_ORDER:
            if remaining > 0 and counts[kind] < len(groups[kind]):
                counts[kind] += 1
                remaining -= 1
    return [item for kind in _KIND_ORDER for item in groups[kind][: counts[kind]]]


def _document_items(
    retrievals: list[RetrievalSource], filenames: dict[str, str],
) -> list[RunSourceItem]:
    """파일명이 있으면 파일명, 없으면 문서 키로 중복을 제거한다.

    같은 파일을 다시 올리면 document_id 만 달라 같은 이름의 칩이 겹친다 (실측).
    """
    seen: dict[str, RunSourceItem] = {}
    for r in retrievals:
        if r.collection_name == WEB_COLLECTION:
            continue
        filename = _text_field(r.metadata_json, "filename") or filenames.get(
            r.document_id or ""
        )
        item = _document_item(r, filename)
        seen.setdefault(filename or item.key, item)
    return list(seen.values())


def _document_item(r: RetrievalSource, filename: Optional[str]) -> RunSourceItem:
    label = (
        filename
        or _text_field(r.metadata_json, "clause_title")
        or _text_field(r.metadata_json, "kb_name")
        or DOCUMENT_FALLBACK_LABEL
    )
    return RunSourceItem(
        kind=SourceKind.DOCUMENT,
        label=label,
        excerpt=r.content_preview or "",
        key=r.document_id or r.chunk_id or r.id,
    )


def _web_item(r: RetrievalSource) -> RunSourceItem:
    raw_url = _text_field(r.metadata_json, "url_full") or r.document_id
    url = _safe_url(raw_url)
    label = (
        _text_field(r.metadata_json, "title")
        or (urlsplit(url).hostname if url else None)
        or WEB_FALLBACK_LABEL
    )
    return RunSourceItem(
        kind=SourceKind.WEB,
        label=label,
        excerpt=r.content_preview or "",
        key=raw_url or r.id,
        url=url,
    )


def _wiki_item(call: ToolCall) -> Optional[RunSourceItem]:
    if call.tool_name != WIKI_TOOL_NAME or call.status != TOOL_SUCCESS_STATUS:
        return None
    article_id = _text_field(call.arguments_json, "article_id")
    excerpt = unwrap_tool_summary(call.result_summary)
    header = _WIKI_HEADER.match(excerpt)
    if article_id is None or header is None:
        return None
    return RunSourceItem(
        kind=SourceKind.WIKI,
        label=header.group("title"),
        excerpt=excerpt,
        key=article_id,
    )


def _mcp_item(
    call: ToolCall, mcp_tools: dict[str, McpToolInfo],
) -> Optional[RunSourceItem]:
    info = mcp_tools.get(call.tool_name)
    if info is None or info.requires_approval or info.category == MCP_ACTION_CATEGORY:
        return None
    excerpt = unwrap_tool_summary(call.result_summary)
    failed = call.status != TOOL_SUCCESS_STATUS or excerpt.startswith(MCP_ERROR_PREFIX)
    if failed or not excerpt:
        return None
    return RunSourceItem(
        kind=SourceKind.MCP,
        label=info.display_name,
        excerpt=excerpt,
        key=info.tool_id or call.tool_name,
    )
