"""ExtensionHooks — 앱 수명 단일 레지스트리.

Design Ref: graph-rag-foundation §3.1 / D11 — 기동 시 확장 모듈이 한 번 채우고
요청 중에는 읽기만 한다(요청별로 바뀌는 bind_auth_ctx 류 상태와 다르다).
아무것도 등록하지 않으면 모든 슬롯이 None 이고 코어는 기존과 똑같이 동작한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.extension_hooks.ports import (
    DocumentDeletionHook,
    FeatureExposurePort,
    PostIngestHook,
    SupplementalRetrievalSource,
)

_SLOTS = ("post_ingest", "deletion", "supplemental", "exposure")


@dataclass
class ExtensionHooks:
    post_ingest: PostIngestHook | None = None
    deletion: DocumentDeletionHook | None = None
    supplemental: SupplementalRetrievalSource | None = None
    exposure: FeatureExposurePort | None = None
    _owners: dict[str, str | None] = field(default_factory=dict, repr=False)

    def register(self, *, owner: str | None = None, **slots: object) -> None:
        """슬롯 등록.

        다른 확장이 이미 차지한 슬롯이면 기동 시점에 ValueError 로 드러낸다.
        같은 owner 의 재등록(create_app 재호출·테스트)은 교체한다.
        owner 가 None 이면 항상 새 소유자로 본다(이중 등록 = 오류).
        """
        for name, impl in slots.items():
            if name not in _SLOTS:
                raise ValueError(f"unknown extension slot: {name}")
            if impl is None:
                continue
            taken = getattr(self, name) is not None
            same_owner = owner is not None and self._owners.get(name) == owner
            if taken and not same_owner:
                raise ValueError(f"extension slot already registered: {name}")
            setattr(self, name, impl)
            self._owners[name] = owner

    async def is_visible(self, feature: str, *, caller_is_admin: bool) -> bool:
        """노출 판단 — 미등록·오류는 닫힘(False)."""
        if self.exposure is None:
            return False
        try:
            return bool(await self.exposure.is_visible(feature, caller_is_admin))
        except Exception:
            return False
