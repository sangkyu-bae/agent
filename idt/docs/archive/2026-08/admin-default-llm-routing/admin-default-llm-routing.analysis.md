# admin-default-llm-routing Gap Analysis

> **Summary**: 설계-구현 대조. 구조 정합 100%, 기능 충족 100%(코드 검증 가능 범위), 계약 정합 100%.
>
> **v0.3.0**: Design v0.2.0 갱신 + G-7 리팩토링으로 **Important Gap 0건**. 잔여는 G-5(훅 차단)와 V-1~V-3(환경 의존)뿐.
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.3.0
> **Author**: 배상규
> **Date**: 2026-08-30
> **Plan**: `docs/01-plan/features/admin-default-llm-routing.plan.md` (v0.2.0)
> **Design**: `docs/02-design/features/admin-default-llm-routing.design.md` (v0.2.0 — 본 분석 반영 완료)
> **분석 방식**: 세션 내 직접 분석 (gap-detector 서브에이전트 미호출 — 명시 요청 없음)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | LLM 호출 9곳이 팩토리를 우회하고, 모델 교체마다 재시작이 필요하다 |
| **WHO** | P2 — NPU에서 에이전트를 운영하려는 KB 운영자 / 플랫폼 관리자 |
| **RISK** | LangChain 객체 직렬화 불가 → 계층을 잘못 나누면 Redis 전환 시 통째로 못 씀 |
| **SUCCESS** | 관리자가 기본 모델 변경 → 재시작 없이 9경로 전부 새 엔드포인트로 |
| **SCOPE** | 캐시 포트 + 인메모리 + provider + 배선 9곳. 기존 중복 3건 흡수·Redis 어댑터 제외 |

---

## 1. Match Rate

**런타임 미실행** (API 서버·MySQL·NPU 부재) → 정적 공식 적용:

```
Overall = (Structural × 0.2) + (Functional × 0.4) + (Contract × 0.4)
        = (100 × 0.2) + (100 × 0.4) + (100 × 0.4)
        = 20 + 40 + 40
        = 100%          ← Design v0.2.0 기준 (v0.1.0 기준 99%)
```

| 축 | 점수 | 근거 |
|----|-----:|------|
| **Structural** | 100% | Design v0.2.0 §11.1 명세 전부 존재, 누락 0 · 미기재 0 (실측 재확인) |
| **Functional** | 100% | FR-1~FR-11 전부 테스트 증거 보유 (62 tests) |
| **Contract** | 100% | 포트 2개 시그니처 설계와 일치, HTTP API 계약 변경 없음 |
| **Runtime** | N/A | 환경 부재 — §5에 미검증 항목으로 분리 |

> ⚠️ **Match Rate의 한계**: 이 점수는 "설계대로 코드가 존재하는가"를 잰 것이지
> "NPU에서 실제로 동작하는가"가 아니다. 후자는 §5의 미검증 2건에 달려 있으며,
> 그중 Step 0(vLLM tool-calling)은 실패 시 이 기능 전체를 무력화할 수 있다.

---

## 2. Strategic Alignment (Plan 대비)

| 질문 | 판정 | 근거 |
|------|------|------|
| Plan의 핵심 문제(팩토리 우회 9곳)를 해결했는가 | ✅ | 9곳 전부 `llm_provider` 배선 (`main.py` 11회 호출) |
| 재시작 요구를 제거했는가 (FR-5) | ✅ | `test_default_model_swap_reflects_without_restart` |
| 공용 재사용 자산을 만들었는가 (Plan §2.1-A) | ✅ | `CachePort` — LLM 외 도메인도 사용 가능 |
| Redis 전환 가능성을 유지했는가 (NFR-2) | ✅ | L1/L2 분리 + JSON 직렬화 계약 테스트 |
| 스코프 밖을 침범했는가 | ✅ 없음 | 기존 중복 3건·임베딩·ragas 무수정 확인 |

**전략적 오정렬 없음.**

---

## 3. Plan Success Criteria 대조

### 3.1 Definition of Done

| # | 기준 | 판정 | 증거 |
|---|------|:----:|------|
| 1 | `CachePort` + `InMemoryCache` TDD (TTL·삭제·clear) | ✅ | `test_in_memory_cache.py` 16 tests |
| 2 | `LlmModelResolver` 2단 폴백 + 캐시 히트/미스 | ✅ | `test_utility_llm_provider.py` 19 tests (P1~P14) |
| 3 | UseCase 4곳 무효화 의무 호출 + 테스트 | ✅ | `test_use_case_cache_invalidation.py` 11 tests (U1~U6) |
| 4 | 9개 배선 전환, 어댑터 5곳 파라미터 추가 | ⚠️ | 배선 9곳 ✅ / **어댑터는 5곳이 아니라 9곳 수정** (§4 G-3) |
| 5 | 기존 테스트 전량 통과 | ✅ | 58 failed(기준선 동일), 신규 회귀 0, passed 8317→8359 |
| 6 | **재시작 없이 기본 모델 교체 → 9경로 반영 실측** | ⚠️ | in-process 증명 ✅ / **실환경 미검증** (§5) |
| 7 | **self-host `base_url` 지정 시 OpenAI 호출 0건** | ⚠️ | `base_url` 전달 증명 ✅ / **실환경 미검증** (§5) |

**7개 중 4개 완전 충족, 3개 부분 충족.** ❌ 없음.

### 3.2 Functional Requirements

| ID | 요구사항 | 판정 | 증거 |
|----|----------|:----:|------|
| FR-1 | `CachePort` async get/set(ttl)/delete/clear | ✅ | `interfaces.py:38-66`, C1~C6 |
| FR-2 | TTL 만료를 clock 주입으로 테스트 | ✅ | `in_memory_cache.py:36`, C2/C3/C8 |
| FR-3 | `is_default` 모델이 9곳의 LLM이 됨 | ✅ | P1, 통합 `test_selfhost_base_url_reaches_llm_factory` |
| FR-4 | 보조 모델 설정/미설정 분기 | ✅ | P1, P2 |
| FR-5 | **재시작 없이 반영** | ✅ | `test_default_model_swap_reflects_without_restart` |
| FR-6 | UseCase 4곳 무효화 의무 호출 | ✅ | U1~U4 |
| FR-7 | 보조 모델 미해석 시 warning + 기본 폴백 | ✅ | P3, P4 |
| FR-8 | 기본 모델 해석 실패에도 서비스 유지 | ✅ | P5, P11 |
| FR-9 | provider 미주입 시 기존 동작 유지 | ✅ | A1, U6×4 |
| FR-10 | temperature가 캐시 키·팩토리에 전달 | ✅ | P6, P7 |
| FR-11 | 캐시 미스에도 요청 성공 | ✅ | P13 |

**11/11 충족.**

### 3.3 Non-Functional Requirements

| ID | 판정 | 증거 |
|----|:----:|------|
| NFR-1 | ✅ | P8 (L1 히트 시 DB 조회 1회), 통합 `test_no_redundant_db_query_between_swaps` |
| NFR-2 | ✅ | `test_l1_stores_json_serializable_value` — `json.dumps(cached)` 강제 |
| NFR-3 | ✅ | 신규 파일 임포트 검사: domain은 `abc`/`typing`만, provider는 domain 인터페이스만 |
| NFR-4 | ✅ | 전량 회귀, `ChatOpenAI` patch 테스트 유지 (A1 대조군 포함) |
| NFR-5 | ✅ | `verify-logging` — 내 변경분 `print()` 0, `exception=` 전부 포함 |

---

## 4. Gap List

### G-1 — `tests/domain/cache/test_interfaces.py` 미생성 · **Minor** · ✅ 해소

설계 §11.1이 명세한 파일이 없다. 대신 포트 계약 테스트를 `test_in_memory_cache.py`의 `TestCachePortContract`(2건: `isinstance` 검사 + ABC 인스턴스화 거부)로 통합했다.

**영향**: 없음. 검증 내용은 동일하고 위치만 다르다. 순수 ABC를 위한 별도 파일은 실익이 적다.
**조치**: ✅ Design v0.2.0 §11.1 에 실제 위치 반영 완료.

### G-2 — `cache_invalidation.py`가 설계 §11.1에 없음 · **Minor** · ✅ 해소

동일한 try/except가 UseCase 4곳에 반복되는 것을 피해 공용 헬퍼를 신설했다.

**영향**: 없음(품질 개선). application 레이어 내부, 임포트 규칙 준수.
**조치**: ✅ Design v0.2.0 §11.1·§2.1·§4.1 에 반영 완료.

### G-3 — 패턴 C 어댑터 4곳을 수정함 (설계는 "무수정") · **Important** · ✅ 해소

설계 §11.2 6단계는 "패턴 C 4곳 배선 교체 (어댑터 무수정)"인데, 실제로는 `memory/extractor.py` + wiki distiller 3종에 `_resolve_llm()`과 `llm_provider` 파라미터를 추가했다.

**원인**: 해당 문장은 **구 AD-1(부팅 시 주입)** 전제로 작성됐다. Plan v0.2.0이 런타임 해석으로 바뀌며 `provider.get()`이 async가 되어, 동기 싱글톤 getter에서 해석할 수 없다.
**영향**: 설계 의도(런타임 해석)와 코드는 일치. **문서만 낡았다.**
**조치**: ✅ Design v0.2.0 §11.1(패턴별 분류)·§11.2(정정 주석)·§4.2(패턴 C 시그니처)·DR-13 반영 완료.

### G-4 — A7(레거시 chain 지연 생성)이 설계에 없음 · **Important** · ✅ 해소

`ChatOpenAI(model=...)`은 키가 없으면 생성자에서 `OpenAIError: Missing credentials`로 실패한다(module-4 실측). 어댑터가 `__init__`에서 즉시 만드는 구조로는 **NPU 전용 배포가 부팅 불가**다. provider 주입 시에만 지연 생성하도록 구현했고 테스트 6건이 이를 강제한다.

**영향**: 설계 누락을 구현이 메운 경우. SUCCESS 기준의 전제 조건.
**조치**: ✅ Design v0.2.0 DR-12 + §13.0(실측 근거) 추가 완료.

### G-5 — `.env.example` 미반영 · **Minor**

bkit 훅이 해당 경로를 차단했다(`Scope limit: Path ".env.example" matches denied pattern`).

**영향**: 없음. 세 설정 모두 `config.py`에 기본값이 있어 `.env` 없이 동작한다.
**조치**: 사용자가 직접 추가 (블록은 module-1 보고에 제공됨).

### G-6 — 설계 §2.2 의사코드의 레이어 위반 · **Minor (문서)** · ✅ 해소

설계는 `repo = LlmModelRepository(session, logger)`로 쓰였으나, 이는 application → infrastructure 참조(CLAUDE.md §6 금지)다. 구현은 `repo_builder` 주입(`MemoryExtractionService` 선례)으로 처리했고 사용자 승인을 받았다.

**조치**: ✅ Design v0.2.0 §2.1·§2.2·§4.1 + AD-6 반영 완료.

### G-7 — 함수 길이 규칙 초과 (기존 악화) · **Important** · ✅ 해소

| 함수 | HEAD | 현재 | 한도 |
|---|---:|---:|---:|
| `create_llm_model_use_case.execute` | 50 | 57 | 40 |
| `update_llm_model_use_case.execute` | 48 | 55 | 40 |

**둘 다 변경 전부터 초과 상태**였고(git 확인), 무효화 호출 +3줄과 주석 +2~4줄이 더해졌다.
**영향**: CLAUDE.md §3 위반. 기능 영향 없음.

**조치**: ✅ 헬퍼 추출로 해소 (동작 변경 없음, 테스트 59개 그린 유지).

| 파일 | 추출한 헬퍼 | `execute` |
|------|-------------|----------:|
| `create_llm_model_use_case.py` | `_reject_duplicate()` (중복 등록 거부) · `_build_model()` (요청→엔티티) | 57 → **35** |
| `update_llm_model_use_case.py` | `_apply_field_updates()` (PATCH 부분 갱신) · `_apply_default_flag()` (is_default 토글) | 55 → **38** |

`llm_model` UseCase 4개 전 함수가 한도 40 이하로 들어왔다 (최대 40 — pricing `execute`).

### G-8 — 테스트 파일명 불일치 · **Trivial** · ✅ 해소

설계는 `test_*_use_case_invalidation.py`(UseCase별 복수), 실제는 `test_use_case_cache_invalidation.py`(단일 파일에 U1~U6 통합).

**조치**: ✅ Design v0.2.0 §11.1 에 실제 파일명 반영 완료.

---

## 5. 미검증 항목 (환경 부재)

| # | 항목 | 차단 요인 | 위험도 |
|---|------|-----------|:------:|
| **V-1** | **vLLM tool-calling 검증 (Step 0)** | NPU/Gemma 미배포 | **높음** |
| **V-2** | 실환경 무재시작 교체 (실 MySQL + 실 NPU) | MySQL REFUSED, API 미기동 | 중간 |

**V-1이 왜 높은가**: 배선된 어댑터 5곳(패턴 A/B)이 전부 `with_structured_output`을 쓴다. Gemma + vLLM 파서 조합에서 구조화 출력이 안 되면 **배선이 완벽해도 런타임에 전부 실패**한다. 이건 코드로 검증할 수 없고 설계 재검토(예: `method="json_schema"` 폴백)로 이어질 수 있다.

**V-3 — 부수 갭**: 패턴 C 4곳은 `from_openai()`가 `ChatOpenAI`를 즉시 생성한다(폴백용). lazy 싱글톤이라 부팅은 막지 않지만, `OPENAI_API_KEY`가 아예 없는 NPU 전용 환경에서 메모리 추출·위키 정제 **첫 호출 시 실패**한다. 패턴 A/B와 달리 지연 생성을 넣지 않은 이유는 `from_openai`가 `api_key`를 명시 인자로 받는 기존 계약이기 때문이다.

---

## 6. Decision Record 준수 검증

| DR | 결정 | 준수 | 증거 |
|----|------|:----:|------|
| DR-1 | L1(값)/L2(인스턴스) 2계층 | ✅ | `utility_llm_provider.py` — L1은 `CachePort`, L2는 `self._instances` |
| DR-2 | 직렬화 변환을 provider 경계에서 | ✅ | `_to_cache_dict`/`_from_cache_dict` + JSON 강제 테스트 |
| DR-3 | `updated_at`을 L2 키에 포함 | ✅ | `_get_instance()` key 튜플, P10 |
| DR-4 | 리졸버+provider 한 클래스 | ✅ | 단일 `UtilityLLMProvider` |
| DR-5 | 무효화는 두 키 전체 삭제 | ✅ | `invalidate()` — default + name |
| DR-6 | `invalidate()`를 포트에 노출 | ✅ | `UtilityLLMProviderPort.invalidate` |
| DR-7 | provider는 예외를 던지지 않음 | ✅ | P11, P12, P13 |
| DR-8 | 어댑터 파라미터 additive | ✅ | A1, U6×4 |
| DR-9 | `chain` > `llm_provider` > `ChatOpenAI` | ✅ | A6 (`provider.get_calls == 0`) |
| DR-10 | `session_factory` + 단기 세션 | ✅ | provider가 `AsyncSession` 미보유 |
| DR-11 | TTL 60초 기본 | ✅ | `config.py` `llm_model_cache_ttl_seconds` |

**11/11 준수. 이탈 없음.**

---

## 7. 결론

| 항목 | 값 |
|------|-----|
| Overall Match Rate | **100%** (정적, Design v0.2.0 기준) |
| Critical Gap | **0건** |
| Important Gap | **0건** — G-3·G-4 문서 해소, G-7 코드 해소 |
| Minor/Trivial | **1건** (G-5, 훅 차단) — G-1·G-2·G-6·G-8 해소 |
| 미검증 (환경) | 2건 + 부수 1건 |

**Important 3건 전부 해소됐다.** G-3·G-4 는 Design v0.2.0 갱신으로(구현이 설계보다 앞서 나간 경우, 코드는 옳았다), G-7 은 헬퍼 추출로 처리했다. **코드 조치가 필요한 Gap 은 남아 있지 않다.**

잔여는 G-5(bkit 훅 차단으로 사용자 직접 조치)와 V-1~V-3(환경 의존)뿐이다.

**90% 기준을 넘겼으므로 `/pdca iterate` 없이 진행 가능하다.** 다만 V-1(vLLM tool-calling)이 미해결인 채로 Report·Archive까지 가면, 나중에 NPU에서 실패했을 때 "완료된 기능"이 동작하지 않는 상태가 된다.

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-08-30 | 배상규 | 최초 작성 — 정적 Match Rate 99%, Gap 8건, 미검증 2건 |
| 0.2.0 | 2026-08-30 | 배상규 | Design v0.2.0 동기화 후 재대조 — G-1·G-2·G-3·G-4·G-6·G-8 해소, Structural 94→100%, Overall 99→100%. 잔여: G-7(코드), G-5(훅 차단), V-1~V-3(환경) |
| 0.3.0 | 2026-08-30 | 배상규 | **G-7 코드 해소** — `create`/`update` UseCase `execute` 를 헬퍼 추출로 57→35 / 55→38 줄. Important Gap 0건. 잔여: G-5(사용자 직접), V-1~V-3(환경) |
