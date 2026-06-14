"""분석 텍스트 → Chart.js config 생성 LLM 어댑터.

LLM은 데이터(ChartDraft)만 추출하고, 색상·options 표현은 ChartStylePolicy(domain)가
결정론적으로 채운다. 모든 실패는 빈 리스트로 graceful degrade.

chart-builder Design §4.2/§4.3.
"""
from langchain_core.language_models import BaseChatModel

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.visualization.chart_policy import ChartDraftList, ChartStylePolicy
from src.domain.visualization.chart_schemas import ChartConfig
from src.domain.visualization.interfaces import ChartBuilderInterface

_MAX_CONTEXT = 2000


def _build_chart_prompt(question: str, analysis_text: str, context: str) -> str:
    """수치 추출 지시 프롬프트."""
    context_block = (
        f"\n\n[참고 컨텍스트 (수치 근거 보강용)]\n{context[:_MAX_CONTEXT]}"
        if context else ""
    )
    return (
        "다음 분석 결과를 차트로 시각화하기 위한 데이터를 추출하세요.\n"
        "규칙:\n"
        "- 분석 결과에 **명시된 수치만** 사용하고 추측·창작하지 마세요.\n"
        "- labels와 각 series.data의 길이를 반드시 일치시키세요.\n"
        "- chart_type 선택: 시계열/추세=line, 카테고리 비교=bar, "
        "비중/구성=pie 또는 doughnut, 상관관계=scatter, 다축 비교=radar.\n"
        "- 차트로 표현하기 부적절하면 charts를 빈 배열로 두세요.\n"
        "- 색상이나 스타일은 지정하지 마세요 (데이터만).\n\n"
        f"[질문]\n{question}\n\n[분석 결과]\n{analysis_text}"
        f"{context_block}"
    )


class LangChainChartBuilder(ChartBuilderInterface):
    """LangChain BaseChatModel 기반 Chart.js config 빌더."""

    def __init__(
        self,
        llm: BaseChatModel,
        logger: LoggerInterface,
        style_policy: ChartStylePolicy,
        max_count: int,
    ) -> None:
        self._llm = llm
        self._logger = logger
        self._style = style_policy
        self._max_count = max_count

    async def build(
        self, question: str, analysis_text: str, context: str = "",
    ) -> list[ChartConfig]:
        prompt = _build_chart_prompt(question, analysis_text, context)
        try:
            draft_list = await self._llm.with_structured_output(
                ChartDraftList
            ).ainvoke(prompt)
        except Exception as e:
            self._logger.error("chart build failed, fallback []", exception=e)
            return []

        configs: list[ChartConfig] = []
        for draft in draft_list.charts[: self._max_count]:
            if not draft.labels or not draft.series:
                continue
            config = self._style.to_config(draft)
            if config.data.datasets:
                configs.append(config)
        return configs
