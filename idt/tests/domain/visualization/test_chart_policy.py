"""ChartStylePolicy 테스트. Domain: 순수 단위테스트 (mock 금지)."""
from src.domain.visualization.chart_policy import (
    ChartDraft,
    ChartSeriesDraft,
    ChartStylePolicy,
)
from src.domain.visualization.chart_schemas import ChartType


def _draft(chart_type: ChartType, n_labels: int = 3, n_series: int = 1,
           title: str = "", x: str = "", y: str = "") -> ChartDraft:
    labels = [f"L{i}" for i in range(n_labels)]
    series = [
        ChartSeriesDraft(name=f"S{j}", data=[float(i) for i in range(n_labels)])
        for j in range(n_series)
    ]
    return ChartDraft(
        chart_type=chart_type, title=title, x_axis_name=x, y_axis_name=y,
        labels=labels, series=series,
    )


class TestBarLineStyling:
    def test_bar_single_color_and_axis_titles(self) -> None:
        policy = ChartStylePolicy()
        cfg = policy.to_config(_draft(ChartType.BAR, x="월", y="매출"))
        ds = cfg.data.datasets[0]
        # bar는 단일 색상 문자열
        assert isinstance(ds.backgroundColor, str)
        assert ds.backgroundColor.startswith("#")
        # 축 타이틀이 options.scales에 반영
        assert cfg.options["scales"]["x"]["title"]["text"] == "월"
        assert cfg.options["scales"]["y"]["title"]["text"] == "매출"

    def test_line_has_scales(self) -> None:
        policy = ChartStylePolicy()
        cfg = policy.to_config(_draft(ChartType.LINE))
        assert "scales" in cfg.options

    def test_title_goes_to_options_plugins(self) -> None:
        policy = ChartStylePolicy()
        cfg = policy.to_config(_draft(ChartType.BAR, title="월별 매출"))
        assert cfg.options["plugins"]["title"]["text"] == "월별 매출"
        assert cfg.options["plugins"]["title"]["display"] is True

    def test_multi_series_cycles_palette(self) -> None:
        policy = ChartStylePolicy()
        cfg = policy.to_config(_draft(ChartType.BAR, n_series=2))
        c0 = cfg.data.datasets[0].backgroundColor
        c1 = cfg.data.datasets[1].backgroundColor
        assert c0 != c1  # 서로 다른 팔레트 색상


class TestPieStyling:
    def test_pie_per_point_color_list(self) -> None:
        policy = ChartStylePolicy()
        cfg = policy.to_config(_draft(ChartType.PIE, n_labels=4))
        ds = cfg.data.datasets[0]
        # pie/doughnut은 포인트별 색상 리스트
        assert isinstance(ds.backgroundColor, list)
        assert len(ds.backgroundColor) == 4

    def test_pie_has_no_scales(self) -> None:
        policy = ChartStylePolicy()
        cfg = policy.to_config(_draft(ChartType.PIE, x="x", y="y"))
        assert "scales" not in (cfg.options or {})


class TestPreservesData:
    def test_labels_and_values_passthrough(self) -> None:
        policy = ChartStylePolicy()
        draft = _draft(ChartType.LINE, n_labels=3)
        cfg = policy.to_config(draft)
        assert cfg.type == ChartType.LINE
        assert cfg.data.labels == draft.labels
        assert cfg.data.datasets[0].data == draft.series[0].data
