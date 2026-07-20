"""Wiki Router: 정제(distill)/조회/승인·반려·폐기·복구·편집 API (LLM-WIKI-001).

거버넌스 게이트: 자동 생성분은 draft로 적재되고, 승인(approve) 후에만 검색에 노출된다.
wiki-user-facing: 소유자 직접 작성(POST)·트리 조회(GET /tree)를 추가하고,
편집(PUT)·폐기(deprecate)는 인가를 유스케이스(can_manage)로 위임한다
(admin 동작은 기존과 동일 — 소유자 허용이 추가됐을 뿐).
DI는 main.py에서 dependency_overrides로 주입한다.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.application.wiki.api_schemas import (
    CreateWikiRequest,
    DistillRequest,
    DistillResponse,
    EditWikiRequest,
    ListWikiResponse,
    ReviewActionRequest,
    WikiArticleResponse,
    WikiTreeGroupResponse,
    WikiTreeItemResponse,
    WikiTreeResponse,
    to_response,
)
from src.domain.auth.entities import User, UserRole
from src.domain.wiki.entity import WikiStatus
from src.interfaces.dependencies.auth import get_current_user, require_role

router = APIRouter(prefix="/api/v1/wiki", tags=["Wiki"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_distill_use_case():
    raise NotImplementedError


def get_query_use_case():
    raise NotImplementedError


def get_review_use_case():
    raise NotImplementedError


def get_human_write_use_case():
    raise NotImplementedError


def _raise_review_error(exc: ValueError) -> None:
    """리뷰 계열 ValueError를 404/422로 변환한다."""
    msg = str(exc)
    raise HTTPException(status_code=404 if "찾을 수 없" in msg else 422, detail=msg)


def _actor(user: User) -> tuple[str, bool]:
    """인증 사용자 → (actor_id, is_admin). 인가 근거는 body가 아니라 인증 정보다."""
    return str(user.id), user.role == UserRole.ADMIN


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.post("/distill", response_model=DistillResponse)
async def distill_wiki(
    body: DistillRequest,
    use_case=Depends(get_distill_use_case),
    _admin: User = Depends(require_role("admin")),
):
    """특정 에이전트 컬렉션을 정제해 draft 위키 항목을 생성한다."""
    request_id = str(uuid.uuid4())
    try:
        created = await use_case.execute(
            body.agent_id, body.collection_name, body.max_articles, request_id
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return DistillResponse(
        agent_id=body.agent_id,
        created_count=len(created),
        items=[to_response(a) for a in created],
    )


@router.post("", response_model=WikiArticleResponse, status_code=201)
async def create_wiki(
    body: CreateWikiRequest,
    use_case=Depends(get_human_write_use_case),
    user: User = Depends(get_current_user),
):
    """소유자 직접 작성 — source_type=human, 즉시 approved (wiki-user-facing)."""
    request_id = str(uuid.uuid4())
    actor_id, is_admin = _actor(user)
    try:
        article = await use_case.create(
            agent_id=body.agent_id,
            title=body.title,
            content=body.content,
            path=body.path,
            actor_id=actor_id,
            actor_is_admin=is_admin,
            request_id=request_id,
            valid_until=body.valid_until,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        _raise_review_error(e)
    return to_response(article)


# ※ /tree는 반드시 /{id}보다 먼저 선언 — 아니면 "tree"가 id로 매칭된다
@router.get("/tree", response_model=WikiTreeResponse)
async def wiki_tree(
    agent_id: str,
    use_case=Depends(get_query_use_case),
    _user: User = Depends(get_current_user),
):
    """지식 트리 — path 단위 그룹 목록(본문 제외). 계층 조립은 프론트 담당."""
    request_id = str(uuid.uuid4())
    groups = await use_case.list_tree(agent_id, request_id)
    return WikiTreeResponse(
        agent_id=agent_id,
        groups=[
            WikiTreeGroupResponse(
                path=g.path,
                items=[
                    WikiTreeItemResponse(
                        id=i.id, title=i.title, status=i.status,
                        source_type=i.source_type, updated_at=i.updated_at,
                    )
                    for i in g.items
                ],
            )
            for g in groups
        ],
        total=sum(len(g.items) for g in groups),
    )


@router.get("", response_model=ListWikiResponse)
async def list_wiki(
    agent_id: str,
    status: str | None = None,
    use_case=Depends(get_query_use_case),
    _user: User = Depends(get_current_user),
):
    """에이전트 스코프 위키 목록 (status 필터 선택)."""
    request_id = str(uuid.uuid4())
    status_enum = _parse_status(status)
    items = await use_case.list_by_agent(agent_id, request_id, status_enum)
    return ListWikiResponse(
        items=[to_response(a) for a in items], total=len(items)
    )


@router.get("/{id}", response_model=WikiArticleResponse)
async def get_wiki(
    id: str,
    use_case=Depends(get_query_use_case),
    _user: User = Depends(get_current_user),
):
    """위키 단건 조회."""
    request_id = str(uuid.uuid4())
    result = await use_case.get_by_id(id, request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Wiki article not found")
    return to_response(result)


@router.patch("/{id}/approve", response_model=WikiArticleResponse)
async def approve_wiki(
    id: str,
    body: ReviewActionRequest,
    use_case=Depends(get_review_use_case),
    _admin: User = Depends(require_role("admin")),
):
    """초안 승인(draft→approved)."""
    request_id = str(uuid.uuid4())
    try:
        return to_response(await use_case.approve(id, body.reviewer_id, request_id))
    except ValueError as e:
        _raise_review_error(e)


@router.patch("/{id}/reject", response_model=WikiArticleResponse)
async def reject_wiki(
    id: str,
    use_case=Depends(get_review_use_case),
    _admin: User = Depends(require_role("admin")),
):
    """초안 반려(draft→deprecated)."""
    request_id = str(uuid.uuid4())
    try:
        return to_response(await use_case.reject(id, request_id))
    except ValueError as e:
        _raise_review_error(e)


@router.patch("/{id}/deprecate", response_model=WikiArticleResponse)
async def deprecate_wiki(
    id: str,
    use_case=Depends(get_human_write_use_case),
    user: User = Depends(get_current_user),
):
    """승인 항목 폐기(approved→deprecated) — admin 전부, 소유자는 human 문서만."""
    request_id = str(uuid.uuid4())
    actor_id, is_admin = _actor(user)
    try:
        article = await use_case.deprecate(
            article_id=id, actor_id=actor_id, actor_is_admin=is_admin,
            request_id=request_id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        _raise_review_error(e)
    return to_response(article)


@router.patch("/{id}/restore", response_model=WikiArticleResponse)
async def restore_wiki(
    id: str,
    body: ReviewActionRequest,
    use_case=Depends(get_review_use_case),
    _admin: User = Depends(require_role("admin")),
):
    """폐기 항목 복구(deprecated→approved)."""
    request_id = str(uuid.uuid4())
    try:
        return to_response(await use_case.restore(id, body.reviewer_id, request_id))
    except ValueError as e:
        _raise_review_error(e)


@router.put("/{id}", response_model=WikiArticleResponse)
async def edit_wiki(
    id: str,
    body: EditWikiRequest,
    use_case=Depends(get_human_write_use_case),
    user: User = Depends(get_current_user),
):
    """위키 편집(version++) — admin 전부, 소유자는 human 문서만.

    editor 기록은 body.editor_id가 아닌 인증 사용자를 사용한다(위조 방지).
    """
    request_id = str(uuid.uuid4())
    actor_id, is_admin = _actor(user)
    try:
        article = await use_case.edit(
            article_id=id, title=body.title, content=body.content,
            path=body.path, actor_id=actor_id, actor_is_admin=is_admin,
            request_id=request_id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        _raise_review_error(e)
    return to_response(article)


def _parse_status(status: str | None) -> WikiStatus | None:
    """status 쿼리 문자열을 enum으로 변환(잘못된 값 422)."""
    if status is None:
        return None
    try:
        return WikiStatus(status)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid status: {status}")
