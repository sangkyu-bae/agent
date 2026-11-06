"""PiiMaskingService: 외부 LLM 경계의 가역 마스킹/복원 오케스트레이션.

Design Ref: pii-masking-integration §4.1
- mask_text: PII를 placeholder로 치환 (scope.vault에 누적). shadow는 기록만 한다.
- restore_text: placeholder 원복 + 고아 placeholder 처리
- inspect: 값을 바꾸지 않고 타입별 건수만 센다 (MCP 경계)

원본 PII / vault 값은 로그에 기록하지 않는다(LOG-001). 개수만 기록한다.
on 모드의 탐지 예외는 fail-closed: 원문(PII)을 그대로 통과시키지 않는다.
shadow는 관측 단계이므로 실패해도 요청을 바꾸지 않는다.
"""
from __future__ import annotations

from collections.abc import Iterator

from src.application.pii_masking.schemas import PiiMaskingConfig
from src.domain.logging.interfaces import LoggerInterface
from src.domain.pii_masking.interfaces import PiiDetectorPort
from src.domain.pii_masking.policies import REDACT_PREFIX, PiiToolArgumentPolicy
from src.domain.pii_masking.schemas import (
    PLACEHOLDER_PATTERN,
    PiiMaskingMode,
    PiiMatch,
    PiiRunScope,
    PiiType,
)

# 탐지 실패 시 mask_text가 반환하는 안전 마커(원문 미노출).
MASK_FAILURE_PLACEHOLDER = "[PII_MASKING_FAILED]"


def _iter_strings(value: object) -> Iterator[str]:
    """중첩 dict/list의 문자열 값을 순회한다. 키는 검사하지 않는다."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_strings(item)


class PiiMaskingService:
    """PiiInspectPort 구현체이자 마스킹 코어."""

    def __init__(
        self,
        detector: PiiDetectorPort,
        logger: LoggerInterface,
        config: PiiMaskingConfig,
    ) -> None:
        self._detector = detector
        self._logger = logger
        self._config = config

    def new_scope(self) -> PiiRunScope:
        """런 1개의 범위를 만든다. 호출자가 지역 객체로 들고 다닌다."""
        return PiiRunScope(mode=self._config.mode)

    def mask_text(self, text: str, scope: PiiRunScope) -> str:
        """PII를 placeholder로 치환한 텍스트를 반환. shadow는 원문을 돌려준다."""
        if not text:
            return text
        try:
            matches = self._enabled_matches(text)
        except Exception as exc:  # noqa: BLE001 — 실패 처리가 목적
            return self._on_detection_failure(text, scope, exc)
        if scope.mode is PiiMaskingMode.SHADOW:
            for match in matches:
                scope.vault.get_or_create_placeholder(match.pii_type, match.text)
            return text
        return self._replace(text, matches, scope)

    def restore_text(self, text: str, scope: PiiRunScope) -> str:
        """placeholder를 원복하고 고아 placeholder는 redact. shadow는 그대로 둔다."""
        if not text or scope.mode is PiiMaskingMode.SHADOW:
            return text
        return self._redact_orphans(scope.vault.restore(text), scope)

    def restore_known_text(self, text: str, scope: PiiRunScope) -> str:
        """알려진 placeholder만 원복하고 고아는 남긴다. 도구 인자용.

        인자의 고아를 redact하면 `[REDACTED_EMAIL]` 같은 값으로 도구가 실행된다.
        고아를 남겨 두어야 도구 호출 직전에 has_orphan으로 차단할 수 있다.
        """
        if not text or scope.mode is PiiMaskingMode.SHADOW:
            return text
        return scope.vault.restore(text)

    def has_orphan(self, value: object, scope: PiiRunScope) -> bool:
        """도구 인자처럼 중첩된 값에 원복되지 않은 placeholder가 있는지 검사."""
        if scope.mode is PiiMaskingMode.SHADOW:
            return False
        return any(
            scope.vault.is_orphan(match.group(0))
            for text in _iter_strings(value)
            for match in PLACEHOLDER_PATTERN.finditer(text)
        )

    def inspect(self, value: object) -> dict[PiiType, int]:
        """타입별 출현 건수. 검사 실패가 호출을 막지 않도록 예외를 삼킨다."""
        counts: dict[PiiType, int] = {}
        try:
            for text in _iter_strings(value):
                for match in self._enabled_matches(text):
                    counts[match.pii_type] = counts.get(match.pii_type, 0) + 1
        except Exception as exc:  # noqa: BLE001 — Design §6.2
            self._logger.warning("PII inspect failed", exception=exc)
            return {}
        return counts

    def find_orphan_argument(self, value: object) -> str | None:
        """MCP 경계 고아 판정(D-10). shadow는 LLM에 placeholder를 보낸 적이 없으므로
        같은 모양의 문자열은 사용자 값이다 — 막지 않는다 (Check G-3, FR-12)."""
        if self._config.mode is PiiMaskingMode.SHADOW:
            return None
        return PiiToolArgumentPolicy.find_orphan(value)

    def _replace(
        self, text: str, matches: list[PiiMatch], scope: PiiRunScope
    ) -> str:
        """입력에 있던 placeholder 형태 문자열을 예약한 뒤 뒤에서부터 치환."""
        scope.vault.reserve_literals(text)
        result = text
        for match in sorted(matches, key=lambda m: m.start, reverse=True):
            placeholder = scope.vault.get_or_create_placeholder(
                match.pii_type, match.text
            )
            result = result[: match.start] + placeholder + result[match.end :]
        if matches:
            self._logger.info("PII masked", masked_count=len(matches))
        return result

    def _on_detection_failure(
        self, text: str, scope: PiiRunScope, exc: Exception
    ) -> str:
        if scope.mode is PiiMaskingMode.SHADOW:
            self._logger.warning("PII detection failed in shadow mode", exception=exc)
            return text
        self._logger.error("PII detection failed; failing closed", exception=exc)
        return MASK_FAILURE_PLACEHOLDER

    def _redact_orphans(self, text: str, scope: PiiRunScope) -> str:
        """vault로 복원되지 않은 placeholder를 [REDACTED_<TYPE>]로 대체."""
        orphan_count = 0

        def _replace(match) -> str:
            nonlocal orphan_count
            if not scope.vault.is_orphan(match.group(0)):
                return match.group(0)
            orphan_count += 1
            return f"[{REDACT_PREFIX}_{match.group(1).upper()}]"

        result = PLACEHOLDER_PATTERN.sub(_replace, text)
        if orphan_count:
            self._logger.warning(
                "Orphan placeholders redacted", orphan_count=orphan_count
            )
        return result

    def _enabled_matches(self, text: str) -> list[PiiMatch]:
        """설정에 활성화된 타입만 필터링한 탐지 결과."""
        return [
            m
            for m in self._detector.detect(text)
            if m.pii_type in self._config.enabled_types
        ]
