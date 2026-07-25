"""WikiReadTool: 에이전트 위키 단건 열람 LangChain 도구 (wiki-agentic-navigation).

- RunContext(ContextVar)의 agent_id로 자기 위키만 열람 (수평 권한 상승 차단)
- 가드(소유·승인·만료)는 WikiArticleReadUseCase가 담당 — 실패는 단일 텍스트 수렴
- 세션은 호출마다 session_factory로 열고 닫는다 (RunScopedWikiSearch 패턴,
  ToolFactory 싱글톤 안전)
- 열람 기록은 UsageCallback.on_tool_start가 모든 BaseTool을 자동 영속화하므로
  별도 배선 없음 (Design D4 — ai_tool_call.arguments_json에 article_id 기록)
"""
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.application.agent_run.context import get_current_run_context
from src.application.wiki.read_article_use_case import WikiArticleReadUseCase
from src.domain.wiki.entity import WikiArticle

FAIL_TEXT = (
    "요청한 위키 문서를 찾을 수 없거나 열람할 수 없습니다. "
    "시스템 프롬프트의 위키 목차에 있는 id인지 확인하세요."
)


class WikiReadArgs(BaseModel):
    article_id: str = Field(description="열람할 위키 문서 id (목차의 id 값)")


def _render_article(article: WikiArticle) -> str:
    updated = (
        article.updated_at.strftime("%Y-%m-%d") if article.updated_at else "-"
    )
    return (
        f"[위키 문서: {article.title}]\n"
        f"경로: {article.path or '-'} | 갱신: {updated} | "
        f"출처유형: {article.source_type.value}\n\n"
        f"{article.content}"
    )


class WikiReadTool(BaseTool):
    """에이전트의 승인 위키 문서 본문을 id로 열람하는 도구."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "wiki_read"
    description: str = (
        "이 에이전트가 보유한 승인 지식 위키 문서의 본문을 열람합니다. "
        "시스템 프롬프트의 [에이전트 지식 위키 목차]에서 문서 id를 골라 전달하세요. "
        "최근 결정사항, 정리된 지식, 축적된 판단 기준 확인에 사용하세요."
    )
    args_schema: type[BaseModel] = WikiReadArgs

    session_factory: Any
    repo_builder: Any  # (session) -> WikiArticleRepository
    request_id: str = ""
    logger: Any = None

    def _run(self, article_id: str, **kwargs: Any) -> str:
        raise NotImplementedError("WikiReadTool은 async 전용입니다 (_arun 사용)")

    async def _arun(self, article_id: str, **kwargs: Any) -> str:
        ctx = get_current_run_context()
        agent_id = getattr(ctx, "agent_id", None) if ctx is not None else None
        if not agent_id:
            # graph 외부 호출 등 에이전트 컨텍스트 부재 — 열람 불가
            return FAIL_TEXT

        async with self.session_factory() as session:
            use_case = WikiArticleReadUseCase(wiki_repo=self.repo_builder(session))
            article = await use_case.execute(
                article_id, agent_id, datetime.now(timezone.utc), self.request_id
            )
        if article is None:
            return FAIL_TEXT
        return _render_article(article)
