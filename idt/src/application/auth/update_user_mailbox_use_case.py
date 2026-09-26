"""UpdateUserMailboxUseCase — 관리자가 회원의 사내 메일함 UPN 을 설정·해제한다.

Design Ref: mcp-identity-header §4.2. 이 값은 신원 헤더 MCP 호출의 클레임
소스다 — 플랫폼 인증 경로 밖(LLM·도구 인자)에서는 바꿀 수 없다.
"""
from dataclasses import replace
from typing import Optional

from src.domain.auth.entities import User
from src.domain.auth.interfaces import UserRepositoryInterface
from src.domain.auth.policies import MailboxPolicy
from src.domain.logging.interfaces import LoggerInterface


class UserNotFoundError(LookupError):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"User not found: {user_id}")
        self.user_id = user_id


class UpdateUserMailboxUseCase:
    def __init__(self, user_repo: UserRepositoryInterface, logger: LoggerInterface) -> None:
        self._user_repo = user_repo
        self._logger = logger

    async def execute(
        self, user_id: int, mailbox_upn: Optional[str], request_id: str
    ) -> User:
        """정규화(형식 오류는 ValueError) → 존재 확인 → 저장. commit 은 세션 의존성."""
        normalized = MailboxPolicy.normalize(mailbox_upn)
        user = await self._user_repo.find_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        await self._user_repo.update_mailbox(user_id, normalized)
        # 메일함 주소는 개인정보 — 설정/해제 사실만 남긴다.
        self._logger.info(
            "UpdateUserMailbox done",
            request_id=request_id,
            user_id=user_id,
            cleared=normalized is None,
        )
        return replace(user, mailbox_upn=normalized)
