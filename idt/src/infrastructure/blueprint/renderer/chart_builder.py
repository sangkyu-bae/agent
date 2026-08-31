"""네이티브 차트 빌더 — ChartSpec → python-pptx chart (Design D6: bar/line/pie).

팔레트 적용: 시리즈 i 색 = accent1, accent2, …, primary 순환. 파이는 포인트별 색.

blueprint-render-style-fidelity D-1·D-2:
- 데이터 레이블은 style.chart_label_size_pt 가 0 보다 클 때만 (기본값 0 = 현행).
- ChartSpec.unit 은 **리터럴 서식**으로 감싼다 (DR-4). '0.00%' 는 백분율 변환이라
  1.62 가 162.00% 로 표시된다.
- pie 는 value_axis 접근이 ValueError 이므로 레이블에만 적용한다 (DR-5).
"""

from __future__ import annotations

from collections.abc import Sequence

from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.util import Pt

from src.domain.blueprint.value_objects import ChartSpec, StyleTokens

_TYPES = {
    "bar": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "pie": XL_CHART_TYPE.PIE,
}
# DR-6: 차트 종류별 레이블 위치 (실측 확인 — 설계 §13.1)
_LABEL_POSITIONS = {
    "bar": XL_LABEL_POSITION.OUTSIDE_END,
    "line": XL_LABEL_POSITION.ABOVE,
    "pie": XL_LABEL_POSITION.OUTSIDE_END,
}
_AXIS_KINDS = ("bar", "line")  # pie 는 값 축이 없다 (DR-5)
_LABEL_FORMAT = "0.00"
_AXIS_FORMAT = "0.0"


def rgb(hex_color: str) -> RGBColor:
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def series_colors(palette: dict[str, str]) -> list[str]:
    accents = [palette[k] for k in sorted(palette) if k.startswith("accent")]
    return accents + [palette["primary"]]


def add_chart(
    slide,
    box_emu: tuple[int, int, int, int],
    spec: ChartSpec,
    style: StyleTokens,
):
    """DR-9: 시그니처가 palette → style 로 바뀌었다 (레이블 스타일이 필요)."""
    data = CategoryChartData()
    data.categories = list(spec.categories)
    for name, values in spec.series:
        data.add_series(name, list(values))
    x, y, w, h = box_emu
    chart = slide.shapes.add_chart(_TYPES[spec.type], x, y, w, h, data).chart
    palette = style.palette
    colors = series_colors(palette)
    if spec.type == "pie":
        _color_points(chart, colors)
    else:
        _color_series(chart, colors)
    chart.has_legend = len(spec.series) > 1 or spec.type == "pie"
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
    _data_labels(chart, spec, style)
    _axis_format(chart, spec)
    return chart


def _data_labels(chart, spec: ChartSpec, style: StyleTokens) -> None:
    """D-1 — chart_label_size_pt 가 0 이면 아무것도 하지 않는다 (FR-07)."""
    size = style.chart_label_size_pt
    unit_format = _number_format(spec.unit, _LABEL_FORMAT)
    if size <= 0 and unit_format is None:
        return
    plot = chart.plots[0]
    plot.has_data_labels = True
    labels = plot.data_labels
    if size > 0:
        labels.font.size = Pt(size)
        labels.font.bold = style.chart_label_bold
        labels.font.color.rgb = rgb(style.palette["text"])
        labels.position = _LABEL_POSITIONS[spec.type]
    if unit_format is not None:
        labels.number_format = unit_format
        labels.number_format_is_linked = False


def _axis_format(chart, spec: ChartSpec) -> None:
    """D-2 — 값 축이 있는 종류에만. pie 는 ValueError (DR-5)."""
    if spec.type not in _AXIS_KINDS:
        return
    unit_format = _number_format(spec.unit, _AXIS_FORMAT)
    if unit_format is None:
        return
    ticks = chart.value_axis.tick_labels
    ticks.number_format = unit_format
    ticks.number_format_is_linked = False


def _number_format(unit: str | None, base: str) -> str | None:
    """FR-08 — unit 은 LLM 출력이다. 큰따옴표를 제거해 서식이 깨지지 않게 한다."""
    if not unit:
        return None
    safe = unit.replace('"', "").strip()
    if not safe:
        return None
    return f'{base}"{safe}"'


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
