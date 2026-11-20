"""근거 판정 모델 설정 저장소 포트."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.grounding_judge_setting.models import GroundingJudgeSetting


class GroundingJudgeSettingRepositoryPort(ABC):
    @abstractmethod
    async def get(self, request_id: str) -> GroundingJudgeSetting:
        """단일 행 설정. 행이 없으면 빈 설정을 만들어 돌려준다."""

    @abstractmethod
    async def update(
        self, setting: GroundingJudgeSetting, request_id: str
    ) -> GroundingJudgeSetting:
        """단일 행을 덮어쓴다(commit 은 호출측 세션 몫)."""
