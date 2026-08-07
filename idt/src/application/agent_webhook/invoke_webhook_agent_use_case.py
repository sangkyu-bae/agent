"""InvokeWebhookAgentUseCase — 공개 inbound 검증 + 소유자 신원 동기 실행.

Design §4-3 검증 순서:
헤더 → 타임스탬프 허용창 → 채널 조회(미존재/비활성 404) → HMAC 검증(raw bytes)
→ body 파싱 → 소유자 AuthContext 조립(D3) → RunAgentUseCase 위임.

시크릿·서명 값은 로그 인자로 절대 전달하지 않는다 (Design §8 — 미전달 원칙).

M2: 실행 완료 후 outbound 디스패처를 비차단 태스크로 호출한다 (D12 훅 ②).
dispatcher는 optional — 미주입 시 무동작 (FR-16 하위호환).
"""
import asyncio
import time

from pydantic import ValidationError

from src.application.agent_builder.schemas import RunAgentRequest
from src.application.agent_webhook.schemas import WebhookInvokeRequest
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_webhook.interfaces import AgentWebhookRepositoryInterface
from src.domain.agent_webhook.policies import WebhookSignaturePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class WebhookAuthError(Exception):
    """서명·타임스탬프 검증 실패 → 401 (사유 비구분, D8)."""


class WebhookNotFoundError(Exception):
    """채널 미설정·비활성·에이전트 없음 → 404 (단일 문구, D8)."""


class WebhookBadRequestError(Exception):
    """body 파싱/검증 실패 → 422."""


class InvokeWebhookAgentUseCase:
    def __init__(
        self,
        webhook_repo: AgentWebhookRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        user_repo,
        assemble_auth_context_uc,
        run_agent_uc,
        logger: LoggerInterface,
        outbound_dispatcher=None,
        spawn=None,
    ) -> None:
        self._webhook_repo = webhook_repo
        self._agent_repo = agent_repo
        self._user_repo = user_repo
        self._assemble_auth_context_uc = assemble_auth_context_uc
        self._run_agent_uc = run_agent_uc
        self._logger = logger
        # M2 훅 ② — dispatch()는 절대 raise하지 않는 계약(D16)이라 태스크 예외 누수 없음
        self._outbound_dispatcher = outbound_dispatcher
        self._spawn = spawn
        # Check G1: 실행 중 태스크 참조 미보유 시 CPython GC가 태스크를 회수할 수 있음
        # ("Task was destroyed but it is pending") — 완료까지 참조를 보유한다.
        self._background_tasks: set = set()

    async def execute(
        self,
        agent_id: str,
        raw_body: bytes,
        timestamp_header: str | None,
        signature_header: str | None,
        request_id: str,
    ):
        timestamp = self._parse_timestamp(timestamp_header, signature_header)
        webhook = await self._find_active_webhook(agent_id, request_id)
        if not WebhookSignaturePolicy.verify(
            webhook.secret, timestamp, raw_body, signature_header
        ):
            raise WebhookAuthError("서명 검증 실패")

        body = self._parse_body(raw_body)
        owner, owner_ctx = await self._assemble_owner_context(
            agent_id, request_id
        )
        self._logger.info(
            "webhook invoke accepted",
            request_id=request_id,
            agent_id=agent_id,
        )
        result = await self._run_agent_uc.execute(
            agent_id,
            RunAgentRequest(
                query=body.query,
                user_id=str(owner.id),
                session_id=body.session_id,
            ),
            request_id,
            auth_ctx=owner_ctx,
            viewer_user_id=str(owner.id),
            viewer_department_ids=list(owner_ctx.department_ids),
        )
        self._dispatch_outbound(agent_id, result, request_id)
        return result

    def _dispatch_outbound(self, agent_id: str, result, request_id: str) -> None:
        """M2 훅 ② — 비차단 발송 (호출자 응답에 재시도 지연 미전가, D12)."""
        if self._outbound_dispatcher is None:
            return
        spawn = self._spawn or asyncio.create_task
        task = spawn(
            self._outbound_dispatcher.dispatch(
                agent_id, result, "webhook", request_id
            )
        )
        if task is not None and hasattr(task, "add_done_callback"):
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    def _parse_timestamp(
        self, timestamp_header: str | None, signature_header: str | None
    ) -> int:
        if not timestamp_header or not signature_header:
            raise WebhookAuthError("서명 검증 실패")
        try:
            timestamp = int(timestamp_header)
        except ValueError:
            raise WebhookAuthError("서명 검증 실패")
        if not WebhookSignaturePolicy.is_timestamp_valid(
            timestamp, int(time.time())
        ):
            raise WebhookAuthError("서명 검증 실패")
        return timestamp

    async def _find_active_webhook(self, agent_id: str, request_id: str):
        webhook = await self._webhook_repo.find_by_agent_id(
            agent_id, request_id
        )
        if webhook is None or not webhook.enabled:
            raise WebhookNotFoundError("웹훅을 찾을 수 없습니다")
        return webhook

    def _parse_body(self, raw_body: bytes) -> WebhookInvokeRequest:
        try:
            return WebhookInvokeRequest.model_validate_json(raw_body)
        except ValidationError as e:
            raise WebhookBadRequestError(str(e))

    async def _assemble_owner_context(self, agent_id: str, request_id: str):
        """소유자 User 로드 + AuthContext 조립 (D3 — UI 실행과 동작 동등성)."""
        agent = await self._agent_repo.find_by_id(agent_id, request_id)
        if agent is None:
            raise WebhookNotFoundError("웹훅을 찾을 수 없습니다")
        try:
            owner = await self._user_repo.find_by_id(int(agent.user_id))
        except (TypeError, ValueError):
            owner = None
        if owner is None:
            raise WebhookNotFoundError("웹훅을 찾을 수 없습니다")
        owner_ctx = await self._assemble_auth_context_uc.execute(
            owner, request_id
        )
        return owner, owner_ctx
