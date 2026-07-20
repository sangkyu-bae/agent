# agent-memory Design Document (Phase 1)

> **Plan**: `docs/01-plan/features/agent-memory.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-18
> **Status**: Draft
> **소스 기준**: master 워킹트리 실코드 (general_chat/use_case.py · prompt_rendering.py · auth_context.py · config.py · search_history_repository.py · SettingsPage · App.tsx 정독)

---

## 1. Overview

Phase 1 범위: 사용자 수동 등록 메모리(CRUD + 관리 UI) + General Chat 시스템 프롬프트 상주 주입(하드캡).
자동 추출·정합기·org 스코프는 Phase 2/3 — 스키마(tier/scope/status/source_run_id/confidence)만 선반영.

### 1.1 Plan에서 이월된 결정 5건 — 확정

| # | 결정 대상 | 확정안 | 근거 |
|---|-----------|--------|------|
| ① | DDL·인덱스 | V050, `idx_memory_user_status (user_id, status)` 복합 인덱스, enum류는 VARCHAR(MySQL ENUM 미사용 — wiki_article 선례), FK 없음 | 주입 경로 쿼리가 항상 `WHERE user_id=? AND status='active'` — 단일 인덱스로 커버 |
| ② | CRUD 에러 계약 | 401 미인증 / **404 타인·미존재**(403 아님 — 존재 은닉) / 422 검증(타입·길이·개수 상한) | 타인 메모리는 존재 자체를 노출하지 않음 — 리소스 은닉 원칙 |
| ③ | 주입 지점·시그니처 | `_create_agent(tools, auth_ctx, memory_block: str = "")` — `prompt = render_user_context_block(auth_ctx) + memory_block + _SYSTEM_PROMPT`. 블록 조립은 `stream()`에서 agent 생성 직전 1회(비동기) | **agent-user-context의 prepend 선례 재사용** (`use_case.py:245`). `_create_agent`는 sync라 async 로드는 호출부에서 수행 |
| ④ | 토큰 근사 | **한글 최악 기준 1자≈1토큰 보수 근사** → 캡 = `memory_inject_token_cap`(기본 800) **문자** 예산으로 적용 | 정밀 카운트 불필요(캡의 목적은 폭주 방지). 한글 위주 도메인에서 과소추정(캡 초과)이 없는 방향으로 보수 설정 |
| ⑤ | 관리 UI 위치 | **`/settings` 라우트 신설 + SettingsPage 구현** — "AI가 기억하는 내용" 섹션이 첫 콘텐츠 | **실측 정정**: SettingsPage/index.tsx는 빈 스텁(0줄)이고 App.tsx 라우트에 없음 — Plan의 "기존 존재" 전제 수정. 신설이 곧 최소 작업 |

### 1.2 실코드 검증으로 확정된 제약·선례

| 제약/선례 | 내용 | 설계 반영 |
|-----------|------|----------|
| 프롬프트 prepend 선례 | `render_user_context_block(auth_ctx) + _SYSTEM_PROMPT` (`use_case.py:245`, 호출부 `:335`) | 메모리 블록을 두 항 사이에 삽입 — 사용자 정보 다음, 시스템 규칙 앞 |
| user_id 체계 | `GeneralChatRequest.user_id: str` (conversation 계열 String(255)와 동일). `AuthContext.user_id`는 int — **메모리 키는 request.user_id(str)** 사용 | CRUD 라우터는 `str(user.id)` (agent_builder_router `:176` 선례와 동일 변환) |
| 앱 싱글톤 + 세션 문제 | GeneralChatUseCase 수명에서 요청별 세션이 필요 — `RunScopedWikiSearch`/RunTracker가 동일 문제를 **session_factory per-call 패턴**으로 해결(가이드 §6-2) | MemoryContextAssembler도 동일 패턴: 호출마다 짧은 세션 열고 닫음 |
| whitelist 원칙 | user-context 블록은 employee_no/email/user_id 노출 금지 | 메모리 블록은 사용자가 직접 쓴 content만 렌더 — 시스템 필드 미노출 |
| config 패턴 | `Settings(BaseSettings)`에 int 필드 + 기본값 (`config.py`) | `memory_max_active_per_user: int = 30`, `memory_inject_token_cap: int = 800` 추가 |
| CRUD 저장소 선례 | `SearchHistoryRepository(session, logger)` 경량 패턴 | MemoryRepository 동일 구조 (MySQLBaseRepository 불필요한 소형 CRUD) |

---

## 2. Architecture

```
[프론트]  /settings (신설 라우트) → SettingsPage
            └─ "AI가 기억하는 내용" 섹션: 목록(타입 뱃지)·추가 폼·인라인 수정·삭제·상한 안내
                 useMemories 훅 ── GET/POST/PATCH/DELETE /api/v1/memories

[백엔드 — Thin DDD]
 interfaces   memory_router (신설): 인증 사용자 본인 것만, 401/404/422
 application  MemoryCrudUseCase (생성/목록/수정/삭제 + 상한 검증)
              MemoryContextAssembler (session_factory per-call — RunTracker 패턴)
 domain       Memory 엔티티 · MemoryPolicy(타입/길이/상한/우선순위/캡 — 순수 규칙)
              MemoryRepositoryInterface
 infrastructure  MemoryModel(V050) · MemoryRepository(session, logger)

[주입 — General Chat 한정 (차트 렌더링 선례)]
 stream():
   memory_block = await assembler.build_block(request.user_id, request_id)  # 실패 시 "" (격리)
   agent = self._create_agent(tools, auth_ctx=auth_ctx, memory_block=memory_block)
 _create_agent():
   prompt = render_user_context_block(auth_ctx) + memory_block + _SYSTEM_PROMPT
```

## 3. Detailed Design

### 3-1. DB — V050 마이그레이션 (결정 ①)

```sql
-- V050__create_agent_memory.sql
-- agent-memory Phase 1: 사용자 수동 메모리. Phase 2/3 확장 컬럼 선반영.
-- FK/COLLATE 명시 없음 (V037 주석 선례), ENGINE=InnoDB.
CREATE TABLE agent_memory (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    scope         VARCHAR(10)  NOT NULL DEFAULT 'user'   COMMENT 'user|org (Phase1은 user 고정)',
    user_id       VARCHAR(255) NULL                      COMMENT 'scope=user일 때 소유자',
    tier          TINYINT      NOT NULL DEFAULT 0        COMMENT '0=상주 주입, 1=온디맨드(Phase3)',
    mem_type      VARCHAR(20)  NOT NULL                  COMMENT 'profile|preference|domain_term|episode',
    content       VARCHAR(500) NOT NULL,
    source_run_id VARCHAR(64)  NULL                      COMMENT '자동 추출 출처(Phase2) — Phase1은 NULL',
    confidence    TINYINT      NOT NULL DEFAULT 100      COMMENT '수동 입력=100',
    status        VARCHAR(10)  NOT NULL DEFAULT 'active' COMMENT 'pending|active|rejected|expired',
    expires_at    DATETIME     NULL,
    created_at    DATETIME     NOT NULL,
    updated_at    DATETIME     NOT NULL,
    INDEX idx_memory_user_status (user_id, status)
) ENGINE=InnoDB;
```

### 3-2. Domain

**엔티티** (`src/domain/memory/entity.py`):

```python
class MemoryScope(str, Enum): USER = "user"; ORG = "org"
class MemoryType(str, Enum):
    PROFILE = "profile"; PREFERENCE = "preference"
    DOMAIN_TERM = "domain_term"; EPISODE = "episode"
class MemoryStatus(str, Enum):
    PENDING = "pending"; ACTIVE = "active"
    REJECTED = "rejected"; EXPIRED = "expired"

@dataclass
class Memory:
    id: int | None
    scope: MemoryScope
    user_id: str | None
    tier: int
    mem_type: MemoryType
    content: str
    source_run_id: str | None = None
    confidence: int = 100
    status: MemoryStatus = MemoryStatus.ACTIVE
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

**정책** (`src/domain/memory/policies.py`) — 순수 함수만:

```python
class MemoryPolicy:
    CONTENT_MAX = 500
    # 주입 우선순위 (작을수록 먼저) — 동순위는 최신(updated_at desc)
    TYPE_PRIORITY = {PROFILE: 0, DOMAIN_TERM: 1, PREFERENCE: 2, EPISODE: 3}
    # 결정 ④: 한글 최악 1자≈1토큰 보수 근사 — 캡은 문자 예산으로 적용
    CHARS_PER_TOKEN = 1

    @staticmethod
    def validate_content(content: str) -> None:
        """빈 문자열/500자 초과 시 ValueError."""

    @staticmethod
    def validate_active_count(current_count: int, max_count: int) -> None:
        """상한 도달 시 ValueError('메모리 개수 상한...') — 라우터에서 422."""

    @staticmethod
    def sort_for_injection(memories: list[Memory]) -> list[Memory]:
        """TYPE_PRIORITY asc → updated_at desc."""

    @staticmethod
    def truncate_to_budget(memories: list[Memory], token_cap: int) -> tuple[list[Memory], bool]:
        """정렬된 목록을 문자 예산(token_cap × CHARS_PER_TOKEN) 내로 절단.
        Returns (포함 목록, 절단 발생 여부) — 절단 시 호출부가 debug 로그(FR-05)."""
```

**저장소 인터페이스** (`src/domain/memory/interfaces.py`):

```python
class MemoryRepositoryInterface(ABC):
    async def save(self, memory: Memory, request_id: str) -> Memory: ...
    async def find_by_id(self, memory_id: int, request_id: str) -> Memory | None: ...
    async def find_active_by_user(self, user_id: str, request_id: str) -> list[Memory]: ...
    async def count_active_by_user(self, user_id: str, request_id: str) -> int: ...
    async def update(self, memory: Memory, request_id: str) -> Memory: ...
    async def delete(self, memory_id: int, request_id: str) -> bool: ...
```

### 3-3. Application

**`MemoryCrudUseCase`** (`src/application/memory/crud_use_case.py`) — repo·logger 주입(세션은 라우터 DI):

```python
async def create(self, user_id, mem_type, content, request_id) -> Memory:
    # validate_content → count_active_by_user → validate_active_count(settings 상한)
    # → Memory(scope=USER, tier=0, status=ACTIVE, confidence=100) 저장
async def list_active(self, user_id, request_id) -> list[Memory]:
async def update(self, user_id, memory_id, mem_type, content, request_id) -> Memory:
    # find_by_id → None 또는 소유자 불일치 → ValueError("찾을 수 없습니다")  # 결정 ② 404 은닉
async def delete(self, user_id, memory_id, request_id) -> None:  # 동일 소유 검증
```

**`MemoryContextAssembler`** (`src/application/memory/context_assembler.py`) — 결정 ③·격리(FR-07):

```python
class MemoryContextAssembler:
    """General Chat 주입 블록 조립 — RunScopedWikiSearch와 동일한 run-scoped 세션 패턴."""

    def __init__(self, session_factory, logger, token_cap: int): ...

    async def build_block(self, user_id: str, request_id: str) -> str:
        try:
            async with self._session_factory() as session:
                repo = MemoryRepository(session, self._logger)
                memories = await repo.find_active_by_user(user_id, request_id)
            if not memories:
                return ""                       # FR-06: 빈 헤더 금지
            ordered = MemoryPolicy.sort_for_injection(memories)
            included, truncated = MemoryPolicy.truncate_to_budget(ordered, self._token_cap)
            if truncated:
                self._logger.debug("memory block truncated", request_id=request_id, ...)
            self._logger.info("memory block injected", request_id=request_id,
                              count=len(included))
            return self._render(included)
        except Exception:
            self._logger.warning("memory load failed — inject skipped",
                                 request_id=request_id, exc_info=True)   # FR-07 격리
            return ""
```

**블록 렌더 형식** (FR-09 보수적 지침 포함, user-context 블록과 동일한 `---` 구분자):

```
[사용자 메모리]
다음은 사용자가 직접 등록한 배경 정보입니다. 답변에 자연스럽게 반영하되,
내용이 현재 질문과 모순되거나 불확실하면 사용자에게 확인하세요.
- (프로필) 여신 심사팀 소속
- (용어) '한도'는 동일인 여신한도를 의미
- (선호) 근거 조문 번호 인용 선호
---

```

타입 라벨: profile=프로필 · domain_term=용어 · preference=선호 · episode=참고.

**general_chat 통합** (기존 회귀 0 원칙):

```python
# __init__: memory_assembler: MemoryContextAssembler | None = None  ← optional (기존 테스트 무회귀)
# stream() — _create_agent 호출(:335) 직전:
memory_block = ""
if self._memory_assembler is not None:
    memory_block = await self._memory_assembler.build_block(request.user_id, request_id)
agent = self._create_agent(tools, auth_ctx=auth_ctx, memory_block=memory_block)
# _create_agent(:245):
prompt = render_user_context_block(auth_ctx) + memory_block + _SYSTEM_PROMPT
```

### 3-4. Interfaces — `memory_router` (신설, 결정 ②)

```python
router = APIRouter(prefix="/api/v1/memories", tags=["Memory"])
# 전부 get_current_user, user_id = str(user.id)

GET    ""            → MemoryListResponse {items, total, max_count}   # max_count로 프론트 상한 안내
POST   ""            → 201 MemoryResponse     # body: {mem_type, content}
PATCH  "/{memory_id}" → MemoryResponse        # body: {mem_type?, content?}
DELETE "/{memory_id}" → 204

# 에러 매핑: ValueError("찾을 수 없") → 404, 그 외 ValueError(길이·타입·상한) → 422
```

스키마 (`src/interfaces/schemas/memory_schemas.py` — 기존 인터페이스 스키마 위치 관례):
`MemoryResponse {id, mem_type, content, created_at, updated_at}` — scope/tier/status 등 내부 필드는 Phase 1 응답에서 제외(수동 active만 존재), `CreateMemoryRequest`, `UpdateMemoryRequest`.

**config** (`src/config.py`): `memory_max_active_per_user: int = 30`, `memory_inject_token_cap: int = 800`.
**DI** (`main.py`): `create_memory_factories()` — crud per-request 세션 팩토리 + assembler는 앱 기동 시 1개 생성해 GeneralChatUseCase 생성부에 주입.

### 3-5. Frontend (결정 ⑤ — SettingsPage 신설 구현)

- **라우트**: App.tsx에 `/settings` 추가 (보호 라우트 영역) + `SettingsPage` import
- **진입점**: 기존 레이아웃 네비게이션(AgentChatLayout)에 설정 메뉴 1건 — Do에서 레이아웃 실코드 확인 후 최소 추가
- **계약 동기화**: `constants/api.ts` `MEMORY_LIST/CREATE/DETAIL(id)`, `types/memory.ts`(MemoryType 4종 라벨 포함), `services/memoryService.ts`, `hooks/useMemories.ts`(useMemories/useCreateMemory/useUpdateMemory/useDeleteMemory — 뮤테이션 성공 시 memories 키 무효화), `queryKeys.memories`
- **SettingsPage 구성**:
  - 섹션 헤더 "AI가 기억하는 내용" + 카운터 `{total}/{max_count}`
  - 목록: 타입 뱃지(프로필/용어/선호/참고) + content + 수정/삭제 버튼
  - 추가 폼: 타입 select + content textarea(500자 카운터) — 상한 도달 시 폼 비활성 + 안내
  - 인라인 수정: 항목 클릭 → 폼 전환(제출 시 PATCH)
  - 422 에러 표면화(상한/길이) — 문구 그대로 표시
- **MSW**: memories 핸들러 4종 + 상한 시나리오 오버라이드

### 3-6. 사용자 흐름 (E2E 시나리오)

```
/settings → "용어: '한도'는 동일인 여신한도" 등록 → General Chat에서 "한도 관련 규정 알려줘"
→ (LangSmith trace) 시스템 프롬프트에 [사용자 메모리] 블록 확인 → 답변이 용어 문맥 반영
→ 메모리 삭제 → 재질문 시 블록 미주입 확인
```

---

## 4. Test Plan (TDD — Red 먼저 작성)

### 백엔드 (pytest — Windows 격리 실행 기준)

| 파일 | 케이스 |
|------|--------|
| `tests/domain/memory/test_policies.py` (신규) | validate_content(빈/500자/초과) · validate_active_count(미만/도달) · sort_for_injection(타입 우선순위→최신순) · truncate_to_budget(예산 내 전부/절단 발생·플래그/빈 목록) |
| `tests/application/memory/test_crud_use_case.py` (신규) | create(정상·상한 422 경로·길이 검증) · list_active 본인만 · update/delete(본인 성공·타인 소유 "찾을 수 없"·미존재) |
| `tests/application/memory/test_context_assembler.py` (신규) | 정렬·캡 절단·0건 빈 문자열(헤더 금지)·**repo 예외 시 "" 반환 + warning**(FR-07)·렌더 형식(보수 지침 문구 포함) |
| `tests/application/general_chat/` (확장) | `_create_agent`에 memory_block 전달 시 프롬프트 순서(user_ctx→memory→system) · assembler None이면 기존 프롬프트 불변(회귀) · assembler 실패에도 스트림 정상 |
| `tests/api/test_memory_router.py` (신규) | GET 200(max_count 포함)/POST 201/PATCH 200/DELETE 204 · 401 · 타인/미존재 404 · 상한·길이 422 |

### 프론트 (Vitest + MSW — `--pool=threads`, 파일별 3종 훅)

| 파일 | 케이스 |
|------|--------|
| `useMemories.test.ts` (신규) | 목록/생성/수정/삭제 훅 계약 + 무효화 |
| `SettingsPage/index.test.tsx` (신규) | 목록·타입 뱃지 렌더 · 추가 폼 제출 → 목록 갱신 · 인라인 수정 · 삭제 · 상한 도달 시 폼 비활성+안내 · 422 에러 표면화 |

---

## 5. Implementation Order

1. V050 마이그레이션 + `MemoryModel` + domain(entity·policies·interfaces) — 정책 테스트 먼저
2. `MemoryRepository` (search_history 경량 패턴)
3. `MemoryCrudUseCase` + `MemoryContextAssembler` — 유스케이스·조립기 테스트 먼저
4. `memory_schemas` + `memory_router` + config 2키 + main.py DI — 라우터 테스트 먼저
5. general_chat 통합 (`_create_agent` 파라미터 + stream 호출부) — 통합 테스트 먼저, 기존 테스트 회귀 0 확인
6. 프론트 계약 동기화: constants → queryKeys → types → services → hooks (MSW 테스트 먼저)
7. SettingsPage 구현 + `/settings` 라우트 + 네비 진입점
8. `/verify-architecture` · `/verify-tdd` · `/verify-logging` → `/pdca analyze agent-memory`

---

## 6. Plan 리스크 해소 매핑

| Plan 리스크 | 설계 해소 |
|-------------|-----------|
| 주입 메모리의 답변 오염 | 블록에 보수 지침 문구 고정(FR-09) + 본인 등록·삭제 투명 구조 |
| 토큰 증가 폭주 | 개수 상한(config 30) + 문자 예산 캡(config 800, 1자≈1토큰 보수 근사) — 구조적 차단 |
| general_chat 회귀 | optional 의존성(None 기본) + prepend 1항 삽입만 + 실패 격리("" 반환) + 기존 테스트 전체 회귀 확인 |
| Phase 2/3 스키마 재작업 | tier/scope/status/source_run_id/confidence 선반영 (V050) |
| 토큰 카운팅 오차 | 결정 ④ — 정밀 카운트 포기, 한글 최악 보수 근사(과소추정 없음) |
| user_id 타입 불일치 | request.user_id(str) 단일 키 — CRUD도 str(user.id) 동일 변환 (agent_builder 선례) |
| (신규 발견) SettingsPage 부재 | 결정 ⑤ — 빈 스텁 실측 확인, `/settings` 라우트+페이지 신설로 Plan 전제 정정 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-18 | Initial draft — 이월 결정 5건 확정(복합 인덱스·404 은닉·prepend 주입·보수 토큰 근사·SettingsPage 신설), 실코드 선례 6건 반영(agent-user-context prepend·RunScoped 세션 패턴·user_id str 체계 등) | 배상규 |
