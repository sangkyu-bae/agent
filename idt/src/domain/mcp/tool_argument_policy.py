"""MCP 도구 인자에 대한 도메인 규칙.

Design Ref: worker-context-injection §3.2 —
워커 LLM이 에이전트 프롬프트·역할·작업 지시를 잃은 채 도구를 호출하면
`https://www.example.com/...` 같은 문서용 예시 주소를 지어내 MCP 서버로 보낸다.
근거 없는 인자는 서버에 도달하기 전에 여기서 판정한다.

domain 레이어 — 외부 의존성 없음.
"""

from __future__ import annotations

from urllib.parse import urlparse


class ToolArgumentPolicy:
    """LLM이 지어낸 플레이스홀더 인자를 판정한다."""

    # 문서·예제에서만 쓰이는 예약 호스트. 실제 스크래핑 대상일 수 없다.
    # Design Ref: §3.2 — localhost/127.0.0.1 은 사내 로컬 대상 스크래핑
    # 오탐 위험이 실익보다 커서 의도적으로 제외한다.
    PLACEHOLDER_HOSTS: frozenset[str] = frozenset({
        "example.com",
        "example.org",
        "example.net",
        "example.edu",
        "test.com",
        "sample.com",
        "your-domain.com",
        "yourdomain.com",
        "domain.com",
        "site.com",
        "url.com",
    })

    # 중첩 dict/list 순회 상한. 초과분은 조용히 무시한다(예외 금지).
    MAX_SCAN_DEPTH = 4

    # worker-context-injection §6.2 (FR-09): 차단 응답의 식별 접두어.
    # 상위 레이어(워커 노드)가 이 접두어로 차단을 감지해 run step에 반영한다.
    # infrastructure가 application을 참조하지 않고도 관측이 성립하는 접점.
    BLOCKED_PREFIX = "[도구 호출이 차단되었습니다]"

    _URL_SCHEMES = ("http", "https")

    @staticmethod
    def is_placeholder_url(value: str) -> bool:
        """문자열이 URL이고 호스트가 예약 호스트(또는 그 서브도메인)면 True.

        Args:
            value: 검사할 문자열

        Returns:
            플레이스홀더 URL이면 True
        """
        if not isinstance(value, str) or not value.strip():
            return False
        try:
            parsed = urlparse(value.strip())
        except ValueError:
            return False
        if parsed.scheme.lower() not in ToolArgumentPolicy._URL_SCHEMES:
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        return ToolArgumentPolicy._matches_reserved_host(host)

    @staticmethod
    def find_placeholder(arguments: dict | None) -> str | None:
        """인자 트리에서 플레이스홀더 URL을 찾는다.

        도구마다 URL 필드명이 다르므로 필드명에 의존하지 않고 값 전체를 순회한다.

        Args:
            arguments: 도구 실행 인자 (None 허용)

        Returns:
            발견한 플레이스홀더 URL. 없으면 None.
        """
        if not arguments:
            return None
        return ToolArgumentPolicy._scan(arguments, depth=0)

    @staticmethod
    def build_blocked_message(blocked_value: str) -> str:
        """차단 시 워커 LLM에게 되돌려줄 지시성 오류 문자열.

        예외가 아닌 문자열을 반환해야 ToolMessage로 감싸여 react 루프에 돌아가고,
        워커가 스스로 교정할 기회를 얻는다.

        Args:
            blocked_value: 차단된 인자 값

        Returns:
            워커가 다음 행동을 정할 수 있는 안내 문구
        """
        return (
            f"{ToolArgumentPolicy.BLOCKED_PREFIX}\n"
            f"인자에 실재하지 않는 예시 주소가 포함되어 있습니다: {blocked_value}\n"
            "추측한 URL로는 도구를 호출할 수 없습니다.\n"
            "대화 내용이나 이전 단계 결과에서 확인된 대상만 사용하고, "
            "확인된 대상이 없다면 도구를 다시 호출하지 말고 "
            "어떤 정보가 필요한지 답변에 밝히세요."
        )

    @staticmethod
    def is_blocked_message(text: object) -> bool:
        """텍스트가 이 정책이 만든 차단 응답인지 판정한다 (FR-09).

        Args:
            text: 도구 응답 텍스트 (문자열이 아니면 False)

        Returns:
            차단 응답이면 True
        """
        if not isinstance(text, str):
            return False
        return text.startswith(ToolArgumentPolicy.BLOCKED_PREFIX)

    @staticmethod
    def _matches_reserved_host(host: str) -> bool:
        """정확 일치 또는 서브도메인 일치만 인정 — 부분 문자열 매칭 금지."""
        if host in ToolArgumentPolicy.PLACEHOLDER_HOSTS:
            return True
        return any(
            host.endswith(f".{reserved}")
            for reserved in ToolArgumentPolicy.PLACEHOLDER_HOSTS
        )

    @staticmethod
    def _scan(node: object, depth: int) -> str | None:
        """인자 트리를 깊이 우선으로 순회하며 첫 플레이스홀더를 찾는다."""
        if depth > ToolArgumentPolicy.MAX_SCAN_DEPTH:
            return None
        if isinstance(node, str):
            return node if ToolArgumentPolicy.is_placeholder_url(node) else None
        if isinstance(node, dict):
            values = node.values()
        elif isinstance(node, (list, tuple, set)):
            values = node
        else:
            return None
        for value in values:
            found = ToolArgumentPolicy._scan(value, depth + 1)
            if found is not None:
                return found
        return None
