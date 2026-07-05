# Design: self-hosted-qwen-endpoint

> Created: 2026-06-28
> Phase: Design
> Plan: `docs/01-plan/features/self-hosted-qwen-endpoint.plan.md`
> Scope: `idt/` 백엔드 — 폐쇄망 vLLM(OpenAI 호환) Qwen을 모델 레지스트리로 등록·호출 (모델별 `base_url` 지원)
> Code: LLM-MODEL-REG-002 (LLM-MODEL-REG-001 확장)

---

## 0. 확정된 설계 결정 (Plan Open Questions 답변)

| # | Open Question | 결정 |
|---|---------------|------|
| **D1** | vLLM 인증 토큰 유무 | **미정 → 양쪽 모두 수용.** `base_url`이 설정된 경우 api_key가 비어 있어도 통과하고 더미값 `"EMPTY"`로 호출. 실제 키가 있으면 `api_key_env`(예: `QWEN_API_KEY`)로 주입. |
| **D2** | `model_name` ↔ vLLM `--served-model-name` 일치 | **운영 가이드로 명시.** 코드는 등록값을 그대로 호출. 불일치 시 vLLM 404 → 등록 가이드 + (후속) 연결 테스트로 검증. |
| **D3** | 임베딩 self-host 포함 | **비목표.** 본 작업은 채팅/Agent용 LLM(`LLMFactory`) 경로만. 임베딩은 별도 과제. |
| **D4** | 신규 provider 추가 vs 재사용 | **`provider="openai"` 재사용 확정.** vLLM이 OpenAI 호환이므로 분기/어댑터 추가 없음. `base_url`만 모델별로 저장·전달. |
| **D5** | 엔드포인트 저장 위치 | **DB 컬럼(`llm_model.base_url`) 확정.** 멀티 모델·멀티 서버 대응. 환경변수 아님. |

---

## 1. 설계 개요

### 1-1. 핵심 아이디어
LLM 모델 레지스트리에 **모델별 `base_url`(옵셔널)** 한 축을 additive로 추가하고, `LLMFactory`가 이를 LangChain 클라이언트(`ChatOpenAI`/`ChatOllama`)에 전달한다. 신규 provider는 만들지 않는다.

- `base_url`이 **있으면** → 그 주소(폐쇄망 vLLM)로 호출, api_key 비어도 `"EMPTY"`로 통과.
- `base_url`이 **None이면** → 기존과 100% 동일 (api.openai.com / Anthropic / localhost Ollama).

### 1-2. 데이터 흐름

```
[Admin 등록]
POST /api/v1/llm-models
{ provider:"openai", model_name:"Qwen2.5-32B-Instruct",
  display_name:"사내 Qwen", base_url:"http://10.x.x.x:8000/v1",
  api_key_env:"QWEN_API_KEY", is_default:true }
        │
        ▼
[DB] llm_model.base_url 저장 (V035 컬럼)
        │  ← 채팅/Agent가 기본 모델 조회
        ▼
[LLMFactory.create]  provider="openai"
   ChatOpenAI(model="Qwen2.5-32B-Instruct",
              api_key=<QWEN_API_KEY or "EMPTY">,
              base_url="http://10.x.x.x:8000/v1",
              temperature=..., stream_usage=True)
        │
        ▼
[폐쇄망 GPU] vLLM /v1/chat/completions → Qwen 추론
```

---

## 2. 변경 상세

### 2-1. `src/domain/llm_model/entity.py` (Domain)

`LlmModel` 데이터클래스에 옵셔널 필드 추가 (가격 필드와 동일하게 기본값 보유 → 기존 생성자 호출 무영향).

```python
@dataclass
class LlmModel:
    ...
    api_key_env: str
    max_tokens: int | None
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime
    input_price_per_1k_usd: Decimal | None = None
    output_price_per_1k_usd: Decimal | None = None
    pricing_updated_at: datetime | None = None
    base_url: str | None = None   # ★ 신규: self-host 엔드포인트 (vLLM 등). None이면 provider 기본값
```

> docstring `Attributes`에 `base_url` 1줄 추가.

### 2-2. `src/infrastructure/llm_model/models.py` (ORM)

```python
    pricing_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    # LLM-MODEL-REG-002: self-host 엔드포인트 (vLLM/OpenAI 호환). V035 매핑.
    base_url: Mapped[str | None] = mapped_column(String(500))
```

### 2-3. `src/infrastructure/llm_model/llm_model_repository.py` (매핑)

`_to_orm` / `_to_domain` 양쪽에 `base_url=model.base_url` / `base_url=row.base_url` 추가.
`update()` 메서드 row 갱신부에 `row.base_url = model.base_url` 한 줄 추가 (수정 반영).

```python
    def _to_orm(self, model: LlmModel) -> LlmModelModel:
        return LlmModelModel(
            ...
            pricing_updated_at=model.pricing_updated_at,
            base_url=model.base_url,            # ★
        )

    def _to_domain(self, row: LlmModelModel) -> LlmModel:
        return LlmModel(
            ...
            pricing_updated_at=row.pricing_updated_at,
            base_url=row.base_url,              # ★
        )

    async def update(self, model, request_id):
        ...
        row.is_default = model.is_default
        row.base_url = model.base_url           # ★
        row.updated_at = model.updated_at
```

### 2-4. `src/infrastructure/llm/llm_factory.py` (핵심)

`_create_openai` / `_create_ollama`가 `base_url`을 전달하도록 수정. `_resolve_api_key`에 `allow_empty` 도입.

```python
    def _create_openai(self, llm_model, temperature) -> ChatOpenAI:
        # base_url(self-host)이 있으면 키 없이도 허용 → vLLM 더미키 "EMPTY"
        api_key = self._resolve_api_key(
            llm_model, allow_empty=bool(llm_model.base_url)
        )
        kwargs = dict(
            model=llm_model.model_name,
            api_key=api_key,
            temperature=temperature,
            stream_usage=True,
        )
        if llm_model.base_url:
            kwargs["base_url"] = llm_model.base_url   # ★ 폐쇄망 vLLM 주소
        return ChatOpenAI(**kwargs)

    def _create_ollama(self, llm_model, temperature) -> ChatOllama:
        kwargs = dict(model=llm_model.model_name, temperature=temperature)
        if llm_model.base_url:
            kwargs["base_url"] = llm_model.base_url   # ★ 보너스: 원격 Ollama
        return ChatOllama(**kwargs)

    def _resolve_api_key(self, llm_model, allow_empty: bool = False) -> str:
        api_key = os.environ.get(llm_model.api_key_env, "")
        if not api_key:
            if allow_empty:
                return "EMPTY"   # vLLM 인증 미사용 케이스
            raise RuntimeError(
                f"환경변수 '{llm_model.api_key_env}'가 설정되지 않았습니다. "
                f"provider={llm_model.provider}, model={llm_model.model_name}"
            )
        return api_key
```

> `_create_anthropic`은 변경 없음 (해당 없음).

### 2-5. `src/application/llm_model/schemas.py` (API 스키마)

```python
class CreateLlmModelRequest(BaseModel):
    ...
    is_default: bool = False
    base_url: str | None = Field(None, max_length=500)   # ★

class UpdateLlmModelRequest(BaseModel):
    ...
    is_default: bool | None = None
    base_url: str | None = Field(None, max_length=500)   # ★

class LlmModelResponse(BaseModel):
    ...
    pricing_updated_at: datetime | None = None
    base_url: str | None = None                          # ★ additive

    @classmethod
    def from_domain(cls, model):
        return cls(
            ...
            pricing_updated_at=model.pricing_updated_at,
            base_url=model.base_url,                      # ★
        )
```

### 2-6. UseCase

**`create_llm_model_use_case.py`** — 엔티티 생성 시 `base_url=request.base_url` 추가:
```python
            model = LlmModel(
                ...
                is_default=request.is_default,
                created_at=now,
                updated_at=now,
                base_url=request.base_url,    # ★
            )
```

**`update_llm_model_use_case.py`** — 부분 갱신 블록에 추가:
```python
            if request.base_url is not None:
                model.base_url = request.base_url   # ★
```
> 참고: 부분 업데이트라 `base_url=""`(빈 문자열)로 명시 전송 시 빈 값 저장. None은 "변경 안 함". 빈 문자열→None 정규화가 필요하면 UseCase에서 `or None` 처리(선택).

### 2-7. DB Migration

`db/migration/V035__alter_llm_model_add_base_url.sql`
```sql
-- LLM-MODEL-REG-002: self-host 엔드포인트(vLLM/OpenAI 호환) 모델별 저장
ALTER TABLE llm_model ADD COLUMN base_url VARCHAR(500) NULL;
```
> V032(`alter_mcp_server_registry_add_secrets`)와 동일한 NULL 허용 additive ALTER 패턴.

### 2-8. `.env.example`

```
# ── 폐쇄망 self-host LLM (vLLM/OpenAI 호환, LLM-MODEL-REG-002) ──
# vLLM에 인증이 없으면 EMPTY 더미값, 있으면 실제 토큰.
# 엔드포인트 주소는 모델 등록 시 base_url 로 지정한다.
QWEN_API_KEY=EMPTY
```

---

## 3. 레이어 / 아키텍처 적합성

| 항목 | 판정 | 근거 |
|------|------|------|
| 엔티티 `base_url` 필드 | ✅ Domain 순수값 | 외부 호출 없음, 단순 데이터 보관 |
| 팩토리 `base_url` 전달 | ✅ Infrastructure | LangChain 어댑터 조립 책임 (infra) |
| `"EMPTY"` 더미키 처리 | ✅ Infrastructure | 외부 클라이언트 호출 규약 → infra 적합 (비즈니스 규칙 아님) |
| 스키마 additive | ✅ Application | 요청/응답 계약, 기존 필드 불변 |
| domain→infra 참조 | ✅ 없음 | 엔티티는 값만 보유 |
| 로깅 / print | ✅ | 신규 print 없음, 기존 로깅 유지 |
| 하드코딩 | ✅ | 엔드포인트는 DB, 키는 env 참조 |

---

## 4. 영향 범위 & 회귀

| 파일 | 변경 | 회귀 위험 |
|------|------|-----------|
| `domain/llm_model/entity.py` | 옵셔널 필드 1개 | 기본값 None → 기존 생성 무영향 |
| `infrastructure/llm_model/models.py` | 컬럼 1개 | NULL 허용 → 기존 행 무영향 |
| `infrastructure/llm_model/llm_model_repository.py` | 매핑 3곳 | base_url None이면 동작 동일 |
| `infrastructure/llm/llm_factory.py` | openai/ollama 분기 + allow_empty | base_url None & 키 존재 시 기존과 동일 |
| `application/llm_model/schemas.py` | 필드 3곳 additive | 옵셔널 → 기존 프론트 영향 0 |
| `application/llm_model/create_/update_..._use_case.py` | base_url 전달 | additive |
| `db/migration/V035__*` | ALTER ADD | 무중단 |
| `.env.example` | 예시 1개 | 문서 |

### 4-1. 호출부 영향 확인
- `_resolve_api_key` 시그니처에 기본값 `allow_empty=False` → 기존 호출(`_create_openai`만 호출) 외 영향 없음.
- `LLMFactory.create` 진입점/`LlmModel` 생성자 호출부: 모든 신규 인자 기본값 보유 → 컴파일/런타임 호환.

---

## 5. 테스트 설계 (TDD)

### 5-1. Domain
`tests/domain/llm_model/test_entity_base_url.py`
| # | 케이스 | 단언 |
|---|--------|------|
| T1 | `LlmModel(..., base_url="http://x:8000/v1")` | `base_url` 보관 |
| T2 | base_url 미지정 생성 | `base_url is None` (하위호환) |

### 5-2. Infrastructure — LLMFactory
`tests/infrastructure/llm/test_llm_factory_base_url.py`
| # | 케이스 | 단언 |
|---|--------|------|
| T3 | provider=openai + base_url 有 | 생성된 `ChatOpenAI`의 endpoint가 base_url 반영 (`openai_api_base`/`root_client.base_url` 확인) |
| T4 | provider=openai + base_url None | base_url 미전달 (기존 동작) |
| T5 | base_url 有 + 환경변수 미설정 | 예외 없이 생성, 키 `"EMPTY"` 사용 |
| T6 | base_url None + 환경변수 미설정 | `RuntimeError` (기존 동작 유지) |
| T7 | provider=ollama + base_url 有 | `ChatOllama`에 base_url 전달 |

### 5-3. Infrastructure — Repository
`tests/infrastructure/llm_model/test_repository_base_url.py` (또는 기존 파일 보강)
| # | 케이스 | 단언 |
|---|--------|------|
| T8 | save→find_by_id | base_url 왕복 일치 |
| T9 | update(base_url 변경) | 갱신값 반영 |

### 5-4. Application — UseCase / Schema
`tests/application/llm_model/test_create_update_base_url.py`
| # | 케이스 | 단언 |
|---|--------|------|
| T10 | Create(base_url 포함) | 응답 `base_url` 반환, repo save 인자에 base_url |
| T11 | Update(base_url 변경) | 갱신 반영 |
| T12 | Response.from_domain | base_url additive 노출 |

### 5-5. 회귀
- 기존 `tests/.../llm_model` 및 `llm_factory` 테스트 전부 통과 (base_url 미사용 경로 불변).

### 5-6. 검증 스킬
- `/verify-architecture`, `/verify-logging`, 전체 pytest **격리 실행** (Windows 이벤트 루프 flakiness 회피 — backend-test-eventloop-flakiness 메모리 참조).

---

## 6. 구현 순서 (Do 단계)

1. **(Red)** T1·T2 작성 → 엔티티 필드 미존재로 실패.
2. **(Green)** `entity.py`에 `base_url` 추가 → T1·T2 통과.
3. **(Red)** T3~T7 작성 → 팩토리 미구현 실패.
4. **(Green)** `llm_factory.py` 수정 (base_url 전달 + allow_empty) → T3~T7 통과, T4·T6 회귀 확인.
5. **(Green)** `models.py` 컬럼 + `V035` 마이그레이션 작성.
6. **(Red→Green)** T8·T9 → `llm_model_repository.py` 매핑 3곳 수정.
7. **(Red→Green)** T10~T12 → `schemas.py` + create/update UseCase 수정.
8. **(verify)** verify-architecture / verify-logging / 전체 pytest 격리 실행.
9. **(후속)** `/api-contract-sync` → 프론트 타입/등록 폼 `base_url` 추가.

---

## 7. 리스크 / 주의

- **R1. vLLM streaming usage_metadata**: vLLM이 `stream_usage=True`에서 usage를 반환하지 않으면 토큰/비용 집계가 0. → best-effort 처리, 실연결 시 확인. (가격 컬럼은 옵셔널이므로 기능 동작에는 무해.)
- **R2. model_name 불일치(D2)**: 등록 `model_name`이 vLLM served name과 다르면 404. → 등록 가이드 명시 + 후속 연결 테스트.
- **R3. 빈 문자열 base_url**: Update에서 `base_url=""` 전송 시 빈 값 저장 가능 → 필요 시 UseCase에서 `request.base_url or None` 정규화 (구현 시 결정).
- **R4. 폐쇄망 미연결 통합검증 한계**: 단위 테스트로 base_url 전달을 보장하되, 실제 추론은 폐쇄망 내부에서 별도 확인 필요.

---

## 8. 다음 단계

```
/pdca do self-hosted-qwen-endpoint
```
