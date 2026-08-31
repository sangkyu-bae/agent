"""표 셀 테두리 — python-pptx 가 지원하지 않아 oxml 을 직접 다룬다.

Design Ref: blueprint-render-style-fidelity DR-3 / §13.1
- `cell.border_left/right/top/bottom` 이 python-pptx 에 없다(실측 확인). 각 셀의
  `a:tcPr` 에 `a:lnL/lnR/lnT/lnB` 를 직접 넣는 수밖에 없다.
- **이 파일과 run_fonts.py 만 oxml 을 만진다** — 나머지 렌더러는 python-pptx API
  만 쓴다. AST 계약 테스트가 이 규칙을 고정한다.
"""

from __future__ import annotations

from pptx.oxml.ns import qn

_SIDES = ("a:lnL", "a:lnR", "a:lnT", "a:lnB")
_EMU_PER_POINT = 12700
# a:tcPr 안에서 선 요소는 다른 자식보다 앞에 와야 한다 (스키마 순서)
_LINE_INSERT_INDEX = 0


def apply_borders(table, color: str, width_pt: float) -> None:
    """표 전 셀의 네 변에 테두리를 그린다. width_pt <= 0 이면 아무것도 하지 않는다."""
    if width_pt <= 0:
        return  # FR-07: 기본값(0)이면 현행 동작 — 테두리 없음
    width_emu = str(int(width_pt * _EMU_PER_POINT))
    value = color.lstrip("#").upper()
    for row in table.rows:
        for cell in row.cells:
            _set_cell_borders(cell, value, width_emu)


def _set_cell_borders(cell, srgb_value: str, width_emu: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for side in _SIDES:
        _replace_line(tc_pr, side, srgb_value, width_emu)


def _replace_line(tc_pr, side: str, srgb_value: str, width_emu: str) -> None:
    """기존 선을 지우고 새로 넣는다 — 반복 적용해도 요소가 늘지 않는다."""
    for existing in tc_pr.findall(qn(side)):
        tc_pr.remove(existing)
    line = tc_pr.makeelement(qn(side), {"w": width_emu, "cap": "flat"})
    fill = line.makeelement(qn("a:solidFill"), {})
    fill.append(fill.makeelement(qn("a:srgbClr"), {"val": srgb_value}))
    line.append(fill)
    tc_pr.insert(_LINE_INSERT_INDEX, line)
