"""FolderSummaryDistiller: LLM 기반 폴더 안내 설명 증류기 (wiki-folder-summaries D3).

계층 증류(RAPTOR식): leaf는 직속 문서 스니펫, 상위 폴더는 하위 폴더 요약이 주 입력.
입력 상한 — 문서당 500자, 총 20,000자 (doc-extractor LLM 입력 상한 교훈).
"""
from langchain_core.messages import HumanMessage, SystemMessage

from src.application.wiki.interfaces import FolderSummaryDistillerInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.wiki.wiki_distiller import _coerce_text

_DOC_SNIPPET_MAX = 500
_TOTAL_INPUT_MAX = 20_000

_SYSTEM_PROMPT = (
    "당신은 지식 폴더의 안내 설명을 작성하는 사서입니다.\n"
    "아래 폴더가 보유한 문서·하위 폴더 정보를 바탕으로, 이 폴더가 무엇을 다루며 "
    "어떤 질문에 유용한지 2~3문장으로 작성하세요.\n"
    "규칙: 개별 문서 나열 금지, 원문에 있는 사실만 사용(추측·창작 금지), "
    "간결한 평서문."
)


class FolderSummaryDistiller(FolderSummaryDistillerInterface):
    """LLM으로 폴더 안내 설명을 생성한다."""

    def __init__(self, llm, logger: LoggerInterface) -> None:
        self._llm = llm
        self._logger = logger

    @classmethod
    def from_openai(cls, model_name: str, api_key: str, logger: LoggerInterface):
        from langchain_openai import ChatOpenAI

        return cls(ChatOpenAI(model=model_name, api_key=api_key, temperature=0), logger)

    async def summarize_folder(
        self,
        path: str,
        doc_snippets: list[str],
        child_summaries: list[str],
        request_id: str,
    ) -> str:
        parts = [f"[폴더 경로] {path}"]
        if child_summaries:
            parts.append("[하위 폴더 요약]")
            parts.extend(f"- {s}" for s in child_summaries)
        if doc_snippets:
            parts.append("[직속 문서]")
            parts.extend(f"- {s[:_DOC_SNIPPET_MAX]}" for s in doc_snippets)
        source_text = "\n".join(parts)[:_TOTAL_INPUT_MAX]

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=source_text),
        ]
        try:
            response = await self._llm.ainvoke(messages)
        except Exception as e:
            self._logger.error(
                "FolderSummaryDistiller failed", exception=e,
                request_id=request_id, path=path,
            )
            raise
        return _coerce_text(response.content).strip()
