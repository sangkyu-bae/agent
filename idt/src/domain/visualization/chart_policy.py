"""차트 표현 규칙 (색상 팔레트 · options 조립) + LLM 추출 중간 모델.

LLM은 색상/options를 모른 채 데이터만 추출(ChartDraft)하고,
표현 규칙은 이 순수 도메인 Policy가 결정론적으로 수행한다.

chart-builder Design §3.2/§3.3.
"""
from pydantic import BaseModel, Field

from src.domain.visualization.chart_schemas import (
    ChartConfig,
    ChartData,
    ChartDataset,
    ChartType,
)


class ChartSeriesDraft(BaseModel):
    """LLM 추출 시리즈 (색상 없음)."""

    name: str = Field(description="시리즈 이름 (예: '매출')")
    data: list[float] = Field(description="labels와 같은 길이의 수치 배열")


class ChartDraft(BaseModel):
    """LLM structured output 중간 모델 — 데이터만 담는다."""

    chart_type: ChartType
    title: str = Field(default="", description="차트 제목")
    x_axis_name: str = Field(default="", description="x축 이름")
    y_axis_name: str = Field(default="", description="y축 이름")
    labels: list[str] = Field(description="x축 라벨")
    series: list[ChartSeriesDraft] = Field(description="1개 이상 시리즈")


class ChartDraftList(BaseModel):
    """LLM structured output 컨테이너 (0개 이상의 차트)."""

    charts: list[ChartDraft] = Field(default_factory=list)


class ChartEditSeriesDraft(ChartSeriesDraft):
    """차트 변환용 시리즈 — 명시 색상 요청 시만 color 지정.

    chart-context-continuity D5: 색상 결정은 ChartStylePolicy가 전담하되,
    "빨간색으로" 같은 명시 요청에 한해 오버라이드를 허용한다.
    """

    color: str | None = Field(
        default=None, description="사용자가 색상을 명시한 경우만 hex (#RRGGBB)",
    )


class ChartEditDraft(ChartDraft):
    """차트 변환 LLM structured output 중간 모델."""

    series: list[ChartEditSeriesDraft]


class ChartEditDraftList(BaseModel):
    """차트 변환 출력 컨테이너 — 변환 불가 시 charts=[] + message에 사유."""

    charts: list[ChartEditDraft] = Field(default_factory=list)
    message: str = Field(
        default="", description="사용자 확인용 1~2문장 한국어 답변",
    )


class ChartStylePolicy:
    """ChartDraft → 색상·options가 채워진 ChartConfig 변환 규칙.

    순수 도메인 규칙(외부 의존 0). 색상 결정은 도메인 책임으로 둔다.
    """

    PALETTE: tuple[str, ...] = (
        "#4E79A7", "#F28E2B", "#59A14F", "#E15759",
        "#76B7B2", "#EDC948", "#B07AA1", "#FF9DA7",
    )
    _PER_POINT_TYPES = (ChartType.PIE, ChartType.DOUGHNUT, ChartType.RADAR)
    _AXIS_TYPES = (ChartType.BAR, ChartType.LINE)

    def to_config(self, draft: ChartDraft) -> ChartConfig:
        """Draft를 Chart.js config로 변환한다."""
        datasets = [
            self._build_dataset(draft.chart_type, series, idx, len(draft.labels))
            for idx, series in enumerate(draft.series)
        ]
        return ChartConfig(
            type=draft.chart_type,
            data=ChartData(labels=draft.labels, datasets=datasets),
            options=self._build_options(draft),
        )

    def _color(self, idx: int) -> str:
        return self.PALETTE[idx % len(self.PALETTE)]

    def _build_dataset(
        self, chart_type: ChartType, series: ChartSeriesDraft,
        idx: int, n_labels: int,
    ) -> ChartDataset:
        if chart_type in self._PER_POINT_TYPES:
            colors = [self._color(i) for i in range(n_labels)]
            return ChartDataset(
                label=series.name, data=series.data, backgroundColor=colors,
            )
        # chart-context-continuity D5: 명시 색상 요청(ChartEditSeriesDraft.color)만
        # 오버라이드. per-point 타입은 포인트별 팔레트 유지(오버라이드 무시).
        color = getattr(series, "color", None) or self._color(idx)
        return ChartDataset(
            label=series.name, data=series.data,
            backgroundColor=color, borderColor=color,
        )

    def _build_options(self, draft: ChartDraft) -> dict:
        options: dict = {"responsive": True}
        if draft.title:
            options["plugins"] = {
                "title": {"display": True, "text": draft.title}
            }
        if draft.chart_type in self._AXIS_TYPES:
            options["scales"] = {
                "x": self._axis_title(draft.x_axis_name),
                "y": self._axis_title(draft.y_axis_name),
            }
        return options

    @staticmethod
    def _axis_title(name: str) -> dict:
        return {"title": {"display": bool(name), "text": name}}
