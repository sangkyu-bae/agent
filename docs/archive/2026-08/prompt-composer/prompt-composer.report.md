---
template: report
version: 1.3
feature: prompt-composer
---

# prompt-composer 완료 보고서

> **Project**: sangplusbot (idt — 백엔드)
> **Author**: 배상규
> **Period**: 2026-08-14 → 2026-08-18 (5일 / 4세션)
> **Final Match Rate**: **97%** · **Success Criteria 9/9**
> **Status**: ✅ 완료 — 배선(N1)은 다음 사이클

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 시스템 프롬프트 생성이 `AgentComposer`의 structured output 1회 호출 안에 역량분해·워커선정·도구매칭과 한 덩어리로 묶여 있어, 프롬프트만 재생성하거나 섹션을 고치거나 "어떤 입력에서 이 문장이 나왔는지" 되짚는 것이 전부 불가능했다. |
| **Solution** | `prompt-composer` 신규 모듈 — 채팅 + 주입된 `IntentResult` + 지정 `tool_ids`를 받아 `{purpose, roles[], tool_guides[], principles[]}` 구조로 생성하고, **조립은 서버가 결정적으로** 수행한다. 세션/버전 2테이블에 근거(의도 스냅샷·반영 도구)를 동봉해 이력을 남긴다. |
| **Function/UX Effect** | 화면 변화 **없음** (계획대로 배선 없는 백엔드 API). 엔드포인트 3종이 라이브 상태로 등록됐고, 기존 compose 경로는 코드 한 줄도 바뀌지 않았다. |
| **Core Value** | "프롬프트만 따로, 근거와 함께" — 재생성·비교·되돌리기의 **구조적 토대**가 생겼다. 섹션 단위 재생성(N3)은 이제 API 하나만 얹으면 된다. |

### 1.3 Value Delivered (실측)

| 관점 | 계획 | 실제 | 근거 |
|------|------|------|------|
| **회귀 안전성** | 기존 경로 회귀 0건 | ✅ **0건** | 전체 회귀 실행 후 `FAILED` 목록이 베이스라인과 byte-identical (사전 존재 58건, 신규 0건) |
| **실패 내성** | LLM 실패 3종 degraded | ✅ **4종** (error/timeout/schema/empty) | 계획보다 1종 많다 — 타임아웃을 예외와 분리 |
| **결정성** | 동일 섹션 → 동일 문자열 | ✅ 20회 반복 바이트 동일 | `Policy.assemble()` 순수 함수 |
| **검증량** | 4계층 테스트 존재 | ✅ **149 passed + L3 1건** | 코드 1,692줄 : 테스트 1,839줄 (**1.09:1**) |
| **실 LLM 왕복** | 마커 테스트 1건 | ✅ 작성 + **실행 통과** | `degraded=False`, 환각 0건, 10,026ms |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 프롬프트 생성이 도구 선정과 한 호출에 엉켜 있어 단독 재생성·부분 수정·근거 추적이 전부 불가능하다 |
| **WHO** | P2(에이전트 소유자). 1차 소비자는 백엔드 — UI 배선은 다음 사이클 |
| **RISK** | `AgentComposer`와 프롬프트 생성 로직이 2벌 공존. 배선 없이 출하하므로 검증 없는 죽은 코드가 될 위험 |
| **SUCCESS** | 기존 경로 회귀 0건 · LLM 실패 degraded · 조립 결정성 · DDL 전 컬럼 COMMENT |
| **SCOPE** | 백엔드 모듈 + 독립 API + 마이그레이션 2건 |

---

## 2. 산출물

### 2.1 코드 (신규 22개 / 수정 1개)

| Layer | 파일 | 핵심 |
|-------|------|------|
| **domain** | `schemas.py` `policies.py` `interfaces.py` | frozen dataclass VO · 순수 조립 Policy · 포트 3종. 외부 의존 **0** |
| **application** | `compose_prompt_use_case.py` `errors.py` | 흐름 6단계. **try/except 0개** |
| **infrastructure** | `adapter.py` `prompts.py` `models.py` `repository.py` `prompt_composer_config.py` | `_PromptDraft` 오염 차단 · 실패 4종 흡수 · commit 금지 |
| **interfaces** | `schemas/prompt_composer.py` `routes/prompt_composer_router.py` | 검증 + 위임만 |
| **db** | `V061__create_prompt_session.sql` `V062__create_prompt_version.sql` | 테이블 + 전 컬럼 COMMENT |
| **수정** | `src/api/main.py` | DI 조립 + 라우터 등록 (조립 실패 시 미등록 낙하) |

프로덕션 **1,692줄** / 테스트 **1,839줄**.

### 2.2 API

```
POST   /api/v1/prompt-composer/compose          생성 + 버전 저장
GET    /api/v1/prompt-composer/sessions/{id}    세션 + 버전 목록(최신순)
PATCH  /api/v1/prompt-composer/sessions/{id}    agent_id 백필
```

### 2.3 문서

| Phase | 경로 |
|-------|------|
| Plan | `docs/01-plan/features/prompt-composer.plan.md` |
| Design | `docs/02-design/features/prompt-composer.design.md` (v0.2) |
| Analysis | `docs/03-analysis/prompt-composer.analysis.md` (v0.2) |
| Report | `docs/04-report/prompt-composer.report.md` |

---

## 3. Key Decisions & Outcomes

Plan D1~D7 · Design Q1~Q4 · 오염 차단 계약 P1~P5 — **16건 전건 준수, 이탈 0**.

| ID | 결정 | 결과 | 배운 것 |
|----|------|------|---------|
| **D1** | 병렬 신규 경로, `AgentComposer` 무변경 | ✅ | "무변경"을 의지가 아니라 **아키텍처 테스트로 강제**했다 — `agent_composer` import를 금지어 목록에 넣으니 공용화 유혹이 구조적으로 차단됐다 |
| **D2** | 의도는 호출자 주입 | ✅ | 덕분에 작업 중 `intent` 모듈 스키마가 바뀌었는데도 이 모듈은 영향을 받지 않았다 |
| **D4** | 구조화 + 서버 조립 | ✅ | `_PromptDraft`에 `assembled` 필드를 두지 않으니 "LLM이 조립도 해버리는" 사고가 원천 차단 |
| **D6** | LLM 실패 200 + degraded | ✅ 4종 | 계획한 3종에 타임아웃을 분리 추가 — `reason` 값으로 원인이 구분돼 관측이 쉬워졌다 |
| **D7** | 배선 없이 출하 | ⚠️ | 실사용 검증이 0이라는 대가는 그대로 남는다. R2 완화책(실 LLM 테스트)을 **실제로 돌려서** 최소한의 왕복은 증명했다 |
| **Q4** | `schema_version` 선반영 | ✅ | 이력 테이블은 지우지 않으므로 나중에 넣으면 전 행 백필이 필요했다. 컬럼 1개로 산 보험 |
| **P2** | Draft에 계산 필드 부재 | ✅ | **이 사이클의 핵심.** 아래 §4 참조 |
| **P5** | 어댑터가 예외를 안 던짐 | ✅ | UseCase에 try/except가 0개라는 사실을 AST로 검사한다 — 문자열 검색은 설명 주석에 걸려 실패했다 |

---

## 4. 이 사이클에서 실제로 배운 것

### 4.1 저장소가 기록한 실패를 근거로 쓸 수 있었다

`infrastructure/intent/adapter.py:6-10`에 선행 사이클의 실패가 적혀 있었다 — *"`IntentResult`를 겸용하고 3층 방어를 쌓았으나 계산 필드가 3개로 늘면서 확장에 실패했다."*

이 모듈의 계산 필드는 **4개**이고 결과가 **DB에 영속**된다. 오염값이 되돌릴 수 없게 남는다는 점에서 대가가 더 크다. 그래서 Option A(겸용)를 **처음부터** 배제했다. 코드에 남긴 실패 기록이 다음 사이클의 설계 근거로 실제 작동한 사례다.

### 4.2 "프롬프트로 막는다"는 방어가 아니다

프롬프트에 "목록에 없는 도구를 지어내지 마세요"를 넣었지만, 실제 차단은 `drop_hallucinated()`가 한다. 프롬프트는 **2차 방어선**일 뿐이라는 것을 `prompts.py` 주석에 명시했다.

### 4.3 검증 방법 자체가 두 번 틀렸다

| 시도 | 왜 실패했나 | 대체 |
|------|------------|------|
| `try/except` 문자열 검색 | 규칙을 설명하는 **주석**에 그 단어가 당연히 등장 | `ast.Try` / `ast.ExceptHandler` 노드 탐색 |
| `app.routes` 정적 순회로 라우트 확인 | 이 FastAPI 버전이 `include_router`를 `_IncludedRouter`로 지연 보관 | `TestClient` 실제 요청 → 401 확인 |

두 번째 건은 기존 실패 `test_main.py … '_IncludedRouter' object has no attribute 'path'`와 **동일 원인**이다. 라우트 등록 검증은 이 저장소에서 정적으로 하면 안 된다.

### 4.4 Check 단계가 실제로 결함 2건을 잡았다

- **포트 계약 누수**: UseCase가 포트에 없는 `list_versions()`를 호출하고 있었다. Protocol이라 정적 검사도 런타임도 안 잡는다. 구현체를 갈아끼우는 순간 `AttributeError`.
- **실 LLM 검증 부재**: 스키마가 깨져 있어도 어댑터가 degraded로 삼켜서 **대역 테스트로는 영원히 안 드러난다.** 이게 Plan R2가 완화책을 지정했던 이유였고, Do 단계에서 빠뜨렸다.

둘 다 수정했고, 첫 번째는 재발 방지 테스트(포트 선언 ↔ 호출 이름 AST 대조)를 붙였다.

---

## 5. Success Criteria 최종

| # | 기준 | 판정 | 증거 |
|---|------|:----:|------|
| SC-01 | 기존 경로 회귀 0건 | ✅ | `FAILED` 목록 베이스라인과 byte-identical |
| SC-02 | LLM 실패 → 200 + degraded | ✅ | 4종(error/timeout/schema/empty) parametrize |
| SC-03 | 조립 결정성 | ✅ | 20회 반복 바이트 동일 |
| SC-04 | 환각 도구 폐기 | ✅ | `dropped_tool_ids` + 저장값 제외 |
| SC-05 | 레이어 위반 0건 | ✅ | domain 스캔 — langchain/sqlalchemy/fastapi/agent_composer import 0 |
| SC-06 | DDL COMMENT 100% | ✅ | `test_migration_ddl_comments.py` V061/V062 |
| SC-07 | 세션 격리 404 | ✅ | 403 아님 — 존재 노출 방지 |
| SC-08 | `version_no` 단조 증가 | ✅ | L2에서 검증 (측정 지점 Design v0.2 정정) |
| SC-09 | 4계층 테스트 | ✅ | 전 계층 존재 |

**9 / 9 (100%)**

---

## 6. 미이행 · 이월

| ID | 항목 | 이유 |
|----|------|------|
| **FR-14** | LangSmith 추적 (P2) | 배선 전이라 추적할 트래픽이 없다. N1과 함께 |
| **G6** | NFR-02(p95 8초) 대비 실측 **10.0초** | 표본 1개. 가장 가벼운 입력(도구 2개·이력 0턴)이 목표를 넘겼다는 점은 유의미하다 — 배선 후 표본을 모아 목표 조정 또는 모델 재검토 |
| **N1** | UI 배선 + `degraded` 경고 표시 | 본 사이클 완료가 선행 조건 |
| **N2** | `intent` → `prompt-composer` 2단 호출 배선 | 에이전트 빌더용 의도 라벨 세트 정의 필요 |
| **N3** | 섹션 단위 재생성 API | 본 사이클의 구조화 저장으로 **선행 조건 충족됨** |
| **N4** | 고아 세션 TTL 정리 잡 | 실제 누적량 관측 후 |
| **N5** | `AgentComposer` 프롬프트 생성 통합/제거 판단 | N1 이후 품질 비교 데이터 |

> **R1(2벌 공존)은 해소되지 않았다.** §10.3 대조표를 `prompts.py` 상단에 박아 두 모듈이 벌어지는지 볼 기준은 만들었지만, 통합/제거 판단은 N5로 미뤘다. 이 항목을 계속 열어두면 규칙이 조용히 갈라진다.

---

## 7. 운영 메모

| 항목 | 값 |
|------|-----|
| 킬스위치 | `PROMPT_COMPOSER_ENABLED` (기본 `true`) — 끄면 라우터 미등록 |
| 설정 | `PROMPT_COMPOSER_MODEL` / `_TEMPERATURE` / `_TIMEOUT_SEC` / `_MAX_TOOLS` — `PromptComposerConfig` 단일 소스 (`src/config.py` 아님) |
| 마이그레이션 | V061, V062 — 신규 2테이블, 기존 DDL 변경 0 |
| 실 LLM 테스트 | `pytest -m llm tests/infrastructure/prompt_composer/test_real_llm.py -s` |
| 프론트 영향 | 없음 — 소비자가 아직 없어 `api-contract-sync` 대상 아님 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-18 | 완료 보고 — Match Rate 97%, SC 9/9, 결정 16건 전건 준수. 미이행 FR-14 + 이월 N1~N5 | 배상규 |
