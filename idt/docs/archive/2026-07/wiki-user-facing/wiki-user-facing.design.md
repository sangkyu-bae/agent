# wiki-user-facing Design Document

> **Plan**: `docs/01-plan/features/wiki-user-facing.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-18
> **Status**: Draft
> **소스 기준**: master 워킹트리 실코드 (wiki_router.py / entity.py / policies.py / models.py / wiki_first_search_use_case.py / SourceCitation.tsx / types/chat.ts 정독)

---

## 1. Overview

LLM Wiki의 사용자 노출 3축을 설계한다:
① 소유자 직접 작성(`source_type=human`) ② `path`(V051) 기반 지식 트리 ③ 답변 근거 배지→문서 뷰.

### 1.1 Plan에서 이월된 결정 6건 — 확정

| # | 결정 대상 | 확정안 | 근거 |
|---|-----------|--------|------|
| ① | human 문서 생성 상태 | **즉시 approved** (reviewer_id=editor_id=작성자) | agent 스코프라 피해 반경이 본인 에이전트뿐 + 소유자가 곧 검수자 — draft 강제는 자기 글을 자기가 승인하는 요식 단계만 추가. deprecate로 즉시 회수 가능. distill의 draft 기본값은 무변경 |
| ② | source_refs 출처 형식 | **`["human:{user_id}"]`** (prefix 상수 `WikiPolicy.HUMAN_SOURCE_PREFIX`) | 출처 불변식(`SOURCE_REFS_MIN=1`)을 **완화 없이** 충족 — 사람 작성물의 출처는 작성자 본인. 감사 시 작성자 역추적 가능 |
| ③ | 소유자 편집 허용 범위 | 소유자는 **자기 에이전트의 `source_type=human` 문서만** 편집(PUT)·폐기(deprecate) 가능. distilled 문서와 approve/reject/restore/distill은 admin 전용 유지 | 정제물(distilled)은 원본 문서의 대리물 — 소유자 임의 수정 시 출처와 본문이 어긋남. human 문서는 본인 작성물이라 자기 관리가 자연스러움 |
| ④ | 열람 권한 | **현행 유지** — 로그인 사용자 전체 (`get_current_user`). tree API도 동일 | 기존 `GET /wiki`가 이미 이 정책 — 신규 확대가 아님. 에이전트 접근권 연동 강화는 org 스코프 결정(비교 문서 §5-1)과 함께 후속 |
| ⑤ | 지식 브라우저 진입점 | 트리 페이지 **`/agents/:agentId/knowledge`** + 문서 단독 뷰 **`/knowledge/:articleId`** 2개 라우트 | SourceCitation은 article id(chunk_id)만 보유 — agent_id를 모르므로 단독 문서 라우트가 필요. 문서 뷰에서 "전체 지식 보기"로 트리 페이지 연결 |
| ⑥ | 트리 API 응답 | **path 문자열 단위 그룹핑** (서버) + 계층 렌더링은 프론트가 `/` split | 서버는 GROUP BY 한 번으로 끝 — 트리 재귀 조립을 서버에 두면 스키마·테스트만 무거워짐 |

### 1.2 실코드 검증으로 확정된 제약

| 제약 | 내용 | 설계 반영 |
|------|------|----------|
| `DocumentSource`에 metadata 없음 | 프론트 채팅 출처 타입은 `{content, source, chunk_id, score}`뿐 (`types/chat.ts:6-11`) — 위키 title이 프론트에 안 옴 | 배지 라벨은 고정 문구("📖 위키 근거"), title은 문서 뷰에서 표시. **백엔드 계약 무변경 유지** |
| 위키 결과의 chunk_id = article id | `_to_result()`가 `id=article.id`로 매핑 (`wiki_first_search_use_case.py:67`) | `source==="wiki"`인 출처의 chunk_id로 `/knowledge/{chunk_id}` 직행 가능 |
| 라우트 선언 순서 | `GET /wiki/{id}`가 이미 존재 — `/wiki/tree`를 **`/{id}`보다 먼저 선언**하지 않으면 "tree"가 id로 매칭됨 | wiki_router에서 tree 라우트를 `get_wiki` 위에 배치 + 회귀 테스트 |
| 에이전트 소유자 필드 | `agent_definition.user_id` (String(100)) — `AgentAccessPolicy`가 `agent_owner_id`로 소비 | 소유자 판정은 agent 조회 → `user_id` 비교. 필드명 혼동 주의(owner_id 아님) |
| 편집 요청의 editor_id | 기존 `EditWikiRequest.editor_id`는 body 신뢰 | 인가는 **인증 사용자 기준**으로 수행하고 editor_id 기록도 인증 사용자로 통일(body 값은 하위호환 위해 수용하되 무시) |

---

## 2. Architecture

```
[프론트]
 SourceCitation ── source==="wiki" ──▶ /knowledge/:articleId (문서 뷰)
                                            │ "전체 지식 보기"
 AgentKnowledgePage (/agents/:agentId/knowledge)
   ├─ 트리 패널 (path 폴더)                    ├─ GET /api/v1/wiki/tree?agent_id=
   ├─ 문서 뷰 패널                            ├─ GET /api/v1/wiki/{id}
   └─ [소유자만] 작성/수정/폐기 폼              ├─ POST /api/v1/wiki
                                              ├─ PUT /api/v1/wiki/{id}
                                              └─ PATCH /api/v1/wiki/{id}/deprecate

[백엔드 — Thin DDD]
 interfaces   wiki_router: POST "" · GET /tree (── /{id}보다 먼저) · PUT·deprecate 인가 완화
 application  HumanWikiWriteUseCase (생성/편집/폐기 + 소유자 인가)
              WikiQueryUseCase.list_tree (path 그룹핑)
 domain       WikiPolicy 확장: validate_path · can_manage · HUMAN_SOURCE_PREFIX
              WikiArticle: path 필드 추가
 infrastructure  WikiArticleModel.path 컬럼 · repository 트리 그룹핑 쿼리
                 (기존 save/update의 Qdrant 색인 경로 재사용 — human 문서도 즉시 색인)

[DB]  V051: ALTER wiki_article ADD path VARCHAR(255) NULL,
            ADD INDEX idx_wiki_agent_path (agent_id, path)
```

인가 모델 (③·④ 확정 반영):

| 행위 | admin | 소유자(본인 에이전트) | 일반 사용자 |
|------|:-----:|:---------------------:|:-----------:|
| 목록/단건/트리 조회 | ✅ | ✅ | ✅ (현행 유지) |
| human 문서 생성 | ✅ | ✅ | ✗ 403 |
| human 문서 편집/폐기 | ✅ | ✅ | ✗ 403 |
| distilled 문서 편집 | ✅ | ✗ 403 | ✗ 403 |
| approve/reject/restore/distill | ✅ | ✗ | ✗ |

---

## 3. Detailed Design

### 3-1. DB — V051 마이그레이션

```sql
-- V051__alter_wiki_article_add_path.sql
-- wiki-user-facing: 지식 트리(가상 폴더) 분류 경로.
-- NULL = 미분류(기존 행 전부). FK/COLLATE 없음 (V037 주석 선례), ENGINE 변경 없음.
ALTER TABLE wiki_article
    ADD COLUMN path VARCHAR(255) NULL COMMENT '가상 폴더 경로 예: 여신/한도',
    ADD INDEX idx_wiki_agent_path (agent_id, path);
```

기존 행 백필 없음(Plan 6.2 확정 — NULL은 "미분류"로 노출).

### 3-2. Domain

**`WikiArticle`** (entity.py): 필드 추가 — `path: str | None = None`.

**`WikiPolicy`** (policies.py) 추가 상수·함수:

```python
HUMAN_SOURCE_PREFIX = "human:"
PATH_MAX_LEN = 255
PATH_MAX_DEPTH = 3          # "a/b/c"까지
PATH_SEGMENT_MAX = 30       # 세그먼트당 30자

@staticmethod
def validate_path(path: str | None) -> None:
    """None 허용(미분류). 위반 시 ValueError:
    빈 세그먼트(선행/후행/연속 '/'), 깊이 초과, 세그먼트 길이 초과, 전체 길이 초과."""

@staticmethod
def human_source_ref(user_id: str) -> str:
    """f"{HUMAN_SOURCE_PREFIX}{user_id}" — 출처 불변식을 충족하는 사람 출처 표기."""

@staticmethod
def can_manage(article: WikiArticle, actor_id: str, actor_is_admin: bool,
               agent_owner_id: str) -> bool:
    """편집/폐기 인가: admin은 항상, 소유자는 human 문서만.
    (approve/reject/restore는 이 함수를 타지 않음 — admin 전용 유지)"""
    if actor_is_admin:
        return True
    return (
        actor_id == agent_owner_id
        and article.source_type == WikiSourceType.HUMAN
    )
```

`validate_for_creation`은 무변경 — human 문서도 동일 불변식 통과 (source_refs는 `human_source_ref()`로 충족, 결정 ②).

### 3-3. Application

**`HumanWikiWriteUseCase`** (신규 — `src/application/wiki/human_write_use_case.py`)

```python
class HumanWikiWriteUseCase:
    def __init__(self, wiki_repo: WikiArticleRepository,
                 agent_repo,          # AgentDefinitionRepository — 소유자 조회용
                 logger: LoggerInterface): ...

    async def create(self, agent_id, title, content, path, actor_id,
                     actor_is_admin, request_id) -> WikiArticle:
        # 1) agent 조회 → 없으면 ValueError("에이전트를 찾을 수 없습니다")→404
        # 2) 인가: actor_is_admin or actor_id == agent.user_id — 아니면 PermissionError→403
        # 3) WikiPolicy.validate_path(path)
        # 4) WikiArticle(source_type=HUMAN, source_refs=[human_source_ref(actor_id)],
        #                status=APPROVED, confidence=0.5,       # 결정 ① 즉시 승인
        #                editor_id=actor_id, reviewer_id=actor_id, path=path)
        # 5) validate_for_creation → repo.save (MySQL + Qdrant 색인 기존 경로)

    async def edit(self, article_id, title, content, path, actor_id,
                   actor_is_admin, request_id) -> WikiArticle:
        # 조회 → agent 조회 → can_manage 검증(PermissionError→403)
        # → validate_path → apply_edit(+path 갱신, version++) → repo.update

    async def deprecate(self, article_id, actor_id, actor_is_admin,
                        request_id) -> WikiArticle:
        # 조회 → can_manage → validate_transition → mark_deprecated → repo.update
```

- 세션 규칙: 두 repo(wiki·agent)는 **동일 세션**으로 주입 (한 UseCase 한 세션 — CLAUDE.md 금지사항 준수). DI는 main.py `create_wiki_factories()`에 per-request 팩토리 추가.
- 기존 `WikiReviewUseCase`는 무변경 (admin 전용 경로 회귀 방지). 라우터의 PUT/deprecate가 신규 유스케이스로 갈아타되, admin 요청도 동일 유스케이스로 처리(can_manage가 admin 통과).

**`WikiQueryUseCase.list_tree`** (기존 유스케이스에 메서드 추가)

```python
async def list_tree(self, agent_id: str, request_id: str) -> list[TreeGroup]:
    # repo.list_tree(agent_id): SELECT path, id, title, status, source_type, updated_at
    #   WHERE agent_id=? ORDER BY path IS NULL, path, updated_at DESC  (본문 제외)
    # path 문자열 단위 그룹핑(결정 ⑥) — 계층 조립은 프론트
```

**distill 기본 path** (`DistillToWikiUseCase` 소폭 수정): 생성 시 `path=collection_name` 부여 (FR-10). 기존 파라미터·응답 계약 무변경.

### 3-4. Interfaces — wiki_router 변경

```python
# 신규 (※ GET /tree는 반드시 GET /{id} 선언보다 위에)
@router.get("/tree", response_model=WikiTreeResponse)
async def wiki_tree(agent_id: str, _user=Depends(get_current_user), ...): ...

@router.post("", response_model=WikiArticleResponse, status_code=201)
async def create_wiki(body: CreateWikiRequest,
                      user: User = Depends(get_current_user), ...):
    # HumanWikiWriteUseCase.create(..., actor_id=user.id,
    #                              actor_is_admin=user.role=="admin")
    # PermissionError→403, "찾을 수 없"→404, 그 외 ValueError→422

# 인가 완화 (admin → 로그인 사용자, 유스케이스에서 can_manage 인가)
@router.put("/{id}")           # _admin 의존성 제거 → get_current_user
@router.patch("/{id}/deprecate")  # 동일
# approve / reject / restore / distill — require_role("admin") 무변경
```

**api_schemas.py**:

```python
class CreateWikiRequest(BaseModel):
    agent_id: str
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=8000)
    path: str | None = None
    valid_until: datetime | None = None

class WikiTreeItem(BaseModel):
    id: str; title: str; status: str; source_type: str; updated_at: datetime | None

class WikiTreeGroup(BaseModel):
    path: str | None            # None = "미분류"
    items: list[WikiTreeItem]

class WikiTreeResponse(BaseModel):
    agent_id: str; groups: list[WikiTreeGroup]; total: int

# WikiArticleResponse · to_response에 path 필드 추가
# EditWikiRequest에 path: str | None 추가 (editor_id는 하위호환 수용·서버는 인증 사용자 사용)
```

에러 계약: 401(미인증) / 403(비소유자·distilled 편집 시도) / 404(agent·article 없음) / 422(불변식·path 위반).

### 3-5. Frontend

**라우팅** (App 라우터):
- `/agents/:agentId/knowledge` → `AgentKnowledgePage` (트리 + 문서 패널 + 소유자 폼)
- `/knowledge/:articleId` → `KnowledgeArticlePage` (단독 문서 뷰 — SourceCitation 착지점, "전체 지식 보기" 링크로 트리 이동)

**constants/api.ts** 추가:

```ts
WIKI_CREATE: '/api/v1/wiki',
WIKI_TREE: '/api/v1/wiki/tree',
```

**types/wiki.ts**: `WikiArticle`에 `path: string | null`, `CreateWikiRequest`, `WikiTreeGroup`, `WikiTreeResponse` 추가 (백엔드 스키마와 1:1 — §4-1 계약 동기화).

**services/wikiService.ts + hooks/useWiki.ts**: `createArticle`/`getTree` 서비스, `useWikiTree(agentId)`, `useCreateWiki`, (기존 `useUpdateArticle`·`useDeprecateArticle` 재사용 — 엔드포인트 동일). 뮤테이션 성공 시 기존 패턴대로 wiki 쿼리 무효화 + tree 키 포함.

**SourceCitation.tsx**: `source === "wiki"` 분기 —

```tsx
// 위키 출처: 아이콘·색 구분 배지 + 클릭 시 문서 뷰 이동
<button onClick={() => navigate(`/knowledge/${source.chunk_id}`)} ...>
  📖 위키 근거 <span>{Math.round(source.score * 100)}%</span>
</button>
```

라벨은 고정 문구(§1.2 제약 — title 미전달). 비위키 출처 렌더링은 무변경.

**AgentKnowledgePage 구성**: WikiPage의 Table+DetailPanel 패턴 재사용하되 사용자용 read-only. 트리 패널은 `groups[].path`를 `/` split해 폴더 계층 렌더. 소유자 판정: 에이전트 상세 응답의 `user_id` === 현재 사용자 → 작성/수정/폐기 UI 노출(서버가 최종 인가 — 프론트는 표시 제어만). 작성 폼: 제목·본문·path(기존 path 자동완성 datalist).

### 3-6. 사용자 흐름 (E2E 시나리오)

```
[소유자] /agents/A/knowledge → "문서 작성" → 제목·본문·path 입력 → 저장(즉시 approved)
   → use_wiki_first=true 도구가 있는 에이전트 A에게 관련 질문
   → 답변 출처에 "📖 위키 근거" 배지 → 클릭 → /knowledge/{id} 문서 뷰 확인
[일반 사용자] 같은 트리를 읽기 전용으로 탐색 (작성 UI 미노출, POST 시도 시 403)
```

---

## 4. Test Plan (TDD — Red 먼저 작성)

### 백엔드 (pytest — Windows 격리 실행 기준)

| 파일 | 케이스 |
|------|--------|
| `tests/domain/wiki/test_wiki_policies.py` (확장) | validate_path: 정상/None/빈 세그먼트/깊이 4/세그먼트 31자/전체 256자 · human_source_ref 형식 · can_manage 매트릭스(admin×human/distilled, owner×human/distilled, 타인) |
| `tests/application/wiki/test_human_write_use_case.py` (신규) | create: 즉시 approved+reviewer/editor=작성자+source_refs=`human:{id}` · 비소유자 PermissionError · agent 미존재 ValueError · path 검증 위임 · edit: human 소유자 성공(version++), distilled 소유자 거부, admin은 둘 다 성공 · deprecate 전이 검증 |
| `tests/application/wiki/test_wiki_query_tree.py` (신규) | path 그룹핑·NULL 미분류 그룹·본문 미포함·빈 결과 |
| `tests/application/wiki/test_distill_use_case.py` (확장) | 생성 문서에 path=collection_name 부여 |
| `tests/api/test_wiki_router.py` (확장) | POST 201/401/403/404/422 · **GET /tree가 /{id}에 잡히지 않음**(선언 순서 회귀) · PUT 소유자 성공·비소유자 403·admin 기존 동작 회귀 0 · approve 등 admin 전용 경로 무변경 회귀 |

### 프론트 (Vitest + MSW — `--pool=threads`, 파일별 3종 훅)

| 파일 | 케이스 |
|------|--------|
| `SourceCitation.test.tsx` (확장) | source="wiki" 배지 렌더·클릭 내비게이션 · 일반 출처 렌더 회귀 |
| `AgentKnowledgePage/index.test.tsx` (신규) | 트리 렌더(폴더 계층·미분류) · 문서 선택→뷰 · 소유자만 작성 폼 노출 · 작성 성공 시 트리 갱신 |
| `KnowledgeArticlePage.test.tsx` (신규) | 문서 로드·404 처리·트리 링크 |
| `useWiki.test.ts` (확장) | tree/create 훅 계약 + 무효화 |

---

## 5. Implementation Order

1. V051 마이그레이션 + `WikiArticleModel.path` + entity `path` 필드
2. `WikiPolicy` 확장 (validate_path·human_source_ref·can_manage) — 도메인 테스트 먼저
3. `HumanWikiWriteUseCase` + `list_tree` + distill 기본 path — 유스케이스 테스트 먼저
4. `api_schemas` 확장 + `wiki_router` (tree 선언 순서 주의) + main.py DI 팩토리 — 라우터 테스트 먼저
5. 프론트 계약 동기화: constants → types → services → hooks (MSW 테스트 먼저)
6. `SourceCitation` 위키 배지 분기
7. `KnowledgeArticlePage` → `AgentKnowledgePage` (트리+뷰+소유자 폼) → 라우트 등록
8. `/verify-architecture` · `/verify-tdd` · `/verify-logging` → `/pdca analyze wiki-user-facing`

---

## 6. Plan 리스크 해소 매핑

| Plan 리스크 | 설계 해소 |
|-------------|-----------|
| 즉시 approved 시 저품질 지식 노출 | 결정 ①: agent 스코프 한정 + deprecate 즉시 회수 + 감사 필드 기록. org 전파는 본 기능에 없음 |
| human source_refs 불변식 충돌 | 결정 ②: `human:{user_id}` — 불변식 완화 없이 충족 (`validate_for_creation` 무변경) |
| 열람 권한 확대 우려 | 결정 ④: 현행 정책 그대로 — 신규 확대 없음, 문서에 명시 |
| path 트리 난립 | `validate_path`(깊이 3·세그먼트 30자) + 작성 UI 자동완성 |
| admin 경로 회귀 | approve/reject/restore/distill 무변경 + PUT/deprecate는 can_manage가 admin 통과 보장 + 회귀 테스트 명시 |
| SourceCitation 회귀 | `source==="wiki"` 분기 추가만 — 기존 경로 테스트 유지 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-18 | Initial draft — Plan 이월 결정 6건 확정(즉시 approved·human: 출처·human만 소유자 편집·열람 현행 유지·라우트 2종·서버 그룹핑), 실코드 제약 5건 반영(DocumentSource metadata 부재·chunk_id=article id·tree 선언 순서·agent user_id 필드·editor_id 인증 통일) | 배상규 |
