"""PiiMaskingService: 외부 LLM 경계의 가역 마스킹/복원 오케스트레이션.

- mask: 입력/검색결과의 PII를 placeholder로 치환 (session vault에 누적)
- unmask: 응답의 placeholder를 원복 + vault에 없는 신규 PII는 [REDACTED_<TYPE>] 처리

원본 PII / vault 값은 로그에 기록하지 않는다(LOG-001). 개수/타입만 기록.
탐지 예외 시 fail-closed: 원문(PII)을 그대로 통과시키지 않는다.
"""
from __future__ import annotations

import re

from src.application.pii_masking.schemas import PiiMaskingConfig
from src.domain.logging.interfaces import LoggerInterface
from src.domain.pii_masking.interfaces import PiiDetectorPort
from src.domain.pii_masking.policies import REDACT_PREFIX
from src.domain.pii_masking.schemas import PiiMatch, PiiType, TokenVaultRegistry

# 탐지 실패 시 mask가 반환하는 안전 마커(원문 미노출).
MASK_FAILURE_PLACEHOLDER = "[PII_MASKING_FAILED]"

# vault에서 복원되지 않은 고아 placeholder(예: [PHONE_9]) 검출용.
_PLACEHOLDER_PATTERN = re.compile(
    r"\[(" + "|".join(t.value.upper() for t in PiiType) + r")_\d+\]"
)


class PiiMaskingService:
    """PiiMaskingPort 구현체."""

    def __init__(
        self,
        detector: PiiDetectorPort,
        registry: TokenVaultRegistry,
        logger: LoggerInterface,
        config: PiiMaskingConfig,
    ) -> None:
        self._detector = detector
        self._registry = registry
        self._logger = logger
        self._config = config

    def mask(self, text: str, session_id: str) -> str:
        """PII를 placeholder로 치환한 텍스트를 반환. 탐지 실패 시 fail-closed."""
        if not self._config.enabled or not text:
            return text
        try:
            matches = self._enabled_matches(text)
        except Exception as exc:  # noqa: BLE001 — fail-closed가 목적
            self._logger.error(
                "PII detection failed during mask; failing closed",
                exception=exc,
                session_id=session_id,
            )
            return MASK_FAILURE_PLACEHOLDER
        vault = self._registry.get(session_id)
        result = text
        for match in sorted(matches, key=lambda m: m.start, reverse=True):
            placeholder = vault.get_or_create_placeholder(match.pii_type, match.text)
            result = result[: match.start] + placeholder + result[match.end :]
        if matches:
            self._logger.info(
                "PII masked", session_id=session_id, masked_count=len(matches)
            )
        return result

    def unmask(self, text: str, session_id: str) -> str:
        """placeholder를 원복하고, 미매핑 PII/고아 placeholder는 redact."""
        if not self._config.enabled or not text:
            return text
        result = text
        if self._config.output_redact:
            result = self._redact_unmapped(result, session_id)
        vault = self._registry.get(session_id)
        result = vault.restore(result)
        return self._redact_orphan_placeholders(result, session_id)

    def _redact_unmapped(self, text: str, session_id: str) -> str:
        """응답에 새로 등장한 원본 PII를 [REDACTED_<TYPE>]로 치환.

        placeholder([PHONE_1] 등)는 PII 패턴에 매칭되지 않으므로 영향 없음.
        탐지 실패 시 원문 유지(원복 단계 이후 고아 검출이 2차 방어).
        """
        try:
            matches = self._enabled_matches(text)
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "PII detection failed during unmask redact",
                exception=exc,
                session_id=session_id,
            )
            return text
        result = text
        for match in sorted(matches, key=lambda m: m.start, reverse=True):
            token = f"[{REDACT_PREFIX}_{match.pii_type.value.upper()}]"
            result = result[: match.start] + token + result[match.end :]
        if matches:
            self._logger.warning(
                "Unmapped PII redacted in output",
                session_id=session_id,
                redacted_count=len(matches),
            )
        return result

    def _redact_orphan_placeholders(self, text: str, session_id: str) -> str:
        """vault로 복원되지 않은 고아 placeholder를 [REDACTED_<TYPE>]로 대체."""
        orphans = _PLACEHOLDER_PATTERN.findall(text)
        if not orphans:
            return text
        result = _PLACEHOLDER_PATTERN.sub(
            lambda m: f"[{REDACT_PREFIX}_{m.group(1)}]", text
        )
        self._logger.warning(
            "Orphan placeholders redacted",
            session_id=session_id,
            orphan_count=len(orphans),
        )
        return result

    def _enabled_matches(self, text: str) -> list[PiiMatch]:
        """설정에 활성화된 타입만 필터링한 탐지 결과."""
        return [
            m
            for m in self._detector.detect(text)
            if m.pii_type in self._config.enabled_types
        ]
