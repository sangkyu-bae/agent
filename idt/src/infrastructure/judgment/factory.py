"""판정 백엔드 팩토리 — 설정값 하나로 Jev / AnyJev / 없음 을 고른다.

Design Ref: judgment-backend §4.4 —
- `judgment_backend=off` → None. 그 외 조립 실패(오타·키/URL 누락·SDK 미설치·
  스킴 오류)는 예외를 **전파**한다. None 으로 바꾸고 warning 을 남기는 쪽은
  main.py get_judgment_backend() 한 곳(탈착형 이음매, 1회 조립).
- Jev 어댑터 모듈은 여기서 지연 import 한다
  — `typesafe_sdk` 미설치면 ImportError 가 이 지점.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from src.domain.judgment.interfaces import JudgmentPort
from src.domain.judgment.value_objects import JudgmentBackendKind
from src.domain.logging.interfaces.logger_interface import LoggerInterface

if TYPE_CHECKING:  # pragma: no cover
    from src.config import Settings

_ALLOWED_SCHEMES = ("http", "https")


def build_judgment_backend(
    settings: Settings, logger: LoggerInterface
) -> JudgmentPort | None:
    kind = JudgmentBackendKind.from_string(settings.judgment_backend)
    if kind is JudgmentBackendKind.OFF:
        return None
    timeout = float(settings.judgment_timeout_seconds)
    if timeout <= 0:
        raise ValueError("judgment_timeout_seconds must be > 0")
    backend = (
        _build_jev(settings, timeout)
        if kind is JudgmentBackendKind.JEV
        else _build_anyjev(settings, timeout)
    )
    logger.info(
        "judgment backend assembled", backend=kind.value, timeout_seconds=timeout
    )
    return backend


def _build_jev(settings: Settings, timeout: float) -> JudgmentPort:
    api_key = (settings.typesafe_api_key or "").strip()
    if not api_key:
        raise ValueError("typesafe_api_key is required for judgment_backend=jev")
    from src.infrastructure.judgment.jev.adapter import JevJudgmentAdapter

    return JevJudgmentAdapter(
        api_key=api_key,
        model=settings.typesafe_model,
        timeout_seconds=timeout,
        base_url=(settings.typesafe_base_url or "").strip() or None,
    )


def _build_anyjev(settings: Settings, timeout: float) -> JudgmentPort:
    base_url = (settings.anyjev_base_url or "").strip()
    if not base_url:
        raise ValueError("anyjev_base_url is required for judgment_backend=anyjev")
    parts = urlsplit(base_url)
    if parts.scheme not in _ALLOWED_SCHEMES or not parts.netloc:
        raise ValueError("anyjev_base_url must be an http(s) URL")
    from src.infrastructure.judgment.anyjev.adapter import AnyJevJudgmentAdapter

    return AnyJevJudgmentAdapter(
        base_url=base_url,
        timeout_seconds=timeout,
        model_name=settings.anyjev_model,
    )
