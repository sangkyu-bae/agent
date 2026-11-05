from abc import ABC, abstractmethod

from src.domain.kb_default_setting.entities import KbDefaultSetting


class KbDefaultSettingRepositoryInterface(ABC):
    @abstractmethod
    async def get(self, request_id: str) -> KbDefaultSetting:
        """행이 없으면 기본값 행을 만들어 돌려준다 (시드 누락 방어)."""

    @abstractmethod
    async def update(
        self, setting: KbDefaultSetting, request_id: str
    ) -> KbDefaultSetting: ...
