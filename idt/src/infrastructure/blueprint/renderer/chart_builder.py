"""네이티브 차트 빌더 — ChartSpec → python-pptx chart (Design D6: bar/line/pie).

팔레트 적용: 시리즈 i 색 = accent1, accent2, …, primary 순환. 파이는 포인트별 색.
"""

from __future__ import annotations

from collections.abc import Sequence

from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

from src.domain.blueprint.value_objects import ChartSpec

_TYPES = {
    "bar": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "pie": XL_CHART_TYPE.PIE,
}


def rgb(hex_color: str) -> RGBColor:
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def series_colors(palette: dict[str, str]) -> list[str]:
    accents = [palette[k] for k in sorted(palette) if k.startswith("accent")]
    return accents + [palette["primary"]]


def add_chart(
    slide, box_emu: tuple[int, int, int, int], spec: ChartSpec, palette: dict[str, str]
):
    data = CategoryChartData()
    data.categories = list(spec.categories)
    for name, values in spec.series:
        data.add_series(name, list(values))
    x, y, w, h = box_emu
    chart = slide.shapes.add_chart(_TYPES[spec.type], x, y, w, h, data).chart
    colors = series_colors(palette)
    if spec.type == "pie":
        _color_points(chart, colors)
    else:
        _color_series(chart, colors)
    chart.has_legend = len(spec.series) > 1 or spec.type == "pie"
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
    return chart


def _color_series(chart, colors: Sequence[str]) -> None:
    for i, series in enumerate(chart.plots[0].series):
        fill = series.format.fill
        fill.solid()
        fill.fore_color.rgb = rgb(colors[i % len(colors)])
        series.format.line.color.rgb = rgb(colors[i % len(colors)])


def _color_points(chart, colors: Sequence[str]) -> None:
    series = chart.plots[0].series[0]
    for i, point in enumerate(series.points):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = rgb(colors[i % len(colors)])
