# admin-default-llm-routing Design Document

> **Summary**: 범용 `CachePort`를 아래단에 신설하고, 그 위에 `UtilityLLMProvider`(L1 값 캐시 + L2 인스턴스 캐시)를 얹어 하드코딩 `ChatOpenAI` 어댑터 9곳이 관리자 설정 모델을 재시작 없이 따라가게 한다.
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.2.0
> **Author**: 배상규
> **Date**: 2026-08-30
> **Status**: Implemented (Do 완료 · Check 99%)
> **Plan**: `docs/01-plan/features/admin-default-llm-routing.plan.md` (v0.2.0)
> **Analysis**: `docs/03-analysis/admin-default-llm-routing.analysis.md` (v0.1.0)
> **선택 설계안**: **C — 실용 균형** (Checkpoint 3)
>
> **v0.2.0 개정 사유**: 구현 중 확정된 사실을 반영한다. 레이어 규칙 준수를 위한
> `repo_builder` 주입(G-6), 런타임 해석이 요구한 패턴 C 어댑터 수정(G-3),
> 실측으로 드러난 자격증명 검증 문제(G-4 → DR-12).

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | NPU 실측을 하려면 LLM 호출이 한 군데로 모여야 하는데 9곳이 팩토리를 우회하고, 모델 교체마다 재시작이 필요하다 |
| **WHO** | P2 — 자사 인프라(NPU)에서 에이전트를 운영하려는 KB 운영자 / 플랫폼 관리자 |
| **RISK** | LangChain 객체는 직렬화 불가 → 캐시 계층을 잘못 나누면 Redis 전환 시 통째로 못 쓴다 |
| **SUCCESS** | 관리자 화면에서 기본 모델 변경 → 재시작 없이 9경로 전부 새 엔드포인트로 요청 |
| **SCOPE** | 범용 캐시 포트 + 인메모리 어댑터 + LLM provider + 배선 9곳. 기존 중복 3건 흡수·Redis 어댑터는 제외 |

---

## 1. Overview

### 1.1 Design Goals

| ID | 목표 | 근거 |
|----|------|------|
| G1 | 관리자 모델 변경이 **재시작 없이** 반영된다 | Plan FR-5 |
| G2 | Redis 어댑터 추가 시 **소비자 코드 무수정** | Plan NFR-2 |
| G3 | 캐시 모듈이 LLM 외 도메인에서도 재사용 가능하다 | Plan §2.1-A |
| G4 | provider 미주입 시 기존 동작을 100% 유지한다 | Plan FR-9 / R-5 |
| G5 | 캐시·모델 해석 실패가 요청을 실패시키지 않는다 | Plan FR-11 / R-7 |

### 1.2 Design Principles

1. **직렬화 가능한 것만 포트에 담는다** — `CachePort`는 값(dict)만 받는다. LangChain 객체는 프로세스 로컬에 격리한다 (Plan D-9).
2. **캐시는 부가 기능이다** — 미스·에러 시 DB 직행, DB도 실패하면 `None` 반환 후 기존 경로로 낙하. 예외를 위로 던지지 않는다.
3. **무효화 책임은 UseCase에 캡슐화한다** — `update_llm_model_pricing_use_case.py:57` 선례.
4. **키 규약은 provider 안에 가둔다** — UseCase가 `"llm_model:default"` 같은 문자열을 알지 못하게 한다.
5. **additive 변경만 한다** — 어댑터 시그니처에 파라미터를 더할 뿐, 기존 인자·임포트를 제거하지 않는다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| | A. 최소 변경 | B. 완전 분리 | **C. 실용 균형 ★선택** |
|---|---|---|---|
| 신설 파일 | 2개 | 6개 | **4개** |
| 리졸버 위치 | `main.py` 헬퍼 | 독립 클래스 | `UtilityLLMProvider`에 통합 |
| L1/L2 위치 | main.py 클로저 | 두 클래스에 분산 | **한 클래스 안** |
| 어댑터 주입 타입 | `Callable` | 포트 | **포트** |
| 단위 테스트 | 어려움 | 쉬움 | **쉬움** |
| `main.py` 증가 | +60줄 | +15줄 | **+20줄** |
| 복잡도 | 낮음 | 높음 | **중간** |

**선택 사유**: `CachePort`라는 재사용 자산은 확보하되, 아직 두 번째 소비자가 없는 리졸버까지 미리 쪼개는 YAGNI를 피한다. B는 AD-1의 핵심인 `updated_at` 키 연결이 두 클래스에 걸쳐 응집도를 잃는다.

### 2.1 Component Diagram

```
┌─ domain (순수 ABC, 외부 의존 0) ──────────────────────────┐
│  cache/interfaces.py            CachePort                 │
│  llm/interfaces.py              UtilityLLMProviderPort    │
│                                 LLMFactoryInterface (기존) │
│  llm_model/interfaces.py        LlmModelRepositoryInterface│
└───────────────────────────────▲───────────────────────────┘
                                │ 구현/의존
┌─ application ──────────────────┴───────────────────────────┐
│  llm_model/utility_llm_provider.py                         │
│    UtilityLLMProvider(UtilityLLMProviderPort)              │
│      ├ L1  CachePort      → dict (LlmModel 직렬화)         │
│      ├ L2  self._instances → BaseChatModel (프로세스 로컬)  │
│      ├ session_factory    → 캐시 미스 시 단기 세션          │
│      ├ repo_builder       → 저장소 조립 (구현 임포트 금지)  │
│      └ LLMFactoryInterface → 인스턴스 생성                  │
│                                                            │
│  llm_model/cache_invalidation.py                           │
│    invalidate_llm_model_cache()  ← UseCase 4곳 공용 헬퍼    │
│                                                            │
│  llm_model/{create,update,deactivate,update_pricing}_*.py  │
│    └ 위 헬퍼로 provider.invalidate() 의무 호출              │
└───────────────────────────────▲────────────────────────────┘
                                │
┌─ infrastructure ───────────────┴───────────────────────────┐
│  cache/in_memory_cache.py   InMemoryCache(CachePort)       │
│  llm/llm_factory.py         LLMFactory (기존, 무수정)       │
│                                                            │
│  hallucination/adapter.py   ┐                              │
│  search_decision/adapter.py │ UtilityLLMProviderPort 주입   │
│  intent/adapter.py          │ (additive, 기본값 None)       │
│  prompt_composer/adapter.py │                              │
│  eval_testset/qa_generator.py┘                             │
│  memory/extractor.py        ┐ 무수정 — main.py 호출부만     │
│  wiki/*_distiller.py 3종    ┘                              │
└───────────────────────────────▲────────────────────────────┘
                                │ 조립
┌─ api/main.py ──────────────────┴───────────────────────────┐
│  _cache    = InMemoryCache(...)                            │
│  _utility_llm_provider = UtilityLLMProvider(...)           │
│  → 어댑터 9곳에 주입                                        │
└────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

**해석 경로 (캐시 히트)**

```
어댑터.evaluate()
  └ await provider.get(temperature=0.0)
      └ L2 조회  key=(id, updated_at, 0.0)  → HIT → BaseChatModel 반환
                                                     (DB 조회 0, 객체 생성 0)
```

**해석 경로 (L2 미스, L1 히트)**

```
provider.get(0.0)
  └ L1 조회  "llm_model:default"  → HIT → dict → LlmModel 복원
  └ L2 미스  → LLMFactory.create(model, 0.0) → L2 저장 → 반환
```

**해석 경로 (전부 미스)**

```
provider.get(0.0)
  └ L1 미스
  └ async with session_factory() as session:        ← 단기 읽기 세션
        repo = self._repo_builder(session)           ← 주입된 빌더 (AD-6)
        model = await repo.find_default(request_id)
  └ L1 저장  key="llm_model:default"  ttl=60s
  └ LLMFactory.create → L2 저장 → 반환
```

> **`repo_builder` 를 쓰는 이유 (AD-6)**: provider 는 application 레이어이므로
> infrastructure 의 `LlmModelRepository` 를 **직접 임포트할 수 없다**
> (CLAUDE.md §6). 저장소 조립 함수를 주입받아 인터페이스에만 의존한다 —
> `MemoryExtractionService` 의 `_repo_builder` 선례와 동일하다.
> 부수 효과로 단위 테스트가 실 DB 없이 `InMemoryLlmModelRepository` 를 꽂는다.

**무효화 경로**

```
관리자 PATCH /api/v1/llm-models/{id}
  └ UpdateLlmModelUseCase.execute()
      └ repo.update(model)              model.updated_at 갱신됨
      └ await provider.invalidate()     ← 의무 호출
          └ cache.delete("llm_model:default")
          └ cache.delete("llm_model:name:<utility_name>")
             ※ L2는 건드리지 않는다 — 다음 L1 조회가 새 updated_at을
               가져오면 L2 키가 자연히 달라져 구 엔트리는 방치 후 만료된다 (DR-3)
```

### 2.3 실행 순서 — `UtilityLLMProvider.get(temperature)`

```
1. model = await self._resolve_model(request_id)        # L1 경유
     1-1. name = settings.utility_llm_model_name
     1-2. name 있으면:
            L1 "llm_model:name:<name>" 조회
            miss → 단기 세션 → repo.list_active() 에서 model_name 일치 탐색
            찾음 → L1 저장 후 반환
            못 찾음 → logger.warning(fallback_to="default") → 1-3 으로 낙하
     1-3. L1 "llm_model:default" 조회
            miss → 단기 세션 → repo.find_default()
            찾음 → L1 저장 후 반환
            None  → logger.warning → None 반환
2. model is None  → return None                          # 어댑터가 기존 경로로 낙하
3. key = (model.id, model.updated_at.isoformat(), temperature)
4. self._instances 에 key 있으면 → 반환
5. llm = self._llm_factory.create(model, temperature)
6. self._instances[key] = llm   (상한 초과 시 가장 오래된 항목 제거)
7. return llm
```

**예외 정책**: 1~6 단계에서 발생한 모든 예외는 `logger.error` 후 `None` 반환으로 흡수한다. provider는 절대 예외를 위로 던지지 않는다 (G5).

### 2.4 Dependencies

신규 외부 패키지 **없음**. `redis>=5.0.0`은 이미 `pyproject.toml:52`에 있으나 이번 사이클에서 사용하지 않는다.

---

## 3. Data Model

### 3.1 캐시 키 규약

| 키 | 값 | TTL | 무효화 시점 |
|----|-----|-----|-------------|
| `llm_model:default` | `LlmModel` 직렬화 dict | `settings.llm_model_cache_ttl_seconds` (60s) | create / update / deactivate / pricing |
| `llm_model:name:<model_name>` | 동일 | 동일 | 동일 |

네임스페이스 규약: `<도메인>:<식별자>`. 다른 도메인이 `CachePort`를 쓸 때도 이 규약을 따른다.

**무효화 입도**: 모델 단위가 아니라 **두 키 전체**를 지운다. `is_default` 변경은 "어느 모델이 기본이냐"가 바뀌는 것이라 특정 모델 ID만 지우면 낡은 default가 남는다.

### 3.2 직렬화 계약 ★

`CachePort`에 담기는 값은 **JSON 직렬화 가능해야 한다**. `LlmModel`은 `Decimal`·`datetime`을 포함하므로 provider가 경계에서 변환한다.

```python
# LlmModel → dict  (L1 저장 시)
{
  "id": str, "provider": str, "model_name": str, "display_name": str,
  "description": str | None, "api_key_env": str, "max_tokens": int | None,
  "is_active": bool, "is_default": bool,
  "created_at": str,          # ISO8601
  "updated_at": str,          # ISO8601  ← L2 키 재료
  "input_price_per_1k_usd":  str | None,   # Decimal → str (정밀도 보존)
  "output_price_per_1k_usd": str | None,
  "pricing_updated_at": str | None,
  "base_url": str | None,
  "supports_vision": bool,
}
```

이 변환을 provider 안에 두면 Redis 어댑터를 붙일 때 **provider·어댑터·UseCase 어느 것도 수정할 필요가 없다** (G2).

### 3.3 L2 인스턴스 캐시

```python
key   = (model.id, model.updated_at.isoformat(), temperature)
value = BaseChatModel
상한   = settings.llm_instance_cache_max_entries (기본 32)
```

`updated_at`이 키에 있어 모델 수정 시 자동으로 다른 키가 된다 (DR-3). 상한 초과 시 삽입 순서 기준 가장 오래된 항목을 제거한다(`dict`는 삽입 순서를 보존).

### 3.4 Database Schema

**변경 없음.** 마이그레이션 파일을 추가하지 않는다.

---

## 4. API Specification

### 4.1 포트 시그니처

```python
# src/domain/cache/interfaces.py
class CachePort(ABC):
    """범용 KV 캐시.

    계약: value 는 JSON 직렬화 가능해야 한다.
    Redis 등 프로세스 외부 저장소로 교체될 수 있으므로,
    소켓·클라이언트 핸들을 가진 객체(예: LangChain BaseChatModel)를
    담아서는 안 된다.
    구현체는 어떤 경우에도 예외를 던지지 않는다 — 실패는 miss 로 취급한다.
    """

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """캐시 값. 미스·만료·오류면 None."""

    @abstractmethod
    async def set(
        self, key: str, value: Any, ttl_seconds: float | None = None
    ) -> None:
        """값 저장. ttl_seconds=None 이면 구현체 기본 TTL."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """단건 삭제. 없는 키여도 오류가 아니다."""

    @abstractmethod
    async def clear(self) -> None:
        """전체 비움."""
```

```python
# src/domain/llm/interfaces.py  (추가)
class UtilityLLMProviderPort(ABC):
    """보조 LLM 공급자. 관리자 설정 모델을 런타임에 해석한다."""

    @abstractmethod
    async def get(self, temperature: float = 0.0) -> BaseChatModel | None:
        """현재 유효한 보조 LLM. 해석 불가 시 None (호출부는 기존 경로로 낙하)."""

    @abstractmethod
    async def invalidate(self) -> None:
        """모델 해석 캐시 무효화. 관리자 변경 UseCase가 의무 호출한다."""
```

```python
# src/infrastructure/cache/in_memory_cache.py
class InMemoryCache(CachePort):
    def __init__(
        self,
        *,
        default_ttl_seconds: float | None = None,
        max_entries: int = 1000,
        clock: Callable[[], float] = time.monotonic,   # 테스트 주입 (CostCalculator 선례)
    ) -> None: ...
```

```python
# src/application/llm_model/utility_llm_provider.py
class UtilityLLMProvider(UtilityLLMProviderPort):
    def __init__(
        self,
        cache: CachePort,
        llm_factory: LLMFactoryInterface,
        session_factory: Callable[[], AsyncSession],
        # AD-6: infrastructure 구현을 직접 임포트하지 않기 위한 조립 함수.
        repo_builder: Callable[[AsyncSession], LlmModelRepositoryInterface],
        logger: LoggerInterface,
        *,
        utility_model_name: str | None = None,
        ttl_seconds: float = 60.0,
        max_instances: int = 32,
    ) -> None: ...
```

```python
# src/application/llm_model/cache_invalidation.py  (UseCase 4곳 공용)
async def invalidate_llm_model_cache(
    provider: UtilityLLMProviderPort | None,
    logger: LoggerInterface,
    request_id: str,
    model_id: str | None = None,
) -> None:
    """관리자 변경 후 캐시 무효화. provider=None 이면 no-op (FR-9).

    호출 시점에는 변경이 이미 DB 에 반영된 뒤다 — 무효화 실패로 예외를 올리면
    "저장은 됐는데 실패로 응답되는" 상태가 되므로 warning 후 삼킨다 (§6.1).
    """
```

### 4.2 어댑터 시그니처 변경 (additive)

```python
# 패턴 A — 예: hallucination/adapter.py
def __init__(
    self,
    model_name: str = "gpt-4o-mini",      # 유지
    temperature: float = 0.0,             # 유지
    llm_provider: UtilityLLMProviderPort | None = None,   # ★ 추가
) -> None: ...

# 패턴 B — 예: intent/adapter.py
def __init__(
    self,
    logger: LoggerInterface,
    config: IntentConfig | None = None,
    chain: IntentChain | None = None,     # 유지 (기존 테스트 의존)
    llm_provider: UtilityLLMProviderPort | None = None,   # ★ 추가
) -> None: ...

# 패턴 C — 예: memory/extractor.py, wiki/*_distiller.py 3종
#   chain 을 조립하지 않고 self._llm.ainvoke() 를 직접 부르므로 더 단순하다.
def __init__(
    self,
    llm,
    logger: LoggerInterface,
    llm_provider: UtilityLLMProviderPort | None = None,   # ★ 추가
) -> None: ...

@classmethod
def from_openai(cls, model_name, api_key, logger,
                llm_provider=None):                        # ★ 추가
    ...

async def _resolve_llm(self):
    """호출 시점의 유효 LLM. 미주입·해석 실패면 생성자 주입 LLM 으로 낙하."""
```

**주입 우선순위**: `chain` > `llm_provider` > 기존 `ChatOpenAI`. 명시적으로 주입된 chain이 항상 이긴다(기존 테스트 보호).

**패턴 A/B 와 C 의 차이**: A/B 는 `prompt | llm.with_structured_output(...)` chain 을
재조립해야 하므로 `_resolve_chain()` + 객체 동일성 메모이제이션이 필요하다.
C 는 LLM 을 직접 호출하므로 `_resolve_llm()` 한 개면 된다(메모이제이션 불요).

### 4.3 관찰 가능한 동작 변화

| 상황 | 변경 전 | 변경 후 |
|------|---------|---------|
| 관리자가 `is_default` 변경 | 재시작 전까지 무시됨 | 다음 요청부터 반영 |
| `UTILITY_LLM_MODEL_NAME` 설정 | (없던 개념) | 9곳이 해당 모델 사용 |
| 보조 모델명 오타 | — | warning 로그 + 기본 모델로 동작 |
| DB 조회 실패 | 부팅 시 폴백 | warning 로그 + 기존 `ChatOpenAI` 경로 |
| provider 미주입 | — | 기존과 완전 동일 |

**HTTP API 계약 변경 없음** → 프론트엔드 타입 동기화 불필요 (루트 CLAUDE.md §4-1 해당 없음).

---

## 5. UI/UX Design

**해당 없음.** 관리자 화면은 기존 `is_default` 토글을 그대로 사용한다. 신규 화면·필드 없음.

---

## 6. Error Handling

### 6.1 오류 정책

| 상황 | 처리 | 로그 레벨 | 결과 |
|------|------|-----------|------|
| 캐시 `get` 실패 | miss로 취급 | debug | DB 조회로 진행 |
| 캐시 `set` 실패 | 무시 | debug | 정상 반환 |
| 보조 모델명 미해석 | 기본 모델로 폴백 | **warning** | 정상 동작 |
| 기본 모델 없음 | `None` 반환 | **warning** | 어댑터가 기존 경로 |
| DB 조회 예외 | `None` 반환 | **error** (스택 포함) | 어댑터가 기존 경로 |
| `LLMFactory.create` 실패 | `None` 반환 | **error** (스택 포함) | 어댑터가 기존 경로 |
| `invalidate` 실패 | 무시 | **warning** | 관리자 요청은 성공 처리 |

**원칙**: provider는 예외를 위로 던지지 않는다. LLM 해석 실패가 사용자 요청을 실패시켜서는 안 된다 (G5).

### 6.2 로깅

```python
# 폴백 — warning (에러 아님, 정상 경로)
self._logger.warning(
    "Utility LLM model unresolved — falling back to default",
    request_id=request_id,
    model_name=name,
    fallback_to="default",
)

# 해석 성공 — debug (요청마다 찍히므로 info 금지)
self._logger.debug(
    "Utility LLM resolved",
    request_id=request_id,
    model_name=model.model_name,
    provider=model.provider,
    base_url=model.base_url,
    cache="L1_hit" | "L1_miss" | "L2_hit",
)

# 무효화 — info (관리자 액션이라 빈도 낮음)
self._logger.info(
    "LLM model cache invalidated",
    request_id=request_id,
    model_id=model_id,
)
```

`base_url`을 로그에 남기는 것이 **NPU 전환 실측의 근거**가 된다 (Plan §4.1 DoD).

---

## 7. Security Considerations

| 항목 | 판단 |
|------|------|
| API 키 노출 | `LlmModel`에는 `api_key_env`(환경변수 **이름**)만 있고 키 값은 없다. 캐시에 담겨도 비밀 노출 아님 |
| `base_url` 로깅 | 내부 엔드포인트 주소. 기존 `llm_factory` 로깅 수준과 동일 |
| 캐시 격리 | 인메모리는 프로세스 로컬. 테넌트 간 공유 데이터 아님(모델 레지스트리는 전역 설정) |
| Redis 전환 시 | 저장 값에 비밀이 없으므로 암호화 불요. 단 `base_url`이 내부망 정보이므로 Redis 접근 통제는 유지 |
| 권한 | 모델 변경은 기존 관리자 라우터 권한을 그대로 따른다. 신규 엔드포인트 없음 |

---

## 8. Test Plan

### 8.1 Test Scope

| Level | 대상 | 도구 |
|-------|------|------|
| L1 | `InMemoryCache` TTL/삭제/상한 | pytest |
| L2 | `UtilityLLMProvider` 해석·폴백·L1/L2 캐시 | pytest + fake |
| L3 | UseCase 무효화 의무 호출 | pytest + spy |
| L4 | 어댑터 주입/미주입 동작 | pytest |
| L5 | 회귀 — 기존 테스트 전량 | pytest |

### 8.2 L1: `InMemoryCache` 시나리오

| ID | 시나리오 | 기대 |
|----|----------|------|
| C1 | `set` 후 즉시 `get` | 값 반환 |
| C2 | TTL 경과 후 `get` (clock 조작) | `None` |
| C3 | TTL `None` + 기본 TTL 설정 | 기본 TTL 적용 |
| C4 | `delete` 후 `get` | `None` |
| C5 | 없는 키 `delete` | 예외 없음 |
| C6 | `clear` 후 전체 `get` | 모두 `None` |
| C7 | `max_entries` 초과 삽입 | 가장 오래된 항목 제거, 크기 유지 |
| C8 | 만료 항목이 있는 상태에서 `get` | lazy 삭제되어 크기 감소 |

### 8.3 L2: `UtilityLLMProvider` 시나리오

| ID | 시나리오 | 기대 |
|----|----------|------|
| P1 | 보조 모델명 미설정 + 기본 모델 존재 | 기본 모델의 LLM 반환 |
| P2 | 보조 모델명 설정 + DB에 존재 | 보조 모델 반환 |
| P3 | 보조 모델명 설정 + DB에 없음 | **warning** + 기본 모델로 폴백 |
| P4 | 보조 모델명이 비활성 모델 | **warning** + 기본 모델로 폴백 |
| P5 | 기본 모델도 없음 | **warning** + `None` |
| P6 | 동일 temperature 2회 호출 | L2 히트 — `LLMFactory.create` 1회만 |
| P7 | 다른 temperature 2회 호출 | `create` 2회 (키가 다름) |
| P8 | 2회 호출 사이 L1 히트 | DB 조회 1회만 |
| P9 | `invalidate()` 후 호출 | DB 재조회 발생 |
| P10 | `updated_at`이 바뀐 모델 반환 | L2 새 키 → 새 인스턴스 |
| P11 | DB 조회가 예외 발생 | **error** 로그 + `None` (예외 전파 없음) |
| P12 | `LLMFactory.create` 예외 | **error** 로그 + `None` |
| P13 | 캐시 `get`이 예외 발생 | miss 취급, 정상 동작 |
| P14 | `base_url` 있는 모델 해석 | 로그에 `base_url` 포함 |

### 8.4 L3: UseCase 무효화 시나리오

| ID | 시나리오 | 기대 |
|----|----------|------|
| U1 | `UpdateLlmModelUseCase.execute` | `provider.invalidate()` 1회 호출 |
| U2 | `CreateLlmModelUseCase.execute` | 동일 |
| U3 | `DeactivateLlmModelUseCase.execute` | 동일 |
| U4 | `UpdateLlmModelPricingUseCase.execute` | `cost_calc.invalidate` **및** `provider.invalidate` 호출 |
| U5 | `invalidate`가 예외를 던짐 | UseCase는 성공 반환 (warning 로그) |
| U6 | provider 미주입(None) | 기존 동작, 예외 없음 |

### 8.5 L4: 어댑터 시나리오 (5개 어댑터 공통)

| ID | 시나리오 | 기대 |
|----|----------|------|
| A1 | `llm_provider` 미주입 | 기존 `ChatOpenAI` 경로 (하위호환) |
| A2 | `llm_provider` 주입 + `get`이 LLM 반환 | 주입된 LLM으로 chain 구성 |
| A3 | `llm_provider` 주입 + `get`이 `None` | 기존 `ChatOpenAI` 경로로 낙하 |
| A4 | 연속 2회 호출, 동일 LLM 객체 | chain 재조립 없음 (메모이제이션) |
| A5 | 2회 호출 사이 LLM 객체 변경 | chain 재조립 |
| A6 | `chain` 명시 주입 + `llm_provider` 동시 주입 | `chain`이 이긴다 |
| **A7** ★ | `OPENAI_API_KEY` 없는 환경 + provider 주입 | **생성자가 성공한다** (DR-12). 대조군: 미주입 시에는 종전대로 실패 |

### 8.5-b L6: 체인 통합 시나리오 (`tests/integration/test_llm_routing_chain.py`)

실물 `InMemoryCache` · `InMemoryLlmModelRepository` · provider · 어댑터를 잇고
LLM 생성 지점 하나만 스텁으로 둔다. FR-5 를 실환경 없이 증명한다.

| ID | 시나리오 | 기대 |
|----|----------|------|
| I1 | 모델 A로 판단 → 관리자가 B를 default로 변경 → 재호출 | **재시작 없이** B로 바뀐다 (FR-5) |
| I2 | self-host 모델 해석 | `base_url` 이 `LLMFactory` 까지 온전히 전달 |
| I3 | 무효화 없이 3회 연속 호출 | LLM 생성 1회 (L1/L2 히트) |
| I4 | provider 미주입 UseCase 로 모델 변경 | 낡은 모델이 계속 쓰인다 — **D-8 구멍 회귀 방지** |

### 8.6 L5: 기존 테스트 회귀 (Plan R-5)

| 대상 | 확인 |
|------|------|
| `tests/infrastructure/hallucination/test_adapter.py` | `patch("...adapter.ChatOpenAI")` 가 여전히 유효 |
| `tests/infrastructure/intent/test_adapter.py` | `chain` 주입 경로 유지 |
| `tests/application/llm_model/*` | UseCase 시그니처 변경 후에도 통과 |
| `tests/infrastructure/llm/test_llm_factory_*.py` | `LLMFactory` 무수정이므로 영향 없음 |
| 전량 | `pytest tests/ -q` |

### 8.7 Seed Data Requirements

없음. 테스트는 fake repository / fake cache 를 주입한다.

---

## 9. Clean Architecture

### 9.1 Layer Structure

```
domain/cache/interfaces.py            CachePort                 (신규)
domain/llm/interfaces.py              UtilityLLMProviderPort    (추가)
        ▲
application/llm_model/utility_llm_provider.py                   (신규)
application/llm_model/{create,update,deactivate,pricing}_*.py   (수정)
        ▲
infrastructure/cache/in_memory_cache.py                         (신규)
infrastructure/{hallucination,search_decision,intent,
                prompt_composer,eval_testset}/                  (수정: 파라미터 추가)
        ▲
api/main.py                                                     (조립)
```

### 9.2 Dependency Rules

| 규칙 | 준수 방법 |
|------|-----------|
| domain → 외부 참조 금지 | `CachePort`·`UtilityLLMProviderPort`는 `abc` + `typing` + `BaseChatModel` 타입 힌트만 사용 (기존 `LLMFactoryInterface`와 동일 수준) |
| infrastructure → application 참조 금지 | 어댑터는 **포트(domain)** 만 임포트한다. 구현체 주입은 `main.py`가 수행 |
| application → infrastructure 참조 금지 | provider는 `CachePort`·`LLMFactoryInterface`·`LlmModelRepositoryInterface` 등 전부 인터페이스에만 의존 |
| Repository commit 금지 | provider는 읽기 전용 조회만 수행 |

### 9.3 This Feature's Layer Assignment

| 컴포넌트 | 레이어 | 사유 |
|----------|--------|------|
| `CachePort` | domain | 순수 ABC. 외부 의존 0 |
| `UtilityLLMProviderPort` | domain | 동일. 기존 `LLMFactoryInterface`와 같은 파일군 |
| `UtilityLLMProvider` | **application** | repo·cache·factory를 **조합**하는 흐름 제어. 비즈니스 규칙 없음 |
| `InMemoryCache` | infrastructure | 저장소 구현체 |
| 어댑터 파라미터 추가 | infrastructure | 기존 위치 유지 |

### 9.4 DB 세션 규칙 준수 ★

`UtilityLLMProvider`는 앱 수명 싱글톤이면서 DB 조회가 필요하다. `docs/rules/db-session.md`의 "lifespan singleton UseCase가 AsyncSession을 보유 금지"와 충돌하지 않도록:

- **`AsyncSession`을 보유하지 않는다.** `session_factory`를 주입받아 캐시 미스 시에만 `async with`로 단기 세션을 연다.
- 근거 — 프로젝트 확립 패턴. `src/application/agent_run/ws_auth_context.py:5`:
  > "조립 시점에만 단기 세션을 연다 (CLAUDE.md §6: session_factory 주입, async with 사용)."
  
  동일 패턴이 `agent_run/tracker.py`, `memory/extraction_service.py`, `memory/context_assembler.py`, `background_job/worker.py` 등 10곳 이상에서 사용된다.
- 금지 대상은 서비스가 `get_session_factory()()`를 **직접 호출**하는 것이며, 주입받은 factory를 단기 사용하는 것은 승인된 패턴이다.
- 읽기 전용 단건 조회이며 TTL 60초로 빈도가 제한되므로 커넥션 풀 압박이 없다.

---

## 10. Coding Convention Reference

### 10.1 준수 규칙

- 함수 40줄 이하 — `_resolve_model()`이 길어지면 `_resolve_by_name()` / `_resolve_default()`로 분리
- if 중첩 2단계 이하
- `print()` 금지, `logger` 사용
- 에러 처리 시 스택 트레이스 포함 (`logger.error(..., exception=e)`)
- config 하드코딩 금지 → `settings` 경유
- Repository 내부 `commit()`/`rollback()` 금지 (읽기 전용이라 해당 없음)

### 10.2 명명

| 대상 | 규칙 | 예 |
|------|------|-----|
| 포트 | `<역할>Port` | `CachePort`, `UtilityLLMProviderPort` |
| 인메모리 구현 | `InMemory<역할>` | `InMemoryCache` |
| 캐시 키 | `<도메인>:<식별자>` | `llm_model:default` |
| 설정 | `<도메인>_<속성>` | `utility_llm_model_name` |

### 10.3 신규 설정

```python
# src/config.py
utility_llm_model_name: str | None = None       # 미설정 시 기본 모델 사용
llm_model_cache_ttl_seconds: float = 60.0       # L1 TTL (다중 워커 안전장치)
llm_instance_cache_max_entries: int = 32        # L2 상한
```

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/
│   ├── cache/
│   │   ├── __init__.py                    [신규]
│   │   └── interfaces.py                  [신규]  CachePort
│   └── llm/
│       └── interfaces.py                  [수정]  +UtilityLLMProviderPort
├── application/
│   └── llm_model/
│       ├── utility_llm_provider.py        [신규]  UtilityLLMProvider (L1+L2)
│       ├── cache_invalidation.py          [신규]  무효화 공용 헬퍼
│       ├── create_llm_model_use_case.py   [수정]  +llm_provider, invalidate
│       ├── update_llm_model_use_case.py   [수정]  ← D-8 핵심 구멍
│       ├── deactivate_llm_model_use_case.py [수정]
│       └── update_llm_model_pricing_use_case.py [수정] cost_calc + provider
├── infrastructure/
│   ├── cache/
│   │   ├── __init__.py                    [신규]
│   │   └── in_memory_cache.py             [신규]  InMemoryCache
│   │
│   │   ── 패턴 A: model_name 고정 → _resolve_chain() ──
│   ├── hallucination/adapter.py           [수정]  +llm_provider
│   ├── search_decision/adapter.py         [수정]  +llm_provider
│   ├── eval_testset/qa_generator.py       [수정]  +llm_provider
│   │   ── 패턴 B: chain 주입 seam 보유 ──
│   ├── intent/adapter.py                  [수정]  +llm_provider (chain 우선)
│   ├── prompt_composer/adapter.py         [수정]  +llm_provider (chain 우선)
│   │   ── 패턴 C: llm 직접 호출 → _resolve_llm() ──
│   ├── memory/extractor.py                [수정]  +llm_provider
│   ├── wiki/wiki_distiller.py             [수정]  +llm_provider
│   ├── wiki/feedback_distiller.py         [수정]  +llm_provider
│   └── wiki/folder_summary_distiller.py   [수정]  +llm_provider
├── api/main.py                            [수정]  provider 싱글톤 + 9곳 배선
└── config.py                              [수정]  설정 3개

tests/
├── infrastructure/cache/test_in_memory_cache.py      [신규] C1~C9 + 포트 계약 (16)
├── application/llm_model/
│   ├── test_utility_llm_provider.py                  [신규] P1~P14 (19)
│   └── test_use_case_cache_invalidation.py           [신규] U1~U6 (11)
├── infrastructure/test_adapter_llm_provider.py       [신규] A1~A7 (12)
└── integration/test_llm_routing_chain.py             [신규] 체인 통합 (4)
```

**설계 v0.1.0 대비 변경**

| 항목 | v0.1.0 | v0.2.0 (실제) | 사유 |
|------|--------|---------------|------|
| 어댑터 수정 범위 | 5곳 (패턴 A/B) | **9곳** (+ 패턴 C 4) | 런타임 해석이 async 여서 동기 배선 불가 (§11.2 주석) |
| `cache_invalidation.py` | 없음 | 신규 | 동일 try/except 4중복 제거 |
| `tests/domain/cache/test_interfaces.py` | 별도 파일 | `test_in_memory_cache.py` 의 `TestCachePortContract` 로 통합 | 순수 ABC 전용 파일은 실익 적음 |
| 무효화 테스트 | UseCase별 복수 파일 | 단일 `test_use_case_cache_invalidation.py` | U1~U6 이 서로 대조군 역할 |
| 통합 테스트 | 없음 | `tests/integration/test_llm_routing_chain.py` | FR-5(무재시작)를 실환경 없이 증명 |

### 11.2 Implementation Order

| # | 작업 | 검증 |
|---|------|------|
| 1 | `CachePort` + `InMemoryCache` (TDD) | C1~C8 |
| 2 | `config.py` 설정 3개 + `.env.example` | — |
| 3 | `UtilityLLMProviderPort` + `UtilityLLMProvider` (TDD) | P1~P14 |
| 4 | UseCase 4곳 무효화 (TDD) | U1~U6 |
| 5 | `main.py` 조립 (cache, provider 싱글톤) | 부팅 성공 |
| 6 | 패턴 A 3곳 (`hallucination`, `search_decision`, `qa_generator`) | A1~A7 |
| 7 | 패턴 B 2곳 (`intent`, `prompt_composer`) | A6 (chain 우선) |
| 8 | 패턴 C 4곳 (`memory`, wiki distiller 3종) | 회귀 |
| 9 | 전량 회귀 + `/verify-architecture` + `/verify-logging` | L5 |
| 10 | self-host 모델 등록 → 무재시작 전환 실측 | Plan DoD |

**순서 원칙**: 아래단(포트·캐시)부터 위로.

> **v0.2.0 정정 — 패턴 C 는 "어댑터 무수정"이 아니다.**
> v0.1.0 은 6단계를 "패턴 C 4곳 배선 교체 (어댑터 무수정)"로 적고 최저 리스크
> 작업으로 먼저 배치했다. 이는 **구 AD-1(부팅 시 주입)** 전제로 쓰인 문장이다.
> Plan v0.2.0 이 런타임 해석으로 바뀌며 `provider.get()` 이 async 가 되었고,
> 동기 싱글톤 getter 안에서는 await 할 수 없다. 따라서 패턴 C 도 어댑터에
> `_resolve_llm()` 을 넣어야 하며, 배선만으로는 해결되지 않는다.
> 대신 chain 재조립이 없어 패턴 A/B 보다 단순하므로 마지막에 배치한다.

### 11.3 Session Guide

| Module | 범위 | 산출물 | 선행 |
|--------|------|--------|------|
| **module-1** | 공통 캐시 모듈 | `CachePort`, `InMemoryCache`, 설정 | 없음 |
| **module-2** | LLM provider | `UtilityLLMProviderPort`, `UtilityLLMProvider` | module-1 |
| **module-3** | 무효화 배선 | UseCase 4곳 | module-2 |
| **module-4** | 어댑터 전환 | `main.py` 조립 + 어댑터 9곳 | module-2 |
| **module-5** | 검증 | 회귀 + 규칙 검사 + NPU 실측 | module-3, 4 |

```bash
/pdca do admin-default-llm-routing --scope module-1
/pdca do admin-default-llm-routing --scope module-2
/pdca do admin-default-llm-routing --scope module-3,module-4
/pdca do admin-default-llm-routing --scope module-5
```

**권장 분할**: module-1+2를 한 세션(아래단 완성, 독립 테스트 가능), module-3+4를 한 세션(배선), module-5를 한 세션(검증). module-1만 먼저 끝내도 다른 도메인이 `CachePort`를 쓸 수 있어 단독 가치가 있다.

---

## 12. Key Design Decisions (DR)

| ID | 결정 | 대안 | 사유 |
|----|------|------|------|
| **DR-1** | 캐시를 L1(값)/L2(인스턴스) 2계층으로 분리 | 단일 캐시에 LLM 객체 저장 | LangChain 객체는 직렬화 불가. 단일 캐시로 만들면 Redis 전환 시 전면 재작업 (Plan D-9 / R-1) |
| **DR-2** | 직렬화 변환을 provider 경계에서 수행 | 포트가 `LlmModel`을 그대로 받음 | 포트 계약을 "JSON 가능한 값"으로 유지해야 Redis 어댑터 추가 시 소비자 무수정 (G2) |
| **DR-3** | `updated_at`을 L2 키에 포함 | L2도 명시적 무효화 | L1 갱신이 새 `updated_at`을 실어오면 L2 키가 자연히 달라져 **무효화 로직이 한 곳으로 줄어든다**. 구 엔트리는 상한 정책으로 밀려난다 |
| **DR-4** | 리졸버와 provider를 한 클래스로 통합 | 두 클래스 분리(설계안 B) | DR-3의 L1→L2 키 연결이 한 곳에 모여 응집도 유지. 두 번째 소비자가 없어 분리는 YAGNI |
| **DR-5** | 무효화는 두 키 전체 삭제 | 모델 ID 단위 삭제 | `is_default` 변경은 "어느 모델이 기본이냐"가 바뀌는 것. ID 단위로는 낡은 default가 남는다 |
| **DR-6** | `invalidate()`를 포트에 노출 | UseCase가 `CachePort.delete(키)` 직접 호출 | 키 규약이 UseCase로 새지 않게 provider 안에 캡슐화 (원칙 4) |
| **DR-7** | provider는 예외를 던지지 않는다 | 예외 전파 | LLM 해석 실패가 사용자 요청을 실패시키면 안 된다. `_build_tool_filter()` 선례 (G5) |
| **DR-8** | 어댑터 파라미터는 additive, 기본값 `None` | 기존 `model_name` 제거 | `tests/infrastructure/hallucination/test_adapter.py:24`가 `ChatOpenAI` 심볼을 patch 중. 제거 시 회귀 (Plan R-5) |
| **DR-9** | 주입 우선순위 `chain` > `llm_provider` > `ChatOpenAI` | provider 우선 | 명시적 chain 주입은 테스트 의도. 항상 이겨야 한다 |
| **DR-10** | `session_factory` 주입 + 단기 세션 | 세션 보유 / 요청마다 repo 전달 | lifespan singleton의 세션 보유 금지 회피. 10곳 이상 확립된 패턴 (§9.4) |
| **DR-11** | TTL 60초 기본 | TTL 무한 | 단일 서버 현재는 명시적 무효화로 충분하나, 다중 워커 전환 시 무효화 미전파 구간을 수렴시키는 안전장치 (Plan R-2 / AD-4) |
| **DR-12** ★ | provider 주입 시 레거시 `ChatOpenAI` 를 **지연 생성** | `__init__` 에서 즉시 생성 (기존 구조) | **실측**: `ChatOpenAI(model=...)` 은 키가 없으면 생성자에서 `OpenAIError: Missing credentials` 로 실패한다. 어댑터가 즉시 만들면 `OPENAI_API_KEY` 없는 **self-host 전용 배포가 부팅조차 못 한다** — 이 기능의 SUCCESS 기준("OpenAI 호출 0건")이 곧 "OpenAI 키 없이 뜬다"이므로 선택이 아닌 필수 조건이다. provider 미주입 시에는 종전대로 즉시 생성해 하위호환을 유지한다 |
| **DR-13** | 패턴 C 는 `_resolve_llm()` 만 (메모이제이션 없음) | 패턴 A/B 와 동일하게 chain 캐시 | 패턴 C 는 `llm.ainvoke()` 를 직접 부른다 — 재조립 대상인 chain 자체가 없으므로 캐시할 것이 없다 |

**AD-6 — 저장소는 `repo_builder` 로 주입받는다** (§2.2 / §4.1)

`UtilityLLMProvider` 는 application 레이어다. infrastructure 의
`LlmModelRepository` 를 직접 임포트하면 CLAUDE.md §6 금지 사항을 위반한다.
저장소 조립 함수를 주입받아 `LlmModelRepositoryInterface` 에만 의존하며,
이는 `MemoryExtractionService._repo_builder` 로 확립된 패턴이다.
부수 효과로 단위 테스트가 실 DB 없이 `InMemoryLlmModelRepository` 를 꽂는다.

---

## 13. Verification Notes (설계 중 실측)

### 13.1 `updated_at`이 실제로 갱신되는가 — 확인됨

`UpdateLlmModelUseCase`(`update_llm_model_use_case.py:56`)가 저장 직전 갱신한다:

```python
model.updated_at = datetime.now(timezone.utc)
updated = await self._repository.update(model, request_id)
```

`UpdateLlmModelPricingUseCase`도 동일(`:52`). **DR-3의 전제가 성립한다.**

### 13.2 무효화 훅이 비어 있는 경로 — 확인됨

`invalidate` 호출은 `update_llm_model_pricing_use_case.py:57` **단 1곳**뿐이다. `create` / `update` / `deactivate` 는 없다. 관리자가 `is_default`를 바꾸는 경로(`update_llm_model_use_case.py:50-54`)가 여기 포함된다 — Plan D-8이 코드로 확인된다.

### 13.3 Repository 인터페이스로 해석이 가능한가 — 확인됨

`LlmModelRepositoryInterface`에 `find_default()`, `list_active()`가 이미 있다. **신규 메서드 추가 불필요.**

- 기본 모델: `find_default(request_id)`
- 보조 모델: `list_active(request_id)`에서 `model_name` 일치 탐색
  - `find_by_provider_and_name`은 provider까지 요구해 설정이 번거로워지므로 사용하지 않는다. 활성 모델 수는 적어 목록 탐색 비용이 무시 가능하며, **비활성 모델이 자동으로 걸러지는 이점**이 있다(P4).

### 13.0 `ChatOpenAI` 는 키 없이 생성되는가 — **실패 확인** (DR-12 근거)

```python
>>> os.environ.pop("OPENAI_API_KEY")
>>> ChatOpenAI(model="gpt-4o-mini", temperature=0)
OpenAIError: Missing credentials. Please pass an `api_key`, ...
```

생성자가 자격증명을 검증한다. 어댑터가 `__init__` 에서 즉시 만드는 기존 구조로는
**self-host 전용 배포(= 이 기능의 목표)가 부팅 불가**다. → DR-12 도입.

### 13.4 `LLMFactory`는 손댈 필요가 없는가 — 확인됨

`_create_openai`가 `base_url`을 이미 처리하고(`llm_factory.py:44-46`), 인증 없는 self-host를 더미키로 통과시킨다(`:69-83`). provider는 `LlmModel`을 그대로 넘기기만 하면 된다. **`llm_factory.py` 무수정.**

---

## 14. Plan 문서 갱신 필요 항목

| 항목 | Plan 기재 | 최종 확정 | 상태 |
|------|-----------|-----------|:----:|
| 신설 파일 수 | "리졸버 신규" | `utility_llm_provider.py` + `cache_invalidation.py` 2개 (DR-4) | 📝 |
| 설정 개수 | 2개 | **3개** — `llm_instance_cache_max_entries` 추가 | 📝 |
| Plan §6.1의 `application/llm_model/resolver.py` | 별도 리졸버 파일 | `utility_llm_provider.py`로 대체 | 📝 |
| Plan §2.1-D "어댑터 5곳" | 패턴 A 3 + B 2 | **어댑터 9곳** (+ 패턴 C 4) — §11.2 정정 참조 | 📝 |
| Plan DoD "어댑터 5곳 파라미터 추가" | 5곳 | 9곳 | 📝 |

📝 = Plan 문서 미반영. 본 설계 문서(v0.2.0)와 Analysis(v0.1.0)를 우선 근거로 삼는다.

### 14.1 미해소 항목 (코드 조치 필요)

| ID | 항목 | 근거 |
|----|------|------|
| **G-7** | `create`/`update` UseCase 의 `execute` 가 57·55줄 (한도 40) | 변경 전부터 초과(50·48)였고 무효화 호출로 +7 |
| **V-3** | 패턴 C 4곳의 `from_openai()` 는 여전히 `ChatOpenAI` 즉시 생성 | `api_key` 를 명시 인자로 받는 기존 계약 유지. lazy 싱글톤이라 부팅은 무사하나, 키 없는 NPU 전용 환경에서 첫 호출 시 실패 |

### 14.2 환경 의존 미검증 (코드로 불가)

| ID | 항목 | 위험도 |
|----|------|:------:|
| **V-1** | vLLM tool-calling 검증 (Step 0) — 패턴 A/B 5곳이 전부 `with_structured_output` 사용 | **높음** |
| **V-2** | 실 MySQL + 실 NPU 에서의 무재시작 교체 | 중간 |

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-08-29 | 배상규 | 최초 작성 — 설계안 C 선택. 2계층 캐시(DR-1~3), 세션 규칙 준수 근거(§9.4), 설계 중 실측 4건(§13) |
| 0.2.0 | 2026-08-30 | 배상규 | 구현 결과 반영 (Analysis Gap G-1~G-4/G-6/G-8). **AD-6** `repo_builder` 주입(§2.2/§4.1), **DR-12** 레거시 chain 지연 생성(§13.0 실측), **DR-13** 패턴 C 메모이제이션 불요, §11.1 파일 구조 실제화(어댑터 5→9곳), §11.2 "패턴 C 무수정" 정정, §8.5 A7 · §8.5-b 통합 시나리오 추가, §14 미해소·미검증 분리 |
