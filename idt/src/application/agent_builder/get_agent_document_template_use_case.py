"""GetAgentDocumentTemplateUseCase: 빌더 수정 화면용 저장 양식 조회.

Design Ref: extractor-template-preview §4.2 — 조회 키는 추출기 워커
tool_config.template_id (포크는 원작자 template_id 를 공유하고, 런타임도
find_by_id 로 찾는다). 예시값은 양식을 만든 에이전트의 소유자에게만 보낸다.
"""
from src.application.agent_builder.document_template_binding import (
    DOCUMENT_EXTRACTOR_TOOL_ID,
)
from src.application.agent_builder.schemas import (
    AgentDocumentTemplateResponse,
    SavedTemplateSlot,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, VisibilityPolicy
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.document_extractor.interfaces import (
    DocumentTemplateRepositoryInterface,
)
from src.domain.document_extractor.policies import TemplateSampleExposurePolicy
from src.domain.document_extractor.schemas import TEMPLATE_STATUS_ACTIVE
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class AgentNotFoundError(Exception):
    """에이전트 없음 — 404."""


class AgentDocumentTemplateNotFoundError(Exception):
    """추출기 워커·template_id·활성 양식 중 하나라도 없음 — 404."""


class GetAgentDocumentTemplateUseCase:
    def __init__(
        self,
        agent_repository: AgentDefinitionRepositoryInterface,
        template_repository: DocumentTemplateRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_repository = agent_repository
        self._template_repository = template_repository
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        request_id: str,
        viewer_user_id: str,
        viewer_role: str = "user",
    ) -> AgentDocumentTemplateResponse:
        self._logger.info(
            "GetAgentDocumentTemplateUseCase start",
            request_id=request_id, agent_id=agent_id,
        )
        try:
            agent = await self._agent_repository.find_by_id(agent_id, request_id)
            if agent is None:
                raise AgentNotFoundError(f"Agent not found: {agent_id}")

            ctx = AccessCheckInput(
                agent_owner_id=agent.user_id,
                agent_visibility=agent.visibility,
                agent_department_id=agent.department_id,
                viewer_user_id=viewer_user_id,
                viewer_department_ids=[],
                viewer_role=viewer_role,
            )
            # 빌더 수정 화면과 같은 권한 — 소유자만 (관리자 예외 없음, Design §1.2)
            if not VisibilityPolicy.can_edit(ctx):
                raise PermissionError("양식 조회 권한이 없습니다")

            template_id = self._extractor_template_id(agent)
            if template_id is None:
                raise AgentDocumentTemplateNotFoundError("Document template not found")

            template = await self._template_repository.find_by_id(
                template_id, request_id
            )
            if template is None or template.status != TEMPLATE_STATUS_ACTIVE:
                raise AgentDocumentTemplateNotFoundError("Document template not found")

            is_inherited = template.agent_id != agent.id
            origin_owner_id = (
                await self._origin_owner_id(template.agent_id, request_id)
                if is_inherited
                else agent.user_id
            )
            show_samples = TemplateSampleExposurePolicy.can_view_samples(
                viewer_user_id, origin_owner_id
            )

            response = AgentDocumentTemplateResponse(
                template_id=template.id,
                name=template.name,
                source_format=template.source_format,
                html_skeleton=template.html_skeleton,
                slots=[
                    SavedTemplateSlot(
                        key=slot.key,
                        label=slot.label,
                        slot_type=slot.slot_type,
                        description=slot.description,
                        sample_value=slot.sample_value if show_samples else "",
                    )
                    for slot in template.slots
                ],
                samples_hidden=not show_samples,
                is_inherited=is_inherited,
                updated_at=template.updated_at,
            )
            self._logger.info(
                "GetAgentDocumentTemplateUseCase done",
                request_id=request_id, agent_id=agent_id,
                template_id=template.id, samples_hidden=not show_samples,
            )
            return response
        except (
            AgentNotFoundError, AgentDocumentTemplateNotFoundError, PermissionError
        ):
            raise
        except Exception as e:
            self._logger.error(
                "GetAgentDocumentTemplateUseCase failed",
                exception=e, request_id=request_id, agent_id=agent_id,
            )
            raise

    @staticmethod
    def _extractor_template_id(agent: AgentDefinition) -> str | None:
        worker = next(
            (
                w for w in agent.workers
                if w.worker_type == "tool" and w.tool_id == DOCUMENT_EXTRACTOR_TOOL_ID
            ),
            None,
        )
        if worker is None:
            return None
        template_id = (worker.tool_config or {}).get("template_id")
        return template_id if isinstance(template_id, str) and template_id else None

    async def _origin_owner_id(
        self, origin_agent_id: str, request_id: str
    ) -> str | None:
        """포크로 물려받은 양식의 원작자. 원 에이전트가 없으면 None (예시값 숨김)."""
        origin = await self._agent_repository.find_by_id(origin_agent_id, request_id)
        return origin.user_id if origin is not None else None
