"""도구 권한 예외.

Design Ref: tool-access-control §4.2, §6.1
- ToolAccessDeniedError: PermissionError 하위형 — 라우터는 기존 `except PermissionError`
  보다 먼저 잡아 403 TOOL_ACCESS_DENIED + tool_ids 로 응답한다.
- UnknownToolIdsError: 관리자 PUT 에 카탈로그(활성)에 없는 id → 400.
"""
from collections.abc import Iterable


class ToolAccessDeniedError(PermissionError):
    def __init__(self, tool_ids: Iterable[str]) -> None:
        self.tool_ids: tuple[str, ...] = tuple(sorted(set(tool_ids)))
        super().__init__(f"권한이 없는 도구가 포함되어 있습니다: {list(self.tool_ids)}")


class UnknownToolIdsError(ValueError):
    def __init__(self, tool_ids: Iterable[str]) -> None:
        self.tool_ids: tuple[str, ...] = tuple(sorted(set(tool_ids)))
        super().__init__(f"카탈로그에 없는 도구입니다: {list(self.tool_ids)}")
