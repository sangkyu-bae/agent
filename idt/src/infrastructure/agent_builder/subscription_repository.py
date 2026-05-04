"""SubscriptionRepository: user_agent_subscription MySQL CRUD."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_builder.interfaces import SubscriptionRepositoryInterface
from src.domain.agent_builder.subscription import Subscription
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.subscription_model import UserAgentSubscriptionModel


class SubscriptionRepository(SubscriptionRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, subscription: Subscription, request_id: str) -> Subscription:
        self._logger.info(
            "Subscription save", request_id=request_id, sub_id=subscription.id
        )
        try:
            model = UserAgentSubscriptionModel(
                id=subscription.id,
                user_id=subscription.user_id,
                agent_id=subscription.agent_id,
                is_pinned=subscription.is_pinned,
                subscribed_at=subscription.subscribed_at,
            )
            self._session.add(model)
            await self._session.flush()
            return subscription
        except Exception as e:
            self._logger.error(
                "Subscription save failed", exception=e, request_id=request_id
            )
            raise

    async def find_by_user_and_agent(
        self, user_id: str, agent_id: str, request_id: str
    ) -> Subscription | None:
        self._logger.info(
            "Subscription find_by_user_and_agent",
            request_id=request_id,
            user_id=user_id,
            agent_id=agent_id,
        )
        try:
            stmt = select(UserAgentSubscriptionModel).where(
                UserAgentSubscriptionModel.user_id == user_id,
                UserAgentSubscriptionModel.agent_id == agent_id,
            )
            result = await self._session.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_domain(model)
        except Exception as e:
            self._logger.error(
                "Subscription find_by_user_and_agent failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def delete(self, user_id: str, agent_id: str, request_id: str) -> None:
        self._logger.info(
            "Subscription delete",
            request_id=request_id,
            user_id=user_id,
            agent_id=agent_id,
        )
        try:
            stmt = delete(UserAgentSubscriptionModel).where(
                UserAgentSubscriptionModel.user_id == user_id,
                UserAgentSubscriptionModel.agent_id == agent_id,
            )
            await self._session.execute(stmt)
            await self._session.flush()
        except Exception as e:
            self._logger.error(
                "Subscription delete failed", exception=e, request_id=request_id
            )
            raise

    async def update_pin(
        self, user_id: str, agent_id: str, is_pinned: bool, request_id: str
    ) -> Subscription:
        self._logger.info(
            "Subscription update_pin",
            request_id=request_id,
            user_id=user_id,
            agent_id=agent_id,
            is_pinned=is_pinned,
        )
        try:
            stmt = (
                update(UserAgentSubscriptionModel)
                .where(
                    UserAgentSubscriptionModel.user_id == user_id,
                    UserAgentSubscriptionModel.agent_id == agent_id,
                )
                .values(is_pinned=is_pinned)
            )
            await self._session.execute(stmt)
            await self._session.flush()

            sub = await self.find_by_user_and_agent(user_id, agent_id, request_id)
            if sub is None:
                raise ValueError("구독을 찾을 수 없습니다")
            return sub
        except Exception as e:
            self._logger.error(
                "Subscription update_pin failed", exception=e, request_id=request_id
            )
            raise

    async def list_by_user(
        self, user_id: str, request_id: str
    ) -> list[Subscription]:
        self._logger.info(
            "Subscription list_by_user", request_id=request_id, user_id=user_id
        )
        try:
            stmt = (
                select(UserAgentSubscriptionModel)
                .where(UserAgentSubscriptionModel.user_id == user_id)
                .order_by(UserAgentSubscriptionModel.subscribed_at.desc())
            )
            result = await self._session.execute(stmt)
            return [self._to_domain(m) for m in result.scalars().all()]
        except Exception as e:
            self._logger.error(
                "Subscription list_by_user failed", exception=e, request_id=request_id
            )
            raise

    async def find_subscribers_by_agent(
        self, agent_id: str, request_id: str
    ) -> list[Subscription]:
        self._logger.info(
            "Subscription find_subscribers_by_agent",
            request_id=request_id,
            agent_id=agent_id,
        )
        try:
            stmt = select(UserAgentSubscriptionModel).where(
                UserAgentSubscriptionModel.agent_id == agent_id
            )
            result = await self._session.execute(stmt)
            return [self._to_domain(m) for m in result.scalars().all()]
        except Exception as e:
            self._logger.error(
                "Subscription find_subscribers_by_agent failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def delete_by_agent(self, agent_id: str, request_id: str) -> int:
        self._logger.info(
            "Subscription delete_by_agent", request_id=request_id, agent_id=agent_id
        )
        try:
            count_stmt = select(func.count()).where(
                UserAgentSubscriptionModel.agent_id == agent_id
            )
            count = (await self._session.execute(count_stmt)).scalar_one()

            stmt = delete(UserAgentSubscriptionModel).where(
                UserAgentSubscriptionModel.agent_id == agent_id
            )
            await self._session.execute(stmt)
            await self._session.flush()
            return count
        except Exception as e:
            self._logger.error(
                "Subscription delete_by_agent failed",
                exception=e,
                request_id=request_id,
            )
            raise

    def _to_domain(self, model: UserAgentSubscriptionModel) -> Subscription:
        return Subscription(
            id=model.id,
            user_id=model.user_id,
            agent_id=model.agent_id,
            is_pinned=model.is_pinned,
            subscribed_at=model.subscribed_at,
        )
