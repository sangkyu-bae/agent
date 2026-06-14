"""기존 차트 config + 사용자 지시 → 새 차트 변환 LLM 어댑터.

LLM은 데이터 재구조화(ChartEditDraft)만 수행하고, 표현(색상·options)은
ChartStylePolicy(domain)가 결정론적으로 채운다. 명시 색상 요청만 series.color
오버라이드 허용. 모든 실패는 charts=[] 결과로 graceful degrade.

chart-context-continuity Design §3.6.
"""
import json

from langchain_core.language_models import BaseChatModel

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.visualization.chart_policy import ChartEditDraftList, ChartStylePolicy
from src.domain.visualization.chart_schemas import ChartConfig
from src.domain.visualization.interfaces import (
    ChartTransformerInterface,
    ChartTransformResult,
)

_MAX_CHARTS_JSON = 8_000   # 기존 차트 직렬화 상한 (Design 수치 상한표)
_MAX_DATA_POINTS = 100     # 초과 시 labels/dataset.data 앞 N포인트 절단
_MAX_CONTEXT = 2_000       # 보조 컨텍스트 상한 (llm_chart_builder와 동일)


def _shrink_chart(chart: dict) -> dict:
    """labels/dataset.data를 앞 _MAX_DATA_POINTS개로 절단한 사본 반환."""
    data = chart.get("data") if isinstance(chart, dict) else None
    if not isinstance(data, dict):
        return chart
    shrunk_data = dict(data)
    labels = data.get("labels")
    if isinstance(labels, list):
        shrunk_data["labels"] = labels[:_MAX_DATA_POINTS]
    datasets = data.get("datasets")
    if isinstance(datasets, list):
        shrunk_data["datasets"] = [
            {**ds, "data": ds.get("data", [])[:_MAX_DATA_POINTS]}
            if isinstance(ds, dict) else ds
            for ds in datasets
        ]
    return {**chart, "data": shrunk_data}


def _serialize_charts(charts: list[dict]) -> str:
    """기존 차트 직렬화. 8KB 초과 시 데이터 절단 후 하드 컷."""
    serialized = json.dumps(charts, ensure_ascii=False)
    if len(serialized) > _MAX_CHARTS_JSON:
        serialized = json.dumps(
            [_shrink_chart(c) for c in charts], ensure_ascii=False,
        )
    return serialized[:_MAX_CHARTS_JSON]


def _build_transform_prompt(instruction: str, charts_json: str, context: str) -> str:
    context_block = (
        f"\n\n[분석 데이터 컨텍스트 (추가 차트 근거용)]\n{context[:_MAX_CONTEXT]}"
        if context else ""
    )
    return (
        "아래 [기존 차트]에 사용자 지시를 적용한 새 차트를 생성하세요.\n"
        "규칙:\n"
        "- 기존 차트의 데이터 수치를 기반으로 하고, 수치를 창작하지 마세요.\n"
        "- 재구조화(시리즈 분리/병합, 타입 변경, 라벨 재배열)는 허용됩니다.\n"
        "- 색상은 사용자가 명시적으로 요청한 경우에만 series.color에 hex로 지정하세요.\n"
        "- labels와 각 series.data의 길이를 반드시 일치시키세요.\n"
        "- 지시를 적용할 수 없으면 charts를 빈 배열로 두고 message에 사유를 쓰세요.\n"
        "- message는 사용자에게 보여줄 1~2문장 한국어 확인 답변입니다.\n\n"
        f"[사용자 지시]\n{instruction}\n\n[기존 차트]\n{charts_json}"
        f"{context_block}"
    )


class LangChainChartTransformer(ChartTransformerInterface):
    """LangChain BaseChatModel 기반 차트 변환기."""

    def __init__(
        self,
        llm: BaseChatModel,
        logger: LoggerInterface,
        style_policy: ChartStylePolicy,
    ) -> None:
        self._llm = llm
        self._logger = logger
        self._style = style_policy

    async def transform(
        self, instruction: str, charts: list[dict], context: str = "",
    ) -> ChartTransformResult:
        prompt = _build_transform_prompt(
            instruction, _serialize_charts(charts), context,
        )
        try:
            draft_list = await self._llm.with_structured_output(
                ChartEditDraftList
            ).ainvoke(prompt)
        except Exception as e:
            self._logger.error("chart transform failed, fallback []", exception=e)
            return ChartTransformResult(charts=[], message="")

        configs: list[ChartConfig] = []
        for draft in draft_list.charts:
            if not draft.labels or not draft.series:
                continue
            config = self._style.to_config(draft)
            if config.data.datasets:
                configs.append(config)
        return ChartTransformResult(charts=configs, message=draft_list.message)
