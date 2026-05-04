"""SubscribeUseCase: 에이전트 구독/해제/설정변경."""
import uuid
from datetime import datetime, timezone

from src.application.agent_builder.schemas import SubscribeResponse
from src.domain.agent_builder.interfaces import (
    AgentDefinitionRepositoryInterface,
    SubscriptionRepositoryInterface,
)
from src.domain.agent_builder.policies import AccessCheckInput
from src.domain.agent_builder.subscription import Subscription, SubscriptionPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class SubscribeUseCase:
    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        subscription_repo: SubscriptionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_repo = agent_repo
        self._subscription_repo = subscription_repo
        self._logger = logger

    async def subscribe(
        self,
        agent_id: str,
        user_id: str,
        viewer_department_ids: list[str],
        request_id: str,
    ) -> SubscribeResponse:
        self._logger.info(
            "SubscribeUseCase.subscribe start",
            request_id=request_id,
            agent_id=agent_id,
            user_id=user_id,
        )
        try:
            agent = await self._agent_repo.find_by_id(agent_id, request_id)
            if agent is None:
                raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")

            ctx = AccessCheckInput(
                agent_owner_id=agent.user_id,
                agent_visibility=agent.visibility,
                agent_department_id=agent.department_id,
                viewer_user_id=user_id,
                viewer_department_ids=viewer_department_ids,
                viewer_role="user",
            )
            if not SubscriptionPolicy.can_subscribe(ctx):
                if agent.user_id == user_id:
                    raise ValueError("자신의 에이전트는 구독할 수 없습니다")
                raise PermissionError("접근 권한이 없습니다")

            existing = await self._subscription_repo.find_by_user_and_agent(
                user_id, agent_id, request_id
            )
            if existing is not None:
                raise ValueError("이미 구독 중입니다")

            subscription = Subscription(
                id=str(uuid.uuid4()),
                user_id=user_id,
                agent_id=agent_id,
                is_pinned=False,
                subscribed_at=datetime.now(timezone.utc),
            )
            saved = await self._subscription_repo.save(subscription, request_id)

            self._logger.info(
                "SubscribeUseCase.subscribe done",
                request_id=request_id,
                subscription_id=saved.id,
            )
            return SubscribeResponse(
                subscription_id=saved.id,
                agent_id=agent_id,
                agent_name=agent.name,
                is_pinned=saved.is_pinned,
                subscribed_at=saved.subscribed_at.isoformat(),
            )
        except Exception as e:
            self._logger.error(
                "SubscribeUseCase.subscribe failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def unsubscribe(
        self, agent_id: str, user_id: str, request_id: str
    ) -> None:
        self._logger.info(
            "SubscribeUseCase.unsubscribe start",
            request_id=request_id,
            agent_id=agent_id,
            user_id=user_id,
        )
        try:
            existing = await self._subscription_repo.find_by_user_and_agent(
                user_id, agent_id, request_id
            )
            if existing is None:
                raise ValueError("구독을 찾을 수 없습니다")

            await self._subscription_repo.delete(user_id, agent_id, request_id)
            self._logger.info(
                "SubscribeUseCase.unsubscribe done", request_id=request_id
            )
        except Exception as e:
            self._logger.error(
                "SubscribeUseCase.unsubscribe failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def update_pin(
        self,
        agent_id: str,
        user_id: str,
        is_pinned: bool,
        request_id: str,
    ) -> SubscribeResponse:
        self._logger.info(
            "SubscribeUseCase.update_pin start",
            request_id=request_id,
            agent_id=agent_id,
            is_pinned=is_pinned,
        )
        try:
            existing = await self._subscription_repo.find_by_user_and_agent(
                user_id, agent_id, request_id
            )
            if existing is None:
                raise ValueError("구독을 찾을 수 없습니다")

            updated = await self._subscription_repo.update_pin(
                user_id, agent_id, is_pinned, request_id
            )

            agent = await self._agent_repo.find_by_id(agent_id, request_id)
            agent_name = agent.name if agent else ""

            self._logger.info(
                "SubscribeUseCase.update_pin done", request_id=request_id
            )
            return SubscribeResponse(
                subscription_id=updated.id,
                agent_id=agent_id,
                agent_name=agent_name,
                is_pinned=updated.is_pinned,
                subscribed_at=updated.subscribed_at.isoformat(),
            )
        except Exception as e:
            self._logger.error(
                "SubscribeUseCase.update_pin failed",
                exception=e,
                request_id=request_id,
            )
            raise
