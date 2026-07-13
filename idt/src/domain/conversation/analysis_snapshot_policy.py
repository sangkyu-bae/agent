"""분석 원천 데이터 스냅샷의 스키마·상한·선별·렌더 규칙 (순수 도메인, 외부 의존 0).

analysis-data-continuity Design §3.1 (D1):
- 스냅샷 = 한 턴의 분석에 사용된 원천 데이터 묶음. assistant 메시지의
  analysis_data(JSON)로 영속되고, 다음 턴 컨텍스트에 재주입된다.
- 복원은 최근 윈도우가 아니라 세션 전체 히스토리 역순 스캔 (compact 공존).
- 재주입분은 REINJECTED_MARKER로 식별해 다음 턴 수집에서 제외한다.
"""
from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.value_objects import MessageRole

# 재주입 본문 식별자 — 재캡처(스냅샷 앞으로 복사) 방지 (Design §2.2)
REINJECTED_MARKER = "(이전 턴 수집 데이터)"

_QUESTION_MAX_CHARS = 200
_CONTEXT_BLOCK_HEADER = "[이전 분석 데이터]"


class AnalysisSnapshotPolicy:
    """스냅샷 빌드(절단·상한) / 선별(최신 N·누적 캡) / 재주입 렌더 규칙."""

    # analysis-source-preservation: 원천(raw_source) 항목 식별 kind.
    RAW_SOURCE_KIND = "raw_source"

    def __init__(
        self,
        item_max_chars: int = 4000,
        total_max_chars: int = 8000,
        retention: int = 2,
        raw_source_max_chars: int = 6000,
        raw_source_total_max_chars: int = 8000,
        raw_source_max_rows: int = 200,
    ) -> None:
        self._item_max_chars = item_max_chars
        self._total_max_chars = total_max_chars
        self._retention = retention
        # analysis-source-preservation: raw_source는 비-raw와 독립 budget으로 상한한다
        # (기존 analysis-data-continuity 동작 불변).
        self._raw_source_max_chars = raw_source_max_chars
        self._raw_source_total_max_chars = raw_source_total_max_chars
        self._raw_source_max_rows = raw_source_max_rows

    def build_snapshot(self, question: str, items: list[dict]) -> dict | None:
        """수집 항목 → 스냅샷 dict. 유효 항목 0개면 None (엔티티 규칙과 일치).

        - 빈/공백 content 항목 제거, kind별 상한 절단(truncated 표기)
        - kind별 독립 budget 누적 도달 시 해당 kind 이후 항목 드롭
          (raw_source vs 그 외 — raw가 기존 항목 budget을 잠식하지 않음)
        """
        built: list[dict] = []
        total = 0
        raw_total = 0
        for item in items:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            kind = str(item.get("kind", ""))
            is_raw = kind == self.RAW_SOURCE_KIND
            cap = self._raw_source_max_chars if is_raw else self._item_max_chars
            budget = (
                self._raw_source_total_max_chars if is_raw
                else self._total_max_chars
            )
            truncated = len(content) > cap
            content = content[:cap]
            used = raw_total if is_raw else total
            if used + len(content) > budget:
                continue
            if is_raw:
                raw_total += len(content)
            else:
                total += len(content)
            built.append(
                {
                    "origin": str(item.get("origin", "")),
                    "kind": kind,
                    "content": content,
                    "truncated": truncated,
                }
            )
        if not built:
            return None
        return {
            "version": 1,
            "question": (question or "")[:_QUESTION_MAX_CHARS],
            "items": built,
        }

    def render_raw_source(self, excel: dict) -> str | None:
        """ExcelData.to_dict() → 압축 표 텍스트 (행 샘플링 + 상한). 무효 시 None.

        형식:
          [원천 데이터: vac.xlsx]
          # 시트 Sheet1 (12행 × 3열)
          월,사용일수,잔여
          1월,1.0,14
          ... (총 12행 중 2행)
        """
        sheets = (excel or {}).get("sheets")
        if not isinstance(sheets, dict) or not sheets:
            return None
        filename = str((excel or {}).get("filename", "")) or "(파일)"
        lines: list[str] = [f"[원천 데이터: {filename}]"]
        for name, sheet in sheets.items():
            if not isinstance(sheet, dict):
                continue
            columns = sheet.get("columns") or []
            rows = sheet.get("data") or []
            total_rows = sheet.get("row_count", len(rows))
            shown = rows[: self._raw_source_max_rows]
            lines.append(
                f"# 시트 {name} ({total_rows}행 × {len(columns)}열)"
            )
            lines.append(",".join(str(c) for c in columns))
            for row in shown:
                lines.append(
                    ",".join(str(row.get(c, "")) for c in columns)
                )
            if len(shown) < total_rows:
                lines.append(f"... (총 {total_rows}행 중 {len(shown)}행)")
        body = "\n".join(lines)
        if len(body) <= 1:
            return None
        return body[: self._raw_source_max_chars]

    def select_recent(self, messages: list[ConversationMessage]) -> list[dict]:
        """turn_index 역순 전체 스캔 → 최신 retention개 (반환은 오래된 것 → 최신).

        누적 크기 상한 초과 시 오래된 스냅샷을 드롭한다(최신 우선, Plan 제약 3).
        analysis-source-preservation: raw_source와 비-raw를 **독립 budget**으로 누적
        해 원천이 비-raw 재주입 선별을 잠식하지 않게 한다(Design §3.3, build_snapshot 동형).
        """
        selected: list[dict] = []
        non_raw_total = 0
        raw_total = 0
        for msg in sorted(
            messages, key=lambda m: m.turn_index.value, reverse=True
        ):
            if len(selected) >= self._retention:
                break
            if msg.role != MessageRole.ASSISTANT or not msg.analysis_data:
                continue
            non_raw, raw = self._snapshot_sizes(msg.analysis_data)
            if selected and (
                non_raw_total + non_raw > self._total_max_chars
                or raw_total + raw > self._raw_source_total_max_chars
            ):
                break
            non_raw_total += non_raw
            raw_total += raw
            selected.append(msg.analysis_data)
        return list(reversed(selected))

    def render_reinjection_body(self, snapshot: dict, item: dict) -> str:
        """재주입 본문 — format_search_result(item["origin"], body)로 감싸 사용."""
        return (
            f"{REINJECTED_MARKER} (질문: {snapshot.get('question', '')})\n"
            f"{item.get('content', '')}"
        )

    def render_context_block(self, snapshots: list[dict]) -> str:
        """General Chat용 system 블록. 스냅샷 없으면 ""."""
        sections: list[str] = []
        for snap in snapshots:
            body = "\n\n".join(
                f"[{it.get('origin', '')}]\n{it.get('content', '')}"
                for it in snap.get("items", [])
            )
            sections.append(f"(질문: {snap.get('question', '')})\n{body}")
        if not sections:
            return ""
        joined = "\n\n---\n\n".join(sections)
        return f"{_CONTEXT_BLOCK_HEADER}\n{joined}"

    @staticmethod
    def is_reinjected(content: str) -> bool:
        """재주입 메시지 판정 — 수집(재캡처)에서 제외하기 위한 식별."""
        return REINJECTED_MARKER in (content or "")

    @classmethod
    def _snapshot_sizes(cls, snapshot: dict) -> tuple[int, int]:
        """스냅샷의 (비-raw 문자수, raw_source 문자수) — kind별 독립 누적용."""
        non_raw = 0
        raw = 0
        for it in snapshot.get("items", []):
            size = len(it.get("content", ""))
            if it.get("kind") == cls.RAW_SOURCE_KIND:
                raw += size
            else:
                non_raw += size
        return non_raw, raw
