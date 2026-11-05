"""User kb-defaults router: GET /api/v1/kb-defaults.

agent-kb-quick-setup Design §4.2. 빌더 블록이 업로드 전 "관리자가 기본 임베딩
모델을 설정해야 합니다" 안내를 띄우기 위한 읽기 전용 축약.
UseCase 는 관리자 라우터와 공유한다 (DI 플레이스홀더 재사용).
"""
import uuid

from fastapi import APIRouter, Depends

from src.api.routes.admin_kb_defaults_router import get_kb_default_setting_use_case
from src.application.kb_default_setting.use_case import KbDefaultSettingUseCase
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user
from src.interfaces.schemas.kb_defaults import KbDefaultsPublicResponse

router = APIRouter(prefix="/api/v1/kb-defaults", tags=["kb-defaults"])


@router.get("", response_model=KbDefaultsPublicResponse)
async def get_kb_defaults_public(
    current_user: User = Depends(get_current_user),
    use_case: KbDefaultSettingUseCase = Depends(get_kb_default_setting_use_case),
) -> KbDefaultsPublicResponse:
    view = await use_case.get(request_id=str(uuid.uuid4()))
    return KbDefaultsPublicResponse.from_view(view)
