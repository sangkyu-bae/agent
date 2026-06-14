"""ChartCaptionPolicy 테스트 (chart-context-continuity Design §3.1, D7-rev1)."""
from src.domain.conversation.chart_caption_policy import ChartCaptionPolicy


def _chart(
    chart_type: str = "bar",
    title: str | None = "부서별 대출 건수",
    labels: list[str] | None = None,
    series: list[str] | None = None,
) -> dict:
    """저장된 charts(JSON dict) 형태 — ChartConfig.model_dump 결과와 동형."""
    options: dict = {"responsive": True}
    if title:
        options["plugins"] = {"title": {"display": True, "text": title}}
    return {
        "type": chart_type,
        "data": {
            "labels": labels if labels is not None else ["영업", "심사", "관리"],
            "datasets": [
                {"label": name, "data": [1.0, 2.0, 3.0]}
                for name in (series or ["건수"])
            ],
        },
        "options": options,
    }


class TestBuildCaption:
    def setup_method(self) -> None:
        self.policy = ChartCaptionPolicy()

    def test_single_chart_caption_format(self) -> None:
        caption = self.policy.build_caption([_chart()])
        assert caption.startswith("[생성된 차트:")
        assert caption.endswith("]")
        assert "bar" in caption
        assert "부서별 대출 건수" in caption
        assert "영업" in caption
        assert "건수" in caption

    def test_no_title_omits_quotes(self) -> None:
        caption = self.policy.build_caption([_chart(title=None)])
        assert '""' not in caption
        assert "bar" in caption

    def test_labels_truncated_to_max(self) -> None:
        labels = [f"L{i}" for i in range(8)]
        caption = self.policy.build_caption([_chart(labels=labels)])
        assert "L4" in caption       # MAX_LABELS=5 → L0~L4까지 표기
        assert "L5" not in caption
        assert "외 3" in caption      # 8 - 5 = 3

    def test_more_than_max_charts_marked(self) -> None:
        charts = [_chart(title=f"차트{i}") for i in range(3)]
        caption = self.policy.build_caption(charts)
        assert "차트0" in caption
        assert "차트1" in caption
        assert "차트2" not in caption  # MAX_CHARTS=2
        assert "외 1개" in caption

    def test_total_length_capped(self) -> None:
        charts = [
            _chart(title="제목" * 100, labels=["라벨" * 20] * 5, series=["시리즈" * 30])
        ]
        caption = self.policy.build_caption(charts)
        assert len(caption) <= ChartCaptionPolicy.MAX_LEN

    def test_empty_charts_returns_empty(self) -> None:
        assert self.policy.build_caption([]) == ""

    def test_malformed_chart_returns_empty(self) -> None:
        # dict 형식 파손 → graceful "" (예외 전파 금지)
        assert self.policy.build_caption([{"weird": True}]) == ""
        assert self.policy.build_caption(["not-a-dict"]) == ""  # type: ignore[list-item]

    def test_malformed_mixed_with_valid_keeps_valid(self) -> None:
        caption = self.policy.build_caption([{"weird": True}, _chart()])
        assert "bar" in caption
