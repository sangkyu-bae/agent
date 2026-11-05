"""UserSelectedCollectionAssigner — 사용자 선택형 물리 컬렉션 배정 (Design D6).

물리 컬렉션 접근 검사는 KB 생성 시 이 1회만 수행한다 (Plan §4-3).
"""
from typing import TYPE_CHECKING

from src.application.collection.permission_service import (
    CollectionPermissionService,
)
from src.domain.auth.entities import User
from src.domain.collection.interfaces import CollectionRepositoryInterface
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.collection.schemas import CreateCollectionRequest
from src.domain.knowledge_base.interfaces import CollectionAssignerInterface
from src.domain.knowledge_base.quick_setup_policy import KbQuickSetupPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface

if TYPE_CHECKING:
    from src.application.collection.use_case import CollectionManagementUseCase
    from src.application.kb_default_setting.use_case import KbDefaultSettingUseCase


class UserSelectedCollectionAssigner(CollectionAssignerInterface):
    def __init__(
        self,
        collection_repo: CollectionRepositoryInterface,
        perm_service: CollectionPermissionService,
    ) -> None:
        self._collection_repo = collection_repo
        self._perm_service = perm_service

    async def assign(
        self,
        user: User,
        requested_collection: str | None,
        request_id: str,
        *,
        kb_id: str | None = None,
        scope: CollectionScope | None = None,
        department_id: str | None = None,
    ) -> str:
        if not requested_collection:
            raise ValueError("collection_name is required")
        if not await self._collection_repo.collection_exists(
            requested_collection
        ):
            raise ValueError(
                f"Collection '{requested_collection}' not found"
            )
        await self._perm_service.check_read_access(
            requested_collection, user, request_id
        )
        return requested_collection


class AutoProvisionCollectionAssigner(CollectionAssignerInterface):
    """컬렉션 미지정 시 KB 전용 컬렉션을 자동 생성하는 배정기.

    agent-kb-quick-setup Design §9.4.
    - requested_collection 이 있으면 사용자 선택형(fallback)에 위임 — 기존 경로 무변경.
    - 없으면 관리자 기본 임베딩 모델로 `kb-{kb_id[:8]}` 컬렉션을 만든다. 기존
      CollectionManagementUseCase.create_collection 을 그대로 거치므로 권한 행과
      활동 로그 CREATE(embedding_model)가 남고, 적재 시 임베딩 모델 결정이 성립한다.
    - 미설정이면 KbDefaultsNotConfiguredError(422) — 조용한 폴백 금지 (Plan FR-03).
    """

    def __init__(
        self,
        fallback: CollectionAssignerInterface,
        defaults: "KbDefaultSettingUseCase",
        collection_use_case: "CollectionManagementUseCase",
        logger: LoggerInterface,
    ) -> None:
        self._fallback = fallback
        self._defaults = defaults
        self._collections = collection_use_case
        self._logger = logger

    async def assign(
        self,
        user: User,
        requested_collection: str | None,
        request_id: str,
        *,
        kb_id: str | None = None,
        scope: CollectionScope | None = None,
        department_id: str | None = None,
    ) -> str:
        if requested_collection:
            return await self._fallback.assign(
                user, requested_collection, request_id,
                kb_id=kb_id, scope=scope, department_id=department_id,
            )
        if not kb_id:
            raise ValueError("kb_id is required for auto-provisioned collections")
        model = await self._defaults.resolve_default_model(request_id)
        name = KbQuickSetupPolicy.collection_name_for(kb_id)
        await self._collections.create_collection(
            CreateCollectionRequest(
                name=name,
                vector_size=model.vector_dimension,
                embedding_model=model.model_name,
            ),
            request_id,
            user_id=str(user.id) if user.id is not None else None,
            user=user,
            scope=scope or CollectionScope.PERSONAL,
            department_id=department_id,
        )
        self._logger.info(
            "Auto-provisioned KB collection",
            request_id=request_id,
            collection_name=name,
            kb_id=kb_id,
            embedding_model=model.model_name,
        )
        return name

    async def rollback(
        self, collection_name: str, user: User, request_id: str
    ) -> None:
        """자동 생성 컬렉션만 best-effort 삭제.

        사용자 선택 컬렉션(접두 불일치)은 절대 지우지 않는다.
        """
        if not KbQuickSetupPolicy.is_auto_collection(collection_name):
            return
        try:
            await self._collections.delete_collection(
                collection_name, request_id,
                user_id=str(user.id) if user.id is not None else None,
                user=user,
            )
        except Exception as e:
            self._logger.warning(
                "Auto-provisioned collection rollback failed (orphan left)",
                request_id=request_id,
                collection_name=collection_name,
                exception=e,
            )
