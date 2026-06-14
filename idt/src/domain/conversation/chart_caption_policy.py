"""저장된 차트 메타 → 컨텍스트용 캡션 변환 규칙 (순수 도메인, 외부 의존 0).

chart-context-continuity Design §3.1 (D1, D7-rev1):
- full config는 LLM 컨텍스트에 미투입, 캡션 1줄만 투입한다.
- 파싱 실패는 모두 빈 문자열로 graceful degrade (본 답변 흐름 보호).
"""


class ChartCaptionPolicy:
    """charts(list[dict], ChartConfig.model_dump 동형) → 1줄 캡션."""

    MAX_CHARTS = 2
    MAX_LABELS = 5
    MAX_LEN = 200

    def build_caption(self, charts: list[dict]) -> str:
        """예: '[생성된 차트: bar "부서별 대출 건수" (labels: 영업,심사 | series: 건수)]'

        charts가 비었거나 전부 기형이면 "" 반환.
        """
        parts = [p for p in (self._describe(c) for c in charts or []) if p]
        if not parts:
            return ""
        shown = parts[: self.MAX_CHARTS]
        body = "; ".join(shown)
        extra = len(parts) - len(shown)
        if extra > 0:
            body += f" 외 {extra}개"
        caption = f"[생성된 차트: {body}]"
        if len(caption) > self.MAX_LEN:
            caption = caption[: self.MAX_LEN - 1] + "]"
        return caption

    def _describe(self, chart: object) -> str:
        """차트 1개 요약. 기형이면 ""."""
        if not isinstance(chart, dict):
            return ""
        chart_type = chart.get("type")
        data = chart.get("data")
        if not isinstance(chart_type, str) or not isinstance(data, dict):
            return ""
        head = chart_type
        title = self._extract_title(chart)
        if title:
            head += f' "{title}"'
        details = self._describe_details(data)
        return f"{head} ({details})" if details else head

    def _describe_details(self, data: dict) -> str:
        fragments = []
        labels = data.get("labels")
        if isinstance(labels, list) and labels:
            shown = ",".join(str(lb) for lb in labels[: self.MAX_LABELS])
            if len(labels) > self.MAX_LABELS:
                shown += f" 외 {len(labels) - self.MAX_LABELS}"
            fragments.append(f"labels: {shown}")
        datasets = data.get("datasets")
        if isinstance(datasets, list):
            names = [
                str(ds.get("label"))
                for ds in datasets
                if isinstance(ds, dict) and ds.get("label")
            ]
            if names:
                fragments.append(f"series: {','.join(names)}")
        return " | ".join(fragments)

    @staticmethod
    def _extract_title(chart: dict) -> str:
        options = chart.get("options")
        if not isinstance(options, dict):
            return ""
        plugins = options.get("plugins")
        if not isinstance(plugins, dict):
            return ""
        title = plugins.get("title")
        if not isinstance(title, dict):
            return ""
        return str(title.get("text") or "")
