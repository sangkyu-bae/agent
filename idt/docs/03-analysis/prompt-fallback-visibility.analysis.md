# Gap Analysis — prompt-fallback-visibility

> Feature: `prompt-fallback-visibility`
> Analyzed: 2026-09-21
> Phase: check
> 분석 범위: **module-0 (`root-cause-fix`) 한정** — module-1/2는 의도적 미착수
> Plan: `docs/01-plan/features/prompt-fallback-visibility.plan.md`
> Design: `docs/02-design/features/prompt-fallback-visibility.design.md`

---

## Context Anchor

| 축 | 내용 |
|---|---|
| **WHY** | 사용자가 받은 프롬프트는 폴백 상수와 바이트 단위로 일치 — LLM 생성 결과가 아니라 실패의 산물이었다. |
| **WHO** | P2(KB 운영자/에이전트 소유자). |
| **RISK** | 저장 차단이 과하면 "일단 만들고 고치기" 흐름을 막는다. |
| **SUCCESS** | degraded 프롬프트가 저장으로 흘러가지 않고, 사용자가 사유를 읽고 재시도할 수 있다. |
| **SCOPE** | 근본 원인 수정(module-0) + 차단·가시성(module-1/2). **이번 구현은 module-0만.** |

---

> **★ 갱신 (2026-09-21 14:19) — G0 해소됨.** 사용자가 서버를 재시작(PID 37420,
> 11:38:59)한 뒤 동일 호출 4회 재현 결과 `prompt` 단계가 **4/4 정상**이 되었다.
> 상세는 §0-1. 최종 Match Rate는 §6-1.

## 0. ~~★ Critical~~ (해소됨) — 코드는 고쳤으나 **실행 중인 서버에는 반영되지 않았다**

실행 중인 dev 서버(`http://localhost:8000`)로 파이프라인을 실제 호출한 결과:

```
POST /api/v1/agents/pipeline/stream   (2026-09-21 09:41)
  intent   ok          7937ms
  tools    ok          1405ms
  prompt   degraded   20156ms   reason='timeout'     ← 30초가 아니라 20초 벽
  ==> status=prompt_ready  degraded_stages=['prompt']
```

`20156ms`는 **구 설정값(20.0s)** 이다. 새 값(30.0s)이었다면 gpt-5.1의 21~22초를
흡수해 성공했어야 한다.

**원인**: uvicorn 프로세스가 **2026-09-18 16:28 시작 이후 한 번도 재시작되지 않았다.**

| PID | 생성 시각 |
|---|---|
| 18464 (reloader) | 2026-09-18 16:28:15 |
| 9736 (worker) | 2026-09-18 16:28:15 |

`--reload` 워커가 부모와 같은 시각이면 리로드가 한 번도 일어나지 않은 것이다.
게다가 `.env`는 uvicorn의 watch 대상이 아니므로, 리로드가 돌았더라도
`UTILITY_LLM_MODEL_NAME`은 반영되지 않는다 — `load_dotenv()`는 모듈 import
시점에만 실행된다(`src/api/main.py:20`).

**T-15가 3/3 성공한 것과 모순이 아니다.** T-15는 새 설정을 읽는 **인프로세스**
실행이었고, 실서버는 구 설정 프로세스다. 두 결과가 함께 증명하는 것은
**"코드는 옳고, 배포가 안 됐다"** 이다.

> **조치**: 서버 재시작 필요. 이 항목이 해소되기 전에는 사용자가 위저드를 써도
> 여전히 100% 폴백을 받는다.

---

---

## 0-1. G0 해소 검증 (2026-09-21 14:18~14:19)

서버 재시작(PID 37420/6192, 11:38:59) 후 §0과 **동일 요청**으로 4회 호출:

| 실행 | intent | tools | **prompt** |
|---|---|---|---|
| 1 (재시작 후 첫 호출) | ⚠️ degraded 10563ms | ok 1686ms | **ok 6438ms** |
| 2 | ok 4842ms | ok 860ms | **ok 5047ms** |
| 3 | ok 4186ms | ok 1032ms | **ok 5625ms** |
| 4 | ok 4327ms | ok 781ms | **ok 8671ms** |

**`prompt` 4/4 정상.** 평균 6.4초로 인프로세스 실측(gpt-4o-mini 4.48~6.37s)과
일치하며, 30초 예산 대비 **3.4배 여유**다. 재시작 전 `degraded 20156ms` 와 대비된다.

### 새 관측 — 이제 가장 빠듯한 단계는 `intent` 다

실행 1의 `intent degraded 10563ms` 는 `INTENT_ANALYZER_TIMEOUT_SEC = 10.0` 벽이다.
2~4회차가 4.2~4.8초인 것으로 보아 **재시작 직후 콜드 스타트**(LLM 클라이언트 초기화,
utility provider L1 캐시 미스, DB 커넥션 풀 워밍업)가 원인으로 보인다.

| 단계 | 예산 | 관측 최대 | 여유 |
|---|---|---|---|
| `tools` | 5.0s | 1.69s | 3.0배 |
| **`intent`** | **10.0s** | **10.56s (콜드)** | **초과** |
| `prompt` | 30.0s | 8.67s | 3.4배 |

module-0이 `prompt` 의 여유를 3.4배로 넓힌 결과, **병목이 `intent` 로 이동**했다.
`intent` degraded 는 `PipelinePolicy.decide_after_intent` 가 **무조건 proceed** 하므로
(`policies.py:57`) 되묻기가 통째로 생략된다 — 사용자가 원래 문제 삼았던
"물어봤어야 하는데 안 물었다"가 정확히 이 경로다.

> 콜드 스타트 1회 관측이므로 단정하지 않는다. 후속 항목 N1(§9)로 기록한다.

---

## 1. Plan Success Criteria 평가

| ID | 기준 | 판정 | 근거 |
|---|---|:--:|---|
| SC-01 | 실패 시 "스튜디오로 보내기" 비활성 + 사유 노출 | ❌ | module-2 미착수. `PromptStep.tsx:52` 배너 그대로 |
| SC-02 | degraded 프롬프트로 `POST /api/v1/agents` 직접 호출 시 거부 | ❌ | module-1 미착수. `prompt_version_id`·`DegradedPromptPolicy` grep 0건 |
| SC-03 | 편집하면 저장 허용 | ❌ | module-1 미착수 |
| SC-04 | "다시 생성" 성공 시 차단 해제 | ❌ | module-2 미착수 |
| SC-05 | 4개 `reason` 한국어 매핑 | ❌ | module-2 미착수 |
| **SC-06** | **실패 원인 특정 + 재발 방지 테스트** | ✅ | 원인 = gpt-5.1 × 20초 예산(§2). 테스트 9건 추가 |
| SC-07 | `tools` degraded는 저장을 막지 않는다 | ⚠️ | 차단 기능 자체가 없어 자명히 충족되나 **테스트로 고정되지 않음** |

**Plan 전체 기준 1/7.** 다만 SC-01~05는 전부 module-1/2 소관이며 **의도적 미착수**다.
Plan 작성 시점에 module-0이 존재하지 않았으므로(Design에서 신설) SC 표에
module-0 항목이 없다 — 이것이 Plan 문서의 갱신 필요 사항이다.

---

## 2. SC-06 상세 — 원인 규명 결과

Design §1-1에서 규명하고, Do 단계 실측으로 확정했다.

**원인 체인** (전부 코드·DB로 확인)

```
.env 에 UTILITY_LLM_MODEL_NAME 없음
  → src/config.py:37  utility_llm_model_name = None
  → utility_llm_provider.py:105-118  _resolve_default()
  → llm_model.is_default=1 = openai/gpt-5.1  (updated_at 2026-09-04 10:50:09)
  → prompt_version 첫 timeout            (created_at 2026-09-04 10:52:25, +2분 16초)
  → adapter.py:193-200  wait_for(timeout=20.0) 초과 → 폴백
```

**실측 (2026-09-21, 도구 3개 동일 입력 × 3회)**

| 모델 | 측정값 | 20초 통과 |
|---|---|---|
| gpt-5.1 | 21.06 / 21.97 / 22.52 s | **0/3** |
| gpt-4o-mini | 4.48 / 6.31 / 6.37 s | 3/3 |

**DB 운영 관측** — `prompt_version` 18건 중 degraded 4건, `reason`은 **4/4 전부 `timeout`**,
`elapsed_ms` 20000·20016·20023·20030 (전부 20초 벽). 월별 2026-08 실패 0 / 2026-09 실패 4.

→ "가끔 느렸다"가 아니라 **100% 실패가 구조적으로 보장된 상태**였다.

---

## 3. FR-00 구현 대조 (module-0)

| FR | 판정 | 근거 |
|---|:--:|---|
| FR-00a 보조 모델 명시 | ✅ | `.env:104` `UTILITY_LLM_MODEL_NAME=gpt-4o-mini` → `Settings().utility_llm_model_name = 'gpt-4o-mini'` 확인. `main.py:780`이 provider에 전달. `llm_model` 테이블에 해당 row 존재·`is_active=1` 확인 |
| FR-00b 타임아웃 재산정 | ✅ | `prompt_composer_config.py:34` `30.0`. 근거 주석 `:23-33`에 실측·선택 이유 기록 |
| FR-00c 해석 로그 | ✅ | `utility_llm_provider.py:223` INFO 승격, `:137` `source="utility"` / `:158` `source="default"`, L2 히트는 `:233` `_log_instance_hit`로 분리(debug 유지) |
| FR-00d degrade 로그 | ⚠️ | 구현 충족(`adapter.py:309-310`). **단 provider 우선 분기가 무테스트** → G1 |

**부수 개선 (설계 외)**: `adapter.py:188-191` — provider가 `None`을 반환해
`ChatOpenAI` 폴백으로 떨어지는 구간에 warning 추가. 종전 무로그였다.

---

## 4. 테스트 커버리지

| Design §8 ID | 상태 |
|---|---|
| T-01~T-10 | ❌ module-1 미착수 (의도적) |
| T-11~T-14 | ❌ module-2 미착수 (의도적) |
| **T-15** (수동) | ✅ **수행** — 인프로세스 3/3 성공(5.12 / 7.33 / 10.53s, degraded 0) |

**Design §8의 설계 결함**: Test Plan T-01~T-15 중 module-0에 해당하는 것이
**T-15 하나뿐**이었다. 실제 구현은 FR-00c/00d 테스트 9건을 추가했다.
구현이 설계를 보강한 경우이며, Design 문서 갱신이 필요하다.

**신규 테스트 고정력**

| 파일 | 평가 |
|---|---|
| `test_utility_llm_default_observability.py` (5건) | ✅ 충분 — `RecordingLogger.debug`가 no-op(`:36`)이라 **debug로 되돌리면 테스트가 깨진다.** 레벨 승격이 실제로 고정됨 |
| `test_degrade_observability.py` (4건) | ⚠️ 절반 — 필드 존재는 고정하나 `chain=` 주입 경로만 타서 `_active_model_name()`의 provider 우선 분기는 미검증 (G1) |

전체 스위트: **53 failed / 9193 passed** — 기존 실패 53건은 이번 변경과 무관
(parser/retriever/es_client/api). **회귀 0건.**

---

## 5. Gap 목록

| # | Gap | Severity | Conf. | 근거 |
|---|---|:--:|:--:|---|
| **G0** | **실행 중인 서버에 설정 미반영** — 실호출에서 `prompt degraded 20156ms`. 프로세스가 09-18 이후 미재시작 | **Critical** | 100% | §0 실측 |
| G1 | `_active_model_name()`의 provider 우선 분기가 무테스트. 운영 경로(`main.py:4382`)가 정확히 그 분기 | Important | 95% | `test_degrade_observability.py:65-70` vs `adapter.py:168,180-181` |
| G2 | `.env.example`에 `UTILITY_LLM_MODEL_NAME`·`PROMPT_COMPOSER_TIMEOUT_SEC` **둘 다 부재**. 사고 원인이 "env 미설정"이었는데 템플릿이 그대로 | Important | 100% | `.env.example` grep 0건 |
| G3 | SC-07(`tools` degraded 미차단)이 테스트로 고정되지 않음 | Minor | 90% | module-1 착수 시 T-10으로 해소 예정 |
| G4 | `_resolve_by_name` 미해석 시 negative 캐싱 없음 → 매 호출 DB 조회 + warning. FR-00a가 활성화한 신규 경로 | Minor | 70% | `utility_llm_provider.py:128-135`. **단 row 존재·활성 확인되어 현재 발현 안 됨** |
| G5 | `_log_instance_hit`(`:242`)에 `source` 필드 없음 — `_log_resolved`(`:230`)와 스키마 불일치 | Minor | 100% | — |
| G6 | `src/config.py:5` `env_file_encoding="utf-8"` (≠`utf-8-sig`). `.env`에 **BOM 실존 확인** | Minor | 100% | `.env` 첫 3바이트 `\xef\xbb\xbf`. 현재 무영향(키가 104행)이나 첫 키는 취약 |
| G7 | Plan SC 표에 module-0 항목 없음, Design §8에 module-0 테스트 T번호 없음 | Minor | 100% | 문서 갱신 필요 |

---

## 6. Match Rate

**module-0 범위 한정**

| 축 | 점수 | 근거 |
|---|:--:|---|
| Structural | 95% | Design §9.2 module-0 대상 4개 반영, `.env.example`만 누락(G2) |
| Functional | 95% | FR-00a/b/c 완전, FR-00d 구현 완전 |
| Intent (문제 해결) | **50%** | 코드·인프로세스는 해결(T-15 3/3), **실환경은 미해결(G0)** |
| Behavioral | 75% | G1 미테스트 분기, G2 템플릿 누락 |

```
Overall = 95×0.10 + 95×0.40 + 50×0.35 + 75×0.15 = 76.3%
```

> gap-detector는 88.5%로 산정했으나, **실서버 미반영(G0)을 알지 못했다.**
> "원인 체인을 끊었는가"가 이 feature의 존재 이유이고 실환경에서는 아직
> 끊기지 않았으므로 Intent 축을 50%로 내렸다.

**Plan 전체 범위**: SC 1/7 = 14% — 단 module-1/2 미착수가 의도적이므로
이 숫자는 진척도 지표가 아니다.

---

## 7. Decision Record 준수 여부

| 결정 | 준수 | 근거 |
|---|:--:|---|
| D1 module-0 최우선 | ✅ | module-0만 구현 |
| D2 Option C (서버 DB 재조회) | — | module-1 소관, 미착수 |
| D3 내용 비교로 편집 판정 | — | 〃 |
| D4 폴백 문구 불변 | ✅ | `policies.py`의 `_FALLBACK_*` 상수 무변경 |
| D5 `tools` 미차단 | ✅ | 차단 기능 자체 없음 |

---

## 8. 잔여 위험 (module-1/2 미착수)

module-0은 **발생률**을 낮췄을 뿐 **결과의 가시성·차단**은 바뀌지 않았다.

| 위험 | 상태 |
|---|---|
| degraded 프롬프트가 그대로 저장됨 | 서버 게이트 전무 (SC-02/03 미충족) |
| 사용자가 실패를 인지 못함 | 배너뿐, 차단형 UI 없음 (SC-01/04/05 미충족) |
| 잔여 실패율 ≠ 0 | `schema`/`empty`/`error` 3개 사유는 타임아웃과 무관. 발생 시 여전히 조용히 저장됨 (`adapter.py:201-208`) |
| 2차 전파 경로 | 보조 모델이 비활성화되면 `_resolve_model:118`이 기본 모델로 되돌아간다. 30초 예산이 gpt-5.1(22.5s)을 흡수하는 것이 유일한 방어 |

**단, 관측성은 확실히 개선됐다.** 동일 사고 재발 시
`Utility LLM resolved(source=default, model_name=...)` INFO 한 줄과
`prompt generation timeout(model=..., timeout_sec=...)`만으로
DB 포렌식 없이 원인이 드러난다.

---

## 8-1. Act(iterate) 처리 결과 — 2026-09-21

| # | Gap | 상태 | 조치 |
|---|---|:--:|---|
| **G0** | 실서버 설정 미반영 | ✅ **해소 (14:19)** | 사용자 서버 재시작 → 실호출 4회 `prompt` 4/4 정상 (§0-1) |
| G1 | provider 우선 분기 무테스트 | ✅ 해소 | `test_degrade_observability.py`에 `TestActiveModelNamePrefersProvider` 3건 추가. `_StubProvider`+`_ProviderLLM(model_name=...)`로 운영 배선 재현, config 폴백값과 구분 단언 |
| G2 | `.env.example` 두 키 부재 | ✅ 해소 | `.env.example:88-100`에 `UTILITY_LLM_MODEL_NAME`·`PROMPT_COMPOSER_TIMEOUT_SEC` + 사고 경위 주석 추가 |
| G3 | SC-07 테스트 미고정 | ⏭ **보류** | 차단 기능 자체가 없어 지금 테스트는 공허하다. module-1의 T-10으로 처리 |
| G4 | negative 캐싱 부재 | ⏭ 보류 | `gpt-4o-mini` row `is_active=1` 확인 → **현재 발현 안 됨**. module-1과 무관한 선택 항목 |
| G5 | 로그 스키마 불일치 | ✅ 해소 | `_log_instance_hit`에 `source="cached"` 추가 — 같은 메시지명이므로 필드 집합 일치 |
| G6 | `.env` BOM | ✅ 완화 | `src/config.py:5-10` `env_file_encoding="utf-8-sig"`. **실증: BOM이 1행 주석에 있어 현재 어떤 키에도 무영향**(잠재 위험). 나머지 6개 config는 동일 이유로 미변경 |
| G7 | 문서 정합성 | ✅ 해소 | Plan SC 표에 SC-00a~c, Design §8에 T-00a~d 채번 |

### ★ iterate 중 발생시킨 회귀와 그 수정

`tests/conftest.py`(Do 단계 산출물)가 **DB 연동 테스트 91건에
`RuntimeError: Event loop is closed`를 유발**하고 있었다. 동일 조건 대조:

| conftest | failed | passed | errors |
|---|---|---|---|
| 있음 (함수 스코프) | 29 | 2406 | **91** |
| 없음 | 29 | 2497 | 0 |
| **있음 (세션 스코프, 수정 후)** | 29 | 2497 | **0** |

**원인**: 루트 conftest의 **함수 스코프 autouse** 픽스처가 모든 테스트의 픽스처
그래프에 끼어들며 DB 엔진 픽스처와 이벤트 루프 생명주기를 어긋나게 했다.

**수정**: `scope="session"` + `pytest.MonkeyPatch()` 수동 생성/`undo()`.
키 격리는 프로세스 1회면 충분하고, 키를 쓰는 테스트는 스스로
`monkeypatch.setenv`(함수 스코프)를 하므로 영향이 없다.

> Check 단계 초기 측정(53 failed)에서 이 에러가 안 잡힌 이유: `pytest-randomly`로
> 순서가 무작위였고 errors 발생이 순서 의존적이었다. `-p no:randomly` 고정 실행이
> 재현성을 확보했다.

**최종 전체 스위트**: `53 failed / 9347 passed / 2 skipped / 0 errors` — baseline
53건과 동일, **회귀 0건**.

### 갱신된 Match Rate

| 축 | 이전 | 현재 | 사유 |
|---|:--:|:--:|---|
| Structural | 95% | **100%** | G2 해소 |
| Functional | 95% | **100%** | — |
| Intent | 50% | **50%** | G0 미해소 (서버 재시작 대기) |
| Behavioral | 75% | **95%** | G1·G5·G6·G7 해소. G3·G4는 보류(근거 있음) |

```
Overall = 100×0.10 + 100×0.40 + 50×0.35 + 95×0.15 = 81.75%   (G0 미해소 시점)
```

### 6-1. 최종 Match Rate (G0 해소 후, 2026-09-21 14:19)

| 축 | 점수 | 근거 |
|---|:--:|---|
| Structural | 100% | Design §9.2 module-0 대상 전부 반영 + `.env.example` |
| Functional | 100% | FR-00a/b/c/d 완전 |
| **Intent** | **95%** | 실환경 `prompt` 4/4 정상(§0-1). 5% 감점은 N1(intent 콜드 스타트) |
| Behavioral | 95% | G1·G5·G6·G7 해소, G3·G4 근거 있는 보류 |

```
Overall = 100×0.10 + 100×0.40 + 95×0.35 + 95×0.15 = 97.5%
```

**module-0 범위에서 90% 게이트 통과.** Plan 전체(module-1/2 포함) 기준으로는
SC-01~05가 미착수 상태이므로 별개 사이클로 다룬다.

---

## 9. 권고 조치

| 우선 | 항목 | 상태 |
|:--:|---|---|
| ~~1~~ | ~~G0 서버 재시작 후 재현~~ | ✅ 완료 (§0-1) |
| ~~2~~ | ~~G2 `.env.example`~~ | ✅ 완료 |
| ~~3~~ | ~~G1 provider 주입 테스트~~ | ✅ 완료 |
| ~~4~~ | ~~G7 문서 정합성~~ | ✅ 완료 |
| — | G3(SC-07 테스트) | ⏭ module-1 T-10으로 |
| — | G4(negative 캐싱) | ⏭ 선택, 현재 미발현 |

### 후속 관측 항목

| ID | 내용 | 근거 |
|---|---|---|
| **N1** | **`intent` 단계가 이제 가장 빠듯하다.** 예산 10초, 콜드 스타트 관측 10.56초. degraded 시 되묻기가 통째로 생략되어(`policies.py:57`) 원래 사용자 불만("안 물어봤다")이 재현된다 | §0-1 |
| N2 | `uvicorn --reload` 가 09-18~09-21 내내 한 번도 동작하지 않았다. reloader는 venv python, 워커는 시스템 python 불일치 | §0 |

---

## Version History

| 버전 | 일자 | 내용 |
|---|---|---|
| 0.1 | 2026-09-21 | 최초 작성. G0(실서버 미반영) Critical 발견. Match Rate 76.3%. |
