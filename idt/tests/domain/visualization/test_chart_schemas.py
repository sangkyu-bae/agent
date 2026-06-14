"""ChartConfig 계약 스키마 테스트. Domain: 순수 단위테스트."""
from src.domain.visualization.chart_schemas import (
    ChartConfig,
    ChartData,
    ChartDataset,
    ChartType,
)


class TestChartType:
    """프론트 SUPPORTED_CHART_TYPES와 동일한 화이트리스트여야 한다."""

    def test_whitelist_matches_frontend(self) -> None:
        # idt_front/src/types/chart.ts SUPPORTED_CHART_TYPES
        expected = {"bar", "line", "pie", "doughnut", "scatter", "radar"}
        assert {t.value for t in ChartType} == expected


class TestChartConfigDump:
    """model_dump 결과가 프론트 ChartPayload 구조와 일치해야 한다."""

    def test_dump_structure(self) -> None:
        cfg = ChartConfig(
            type=ChartType.BAR,
            data=ChartData(
                labels=["1월", "2월"],
                datasets=[ChartDataset(label="매출", data=[100.0, 130.0])],
            ),
            options={"responsive": True},
        )
        dumped = cfg.model_dump(exclude_none=True)
        assert dumped["type"] == "bar"
        assert dumped["data"]["labels"] == ["1월", "2월"]
        assert dumped["data"]["datasets"][0]["label"] == "매출"
        assert dumped["data"]["datasets"][0]["data"] == [100.0, 130.0]
        assert dumped["options"] == {"responsive": True}

    def test_exclude_none_drops_empty_color_keys(self) -> None:
        cfg = ChartConfig(
            type=ChartType.LINE,
            data=ChartData(
                labels=["a"],
                datasets=[ChartDataset(label="s", data=[1.0])],
            ),
        )
        dumped = cfg.model_dump(exclude_none=True)
        ds = dumped["data"]["datasets"][0]
        assert "backgroundColor" not in ds
        assert "borderColor" not in ds
        assert "options" not in dumped

    def test_empty_datasets_allowed_at_model_level(self) -> None:
        # 모델 생성 자체는 가능 (검증/필터는 빌더 책임)
        data = ChartData(labels=[], datasets=[])
        assert data.datasets == []
