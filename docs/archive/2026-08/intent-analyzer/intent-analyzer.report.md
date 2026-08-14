# intent-analyzer Completion Report

> **Status**: **Partial** — 코드 스코프는 100% 인도, **실 LLM 검증 1건 미완**
>
> **Project**: sangplusbot (idt — 백엔드)
> **Author**: 배상규
> **Completion Date**: 2026-08-13
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | intent-analyzer — 탈착형 의도 분석 모듈 |
| Start Date | 2026-08-13 |
| End Date | 2026-08-13 |
| Duration | 1일 (Plan → Design → Do 3세션 → Check) |
| PM 단계 | 미실행 (모듈 단위 기능이라 생략) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Plan Success Criteria: 8 / 11 충족          │
├─────────────────────────────────────────────┤
│  ✅ 충족:      8 / 11                        │
│  ⚠️ 부분:      1 / 11  (verify 스킬 미실행)   │
│  ❌ 미충족:    2 / 11  (1건 외부, 1건 환경)   │
├─────────────────────────────────────────────┤
│  FR 구현:     13 / 13   (100%)               │
│  Match Rate:  100%      (목표 90%)           │
│  Critical:    0건                            │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 의도 판정 로직이 `multi_query.classify`·`chart_router`·`search_decision`·supervisor 프롬프트 4곳에 각각 하드코딩되어, 새 경로에 붙이려면 매번 다시 만들어야 했다 |
| **Solution** | `domain/intent` 포트 + `infrastructure/intent` LLM 어댑터 + `application/intent` UseCase·노드 팩토리 + 독립 API. **분류 체계(라벨)를 호출 인자로 외부화**해 모듈이 라벨 의미를 모르게 만듦 |
| **Function/UX Effect** | 사용자 화면 변화 **0** (의도적 — 기존 경로 무배선). 프로덕션 605줄 / 테스트 1,117줄(비율 **1.85:1**), 커버리지 **97%**, 기존 파일 변경 **1개(+14줄, 삭제 0줄)**, 마이그레이션 **0건**, 회귀 **0건** |
| **Core Value** | **"끼웠다 뺐다"가 코드로 증명됨** — 모듈을 참조하는 파일이 `main.py` 단 1개(grep 전수 확인). `analyzer=None`이면 노드 팩토리가 `None`을 반환해 그래프에 노드가 존재조차 하지 않고, LLM이 죽어도 `degraded=True`만 반환해 호출자 흐름을 막지 않는다 |

---

## 1.4 Success Criteria Final Status

### Definition of Done (Plan §4.1)

| # | 기준 | 상태 | 증거 |
|---|------|:----:|------|
| SC-1 | FR-01 ~ FR-13 전부 구현 | ✅ Met | Analysis §3.2 — 13/13 |
| SC-2 | `pytest` 전체 통과 (기존 실패 0건) | ❌ Not Met | `7049 passed, 58 failed` — **58건 전부 baseline 동일**(파일별 개수까지 일치), 본 기능 무관. 원인은 라이브러리 버전 드리프트 |
| SC-3 | supervisor/general_chat/multi_query 변경 0건 | ✅ Met | `git status` — 내 변경은 `src/api/main.py` 1개뿐 |
| SC-4 | `db/migration/` 신규 0건 | ✅ Met | `git status -- db/migration` → 0 |
| SC-5 | verify 스킬 3종 통과 | ⚠️ Partial | 스킬 미실행. grep·AST 수동 대조로 동등 확인 (A1·A2·A5·A6) |
| SC-6 | 실호출 1회 성공 (수동) | ❌ Not Met | 서버 미기동 + API 키 필요 → **최우선 이월 (G1)** |

### Quality Criteria (Plan §4.2)

| # | 기준 | 상태 | 증거 |
|---|------|:----:|------|
| SC-7 | `IntentResultPolicy` 분기 100% | ✅ Met | `policies.py 26 stmts / 0 miss / 100%` |
| SC-8 | LLM 실패 3종 각각 degraded 테스트 | ✅ Met | 예외·타임아웃·스키마위반 3건 통과 |
| SC-9 | spec 밖 라벨 → 강등 테스트 | ✅ Met | domain 1건 + adapter 1건 |
| SC-10 | API 200/401/422 테스트 | ✅ Met | 라우터 13건 통과 |
| SC-11 | 40줄 이내 / if 중첩 2단계 이내 | ✅ Met | AST 검사 위반 0건 |

**Success Rate: 8/11 충족 (73%)** — 부분 1, 미충족 2 (SC-2는 외부 원인, SC-6은 환경 의존)

> 코드로 만들 수 있는 것은 전부 만들었고, 미충족 2건은 **코드가 아니라 환경**에 달려 있다.

---

## 1.5 Decision Record Summary

| Source | Decision | 준수 | 실제 결과 |
|--------|----------|:----:|-----------|
| [Plan] D1 | 산출물 = 구조화 의도 객체 | ✅ | `IntentResult` 7필드. `rewritten_query`는 `query_rewrite` 기존 책임이라 제외한 판단이 유효했음 |
| [Plan] D2 | LLM 전용 (휴리스틱 포기) | ✅ | D3와의 충돌을 설계 단계에서 해소한 결과. Policy는 판정이 아닌 **정규화**만 맡아 순수함수 100% 커버 달성 |
| [Plan] D3 | 라벨 호출자 주입 | ✅ | **프로덕션 코드에 도메인 라벨 문자열 0건**(grep 검증). `search`/`analysis`는 테스트 픽스처에만 존재 |
| [Plan] D4 | 포트 + 노드 팩토리 | ✅ | `search_decision` 선례의 4번째 인스턴스로 안착. 새 패턴 도입 0 |
| [Plan] D5 | 조언 전용 | ✅ | 노드가 state 1키만 기록, 분기 강제 없음 |
| [Plan] D6 | 실패 시 `degraded` | ✅ | HTTP 200 + `degraded=true` 계약까지 테스트로 고정 |
| [Plan] D7 | 메시지 + optional 이력, 무상태 | ✅ | 상태 필드 0건(grep). 이력은 인자로만 |
| [Plan] D8 | 배선 없음 (모듈만) | ✅ | 회귀 0건의 직접 원인. 이 결정이 없었다면 R2를 검증 없이 떠안았을 것 |
| [Design] Option C | search_decision 패턴 복제 | ✅ | 신규 12파일. Option B(매퍼 분리) 대비 유지비 절감 |
| [Design] §2.4 | `degraded` 3층 방어 | ✅ | LLM이 `degraded=True`를 반환해도 성공 경로면 무시 — 테스트 2건으로 고정 |
| [Design] §4.3 | 프롬프트 3층 방어 (R2) | ⚠️ **미검증** | 코드에는 반영. **실 LLM에서 통하는지는 확인 안 됨 → G1** |
| [Design] §11.4 | 1차 배선 = supervisor shadow 2단계 | — | 다음 사이클 대상 |

**결정 이탈: 0건**

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| PM | — | 미실행 (모듈 단위라 생략) |
| Plan | [intent-analyzer.plan.md](../01-plan/features/intent-analyzer.plan.md) | ✅ 확정 |
| Design | [intent-analyzer.design.md](../02-design/features/intent-analyzer.design.md) | ✅ 확정 |
| Check | [intent-analyzer.analysis.md](../03-analysis/intent-analyzer.analysis.md) | ✅ 완료 (v0.2) |
| Act | 본 문서 | ✅ 작성 |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | 요구 | 상태 | 비고 |
|----|------|:----:|------|
| FR-01 | 도메인 포트, 외부 의존 0 | ✅ | `IntentAnalyzerInterface` |
| FR-02 | 라벨 호출자 주입 | ✅ | `IntentSpec(labels=[IntentLabel(name, description)])` |
| FR-03 | 구조화 객체 7필드 | ✅ | `IntentResult` |
| FR-04 | history optional, 무상태 | ✅ | 노드 레벨 검증은 Check 단계에서 보강 (G2) |
| FR-05 | LLM 전용 structured output | ✅ | `adapter.py:72` |
| FR-06 | 실패 3종 → degraded | ✅ | 예외 미전파 계약 |
| FR-07 | `normalize` 4규칙 | ✅ | 분기 100% |
| FR-08 | state_key 1개만 갱신 | ✅ | messages 미생성(위키 계약 1) |
| FR-09 | `analyzer=None` → `None` | ✅ | **탈착 이음매의 핵심** |
| FR-10 | POST + 인증 | ✅ | `Depends(get_current_user)` |
| FR-11 | labels<2 → 422 | ✅ | pydantic `min_length=2` |
| FR-12 | config 주입 | ✅ | `IntentConfig` 4항목, 전부 기본값 보유 |
| FR-13 | 판정당 구조화 로그 1건 | ✅ | `exception=e` 규약 준수 |

**13/13 완료**

### 3.2 Non-Functional Requirements

| 항목 | 목표 | 달성 | 상태 |
|------|------|------|:----:|
| 결합도 — domain→infra import | 0 | 0 | ✅ |
| 결합도 — application→langchain import | 0 | 0 | ✅ |
| 탈착성 — 모듈 참조 파일 | main.py만 | main.py만 | ✅ |
| 회귀 — 기존 파일 변경 | 1개 | 1개 (+14/-0) | ✅ |
| 지연 — 타임아웃 | 10s, 초과 시 degraded | 구현+테스트 | ✅ |
| 관측성 — 스택 트레이스 | `exception=e` | 준수 | ✅ |
| 테스트 — policy 분기 | 100% | 100% | ✅ |
| 커버리지 (모듈 전체) | — | **97%** | ✅ |

### 3.3 Deliverables

| 산출물 | 위치 | 줄 수 | 상태 |
|--------|------|------:|:----:|
| 도메인 (VO·포트·정책) | `src/domain/intent/` | 200 | ✅ |
| 응용 (UseCase·노드 팩토리) | `src/application/intent/` | 138 | ✅ |
| 인프라 (LLM 어댑터) | `src/infrastructure/intent/` | 176 | ✅ |
| 설정 | `src/infrastructure/config/intent_config.py` | 19 | ✅ |
| API 스키마 | `src/interfaces/schemas/intent.py` | 26 | ✅ |
| 라우터 | `src/api/routes/intent_router.py` | 46 | ✅ |
| DI 배선 | `src/api/main.py` | +14 | ✅ |
| 테스트 8파일 | `tests/{domain,application,infrastructure,api}/` | 1,117 | ✅ |
| PDCA 문서 3종 | `docs/{01-plan,02-design,03-analysis}/` | — | ✅ |

**프로덕션 605줄 : 테스트 1,117줄 = 1 : 1.85**

---

## 4. Incomplete Items

### 4.1 다음 사이클 이월

| 항목 | 사유 | 우선순위 | 예상 공수 |
|------|------|:--------:|-----------|
| **G1 — 실 LLM 호출 검증 1회** | 서버 기동 + `OPENAI_API_KEY` 필요, 자동화 불가 | **최상** | 10분 (환경 준비 별도) |
| **배선 1단계 (supervisor shadow)** | Plan D8에서 의도적으로 스코프 밖 | 상 | 별도 PDCA 사이클 |
| 배선 2단계 (조언 주입) + R2 재평가 | 1단계 데이터 수집 후 | 중 | 별도 사이클 |
| 라벨 DB 설정화 + 빌더 UI | Plan §2.2 Out of Scope (마이그레이션+UI로 범위 확대) | 하 | 별도 사이클 |
| 기존 3개 판정 모듈 통합 검토 | 소비자 2곳 이상 생긴 뒤 판단 | 하 | — |

> **G1은 단순 체크리스트 항목이 아니다.** Design §4.3 프롬프트는 위키 계약 2
> (목록 프레이밍 과차단, 커밋 08d37cab 실장애)를 완화하려고 짠 문안이고, 그것이
> 실제로 통하는지 확인하는 **유일한 수단**이다. Analysis 문서에 **배선 사이클 진입
> 조건**으로 명시했다.

### 4.2 취소/보류

| 항목 | 사유 | 대안 |
|------|------|------|
| 휴리스틱 1차 필터 | D3(라벨 주입)와 논리적 충돌 — Policy가 라벨 의미를 모르면 매칭 불가 | LLM 전용(D2). 비용 절감은 배선 시점에 캐시로 재검토 |
| `rewritten_query` 필드 | `query_rewrite` 모듈의 기존 책임 | 기존 모듈 사용 |
| UseCase의 `logger` 의존 | 어댑터가 이미 로깅 — 죽은 의존 | 제거 (Design 이탈 #1, 문서화됨) |

---

## 5. Quality Metrics

### 5.1 최종 분석 결과

| 지표 | 목표 | 최초 측정 | 최종 | 변화 |
|------|-----:|---------:|-----:|-----:|
| Design Match Rate | 90% | 96.8% | **100%** | +3.2%p |
| — Structural | — | 100% | 100% | — |
| — Functional | — | 92% | **100%** | +8%p |
| — Contract | — | 100% | 100% | — |
| 모듈 테스트 | — | 58 passed | **66 passed** | +8 |
| 모듈 커버리지 | — | 88% | **97%** | +9%p |
| `node.py` 커버리지 | — | 67% | **100%** | +33%p |
| Critical 이슈 | 0 | 0 | **0** | ✅ |
| 전체 스위트 회귀 | 0 | 0 | **0** | ✅ |

### 5.2 해소한 이슈

| 이슈 | 조치 | 결과 |
|------|------|------|
| **G2** — `node.py` history 경로 전량 미테스트 (13 stmts) | 테스트 6건 추가 (정상 변환 / `Turn` 통과 / 형식불일치 무시 / 전량무효 / 비리스트 / `history_key` 미지정) | ✅ 67% → 100%, **프로덕션 코드 무수정** |
| **G3** — `allow_unknown=False` 분기 미테스트 | 테스트 2건 추가 | ✅ 해소 |
| 설계 충돌 — 라벨 주입 vs 휴리스틱 | Design 단계에서 D2를 LLM 전용으로 전환 | ✅ 구현 전 해소 |
| `Any` 금지 vs fake chain 주입 | `IntentChain` Protocol 도입 | ✅ 양립 + 테스트의 `type: ignore` 제거 |
| 사용자 메시지의 중괄호가 템플릿 파손 | 회귀 테스트 추가 | ✅ 방지 |
| 빈 state에서 LLM 호출 비용 발생 | 메시지 없으면 LLM 미호출 후 degraded | ✅ 설계 확장 |

**G3 두 번째 테스트는 단순 커버리지 채우기가 아니다** — `allow_unknown=False`를
"빈 label 금지"로 해석하는 순간 위키 계약 2의 과차단이 재현되므로, 그 해석을
`assert "비워 두어도" in block` 으로 못 박았다.

### 5.3 미검증 잔여 영역 (정직한 공백)

| 영역 | 사유 |
|------|------|
| `_build_chain` (adapter:65-73) | 실 `ChatOpenAI` 필요 — G1이 대신함 |
| `IntentAnalyzerInterface.analyze` 추상 `raise` | 도달 불가 코드 |
| **프롬프트 실효성 전체** | **G1 — 이 사이클의 가장 큰 공백** |
| mypy strict (infra 계층) | `numpy` 스텁 vs `python_version=3.11` 환경 문제. 기존 `search_decision`도 동일하게 실패함을 대조 확인 |

---

## 6. Lessons Learned & Retrospective

### 6.1 Keep — 잘 된 것

- **위키를 SoT로 먼저 읽은 것이 최대 수확.** `supervisor-graph-contracts.md`의 계약 2(목록 프레이밍 과차단)를 **Plan 단계에서** 발견해 R2로 등록했고, 그 결과 Design §4.3의 3층 방어와 §11.4의 2단계 배선 절차가 나왔다. 위키를 안 봤다면 "라벨 목록을 프롬프트에 넣는다"는 걸 아무 의심 없이 했을 것이다.
- **기존 선례 3개(`search_decision`·`chart_router`·`planner`)를 먼저 찾은 것.** 설계를 새로 발명하지 않고 "4번째 인스턴스"로 규정하니 구조 논쟁이 사라졌다.
- **TDD Red를 매번 실제로 확인.** 3개 모듈 모두 `ModuleNotFoundError`를 눈으로 보고 넘어갔다. 형식적 TDD가 되지 않았다.
- **인터뷰에서 발견한 논리 충돌을 구현 전에 해소.** "라벨 주입 + 휴리스틱 1차"가 성립하지 않는다는 걸 Design 착수 시점에 지적해 D2를 바꿨다. 구현 후였다면 재작업이었다.
- **미배선 결정(D8)이 회귀 0건을 만들었다.** 기존 파일 변경 1개, 삭제 0줄.

### 6.2 Problem — 개선 필요

- **설계 이탈 시 테스트를 같이 늘리지 않았다 → G2의 직접 원인.** Design에 없던 `history_key`·`message_key`를 추가하면서 테스트는 Design §8.2 시나리오 목록만 따랐다. 결과적으로 13 stmts가 통째로 미검증 상태로 Check까지 갔다.
- **Do 단계에서 커버리지를 재지 않았다.** ruff·pytest만 돌리고 넘어가, G2·G3를 Check에서야 발견했다. Do 종료 조건에 커버리지가 없었다.
- **전체 스위트를 module-1,2 완료 시점에 처음 돌렸다.** 58건의 기존 실패를 그때 알았고, "baseline인지 내가 깼는지" 확인에 추가 시간이 들었다. 착수 전에 baseline을 한 번 떠놨어야 했다.
- **Explore 서브에이전트가 스톨해 조사 결과를 유실**했다(4분 소요 후 실패). 수동 재조사로 복구했지만, 단일 에이전트에 조사를 몰아준 게 단일 실패점이 됐다.
- **프롬프트 의존 기능인데 실호출 검증 계획을 "수동 체크리스트"로만 뒀다.** 그 결과 사이클이 끝나도록 미실행이다. 리스크의 크기(R2 = High)에 비해 검증 장치가 약했다.

### 6.3 Try — 다음에 시도할 것

- **Design 이탈 표를 Do 단계 산출물로 의무화**: "이탈 항목 → 대응 테스트" 2열 표. 이탈을 적는 순간 테스트도 적게 만든다.
- **Do 종료 조건에 커버리지 측정 추가**: 모듈 커버리지를 찍고 미커버 라인을 눈으로 확인한 뒤에만 Do를 닫는다.
- **작업 착수 전 baseline 테스트 결과 스냅샷**: `pytest -q | tail -1`을 Plan 단계에서 한 번 기록.
- **프롬프트 의존 기능은 Design에 "실호출 게이트"를 명시적 단계로 못박기**: 수동 체크리스트가 아니라 Do 단계의 종료 조건으로. 환경이 없으면 그 사실 자체를 Plan 리스크로 올린다.
- **조사 작업은 좁게 쪼개서 병렬화**: 7문항을 한 에이전트에 몰지 말 것.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA 프로세스

| Phase | 이번 사이클 실태 | 개선 제안 |
|-------|-----------------|-----------|
| Plan | 인터뷰 10문항으로 D1~D8 확정 — 잘 작동 | baseline 테스트 스냅샷 1줄 추가 |
| Design | 3안 비교가 실질적 선택지였음(A는 FR 미달, B는 선례 이탈) | 유지 |
| Do | 커버리지 미측정 · 설계 이탈 테스트 누락 | 종료 조건에 **커버리지 + 이탈 표** 추가 |
| Check | `gap-detector` 미호출(운영 제약) → 수동 대조로 충분히 대체됨. **커버리지가 실제 갭 2건을 잡아냄** | 커버리지를 Check 표준 항목으로 승격 |
| Act | 테스트 추가만으로 해소, 프로덕션 무수정 | 유지 |

### 7.2 도구/환경

| 영역 | 개선 제안 | 기대 효과 |
|------|-----------|-----------|
| 테스트 | 기존 실패 58건 정리 (parser 21 / agent_builder_stream 9 / retriever 7 / general_chat 7 …) | Plan DoD "전체 통과" 기준이 의미를 되찾음 |
| 타입 검사 | `numpy` 스텁 vs `python_version=3.11` 불일치 해소 | infra 계층 mypy strict 복구 |
| 로컬 검증 | 개발용 `.env` + 기동 스크립트 정비 | G1류 수동 검증이 매 사이클 이월되지 않음 |
| 동시 작업 | 같은 워크스페이스 병행 세션 시 커밋 분리 가이드 | 이번에 `src/config.py`·`tool_selection/`이 섞여 보임 |

---

## 8. Next Steps

### 8.1 즉시

- [ ] **G1 — 실 LLM 호출 1회 검증** (최우선)
  ```bash
  uvicorn src.main:app --reload --port 8000
  # 인증 토큰으로 POST /api/v1/intent/analyze 1회
  ```
  확인 포인트: ① 라벨이 정확히 붙는가 ② **후보 밖 질문에서 과차단 없이 빈 label이 나오는가(R2 실증)** ③ 지연·비용
- [ ] 커밋 시 `src/config.py`·`tool_selection/`(다른 세션의 tool-recommender 작업) 분리
- [ ] `.env.example`에 `INTENT_ANALYZER_*` 4항목 추가 여부 확인

### 8.2 다음 PDCA 사이클

| 항목 | 우선순위 | 진입 조건 |
|------|:--------:|-----------|
| **배선 1단계 — supervisor shadow** (state 기록만, 프롬프트 미주입) | 상 | **G1 완료 필수** |
| 배선 2단계 — 조언 주입 + R2 재평가 | 중 | 1단계 로그로 정확도·`degraded` 비율·지연 확보 |
| 기존 테스트 58건 실패 정리 | 중 | 독립 |
| 라벨 DB 설정화 + 빌더 UI (P2 자가 구성) | 하 | 배선 2단계 이후 |

---

## 9. Changelog

### v1.0.0 (2026-08-13)

**Added**
- `domain/intent` — `Turn`·`IntentLabel`·`IntentSpec`·`IntentResult` VO, `IntentAnalyzerInterface` 포트, `IntentResultPolicy` 정규화 정책
- `application/intent` — `AnalyzeIntentUseCase`, `create_intent_node()` 탈착 노드 팩토리
- `infrastructure/intent` — `LLMIntentAnalyzerAdapter` (structured output + 3종 폴백)
- `infrastructure/config/intent_config.py` — `IntentConfig` (모델·온도·타임아웃·이력 길이)
- `POST /api/v1/intent/analyze` — 라벨 주입형 의도 판정 API
- 테스트 8파일 1,117줄 (66 케이스)
- PDCA 문서 3종 (plan / design / analysis)

**Changed**
- `src/api/main.py` — intent 라우터 등록 + DI 배선 (+14줄, 삭제 0줄)

**Fixed**
- 해당 없음 (신규 기능)

**Notes**
- 기존 실행 경로(supervisor / general_chat / multi_query) **변경 없음**
- DB 마이그레이션 **0건**
- 프론트엔드 변경 **0건** — API 계약 동기화 불필요

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-13 | 완료 보고서 작성. Status=Partial (G1 이월) | 배상규 |
