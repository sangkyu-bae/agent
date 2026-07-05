# DB Session & Transaction Rules (DB-001)

> 원본: CLAUDE.md §10

---

## 핵심 원칙

> **요청 1건 = AsyncSession 1개 = 트랜잭션 1건**

- 하나의 HTTP 요청은 **단 하나의** `AsyncSession` 을 사용한다.
- 하나의 세션은 **단 하나의** 트랜잭션 경계 안에서 실행된다.
- UseCase 내부의 모든 Repository 는 **동일한 세션**을 공유한다.

이 원칙을 위반하면 (1) 커넥션 풀 고갈, (2) 원자성 붕괴, (3) `flush()` greenlet 실패가 발생한다.

---

## 세션 주입 규칙

- FastAPI Dependency `get_session` 을 통해서만 세션을 얻는다.
- `get_session` 은 `async with factory() as session: async with session.begin(): yield session` 패턴으로 **자동 commit/rollback** 을 보장한다.
- `session_factory()` 를 팩토리/서비스 코드에서 직접 호출하여 세션을 만들지 않는다.
- UseCase 팩토리는 `session: AsyncSession = Depends(get_session)` 을 받아 repository 를 조립한다.

```python
# ✅ 권장
async def _factory(
    session: AsyncSession = Depends(get_session),
) -> SomeUseCase:
    repo_a = RepoA(session)    # 공유
    repo_b = RepoB(session)    # 공유
    return SomeUseCase(repo_a, repo_b)

# ❌ 금지 — 팩토리 내부에서 세션 생성 금지
async def _factory() -> SomeUseCase:
    factory = get_session_factory()
    repo_a = RepoA(factory())   # 세션 누수
    repo_b = RepoB(factory())   # 세션 분리 → 원자성 붕괴
    return SomeUseCase(repo_a, repo_b)
```

---

## Repository 트랜잭션 규칙

- Repository 는 `session.add`, `session.flush`, `session.execute`, `session.scalar` 만 사용한다.
- ❌ Repository 내부에서 `session.commit()` / `session.rollback()` 호출 금지
- ❌ Repository 내부에서 `async with session.begin():` 중첩 금지
- 트랜잭션 경계는 **`get_session` dependency** 가 책임진다 (요청 단위).

| 작업 | Repository | Dependency (`get_session`) |
|------|-----------|----------------------------|
| add / execute DML | ✅ | |
| flush (id 확보) | ✅ | |
| commit | ❌ 금지 | ✅ `session.begin()` 종료 시 자동 |
| rollback | ❌ 금지 | ✅ 예외 전파 시 자동 |

---

## lifespan-scoped UseCase 금지

- 앱 시작 시점(lifespan) 에 세션을 가진 UseCase 를 `singleton` 으로 만들지 않는다.
- lifespan-scoped UseCase 가 DB 가 필요한 다른 UseCase 를 필요로 한다면,
  **`execute(*, injected_uc)`** 형태로 요청 시점에 주입받는다.
- 이유: lifespan 싱글턴이 세션을 영구 점유하면 앱 전체가 풀 고갈의 원인이 된다.

---

## 금지 사항 요약

- ❌ 팩토리/서비스에서 `get_session_factory()()` 로 세션 직접 생성
- ❌ 동일 UseCase 안에서 repository 별 서로 다른 세션 사용
- ❌ Repository 내부에서 `commit()` / `rollback()` 호출
- ❌ `async with session.begin():` 중첩 호출 (dependency 에서만 사용)
- ❌ lifespan singleton UseCase 가 AsyncSession 을 보유
