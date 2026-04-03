# REDIS-001: Redis DB 모듈 (공통 기반 레이어)

> Task ID: REDIS-001
> 의존성: LOG-001
> 상태: Plan
> Plan 문서: docs/01-plan/features/redis.plan.md

---

## 목적

멀티 에이전트 및 프로젝트 전반에서 공통으로 사용할 최소 Redis 기반 레이어.
LLM 에이전트가 상태/데이터를 읽고 쓸 수 있는 기본 키-값 인터페이스만 제공한다.
이후 필요 기능(Hash, Lock, Queue 등)은 이 위에 확장한다.

---

## 구현 대상

### Domain Layer
| 파일 | 설명 |
|------|------|
| `src/domain/redis/interfaces.py` | `RedisRepositoryInterface` (추상) |

### Infrastructure Layer
| 파일 | 설명 |
|------|------|
| `src/infrastructure/redis/redis_client.py` | Redis 연결 풀 (redis-py asyncio) |
| `src/infrastructure/redis/redis_repository.py` | 기본 CRUD 구현 |
| `src/infrastructure/config/redis_config.py` | `RedisConfig` (pydantic-settings) |

---

## 인터페이스

```python
class RedisRepositoryInterface(ABC):
    async def get(self, key: str) -> Optional[str]: ...
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def expire(self, key: str, ttl: int) -> None: ...
```

---

## 환경 변수

```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
REDIS_MAX_CONNECTIONS=20
```

---

## 테스트 파일

| 테스트 파일 | 대상 |
|------------|------|
| `tests/infrastructure/redis/test_redis_client.py` | 연결/해제 (Mock) |
| `tests/infrastructure/redis/test_redis_repository.py` | get/set/delete/exists/expire (Mock) |

---

## LOG-001 로깅 체크리스트

- [ ] `LoggerInterface` 주입 받아 사용
- [ ] Redis 연결 에러 ERROR 로그 + 스택 트레이스
- [ ] REDIS_PASSWORD 로그 마스킹

---

## 완료 기준

- [ ] `RedisRepositoryInterface` 추상 클래스 정의
- [ ] `RedisClient` 비동기 연결 어댑터
- [ ] `RedisRepository` 기본 CRUD 구현
- [ ] `RedisConfig` 설정 정의
- [ ] `.env.example` 업데이트
- [ ] 전체 테스트 통과
- [ ] LOG-001 로깅 적용
