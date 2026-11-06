"""PlaceholderStreamRestorer: 토큰 스트림의 placeholder 원복.

Design Ref: pii-masking-integration §4.5 (FR-09) — 미들웨어는 토큰 이벤트를
가로채지 못한다. 스파이크에서 `[PHONE_1]`이 `[PH`, `ONE`, `_1]`로 나뉘어 화면에
흘렀다. 이벤트 매핑 직전에 LLM 호출(run_id)별 버퍼로 접두를 보류했다가 원복한다.
병렬 워커의 토큰이 섞이므로 버퍼는 반드시 호출 단위로 나눈다.
"""

from __future__ import annotations

from src.application.pii_masking.pii_masking_service import PiiMaskingService
from src.domain.pii_masking.policies import PlaceholderStreamPolicy
from src.domain.pii_masking.schemas import PiiMaskingMode, PiiRunScope


class PlaceholderStreamRestorer:
    """런 1개에서 쓰는 지역 객체. 보류 중인 꼬리만 들고 있다."""

    def __init__(self, service: PiiMaskingService, scope: PiiRunScope) -> None:
        self._service = service
        self._scope = scope
        self._pending: dict[str, str] = {}

    def feed(self, key: str, chunk: str) -> str:
        """청크를 받아 지금 내보내도 되는 원복 텍스트를 돌려준다."""
        if self._scope.mode is PiiMaskingMode.SHADOW:
            return chunk
        buffer = self._pending.pop(key, "") + chunk
        hold = PlaceholderStreamPolicy.hold_start(buffer)
        if hold is not None:
            self._pending[key] = buffer[hold:]
            buffer = buffer[:hold]
        return self._service.restore_text(buffer, self._scope)

    def flush(self, key: str) -> str:
        """호출이 끝나면 남은 꼬리를 원복해 내보낸다. 미완성 접두는 그대로 나간다."""
        tail = self._pending.pop(key, "")
        return self._service.restore_text(tail, self._scope)

    def restore(self, text: str) -> str:
        """한 번에 받은 완성 텍스트(추론 이벤트 등)를 원복한다. 버퍼는 쓰지 않는다."""
        return self._service.restore_text(text, self._scope)
