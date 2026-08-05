# Builtin Middleware Planning Document

> **Summary**: 메인 에이전트(커스텀 에이전트 워커 + General Chat)에 **빌트인 미들웨어** 개념을 도입한다.
> LLM 호출 실패 시 지수 백오프 자동 재시도 같은 횡단 관심사를 미들웨어 카탈로그로 선언하고,
> 관리자는 미들웨어별 **빌트인(기본 적용) / 강제(enforced)** 를 토글하며, 사용자는 에이전트
> 생성/수정 시 빌트인을 끼고 뺄 수 있다(강제는 해제 불가 — 런타임에 끼어들어 적용).
> 기술적으로는 langchain v1 `create_agent` + 공식 미들웨어 스택으로 전환하되(A안),
> 커스텀 구현(B안)으로 갈아탈 수 있도록 미들웨어 생성을 빌더 추상화 뒤에 격리한다.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-04
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 네트워크 불안정·모델 장애·무한 루프 같은 실행 안정성 문제를 지금은 에이전트가 스스로 방어하지 못한다. LLM 호출이 한 번 실패하면 그대로 사용자 에러가 되고, 재시도·폴백·호출 상한 같은 안전장치를 넣을 자리(미들웨어 계층)가 메인 에이전트 경로(create_react_agent)에 아예 없다. 이전에 만든 v2 미들웨어 에이전트(`/api/v2/agents`)는 langchain v1 미설치로 동작 불가한 실험 경로로 방치되어 있다 |
| **Solution** | ① langchain v1 설치 + 워커/General Chat 에이전트 생성을 `create_agent(middleware=[...])`로 전환 — 단, 미들웨어 인스턴스화는 `MiddlewareBuilder` 추상화 뒤에 격리해 커스텀 구현(B안) 전환 용이성 확보 ② `middleware_catalog` 테이블(V056) 신설 — 미들웨어 4종(LLM 재시도·도구 재시도·모델 폴백·호출 상한)을 시드하고 관리자가 `is_builtin`(기본 적용)·`is_enforced`(강제) 2단계 토글 ③ 에이전트 생성 시 빌트인 스냅샷 주입(+수동 opt-out, builtin-tools 계약 대칭), 실행 시 enforced 미들웨어 강제 병합 |
| **Function/UX Effect** | 신규 에이전트는 만들자마자 지수 백오프 재시도 등 안정성 미들웨어가 기본 탑재. 생성 폼에 미들웨어 섹션이 생겨 "기본" 배지와 함께 끼고 뺄 수 있고, 강제 미들웨어는 잠금 표시로 항상 적용됨을 안내. 관리자는 미들웨어 관리 화면에서 빌트인/강제/기본 설정값을 코드 배포 없이 조정 |
| **Core Value** | 실행 안정성(재시도·폴백·상한)을 "플랫폼 표준"으로 데이터화하는 확장점 — builtin-tools(V054)의 도구 축을 미들웨어 축으로 일반화. 이후 요약·PII 등 신규 미들웨어도 카탈로그 등록만으로 전 에이전트에 보급 가능하며, deprecated인 create_react_agent에서 langchain v1 표준 경로로의 기술 부채 해소를 겸한다 |

---

## 1. Overview

### 1.1 Purpose

메인 에이전트 실행 경로에 미들웨어 계층을 도입하고, 어떤 미들웨어를 기본/강제로
적용할지를 **관리자가 화면에서 제어**, 사용자는 에이전트 단위로 **빌트인을 끼고 뺄 수**
있게 한다. 1차 미들웨어는 실행 안정성 4종:

| middleware_type | 기능 | langchain v1 매핑 |
|---|---|---|
| `model_retry` | LLM 호출 실패 시 지수 백오프 자동 재시도 (네트워크 불안정 대응) | `ModelRetryMiddleware` |
| `tool_retry` | 도구(내부/MCP) 호출 실패 시 백오프 재시도 | `ToolRetryMiddleware` |
| `model_fallback` | 주 모델 실패 시 대체 모델 자동 전환 | `ModelFallbackMiddleware` |
| `model_call_limit` | run당 LLM 호출 횟수 상한 (무한 루프/비용 폭주 방어) | `ModelCallLimitMiddleware` (run_limit만, thread_limit은 checkpointer 필요라 제외) |

### 1.2 Background — 현행 구조 (2026-08-04 조사)

- **메인 에이전트**: `WorkflowCompiler`(`src/application/agent_builder/workflow_compiler.py`)가
  워커를 `langgraph.prebuilt.create_react_agent`로 생성 — **미들웨어 파라미터가 없다**.
  supervisor 노드는 자체 구현(`create_supervisor_node`), search 워커는 별도 파이프라인 노드.
- **General Chat**: `src/application/general_chat/use_case.py`의 `_create_agent`도
  `create_react_agent(llm, tools, prompt)` — 동일하게 미들웨어 불가.
- **v2 실험 경로**: `/api/v2/agents`(`middleware_agent` 모듈)가 `langchain.agents.create_agent`
  + 미들웨어 5종 구조로 이미 존재하나, **`.venv`에 `langchain` v1 패키지 미설치**로 import가
  None 폴백되어 런타임 동작 불가. 도메인 스키마(`MiddlewareType`/`MiddlewareConfig`)와
  `MiddlewareBuilder` 패턴은 본 기능의 설계 자산으로 재사용 가능.
- **설치 현황**: langchain-core 1.2.26 / langgraph 1.1.6 / langgraph-prebuilt 1.0.9 —
  langchain v1과 호환 기반은 갖춰졌고 메타 패키지만 없음. `create_react_agent`는
  langgraph v1에서 deprecated(공식 후속 = langchain `create_agent`).
- **선례 (builtin-tools, V054)**: `tool_catalog.is_builtin` 관리자 토글 + 생성 시
  스냅샷 주입 + `exclude_builtin_tool_ids` 수동 opt-out — 본 기능의 제어 모델 원형.

### 1.3 사용자 결정 사항 (2026-08-04 인터뷰)

| 질문 | 결정 |
|------|------|
| 기술 경로 | **A안(langchain v1 + create_agent 전환)하되 B안(커스텀 계층) 전환이 용이하도록** — langchain 클래스 의존을 MiddlewareBuilder 내부로 격리, 도메인/카탈로그/API는 방식 중립 |
| 1차 미들웨어 | **LLM 재시도(지수 백오프) + 도구 재시도 + 모델 폴백 + 모델 호출 상한** 4종 전부 |
| 제어 모델 | **2단계: `is_builtin`(생성 시 기본 적용, 사용자 해제 가능) + `is_enforced`(강제 — 사용자가 빼도 런타임에 끼어들어 적용)** |
| 적용 범위 | **커스텀 에이전트 + General Chat 모두** (General Chat은 에이전트 정의가 없으므로 카탈로그의 빌트인+강제를 그대로 적용, 사용자 제어 없음) |

### 1.4 Related Documents

- `docs/wiki/_INDEX.md` — 에이전트 빌더/실행 경로 승인 문서 우선 참조
- `src/claude/task/task-middleware-agent-builder.md` — v2 실험 경로 설계 (재사용 참조)
- 선례 plan: `docs/archive/2026-08/builtin-tools/builtin-tools.plan.md` (제어 모델 원형)
- 메모리 선례: 독립 opt-in 필드 선호, 워커 산출물=AIMessage(name) 1건 규약
  (worker-toolmessage-leak-fix — create_agent 전환 시 보존 필수)

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. 의존성**: `pyproject.toml`에 `langchain>=1.0` 추가 + 설치 검증
      (langchain-classic 1.0.3과 공존 확인)
- [ ] **S2. 스키마**: `middleware_catalog` 테이블 신설(V056, 전 컬럼 COMMENT) —
      `middleware_type`(unique), `name`, `description`, `is_builtin`, `is_enforced`,
      `default_config`(JSON), `is_active`, `sort_order`. 4종 시드 포함
      (초기값: `model_retry`는 빌트인 on, 나머지는 Design에서 확정)
- [ ] **S3. 에이전트별 스냅샷**: `agent_middleware` 테이블 신설(V056 동봉) —
      agent_id별 적용 미들웨어 스냅샷(middleware_type, config, sort_order).
      builtin-tools의 agent_tool 스냅샷 계약과 대칭
- [ ] **S4. 관리자 API**: 미들웨어 카탈로그 목록 + `is_builtin`/`is_enforced`/
      `default_config` 수정(ADMIN 전용, 비관리자 403)
- [ ] **S5. 생성 시 빌트인 주입**: `CreateAgentUseCase`에서 빌트인 미들웨어를
      `agent_middleware`로 스냅샷 저장. `exclude_builtin_middleware_types`(신규 optional
      필드)로 수동 opt-out — 폼에서만 전달, 채팅 초안 경로는 미사용(LLM 우회 불가,
      builtin-tools D5/FR-05 계약 대칭). 수정(update) 경로도 동일 규약으로 편집 허용
- [ ] **S6. 실행 시 조립**: `WorkflowCompiler` 워커 생성을 `create_react_agent` →
      `create_agent(model, tools, middleware=...)`로 전환. 적용 목록 =
      에이전트 스냅샷 ∪ enforced(카탈로그) — 중복 시 1회만, enforced의 config 우선.
      search 파이프라인 노드·analysis 노드·supervisor는 현행 유지(react 워커만 전환)
- [ ] **S7. General Chat 적용**: `general_chat/use_case.py._create_agent`도 동일 전환 —
      카탈로그의 빌트인+enforced 전부 적용(에이전트 정의 없음), astream_events
      스트리밍 무회귀 검증 포함
- [ ] **S8. 빌더 추상화 (B안 전환 용이성)**: `MiddlewareBuilder`가
      `MiddlewareConfig 목록 → 미들웨어 인스턴스 목록` 변환을 전담 — langchain v1
      클래스 참조는 이 모듈 안에만 존재. 도메인은 `MiddlewareType`/`MiddlewareConfig`만
      알고, 카탈로그/스냅샷/API는 방식 중립. 기존 `middleware_agent` 도메인 스키마
      재사용/이관 여부는 Design에서 확정
- [ ] **S9. 프론트 — 생성/수정 폼**: 미들웨어 섹션 신설 — 빌트인은 "기본" 배지와 함께
      기본 on(해제 시 exclude 전달), enforced는 잠금 표시(해제 불가 안내),
      각 미들웨어의 설정값은 열람만(1차)
- [ ] **S10. 프론트 — 관리자 화면**: 미들웨어 카탈로그 관리(빌트인/강제 토글 +
      기본 설정 편집), 관리자 네비 4그룹 구조에 배치 (api-contract-sync 동기화)
- [ ] **S11. 관측/로깅**: 실행 시 적용된 미들웨어 목록을 구조화 로그로 남김
      (request_id 포함) — 재시도 발생/폴백 전환도 확인 가능하게
- [ ] **S12. 테스트**: TDD — 카탈로그 토글/권한(403)/주입/opt-out/enforced 병합/
      create_agent 전환 무회귀(워커 name 규약 포함) 백엔드 테스트,
      폼 배지·잠금·관리자 토글 프론트 테스트

### 2.2 Out of Scope

- **에이전트별 미들웨어 설정값 오버라이드** — 1차는 on/off만, 설정값은 관리자의
  `default_config` 단일 소스 (사용자별 튜닝은 후속)
- **나머지 미들웨어 유형** — summarization, PII(별도 커스텀 모듈 기존재 —
  pii-masking-integration 후속과 통합 검토), HITL, tool_call_limit, context editing 등은
  카탈로그 확장으로 후속 (본 기능이 그 확장점을 만드는 것)
- **기존 에이전트 소급 적용** — 스냅샷 방식(빌트인은 신규 생성분부터). 단 enforced는
  런타임 병합이므로 기존 에이전트에도 즉시 적용됨(의도된 동작)
- **v2 `/api/v2/agents` 경로의 통합/제거** — 도메인 스키마 재사용만 하고 라우트
  정리는 별도 과제
- **supervisor 노드/search 파이프라인의 미들웨어화** — react 워커와 General Chat만.
  supervisor는 자체 구현이라 create_agent 대상 아님
- **`thread_limit`류 checkpointer 의존 기능** — checkpointer 미도입 상태 유지

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `langchain>=1.0` 설치 후 `from langchain.agents import create_agent` 및 미들웨어 4종 import가 성공한다 (기존 langgraph 경로 무회귀) | High | Pending |
| FR-02 | V056: `middleware_catalog` + `agent_middleware` 테이블 생성, 4종 시드, 전 컬럼 COMMENT | High | Pending |
| FR-03 | 관리자만 미들웨어 `is_builtin`/`is_enforced`/`default_config` 수정 가능 (비관리자 403) | High | Pending |
| FR-04 | 미들웨어 카탈로그 목록 API — 프론트 폼/관리자 화면 공용, `is_builtin`/`is_enforced`/`default_config` 노출 | High | Pending |
| FR-05 | 에이전트 생성 시(모든 경로) 빌트인 미들웨어가 `agent_middleware` 스냅샷으로 저장되고, `exclude_builtin_middleware_types`로 명시 해제한 것만 제외된다 (채팅 초안 경로는 이 필드 미사용) | High | Pending |
| FR-06 | 에이전트 실행 시 워커가 `create_agent(middleware=스냅샷∪enforced)`로 조립된다 — enforced는 스냅샷에 없어도 적용, 중복 적용 없음 | High | Pending |
| FR-07 | 미들웨어 미적용 시(카탈로그 전부 off) 워커 동작이 기존 create_react_agent와 동등하다 — 워커 산출물 "AIMessage(name) 1건" 규약, supervisor 라우팅, 스트리밍 무회귀 | High | Pending |
| FR-08 | General Chat 경로에 카탈로그 빌트인+enforced가 적용되고 astream_events 토큰 스트리밍이 유지된다 | High | Pending |
| FR-09 | `model_retry` 빌트인 상태에서 LLM 호출이 일시 실패하면 지수 백오프로 재시도되어 사용자 에러 없이 응답이 완성된다 (로그로 재시도 확인 가능) | High | Pending |
| FR-10 | 생성/수정 폼: 미들웨어 섹션 — 빌트인 "기본" 배지+기본 on+수동 해제, enforced 잠금 표시, 설정값 열람 | High | Pending |
| FR-11 | 관리자 화면: 카탈로그 목록 + 빌트인/강제 토글 + 기본 설정 편집 (ADMIN에만 노출) | Medium | Pending |
| FR-12 | 실행 로그에 적용 미들웨어 목록·재시도/폴백 이벤트가 request_id와 함께 기록된다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | langchain v1 클래스 의존은 application의 MiddlewareBuilder 내부로 격리 — domain은 타입/VO만, 레이어 이동 없음 | verify-architecture 스킬 |
| 전환 용이성 | B안(커스텀) 전환 시 MiddlewareBuilder 구현 교체만으로 가능 — 카탈로그/스냅샷/API/프론트 무변경 | Design 리뷰 (빌더 인터페이스 계약) |
| TDD | 테스트 선행 (Red → Green), 신규 모듈 테스트 파일 존재 | verify-tdd 스킬 |
| DB | DDL 전 컬럼 COMMENT(V054 이후 자동 검사), FK CHARSET/COLLATE 명시 금지, Repository 내 commit 금지 | tests/db/test_migration_ddl_comments.py + 코드 리뷰 |
| API 계약 | 백엔드 스키마 변경분 프론트 타입/서비스/훅 동기화 | api-contract-sync 체크리스트 |
| 회귀 안전 | create_agent 전환 후 기존 에이전트 실행/General Chat 전 테스트 무회귀 (Windows 격리 실행 관례) | pytest 격리 실행 + vitest --pool=threads |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 관리자가 화면에서 미들웨어별 빌트인/강제를 등록·해제할 수 있다
- [ ] 신규 에이전트를 폼·채팅 어느 경로로 만들어도 빌트인 미들웨어가 적용돼 있다
- [ ] 폼에서 빌트인을 해제하고 만들면 해당 미들웨어가 빠진다 — 단 enforced는 빼도 적용된다
- [ ] General Chat에서도 빌트인+enforced 미들웨어가 동작한다
- [ ] LLM 일시 장애 시나리오에서 지수 백오프 재시도가 로그로 확인되고 사용자 응답이 성공한다
- [ ] 미들웨어 전부 off 상태의 에이전트 실행이 기존과 동등하다 (무회귀 게이트)
- [ ] 비관리자의 토글 시도는 403

### 4.2 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, config 하드코딩 없음 (백오프 기본값도 카탈로그 default_config로)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| create_react_agent → create_agent 전환이 워커 산출물 규약("AIMessage(name) 1건")·supervisor 라우팅·astream_events 스트리밍을 깨뜨림 | High | Medium | FR-07을 독립 무회귀 게이트로 — 미들웨어 0개 상태의 동등성 테스트를 전환 커밋에 선행. `name`/`system_prompt` 파라미터 매핑은 Design에서 create_agent 시그니처 기준 확정 |
| langchain v1 설치가 기존 패키지(langchain-classic 1.0.3, langchain-community 0.4.1)와 충돌 | High | Low | S1에서 별도 커밋으로 설치+전체 테스트 격리 실행 먼저 검증. 충돌 시 B안 폴백 가능(빌더 추상화 덕분에 계획 유지) |
| `ModelCallLimitMiddleware`의 `exit_behavior="end"`가 supervisor-워커 그래프에서 워커만 조기 종료 → supervisor가 재위임 루프를 돌 가능성 | Medium | Medium | Design에서 exit_behavior 선택("end" vs "error")과 supervisor 측 처리(품질 게이트/최대 반복과의 상호작용) 확정 + 시나리오 테스트 |
| `model_fallback` 폴백 모델의 자격증명/등록 부재 시 런타임 실패 | Medium | Medium | default_config의 폴백 모델을 llm_model 등록 모델로 제한(검증), 미검증 모델은 토글 시 400. MCP 빌트인 안전장치(builtin-tools FR-07)와 동일하게 조립 실패 시 해당 미들웨어만 제외+경고 로그 |
| enforced 런타임 병합과 스냅샷 중복 → 같은 미들웨어 2회 적용(재시도 횟수 곱연산 등) | Medium | High (설계 누락 시 확정) | FR-06에 중복 제거 명시 — middleware_type 기준 dedupe, enforced의 config 우선. 병합 단위 테스트 필수 |
| 미들웨어가 매 요청 조립되어 카탈로그 DB 조회가 실행 핫패스에 추가됨 | Low | Medium | 카탈로그는 행 수 ~수십 — 요청당 1회 조회 수용. 병목 시 wiki-tree-performance 선례(DI 싱글턴 캐시) 적용 여지를 Design에 명시 |
| v2 middleware_agent 모듈과 신규 모듈의 개념 중복으로 유지보수 혼선 | Low | High | 도메인 스키마는 재사용/이관하고 v2 경로는 명시적으로 "실험 경로, 후속 정리" 주석 — 정리 자체는 out of scope |
| General Chat은 에이전트 정의가 없어 사용자 opt-out 불가 — "왜 못 빼냐" 혼선 | Low | Low | 의도된 동작(플랫폼 기본기) — 관리자 화면 설명문구로 안내 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| Starter | Simple structure | ☐ |
| Dynamic | Feature-based modules | ☐ |
| **Enterprise** | 기존 프로젝트 구조 (Thin DDD) | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 기술 경로 | A. langchain v1 create_agent / B. 커스텀 래핑(with_retry 등) / A+B 단계 | **A + B 전환 용이 설계** (사용자 결정) | 공식 미들웨어 4종을 재구현 없이 확보 + create_react_agent deprecated 부채 해소. langchain 의존을 MiddlewareBuilder에 격리해 B 폴백/전환 시 빌더 교체만으로 대응 |
| 제어 SoT | 코드 상수 / **DB 카탈로그** / 에이전트 정의만 | **`middleware_catalog` 테이블** | 관리자가 배포 없이 토글 — tool_catalog.is_builtin 선례. enforced 판단도 런타임 조회라 DB가 유일한 공통 지점 |
| 빌트인 적용 시점 | 실행 시 동적 / **생성 시 스냅샷** | **생성 시 스냅샷 (builtin-tools 대칭)** | 에이전트 정의 자기완결성 + 사용자 opt-out이 정의에 기록됨. 카탈로그 변경이 기존 에이전트를 소리 없이 바꾸지 않음 |
| 강제(enforced) 적용 시점 | 스냅샷 / **실행 시 병합** | **실행 시 병합** | "사용자가 빼도 끼어들어 강제"의 기술적 구현 — 스냅샷과 무관하게 조립 시 주입, 관리자 변경이 즉시 전 에이전트 반영 |
| opt-out 채널 | 없음 / **exclude 요청 필드** / 사후 수정만 | **`exclude_builtin_middleware_types`** | builtin-tools의 exclude_builtin_tool_ids와 동일 계약 — 폼만 이 필드를 만들 수 있어 채팅 초안 LLM이 구조적으로 우회 불가 |
| 설정값 소유 | 사용자별 / **관리자 default_config** | **관리자 단일 소스 (1차)** | YAGNI — 사용자는 on/off + 열람만. 오버라이드는 스냅샷 config 컬럼을 이미 확보해 후속 확장 여지 유지 |
| 적용 노드 범위 | 전 노드 / **react 워커 + General Chat** | **react 워커 + General Chat** | supervisor·search 파이프라인·analysis는 자체 구현 노드라 create_agent 비대상 — 무리한 일반화 대신 실효 지점만 |

### 6.3 변경 대상 파일 (예상)

```
idt/
├── pyproject.toml                                          # S1 langchain>=1.0
├── db/migration/V056__create_middleware_catalog.sql        # S2/S3 (2테이블+시드)
├── src/domain/middleware/ (신규 또는 middleware_agent 이관)
│   ├── entities.py          # MiddlewareCatalogEntry, MiddlewareType, MiddlewareConfig
│   └── interfaces.py        # MiddlewareCatalogRepositoryInterface
├── src/infrastructure/middleware/
│   ├── models.py            # middleware_catalog, agent_middleware ORM
│   └── repository.py
├── src/application/middleware/
│   ├── list_middleware_catalog_use_case.py                 # S4/FR-04
│   ├── set_middleware_flags_use_case.py                    # S4/FR-03 (builtin/enforced/config)
│   └── middleware_builder.py                               # S8 (v2 빌더 이관·확장, langchain 격리)
├── src/application/agent_builder/
│   ├── schemas.py           # exclude_builtin_middleware_types
│   ├── create_agent_use_case.py                            # S5 스냅샷 주입
│   └── workflow_compiler.py                                # S6 create_agent 전환+병합
├── src/application/general_chat/use_case.py                # S7
├── src/api/routes/ + main.py                               # S4 라우터+DI (ADMIN 가드)
└── tests/ (domain/application/api/db)                      # S12

idt_front/
├── src/types + services + hooks (middleware catalog)       # FR-04 동기화
├── 에이전트 생성/수정 폼 — 미들웨어 섹션                    # S9 배지·잠금·exclude
└── 관리자 미들웨어 관리 화면                                # S10 토글+설정 편집
```

---

## 7. Convention Prerequisites

- [x] 검증 스킬: verify-architecture, verify-tdd, api-contract-sync
- [x] DDL COMMENT 필수(자동 검사 대상) / FK CHARSET·COLLATE 명시 금지 관례
- [x] 워커 산출물 = AIMessage(name) 1건 규약 (worker-toolmessage-leak-fix) — 전환 시 보존
- [x] idt 서버는 .venv 인터프리터로 기동 (idt-server-must-run-on-venv)
- 배포 시 **V056 적용 + langchain v1 설치 필수** (미적용 시 카탈로그 조회/조립 실패)

---

## 8. Implementation Guide

### 8.1 구현 순서

```
1. S1/FR-01   langchain v1 설치 검증 커밋 (import 스모크 + 전체 테스트 격리 실행 무회귀)
2. FR-07      create_agent 전환 무회귀 게이트 — 미들웨어 0개 동등성 테스트(Red 불가 항목은
              특성 테스트로 현행 고정) → 워커/General Chat 전환
3. S2~S3/FR-02 V056 + 도메인/인프라 (테스트 선행)
4. S4/FR-03~04 카탈로그 목록·토글 UseCase + 라우터(ADMIN 가드)
5. S5/FR-05   생성 시 빌트인 스냅샷 + exclude opt-out
6. S6~S7/FR-06,08~09 실행 시 병합 조립 + General Chat + 재시도 시나리오
7. S9~S10     프론트 — 타입 동기화 → 폼 섹션 → 관리자 화면
8. S11~S12    관측 로깅 + 회귀 (pytest 격리 + vitest --pool=threads)
```

### 8.2 검증 시나리오 (수동 E2E — 이월 가능)

- 관리자로 `model_retry` 빌트인 등록 → 신규 에이전트 생성 → LLM 일시 장애(잘못된
  base_url 등) 유도 → 재시도 로그 확인 → 폼에서 해제 후 생성하면 미적용 확인
- `model_call_limit` enforced 등록 → 빌트인 해제한 에이전트에서도 상한 동작 확인
- General Chat에서 빌트인 미들웨어 적용 + 토큰 스트리밍 정상 확인
- 미들웨어 전부 off → 기존 에이전트 실행 체감 동일 확인

---

## 9. Next Steps

1. [ ] Write design document (`/pdca design builtin-middleware`) — create_agent 시그니처
       매핑(name/system_prompt), exit_behavior×supervisor 상호작용, v2 도메인 스키마
       이관 범위, 시드 초기값(4종 중 기본 on 대상), 폴백 모델 검증 규칙 확정
2. [ ] 구현 (TDD)
3. [ ] Gap 분석 (`/pdca analyze builtin-middleware`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-04 | Initial draft — 기술 경로(A+B 전환 용이)·1차 4종·2단계 제어(builtin/enforced)·범위(커스텀+General Chat) 사용자 인터뷰 반영 | 배상규 |
