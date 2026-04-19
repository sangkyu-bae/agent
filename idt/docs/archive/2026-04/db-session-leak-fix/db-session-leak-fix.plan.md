# Plan: db-session-leak-fix

> Feature: DB 세션 누수 및 커넥션 풀 고갈 수정
> Created: 2026-04-18
> Status: Plan
> 우선순위: Critical
> 관련 Task: CHAT-001, CONV-001, MYSQL-001

---

## 1. 문제 정의 (Problem Statement)

`POST /api/v1/chat` 호출 중 `GeneralChatUseCase._build_summarized_context` 단계에서
SQLAlchemy AsyncSession이 커넥션을 확보하지 못해 `flush()`가 실패한다.

```
[2026-04-17T07:44:52Z] ERROR GeneralChatUseCase failed
request_id : 3aee133b-e29a-4909-9233-35f51deab305
location   : use_case.py:execute:167

File "src/application/general_chat/use_case.py", line 195, in _build_summarized_context
    await self._summary_repo.save(summary)
File "src/infrastructure/persistence/repositories/conversation_summary_repository.py", line 42, in save
    await self._session.flush()
File "sqlalchemy/ext/asyncio/session.py", line 787, in flush
    await greenlet_spawn(self.sync_session.flush, objects=objects)
```

- 서버 기동 후 요청이 누적될수록 재현율이 높아진다(=전형적 풀 고갈 패턴).
- `_build_summarized_context` 분기(대화 턴 6개 초과)에서 주로 발생한다.

---

## 2. 근본 원인 분석 (Root Cause)

### 2-1. [Critical] 팩토리가 AsyncSession을 생성만 하고 close 하지 않는다

**파일**: `src/api/main.py :: create_general_chat_use_case_factory`
(동일 패턴이 `create_conversation_use_case_factory`, `create_history_use_case_factory`,
`create_agent_builder_factories`, `create_auth_factories`, AutoBuild 관련 팩토리 등 **전 팩토리에 존재**)

```python
# 현재 (문제 있음)
async def _factory() -> GeneralChatUseCase:
    session_factory = get_session_factory()
    message_repo = SQLAlchemyConversationMessageRepository(session_factory())   # 세션 A
    summary_repo = SQLAlchemyConversationSummaryRepository(session_factory())   # 세션 B
    ...
    mcp_repo = MCPServerRepository(session=session_factory(), logger=app_logger) # 세션 C
    ...
    return GeneralChatUseCase(message_repo=..., summary_repo=..., ...)
```

문제:
1. **세션 3개**를 한 요청에 만든다 (message, summary, mcp).
2. 어느 세션도 `async with` / `session.close()` 경로가 없다 → **요청 종료 후에도 커넥션이 풀로 반환되지 않는다**.
3. 풀 설정은 `pool_size=5, max_overflow=10` → 총 15 커넥션.
   - 요청 1회마다 3 커넥션 누수 → 약 5회 요청 후 풀 고갈.
   - 이후 요청의 `flush()`는 `pool_pre_ping`과 함께 새 커넥션 확보 대기 → 타임아웃/greenlet 실패.

### 2-2. [Critical] 같은 UseCase 안에서 repository 들이 서로 다른 세션을 공유하지 않는다

```python
message_repo = SQLAlchemyConversationMessageRepository(session_factory())  # 세션 A
summary_repo = SQLAlchemyConversationSummaryRepository(session_factory())  # 세션 B ← 별도 세션
```

반면 `create_conversation_use_case_factory`는 **동일 세션을 공유**한다:

```python
session = factory()
message_repo = SQLAlchemyConversationMessageRepository(session)   # 세션 공유
summary_repo = SQLAlchemyConversationSummaryRepository(session)   # 세션 공유
```

영향:
- 요약 저장(summary_repo) 과 메시지 저장(message_repo) 이 **다른 트랜잭션**에서 수행된다.
- 부분 실패 시 일관성이 깨진다 (요약은 저장됐는데 메시지는 실패 등).
- 세션이 N개 → 커넥션 풀 고갈도 N배 빨리 발생한다.

### 2-3. [High] Repository 가 `commit` 을 자체적으로 수행 (트랜잭션 경계 위반)

`SQLAlchemyConversationMessageRepository.save`:

```python
await self._session.flush()
await self._session.commit()   # ← 레포가 commit 함
```

vs `SQLAlchemyConversationSummaryRepository.save`:

```python
await self._session.flush()   # ← commit 없음
# refresh 호출
```

문제:
- 둘의 **정책이 일관되지 않다** → 어떤 save 는 커밋되고, 어떤 save 는 풀로 반환되지 않은 채 트랜잭션이 남는다.
- DDD 원칙상 **트랜잭션 경계는 Application/Interface 층**이 책임져야 한다(레포는 순수 조작만).
- 하나의 UseCase 안에서 repo 마다 자발적 commit → 원자성 불가.

### 2-4. [Medium] `refresh()` 가 불필요하게 호출되어 커넥션 점유 시간이 늘어난다

`save()` 가 `refresh(model)` 을 호출해 INSERT 된 행을 다시 SELECT 로 읽어온다.
대부분의 호출 시점에서 auto-assigned `id` 외에는 읽을 필요가 없는데, `refresh` 는
세션이 커넥션을 붙잡고 추가 RTT를 발생시킨다.

### 2-5. [Medium] `_factory` 호출당 세션 팩토리는 1번만 필요

팩토리에서 `get_session_factory()` 결과인 `async_sessionmaker` 자체는 재사용 가능하지만,
**매 호출에서 새 세션 3개**를 만든 뒤 묶어두는 현재 구조는 "요청 1 = 세션 1 = 트랜잭션 1" 이라는
FastAPI 권장 패턴을 벗어난다.

### 2-6. [추정, 확인 필요] 에러 스택이 잘려 최종 에러 메시지 확인 불가

제공된 로그는 `greenlet_spawn(self.sync_session.flush, ...)` 라인에서 끊겨 있다.
실제 최종 원인이 다음 중 어느 것인지는 수정 과정에서 재현 테스트로 확정한다:

1. `TimeoutError: QueuePool limit of size 5 overflow 10 reached` (풀 고갈)
2. `StatementError: (sqlalchemy.exc.InterfaceError) connection already closed`
3. `IllegalStateChangeError: Method 'close()' can't be called here`

→ 2-1 / 2-2 가 해결되면 세 경우 모두 사라질 것으로 예상.

---

## 3. 기능 범위 (Scope)

### In Scope

#### DB-FIX-A: 요청 스코프 AsyncSession 생명주기 통일 (필수)

- `get_session` dependency 가 이미 `async with factory() as session: yield; finally close()` 패턴으로
  존재함 → FastAPI `Depends(get_session)` 로 **세션 1 개를 요청마다 주입** 받도록 통일.
- 각 use case 팩토리는 `session: AsyncSession` 을 **인자로 받아** repository 를 조립한다.
- 세션은 FastAPI dependency 가 자동으로 close → 풀 고갈 해소.

대상 팩토리 (전수):
- `create_general_chat_use_case_factory`
- `create_conversation_use_case_factory`
- `create_history_use_case_factory`
- `create_auth_factories` (`_make_user_repo`, `_make_rt_repo`)
- `create_agent_builder_factories` (`_make_repo`)
- `_make_create_middleware_agent_uc` (auto build)
- MCP registry / agent repo 사용처

#### DB-FIX-B: UseCase 내 repository 는 동일 세션을 공유 (필수)

- `GeneralChatUseCase` 의 `message_repo`, `summary_repo`, `mcp_repo` 는 **같은 AsyncSession** 을 사용한다.
- UseCase 호출이 단일 트랜잭션 경계 안에서 실행되도록 한다.

#### DB-FIX-C: Repository 에서 commit 제거 (필수)

- `SQLAlchemyConversationMessageRepository.save` 의 `await session.commit()` 제거.
- Repository 는 `flush` 만 수행 (auto-assigned id 획득용).
- 트랜잭션 경계(commit/rollback)는 Interface/Application 층에서 관리.

#### DB-FIX-D: 요청 스코프 트랜잭션 미들웨어/Dependency (필수)

- `get_session` 에 `async with session.begin()` 블록을 추가, 또는
- UseCase 계층에 "UnitOfWork" 래퍼를 두어 정상 종료 시 commit, 예외 시 rollback.
- 택 1 (후보 설계):
  - **Option 1 (선호)**: `get_session` 에서 `async with session.begin()` 자동 트랜잭션.
    FastAPI 의존성 라이프사이클과 자연스럽게 맞물림.
  - **Option 2**: UseCase 가 `commit()` 을 명시 호출 (기존 코드 변경 범위 ↑).

#### DB-FIX-E: 불필요한 `refresh()` 축소 (권장)

- `save()` 반환값에서 모델 전체가 필요한 경우만 `refresh` 유지, 그 외엔 `flush` 로 얻은 id 만 사용.

#### DB-FIX-F: 회귀 방지 테스트 (필수, TDD)

- `tests/integration/test_db_session_lifecycle.py` 신규:
  1. 50 회 연속 `/api/v1/chat` 요청 후 풀의 `checkedin == pool_size`, `checkedout == 0` 인지 확인.
  2. 7 턴 이상 대화(요약 분기) 시 `flush()` 예외 없음 + `conversation_summary` 1 행 저장.
  3. UseCase 중간에 예외가 발생하면 `conversation_message` 0 행 + `conversation_summary` 0 행 (원자성).
- pytest + testcontainers(또는 .env 기반 로컬 MySQL) 사용. 도메인 레이어 mock 금지 규칙 준수.

### Out of Scope

- MySQL 자체 튜닝 (server-side `max_connections`, timeout 등) — 별도 이슈
- Qdrant / Redis 커넥션 풀 — 동일 클래스 문제 여부는 follow-up 으로 분리
- ORM → SQL 리포팅 레이어 재설계

---

## 4. 설계 방향 (High-level Design)

### 4-1. 레이어 책임 재정리

| 레이어 | 이전 | 개선 |
|--------|------|------|
| interfaces (FastAPI) | 세션 생성 + use case 조립 | `Depends(get_session)` 로 세션만 주입, use case 는 세션을 받는 팩토리가 조립 |
| application (UseCase) | 여러 repo, 트랜잭션 비관리 | 한 세션 = 한 트랜잭션, UoW 경계 명확 |
| infrastructure (Repository) | `flush + commit + refresh` | `add + flush` 만, commit 금지 |

### 4-2. 세션 주입 샘플 (after)

```python
# interfaces/dependencies/db.py  (신규 또는 기존 get_session 활용)
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():   # 자동 commit / rollback
            yield session

# api/main.py
def create_general_chat_use_case_factory():
    app_logger = get_app_logger()
    def _factory(session: AsyncSession = Depends(get_db_session)) -> GeneralChatUseCase:
        message_repo = SQLAlchemyConversationMessageRepository(session)
        summary_repo = SQLAlchemyConversationSummaryRepository(session)
        mcp_repo     = MCPServerRepository(session=session, logger=app_logger)
        ...
        return GeneralChatUseCase(message_repo=message_repo,
                                  summary_repo=summary_repo, ...)
    return _factory
```

### 4-3. Repository 변경 (after)

```python
async def save(self, message: ConversationMessage) -> ConversationMessage:
    model = ConversationMessageMapper.to_model(message)
    self._session.add(model)
    await self._session.flush()    # id 확보까지만, commit 금지
    return ConversationMessageMapper.to_entity(model)
```

---

## 5. 변경 파일 목록 (Impact)

| 경로 | 변경 내용 |
|------|-----------|
| `src/infrastructure/persistence/database.py` | `get_session` 에 `session.begin()` 추가 (또는 별도 `get_db_session`) |
| `src/infrastructure/persistence/repositories/conversation_repository.py` | `save()` 의 `commit()` 제거, `refresh()` 최소화 |
| `src/infrastructure/persistence/repositories/conversation_summary_repository.py` | `save()` 표준화 (flush 만), `delete_by_session` 확인 |
| `src/api/main.py` | 전 팩토리의 세션 생성 부위를 `Depends(get_db_session)` 기반으로 리팩토링 |
| `src/api/routes/general_chat_router.py` | 필요 시 `Depends(get_db_session)` 주입 정합성 확인 |
| `src/application/general_chat/use_case.py` | 변경 없음 (세션 소유권 상위로 이동) |
| `src/infrastructure/persistence/mysql_base_repository.py` | `save/delete` 에서 commit 부재 확인 (현재 OK) |
| `tests/integration/test_db_session_lifecycle.py` | 신규 — 풀 고갈/원자성 회귀 테스트 |

---

## 6. 수용 기준 (Acceptance Criteria)

- [ ] 50 회 연속 `/api/v1/chat` 요청 후 풀 상태: `checkedout == 0`, `checkedin == pool_size`
- [ ] 7 턴 이상 대화에서 `flush()` 예외 없이 요약이 저장된다
- [ ] UseCase 내부 예외 시 `conversation_message`, `conversation_summary` 어떤 테이블에도 partial row 가 남지 않는다
- [ ] 기존 회귀 테스트 전부 통과 (CONV-001, CHAT-001, AUTH-001, MYSQL-001)
- [ ] `print()` 추가 금지, `LOG-001` 준수
- [ ] Repository 내부에 `commit()` 호출이 하나도 남아있지 않다

---

## 7. 리스크 및 완화

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 다른 팩토리의 암묵적 commit 의존 | 중 | 전수 grep 후 테스트로 확인 |
| `session.begin()` 중첩(repo 에서 다시 begin) | 중 | `begin_nested()` 또는 flat transaction 규칙 문서화 |
| 동일 세션 공유 → 다른 테이블 락 충돌 | 낮음 | 대화 관련 테이블만 공유, MCP 조회는 read-only |
| 프론트엔드 영향 | 없음 | API 계약 변경 없음 |

---

## 8. 작업 순서 (To Do 예정)

1. **Red**: `test_db_session_lifecycle.py` 실패 테스트 작성 (풀 고갈 재현 / 원자성)
2. `get_db_session` dependency 정리 + `session.begin()` 적용
3. Repository 의 `commit()` 제거 + `refresh` 축소
4. `create_general_chat_use_case_factory` 를 세션 주입 방식으로 리팩토링
5. 나머지 팩토리(conversation, history, auth, agent_builder, auto_build, mcp_registry) 전수 리팩토링
6. **Green**: 신규 및 기존 테스트 통과 확인
7. **Refactor**: 중복 팩토리 패턴 추출 (ex. `build_with_session(session, factory_fn)`)
8. Gap 분석 (`/pdca analyze db-session-leak-fix`) → 90% 이상이면 report

---

## 9. 연관 Task 참조

- CHAT-001 (General Chat API) — 오류 발생 지점
- CONV-001 (Conversation Memory) — save/summary 로직 직접 관련
- MYSQL-001 (Base Repository) — 공통 레포 정책 근거
- LOG-001 (Logging) — 수정 과정의 로그 준수
