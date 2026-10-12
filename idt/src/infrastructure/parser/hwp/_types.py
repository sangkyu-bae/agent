"""한글 문서 리더 내부 계약과 공통 표 표기 (hwp-parser Design §3.1, §3.3).

HWP 5.0·HWPX 리더가 같은 표 표기를 쓰도록 렌더링을 여기 한 곳에 둔다.
"""
from typing import Protocol

CELL_SEPARATOR = " | "


class HwpSectionReader(Protocol):
    def read_sections(self, data: bytes) -> list[str]:
        """문서 순서대로 섹션별 텍스트를 돌려준다. 실패 시 HwpParseError 계열."""
        ...


def render_table(rows: list[list[str]]) -> str:
    """셀은 " | ", 행은 줄바꿈으로 잇는다. 빈 행은 버린다."""
    lines = [CELL_SEPARATOR.join(cells) for cells in rows if any(cells)]
    return "\n".join(lines)


def join_blocks(blocks: list[str]) -> str:
    """문단은 줄바꿈, 표 블록은 앞뒤 빈 줄로 구분한 섹션 텍스트를 만든다.

    표 블록은 "\\n" 접두·접미가 붙어 들어오므로, 3줄 이상 연속 개행만 정리한다.
    """
    text = "\n".join(b for b in blocks if b.strip())
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()
