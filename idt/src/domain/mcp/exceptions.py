"""MCP 도메인 예외.

Design Ref: fix-mcp-tool-call-not-reaching-server §6.2
"""


class McpWiringError(ValueError):
    """MCP 의존(로더/저장소)이 주입되지 않은 배선 오류.

    워커 단위 실패 격리에서 **제외**되어야 하는 오류를 구분하기 위한 타입이다.
    서버 장애·도구 부재는 워커 하나만 스킵하면 되지만, 배선 누락은 개발자
    실수이며 조용히 넘어가면 "도구를 호출했는데 아무 일도 없다"는 이 사이클의
    실패 모드가 그대로 재발한다 — 즉시 드러나야 한다.

    기존 ValueError 기반 처리(라우터 매핑 등)와 호환되도록 ValueError를 상속한다.
    """
