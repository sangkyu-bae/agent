# admin-default-llm-routing Completion Report

> **Project**: idt (sangplusbot 백엔드)
> **Version**: 1.0.0
> **Author**: 배상규
> **Date**: 2026-08-31
> **Status**: **코드 완료 · 실환경 미검증**
> **Match Rate**: 100% (정적) · Critical 0 · Important 0

---

## 1. Summary

### 1.1 Project Overview

NPU 위에 Gemma를 띄우고 붙어서 실측하려면, LLM 호출이 한 군데로 모여야 한다.
그런데 **의도 판정·웹검색 판단·환각 검사·프롬프트 합성·메모리 추출·위키 정제
어댑터 9곳이 `LLMFactory`를 우회해 생성자에서 `ChatOpenAI`를 직접 만들고 있었다.**
관리자가 기본 모델을 NPU로 바꿔도 이 경로는 `api.openai.com`으로 나가므로,
"NPU에 붙었다"고 해도 **절반만 붙은 상태**로 지연·비용·품질을 측정하게 된다.

게다가 `_default_llm_model`은 부팅 시 1회만 로드돼 모델 교체마다 **서버 재시작**이
필요했다.

이 사이클은 두 문제를 함께 해결했다 — 아래단에 **범용 캐시 포트**를 뚫고 그 위에
런타임 LLM 공급자를 올려, 관리자 설정이 **재시작 없이** 9경로 전부에 반영되게 했다.

### 1.2 Results Summary

| 항목 | 결과 |
|------|------|
| PDCA 사이클 | Plan → Design → Do(module 1~5) → Check → Report |
| Match Rate | **100%** (정적) — Structural/Functional/Contract 각 100% |
| Gap | Critical **0** · Important **0** · Minor 1 (사용자 조치) |
| 신규 테스트 | **62개** (전부 통과) |
| 전체 회귀 | 58 failed(기준선 동일, 신규 회귀 **0**) / 8,363 passed |
| 코드 변경 | 신규 4파일 462줄 · 수정 16파일 (+665 / -97) |
| 테스트 코드 | 신규 5파일 1,447줄 |
| DB 마이그레이션 | **없음** |
| API 계약 변경 | **없음** (프론트 동기화 불필요) |

---

## 2. Related Documents

| 문서 | 경로 | 버전 |
|------|------|------|
| Plan | `docs/01-plan/features/admin-default-llm-routing.plan.md` | v0.2.0 |
| Design | `docs/02-design/features/admin-default-llm-routing.design.md` | v0.2.0 |
| Analysis | `docs/03-analysis/admin-default-llm-routing.analysis.md` | v0.3.0 |
| PRD | — | 미작성 (선택 단계) |

---

## 3. Executive Summary

### 3.1 Value Delivered

| Perspective | 계획 | 실제 결과 |
|-------------|------|-----------|
| **Problem** | 어댑터 9곳이 팩토리를 우회 + 교체마다 재시작 | 9곳 전부 배선 완료(`main.py` 11회 주입), 재시작 요구 제거 |
| **Solution** | 범용 `CachePort` + 런타임 LLM 공급자 | L1(값)/L2(인스턴스) 2계층으로 구현. Redis 교체 시 소비자 무수정 보장 |
| **Function/UX Effect** | 관리자가 모델 바꾸면 다음 요청부터 반영 | 통합 테스트로 증명 (`test_default_model_swap_reflects_without_restart`) |
| **Core Value** | NPU 검증의 전제 조건 확보 | **코드 레벨 완료.** 단 NPU 실측은 환경 부재로 미완 (§8) |

### 3.2 부수 성과

- **재사용 자산**: `CachePort`는 LLM 외 도메인도 쓸 수 있다. 같은 dict 캐시 패턴이
  이미 3곳(`CostCalculator`·`ModelNameResolver`·`InMemoryChatStreamCache`)에
  중복 구현돼 있었고, 향후 이들을 흡수할 토대가 생겼다.
- **숨은 결함 발견**: 관리자가 `is_default`를 바꾸는 경로에 캐시 무효화 훅이
  **비어 있었다**(Plan D-8). `invalidate` 호출은 가격 변경 1곳뿐이었다.

---

## 4. What Was Built

### 4.1 Functional Requirements (11/11 충족)

| ID | 요구사항 | 증거 |
|----|----------|------|
| FR-1 | `CachePort` async get/set(ttl)/delete/clear | C1~C6 |
| FR-2 | TTL 만료를 clock 주입으로 테스트 | C2/C3/C8 |
| FR-3 | `is_default` 모델이 9곳의 LLM이 됨 | P1 + 통합 I2 |
| FR-4 | 보조 모델 설정/미설정 분기 | P1, P2 |
| FR-5 | **재시작 없이 반영** | 통합 I1 |
| FR-6 | UseCase 4곳 무효화 의무 호출 | U1~U4 |
| FR-7 | 보조 모델 미해석 시 warning + 기본 폴백 | P3, P4 |
| FR-8 | 기본 모델 해석 실패에도 서비스 유지 | P5, P11 |
| FR-9 | provider 미주입 시 기존 동작 유지 | A1, U6×4 |
| FR-10 | temperature가 캐시 키·팩토리에 전달 | P6, P7 |
| FR-11 | 캐시 미스에도 요청 성공 | P13 |

### 4.2 Non-Functional Requirements (5/5 충족)

| ID | 요구사항 | 결과 |
|----|----------|------|
| NFR-1 | 캐시 히트 시 DB 조회 0회 | P8, 통합 I3 (3회 호출 → LLM 생성 1회) |
| NFR-2 | Redis 어댑터 추가 시 소비자 무수정 | `json.dumps(cached)` 강제 테스트로 계약 고정 |
| NFR-3 | 아키텍처 불변 | domain은 `abc`/`typing`만, provider는 domain 인터페이스만 |
| NFR-4 | 기존 테스트 전량 통과 | 신규 회귀 0건 |
| NFR-5 | 로깅 규칙 준수 | 변경분 `print()` 0, `exception=` 전부 포함 |

### 4.3 Deliverables

**신규 (462줄)**

| 파일 | 줄 | 역할 |
|------|---:|------|
| `src/domain/cache/interfaces.py` | 58 | `CachePort` — 범용 KV 캐시 포트 |
| `src/infrastructure/cache/in_memory_cache.py` | 78 | TTL·상한·clock 주입 인메모리 어댑터 |
| `src/application/llm_model/utility_llm_provider.py` | 284 | L1+L2 2계층 공급자 + 직렬화 경계 |
| `src/application/llm_model/cache_invalidation.py` | 42 | UseCase 4곳 공용 무효화 헬퍼 |

**수정 (16파일 · +665 / -97)**

| 그룹 | 파일 | 변경 |
|------|------|------|
| 포트 | `domain/llm/interfaces.py` | `+UtilityLLMProviderPort` |
| UseCase | `create`/`update`/`deactivate`/`update_pricing` | `llm_provider` 주입 + 무효화 의무 호출 |
| 패턴 A | `hallucination`·`search_decision`·`qa_generator` | `_resolve_chain()` + 지연 생성 |
| 패턴 B | `intent`·`prompt_composer` | 위 + `chain` 명시 주입 우선 |
| 패턴 C | `memory/extractor`·wiki distiller 3종 | `_resolve_llm()` |
| DI | `api/main.py` | provider lazy 싱글톤 + 9곳 배선 |
| 설정 | `config.py` | 설정 3개 |

**테스트 (5파일 1,447줄 · 62개)**

| 파일 | 개수 | 범위 |
|------|---:|------|
| `test_in_memory_cache.py` | 16 | C1~C9 + 포트 계약 |
| `test_utility_llm_provider.py` | 19 | P1~P14 |
| `test_use_case_cache_invalidation.py` | 11 | U1~U6 |
| `test_adapter_llm_provider.py` | 12 | A1~A7 |
| `test_llm_routing_chain.py` | 4 | 체인 통합 I1~I4 |

---

## 5. Key Decisions & Outcomes

| DR | 결정 | 따랐는가 | 결과 |
|----|------|:--------:|------|
| **DR-1** | 캐시를 L1(값)/L2(인스턴스) 2계층 분리 | ✅ | **이 사이클 최대 판단.** LangChain 객체는 직렬화 불가라, 단일 캐시로 만들었으면 Redis 전환 시 전면 재작업이었다 |
| **DR-2** | 직렬화 변환을 provider 경계에서 | ✅ | `json.dumps` 강제 테스트가 계약을 지킨다 — 어기면 Redis 전환 시점이 아니라 **지금** 실패한다 |
| **DR-3** | `updated_at`을 L2 키에 포함 | ✅ | **L2 무효화 코드가 아예 불필요해졌다.** L1 갱신이 새 `updated_at`을 실어오면 L2 키가 자연히 달라진다 |
| **DR-4** | 리졸버+provider 한 클래스 통합 | ✅ | DR-3의 L1→L2 키 연결이 한 곳에 모여 응집도 유지 |
| **DR-7** | provider는 예외를 던지지 않음 | ✅ | P11~P13 — DB·팩토리·캐시 세 실패 경로 모두 요청을 살린다 |
| **DR-8/9** | additive 파라미터 + `chain` 최우선 | ✅ | 기존 `ChatOpenAI` patch 테스트가 그대로 산다 |
| **DR-10** | `session_factory` + 단기 세션 | ✅ | lifespan singleton의 세션 보유 금지 회피 |
| **DR-12** ★ | 레거시 chain 지연 생성 | ✅ | **설계에 없던 필수 조건.** 실측으로 뒤늦게 발견 (§6) |
| **AD-6** ★ | 저장소를 `repo_builder`로 주입 | ✅ | 설계 의사코드의 레이어 위반을 구현 단계에서 교정 |

---

## 6. 구현 중 발견한 것 (Design 문서에 없던 사실)

### 6.1 `ChatOpenAI`는 키 없이 생성조차 안 된다 — DR-12의 근거

```python
>>> os.environ.pop("OPENAI_API_KEY")
>>> ChatOpenAI(model="gpt-4o-mini", temperature=0)
OpenAIError: Missing credentials. Please pass an `api_key`, ...
```

생성자가 자격증명을 검증한다. 어댑터가 `__init__`에서 즉시 만드는 기존 구조로는
**`OPENAI_API_KEY`가 없는 순수 NPU 배포에서 서버가 부팅조차 못 한다.**

이 기능의 SUCCESS 기준("OpenAI 호출 0건")은 곧 "OpenAI 키 없이 뜬다"는 뜻이므로,
레거시 chain의 지연 생성은 선택이 아니라 **전제 조건**이었다. 설계에 없던 항목을
구현이 메운 경우로, 테스트 6건(A7)이 이를 강제한다.

### 6.2 설계 §11.2의 "패턴 C 어댑터 무수정"은 성립하지 않았다

해당 문장은 **구 AD-1(부팅 시 주입)** 전제로 쓰였다. Plan v0.2.0이 런타임 해석으로
바뀌며 `provider.get()`이 async가 되었고, 동기 싱글톤 getter 안에서는 await할 수
없다. 결과적으로 어댑터는 5곳이 아니라 **9곳**을 수정했다.

### 6.3 무효화 훅이 비어 있었다 (Plan D-8이 코드로 확인됨)

`invalidate` 호출은 `update_llm_model_pricing_use_case.py:57` **단 1곳**뿐이었다.
관리자가 `is_default`를 바꾸는 바로 그 경로(`update_llm_model_use_case.py`)에는
없었다. 통합 테스트 I4가 이 상태를 재현해 **무효화가 FR-5의 필수 조건임을 증명**하고,
동시에 회귀를 막는다.

---

## 7. Gap Analysis Summary

| Gap | 심각도 | 상태 | 조치 |
|-----|--------|:----:|------|
| G-1 포트 계약 테스트 위치 | Minor | ✅ | Design v0.2.0 §11.1 반영 |
| G-2 `cache_invalidation.py` 미기재 | Minor | ✅ | Design v0.2.0 반영 |
| G-3 패턴 C 어댑터 수정 | **Important** | ✅ | Design v0.2.0 §11.2 정정 주석 |
| G-4 A7 지연 생성 누락 | **Important** | ✅ | Design v0.2.0 DR-12 + §13.0 |
| G-5 `.env.example` 미반영 | Minor | ⚠️ | **사용자 직접 조치 필요** (§9) |
| G-6 §2.2 의사코드 레이어 위반 | Minor | ✅ | Design v0.2.0 AD-6 |
| G-7 함수 길이 초과 | **Important** | ✅ | 헬퍼 추출 — `execute` 57→35 / 55→38 |
| G-8 테스트 파일명 불일치 | Trivial | ✅ | Design v0.2.0 반영 |

**Important 3건 중 2건(G-3·G-4)은 구현이 설계보다 앞서 나간 경우로 코드가 옳았고,
문서 갱신으로 해소했다.** 실제 코드 조치는 G-7 하나였다.

---

## 8. ⚠️ 미검증 항목 — 이 기능은 아직 실환경에서 확인되지 않았다

Match Rate 100%는 **"설계대로 코드가 존재한다"**는 뜻이지 **"NPU에서 동작한다"**가
아니다. 아래는 코드로 증명할 수 없는 항목이다.

| ID | 항목 | 차단 요인 | 위험도 |
|----|------|-----------|:------:|
| **V-1** | **vLLM tool-calling 검증 (Step 0)** | NPU/Gemma 미배포 | **높음** |
| V-2 | 실 MySQL + 실 NPU 무재시작 교체 | MySQL REFUSED, API 미기동 | 중간 |
| V-3 | 패턴 C `from_openai()`의 즉시 `ChatOpenAI` 생성 | 키 없는 환경에서만 발현 | 낮음 |

### V-1이 이 기능의 실질적 관문이다

배선된 패턴 A/B 어댑터 5곳이 **전부** `with_structured_output`을 쓴다
(코드베이스 전체로는 28곳). Gemma + vLLM 파서 조합에서 구조화 출력이 안 되면
**배선이 100% 완벽해도 런타임에 전부 실패한다.**

착수 전 검증 절차:

```bash
curl http://<NPU_HOST>:8000/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model":"gemma-3-27b",
  "messages":[{"role":"user","content":"서울 날씨 알려줘"}],
  "tools":[{"type":"function","function":{"name":"get_weather",
    "parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],
  "tool_choice":"auto"
}'
```

실패 시 후속 판단: `with_structured_output(Schema, method="json_schema")` 폴백
검토 → 설계 재검토가 필요할 수 있다.

### V-3 상세

패턴 C 4곳(`memory/extractor`, wiki distiller 3종)은 `from_openai()`가
`ChatOpenAI`를 즉시 만든다(폴백용). lazy 싱글톤이라 **부팅은 막지 않지만**,
`OPENAI_API_KEY`가 아예 없는 NPU 전용 환경에서 메모리 추출·위키 정제 **첫 호출 시
실패**한다. 패턴 A/B와 달리 지연 생성을 넣지 않은 이유는 `from_openai`가
`api_key`를 명시 인자로 받는 기존 계약이기 때문이다.

---

## 9. Next Steps

| 우선 | 항목 | 담당 |
|:----:|------|------|
| **1** | **Step 0 — vLLM tool-calling 검증** (V-1) | 인프라 준비 후 |
| 2 | `.env.example`에 설정 3개 추가 (G-5, bkit 훅 차단) | 사용자 직접 |
| 3 | self-host 모델 등록 → 무재시작 교체 실측 (V-2) | MySQL·NPU 기동 후 |
| 4 | V-3 판단 — 패턴 C도 지연 생성으로 갈지 | V-1 결과 확인 후 |
| 5 | 기존 중복 캐시 3건 흡수 (Plan Out of Scope) | 별도 사이클 |
| 6 | Redis 어댑터 추가 (다중 서버 전환 시) | 별도 사이클 |

### 9.1 `.env.example` 추가 블록 (G-5)

`QWEN_API_KEY=EMPTY` 다음 줄에 넣으면 된다. 세 값 모두 `config.py`에 기본값이
있어 `.env` 없이도 동작한다.

```bash
# 보조 LLM 라우팅 (admin-default-llm-routing)
# 비워두면 관리자가 지정한 기본 모델(is_default=True)을 그대로 따라간다.
# ⚠️ NPU/self-host 전면 테스트 시에는 반드시 비워둘 것 — 그래야 모든 보조
#    호출이 기본 모델로 흘러 외부 OpenAI 호출이 0이 된다.
UTILITY_LLM_MODEL_NAME=
# 모델 해석 결과(L1) 캐시 TTL(초). 다중 워커 전환 시 무효화 미전파 구간의 안전장치.
LLM_MODEL_CACHE_TTL_SECONDS=60
# LLM 인스턴스(L2) 캐시 상한. (model_id, updated_at, temperature) 키 기준.
LLM_INSTANCE_CACHE_MAX_ENTRIES=32
```

### 9.2 NPU 전환 실행 절차 (환경 준비 후)

```bash
# 1. 모델 등록 (provider 는 반드시 "openai" — llm_factory 가 base_url 로 분기)
curl -X POST http://localhost:8000/api/v1/llm-models -H 'Content-Type: application/json' -d '{
  "provider": "openai",
  "model_name": "gemma-3-27b",
  "display_name": "Gemma 3 27B (NPU)",
  "base_url": "http://<NPU_HOST>:8000/v1",
  "api_key_env": "NPU_API_KEY",
  "is_default": true,
  "input_price_per_1k_usd": "0",
  "output_price_per_1k_usd": "0"
}'

# 2. 재시작 불필요 — 다음 요청부터 반영된다
# 3. 확인: 해석 로그의 base_url 필드 (§6.2 P14 가 이를 위해 존재)
```

---

## 10. Lessons Learned

### 10.1 Keep — 잘 된 것

- **설계 전 코드 실측.** Plan 단계에서 "9곳 중 실제 배선된 건 몇 개인가"를
  `main.py`에서 직접 세었고, 덕분에 19개 파일이 아니라 9곳으로 범위가 좁혀졌다.
- **선례 탐색이 설계를 대체했다.** `CachePort`(SelectionCachePort), 무효화 책임
  위치(`update_llm_model_pricing_use_case`), `repo_builder`(MemoryExtractionService),
  clock 주입(CostCalculator) — 새로 만든 패턴이 거의 없다.
- **회귀 판정에 기준선을 썼다.** 전체 스위트에 기존 실패 58건이 있었는데, 파일별
  개수까지 대조해 "신규 회귀 0건"을 정확히 말할 수 있었다. 내 변경을 되돌려
  재실행하는 실증까지 거쳤다.
- **부정 테스트(I4)를 넣었다.** 무효화를 뺐을 때 낡은 모델이 남는 것을 재현해,
  D-8 구멍이 되살아나면 테스트가 잡는다.

### 10.2 Problem — 아쉬운 것

- **설계 문서가 Plan 개정을 따라가지 못했다.** Plan이 v0.2.0(런타임 해석)으로
  바뀌었는데 Design §11.2에는 구 AD-1(부팅 주입) 전제 문장이 남아, 구현 중에야
  G-3로 드러났다. Plan 개정 시 Design의 파생 항목을 함께 훑었어야 했다.
- **환경 없이 시작했다.** NPU·MySQL이 없는 상태로 5개 모듈을 다 만들었고, 결국
  SUCCESS 기준 2개를 미검증으로 남겼다. Step 0을 Plan §9에 1순위로 적어두고도
  실행하지 않은 채 진행한 것이 실책이다.
- **기존 규칙 위반을 키웠다.** G-7 — 이미 40줄을 넘던 함수에 코드를 더해 57·55줄로
  만들었다. 마지막에 정리했지만, 넣는 시점에 알아챘어야 했다.

### 10.3 Try — 다음에 시도할 것

- **Plan 개정 시 Design 영향 범위를 명시적으로 훑기.** "이 결정이 뒤집히면 Design의
  어느 절이 낡는가"를 개정 노트에 남긴다.
- **환경 의존 검증은 착수 조건으로 걸기.** Step 0 같은 항목은 "Next Steps 1순위"가
  아니라 **게이트**로 두고, 미충족이면 범위를 축소하거나 착수를 미룬다.
- **파일을 열 때 함수 길이를 먼저 재기.** 이미 위반 중인 파일에 코드를 더하기 전에
  추출부터 한다.

---

## 11. Process Improvement Suggestions

| 대상 | 제안 |
|------|------|
| PDCA | Plan 개정 시 "Design 파생 영향" 섹션을 강제하면 G-3 같은 이월 오류를 잡는다 |
| 검증 | `/verify-architecture`가 기존 위반과 신규 위반을 구분해 보여주면 판정이 빨라진다 (이번엔 수동으로 `git show HEAD:` 대조가 필요했다) |
| bkit | `.env.example` 훅 차단이 정당하나, 차단 시 "사용자가 직접 넣을 블록"을 남기도록 워크플로에 명시하면 누락을 막는다 |

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-08-31 | 배상규 | 최초 작성 — Match Rate 100%, FR 11/11, 신규 테스트 62개. 미검증 3건(V-1~V-3) 및 사용자 조치 1건(G-5) 명시 |
