"""AgentRun application 레이어 예외 (M4).

router 단에서 HTTP status code로 매핑된다:
- RunNotFoundError    -> 404
- RunAccessDeniedError -> 403
"""


class RunNotFoundError(LookupError):
    """존재하지 않는 run_id."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run not found: {run_id}")
        self.run_id = run_id


class RunAccessDeniedError(PermissionError):
    """run 존재하나 본인 아님 + non-admin."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Access denied for run: {run_id}")
        self.run_id = run_id


class MessageNotFoundError(LookupError):
    """존재하지 않는 conversation_message id (retrieval-observability §4.6)."""

    def __init__(self, message_id: int) -> None:
        super().__init__(f"Message not found: {message_id}")
        self.message_id = message_id


class MessageAccessDeniedError(PermissionError):
    """메시지 존재하나 본인 아님 + non-admin (retrieval-observability §4.6)."""

    def __init__(self, message_id: int) -> None:
        super().__init__(f"Access denied for message: {message_id}")
        self.message_id = message_id
