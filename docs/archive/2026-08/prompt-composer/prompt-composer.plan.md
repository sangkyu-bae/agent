# prompt-composer Planning Document

> **Summary**: 사용자 채팅 + (주입된) 의도 분석 결과 + 지정 도구 카탈로그 메타를 입력받아 **구조화된 시스템 프롬프트**를 생성하고 버전 이력을 남기는 독립 백엔드 모듈. 기존 `AgentComposer` 경로는 건드리지 않는 병렬 신설이다.
>
> **Project**: sangplusbot (idt — 백엔드)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-08-14
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 시스템 프롬프트 생성이 `AgentComposer`의 structured output 1회 호출 안에 역량분해·워커선정·도구매칭과 **한 덩어리로 묶여** 있다. 프롬프트만 다시 뽑거나, 일부 섹션만 고치거나, 어떤 입력에서 이 프롬프트가 나왔는지 되짚을 방법이 없다. 의도 분석(`intent`)·도구 선별(`tool_selection`) 모듈은 만들어 뒀지만 프롬프트 생성에 연결된 적이 없다. |
| **Solution** | `prompt-composer` 신규 모듈 — 채팅 + `IntentResult`(주입) + `tool_ids`를 받아 `{purpose, roles[], tool_guides[], principles[]}` 구조로 생성하고, **조립은 서버가 결정적으로** 수행한다. 세션/버전 2테이블에 이력을 남겨 재생성·비교·되돌리기의 토대를 만든다. 기존 compose 경로는 **무변경**. |
| **Function/UX Effect** | 이번 사이클엔 화면 변화 **없음** (배선 없는 백엔드 API만). P2는 `POST /api/v1/prompt-composer/compose`로 프롬프트를 뽑고 세션 이력을 조회할 수 있다. |
| **Core Value** | "프롬프트만 따로, 근거와 함께" — 어떤 요청·어떤 의도·어떤 도구에서 이 문장이 나왔는지가 버전 레코드에 남고, 섹션 단위로 재생성할 수 있다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 프롬프트 생성이 도구 선정과 한 호출에 엉켜 있어 단독 재생성·부분 수정·근거 추적이 전부 불가능하다 |
| **WHO** | P2(에이전트 소유자). 1차 소비자는 백엔드 — UI 배선은 다음 사이클 |
| **RISK** | `AgentComposer`와 프롬프트 생성 로직이 **2벌 공존**한다. 배선 없이 출하하므로 검증 없는 죽은 코드가 될 위험 + 두 프롬프트 규칙이 서로 벌어질 위험 |
| **SUCCESS** | 기존 경로 회귀 0건 · LLM 실패 3종 모두 `degraded=true` + 규칙기반 폴백 반환 · 동일 입력 → 동일 `assembled` (조립 결정성) · DDL 전 컬럼 COMMENT |
| **SCOPE** | 백엔드 모듈 + 독립 API + 마이그레이션 2건. **스코프 밖**: 프론트 UI, `AgentComposer` 수정/대체, `tool_selection` 배선, 의도 분석 내부 호출 |

---

## 1. Overview

### 1.1 Purpose

자연어 요청과 그에 대한 분석 결과(의도 + 선택된 도구)를 재료로 **에이전트 시스템 프롬프트를 생성하는 단일 책임 모듈**을 만든다. 핵심은 문장 품질이 아니라 **경계**다 — 도구를 고르지 않고(호출자가 준 `tool_ids`만 씀), 의도를 분석하지 않으며(주입받음), 오직 "재료 → 프롬프트"만 한다.

### 1.2 Background

현재 프롬프트 생성의 실제 위치는 한 곳이다.

| 위치 | 하는 일 | 문제 |
|------|---------|------|
| `application/agent_composer/composer.py:68` `_ComposeOutput` | `capabilities` + `workers` + `flow_hint` + **`system_prompt`** + `agent_name`을 LLM 1회로 동시 생성 | 프롬프트만 재생성 불가. 섹션 구조가 프롬프트 텍스트 안에만 존재(`_SYSTEM_PROMPT:97-102`)해 파싱·부분수정 불가 |
| `application/agent_composer/planner.py` | HITL 질문 + `BuildPlan` | 프롬프트 미관여 |

동시에 최근 두 사이클에서 **입력 재료를 만드는 모듈**은 이미 출하됐다.

| 모듈 | 산출물 | 현재 배선 |
|------|--------|-----------|
| `intent` (intent-analyzer) | `IntentResult{label, confidence, entities, ambiguous, missing_slots, reason, degraded}` | **없음** — `POST /api/v1/intent/analyze` 단독 노출 |
| `tool_selection` | `SelectionResult{selected_ids, final_ids, dropped_ids, fallback}` | General Chat 런타임만 (`tool_selector_enabled` 기본 False) |
| `tool_catalog` | `ToolCatalogModel{tool_id, source, mcp_server_id, name, description, requires_env, is_builtin}` | 전역 사용 |

본 기능은 이 재료들을 **소비하는 첫 모듈**이다. 단, 이번 사이클에서는 `SelectionResult`를 직접 참조하지 않고 **`tool_ids: list[str]`라는 최소 계약**만 받는다 — 도구를 누가 골랐든(셀렉터든, 사용자 수동 선택이든) 무관하게 동작하기 위해서다.

### 1.3 Design Decisions (확정)

| ID | 결정 | 근거 | 대가 |
|----|------|------|------|
| **D1** | **병렬 신규 경로** — `AgentComposer` 무변경, 별도 라우터 신설 | compose는 진입 화면·Fix 탭이 이미 의존하는 라이브 경로다. 프롬프트 필드를 떼면 프론트 계약까지 동시에 깨진다 | 프롬프트 생성 규칙이 2벌 공존 → §5 R1로 관리 |
| **D2** | 의도는 **호출자 주입** (`IntentResult`를 요청 본문으로) | 모듈 내부에서 `AnalyzeIntentUseCase`를 부르면 라벨 체계를 이 모듈이 소유하게 되어 `intent`의 "결합도 0" 설계를 깬다. LLM 호출도 1회로 유지 | 호출자가 2번 호출해야 함 (`/intent/analyze` → `/prompt-composer/compose`) |
| **D3** | 도구는 **요청이 지정한 `tool_ids`만** `tool_catalog`에서 조회 | 도구 선별은 `tool_selection`/`AgentComposer`의 책임. 여기서 또 고르면 3벌째가 된다 | 호출자가 도구를 먼저 정해야 함 |
| **D4** | 출력은 **구조화 섹션 + 서버 조립** — LLM은 `assembled`를 만들지 않는다 | 동일 섹션 → 동일 문자열이 보장돼야 섹션 단위 재생성·diff가 성립한다 | 조립 포맷이 코드에 고정됨 (커스터마이즈 불가) |
| **D5** | `prompt_session`(1) ─ `prompt_version`(N), `agent_id`는 **nullable** | 생성 시점엔 저장된 에이전트가 없다. 나중에 저장되면 백필 | 고아 세션 누적 → §5 R3 |
| **D6** | LLM 실패는 **200 + `degraded=true` + 규칙기반 폴백** | `intent` 모듈과 동일 계약. 호출자가 에러 핸들링 없이 "기본 프롬프트라도 받는다" | 저품질 프롬프트가 조용히 나갈 수 있음 → `degraded` 플래그로 관측 |
| **D7** | **배선 없이 출하** (UI·기존 그래프 미연결) | `intent-analyzer`와 동일 관례. 회귀 위험 0 | 실사용 검증 없이 다음 사이클로 넘어감 → §5 R2 |

---

## 2. Scope

### 2.1 In Scope

| # | 항목 |
|---|------|
| S1 | `domain/prompt_composer` — VO(`PromptSections`, `ToolMeta`, `ComposedPrompt`), 조립 Policy, 포트 인터페이스 |
| S2 | `application/prompt_composer` — `ComposePromptUseCase` (조회 → LLM → 조립 → 저장) |
| S3 | `infrastructure/prompt_composer` — LLM 어댑터 + 프롬프트 템플릿 + SQLAlchemy 모델 2종 + Repository |
| S4 | `api/routes/prompt_composer_router.py` + `interfaces/schemas/prompt_composer.py` |
| S5 | 마이그레이션 `V061__create_prompt_session.sql`, `V062__create_prompt_version.sql` (테이블 + 전 컬럼 COMMENT) |
| S6 | `main.py` DI 조립 + 라우터 등록 (조립 실패 시 라우터 미등록으로 낙하) |
| S7 | 테스트 — domain/application/infrastructure/api 4계층 |

### 2.2 Out of Scope

| # | 항목 | 이유 |
|---|------|------|
| O1 | 프론트엔드 UI (진입 화면·Fix 탭 연결) | D7 — 다음 사이클 |
| O2 | `AgentComposer`의 `system_prompt` 필드 제거/대체 | D1 — 라이브 경로 무변경 |
| O3 | `tool_selection` 셀렉터를 이 경로에 배선 | D3 — 도구는 주입받음 |
| O4 | 의도 분석 내부 호출 | D2 |
| O5 | MCP `list_tools` 실시간 조회(inputSchema 주입) | 연결 지연·실패 처리가 별도 설계 필요. `tool_catalog.description`으로 충분 |
| O6 | 섹션 **부분** 재생성 API (`regenerate?section=tool_guides`) | 구조화 저장이 선행 조건. 구조만 깔고 API는 다음 사이클 |
| O7 | 프롬프트 품질 평가(RAGAS/eval 연동) | 별도 기능 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|:--------:|
| **FR-01** | `POST /api/v1/prompt-composer/compose` — `user_request`(필수) + `history`(선택) + `intent`(선택) + `tool_ids`(선택) → 구조화 프롬프트 + `assembled` + `version_id` 반환 | P0 |
| **FR-02** | `tool_ids`로 `tool_catalog`를 조회해 `name`/`description`/`source`/`mcp_server_id`를 프롬프트 컨텍스트로 구성한다. 카탈로그에 없거나 `is_active=false`인 ID는 **무시하고** 응답의 `unknown_tool_ids`로 에코백한다 | P0 |
| **FR-03** | LLM `with_structured_output` **1회** 호출로 `{purpose, roles[], tool_guides[], principles[]}`를 생성한다 | P0 |
| **FR-04** | `assembled` 문자열은 **서버가 결정적으로 조립**한다. LLM 출력에 `assembled` 필드를 두지 않는다. 동일 섹션 입력 → 바이트 동일 출력 | P0 |
| **FR-05** | `tool_guides[].tool_id`가 조회된 도구 집합에 없으면 **폐기**하고 `dropped_tool_ids`에 기록한다 (환각 방어 — `tool_selection` §6.1 #6 관례) | P0 |
| **FR-06** | LLM 호출 실패 / 스키마 위반 / 빈 결과 시 **200 + `degraded=true`** + 규칙기반 폴백 프롬프트를 반환한다. 폴백도 정상적으로 저장된다 | P0 |
| **FR-07** | 성공·degraded 무관하게 `prompt_session` + `prompt_version`에 저장한다. `version_no`는 세션 내 1부터 증가 | P0 |
| **FR-08** | 요청에 `session_id`가 있으면 **새 세션을 만들지 않고** 해당 세션에 버전을 append 한다 (재생성). 타인 세션이면 404 | P0 |
| **FR-09** | `GET /api/v1/prompt-composer/sessions/{session_id}` — 세션 메타 + 버전 목록(최신순) 반환. 본인 세션만 | P1 |
| **FR-10** | `PATCH /api/v1/prompt-composer/sessions/{session_id}` — `agent_id` 바인딩(백필). 이미 바인딩된 세션이면 409 | P1 |
| **FR-11** | 모든 엔드포인트 인증 필수(`get_current_user`). 조회/수정은 `user_id` 일치 검사 | P0 |
| **FR-12** | 입력 검증 — `user_request` 1~1000자, `tool_ids` 최대 50개, `history` 최대 20턴(초과분 최신 우선 절단), `intent.label` 최대 100자 | P0 |
| **FR-13** | `intent`가 없거나 `intent.degraded=true`면 의도 블록을 프롬프트에 **부착하지 않는다** (오염된 판정으로 프롬프트를 왜곡시키지 않음) | P0 |
| **FR-14** | LangSmith 추적 — 프로젝트 `prompt-composer`, `run_name=prompt:{요청 앞 30자}` (`AgentComposer._build_trace_config` 관례 계승). API 키 없으면 무시 | P2 |

### 3.2 Non-Functional Requirements

| ID | 요구사항 | 목표 |
|----|----------|------|
| **NFR-01** | LLM 호출 횟수 | 요청당 **1회** (재시도 없음 — D6) |
| **NFR-02** | 응답 시간 | p95 8초 이내 (LLM 지배적). 폴백 경로는 200ms 이내 |
| **NFR-03** | 로깅 | 시작/종료/실패 3지점, `request_id`·`tool_count`·`degraded`·`elapsed_ms` 구조화 필드. `print()` 금지 |
| **NFR-04** | 레이어 규칙 | `domain/prompt_composer`는 LangChain·SQLAlchemy·FastAPI를 import 하지 않는다 |
| **NFR-05** | 트랜잭션 | Repository 내부 commit/rollback 금지. UseCase 단일 세션 (`docs/rules/db-session.md`) |
| **NFR-06** | DDL | 테이블 + 전 컬럼 COMMENT 필수 (`tests/db/test_migration_ddl_comments.py` 통과) |
| **NFR-07** | 설정 | `PROMPT_COMPOSER_*` 환경변수 (모델명/temperature/최대 도구 수/타임아웃). 하드코딩 금지 |

### 3.3 데이터 계약 초안

```python
# domain/prompt_composer/schemas.py  (순수 dataclass — 외부 의존 0)

@dataclass(frozen=True)
class ToolMeta:
    tool_id: str
    name: str
    description: str
    source: str            # "internal" | "mcp"
    server_name: str | None = None

@dataclass(frozen=True)
class RoleSection:
    title: str
    detail: str

@dataclass(frozen=True)
class ToolGuide:
    tool_id: str
    when: str              # 언제 사용하는가
    how: str               # 어떤 입력으로 호출하는가
    caution: str = ""      # 주의사항

@dataclass(frozen=True)
class PromptSections:
    purpose: str
    roles: tuple[RoleSection, ...]
    tool_guides: tuple[ToolGuide, ...]
    principles: tuple[str, ...]

@dataclass(frozen=True)
class ComposedPrompt:
    sections: PromptSections
    assembled: str
    degraded: bool = False
    reason: str | None = None
    dropped_tool_ids: tuple[str, ...] = ()
    unknown_tool_ids: tuple[str, ...] = ()
    elapsed_ms: int = 0
```

**조립 규칙 (FR-04, Policy에 고정)** — 빈 섹션은 헤더째 생략한다.

```
{purpose}

[역할]
- {role.title}: {role.detail}

[도구 지침]
- {tool.name} ({tool_id}): {when} / {how}
  주의: {caution}

[동작 원칙]
- {principle}
```

### 3.4 DB 스키마 초안

```sql
-- V061__create_prompt_session.sql
CREATE TABLE prompt_session (
  id            VARCHAR(36)  NOT NULL COMMENT '세션 UUID',
  user_id       VARCHAR(36)  NOT NULL COMMENT '생성 요청 사용자 ID',
  agent_id      VARCHAR(36)  NULL     COMMENT '바인딩된 에이전트 ID. 생성 시점엔 미저장 상태라 NULL 허용(D5)',
  user_request  TEXT         NOT NULL COMMENT '최초 자연어 요청 원문',
  created_at    DATETIME     NOT NULL COMMENT '생성 시각',
  updated_at    DATETIME     NOT NULL COMMENT '수정 시각(agent_id 백필 시 갱신)',
  PRIMARY KEY (id),
  KEY ix_prompt_session_user (user_id, created_at),
  KEY ix_prompt_session_agent (agent_id)
) COMMENT='시스템 프롬프트 생성 세션 — 하나의 요청에서 파생된 버전들의 묶음';

-- V062__create_prompt_version.sql
CREATE TABLE prompt_version (
  id             VARCHAR(36) NOT NULL COMMENT '버전 UUID',
  session_id     VARCHAR(36) NOT NULL COMMENT '소속 prompt_session ID',
  version_no     INT         NOT NULL COMMENT '세션 내 버전 번호(1부터 증가)',
  sections       JSON        NOT NULL COMMENT '구조화 섹션 {purpose, roles, tool_guides, principles}',
  assembled      TEXT        NOT NULL COMMENT '서버가 결정적으로 조립한 최종 프롬프트 문자열',
  intent_snapshot JSON       NULL     COMMENT '생성에 사용된 IntentResult 스냅샷. 미주입/degraded면 NULL',
  tool_ids       JSON        NOT NULL COMMENT '생성에 실제 반영된 tool_id 배열',
  degraded       TINYINT(1)  NOT NULL COMMENT 'LLM 실패로 규칙기반 폴백이 쓰였는지 여부',
  reason         VARCHAR(500) NULL    COMMENT 'degraded 사유 또는 관측 메모',
  created_at     DATETIME    NOT NULL COMMENT '생성 시각',
  PRIMARY KEY (id),
  UNIQUE KEY uq_session_version (session_id, version_no),
  CONSTRAINT fk_prompt_version_session FOREIGN KEY (session_id)
    REFERENCES prompt_session(id) ON DELETE CASCADE
) COMMENT='시스템 프롬프트 버전 이력 — 생성 1회당 1행, 근거(의도/도구) 동봉';
```

> `agent_id`에 FK를 걸지 않는다 — 에이전트 삭제가 이력 삭제로 전이되면 "왜 이 프롬프트가 나왔는가"의 기록이 사라진다. 정합성은 백필 API(FR-10)에서 존재 검증으로 확보한다.

---

## 4. Success Criteria

| # | 기준 | 측정 방법 |
|---|------|-----------|
| SC-01 | 기존 경로 회귀 0건 | `agent_composer`·`general_chat`·`intent` 기존 테스트 전량 통과 |
| SC-02 | LLM 실패 3종(예외 / 스키마 위반 / 빈 결과) 모두 200 + `degraded=true` + 비어 있지 않은 `assembled` | `tests/infrastructure/prompt_composer/test_adapter.py` 3케이스 |
| SC-03 | 조립 결정성 — 동일 `PromptSections` → 바이트 동일 `assembled` | Policy 단위 테스트(반복 호출 동일성 + 빈 섹션 생략) |
| SC-04 | 환각 도구 폐기 — 후보에 없는 `tool_id`가 `tool_guides`에 오면 `dropped_tool_ids`로 이동 | UseCase 테스트 |
| SC-05 | 레이어 위반 0건 | `/verify-architecture` — `domain/prompt_composer`에 langchain/sqlalchemy/fastapi import 0 |
| SC-06 | DDL COMMENT 100% | `tests/db/test_migration_ddl_comments.py` 통과 (V061/V062) |
| SC-07 | 세션 격리 | 타인 `session_id` 조회/PATCH 시 404 (403 아님 — 존재 노출 방지) |
| SC-08 | 버전 append — 같은 `session_id`로 3회 호출 시 `version_no` 1,2,3 | API 통합 테스트 |
| SC-09 | 테스트 커버리지 | 신규 모듈 4계층 모두 테스트 존재 (`/verify-tdd`) |

---

## 5. Risks and Mitigation

| ID | 리스크 | 영향 | 확률 | 완화 |
|----|--------|:----:|:----:|------|
| **R1** | `AgentComposer`와 프롬프트 규칙 **2벌 공존** → 시간이 지나며 산출물 품질/포맷이 벌어진다 | 高 | 高 | 프롬프트 템플릿에 "이 모듈은 `agent_composer/composer.py:_SYSTEM_PROMPT`의 섹션 규칙(목적/역할/도구지침/동작원칙)을 **구조화 형태로 계승**한다"를 주석으로 명시. Design 단계에서 두 템플릿의 섹션 대조표 작성. 통합/제거는 배선 사이클에서 결정 |
| **R2** | 배선 없이 출하 → **실사용 검증 0**인 채로 코드만 늘어난다 | 中 | 高 | 실 LLM 호출 테스트를 `@pytest.mark.real_llm`로 1건 작성(기본 제외, 수동 실행). 다음 사이클 배선을 Next Steps에 명시적으로 예약 |
| **R3** | `agent_id=NULL` **고아 세션 누적** — 저장까지 안 간 초안이 계속 쌓인다 | 中 | 中 | 이번 스코프는 인덱스만. 정리는 `background_job` 기반 TTL 잡으로 다음 사이클 (지금 만들면 YAGNI) |
| **R4** | `degraded` 폴백 프롬프트가 **조용히 저품질**로 나가 사용자가 그대로 저장한다 | 中 | 中 | 응답·DB 양쪽에 `degraded` 플래그 + `reason` 저장. 로그 `warning` 레벨. UI 경고는 배선 사이클 책임으로 이월 |
| **R5** | `intent` 주입이 선택이라 대부분 **없이 호출**되어 의도 분석 모듈이 여전히 미사용으로 남는다 | 低 | 中 | FR-13대로 없어도 정상 동작. 다음 사이클 배선 시 호출자가 2단 호출하도록 설계 (Next Steps N2) |
| **R6** | JSON 컬럼(`sections`)이라 **스키마 변경 시 과거 버전 파싱 실패** | 中 | 低 | 역직렬화에 관대한 파싱(누락 키는 기본값). 파싱 실패 시 예외 대신 `assembled`만 반환 |
| **R7** | `tool_ids` 50개 상한을 넘는 요청에서 프롬프트가 비대해져 토큰 초과 | 低 | 低 | FR-12 상한 + `PROMPT_COMPOSER_MAX_TOOLS` 설정. 초과분 절단 시 `warning` 로그 (`build_candidates_block` 관례 동일) |

---

## 6. Impact Analysis

### 6.1 신규 파일

```
idt/src/
├── domain/prompt_composer/
│   ├── schemas.py            # VO (§3.3)
│   ├── policies.py           # 조립 규칙 + 환각 폐기 + 절단
│   └── interfaces.py         # PromptGeneratorPort, PromptRepositoryPort, ToolMetaReaderPort
├── application/prompt_composer/
│   └── compose_prompt_use_case.py
├── infrastructure/prompt_composer/
│   ├── adapter.py            # LLM structured output + degraded 흡수
│   ├── prompts.py            # 템플릿
│   ├── models.py             # PromptSessionModel, PromptVersionModel
│   └── repository.py
├── interfaces/schemas/prompt_composer.py
├── api/routes/prompt_composer_router.py
└── infrastructure/config/prompt_composer_config.py
idt/db/migration/V061__create_prompt_session.sql
idt/db/migration/V062__create_prompt_version.sql
```

### 6.2 수정 파일

| 파일 | 변경 | 위험 |
|------|------|:----:|
| `src/api/main.py` | DI 조립 + 라우터 등록. **조립 실패 시 라우터 미등록**으로 낙하 (`tool_selection` 관례 계승) | 低 |
| `src/config.py` | `PROMPT_COMPOSER_*` 5종 추가 | 低 |
| 모델 등록 지점 (`persistence/models` 임포트 집합) | 신규 모델 2종 등록 | 低 — 누락 시 테이블 미생성으로 즉시 드러남 |

### 6.3 무영향 확인

- `agent_composer` / `general_chat` / `intent` / `tool_selection` — **코드 변경 0**
- 프론트엔드 — **변경 0** (API 계약 신설이지만 소비자 없음 → `api-contract-sync` 대상 아님)
- 기존 테이블 — **DDL 변경 0** (신규 2테이블만)

---

## 7. Architecture Considerations

### 7.1 레이어 배치

| Layer | 구성요소 | 금지사항 준수 |
|-------|----------|---------------|
| **domain** | VO, 조립 Policy, 3개 포트 | LangChain/SQLAlchemy/FastAPI import 0 |
| **application** | `ComposePromptUseCase` — 도구메타 조회 → 생성 → 조립 → 저장 순서 제어 | 조립 규칙 자체는 Policy에 위임 (흐름만 제어) |
| **infrastructure** | LLM 어댑터, ORM 모델, Repository | 비즈니스 규칙 미포함. Repository 내 commit 금지 |
| **interfaces** | 라우터, 요청/응답 스키마 | 로직 0 — UseCase 위임만 (`intent_router.py` 관례) |

### 7.2 포트 3개로 나누는 이유

`ToolMetaReaderPort`를 별도로 두는 것은 UseCase가 `tool_catalog` 인프라를 직접 알지 않게 하기 위함이며, 동시에 **도구 메타 출처를 나중에 바꿔도**(카탈로그 → MCP 실시간 조회, O5) UseCase가 무변경으로 남는다.

### 7.3 참조 관례

| 항목 | 따를 선례 |
|------|-----------|
| degraded 계약 + 어댑터가 모든 실패 흡수 | `infrastructure/intent/adapter.py`, `api/routes/intent_router.py` |
| 환각 ID 폐기 + 관측 필드 | `domain/tool_selection/schemas.py:SelectionResult` |
| 후보 블록 생성 + 상한 절단 경고 | `application/agent_composer/composer.py:build_candidates_block` |
| LangSmith 추적 config | `AgentComposer._build_trace_config` |
| DI 조립 실패 시 낙하 | `tool_selection` 배선 (`main.py`) |

### 7.4 미해결 — Design 단계에서 결정할 것

| # | 쟁점 | 후보 |
|---|------|------|
| Q1 | `roles[]`를 LLM이 자유 생성 vs 도구 개수에 종속 | Design §2에서 3안 비교 |
| Q2 | `assembled` 조립을 domain Policy vs application 어느 쪽에 둘지 | Policy(순수 함수) 유력 — SC-03 테스트 용이성 |
| Q3 | `history` 절단 정책을 `ComposePolicy.clamp_history` 재사용 vs 자체 구현 | 재사용 시 `agent_composer` 의존 발생 → 복제가 나을 수 있음 |
| Q4 | `prompt_version.sections` JSON 스키마 버전 필드(`schema_version`) 선반영 여부 | R6 완화 목적. 넣으면 컬럼 1개 추가 |

---

## 8. Convention Prerequisites

| 규칙 | 문서 | 이번 기능의 적용점 |
|------|------|-------------------|
| DB 세션·트랜잭션 | `idt/docs/rules/db-session.md` | UseCase 단일 세션, Repository commit 금지, `get_session_factory()()` 직접 호출 금지 |
| 로깅·에러 추적 | `idt/docs/rules/logging.md` | 어댑터 3지점 구조화 로그, 스택 트레이스 필수, `print()` 금지 |
| 도구 & MCP | `idt/docs/rules/tool-and-mcp.md` | `tool_id` 표기 규약(`internal:` / `mcp:{server_id}:{tool_name}`) 준수 |
| 테스트·작업 절차 | `idt/docs/rules/testing.md` | TDD — 테스트 먼저, Red 확인 후 구현 |
| DDL COMMENT | `idt/CLAUDE.md` §3 | V061/V062 테이블 + 전 컬럼 COMMENT, SQLAlchemy 모델에 `comment=` 동일 반영 |
| 함수 길이/중첩 | `idt/CLAUDE.md` §3 | 40줄 초과 금지, if 2단 초과 금지 — 조립 함수가 위험 지점 |

---

## 9. Next Steps

### 9.1 이번 사이클

1. `/pdca design prompt-composer` — Q1~Q4 결정 + 3안 아키텍처 비교 + 모듈 맵
2. `/pdca do prompt-composer --scope module-1` (domain + 조립 Policy, TDD)
3. `--scope module-2` (infrastructure: 어댑터 + 모델 + Repository + 마이그레이션)
4. `--scope module-3` (application + API + DI 배선 + 통합 테스트)
5. `/pdca analyze` → `/pdca report`

### 9.2 다음 사이클 예약 (스코프 밖, 명시적 이월)

| ID | 항목 | 선행 조건 |
|----|------|-----------|
| **N1** | 진입 화면/Fix 탭 UI 배선 + `degraded` 경고 표시 (R4) | 본 사이클 완료 |
| **N2** | `intent` → `prompt-composer` 2단 호출 배선 (R5) | 에이전트 빌더용 의도 라벨 세트 정의 |
| **N3** | 섹션 단위 재생성 API (O6) | 본 사이클의 구조화 저장 |
| **N4** | 고아 세션 TTL 정리 잡 (R3) | 실제 누적량 관측 |
| **N5** | `AgentComposer` 프롬프트 생성 통합/제거 판단 (R1) | N1 이후 품질 비교 데이터 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-14 | 초안 — D1~D7 확정(병렬 신규 경로 / 의도 주입 / tool_ids 지정 / 구조화+서버조립 / 세션·버전 2테이블 / degraded 폴백 / 배선 없음) | 배상규 |
