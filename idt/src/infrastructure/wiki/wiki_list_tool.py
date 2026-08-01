"""WikiListTool: 에이전트 위키 폴더 진입 LangChain 도구 (wiki-folder-summaries D4).

- RunContext(ContextVar)의 agent_id로 자기 위키만 조회 (수평 권한 상승 차단)
- 미존재/타 에이전트/빈 폴더는 단일 실패 문구로 수렴 (path 오라클 차단 — wiki_read 관례)
- 문서 목록은 항상 실시간 쿼리 — 폴더 요약 stale과 무관하게 목록이 진실 (D2 계약)
- 세션은 호출마다 session_factory로 열고 닫는다 (WikiReadTool 패턴)
- 호출 기록은 UsageCallback.on_tool_start 자동 영속화 (배선 0 — arguments_json.path)
"""
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.application.agent_run.context import get_current_run_context
from src.application.wiki.schemas import WikiTreeItem
from src.domain.wiki.entity import WikiFolderSummary

FAIL_TEXT = (
    "요청한 위키 폴더를 찾을 수 없거나 비어 있습니다. "
    "위키 지도의 폴더 경로인지 확인하세요."
)

_ROOT_LABEL = "루트"
_FOOTER = (
    "\n폴더는 wiki_list 도구로 더 들어가고, 문서는 wiki_read 도구에 id를 전달해 "
    "본문을 열람하세요."
)


class WikiListArgs(BaseModel):
    path: str = Field(
        default="",
        description='열어볼 폴더 경로 (예: "여신/한도"). 빈 값이면 최상위(루트)',
    )


def _is_direct_child(candidate: str, parent: str) -> bool:
    """candidate가 parent의 직속 하위 폴더 경로인지 — 루트(parent="")는 1세그먼트."""
    if parent == "":
        return "/" not in candidate
    prefix = parent + "/"
    return candidate.startswith(prefix) and "/" not in candidate[len(prefix):]


def _doc_line(item: WikiTreeItem) -> str:
    updated = item.updated_at.strftime("%Y-%m-%d") if item.updated_at else "-"
    return f"- (id: {item.id}) {item.title} — 갱신 {updated}"


def _render(
    path: str,
    child_folders: list[WikiFolderSummary],
    direct_docs: list[WikiTreeItem],
) -> str:
    lines = [f"[위키 폴더: {path or _ROOT_LABEL}]"]
    if child_folders:
        lines.append("▸ 하위 폴더:")
        lines.extend(
            f"- {f.path} — {f.summary} ({f.article_count}건)" for f in child_folders
        )
    if direct_docs:
        lines.append("▸ 문서:")
        lines.extend(_doc_line(d) for d in direct_docs)
    return "\n".join(lines) + _FOOTER


class WikiListTool(BaseTool):
    """위키 지도의 폴더를 열어 하위 폴더 요약과 문서 목록을 조회하는 도구."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "wiki_list"
    description: str = (
        "이 에이전트 지식 위키의 폴더를 열어 하위 폴더 요약과 문서 목록(id 포함)을 "
        "조회합니다. 시스템 프롬프트의 [에이전트 지식 위키 지도]에서 관련 폴더 경로를 "
        "골라 전달하세요. 빈 경로는 최상위 목록을 반환합니다."
    )
    args_schema: type[BaseModel] = WikiListArgs

    session_factory: Any
    repo_builder: Any         # (session) -> WikiArticleRepository
    folder_repo_builder: Any  # (session) -> WikiFolderSummaryRepository
    request_id: str = ""
    logger: Any = None

    def _run(self, path: str = "", **kwargs: Any) -> str:
        raise NotImplementedError("WikiListTool은 async 전용입니다 (_arun 사용)")

    async def _arun(self, path: str = "", **kwargs: Any) -> str:
        ctx = get_current_run_context()
        agent_id = getattr(ctx, "agent_id", None) if ctx is not None else None
        if not agent_id:
            return FAIL_TEXT

        normalized = path.strip().strip("/")
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            items = await self.repo_builder(session).list_searchable_tree_items(
                agent_id, now, self.request_id
            )
            folders = await self.folder_repo_builder(session).list_by_agent(
                agent_id, self.request_id
            )

        child_folders = [
            f for f in folders if _is_direct_child(f.path, normalized)
        ]
        if normalized == "":
            # 루트: 미분류(path=None) 문서를 직속으로 노출 — 유실 금지
            direct_docs = [i for i in items if i.path is None]
        else:
            direct_docs = [i for i in items if i.path == normalized]

        if not child_folders and not direct_docs:
            return FAIL_TEXT
        return _render(normalized, child_folders, direct_docs)
