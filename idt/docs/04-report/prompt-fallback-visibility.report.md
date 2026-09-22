# 완료 리포트 — prompt-fallback-visibility (module-0)

> Feature: `prompt-fallback-visibility`
> Completed: 2026-09-21
> 범위: **module-0 (`root-cause-fix`) 완료** / module-1·2 미착수
> Match Rate: **97.5%** (module-0 범위)
> 문서: [Plan](../01-plan/features/prompt-fallback-visibility.plan.md) ·
> [Design](../02-design/features/prompt-fallback-visibility.design.md) ·
> [Analysis](../03-analysis/prompt-fallback-visibility.analysis.md)

---

## Executive Summary

| 관점 | 내용 |
|---|---|
| **Problem** | 에이전트 생성 프롬프트가 2주간 100% 빈 껍데기로 나갔다. 원인은 프롬프트 품질이 아니라 **관리자가 기본 LLM을 추론 모델로 바꾸자 보조 작업용 20초 타임아웃이 뚫린 것**이었고, 규칙기반 폴백이 그 실패를 가렸다. |
| **Solution** | 보조 LLM 모델을 명시해 관리자의 기본 모델 변경과 분리하고, 타임아웃을 실측 기준으로 재산정했다. 동시에 "어떤 모델로 어떤 예산에서 실패했는가"를 로그만으로 알 수 있게 했다. |
| **Function UX Effect** | 사용자 화면 변화 없음. **실패하던 기능이 동작하게 되었다** — 실호출 4/4 정상(평균 6.4초). |
| **Core Value** | 재발 시 DB 포렌식 없이 로그 두 줄로 원인이 드러난다. 같은 은폐가 3개월 지속된 선례(intent 모듈)가 코드 주석에 남아 있었고, 이번에 그 구조를 깼다. |

### Value Delivered (실측)

| 지표 | Before | After |
|---|---|---|
| 프롬프트 생성 성공률 (실호출) | **0/4** (2026-09 DB 관측 4/4 timeout) | **4/4** |
| 실호출 지연 | 20156ms → 폴백 | **5047~8671ms** (평균 6.4s) |
| 타임아웃 여유 | 20초 예산 / gpt-5.1 최소 21.06초 → **구조적 100% 실패** | 30초 예산 / 최대 8.67초 → **3.4배** |
| 모델 관측성 | 로그 0줄 (debug 레벨이라 미출력) | INFO 1줄 (`model_name`·`source`) |
| 실패 진단 정보 | `latency_ms` 만 | `model` + `timeout_sec` + `latency_ms` |

---

## 1. Key Decisions & Outcomes

| 단계 | 결정 | 따랐는가 | 결과 |
|---|---|:--:|---|
| Plan | 폴백 문구 **유지** + 저장 차단 (설계 결정 prompt-depth §5.1 A-6 존중) | ✅ | `_FALLBACK_*` 상수 무변경 |
| Plan | LangSmith 배선을 **선행 feature로 분리** | ✅ | `pipeline-langsmith-tracing` 별도 진행 |
| Design | **module-0 신설** — 근본 원인 수정을 차단 UI보다 앞에 | ✅ | module-0만으로 실사용 문제 해결 |
| Design | Option C (서버 DB 재조회) | ⏭ | module-1 소관, 미착수 |
| Design | FR-00a/b **값은 실측 후 확정** | ✅ | 추측 없이 6회 실측으로 결정 |
| Do | `tools` degraded는 차단하지 않음 (D5) | ✅ | 차단 기능 자체 미도입 |

### 진단이 세 번 교정된 기록

| 시점 | 진단 | 판정 |
|---|---|---|
| 받은 피드백 | "compose가 정보량 적은 요청을 generic 문구로 메웠다" | ❌ LLM 출력이 아예 없었다 |
| Plan §1-1 | "PROMPT 단계 LLM 호출이 실패했다 (원인 미상)" | △ 절반 |
| **Design §1-1** | **"기본 LLM이 gpt-5.1로 바뀌어 20초 예산을 넘겼다"** | ✅ |

피드백이 지목한 `AgentPlanner`는 **다른 경로(`/compose`, Fix 패널)** 소속이라
위저드(`/agents/pipeline/stream`)와 무관했다. 코드 대조로 바로잡았다.

---

## 2. Success Criteria 최종 상태

### module-0 (이번 범위)

| ID | 기준 | 결과 | 근거 |
|---|---|:--:|---|
| SC-00a | 보조 LLM 명시로 기본 모델 변경이 전파되지 않음 | ✅ | `.env:104`, `Settings().utility_llm_model_name = 'gpt-4o-mini'` |
| SC-00b | 타임아웃 실측 기준 재산정 | ✅ | `prompt_composer_config.py:34` `30.0` + 근거 주석 `:23-33` |
| SC-00c | 모델·예산이 로그만으로 드러남 | ✅ | `utility_llm_provider.py:223` INFO, `adapter.py:309-310` |
| SC-06 | 실패 원인 특정 + 재발 방지 테스트 | ✅ | 원인 = gpt-5.1 × 20초. 테스트 12건 |

**4/4 충족.**

### module-1/2 (미착수)

| ID | 기준 | 결과 |
|---|---|:--:|
| SC-01·04·05 | 차단형 UI / 재시도 / reason 한국어 | ❌ module-2 |
| SC-02·03 | 서버 저장 차단 / 편집 시 허용 | ❌ module-1 |
| SC-07 | `tools` degraded 미차단 | ⚠️ 자명 충족, 테스트 미고정 |

---

## 3. 구현 내역

### 프로덕션 (4파일)

| 파일 | 변경 |
|---|---|
| `.env` | `UTILITY_LLM_MODEL_NAME=gpt-4o-mini` (FR-00a) — gitignore 대상 |
| `.env.example` | 위 키 + `PROMPT_COMPOSER_TIMEOUT_SEC` + 사고 경위 주석 (G2) |
| `src/infrastructure/config/prompt_composer_config.py` | `TIMEOUT_SEC 20.0 → 30.0` + 실측 근거 주석 (FR-00b) |
| `src/application/llm_model/utility_llm_provider.py` | `_log_resolved` **debug → info** + `source` 필드, `_log_instance_hit` 분리 (FR-00c, G5) |
| `src/infrastructure/prompt_composer/adapter.py` | `_degrade` 로그에 `model`·`timeout_sec`, `_active_model_name()` 신설, provider 폴백 warning (FR-00d) |
| `src/config.py` | `env_file_encoding="utf-8-sig"` (G6, 방어적) |

### 테스트 (신규 2파일 12건 + 기존 1건 갱신)

| 파일 | 건수 |
|---|---|
| `tests/application/llm_model/test_utility_llm_default_observability.py` | 4 |
| `tests/infrastructure/prompt_composer/test_degrade_observability.py` | 8 (G1 반영 3건 포함) |
| `tests/application/llm_model/test_utility_llm_provider.py` | P14 레벨 계약 갱신 |

**전체 스위트: 53 failed / 9347 passed / 0 errors — 기존 실패 53건과 동일, 회귀 0건.**

---

## 4. 배운 것 (다음 사이클을 위한 기록)

### L1 — 증거는 DB에 이미 있었다

Plan은 FR-07(원인 규명)을 Do 항목으로 미뤘으나, `prompt_version` 테이블에
`degraded`/`reason`/`elapsed_ms` 가 **이미 영속되고 있었다**. Design 단계에서
한 번의 쿼리로 `reason='timeout' × 4`, `elapsed_ms` 20000~20030 을 얻어
원인을 확정했다. **관측 데이터의 존재 여부를 먼저 확인하면 규명 단계가 통째로 사라진다.**

### L2 — 로그 레벨이 곧 관측성이다

`_log_resolved` 는 **처음부터 있었다.** 다만 `debug` 였고 운영 기본 설정이
INFO라 한 줄도 출력되지 않았다. 코드가 존재한다고 관측되는 것이 아니다.
"이 로그가 실제로 보이는가"를 레벨까지 포함해 확인해야 한다.

### L3 — 설정 미반영은 코드 성공과 무관하다

인프로세스 검증(T-15)은 3/3 성공했으나 **실행 중인 서버는 여전히 실패**했다.
`uvicorn --reload` 가 09-18 이후 한 번도 동작하지 않았고 `.env` 는 애초에 watch
대상이 아니다. **"코드가 맞다"와 "환경이 고쳐졌다"는 별개의 검증이다.**
Check 단계에서 실서버를 직접 호출한 것이 이를 잡았다.

### L4 — 루트 conftest의 함수 스코프 autouse는 위험하다

테스트 위생을 위해 넣은 `tests/conftest.py` 가 DB 테스트 91건에
`RuntimeError: Event loop is closed` 를 유발했다. 함수 스코프 autouse 가 모든
테스트의 픽스처 그래프에 끼어들어 DB 엔진과 이벤트 루프 생명주기를 어긋나게 했다.
`scope="session"` 으로 해결. **전역 픽스처는 필요한 최소 스코프로.**

### L5 — `pytest-randomly` 는 회귀 측정을 가린다

Check 초기 측정(53 failed)에서 L4의 91 errors 가 안 잡힌 이유는 순서가
무작위였고 에러가 순서 의존적이었기 때문이다. **회귀 비교는 `-p no:randomly`
로 순서를 고정해야 한다.**

### L6 — 병목은 이동한다

`prompt` 여유를 3.4배로 넓히자 **병목이 `intent`(10초 예산)로 옮겨갔다.**
재시작 직후 콜드 스타트에서 10.56초로 예산을 넘겼다. 한 단계의 예산만 고치면
다음으로 빠듯한 단계가 드러난다.

---

## 5. 잔여 위험 / 후속 항목

| ID | 항목 | 심각도 | 비고 |
|---|---|:--:|---|
| **N1** | **`intent` 단계가 이제 가장 빠듯하다** — 예산 10초, 콜드 스타트 10.56초 관측. degraded 시 `decide_after_intent` 가 무조건 proceed 하여 **되묻기가 통째로 생략**된다(`policies.py:57`). 사용자가 원래 문제 삼았던 "안 물어봤다"가 정확히 이 경로 | **높음** | 1회 관측, 재현 필요 |
| N2 | `uvicorn --reload` 미동작. reloader는 venv python, 워커는 시스템 python 불일치 | 중 | 개발 생산성 |
| R1 | degraded 프롬프트가 여전히 저장된다 — 서버 게이트 없음 | 중 | module-1 |
| R2 | 사용자가 실패를 인지 못한다 — 배너뿐 | 중 | module-2 |
| R3 | `schema`/`empty`/`error` 3개 사유는 타임아웃과 무관. 발생 시 조용히 저장됨 | 중 | module-1/2 |
| R4 | 보조 모델이 비활성화되면 `_resolve_model:118` 이 기본 모델로 되돌아간다 | 낮음 | 30초 예산이 gpt-5.1(22.5s) 흡수 |
| G3 | SC-07 테스트 미고정 | 낮음 | module-1 T-10 |
| G4 | `_resolve_by_name` negative 캐싱 없음 | 낮음 | 현재 미발현(row 활성 확인) |

### 별도 feature 후보

- **`TraceExtractor` 미작동** — `ai_run` 152건 중 `langsmith_trace_id` **0건**.
  `extract()` 가 그래프 실행 **후** 호출되어 run tree contextvar 가 이미 해제된다.
  상세: `pipeline-langsmith-tracing` Design §12-2

---

## 6. 다음 단계

```
/pdca do prompt-fallback-visibility --scope server-gate     # module-1
/pdca do prompt-fallback-visibility --scope frontend-block  # module-2
/pdca analyze pipeline-langsmith-tracing                    # 미실행
```

**우선순위 제안**: N1(`intent` 예산)이 module-1/2보다 급하다. 실사용자가 체감하는
증상("되물어야 하는데 안 물었다")에 직결되고, module-0과 동일한 성격의 1줄 수정이다.

---

## Version History

| 버전 | 일자 | 내용 |
|---|---|---|
| 1.0 | 2026-09-21 | module-0 완료. Match Rate 97.5%. G0 실환경 검증 완료. |
