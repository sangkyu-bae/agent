"""WikiDistiller: LLM 기반 원본 청크 정제기 (LLM-WIKI-001, Phase 1/B).

청크 그룹을 사실 중심 위키 본문으로 요약한다. LLM은 주입받아(테스트 용이)
ainvoke 가능한 객체면 된다. 운영에서는 from_openai 팩토리로 ChatOpenAI를 쓴다.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from src.application.wiki.interfaces import WikiDistillerInterface
from src.application.wiki.schemas import DistilledContent, WikiSourceGroup
from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_SYSTEM_PROMPT = (
    "당신은 금융/정책 문서를 사실 중심으로 정제하는 전문가입니다.\n"
    "규칙:\n"
    "- 원문에 있는 사실만 사용(추측·창작 금지)\n"
    "- 결정사항·수치·조건을 보존, 중복 제거\n"
    "- 질문/답변 형식 금지, 간결한 위키 항목 본문으로 작성\n"
    "아래 원문들을 하나의 위키 본문으로 정제하세요."
)
_TITLE_MAX = 200


def _coerce_text(content) -> str:
    """LLM content가 블록 리스트로 와도 문자열로 정규화 (메모리 노트)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            blk.get("text", "") if isinstance(blk, dict) else str(blk)
            for blk in content
        ]
        return "".join(parts)
    return str(content)


def _derive_title(content: str) -> str:
    """제목 힌트가 없을 때 본문 첫 문장에서 제목을 파생한다."""
    first = content.strip().split("\n", 1)[0].strip()
    head = first.split(". ")[0][:_TITLE_MAX].strip()
    return head or "위키 항목"


class WikiDistiller(WikiDistillerInterface):
    """LLM으로 청크 그룹을 위키 본문으로 정제한다."""

    def __init__(
        self,
        llm,
        logger: LoggerInterface,
        llm_provider: UtilityLLMProviderPort | None = None,
    ) -> None:
        self._llm = llm
        self._logger = logger
        self._llm_provider = llm_provider

    async def _resolve_llm(self):
        """호출 시점의 유효 LLM. admin-default-llm-routing AD-2.

        provider 미주입이거나 해석 실패면 생성자 주입 LLM 으로 낙하한다.
        """
        if self._llm_provider is not None:
            resolved = await self._llm_provider.get(0.0)
            if resolved is not None:
                return resolved
        return self._llm

    @classmethod
    def from_openai(
        cls,
        model_name: str,
        api_key: str,
        logger: LoggerInterface,
        llm_provider: UtilityLLMProviderPort | None = None,
    ):
        """레거시 ChatOpenAI 를 폴백으로 두고, provider 가 있으면 그쪽을 우선한다."""
        from langchain_openai import ChatOpenAI

        return cls(
            ChatOpenAI(model=model_name, api_key=api_key, temperature=0),
            logger,
            llm_provider=llm_provider,
        )

    async def distill(
        self, group: WikiSourceGroup, request_id: str
    ) -> DistilledContent:
        source_text = "\n\n".join(group.texts)
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=source_text),
        ]
        try:
            llm = await self._resolve_llm()
            response = await llm.ainvoke(messages)
        except Exception as e:
            self._logger.error("WikiDistiller failed", exception=e, request_id=request_id)
            raise
        content = _coerce_text(response.content)
        title = group.topic_hint or _derive_title(content)
        return DistilledContent(title=title[:_TITLE_MAX], content=content)
