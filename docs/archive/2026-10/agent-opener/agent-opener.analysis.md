# agent-opener Gap Analysis

> **Feature**: agent-opener
> **Date**: 2026-10-25
> **Analyst**: gap-detector(정적) + 세션 실런(런타임)
> **Plan**: [agent-opener.plan.md](../01-plan/features/agent-opener.plan.md)
> **Design**: [agent-opener.design.md](../02-design/features/agent-opener.design.md)
> **Status**: Check → Act-1 완료 — Match Rate **96.1% → 100%** (G1·G3·G4 수정 후 재검증)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트별 "무엇을 물어볼지"를 첫 화면에서 안내할 수단이 없고, 빌더 오프너 탭은 placeholder뿐이다 |
| **WHO** | P2 에이전트 소유자(등록) · P1 채팅 이용자(클릭해 시작) |
| **RISK** | `/agents/my` N+1 → 배치 필수. 4곳 세트 누락 시 조용히 미저장 |
| **SUCCESS** | 12개 등록·저장·프라임, 채팅 카드·즉시 전송, 기존 화면 무회귀, FAILED diff 0 |
| **SCOPE** | module-1 백엔드 → module-2 빌더 탭 → module-3 채팅 빈 상태 (전부 구현) |

---

## Strategic Alignment Check

### PRD Alignment

PRD 없음(Plan 직행). Plan의 핵심 문제(에이전트별 시작 안내 부재)는 빌더 등록 → 채팅 빈 상태 노출 → 클릭 즉시 전송 경로가 실 브라우저에서 끝까지 동작함으로 해소됐다.

### Success Criteria Status (Plan §4.1)

| 기준 | 상태 | 근거 |
|---|---|---|
| FR-01~13 구현 + 테스트 | ✅ Met | Act-1에서 FR-06 결함(G1) 수정 — §2 표 |
| 백엔드 FAILED 목록 diff 0 | ✅ Met | 53 failed / 10,705 passed — 상시 실패 목록과 파일 단위 일치 |
| 프론트 vitest·lint·tsc 신규 실패 0 | ✅ Met | vitest 실패 15건 = 상시 9 + 부하 민감 3파일(단독 통과), tsc 210=기준선, eslint 신규 0 |
| 수동 E2E 등록→저장→프라임→채팅 카드→클릭 전송 | ✅ Met | §2.7 L3 #1 브라우저 실행 |
| 오프너 없음·super는 기존 카드 | ✅ Met | §2.7 L3 #2 + vitest |
| 위키 미갱신, V080 배포 의존 보고 명시 | ✅ Met | Report에 기재 예정(G7) |

### Decision Record Verification

| 결정 | 준수 | 근거 |
|---|---|---|
| [Plan] 별도 테이블 `agent_opener` | ✅ | V080 |
| [Plan] 목록 응답에 openers, 배치 1쿼리 | ✅ | `list_my_agents_use_case.py:106-116`, 테스트 `batch_calls == 1` |
| [Plan] 포크 복사 | ✅ | `fork_agent_use_case.py:85-92`, 실런 #11 |
| [Plan] 12·200·중복 422 | ✅ (Act-1) | 12·200은 Pydantic 422. 중복 메시지에서 사용자 텍스트 제거 → 항상 422 |
| [Design] Option C — 엔티티·AgentDefinitionRepository 무변경 | ✅ | grep "opener" 무 hit |
| [Design] 폼 staged + 상단 저장, 빈 행 제거 | ✅ | `openerPayload.ts`, 페이지 `:289`, `:375-378` |
| [Design] super는 고정 카드 | ✅ | `ChatPage/index.tsx:38-43` |
| [Design §6.3] 정책 메시지에 트리거 단어 금지 | ✅ (Act-1) | `{text}` 삽입 제거, 위치 번호만 사용. Design §3.1 메시지 표 v0.2로 갱신 |

---

## 1. Analysis Overview

### 1.1 Purpose
Design(§3·§4·§5.4·§6.3·§8) 대비 구현 일치도와 Plan FR·Success Criteria 충족 여부를 정적+런타임으로 판정한다.

### 1.2 Scope
백엔드 idt/ (V080·domain·infra·application·DI·tests), 프론트 idt_front/ (타입·상수·OpenerPanel·빌더 페이지·채팅 빈 상태·tests). 분석 대상 외: AutoForkService(범위 밖), 스토어 상세 모달(범위 밖).

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints

| Design §4.1 | 구현 | 상태 |
|---|---|---|
| POST `/api/v1/agents` 요청 `openers?`, 응답 `openers` | `schemas.py:129`, `:165`; `create_agent_use_case.py:246-248, 278-279, 326` | ✅ |
| PATCH `/api/v1/agents/{id}` None/[]/[...] | `schemas.py:196`; `update_agent_use_case.py:253-257` | ✅ |
| GET `/api/v1/agents/{id}` `openers` | `schemas.py:247`; `get_agent_use_case.py:111-115,138` | ✅ |
| GET `/api/v1/agents/my` `agents[].openers` 배치 | `schemas.py:387`; `list_my_agents_use_case.py:86-87,106-116` | ✅ |
| POST `/agents/{id}/fork` 복사 | `fork_agent_use_case.py:85-92` | ✅ |

### 2.2 Data Model

| Design §3 | 구현 | 상태 |
|---|---|---|
| `agent_opener` DDL (FK CASCADE, VARCHAR(200), sort_order, INDEX, COLLATE 미명시, 전 COMMENT) | `V080__create_agent_opener.sql:8-18` | ✅ (로컬 적용, errno 3780 없음) |
| ORM FK 미선언, index | `models/agent_opener/models.py:13-32` | ✅ |
| 포트 3 메서드, `list[str]` 반환 | `domain/agent_opener/interfaces.py` | ✅ |
| `OpenerPolicy.normalize` 상수 12/200 | `policies.py:17-38` | ✅ (메시지 결함 G1) |

### 2.3 Component Structure

Design §11.1 파일 전부 존재. 구조 일치 100%.

### 2.4 Functional Depth

placeholder 없음. use case 5종 의미론 5/5. §6.3 1.5/2 (G1). 테스트 미비 1건(§8.3 #7 서버 422 표시, G3).

### 2.5 Page UI Checklist (Design §5.4)

| 항목 | 상태 | 근거 |
|---|---|---|
| 빌더: 탭 활성 | ✅ | `AgentTestPanel.tsx:66`, 브라우저 확인 |
| 안내문 / `n/12` / `+ 추가`(12개 disabled) | ✅ | `OpenerPanel.tsx:85-97`, 브라우저 0/12→3/12 확인 |
| 행: 번호·input maxLength 200·삭제 aria-label | ✅ | `OpenerPanel.tsx` OpenerRow, 테스트 |
| 빈 안내 | ✅ | `OpenerPanel.tsx:104` (Act-1에서 Design 문구로 정합) |
| 저장: 빈 행 제거, update 전체 교체 기준선 | ✅ | DB 조회 — 빈 3행 제외 2행 저장 |
| 프라임 | ✅ | `agentDetailMapping.ts:90`, vitest |
| 서버 422 표시·입력 유지 | ✅ (Act-1) | MSW 422 테스트 추가 — 메시지 표시 + 행 유지 단언 |
| 채팅: 카드·클릭 전송·fallback·super·HTML 미해석 | ✅ | vitest 5건 + 브라우저 |

### 2.6 API Contract (3-way)

Design §4 ↔ 서버 스키마/DI(`main.py:3104-3105`, 5 팩토리) ↔ 클라 타입(`agentBuilder.ts:76,103,139,197`, `agentStore.ts:55`, `agent.ts:20,106`)·페이로드(`AgentBuilderPage/index.tsx:289, 375-378`) 전부 일치. 5/5.

### 2.7 Runtime Verification Results

실행 환경: 로컬 MySQL(V080 수동 적용) + `TestClient(app)` 인프로세스 + 실행 중인 dev 서버(8000/5173) + Chrome.

**L1 API (실 DB 스모크, 2026-10-25 2회 실행)**

| # | 시나리오 | 결과 |
|---|---|---|
| 1 | POST openers 2건 → 201, 정규화 에코 | PASS |
| 2 | POST 미전달 → `openers: []` | PASS (라우터 계약 테스트) |
| 3/4 | 13건 / 201자 → 422 | PASS (라우터 계약 테스트) |
| 5 | POST `["a","a"]` → 422 | PASS |
| 5b | PATCH `["최대 한도 알려줘","최대 한도 알려줘"]` → 422 | Check: **FAIL 409** (G1) → Act-1 재실행: **PASS 422** |
| 6 | PATCH → GET 반영 | PASS |
| 7 | PATCH `[]` → GET `[]` | PASS |
| 8 | name만 PATCH → 유지 | PASS |
| 9 | PATCH `[" a ","a"]` → 422 | PASS |
| 10 | GET `/my` 오프너 노출 | PASS (배치 1회는 use case 테스트로 단언) |
| 11 | 포크 → 사본 동일 | PASS |
| 12 | DDL COMMENT 검사 + 전체 pytest diff 0 | PASS |

L1: Check 12/13 → Act-1 13/13.

**L2 UI (vitest 19건 + 브라우저)**

#1~#6, #8~#11 PASS (vitest + 브라우저에서 탭 진입·추가·3/12·저장 확인). #7(서버 422 표시)은 Act-1에서 MSW 테스트로 PASS. L2: 10/11 → 11/11.

**L3 E2E (브라우저, Chrome)**

| # | 시나리오 | 결과 |
|---|---|---|
| 1 | 빌더 edit(데이터 분석) → 오프너 2건 + 빈 행 1 → 저장 → DB 2행(순서 보존, 빈 행 제거) → `/chatpage` 해당 에이전트 선택 → 카드 2개(고정 카드 숨음) → 카드 클릭 → 사용자 메시지로 즉시 전송·에이전트 응답 스트리밍 시작 | PASS |
| 2 | super 선택 시 고정 카드(문서 검색·자유 대화 등) 그대로 | PASS |

L3: 2/2. **Runtime = Check 24/26 = 92.3% → Act-1 26/26 = 100%**

### 2.8 Match Rate Summary

| 축 | 점수 | 가중치 |
|---|---|---|
| Structural | 100% | 0.15 |
| Functional | 95.2% → 100% (G1·G3 해소) | 0.25 |
| Contract | 100% | 0.25 |
| Runtime | 92.3% → 100% | 0.35 |
| **Overall** | **96.1% → 100%** | |

(정적만: 100×0.2 + 95.2×0.4 + 100×0.4 = 98.1%)

---

## 3. Code Quality Analysis

- 함수 길이·중첩: 신규 함수 전부 40줄 이내, if 2단계 이내.
- 코드 스멜: 없음. `OpenerPanel` 초기 구현의 렌더 중 ref 접근은 Do 단계 린트에서 상태로 교체 완료.
- 보안: 오프너는 평문 텍스트 렌더(React 텍스트 노드), HTML 미해석 테스트 통과. 인가는 기존 can_edit·가시성 가드 그대로.

---

## 4. Performance

`/agents/my`는 페이지 슬라이스 후 `list_by_agent_ids` 1회(IN 쿼리). 기존 구독 건별 `find_by_id` N+1은 이 기능 범위 밖(이월).

---

## 5. Test Coverage

| 영역 | 테스트 | 상태 |
|---|---|---|
| 도메인 정책 | 16 | ✅ (Act-1: 트리거 단어를 품은 중복·빈 항목 케이스 4건 추가) |
| use case 5종 (fake repo) | 14 | ✅ |
| 라우터 계약 (mock use case) | 12 | ✅ (Act-1: 트리거 단어 중복 422 ×2 추가) |
| 실 DI 왕복 | 스크래치 스모크만 (커밋된 테스트 없음) | ⚠️ G2 |
| 리포지토리 실 DB | 없음 (스모크로만 간접 확인) | ⚠️ G5 |
| 프론트 | OpenerPanel 7, 유틸 3, 페이지 3, 채팅 5 | ✅ (Act-1: 서버 422 표시·행 유지 테스트 추가) |

---

## 6. Clean Architecture Compliance

domain `agent_opener` 외부 import 없음 · application → domain 포트만 참조 · infrastructure → domain만 · DI는 main.py. `AgentDefinition`·`AgentDefinitionRepository` 무변경(grep 확인). 위반 0.

---

## 7. Convention Compliance

네이밍(`agent_opener`/`openers`/`OpenerPanel`/`OPENER_LIMITS`) · 상수 위치 `constants/` · V080 COMMENT 규칙 · `uv run python -m pytest` · 디자인 토큰(인라인 style 미사용) 전부 준수. 빈 안내 문구(G4)는 Act-1에서 정합.

---

## 8. Gap List

> Act-1(2026-10-26) 처리: G1·G3·G4 수정 완료, G2·G5·G6 이월(사용자 결정).

| # | 심각도 | 확신 | 위치 | 내용 | 조치 |
|---|---|---|---|---|---|
| G1 | **Important** | 95% (실런 재현) | `idt/src/domain/agent_opener/policies.py:35` | 중복 메시지가 사용자 텍스트를 포함해 "최대/이미/찾을 수 없"이 들어간 오프너가 중복이면 라우터 매퍼가 409/404로 바꿈 | `{text}` 대신 항목 번호로 메시지 구성 + 정책 테스트에 "최대 한도" 중복 케이스 + 라우터 422 테스트 추가 |
| G2 | Important | 95% | `idt/tests/api/test_agent_builder_router.py` | Design §4.4의 실 DI PATCH→GET 왕복이 커밋된 테스트로 없음(스크래치 스모크로만 수행) | 인프로세스 실 DB 테스트는 로컬 전용이라 CI 부적합 — 스모크 스크립트를 `tests/manual/`로 보존하고 Report에 실행 결과 기록 (이월 수용) |
| G3 | Minor | 85% | `idt_front/src/pages/AgentBuilderPage/index.test.tsx` | 서버 422 → 메시지 표시·행 유지 테스트 없음 | MSW 422 테스트 1건 추가 |
| G4 | Minor | 90% | `OpenerPanel.tsx:104` | 빈 안내 문구 "추가 버튼으로 시작하세요" vs Design "+ 추가로 시작하세요" | Design 문구에 맞춤 |
| G5 | Minor | 80% | `agent_opener_repository.py` | 실 DB 리포지토리 단위 테스트 없음 | G2와 동일 처리(스모크로 간접 검증, 이월) |
| G6 | Minor | 70% | `authClient.ts:64` | Pydantic 422(배열 detail)는 "알 수 없는 오류"로 표시 — 프론트 가드로 사실상 미발생 | 기존 인터셉터 동작, 범위 밖 이월 |
| G7 | Docs | 100% | Plan §4.1 | Report에 `ops/migration-deploy-deps.md` V080 항목 필요를 명시 | Report 단계 |

---

## 9. Recommended Actions

### 9.1 Immediate (iterate)
| 우선 | 항목 | 파일 |
|---|---|---|
| 🔴 1 | G1 메시지에서 사용자 텍스트 제거 + 테스트 2건 | `policies.py`, `test_opener_policy.py`, `test_agent_builder_router.py` |
| 🟡 2 | G3 서버 422 표시 테스트 | `AgentBuilderPage/index.test.tsx` |
| 🟡 3 | G4 빈 안내 문구 정합 | `OpenerPanel.tsx` |

### 9.2 이월 (explicit-gap-carryover)
G2·G5(실 DB 테스트는 로컬 전용 스모크로 대체, 스크립트 보존), G6(기존 인터셉터), 기존 `/my` 구독 N+1, 스트리밍 중 supervisor JSON 원문 노출(agent-chat-reasoning-display 영역, 이번 E2E에서 관찰됨 — 이 기능과 무관).

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-10-25 | 정적(gap-detector) + 런타임(L1 실DB·L2 vitest/브라우저·L3 브라우저) 분석 |
| 0.2 | 2026-10-26 | Act-1 — G1(정책 메시지 사용자 텍스트 제거)·G3(422 표시 테스트)·G4(문구) 수정, 재검증 반영 |
