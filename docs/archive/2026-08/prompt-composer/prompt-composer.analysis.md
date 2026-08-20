---
template: analysis
version: 1.3
feature: prompt-composer
---

# prompt-composer Gap Analysis

> **Summary**: 최초 측정 **94%** → Important 2건 수정 + Design 정정 후 **97%**. Critical 0건. 잔여 미이행은 **FR-14(LangSmith 추적, P2)** 1건이며 배선 사이클로 이월했다. Success Criteria **9/9 충족**.
>
> **Project**: sangplusbot (idt — 백엔드)
> **Author**: 배상규
> **Date**: 2026-08-18
> **Plan**: [prompt-composer.plan.md](../01-plan/features/prompt-composer.plan.md)
> **Design**: [prompt-composer.design.md](../02-design/features/prompt-composer.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 프롬프트 생성이 도구 선정과 한 호출에 엉켜 있어 단독 재생성·부분 수정·근거 추적이 전부 불가능하다 |
| **WHO** | P2(에이전트 소유자). 1차 소비자는 백엔드 — UI 배선은 다음 사이클 |
| **RISK** | `AgentComposer`와 프롬프트 생성 로직이 **2벌 공존**한다. 배선 없이 출하하므로 검증 없는 죽은 코드가 될 위험 |
| **SUCCESS** | 기존 경로 회귀 0건 · LLM 실패 3종 degraded · 조립 결정성 · DDL 전 컬럼 COMMENT |
| **SCOPE** | 백엔드 모듈 + 독립 API + 마이그레이션 2건 |

---

## 1. Match Rate

정적 분석 공식 (실행 중인 서버 없음 → runtime 축 제외):

```
최초:  96×0.2 + 93×0.4 + 95×0.4  = 94.4  →  94%
수정후: 100×0.2 + 93×0.4 + 100×0.4 = 97.2  →  97%
```

| 축 | 최초 | 수정 후 | 근거 |
|----|:----:|:------:|------|
| **Structural** | 96% | **100%** | Design §11.1 신규 22개 전량 존재. `config.py`는 Design v0.2에서 수정 대상 제외(설정 단일 소스) |
| **Functional** | 93% | 93% | FR-01~FR-13 이행. **FR-14(LangSmith, P2) 미구현** — 이월 |
| **Contract** | 95% | **100%** | API §4.1~§4.3 전량 일치 + 포트에 `list_versions` 선언 완료 |

**테스트 근거**: 신규 4계층 **149 passed + 1 deselected(L3)** (domain 34 / application 25 / infrastructure 55 / api 25 / db 10). L3는 `-m llm`으로 별도 실행해 통과.

---

## 2. Strategic Alignment (PRD/Plan 정렬)

PRD 없음(`/pdca pm` 미실행) → Plan Context Anchor 기준으로 평가한다.

| 질문 | 판정 | 근거 |
|------|:----:|------|
| WHY의 문제(단독 재생성·부분 수정·근거 추적 불가)를 해결했는가 | ✅ | `POST /compose`가 `session_id` 재사용으로 단독 재생성, `prompt_version.sections` JSON이 섹션 단위 구조 보존, `intent_snapshot`+`tool_ids`가 근거 동봉 |
| 스코프를 넘지 않았는가 | ✅ | `agent_composer`/`general_chat`/`intent`/`tool_selection` 코드 변경 0. 프론트 변경 0 |
| RISK(2벌 공존)를 관리했는가 | ⚠️ | §10.3 대조표를 `prompts.py` 상단에 복사 완료. 다만 **R2 완화책(실 LLM 테스트 1건)은 미이행** → G2 |
| 핵심 설계 결정(D1~D7, Q1~Q4)이 지켜졌는가 | ✅ | §4 참조 — 11건 전건 준수 |

---

## 3. Plan Success Criteria

| # | 기준 | 판정 | 근거 |
|---|------|:----:|------|
| SC-01 | 기존 경로 회귀 0건 | ✅ | 전체 회귀 실행 후 `FAILED` 목록이 베이스라인과 **byte-identical** (58건 사전 존재, 신규 0건) |
| SC-02 | LLM 실패 3종 → 200 + degraded + 비어있지 않은 assembled | ✅ | 4종(error/timeout/schema/empty) 커버 — `test_adapter.py`, `test_prompt_composer_router.py:196` parametrize |
| SC-03 | 조립 결정성 (바이트 동일) | ✅ | `test_policies.py` 20회 반복 호출 동일성 |
| SC-04 | 환각 도구 폐기 | ✅ | `test_use_case.py:191 test_compose_drops_guides_outside_candidates` + `:206 saves_only_surviving_tool_ids` |
| SC-05 | 레이어 위반 0건 | ✅ | `domain/prompt_composer/*.py` 스캔 테스트 — `langchain`·`sqlalchemy`·`fastapi`·`agent_composer` import 0 |
| SC-06 | DDL COMMENT 100% | ✅ | `tests/db/test_migration_ddl_comments.py` 통과 (V061/V062) |
| SC-07 | 세션 격리 404 | ✅ | `test_get_session_of_other_user_returns_404` + UseCase 레벨 2건 |
| SC-08 | 같은 session_id 반복 → version_no 단조 증가 | ✅ | Repository 레벨 `1` + UseCase 레벨 `2` + `uq_session_version` 충돌 재시도 테스트. 측정 지점을 L1→L2로 정정(Design v0.2) — stub 기반 라우터 테스트로는 구조적으로 볼 수 없다 |
| SC-09 | 4계층 테스트 존재 | ✅ | domain/application/infrastructure/api 전 계층 테스트 파일 존재 |

**충족률: 9 / 9 (100%)**

---

## 4. Decision Record 검증

| ID | 결정 | 준수 | 증거 |
|----|------|:----:|------|
| D1 | 병렬 신규 경로, `AgentComposer` 무변경 | ✅ | `git status` — `agent_composer` 하위 변경 0. 아키텍처 테스트가 import 금지 |
| D2 | 의도는 호출자 주입 | ✅ | `AnalyzeIntentUseCase` import 0. 요청 본문 `intent` |
| D3 | 요청 지정 `tool_ids`만 조회 | ✅ | `ToolCatalogMetaReader.fetch(tool_ids)` — 선별 로직 없음 |
| D4 | 구조화 + 서버 조립 | ✅ | `_PromptDraft`에 `assembled` 필드 없음. `Policy.assemble()`이 유일 생성점 |
| D5 | `agent_id` nullable + 백필 | ✅ | V061 `NULL` + `PATCH /sessions/{id}` |
| D6 | LLM 실패 200 + degraded | ✅ | reason 4종 전부 200 |
| D7 | 배선 없이 출하 | ✅ | UI·그래프 연결 0 |
| Q1 | roles 자유 생성, 상한 6 | ✅ | `MAX_ROLES=6`, 도구 0개에도 생성 |
| Q2 | 조립은 domain Policy | ✅ | `policies.py` 순수 함수 |
| Q3 | `clamp_history` 자체 구현 | ✅ | `agent_composer` 의존 0 |
| Q4 | `schema_version` 컬럼 | ✅ | V062 `SMALLINT NOT NULL DEFAULT 1` |
| P1~P5 | 오염 차단 계약 | ✅ | P2는 필드 집합 동등 비교, P5는 **AST 검사**(`ast.Try`/`ast.ExceptHandler` 부재)로 강제 |

**11/11 + 오염 계약 5/5 준수. 이탈 0건.**

---

## 5. Gap List

### Critical (0건)

없음.

### Important (2건 — **모두 수정 완료**, v0.2)

#### G1 — `PromptRepositoryPort`에 `list_versions` 미선언

| 항목 | 내용 |
|------|------|
| **위치** | `src/domain/prompt_composer/interfaces.py:49-83` ↔ `src/application/prompt_composer/compose_prompt_use_case.py:104` |
| **증상** | UseCase가 `self._repository.list_versions(session_id)`를 호출하는데 포트에는 이 메서드가 없다. 구현체(`PromptRepository`)에만 존재 |
| **영향** | Design §9.2 규칙 3("application은 포트에만 의존한다") 위반. 다른 구현체를 끼우면 런타임 `AttributeError`. Protocol이라 정적 검사가 안 잡는다 |
| **수정** | ✅ **완료** — `interfaces.py`에 `list_versions` 선언 추가. 재발 방지로 `test_use_case_calls_only_declared_repository_methods` 추가: UseCase가 `self._repository.X`로 부르는 이름을 AST로 수집해 포트 선언 집합과 대조한다 (Red 확인 후 Green) |

#### G2 — Plan R2 완화책(실 LLM 테스트) 미이행

| 항목 | 내용 |
|------|------|
| **위치** | `tests/infrastructure/prompt_composer/` |
| **증상** | Plan §5 R2가 "실 LLM 호출 테스트를 마커로 1건 작성(기본 제외, 수동 실행)"을 완화책으로 명시했으나 작성되지 않았다. Design §8.1 L3도 동일 |
| **영향** | **배선 없이 출하**하는 모듈이라 실 LLM 왕복이 한 번도 검증된 적이 없다. `with_structured_output(_PromptDraft)`가 실제 모델에서 파싱되는지 미확인 — 다음 사이클 배선 시 첫 호출에서 드러난다 |
| **수정** | ✅ **완료** — `tests/infrastructure/prompt_composer/test_real_llm.py` 추가(`pytestmark = pytest.mark.llm`, 기본 실행에서 deselect). **실제 1회 실행해 통과 확인**: `degraded=False`, 후보 밖 도구 0건, `roles=6 / guides=2 / principles=10` |
| **부수 발견** | 실 왕복 **10,026ms** — NFR-02(p95 8초) **초과**. 표본 1개라 단정할 수 없으나 목표치가 낙관적일 가능성이 있다 → §5 G6 |

### Minor (3건)

#### G3 — `src/config.py` 미수정 (의도된 이탈)

Design §11.1이 `config.py` [수정] 5종 추가를 명시했으나, `PromptComposerConfig(BaseSettings)` 단일 소스로 대체했다. 설정 출처가 2곳으로 갈라지는 것을 피하기 위한 선택이며 `intent`/`tool_selection` 모듈 관례와 동일하다. **Design 문서 쪽을 현실에 맞추는 편이 낫다** (코드가 진실).

#### G4 — SC-08의 "3회" 검증이 2회까지만

`version_no` 1→2 증가는 Repository·UseCase 양쪽에서 검증되나, Design §8.3 #2가 요구한 API 레벨 3회 연속 호출은 없다. 라우터 테스트가 stub UseCase 기반이라 구조적으로 version 증가를 볼 수 없다. 실 DB 통합 테스트를 추가하거나 Design의 측정 지점을 Repository 레벨로 정정해야 한다.

#### G5 — FR-14 LangSmith 추적 미구현 (P2)

`_build_trace_config` 계승이 어댑터에 없다. 우선순위 P2이고 배선 전이라 추적할 트래픽이 없으므로 실질 영향은 0이나, 미이행은 미이행이다.

#### G6 — NFR-02(p95 8초) 대비 실측 10.0초 (신규 · L3 실행으로 발견)

G2 수정 과정에서 실제 LLM을 1회 호출한 결과 **10,026ms**가 나왔다. 표본 1개이므로
p95를 논할 수 없지만, `gpt-4o-mini` 기본 모델에서 도구 2개·이력 0턴이라는 **가장 가벼운
입력**이 이미 목표를 넘겼다는 점은 유의미하다. 타임아웃 설정은 20초라 degraded로 떨어지지는
않는다. 배선 사이클에서 실측 표본을 모아 NFR-02를 조정하거나 모델을 재검토할 것.

### 참고 — 자동 충족된 항목

**E11**(과거 `sections` JSON 파싱 실패 대비 관대 파싱)은 관대 파싱 코드가 없지만 **위반이 아니다** — 현 스코프에서 `sections`를 역직렬화해 읽는 경로가 존재하지 않는다(`GET /sessions`는 `assembled`만 싣는다). 섹션 재생성 API(N3)가 들어올 때 필요해진다.

---

## 6. Runtime Verification

| Level | 상태 | 근거 |
|-------|:----:|------|
| L1 API 계약 | ✅ 실행 | `TestClient` 25건 — 200/401/404/409/422 전 분기. 실 서버 기동 시 `/compose`·`/sessions/{id}` 401 확인 완료(라우트 등록 증명) |
| L2 통합 | ✅ 실행 | in-memory SQLite(`PRAGMA foreign_keys=ON`) 26건 — 커밋 금지·소유권·동시성 재시도 |
| L3 실 LLM | ✅ 실행 (v0.2) | `pytest -m llm` 1건 통과 — `degraded=False`, 환각 0건, 10,026ms |
| L4/L5 | N/A | 백엔드 단일 모듈, Enterprise 레벨 아님 |

> **주의**: `app.routes` 정적 순회로는 이 모듈의 라우트가 보이지 않는다. 현 FastAPI 버전이 `include_router`를 `_IncludedRouter`로 지연 보관하기 때문이며, 기존 실패 `test_main.py … '_IncludedRouter' object has no attribute 'path'`와 동일 원인이다. 등록 검증은 **실제 요청**으로 해야 한다.

---

## 7. Next Steps

| 상태 | 항목 | 결과 |
|:----:|------|------|
| ✅ | G1 포트에 `list_versions` 선언 + AST 계약 테스트 | 완료 |
| ✅ | G2 `-m llm` 실 LLM 테스트 1건 작성 + 실행 | 완료 (통과) |
| ✅ | G3/G4 Design 문서 정정 (코드가 진실) | Design v0.2 — `config.py` 제외, SC-08 측정 지점 L1→L2, §9.3 포트 현행화 |
| ⏭️ | G5 FR-14 LangSmith 추적 | 배선 사이클(N1)로 이월 — 추적할 트래픽이 아직 없음 |
| ⏭️ | G6 NFR-02 실측 표본 수집 | 배선 사이클 |

이후 `/pdca report prompt-composer`.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.2 | 2026-08-18 | Important 2건 수정(G1 포트 선언 + AST 계약 테스트 / G2 L3 실 LLM 테스트 작성·실행) + Design v0.2 정정. 일치율 94% → **97%**, SC 9/9. 신규 발견 G6(NFR-02 실측 초과) | 배상규 |
| 0.1 | 2026-08-18 | 초안 — 정적 분석 94%, Critical 0 / Important 2 / Minor 3 | 배상규 |
