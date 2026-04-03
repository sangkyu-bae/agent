# Plan: redis

> Feature: Redis DB 모듈 (공통 기반 레이어)
> Created: 2026-03-13
> Status: Plan
> Task ID: REDIS-001

---

## 1. 목적 (Why)

멀티 에이전트 및 프로젝트 전반에서 공통으로 사용할 Redis 연결 기반 레이어.
LLM 에이전트가 상태/데이터를 Redis에 읽고 쓸 수 있는 최소한의 공통 인터페이스를 제공한다.

이후 필요에 따라 세션 저장, 작업 큐, 분산 잠금 등의 기능을 이 위에 추가한다.

---

## 2. 기능 범위 (Scope)

### In Scope (최소 기반)
- Redis 연결 어댑터 (`RedisClient`) — 비동기 (redis-py asyncio)
- 기본 키-값 인터페이스 (`RedisRepositoryInterface`)
  - `get`, `set`, `delete`, `exists`, `expire`
- TTL 지원
- 연결 설정 (`RedisConfig`, pydantic-settings)

### Out of Scope (이후 확장)
- Hash / List / Sorted Set 연산
- 분산 잠금 (Distributed Lock)
- 작업 큐 (Job Queue)
- Pub/Sub

---

## 3. 기술 의존성

| 모듈 | Task ID | 상태 |
|------|---------|------|
| LoggerInterface | LOG-001 | 구현됨 |

외부 라이브러리:
- `redis[asyncio]` >= 5.0

---

## 4. 아키텍처 설계

### Domain Layer
```
src/domain/redis/
└── interfaces.py       # RedisRepositoryInterface (추상)
```

### Infrastructure Layer
```
src/infrastructure/redis/
├── redis_client.py      # Redis 연결 풀 관리
└── redis_repository.py  # RedisRepositoryInterface 구현
```

### Config
```
src/infrastructure/config/redis_config.py   # RedisConfig (pydantic-settings)
```

---

## 5. 인터페이스 설계

```python
# src/domain/redis/interfaces.py
class RedisRepositoryInterface(ABC):
    async def get(self, key: str) -> Optional[str]: ...
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def expire(self, key: str, ttl: int) -> None: ...
```

---

## 6. 환경 변수

```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
REDIS_MAX_CONNECTIONS=20
```

---

## 7. TDD 계획

```
tests/infrastructure/redis/
├── test_redis_client.py        # 연결/해제 (Mock)
└── test_redis_repository.py    # get/set/delete/exists/expire (Mock)
```

---

## 8. CLAUDE.md 규칙 체크

- [x] domain은 `RedisRepositoryInterface`만 정의 (외부 의존성 없음)
- [x] infrastructure에 redis-py 어댑터 구현
- [x] LOG-001 로깅 적용
- [x] TDD 순서: 테스트 → 실패 확인 → 구현 → 통과
- [x] config 하드코딩 금지 (pydantic-settings 사용)

---

## 9. 완료 기준

- [ ] `RedisRepositoryInterface` 정의 (domain)
- [ ] `RedisClient` 비동기 연결 어댑터
- [ ] `RedisRepository` 기본 CRUD 구현
- [ ] `RedisConfig` 설정 정의
- [ ] `.env.example` Redis 항목 추가
- [ ] 전체 테스트 통과
- [ ] LOG-001 로깅 적용
