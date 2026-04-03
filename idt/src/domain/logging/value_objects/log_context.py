"""LogContext Value Object.

로깅에 필요한 컨텍스트 정보를 담는 불변 객체입니다.
"""

from dataclasses import dataclass, field
from typing import Any
import uuid


@dataclass(frozen=True)
class LogContext:
    """로그 컨텍스트 Value Object.

    모든 로그에 포함될 컨텍스트 정보를 담습니다.
    불변(immutable) 객체입니다.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str | None = None
    session_id: str | None = None
    endpoint: str | None = None
    method: str | None = None
    extra: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """컨텍스트를 딕셔너리로 변환.

        None 값은 제외됩니다.

        Returns:
            컨텍스트 정보를 담은 딕셔너리
        """
        result = {"request_id": self.request_id}

        if self.user_id is not None:
            result["user_id"] = self.user_id
        if self.session_id is not None:
            result["session_id"] = self.session_id
        if self.endpoint is not None:
            result["endpoint"] = self.endpoint
        if self.method is not None:
            result["method"] = self.method
        if self.extra is not None:
            result.update(self.extra)

        return result
