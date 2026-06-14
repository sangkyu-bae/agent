"""ChartEditDraft + ChartStylePolicy 색상 오버라이드 테스트.

chart-context-continuity Design §3.5 (D5):
- 색상은 계속 ChartStylePolicy가 결정하되, 명시 요청 시 series.color 오버라이드 허용.
- per-point 타입(pie/doughnut/radar)은 오버라이드 무시 (포인트별 팔레트 유지).
"""
from src.domain.visualization.chart_policy import (
    ChartEditDraft,
    ChartEditDraftList,
    ChartEditSeriesDraft,
    ChartStylePolicy,
)
from src.domain.visualization.chart_schemas import ChartType


def _edit_draft(
    chart_type: ChartType = ChartType.BAR,
    colors: list[str | None] | None = None,
) -> ChartEditDraft:
    names_colors = colors if colors is not None else [None]
    return ChartEditDraft(
        chart_type=chart_type,
        title="t",
        labels=["a", "b", "c"],
        series=[
            ChartEditSeriesDraft(name=f"S{i}", data=[1.0, 2.0, 3.0], color=c)
            for i, c in enumerate(names_colors)
        ],
    )


class TestColorOverride:
    def setup_method(self) -> None:
        self.policy = ChartStylePolicy()

    def test_explicit_color_overrides_palette(self) -> None:
        config = self.policy.to_config(_edit_draft(colors=["#FF0000"]))
        ds = config.data.datasets[0]
        assert ds.backgroundColor == "#FF0000"
        assert ds.borderColor == "#FF0000"

    def test_series_without_color_uses_palette(self) -> None:
        config = self.policy.to_config(_edit_draft(colors=["#FF0000", None]))
        assert config.data.datasets[0].backgroundColor == "#FF0000"
        assert config.data.datasets[1].backgroundColor == ChartStylePolicy.PALETTE[1]

    def test_per_point_type_ignores_override(self) -> None:
        config = self.policy.to_config(
            _edit_draft(chart_type=ChartType.PIE, colors=["#FF0000"])
        )
        # pie는 포인트별 색상 리스트 유지 (단일 오버라이드 무시)
        assert isinstance(config.data.datasets[0].backgroundColor, list)

    def test_plain_draft_unaffected_regression(self) -> None:
        """기존 ChartDraft(color 속성 없음) 경로 회귀 없음."""
        from src.domain.visualization.chart_policy import ChartDraft, ChartSeriesDraft

        draft = ChartDraft(
            chart_type=ChartType.BAR, labels=["a"],
            series=[ChartSeriesDraft(name="S", data=[1.0])],
        )
        config = self.policy.to_config(draft)
        assert config.data.datasets[0].backgroundColor == ChartStylePolicy.PALETTE[0]


class TestEditDraftList:
    def test_message_field_default_empty(self) -> None:
        assert ChartEditDraftList().message == ""

    def test_carries_message(self) -> None:
        dl = ChartEditDraftList(charts=[], message="적용할 수 없습니다")
        assert dl.message == "적용할 수 없습니다"
