# judgment-backend Design Document

> **Summary**: Jev(TypeSafe)·AnyJev(폐쇄망)를 같은 `JudgmentPort` 뒤에 두는 타입 판정 모듈의 상세 설계와 `search_decision` 결선·폴백 명세
>
> **Feature**: judgment-backend
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-10-15
> **Status**: Draft
> **Planning Doc**: [judgment-backend.plan.md](../../01-plan/features/judgment-backend.plan.md)
> **Selected Architecture**: Option C — 실용 균형 (Checkpoint 3, 사용자 선택)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 판정형 LLM 호출이 전부 생성 모델에 묶여 있어 판정 전용 모델(Jev)로 못 바꾸고, 폐쇄망에서는 대체(AnyJev)가 필요한데 포트가 없다 |
| **WHO** | 1차: 운영자/배포 담당 — `.env` 한 줄로 백엔드 교체. 2차: 후속 개발자 — 포트에 질문만 얹어 다음 소비 지점 교체. 3차: 최종 사용자 — 동작 불변(폴백) |
| **RISK** | AnyJev HTTP 계약이 미검증이고 두 백엔드 모두 지금 실호출 불가 → 어댑터는 전송 계층 픽스처로 계약 고정, 실호출은 이월 체크리스트 |
| **SUCCESS** | `JUDGMENT_BACKEND=off`에서 기존 테스트 전량 무변경 통과, `jev`/`anyjev`에서 search_decision이 Noul 확률+임계값으로 결정, 백엔드 실패 시 폴백 100%, AST 경계 테스트 통과, 회귀 `FAILED` diff 0 |
| **SCOPE** | 이번: 포트(Noul+Choice) + Jev/AnyJev 어댑터 + 팩토리 + config + search_decision 교체·폴백 + 테스트. 제외: Score, 인프로세스 AnyJev, 다른 소비 지점, 관리자 UI, DB 레지스트리 |

---

## 0. Decision Record (Plan 미확정 항목 확정 + Design 결정)

Design 단계에서 외부 계약을 소스로 확인한 결과다. **Plan을 정정하는 항목은 굵게** 표시한다.

| ID | 결정 | 근거 |
|----|------|------|
| **D1** | **AnyJev Noul은 에뮬레이션하지 않고 `kind: "noul"`을 그대로 쓴다.** 응답 `probs` 키는 `"Yes"`/`"No"`(대문자 고정)이며 어댑터는 대소문자 무시로 읽는다 | `anyjev/tacit.py decide_batch`가 `KINDS = {"choice","yes_no","noul","score"}`를 받고, `readout.answer_labels`가 noul에 `["Yes","No"]`를 돌려준다. Plan §1.2 "Noul 미지원·로드맵"은 README 기준의 오류였다 — **Plan 정정** |
| D2 | AnyJev HTTP 요청은 항상 배치 형태 `{"items":[...]}`, 응답은 `{"decisions":[...]}` | `serve.py`가 `items` 키 유무로 단건/배치를 가르므로 한 모양만 쓰면 파싱 분기가 없다. 질문 N개 = 같은 `state`를 가진 item N개 |
| D3 | AnyJev item 필드: `state: str`, `question: str`, `kind: "noul"\|"choice"`, `options: list[str]`(choice만). 응답에서 읽는 키: `answer`, `probs`, `margin`, `route`, `reasoning_tokens` | `tacit.py decide_batch` 검증 코드(`question` 필수, `options` 2개 이상 distinct) 기준. 부가 필드는 질문 순서대로 `extra["decisions"][i] = {qid, margin, route, reasoning_tokens}`에 보존(v0.2 — 다중 질문이라 리스트 구조, Check G2) |
| D4 | AnyJev는 `model`을 응답에 주지 않으므로 `JudgmentResponse.model = settings.anyjev_model or "anyjev"` | 서버 CLI `--model`로 고정되는 값이라 요청에 넣을 수 없다 |
| D5 | AnyJev Choice는 criteria 설명을 질문 본문에 접는다: `"{instructions}\n선택지:\n- {label}: {desc}"`. `options`는 라벨 목록 | AnyJev `question`은 문자열 하나뿐. 포맷은 `anyjev/mapping.py` 순수 함수로 고정해 테스트한다 |
| D6 | AnyJev Choice `confidence = max(probs)`, `margin`은 `extra["decisions"][i]["margin"]`(D3) | AnyJev엔 Jev식 confidence가 없다. 근사치임을 docstring에 명시, 소비 지점은 `backend` 값으로 구분 가능 |
| D7 | **`typesafe-sdk`는 `httpx`가 아니라 `httpx2>=2.0`에 의존한다.** 어댑터는 `http_client: httpx2.AsyncClient | None` 주입을 받고, 테스트는 `httpx2.MockTransport`로 가짜 응답을 준다 | PyPI 메타데이터(0.7.5, 2026-10-14). 패키지명이 달라 기존 `httpx>=0.26` 과 충돌하지 않는다. Plan §5 "httpx 충돌" 리스크는 해소 |
| D8 | SDK 버전 `typesafe-sdk>=0.7.5,<0.8` optional extra `judgment`, 클라이언트는 `compression=False` | 0.x라 마이너 고정. `zstd` extra는 넣지 않는다 — SDK는 zstd 미설치 시 `TypeSafeError`를 던지므로(Check G6 정정) 압축을 명시적으로 끈다. 본문이 작아 손실 없음 |
| D9 | Jev 어댑터는 SDK 재시도를 **끈다**(`RetryPolicy(max_retries=0)`) | 폴백이 이미 있고 판정 지연 상한(`judgment_timeout_seconds`)을 지켜야 한다. 재시도는 상한을 깨뜨린다 |
| D10 | 예외 매핑 — Jev: `TypeSafeAPITimeoutError→JudgmentTimeoutError`, `TypeSafeAPIConnectionError→JudgmentUnavailableError`, `TypeSafeAPIError`(401/429/5xx 포함)`→JudgmentUnavailableError(status=)`, `TypeSafeAPIResponseValidationError→JudgmentProtocolError`. AnyJev: `httpx.TimeoutException→Timeout`, `httpx.TransportError`·4xx/5xx`→Unavailable`, JSON/키 누락·확률 검증 실패`→Protocol` | SDK 예외 계층(`exceptions.md`) 기준. 소비 지점은 `JudgmentError` 하나만 잡는다 |
| D11 | domain VO는 **dataclass(frozen)** — pydantic 불사용 | `prompt_guard` domain AST 테스트가 pydantic을 금지한 선례를 따른다. 검증(확률 범위·합)은 `__post_init__` |
| D12 | `JudgmentRequest.state`는 `str \| Mapping[str, str]`. Jev엔 dict 그대로(이름 있는 JSON 필드 권장), AnyJev엔 `"[key]\n{value}"` 블록으로 직렬화 | TypeSafe 문서 "컨텍스트가 여러 부분이면 named JSON 필드". AnyJev `state`는 문자열 |
| D13 | Noul 임계값 비교는 `probability >= threshold` | Plan FR-10. 경계값 0.50은 True |
| D14 | `WebSearchDecision.reason = "judgment:{backend} p={p:.2f} thr={thr:.2f}"`, 폴백 시 reason은 폴백 어댑터 결과 그대로 | 운영자가 이력에서 어느 경로였는지 식별 |
| D15 | 클라이언트는 앱 수명 싱글턴, `JudgmentPort.aclose()`를 포트에 두고 `main.py` lifespan shutdown에서 best-effort 호출 | 위키 app-lifetime-client-singleton. 닫기 실패는 warning만 |
| D16 | `anyjev_base_url` 호스트 검증은 하지 않는다(스킴 `http/https`만 검증). 내부망 전용은 `.env.example` 주석과 config docstring으로 | Plan §5 "문서화" 결정. 호스트 화이트리스트는 배포마다 달라 코드에 못 박지 않는다 |
| D17 | 질문 상수(`SEARCH_DECISION_NOUL`)는 `infrastructure/search_decision/questions.py`에 두고 `judgment_adapter.py`만 읽는다 | Plan FR-13. domain은 질문 문구를 모른다(프롬프트는 infrastructure 관심사 — 기존 `_SYSTEM` 상수와 같은 층) |

---

## 1. Overview

### 1.1 Design Goals

1. `judgment_backend=off`(기본)면 코드 경로·로그·테스트가 지금과 바이트 단위로 같다.
2. 포트는 백엔드 차이(SDK vs HTTP, Noul 네이티브 vs 라벨 명명, confidence 유무)를 전부 어댑터 안에서 흡수하고, 소비 지점은 `NoulAnswer.probability` 하나만 본다.
3. 어떤 실패도 포트 밖으로는 `JudgmentError` 계열 하나로 나가고, 삼키는 곳은 `JudgmentSearchDecisionAdapter` 한 곳이다.
4. 두 어댑터 모두 **전송 계층 주입**이 가능해 실호출 없이 계약 테스트가 된다.

### 1.2 Design Principles

- **탈착형 이음매**: 팩토리 None, 앱 수명 1회 조립, AST 경계 테스트(위키 detachable-module-seam).
- **degraded 경계**: 포트는 던지고, "쓸 수 있는 결과"(기존 LLM 판정)를 아는 소비 지점 어댑터만 흡수(위키 degradation-vs-failure-boundary).
- **config 단일 출처**: 새 키 8개 전부 docstring에 소비 지점 명기. 임계값은 소비 지점 키 1개.
- **additive**: `SearchDecisionInterface`·`ExcelAnalysisWorkflow`·`WebSearchDecision` 무변경. 신규 어댑터는 기존 어댑터를 `fallback`으로 감싼다.

---

## 2. Architecture

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | **Option C: Pragmatic** |
|----------|:-:|:-:|:-:|
| Approach | 포트 없이 `LLMSearchDecisionAdapter` 안에 backend 분기 + 클라이언트 1파일 | C + `application/judgment/` 서비스(캐시·메트릭·질문 레지스트리) + 백엔드 플러그인 레지스트리 | Plan §7.3 구조: domain 포트/VO + 어댑터 2개 + 팩토리 + 소비 지점 어댑터 |
| New Files | 1 | ~14 | 9 (+테스트 8) |
| Modified Files | 3 | 4 | 4 |
| Complexity | Low | High | Medium |
| Maintainability | Low (다음 소비 지점마다 복사) | High | High |
| Effort | Low | High | Medium |
| Risk | "단독 모듈" 요구 미충족 | 소비처 1곳에 두꺼운 DDD(CLAUDE.md §6 금지) | 균형 |

**Selected**: Option C — 포트·어댑터·팩토리만 두고, 두 번째 소비 지점이 생기기 전에는 서비스 계층·레지스트리를 만들지 않는다.

### 2.1 Component Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│ api/main.py                                                                │
│   get_judgment_backend() ── judgment_backend=off / 누락 / ImportError → None│
│        │ build_judgment_backend(settings, logger)                          │
│        ▼                                                                   │
│   search_decision = backend is None                                        │
│        ? LLMSearchDecisionAdapter(...)                 (기존 그대로)         │
│        : JudgmentSearchDecisionAdapter(backend, fallback=LLMSearchDecision…)│
│        │                                                                   │
│        ▼ (SearchDecisionInterface — 무변경)                                 │
│ application/workflows/excel_analysis_workflow.py:236  decide()             │
└────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────┐    ┌──────────────────────────────────────┐
│ infrastructure/search_decision/ │    │ domain/judgment/                     │
│  judgment_adapter.py            │───▶│  interfaces.py   JudgmentPort(ABC)   │
│   state={question,analysis_text}│    │  value_objects.py NoulQuestion …     │
│   Noul 1개 → p >= thr           │    │  exceptions.py   JudgmentError …     │
│   JudgmentError → fallback      │    └──────────────────────────────────────┘
│  questions.py SEARCH_DECISION_NOUL│                 ▲ 구현
└─────────────────────────────────┘                  │
                     ┌───────────────────────────────┴──────────────────────┐
                     │ infrastructure/judgment/                              │
                     │  factory.py   build_judgment_backend()                │
                     │  jev/adapter.py    typesafe-sdk AsyncTypeSafeClient   │
                     │  jev/mapping.py    VO → Noul/Choice, Response → VO    │
                     │  anyjev/adapter.py httpx POST /v1/decide {items}      │
                     │  anyjev/mapping.py state 직렬화·Choice 접기·probs → VO │
                     └───────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
decide(question, analysis_text, request_id)
  │
  ├─ JudgmentRequest(state={"question": q, "analysis_text": a},
  │                  questions={"needs_web_search": NoulQuestion(SEARCH_DECISION_NOUL)})
  │
  ├─ backend.judge(req)  ── asyncio.wait_for(…, judgment_timeout_seconds + 0.5)  ← 외부 안전망
  │     │
  │     ├─ Jev:    client.system_one(state=dict, questions={id: Noul(instructions=…)},
  │     │                            model=…, timeout=…)  → resp.nouls[id].noul
  │     └─ AnyJev: POST {base}/v1/decide {"items":[{"state": "[question]\n…\n\n[analysis_text]\n…",
  │                                                  "question": …, "kind": "noul"}]}
  │                → decisions[0].probs["Yes"]  (대소문자 무시)
  │
  ├─ 성공: p = resp.nouls["needs_web_search"].probability
  │        WebSearchDecision(needs_web_search = p >= thr, reason="judgment:jev p=0.73 thr=0.50")
  │        logger.debug(backend, model, latency_ms, probability, request_id)
  │
  └─ JudgmentError / TimeoutError: logger.warning(…, exception=e, backend, request_id)
                                   → return await fallback.decide(question, analysis_text, request_id)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `domain/judgment` | stdlib(`abc`,`dataclasses`,`enum`,`typing`,`math`) | 포트·VO·예외 |
| `infrastructure/judgment/jev` | `typesafe_sdk`(optional), `httpx2`(SDK 전이), domain | Jev 호출 |
| `infrastructure/judgment/anyjev` | `httpx`(기존 의존), domain | AnyJev 호출 |
| `infrastructure/judgment/factory` | `src.config.Settings`, 두 어댑터(지연 import), `LoggerInterface` | 백엔드 선택·None 폴백 |
| `infrastructure/search_decision/judgment_adapter` | domain/judgment, domain/search_decision, `LoggerInterface` | 판정 + 폴백 |
| `api/main.py` | factory, judgment_adapter | 조립 1곳 |

---

## 3. Data Model

### 3.1 Domain VO (`src/domain/judgment/value_objects.py`)

```python
class JudgmentBackendKind(str, Enum):
    JEV = "jev"
    ANYJEV = "anyjev"
    OFF = "off"

    @classmethod
    def from_string(cls, raw: str | None) -> "JudgmentBackendKind":
        # None/""/대소문자 무시 → OFF 가 아니라 ValueError (오타를 조용히 off 로 만들지 않는다)
        ...

@dataclass(frozen=True)
class NoulQuestion:
    instructions: str                    # 비어 있으면 ValueError

@dataclass(frozen=True)
class ChoiceQuestion:
    instructions: str
    criteria: tuple[tuple[str, str | None], ...]   # (label, description) 순서 보존, 라벨 2개 이상·중복 금지

Question = NoulQuestion | ChoiceQuestion

@dataclass(frozen=True)
class JudgmentRequest:
    state: str | Mapping[str, str]       # dict 는 키 순서 보존 (AnyJev 직렬화 순서)
    questions: Mapping[str, Question]    # id → 질문. 비어 있으면 ValueError

@dataclass(frozen=True)
class NoulAnswer:
    probability: float                   # 0.0 ≤ p ≤ 1.0 (NaN·범위 밖 → ValueError)

@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probabilities: Mapping[str, float]   # 키 집합 == criteria 라벨 집합, 합 1±0.01
    confidence: float                    # 0~1

Answer = NoulAnswer | ChoiceAnswer

@dataclass(frozen=True)
class JudgmentResponse:
    answers: Mapping[str, Answer]        # 요청 questions 의 키 집합과 동일 (어댑터가 보장)
    model: str                           # 실제 응답 모델 id (Jev) / 설정 모델명 (AnyJev)
    backend: JudgmentBackendKind
    latency_ms: int                      # 어댑터가 monotonic 으로 측정 (위키 run-step latency)
    extra: Mapping[str, object] = field(default_factory=dict)   # 백엔드 부가 정보 (margin, route, usage…)

    def noul(self, qid: str) -> NoulAnswer     # 타입 불일치면 JudgmentProtocolError
    def choice(self, qid: str) -> ChoiceAnswer
```

검증 규칙은 전부 `__post_init__`에서 `ValueError`로 던지고, 어댑터는 이를 잡아 `JudgmentProtocolError`로 바꾼다(백엔드가 깨진 확률을 보냈다는 뜻).

### 3.2 예외 (`src/domain/judgment/exceptions.py`)

```
JudgmentError(Exception)                 backend: JudgmentBackendKind
├─ JudgmentTimeoutError                  timeout_seconds: float
├─ JudgmentUnavailableError              status: int | None   (연결 실패·4xx/5xx·키 없음·서버 다운)
└─ JudgmentProtocolError                 detail: str          (응답 스키마·확률 검증 실패)
```

`str(e)`에 API 키·state 원문을 넣지 않는다.

### 3.3 포트 (`src/domain/judgment/interfaces.py`)

```python
class JudgmentPort(ABC):
    kind: JudgmentBackendKind            # 클래스 속성

    @abstractmethod
    async def judge(self, request: JudgmentRequest) -> JudgmentResponse: ...

    async def aclose(self) -> None:      # 기본 no-op
        return None
```

### 3.4 Database Schema

없음(마이그레이션 0).

---

## 4. 외부 계약 명세

### 4.1 Jev (`typesafe-sdk` 0.7.x)

| 항목 | 값 |
|------|----|
| 클라이언트 | `AsyncTypeSafeClient(api_key=, base_url=, model=, timeout=, retry=RetryPolicy(max_retries=0), compression=False, http_client=)` — 전부 명시 인자(FR-04) |
| 호출 | `await client.system_one(state=dict|str, questions={qid: Noul(instructions=…) | Choice(instructions=…, criteria={label: desc})}, model=…, timeout=…)` |
| 응답 | `resp.model: str`, `resp.nouls[qid].noul: float`, `resp.choices[qid].choice/.probabilities/.confidence`, `resp.usage.input_tokens` |
| 예외 | §0 D10 매핑 |
| 모델 기본 | `jev-latest`(현재 1.13). `.env`로 `jev-preview`/버전 id 가능 |
| 테스트 | `http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler))` — 응답 JSON은 `api.md` 예시 그대로: `{"model":"jev-1.13.0","answers":{"needs_web_search":{"type":"noul","noul":0.73}},"usage":{"input_tokens":120,"output_tokens":0}}` |

Choice criteria 변환: `tuple[(label, desc)]` → `{label: desc}` (desc None 허용, SDK가 `None` 라벨 설명을 받는다).

### 4.2 AnyJev (`python -m anyjev.serve`, 기본 `127.0.0.1:8100`)

**Request** `POST {anyjev_base_url}/v1/decide`
```json
{"items": [
  {"state": "[question]\n환율 전망은?\n\n[analysis_text]\n…", "question": "<instructions>", "kind": "noul"},
  {"state": "…", "question": "<instructions>\n선택지:\n- bar: 막대\n- line: 선", "kind": "choice", "options": ["bar", "line"]}
]}
```
- `state`: dict면 D12 직렬화(`"[key]\n{value}"`를 빈 줄로 연결), str이면 그대로.
- Noul은 `options` 없음(서버가 무시). Choice는 라벨 ≥ 2·중복 없음(VO가 선검증).

**Response 200**
```json
{"decisions": [
  {"answer": "Yes", "index": 0, "probs": {"Yes": 0.73, "No": 0.27}, "margin": 0.99, "route": "one_forward"},
  {"answer": "bar", "index": 0, "probs": {"bar": 0.8, "line": 0.2}, "margin": 1.39, "route": "cot", "reasoning_tokens": 311}
]}
```
- Noul: `probs` 중 키를 `casefold()`해 `"yes"`를 찾는다. 없으면 `JudgmentProtocolError`.
- Choice: `probs` 키 집합이 `options`와 정확히 같아야 한다. `confidence = max(probs.values())`(D6).
- `decisions` 길이가 `items`와 다르면 `JudgmentProtocolError`.

**Errors**: `400 {"error": …}`(검증), `502`(vLLM 불통), `404`(경로). 모두 `JudgmentUnavailableError(status=)`. 연결·타임아웃은 `httpx` 예외 → D10.

**Health**: `GET /health → {"ok": true}` — 팩토리는 기동 시 호출하지 **않는다**(기동 지연·폐쇄망 순서 의존 방지). 운영 확인용으로 `.env.example` 주석에만 적는다.

### 4.3 Config (`src/config.py`)

```python
    # Judgment Backend (judgment-backend Design §4.3)
    # 소비 지점은 전부 src/api/main.py get_judgment_backend() → infrastructure/judgment/factory.py.
    # "jev" | "anyjev" | "off". off(기본)면 팩토리가 None → search_decision 은 기존 LLM 어댑터 그대로.
    # 오타는 ValueError → 조립 실패 → None + warning 1회 (prompt_guard_mode 와 같은 함정).
    judgment_backend: str = "off"
    # 판정 1회 타임아웃(초). 두 어댑터 모두 적용, 초과 시 JudgmentTimeoutError → 소비 지점 폴백.
    # 소비: factory.py → JevJudgmentAdapter(timeout=) / AnyJevJudgmentAdapter(timeout=).
    judgment_timeout_seconds: float = 3.0
    # Jev — 소비: factory.py _build_jev(). 키 없으면 조립 실패 → None.
    typesafe_api_key: str | None = None
    typesafe_base_url: str | None = None          # None 이면 SDK 기본(https://api.typesafe.ai)
    typesafe_model: str = "jev-latest"
    # AnyJev — 소비: factory.py _build_anyjev(). URL 없으면 조립 실패 → None.
    # anyjev.serve 는 인증이 없다 — 내부망 주소만 넣을 것 (스킴 http/https 만 검증, 호스트는 검증 안 함).
    anyjev_base_url: str | None = None
    anyjev_model: str | None = None               # 응답 model 표기용 (요청엔 안 실림, 서버 --model 이 결정)
    # search_decision Noul 확률 → bool 임계값 (p >= thr 이면 웹검색 필요).
    # 소비: main.py → JudgmentSearchDecisionAdapter(threshold=). 0~1 밖이면 ValueError.
    search_decision_judgment_threshold: float = 0.5
```

`.env.example` 블록(8키 + 주석 "jev 전용 / anyjev 전용 / health: curl {ANYJEV_BASE_URL}/health").

### 4.4 팩토리 (`src/infrastructure/judgment/factory.py`)

```python
def build_judgment_backend(settings: Settings, logger: LoggerInterface) -> JudgmentPort | None:
    kind = JudgmentBackendKind.from_string(settings.judgment_backend)   # ValueError 전파 (호출측이 잡음)
    if kind is JudgmentBackendKind.OFF:
        return None
    if kind is JudgmentBackendKind.JEV:
        return _build_jev(settings, logger)       # ImportError(typesafe_sdk 미설치)·키 없음 → 예외 전파
    return _build_anyjev(settings, logger)        # URL 없음·스킴 오류 → 예외 전파
```

`main.py`:
```python
_judgment_backend: Optional["JudgmentPort"] = None
_judgment_backend_built = False

def get_judgment_backend() -> Optional["JudgmentPort"]:
    """judgment-backend Design §4.4 — None 이면 판정 백엔드 비활성 (FR-09)."""
    global _judgment_backend, _judgment_backend_built
    if _judgment_backend_built:
        return _judgment_backend
    _judgment_backend_built = True
    if settings.judgment_backend == "off":
        return None
    try:
        from src.infrastructure.judgment.factory import build_judgment_backend
        _judgment_backend = build_judgment_backend(settings, get_app_logger())
    except Exception as e:  # noqa: BLE001 — 판정 백엔드 조립 실패가 앱 기동을 막으면 안 된다
        get_app_logger().warning("judgment backend assembly failed — disabled", exception=e)
    return _judgment_backend
```

`get_prompt_guard()`(main.py:869)와 같은 모양. `search_decision` 조립(main.py:1144):
```python
    llm_search_decision = LLMSearchDecisionAdapter(logger=app_logger, llm_provider=get_utility_llm_provider())
    backend = get_judgment_backend()
    search_decision = (
        llm_search_decision if backend is None
        else JudgmentSearchDecisionAdapter(
            backend=backend, fallback=llm_search_decision,
            threshold=settings.search_decision_judgment_threshold,
            timeout_seconds=settings.judgment_timeout_seconds, logger=app_logger,
        )
    )
```
lifespan shutdown: `if _judgment_backend is not None: await _judgment_backend.aclose()` (try/except warning).

### 4.5 소비 지점 어댑터 (`src/infrastructure/search_decision/judgment_adapter.py`)

```python
class JudgmentSearchDecisionAdapter(SearchDecisionInterface):
    def __init__(self, backend: JudgmentPort, fallback: SearchDecisionInterface,
                 threshold: float, timeout_seconds: float, logger: LoggerInterface) -> None

    async def decide(self, question, analysis_text, request_id) -> WebSearchDecision:
        req = JudgmentRequest(state={"question": question, "analysis_text": analysis_text},
                              questions={QID: NoulQuestion(SEARCH_DECISION_NOUL)})
        try:
            resp = await asyncio.wait_for(self._backend.judge(req), self._timeout + 0.5)
        except (JudgmentError, asyncio.TimeoutError) as e:
            self._logger.warning("judgment failed, falling back to LLM search decision",
                                 exception=e, backend=self._backend.kind.value, request_id=request_id)
            return await self._fallback.decide(question, analysis_text, request_id)
        p = resp.noul(QID).probability
        self._logger.debug("judgment search decision", backend=…, model=resp.model,
                           latency_ms=resp.latency_ms, probability=round(p, 3), request_id=request_id)
        return WebSearchDecision(needs_web_search=p >= self._threshold,
                                 reason=f"judgment:{resp.backend.value} p={p:.2f} thr={self._threshold:.2f}")
```
- `asyncio.wait_for`는 단일 코루틴에만 쓴다(제너레이터 아님 — 위키 sse-heartbeat 해당 없음). `+0.5`는 어댑터 내부 타임아웃이 먼저 발동하게 두는 외부 안전망.
- `resp.noul()`의 `JudgmentProtocolError`도 위 except로 잡힌다(`JudgmentError` 하위).
- state 원문은 로그에 싣지 않는다(FR-14). 길이·해시도 debug에만.

`questions.py`:
```python
QID = "needs_web_search"
SEARCH_DECISION_NOUL = (
    "state.question 은 사용자의 질문, state.analysis_text 는 엑셀 데이터만으로 작성한 분석 답변이다. "
    "답변을 완성하려면 엑셀에 없는 최신 시세·뉴스·외부 통계 같은 정보가 추가로 필요한가? "
    "엑셀 데이터만으로 충분히 답했으면 아니오."
)
```
기존 `_SYSTEM` 프롬프트와 같은 판단 기준(애매하면 아니오 쪽)을 문장으로 옮긴 것. 문구 조정은 이 파일 한 곳.

---

## 5. UI/UX Design

해당 없음(프론트 변경 0).

---

## 6. Error Handling

### 6.1 실패 → 동작 표

| 상황 | 포트 예외 | 소비 지점 동작 | 로그 |
|------|----------|---------------|------|
| `judgment_backend=off` | — (backend None) | 기존 LLM 어댑터 그대로 | 없음 |
| 오타(`jev2`)·키/URL 누락·SDK 미설치 | — (조립 예외) | None → 기존 어댑터 | warning 1회(기동) |
| Jev 401/403/429/5xx | `JudgmentUnavailableError(status)` | 폴백 | warning(`exception=e`) |
| Jev 타임아웃 | `JudgmentTimeoutError` | 폴백 | warning |
| Jev 응답 검증 실패(SDK) | `JudgmentProtocolError` | 폴백 | warning |
| AnyJev 400/404/502, 연결 거부, 디코딩 오류(`httpx.RequestError` 전체) | `JudgmentUnavailableError` | 폴백 | warning |
| 백엔드 on + `search_decision_judgment_threshold` 0~1 밖 | — (조립 예외) | 조립 분기에서 흡수 → 기존 어댑터 (v0.2, Check G5) | warning 1회(기동) |
| AnyJev `probs`에 Yes 없음·길이 불일치·확률 범위 밖 | `JudgmentProtocolError` | 폴백 | warning |
| 외부 `wait_for` 초과 | `asyncio.TimeoutError` | 폴백 | warning |
| 폴백 어댑터도 실패 | — | 기존 동작(`needs_web_search=False`, 기존 error 로그) | 기존 |
| `aclose()` 실패 | — | 무시 | warning |

### 6.2 Error Response Format

HTTP 응답 없음(내부 모듈). 예외 메시지 형식: `"{backend}: {원인 요약}"` — 키·URL 쿼리·state 원문 금지.

---

## 7. Security Considerations

- [x] `typesafe_api_key`는 로그·예외·`repr`에 노출 금지(어댑터 `__repr__` 미정의 또는 마스킹)
- [x] AnyJev 서버 무인증 — `.env.example`·config docstring에 내부망 전용 명시(D16)
- [x] state에 사용자 질문·분석 본문이 들어간다 → 로그에는 길이·SHA-256 앞 12자만(FR-14)
- [x] `anyjev_base_url` 스킴 `http/https` 외 거부(ValueError → 조립 실패)
- [ ] HTTPS 강제 — Jev는 SDK 기본 https. AnyJev는 내부망 http 허용(결정)
- [ ] Rate limiting — Jev 429는 폴백으로 흡수, 재시도 없음(D9)

---

## 8. Test Plan

> 백엔드 전용 모듈이라 L1=단위·계약, L2=조립·결선, L3=실호출 스모크로 읽는다.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1 단위·계약 | domain VO 검증, 두 어댑터 매핑, 전송 픽스처 | pytest, `httpx.MockTransport`, `httpx2.MockTransport` | Do |
| L2 조립·결선 | 팩토리 분기, `main.py` 조립 결과 타입, search_decision 폴백 | pytest, TestClient | Do |
| L3 실호출 | Jev·AnyJev 각 1회 | `pytest -m llm` (env 없으면 skip) | **이월** |
| 경계 | AST import 규칙 | pytest | Do |
| 회귀 | 전체 스위트 `FAILED` diff | `uv run python -m pytest` | Do 종료·Check |

### 8.2 L1 — 단위·계약

| # | 대상 | 시나리오 | 기대 |
|---|------|----------|------|
| 1 | `NoulAnswer` | p=-0.1 / 1.1 / NaN | `ValueError` |
| 2 | `ChoiceAnswer` | 키 누락 / 합 0.9 | `ValueError`; 합 1.005는 통과 |
| 3 | `ChoiceQuestion` | 라벨 1개 / 중복 | `ValueError` |
| 4 | `JudgmentRequest` | questions 비어 있음 | `ValueError` |
| 5 | `JudgmentBackendKind.from_string` | `"JEV"`·`" jev "` → JEV, `"jev2"`·None → `ValueError` | |
| 6 | `JudgmentResponse.noul()` | Choice 답을 noul로 요청 | `JudgmentProtocolError` |
| 7 | jev/mapping | VO → SDK `Noul`/`Choice`(criteria dict, desc None 보존) | 필드 일치 |
| 8 | jev/adapter | MockTransport 200(api.md 예시) | `nouls` p=0.73, `model="jev-1.13.0"`, `extra["usage"]` |
| 9 | jev/adapter | 401 / 429 / 500 | `JudgmentUnavailableError(status=…)` |
| 10 | jev/adapter | 타임아웃(transport가 `httpx2.TimeoutException`) | `JudgmentTimeoutError` |
| 11 | jev/adapter | 응답 `noul` 누락 | `JudgmentProtocolError` |
| 12 | jev/adapter | 재시도 0 — 500 응답 시 transport 호출 횟수 == 1 | |
| 13 | anyjev/mapping | dict state 직렬화 순서·형식, Choice 질문 접기 포맷, Noul은 options 없음 | 고정 문자열 스냅샷 |
| 14 | anyjev/adapter | 200 `decisions`(Yes/No) | p=0.73, `extra["margin"]`, `model=anyjev_model` |
| 15 | anyjev/adapter | `probs` 키가 `"yes"` 소문자 | 통과(casefold) |
| 16 | anyjev/adapter | `probs`에 Yes 없음 / decisions 길이 불일치 / 확률 1.2 | `JudgmentProtocolError` |
| 17 | anyjev/adapter | 400 / 502 / 연결 거부 / 타임아웃 | Unavailable ×3, Timeout |
| 18 | anyjev/adapter | Choice 응답 — `confidence == max(probs)` | |
| 19 | 두 어댑터 | 요청 2문항(Noul+Choice) → answers 키 집합 == questions 키 집합 | |
| 20 | 두 어댑터 | `str(e)`에 api_key·state 문자열 미포함 | |

### 8.3 L2 — 조립·결선

| # | 대상 | 시나리오 | 기대 |
|---|------|----------|------|
| 1 | factory | `off` | `None` |
| 2 | factory | `jev` + 키 없음 / `anyjev` + URL 없음 / URL 스킴 `ftp://` | `ValueError` 전파 |
| 3 | factory | `jev` + `typesafe_sdk` 미설치(`sys.modules` 패치) | `ImportError` 전파 |
| 4 | factory | `jev`·`anyjev` 정상 | 각 어댑터 인스턴스, `kind` 일치 |
| 5 | main.py `get_judgment_backend` | 조립 예외 | `None` + warning 1회, 두 번째 호출은 warning 없음 |
| 6 | main.py 조립 | backend None | `search_decision`이 `LLMSearchDecisionAdapter` |
| 7 | main.py 조립 | backend 있음 | `JudgmentSearchDecisionAdapter`, `fallback`이 LLM 어댑터 |
| 8 | JudgmentSearchDecisionAdapter | p=0.49/0.50/0.51, thr=0.5 | False/True/True |
| 9 | 〃 | 성공 시 | `fallback.decide` 호출 0회, reason 형식 |
| 10 | 〃 | Timeout / Unavailable / Protocol / 외부 wait_for 초과 | `fallback.decide` 1회, 그 반환값 그대로, warning 1회 |
| 11 | 〃 | 폴백도 예외 | 예외 전파하지 않고 폴백 어댑터의 기존 degrade 결과 |
| 12 | 경계 AST | `domain/judgment` stdlib+자기 패키지만, pydantic·httpx·typesafe 금지; `infrastructure/judgment`는 `src.application.*` 금지; `judgment` 패키지 외부 참조는 `_DECLARED_CONSUMERS`(`main.py`, `search_decision/judgment_adapter.py`)만 | |
| 13 | 회귀 | `judgment_backend=off` 기본으로 전체 스위트 | master `FAILED` 목록과 diff 0 |

### 8.4 L3 — 실호출 스모크 (`tests/infrastructure/judgment/test_real_backend_smoke.py`, `-m llm`)

| # | 조건 | 시나리오 | 기대 |
|---|------|----------|------|
| 1 | `TYPESAFE_API_KEY` 있음 | Noul "하늘은 파란가" + Choice 2지 | p>0.5, choice 일치, model 문자열 `jev-` 접두 |
| 2 | `ANYJEV_BASE_URL` 있음 + `/health` ok | 동일 | p>0.5, decisions 2건 |
| 3 | 환경변수 없음 | — | `pytest.skip` |

**실행은 이월**(Plan DoD). 환경 확보 시 양성 대조군 벤치(정상 N + 웹검색 필요 M)를 추가해 임계값을 조정한다.

### 8.5 Seed Data

없음. 픽스처는 `tests/fixtures/judgment/{jev,anyjev}_*.json`(문서 예시 응답).

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| Domain | 포트·VO·예외·enum | `src/domain/judgment/` |
| Infrastructure | SDK/HTTP 어댑터, 팩토리, 소비 지점 어댑터·질문 상수 | `src/infrastructure/judgment/`, `src/infrastructure/search_decision/` |
| Application | (무변경) `ExcelAnalysisWorkflow`는 `SearchDecisionInterface`만 안다 | `src/application/workflows/` |
| Composition | 조립 1곳 | `src/api/main.py` |

### 9.2 Dependency Rules

```
application/workflows ──▶ domain/search_decision ◀── infrastructure/search_decision/judgment_adapter
                                                              │
                                                              ▼
                                             domain/judgment ◀── infrastructure/judgment/{jev,anyjev,factory}
                                                                          ▲
                                                              api/main.py ┘ (유일한 조립 지점)
```

- `domain/judgment`: stdlib만. pydantic·httpx·typesafe_sdk·langchain 금지.
- `infrastructure/judgment`: `src.domain.*`·`src.config`·외부 SDK만. `src.application.*` 금지.
- `judgment` 패키지를 import하는 외부 파일은 `main.py`와 `search_decision/judgment_adapter.py` 두 곳뿐(`_DECLARED_CONSUMERS`).

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `domain/judgment` | stdlib, `src.domain.judgment.*` | 그 외 전부 |
| `infrastructure/judgment/*` | `src.domain.*`, `src.config`, `typesafe_sdk`, `httpx`, `httpx2` | `src.application.*`, `src.api.*` |
| `infrastructure/search_decision/judgment_adapter` | `src.domain.judgment`, `src.domain.search_decision`, `src.domain.logging` | `src.infrastructure.judgment.*`(구현 직접 참조 금지 — 포트만) |
| `api/main.py` | 전부 | — |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `JudgmentPort`, VO, 예외 | Domain | `src/domain/judgment/{interfaces,value_objects,exceptions}.py` |
| `JevJudgmentAdapter` + mapping | Infrastructure | `src/infrastructure/judgment/jev/{adapter,mapping}.py` |
| `AnyJevJudgmentAdapter` + mapping | Infrastructure | `src/infrastructure/judgment/anyjev/{adapter,mapping}.py` |
| `build_judgment_backend` | Infrastructure | `src/infrastructure/judgment/factory.py` |
| `JudgmentSearchDecisionAdapter`, `SEARCH_DECISION_NOUL` | Infrastructure | `src/infrastructure/search_decision/{judgment_adapter,questions}.py` |
| `get_judgment_backend`, 조립 분기, lifespan close | Composition | `src/api/main.py` |

---

## 10. Coding Convention Reference

### 10.1 Naming

| Target | Rule | Example |
|--------|------|---------|
| 패키지 | snake_case | `judgment`, `jev`, `anyjev` |
| 어댑터 | `<Backend>JudgmentAdapter` | `JevJudgmentAdapter` |
| 예외 | `Judgment<Cause>Error` | `JudgmentTimeoutError` |
| 질문 상수 | UPPER_SNAKE | `SEARCH_DECISION_NOUL`, `QID` |
| config 키 | `judgment_*`, `typesafe_*`, `anyjev_*`, `search_decision_judgment_threshold` | — |

### 10.2 Import Order

stdlib → third-party(`httpx`, `typesafe_sdk`) → `src.domain` → `src.infrastructure`(어댑터 내부에서는 자기 패키지만). `typesafe_sdk` import는 `jev/adapter.py` 모듈 상단(모듈 import 자체가 팩토리의 ImportError 지점).

### 10.3 Environment Variables

| Prefix | Purpose | Scope |
|--------|---------|-------|
| `JUDGMENT_` | 백엔드 선택·타임아웃 | Server |
| `TYPESAFE_` | Jev 전용 | Server(jev) |
| `ANYJEV_` | AnyJev 전용 | Server(anyjev) |
| `SEARCH_DECISION_` | 소비 지점 임계값 | Server |

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 로깅 | `LoggerInterface`, `warning(..., exception=e)`, state 원문 금지 |
| 에러 | 포트는 `JudgmentError` 계열만 던짐, 흡수는 소비 지점 어댑터 1곳 |
| config | 키마다 docstring에 소비 지점 파일·함수 명기 |
| 코드 주석 | 파일 상단 `# Design Ref: §N — 요지`, 핵심 분기에 `# Plan SC: …` |
| 함수 길이 | 40줄 이하, if 중첩 2단계 이하 — 매핑 함수는 순수 함수로 분리 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/domain/judgment/
├── __init__.py
├── interfaces.py          JudgmentPort
├── value_objects.py       Question/Answer/Request/Response VO, JudgmentBackendKind
└── exceptions.py          JudgmentError 계층
src/infrastructure/judgment/
├── __init__.py
├── factory.py             build_judgment_backend
├── jev/
│   ├── __init__.py
│   ├── adapter.py         JevJudgmentAdapter
│   └── mapping.py         to_sdk_questions / from_sdk_response / map_exception
└── anyjev/
    ├── __init__.py
    ├── adapter.py         AnyJevJudgmentAdapter
    └── mapping.py         serialize_state / to_items / from_decisions
src/infrastructure/search_decision/
├── judgment_adapter.py    JudgmentSearchDecisionAdapter
└── questions.py           QID, SEARCH_DECISION_NOUL
src/api/main.py            get_judgment_backend, 조립 분기, lifespan aclose
src/config.py              8키
pyproject.toml             [project.optional-dependencies] judgment
.env.example               8키 블록
tests/domain/judgment/test_value_objects.py
tests/infrastructure/judgment/test_jev_adapter.py
tests/infrastructure/judgment/test_anyjev_adapter.py
tests/infrastructure/judgment/test_factory.py
tests/infrastructure/judgment/test_module_boundaries.py
tests/infrastructure/judgment/test_real_backend_smoke.py   (-m llm)
tests/infrastructure/search_decision/test_judgment_adapter.py
tests/api/test_judgment_di.py
tests/fixtures/judgment/*.json
```

### 11.2 Implementation Order

1. [ ] domain VO·예외·포트 + 테스트(8.2 #1~6) + AST 경계 테스트(domain 부분)
2. [ ] `anyjev/mapping.py` → `anyjev/adapter.py` + 픽스처 + 테스트(8.2 #13~20) — SDK 없이 되는 쪽 먼저
3. [ ] pyproject extra 추가·`uv sync --extra judgment` → `jev/mapping.py` → `jev/adapter.py` + 테스트(8.2 #7~12)
4. [ ] `config.py` 8키 → `factory.py` + 테스트(8.3 #1~4) → `.env.example`
5. [ ] `questions.py` → `judgment_adapter.py` + 테스트(8.3 #8~11)
6. [ ] `main.py` `get_judgment_backend`·조립 분기·lifespan + 배선 테스트(8.3 #5~7) + `_DECLARED_CONSUMERS` 갱신(8.3 #12)
7. [ ] `-m llm` 스모크 파일 작성(skip 확인) → 전체 회귀 `FAILED` diff(8.3 #13)

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| Domain | `module-1` | VO·예외·포트 + 경계 테스트 (11.2 #1) | 10-15 |
| Adapters | `module-2` | AnyJev → Jev 어댑터·매핑·픽스처 (11.2 #2~3) | 25-35 |
| Factory+Config | `module-3` | config 8키·팩토리·extra·.env.example (11.2 #4) | 10-15 |
| Wiring | `module-4` | search_decision 어댑터·main.py·배선 테스트·회귀 (11.2 #5~7) | 20-30 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 35-50 |
| Session 3 | Do | `--scope module-3,module-4` | 30-45 |
| Session 4 | Check + Report | 전체 | 25-35 |

---

## 12. Plan 역추적 (FR → Design)

| Plan FR | Design 위치 |
|---------|-------------|
| FR-01 domain stdlib만 | D11, §9.2, 8.3 #12 |
| FR-02 다중 질문 | §3.1 `JudgmentRequest.questions`, D2, 8.2 #19 |
| FR-03 확률 검증·ProtocolError | §3.1 `__post_init__`, 8.2 #1~2·#16 |
| FR-04 명시 인자·http_client 주입 | §4.1, D7 |
| FR-05 응답 model | §4.1, 8.2 #8 |
| FR-06 AnyJev Noul/Choice | **D1 정정**(네이티브 noul), §4.2 |
| FR-07 probs 검증·extra 보존 | §4.2, D3, 8.2 #14·#16 |
| FR-08 타임아웃·예외 정규화 | D9·D10, §6.1 |
| FR-09 팩토리 None·1회 조립 | §4.4, 8.3 #1~5 |
| FR-10 임계값 | D13, §4.5, 8.3 #8 |
| FR-11 폴백 | §4.5, 8.3 #9~11 |
| FR-12 main.py 조립·시그니처 불변 | §4.4, 8.3 #6~7 |
| FR-13 질문은 소비 지점 소유 | D17, `questions.py` |
| FR-14 로그에 원문 금지 | §4.5, §7 |
| FR-15 .env.example | §4.3 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-15 | 초안 — Option C, AnyJev 소스 확인으로 D1 Plan 정정, SDK httpx2 의존 확인 | 배상규 |
