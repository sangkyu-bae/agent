# agent-token-limit Planning Document

> **Summary**: supervisor 그래프의 토큰 한도(`token_limit`)가 코드 기본값 8000 하나로 모든 에이전트에 고정되어 있어, 긴 수집 결과 한 번에 후속 워커(분석·문서 생성)가 실행되지 못한 채 조기 종료된다. 이 값을 **에이전트별 DB 설정**(기본 50000, 범위 8000~500000)으로 옮기고, 생성/수정 API와 Studio 설정 패널에 노출하며, 한도 도달 시 동작을 반복 한도(`max_iterations`)와 **동일하게 통일**(final_answer 경유 안내 답변 + payload 플래그)한다. 서브 에이전트는 부모 값 절반 상속을 버리고 **자기 DB 값**을 쓴다.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front Studio)
> **Author**: 배상규
> **Date**: 2026-11-05
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `SupervisorConfig.token_limit`은 `src/domain/agent_builder/schemas.py:19`의 기본값 8000이 유일한 출처다. `run_agent_use_case.py:985`·`:1363`은 `max_iterations`만 에이전트에서 넘기고 `token_limit`은 생략하므로 모든 에이전트가 8000을 쓴다. 집계는 워커 산출 글자 수 ÷ 4 추정치라 스크랩 워커 1회(약 3만 5천 자)로 8869가 되어 두 번째 supervisor 진입 즉시 토큰 가드(`supervisor_nodes.py:451`)가 걸렸다(LangSmith 런 01a1a939, 2026-11-05). 이 가드는 `limit_reached`를 세우지 않아 final_answer에 "한도 도달" 안내가 없고, 워커 미실행이면 답변 없이 END로 간다. |
| **Solution** | `agent_definition.token_limit INT NOT NULL DEFAULT 50000` 컬럼(V085)을 추가하고 도메인 `TokenLimitPolicy`(DEFAULT 50000, MIN 8000, MAX 500000)로 검증한다. 생성/수정/조회/포크 경로와 Studio 설정 패널(`SettingsPanel`)에 `max_iterations`와 같은 패턴으로 노출한다. 실행 시 `SupervisorConfig(max_iterations=…, token_limit=agent.token_limit)`로 주입하고, 토큰 가드도 `limit_reached=True`와 도달 사유(iteration/token)를 세워 final_answer 안내·`ANSWER_COMPLETED` 플래그를 반복 한도와 공유한다. 서브 에이전트는 컴파일 시 이미 조회한 자기 정의의 `token_limit`을 쓴다. 집계 방식(글자 수 ÷ 4)은 이번 사이클에서 바꾸지 않는다. |
| **Function/UX Effect** | 에이전트 제작자: 설정 탭에서 반복 한도 옆에 토큰 한도를 입력·저장한다(미설정 50000). 최종 사용자: 수집→분석→문서 생성 3~4 워커 체인이 기본값 안에서 완주하고, 한도에 걸린 경우 "토큰 한도 도달, 지금까지 정보로 답변"을 받는다. 프론트: 기존 `limit_reached` 플래그에 사유가 더해져 배지 문구를 구분할 수 있다. |
| **Core Value** | 반복 한도와 토큰 한도가 **같은 단일 소스(agent_definition)·같은 종료 경로**를 갖게 되어 에이전트별 실행 예산이 예측 가능해진다. 비용 상한은 유지하되 한 번의 긴 수집이 전체 작업을 무효화하는 결함을 제거한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 토큰 한도가 코드 상수 8000으로 전 에이전트 고정이라 긴 수집 1회로 후속 워커가 실행되지 못하고, 한도 종료 사실도 사용자에게 전달되지 않는다. |
| **WHO** | P2 KB 운영자/에이전트 소유자(설정), 최종 사용자(완주된 답변 또는 한도 안내). |
| **RISK** | 기본값 상향으로 LLM 비용 상한이 느슨해진다 → 반복 한도가 2차 상한으로 남고, 범위 상한 500000으로 캡. 토큰 가드가 `limit_reached`를 세우면서 되물음 루프 회귀 가능 → 기존 Gap-06 테스트 유지·확장. |
| **SUCCESS** | 2026-11-05 재현 런(스크랩→분석→발표자료)이 기본값으로 완주. 에이전트별 값이 API·UI 왕복 보존. 토큰 한도 도달 시 final_answer 안내와 `limit_reached` 플래그가 반복 한도와 동일하게 나간다. 기존 회귀 테스트 전부 통과. |
| **SCOPE** | DB(V085)+도메인 정책 → 유스케이스/API 스키마 → 실행 경로(루트·서브·재개) → 프론트 타입/설정 패널. 집계 방식 변경·서브 에이전트 상속 규칙 복원은 범위 밖. |

---

## 1. Overview

### 1.1 Purpose

supervisor 그래프의 토큰 한도를 `agent_definition.token_limit` 단일 소스로 옮기고, 한도 도달을 반복 한도와 같은 "조기 답변" 경로로 처리한다.

```
현재:  SupervisorConfig.token_limit = 8000 (코드 상수, 전 에이전트 공통)
         └─ token_usage(글자수÷4 누적) >= 8000 → next_worker="__end__" (limit_reached 없음)
              ├─ 워커 실행 이력 있음 → final_answer (한도 안내 없음)
              └─ 워커 미실행         → END (답변 없음)

목표:  agent_definition.token_limit (기본 50000, 8000~500000)
         ├─▶ SupervisorConfig.token_limit → state 가드
         │      └─ 도달 시: limit_reached=True + 사유(token) → final_answer 안내 → payload 플래그
         ├─▶ 서브 에이전트: 자기 정의의 token_limit (부모 절반 상속 폐기)
         └─▶ 생성/수정/조회/포크 API + Studio 설정 패널
```

### 1.2 Background — 현재 구조 (2026-11-05 코드 확인)

**설정 경로 부재**
- `SupervisorConfig.token_limit: int = 8000` (`src/domain/agent_builder/schemas.py:19`).
- `run_agent_use_case.py:985`(대화 실행)·`:1363`(승인 재개) 모두 `SupervisorConfig(max_iterations=agent.max_iterations)` — `token_limit` 미전달.
- `supervisor_nodes.py:340`에서 `config.token_limit`을 초기 state에 주입. DB 컬럼·API 필드·환경변수·화면 모두 없음.

**집계 방식**
- 워커/노드가 산출 텍스트 길이 ÷ 4를 `token_usage`에 더한다 (`workflow_compiler.py:1830, 2009, 2098, 2218, 2332, 2441, 2675, 2804, 2965` 9곳). LLM 입력·내부 react 루프 토큰은 세지 않는다. **이번 사이클은 집계 방식을 유지한다**(사용자 결정).

**한도 도달 동작의 비대칭**
- 반복 한도 가드(`supervisor_nodes.py:437-449`): `limit_reached=True` → `route_to_worker_or_final`이 워커 미실행이어도 final_answer로 우회 → final_answer가 "[반복 한도 도달 안내]" 블록 삽입(`workflow_compiler.py:1774-1779`) → `run_agent_use_case.py:1497`이 latch → `ANSWER_COMPLETED.limit_reached`.
- 토큰 한도 가드(`:451-461`): `next_worker="__end__"`만 반환. 주석에 "D5 결정에 따라 limit_reached를 세우지 않는다(테스트로 고정)"고 명시 — supervisor-early-finish-fix Gap-06의 무한 루프 방지는 `_challenge_reset()`으로 이미 해결되어 있으므로 플래그를 세워도 되물음 루프는 재발하지 않는다(Design에서 테스트로 확정).

**서브 에이전트**
- `_wrap_sub_agent`가 `SupervisorConfig(max_iterations=sub_limit, token_limit=state["token_limit"] // 2)`로 서브 그래프 초기 state를 만든다 (`workflow_compiler.py:2935-2938`). 서브 정의는 컴파일 시 `self._agent_repository.find_by_id(ref_id)`로 이미 조회된다(`:1426`) — 독립 값을 넘길 수 있다.

**선례: agent-recursion-limit (2026-07, archive)**
- V045 `max_iterations INT NOT NULL DEFAULT 25`, `IterationLimitPolicy`(DEFAULT/MIN/MAX/validate), 도메인 `__post_init__` 검증, 생성/수정/조회/포크/자동포크 유스케이스, 앱 스키마 `Field(25, ge=10, le=1000)`, 프론트 `types/agentBuilder.ts`·`constants/agentSettings.MAX_ITERATIONS`·`SettingsPanel`(blur/Enter clamp). 본 사이클은 이 배선을 그대로 복제한다.

**DB**
- 최신 마이그레이션 V083. V084는 kb-quick-setup 브랜치가 선점 → **본 사이클 V085**. V054 이후 DDL은 테이블·컬럼 COMMENT 필수(`tests/db/test_migration_ddl_comments.py`).

### 1.3 사용자 결정 사항 (2026-11-05 확인)

| 질문 | 결정 |
|------|------|
| 기본값 / 범위 | **기본 50000, 범위 8000~500000**. 기존 행은 DEFAULT로 일괄 50000 |
| 집계 단위 | **현재 추정 방식(글자 수 ÷ 4) 유지**. LLM 실측 교체는 별도 사이클 |
| 한도 도달 동작 | **반복 한도와 통일** — `limit_reached` + final_answer 안내 + payload 플래그. 도달 사유(iteration/token) 구분 필드 추가 |
| 작업 범위 | **풀스택** — DB + API + Studio 설정 패널 |
| 서브 에이전트 | **독립 구조** — 서브 에이전트 자기 DB 값 사용. 부모 절반 상속 폐기 |
| 포크 / 자동 포크 | **원본 값 복사** (max_iterations와 동일) |

### 1.4 Related Documents

- 선행 사이클: `idt/docs/archive/2026-07/agent-recursion-limit/` (plan/design/analysis/report)
- 관련 사이클: supervisor-early-finish-fix (D-05 되물음·Gap-06 토큰 가드 루프), worker-capability-denial-guard (D-07 `_challenge_reset`)
- 재현 런: LangSmith trace `01a1a939-8ed0-79b0-8478-9ec438102fc9` (token_usage 8869 / token_limit 8000, iteration 1/25)
- 규칙: `idt/docs/rules/db-session.md`, `idt/docs/rules/testing.md`, 루트 `CLAUDE.md §4-1 API 계약 동기화`

---

## 2. Scope

### 2.1 In Scope

**A. DB 마이그레이션 (idt/)**
- [ ] `V085__alter_agent_definition_add_token_limit.sql` (additive): `token_limit INT NOT NULL DEFAULT 50000 COMMENT '...'`
- [ ] `AgentDefinitionModel.token_limit` 매핑(`comment=` 포함), repository save/update/row→entity 반영

**B. 도메인 (idt/)**
- [ ] `TokenLimitPolicy` (DEFAULT 50000, MIN 8000, MAX 500000, `validate`) — `IterationLimitPolicy` 동형
- [ ] `AgentDefinition.token_limit` 필드 + `__post_init__` 검증, `with_updates` 류 복사 경로
- [ ] `SupervisorConfig.token_limit` 기본값을 정책 상수로 교체

**C. 애플리케이션 / API (idt/)**
- [ ] 생성·수정 요청 스키마 `token_limit` (`Field(50000, ge=8000, le=500000)`, 수정은 `None`=변경 없음), 응답·상세 스키마
- [ ] create / update / get / fork / auto_fork 유스케이스에 필드 전달
- [ ] `run_agent_use_case.py:985`·`:1363` — `SupervisorConfig(max_iterations=…, token_limit=agent.token_limit)`
- [ ] 서브 에이전트: `_compile_sub_agent`→`_wrap_sub_agent`에 `sub_agent.token_limit` 전달, `state["token_limit"] // 2` 제거
- [ ] 토큰 가드: `limit_reached=True` + 도달 사유 필드 세움. final_answer 안내 블록 문구를 사유별로 분기. payload 사유 필드(명칭·위치는 Design)

**D. 프론트 (idt_front/)**
- [ ] `types/agentBuilder.ts`·`types/agentStore.ts` `token_limit` 추가, `constants/agentSettings`에 `TOKEN_LIMIT` 범위 상수
- [ ] `SettingsPanel`에 토큰 한도 입력(반복 한도와 같은 blur/Enter clamp 패턴), 폼 상태·create/update 전송·edit 프라임
- [ ] `limit_reached` 사유 표시(기존 배지 문구 분기) — 사유 필드가 payload에 추가되는 경우만

**E. 테스트**
- [ ] 백엔드: 정책 검증, 도메인 `__post_init__`, 유스케이스 전달, 실행 경로 주입(루트·재개·서브), 토큰 가드 → final_answer 안내·플래그, 마이그레이션 COMMENT 검사
- [ ] 프론트: SettingsPanel clamp·전송, 타입 계약(MSW)

### 2.2 Out of Scope

- 토큰 집계 방식 변경(LLM `usage_metadata` 실측, 입력 토큰 포함) — 별도 사이클
- 서브 에이전트 한도를 "자기 값과 부모 절반 중 작은 값"으로 캡하는 규칙 — 사용자가 독립 구조로 결정
- 워커 산출 요약으로 토큰 소모를 줄이는 최적화
- 조직/부서 단위 기본값, 환경변수 기반 전역 기본값
- 런 중 실시간 토큰 사용량 표시 UI

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `agent_definition.token_limit INT NOT NULL DEFAULT 50000` 컬럼 추가(V085). 기존 행은 50000. 테이블·컬럼 COMMENT 포함 | High | Pending |
| FR-02 | 도메인 `TokenLimitPolicy`로 8000~500000 범위를 검증한다. 범위 밖은 `AgentDefinition` 생성 시 `ValueError`, API는 422 | High | Pending |
| FR-03 | 생성 API는 `token_limit` 미전달 시 50000, 수정 API는 미전달 시 변경 없음. 조회·상세 응답에 포함 | High | Pending |
| FR-04 | 대화 실행(`:985`)·승인 재개(`:1363`) 모두 `agent.token_limit`을 `SupervisorConfig`에 주입한다 | High | Pending |
| FR-05 | 서브 에이전트 그래프는 **서브 에이전트 자신의** `token_limit`을 쓴다. 부모 값 절반 상속 코드를 제거한다 | High | Pending |
| FR-06 | 토큰 한도 가드는 `limit_reached=True`를 세워 워커 미실행이어도 final_answer를 경유하고, final_answer는 "토큰 한도 도달" 안내 블록을 삽입한다 | High | Pending |
| FR-07 | `ANSWER_COMPLETED` payload의 `limit_reached`는 토큰 한도 도달에도 True가 되며, 도달 사유(iteration / token)를 구분하는 필드를 함께 싣는다 | Medium | Pending |
| FR-08 | 포크·자동 포크는 원본의 `token_limit`을 복사한다 | Medium | Pending |
| FR-09 | Studio 설정 탭에 토큰 한도 입력을 추가한다. 반복 한도와 같은 입력 규칙(자유 타이핑, blur/Enter 시 범위 clamp, 비숫자는 복원), 헤더 저장 버튼으로 create/update에 실린다 | High | Pending |
| FR-10 | 프론트 타입·서비스·훅이 백엔드 스키마와 동기화된다(`/api-contract-sync`) | High | Pending |
| FR-11 | 토큰 가드가 `limit_reached`를 세워도 되물음(`finish_challenge_pending`)과의 무한 루프가 재발하지 않는다(Gap-06 회귀 테스트 유지) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 호환성 | 기존 에이전트·기존 API 클라이언트가 필드 미전달로도 동작(기본값 50000) | 기존 통합 테스트 전부 통과, 마이그레이션 후 기존 행 조회 |
| 안전성 | 토큰 가드 변경이 종료 경로 불변식(모든 조기 return이 `_challenge_reset` 포함)을 깨지 않음 | `tests/application/agent_builder/test_agent_iteration_limit.py` 및 early-finish-fix 테스트 통과 |
| 레이어 규칙 | 정책은 domain, 주입은 application, 매핑은 infrastructure, 라우터에 로직 없음 | `/verify-architecture` |
| 테스트 | TDD(Red→Green), 새 모듈 테스트 파일 존재 | `/verify-tdd`, `uv run python -m pytest` |
| DDL 규칙 | V085 COMMENT 필수 | `tests/db/test_migration_ddl_comments.py` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 재현 시나리오(URL 스크랩 → 분석 → 발표자료)가 기본값 50000으로 토큰 가드 없이 완주한다(로컬 재현 또는 동등한 단위 테스트로 `token_usage` 8869에서 supervisor가 LLM 결정을 수행함을 확인)
- [ ] SC-2: `token_limit`이 생성 → 조회 → 수정 → 조회 → 포크 전 경로에서 왕복 보존된다
- [ ] SC-3: 토큰 한도 도달 시 final_answer 안내 블록과 `limit_reached=True`·사유 필드가 반복 한도 도달과 같은 형태로 나간다. 워커 미실행 상태의 도달도 답변을 낸다
- [ ] SC-4: 서브 에이전트 그래프의 초기 state `token_limit`이 서브 에이전트 정의 값과 같다(부모 값과 무관)
- [ ] SC-5: 범위 밖 값(7999, 500001)은 API 422, 도메인 ValueError
- [ ] SC-6: Studio 설정 탭에서 입력·저장·재진입 시 값이 유지되고 clamp가 동작한다
- [ ] SC-7: 기존 테스트 전부 통과(알려진 master 상시 실패 목록 제외), 프론트 `npm test` 통과

### 4.2 Quality Criteria

- [ ] 백엔드 새 코드 테스트 선행(TDD), 함수 40줄·if 2단계 규칙 준수
- [ ] `/verify-architecture`, `/verify-logging` 통과
- [ ] 프론트 lint·타입 체크 통과, 컴포넌트 파일 런타임 상수 export 금지 규칙 준수

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 기본값 8000→50000 상향으로 런당 LLM 비용 상한이 느슨해짐 | Medium | High | 반복 한도(25)가 2차 상한으로 유지. 범위 상한 500000. 집계는 산출 글자 수 기반이라 실제 비용과 비례하지 않음을 문서화 |
| 토큰 가드가 `limit_reached`를 세우면 `route_to_worker_or_final`의 되물음 분기(`and not limit_reached`)가 바뀌어 기존 테스트가 깨짐 | Medium | High | Gap-06 테스트의 기대값을 "루프 없이 final_answer 도달"로 갱신. 무한 루프 방지는 `_challenge_reset`이 담당함을 테스트로 고정 |
| 서브 에이전트 독립 한도로 부모보다 큰 예산을 쓸 수 있음 | Low | Medium | 사용자 결정 사항. 서브 에이전트 반복 한도(부모 절반)는 유지되어 2차 상한으로 작동 |
| 승인 재개 경로(`:1363`) 누락 | Medium | Medium | FR-04에 두 경로 모두 명시, 각각 주입 테스트 |
| 프론트 폼 상태(`form.maxIterations`) 옆에 필드 추가 시 edit 프라임·복원 누락 | Medium | Medium | `max_iterations` 배선 지점을 grep해 동일 지점 전부 반영, MSW 테스트로 왕복 검증 |
| 로컬 DB에 V085를 수동 적용 후 Flyway 재적용 충돌 | Low | Medium | 메모리 규칙대로 적용 이력을 기록 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `agent_definition` | DB 테이블 | `token_limit INT NOT NULL DEFAULT 50000` 추가 (V085) |
| `AgentDefinitionModel` | SQLAlchemy 모델 | 컬럼 매핑 추가 |
| `AgentDefinition` (domain) | Entity | 필드 + 범위 검증 |
| `TokenLimitPolicy` (domain) | Policy | 신규 |
| `SupervisorConfig` | Domain VO | 기본값을 정책 상수로 |
| `AgentCreateRequest / AgentUpdateRequest / AgentResponse / AgentDetailResponse` | API 스키마 | `token_limit` 필드 |
| `SupervisorState.token_limit` 주입 경로 | Application | 루트·재개·서브 그래프 |
| 토큰 한도 가드 (`supervisor_nodes.py:451`) | Application | `limit_reached` + 사유 |
| final_answer 안내 블록 (`workflow_compiler.py:1774`) | Application | 사유별 문구 |
| `ANSWER_COMPLETED` payload | WS 계약 | 사유 필드 추가 (Design 확정) |
| `types/agentBuilder.ts`, `types/agentStore.ts`, `constants/agentSettings.ts`, `SettingsPanel.tsx` | Frontend | 필드·상수·입력 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `agent_definition` | CREATE | `create_agent_use_case.py:314` | 필드 추가 필요 |
| `agent_definition` | READ | `get_agent_use_case.py:149`, `agent_definition_repository.py:432` | 매핑 추가 |
| `agent_definition` | UPDATE | `update_agent_use_case.py:238`, repository `:117` | 필드 추가 필요 |
| `agent_definition` | COPY | `fork_agent_use_case.py:98`, `auto_fork_service.py:68` | 복사 필요 (FR-08) |
| `SupervisorConfig` | 생성 | `run_agent_use_case.py:985`, `:1363` | `token_limit` 전달 |
| `SupervisorConfig` | 생성 | `workflow_compiler.py:2935` (서브) | 절반 상속 → 서브 정의 값 |
| `SupervisorConfig` | 생성 | `workflow_compiler.py:669` (`supervisor_config or SupervisorConfig()`) | 기본값만 변경, 동작 동일 |
| `state["token_limit"]` | READ | `supervisor_nodes.py:451` 가드 | `limit_reached` 추가 |
| `state["limit_reached"]` | READ | `route_to_worker_or_final`(`:696-703`), final_answer(`:1776`), `run_agent_use_case.py:1497` | 토큰 도달에도 True — 의도된 변경 |
| `limit_reached` payload | READ | 프론트 answer 배지 | 사유 필드 선택적 소비 |
| `tests/application/agent_builder/test_agent_iteration_limit.py` 등 | TEST | Gap-06 "토큰 가드는 limit_reached를 세우지 않는다" 고정 테스트 | **기대값 갱신 필요** |

### 6.3 Verification

- [ ] 위 소비자 전부 반영 여부를 grep(`max_iterations` 배선 지점 ↔ `token_limit`)으로 대조
- [ ] 권한·가시성 변경 없음
- [ ] 필드 추가가 기존 조회·갱신 쿼리를 깨지 않음(NOT NULL DEFAULT)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (Thin DDD: domain → application → infrastructure / interfaces) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 한도 출처 | 코드 상수 / 환경변수 / 에이전트 DB 컬럼 | **에이전트 DB 컬럼** | 반복 한도와 동일한 단일 소스. 에이전트별 작업 성격(수집 중심 vs 대화 중심)이 달라 전역값으로는 부족 |
| 범위 검증 위치 | API 스키마만 / 도메인 정책 + API 스키마 | **도메인 정책 + API 스키마** | `IterationLimitPolicy` 선례. 도메인이 최종 방어선, API는 422로 조기 거부 |
| 한도 도달 신호 | 별도 플래그 / 기존 `limit_reached` 재사용 + 사유 | **기존 재사용 + 사유 필드** | 라우팅·final_answer·latch·payload가 이미 `limit_reached`에 배선됨. 사유만 더해 프론트가 문구를 구분 |
| 서브 에이전트 한도 | 부모 절반 / 자기 값 / min(자기, 부모 절반) | **자기 값** | 사용자 결정. 서브 정의는 컴파일 시 이미 로드됨 |
| 집계 방식 | 유지 / LLM 실측 | **유지** | 범위 최소화. 실측 교체는 집계 지점 9곳·기본값 의미가 함께 바뀌므로 별도 사이클 |

### 7.3 Layer Mapping

```
domain/agent_builder/policies.py        TokenLimitPolicy (DEFAULT/MIN/MAX/validate)
domain/agent_builder/schemas.py         AgentDefinition.token_limit, SupervisorConfig 기본값
application/agent_builder/schemas.py    요청/응답 스키마
application/agent_builder/*_use_case.py create/update/get/fork, run(주입)
application/agent_builder/supervisor_nodes.py   토큰 가드 limit_reached + 사유
application/agent_builder/workflow_compiler.py  final_answer 안내, 서브 에이전트 주입
infrastructure/agent_builder/models.py, agent_definition_repository.py  매핑
db/migration/V085__...sql
idt_front/src/types, constants, components/agent-builder/settings
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` 코딩 규칙(함수 40줄, if 2단계, DDL COMMENT, logger)
- [x] `idt/docs/rules/db-session.md`, `testing.md`
- [x] 프론트: `idt_front/CLAUDE.md`, 컴포넌트 파일 런타임 상수 export 금지(as const는 `src/types/*.ts` 또는 `constants/`)
- [x] 루트 `CLAUDE.md §4-1` API 계약 동기화 → `/api-contract-sync`

### 8.2 Conventions to Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 네이밍 | `max_iterations` / `maxIterations` | `token_limit` / `tokenLimit` 동일 규칙 | High |
| 마이그레이션 | V083까지 | V085, COMMENT 필수 | High |
| 코드 주석 | `agent-recursion-limit D#` 참조 패턴 | `agent-token-limit D#` 참조 | Medium |

### 8.3 Environment Variables Needed

없음 (전역 기본값은 정책 상수로만 둔다).

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`agent-token-limit.design.md`) — payload 사유 필드 명칭·위치, 토큰 가드 변경 후 되물음 분기 불변식, Gap-06 테스트 갱신 범위, SettingsPanel 레이아웃
2. [ ] 사용자 검토·승인
3. [ ] 구현 (module 분할: ① DB+도메인 ② API+유스케이스 ③ 실행 경로·가드 ④ 프론트)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-05 | Initial draft — 사용자 결정 6건 반영 | 배상규 |
