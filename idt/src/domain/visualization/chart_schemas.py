"""Chart.js 네이티브 계약 스키마.

프론트 `idt_front/src/types/chart.ts`의 `ChartPayload`와 1:1 대응한다.
`ChartConfig.model_dump()` 결과가 그대로 `new Chart(ctx, config)`의 입력이 된다.

chart-builder Design §3.1.
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel


class ChartType(str, Enum):
    """프론트 SUPPORTED_CHART_TYPES와 동일 화이트리스트."""

    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    DOUGHNUT = "doughnut"
    SCATTER = "scatter"
    RADAR = "radar"


class ChartDataset(BaseModel):
    """Chart.js dataset. 색상은 백엔드(ChartStylePolicy)가 채운다."""

    label: str
    data: list[float]
    backgroundColor: str | list[str] | None = None
    borderColor: str | None = None


class ChartData(BaseModel):
    """Chart.js data 블록."""

    labels: list[str]
    datasets: list[ChartDataset]


class ChartConfig(BaseModel):
    """= 프론트 ChartPayload. title·축 라벨은 options에 포함."""

    type: ChartType
    data: ChartData
    options: dict[str, Any] | None = None
