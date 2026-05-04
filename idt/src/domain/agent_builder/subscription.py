"""Subscription 엔티티 + SubscriptionPolicy."""
from dataclasses import dataclass
from datetime import datetime

from src.domain.agent_builder.policies import AccessCheckInput, VisibilityPolicy


@dataclass
class Subscription:
    """사용자의 에이전트 구독 (북마크)."""

    id: str
    user_id: str
    agent_id: str
    is_pinned: bool
    subscribed_at: datetime


class SubscriptionPolicy:
    @staticmethod
    def can_subscribe(ctx: AccessCheckInput) -> bool:
        """구독 가능 여부: 접근 가능 + 자신의 에이전트가 아닌 경우."""
        if ctx.agent_owner_id == ctx.viewer_user_id:
            return False
        return VisibilityPolicy.can_access(ctx)
