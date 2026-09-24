"""ToolIdFormatPolicy / ToolCategoryPolicy: tool_id 포맷·분류 검증."""
import re

from src.domain.tool_catalog.mcp_tool_id import parse_mcp_tool_id


class ToolIdFormatPolicy:
    INTERNAL_PATTERN = re.compile(r"^internal:[a-z_]+$")
    MCP_PATTERN = re.compile(
        r"^mcp:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:.+$"
    )

    @staticmethod
    def validate(tool_id: str, source: str) -> None:
        if source == "internal":
            if not ToolIdFormatPolicy.INTERNAL_PATTERN.match(tool_id):
                raise ValueError(
                    f"Internal tool_id must match 'internal:<snake_case>', got: {tool_id!r}"
                )
        elif source == "mcp":
            if not ToolIdFormatPolicy.MCP_PATTERN.match(tool_id):
                raise ValueError(
                    f"MCP tool_id must match 'mcp:<uuid>:<name>', got: {tool_id!r}"
                )
        else:
            raise ValueError(f"Unknown source: {source!r}")


class ToolCategoryPolicy:
    """도구 카테고리·호출 상한 도메인 규칙.

    Design Ref: mcp-tool-category-routing §3.1 (FR-02) / §5 D-04 —
    워커 노드 종류를 결정하는 분류의 단일 검증 지점. None(미분류)은
    이 사이클 이전과 동일한 react 경로를 의미하므로 항상 유효하다 (FR-14).
    """

    SEARCH = "search"
    COLLECT = "collect"
    ANALYSIS = "analysis"
    ACTION = "action"
    ALLOWED = frozenset({SEARCH, COLLECT, ANALYSIS, ACTION})

    # 워커 1회 실행당 도구 호출 상한의 허용 구간.
    # 해석(기본값 적용)은 ToolCallBudgetPolicy가, 저장 검증은 여기가 담당한다.
    MIN_TOOL_CALLS = 1
    MAX_TOOL_CALLS = 20

    @classmethod
    def validate(cls, category: str | None) -> None:
        """카테고리 값 검증. None(미분류)은 허용.

        Args:
            category: 검증할 카테고리 값

        Raises:
            ValueError: 허용값 밖이거나 문자열이 아닌 경우
        """
        if category is None:
            return
        if not isinstance(category, str) or category not in cls.ALLOWED:
            raise ValueError(
                f"category must be one of {sorted(cls.ALLOWED)} or None, "
                f"got: {category!r}"
            )

    @classmethod
    def assert_assignable(cls, category: str | None, tool_id: str) -> None:
        """도구에 해당 카테고리를 지정할 수 있는지 검증한다.

        Design Ref: §5 D-04 — collect는 도구를 정확히 1회 호출하는 단일샷
        계약이다. 서버 단위 레거시 참조(`mcp_{server}`)는 ToolFactory가
        서버의 도구 '전체'를 워커에 바인딩하므로 무엇을 1회 호출한다는
        말 자체가 성립하지 않는다. 조용한 오동작 대신 지정 시점에 막는다.

        Args:
            category: 지정하려는 카테고리
            tool_id: 대상 도구 id

        Raises:
            ValueError: 카테고리가 허용값 밖이거나, collect를 서버 단위
                참조에 지정하려는 경우
        """
        cls.validate(category)
        # action-category-compose-node FR-03: action도 "작성 1회 → 도구 1회 호출"
        # 단일샷 계약이라 collect와 같은 제약을 받는다.
        if category not in (cls.COLLECT, cls.ACTION):
            return
        ref = parse_mcp_tool_id(tool_id)
        if ref is not None and ref.is_server_level:
            raise ValueError(
                f"{category} category requires a single-tool reference "
                f"('mcp:<server>:<tool>' or an internal tool), got: {tool_id!r}"
            )

    @classmethod
    def validate_tool_call_limit(cls, max_tool_calls: int | None) -> None:
        """호출 상한 값 검증. None(정책 기본값 사용)은 허용.

        Args:
            max_tool_calls: 검증할 상한 값

        Raises:
            ValueError: 정수가 아니거나 허용 구간을 벗어난 경우
        """
        if max_tool_calls is None:
            return
        # bool은 int의 하위형이라 isinstance를 통과한다 — 상한 값으로는 무의미.
        if isinstance(max_tool_calls, bool) or not isinstance(max_tool_calls, int):
            raise ValueError(
                f"max_tool_calls must be an int or None, got: {max_tool_calls!r}"
            )
        if not cls.MIN_TOOL_CALLS <= max_tool_calls <= cls.MAX_TOOL_CALLS:
            raise ValueError(
                f"max_tool_calls must be between {cls.MIN_TOOL_CALLS} and "
                f"{cls.MAX_TOOL_CALLS}, got: {max_tool_calls}"
            )
