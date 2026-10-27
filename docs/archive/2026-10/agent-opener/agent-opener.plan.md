# agent-opener Planning Document

> **Summary**: 에이전트 빌더 우측 패널의 비활성 placeholder인 **오프너 탭 활성화** — 에이전트 소유자가 "대화 시작 예시 질문"을 최대 12개 등록·저장하고(`agent_opener` 테이블 신설), 채팅 화면에서 그 에이전트로 새 대화를 시작할 때 빈 상태에 예시 질문 카드로 노출해 클릭 즉시 전송한다. 백엔드(테이블·API) + 프론트(빌더 탭·채팅 빈 상태) 풀스택.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-10-24
> **Status**: Draft
> **목표 UI**: `docs/img/offner.png`

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 빌더 우측 패널의 오프너 탭이 `enabled: false` placeholder로 잠겨 있고(`AgentTestPanel.tsx:61`), 백엔드에도 저장 구조가 없다. 채팅 빈 상태는 모든 에이전트가 같은 고정 제안 카드 4종(문서 요약·문서 검색·AI Agent·자유 대화, `MessageList.tsx`)을 보여줘 "이 에이전트에게 무엇을 물어야 하는지"를 사용자가 알 수 없다. |
| **Solution** | ① `agent_opener` 테이블 신설(agent_definition CASCADE, sort_order) + create/update/detail/my 목록 API에 `openers` additive 확장 ② 빌더 오프너 탭 활성화 — 폼 상태에 staged 후 상단 저장 버튼으로 함께 전송(설정 탭과 동일 방식) ③ 채팅 빈 상태(ChatPage `EmptyAgentState`)에서 선택 에이전트의 오프너가 있으면 그 카드로 교체, 없으면 기존 고정 카드 유지 ④ 포크 시 오프너 복사 |
| **Function/UX Effect** | P2(에이전트 소유자)가 에이전트의 용도를 예시 질문으로 안내할 수 있고, P1(이용자)은 클릭 한 번으로 대화를 시작한다. 에이전트마다 다른 시작 화면이 생겨 "무엇을 하는 에이전트인지"가 첫 화면에서 읽힌다. |
| **Core Value** | 에이전트별 온보딩을 코어 하드코딩 없이 **데이터로** 제공(일반화 우선 원칙). 모든 계약 확장은 additive(optional 필드)라 기존 소비자 회귀 0, 채팅 빈 상태 추가 요청 0건. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트별 "무엇을 물어볼지"를 첫 화면에서 안내할 수단이 없고, 빌더 오프너 탭은 placeholder뿐이다 |
| **WHO** | P2 에이전트 소유자(등록) · P1 채팅 이용자(클릭해 시작) |
| **RISK** | 목록 API(`/agents/my`)에 오프너를 합치며 N+1 조회 추가 → 배치 로드 필수. 수정 가능 필드 4곳 세트(스키마·use_case·repo·DI) 누락 시 조용히 미저장 |
| **SUCCESS** | 빌더에서 12개까지 등록·저장·재진입 프라임 OK, 채팅 빈 상태에서 카드 노출·클릭 즉시 전송 OK, 오프너 없는 에이전트·super는 기존 화면 그대로, 기존 FAILED 목록 diff 0 |
| **SCOPE** | module-1 백엔드(테이블·도메인·API·포크) → module-2 빌더 오프너 탭 → module-3 채팅 빈 상태 노출 |

---

## 1. Overview

### 1.1 Purpose

`/agent-builder` 빌더(StudioLayout) 우측 패널의 오프너 탭을 활성화해 에이전트별 예시 질문을 등록·저장하고,
`/chatpage`에서 해당 에이전트로 새 대화를 시작할 때 빈 상태에 그 질문을 카드로 노출한다.

### 1.2 Background (2026-10-24 코드 조사로 확정)

**현재 상태**

| 구간 | 위치 | 상태 |
|------|------|------|
| 빌더 탭 | `idt_front/src/components/agent-builder/AgentTestPanel.tsx:61` — `{ id: 'opener', enabled: false }`, "준비중" 툴팁 | placeholder |
| 탭 타입 | `RightTabId`에 `'opener'` 이미 존재 (`types/agentBuilder.ts:196`) | 타입 확장 불필요 |
| 채팅 빈 상태 | `pages/ChatPage/index.tsx:38` `EmptyAgentState` → `components/chat/MessageList.tsx` `SuggestionCards` (고정 상수 `SUGGESTIONS` 4종) | 에이전트 무관 고정 |
| 채팅이 가진 에이전트 정보 | `AgentChatLayout` → `useMyAgents()`(GET `/api/v1/agents/my`) → `toAgentSummary` → `AgentSummary {id,name,description,category}` | 오프너 필드 없음 |
| 백엔드 저장 | `agent_definition` 및 자식 테이블 어디에도 오프너 없음 | 신규 필요 |
| 클릭 동작 | `onSuggestionClick(text)` → 즉시 전송 경로가 이미 존재 | 재사용 |

**선례(패턴 차용)**

- 수정 가능 필드 추가 = 스키마 + apply_update + repo update() + DI 4곳 세트 (wiki `agent-screens` 계약 주의, max_iterations 선례)
- 자식 테이블 `agent_skill`(V034): `agent_definition(id)` CASCADE, `sort_order`, 테이블 레벨 COLLATE 미명시(errno 3780 회피, wiki `mysql-fk-collation`), 동기화는 목표 상태 전체 교체(`SyncAgentSkillsUseCase`)
- 설정 탭(agent-settings-tab): 탭 내 별도 저장 없이 상단 저장 버튼에 통합, edit 프라임은 `mapDetailToForm`
- 계약 확장은 additive + optional 필드 (wiki `additive-contract-extension`)

**사전 결정 (2026-10-24 사용자 확정)**

1. 저장 구조: **별도 테이블 `agent_opener`** (JSON 컬럼 아님)
2. 저장 시점: **상단 저장 버튼에 통합** — 생성·수정 모두 폼 staged → create/update 페이로드
3. 클릭 동작: **즉시 전송** (현재 고정 카드와 동일)
4. 노출 위치: **채팅 빈 상태만** (빌더 테스트 탭·스토어 상세 모달은 범위 밖)
5. 채팅 데이터 소스: **`/agents/my` 목록 응답에 `openers` 추가** + 상세 응답에도 추가(edit 프라임용)
6. 포크 시 **오프너 복사**
7. 검증: 최대 12개 · 항목당 공백 제거 후 1~200자 · 빈 항목/중복 항목 422 · 정렬 UI 없음(등록 순서)

### 1.3 Related Documents

- 유저 시나리오: `docs/USER-SCENARIOS.md` (주인공 P2 — 에이전트 소유자)
- 위키: `backend/db/erd-agent.md`, `backend/db/mysql-fk-collation.md`, `frontend/screens/agent-screens.md`, `frontend/screens/chat-screens.md`, `conventions/additive-contract-extension.md`, `conventions/false-green-quality-gates.md`
- 선례 PDCA: `idt/docs/archive/2026-08/agent-settings-tab/` (탭 활성화 + 폼 배선), `idt_front/docs/archive/2026-06/agent-builder-studio-ui/` (placeholder 탭 원 설계 §5.1)
- 목표 UI: `docs/img/offner.png`

---

## 2. Scope

### 2.1 In Scope

**module-1 — 백엔드 (idt/)**

- [ ] Flyway `V080__create_agent_opener.sql` — `agent_opener(id, agent_id FK CASCADE, text VARCHAR(200), sort_order, created_at)` + `INDEX(agent_id)`, 테이블 COLLATE 미명시
- [ ] 도메인: `OpenerPolicy`(MAX_COUNT 12 · MAX_LENGTH 200 · strip 후 빈 값/중복 거부) — 검증은 도메인 정책 한 곳
- [ ] 리포지토리: `list_by_agent_id`, **`list_by_agent_ids`(배치)**, `replace(agent_id, texts)`(목표 상태 전체 교체)
- [ ] `CreateAgentRequest.openers: list[str] | None`, `UpdateAgentRequest.openers: list[str] | None`(None = 변경 안 함, [] = 전부 삭제, [...] = 전체 교체)
- [ ] `GetAgentResponse.openers: list[str] = []`, `MyAgentSummary.openers: list[str] = []`, `CreateAgentResponse.openers`
- [ ] create/update/get/list_my/fork use case 배선 + `main.py` DI
- [ ] 테스트: 정책 단위·use case(fake repo)·라우터 422 계약·마이그레이션 DDL COMMENT 검사 통과

**module-2 — 빌더 오프너 탭 (idt_front/)**

- [ ] `AgentTestPanel` 탭 정의 `opener.enabled = true` + `OpenerPanel` 신설 (`components/agent-builder/opener/`)
- [ ] 목표 UI(`offner.png`): 안내문 "사용자가 대화를 시작할 수 있는 예시 질문을 설정하세요" · 카운터 `n/12` · `+ 추가` 버튼 · 번호 배지 + 텍스트 입력 행 · 행 삭제
- [ ] `AgentBuilderFormData.openers: string[]` + create/update 페이로드 `openers` 전송 + `mapDetailToForm` 역주입
- [ ] 클라이언트 검증(12개 상한에서 추가 버튼 비활성, 200자 maxLength, 빈 행은 저장 시 제거) — 서버 422는 기존 에러 표시 경로로 노출
- [ ] 테스트: OpenerPanel(추가/삭제/상한/카운터), 페이지 저장 페이로드 포함, edit 프라임

**module-3 — 채팅 빈 상태 (idt_front/)**

- [ ] `MyAgent.openers?: string[]`, `AgentSummary.openers?: string[]`, `toAgentSummary` 전달
- [ ] `SuggestionCards`에 `items?: Suggestion[]` optional prop — 전달 시 그 목록, 미전달 시 기존 고정 4종(additive)
- [ ] `EmptyAgentState`: `agent.openers`가 1개 이상이면 오프너 카드, 아니면 기존 고정 카드. super 에이전트는 항상 기존 카드
- [ ] 클릭 → 기존 `onSuggestionClick(text)` 즉시 전송
- [ ] 테스트: 오프너 있음/없음/super 3분기, 클릭 시 전송 호출

### 2.2 Out of Scope

- 드래그/위·아래 버튼 정렬 UI (순서 = 등록 순서)
- 빌더 테스트 탭 빈 상태·에이전트 스토어 상세 모달·워크스페이스 페이지 노출
- 오프너 클릭 통계·추천(LLM 자동 생성)
- 오프너별 아이콘·카테고리 (텍스트 1줄만)
- 일반 채팅(super)·general_chat 경로의 고정 제안 카드 변경
- Fix 탭(compose) 초안에 오프너 포함

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `agent_opener` 테이블 신설 — agent_definition CASCADE, sort_order, text VARCHAR(200) | High | Pending |
| FR-02 | 생성 API(`POST /api/v1/agents`)가 `openers` 배열을 받아 저장한다 (미전달 = 없음) | High | Pending |
| FR-03 | 수정 API(`PATCH /api/v1/agents/{id}`)가 `openers`를 목표 상태로 전체 교체한다 (None = 변경 안 함, [] = 전부 삭제) | High | Pending |
| FR-04 | 상세 API(`GET /api/v1/agents/{id}`) 응답에 `openers`(sort_order ASC) 포함 | High | Pending |
| FR-05 | 내 에이전트 목록 API(`GET /api/v1/agents/my`) 응답 항목에 `openers` 포함 — **배치 조회**(에이전트 수만큼 추가 쿼리 금지) | High | Pending |
| FR-06 | 검증: 최대 12개, 항목당 strip 후 1~200자, 빈 항목·중복 항목은 422 (도메인 정책 단일 지점) | High | Pending |
| FR-07 | 포크 시 원본 오프너를 사본에 복사 | Medium | Pending |
| FR-08 | 빌더 오프너 탭 활성화 — 목록·추가·삭제·`n/12` 카운터, 상한 도달 시 추가 비활성 | High | Pending |
| FR-09 | 오프너는 폼 상태에 staged 되고 상단 저장 버튼으로 create/update 페이로드에 포함 전송 | High | Pending |
| FR-10 | 수정 모드 진입 시 상세 응답의 `openers`로 폼 프라임 | High | Pending |
| FR-11 | 채팅 빈 상태에서 선택 에이전트에 오프너가 있으면 오프너 카드 노출, 없으면 기존 고정 카드 유지, super는 항상 고정 카드 | High | Pending |
| FR-12 | 오프너 카드 클릭 시 그 문장을 즉시 사용자 메시지로 전송 | High | Pending |
| FR-13 | 에이전트 삭제 시 오프너가 함께 삭제된다 (CASCADE) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 성능 | `/agents/my` 응답 시간이 오프너 추가로 에이전트 수에 비례해 늘지 않는다 (배치 1쿼리) | 리포지토리 테스트에서 `list_by_agent_ids` 호출 1회 단언 |
| 호환성 | 모든 계약 확장은 optional/기본값 — 기존 프론트·MSW 핸들러·테스트 무변경으로 통과 | 기존 FAILED 목록 diff 0 (`uv run python -m pytest`, `vitest`) |
| 보안 | 오프너 텍스트는 평문 저장·평문 렌더(React 기본 이스케이프), 마크다운 미해석 | 컴포넌트 테스트에서 `<script>` 문자열이 텍스트로 렌더 |
| 데이터 무결성 | FK CASCADE, 테이블 COLLATE 미명시(errno 3780 회피), DDL COMMENT 안에 최상위 콤마 금지 | `tests/db/test_migration_ddl_comments.py` 통과 |
| 접근성 | 카드는 `button`, 입력 행에 label/aria-label, 삭제 버튼 aria-label | 테스트에서 role 기반 쿼리 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~13 구현 + 각 FR을 가리키는 테스트 존재 (TDD: Red → Green)
- [ ] 백엔드: `uv run python -m pytest` — 정렬된 FAILED 목록이 작업 전과 동일(상시 실패 목록 외 신규 0)
- [ ] 프론트: `npm run test` · `npm run lint` · `tsc -b` 신규 실패 0
- [ ] 수동 E2E: 빌더에서 3개 등록 → 저장 → 재진입 프라임 → `/chatpage`에서 그 에이전트 선택 → 카드 3개 → 클릭 → 사용자 메시지로 전송·응답 수신
- [ ] 오프너 없는 에이전트·super 선택 시 기존 고정 카드 4종 그대로
- [ ] 위키 갱신은 하지 않음 (사용자가 `/wiki update` 호출 시에만) — 단 `ops/migration-deploy-deps.md`에 V080 의존 항목을 추가해야 한다는 점을 보고에 명시

### 4.2 Quality Criteria

- [ ] 검증 규칙(12·200·중복)은 백엔드 도메인 정책 한 곳 + 프론트 상수 한 곳(`types/`)에만 존재, 컴포넌트 파일에 런타임 상수 export 금지
- [ ] 계약 변경 시 `idt/src/application/agent_builder/schemas.py` ↔ `idt_front/src/types/{agentBuilder,agent}.ts` 동기화(`/api-contract-sync`)
- [ ] 린트 0, 빌드 성공

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `/agents/my`가 이미 구독 건마다 `find_by_id`를 호출(N+1)하는데 오프너까지 건별 조회하면 악화 | Medium | High | `list_by_agent_ids(ids) -> dict[agent_id, list[str]]` 배치 메서드로 1쿼리, use case에서 요약 조립 후 일괄 부착 |
| 수정 가능 필드 4곳 세트(스키마·apply_update·repo·DI) 중 하나 누락 → 저장 조용히 실패 | High | Medium | 라우터 실요청 테스트(TestClient)로 PATCH 후 GET 왕복 단언 — 정적 검사만으로 종료 금지 |
| FK 참조 마이그레이션에 COLLATE 명시 → errno 3780 | High | Medium | V034 `agent_skill` DDL을 그대로 본뜸, ENGINE만 명시 |
| 오프너 테이블 FK가 ORM에는 없고 DDL에만 있는 기존 패턴과 혼동 | Low | Medium | ERD 위키 관례대로 "FK 진실은 SQL" 주석을 마이그레이션에 기록 |
| 생성 모드에서 사용자가 오프너를 입력했는데 저장 실패(422 다른 필드) 시 입력 유실 | Medium | Low | 폼 상태가 페이지 소유이므로 실패해도 유지 — 테스트로 고정 |
| 채팅 `AgentSummary`가 여러 곳(사이드바·헤더)에서 쓰여 필드 추가 파급 | Low | Low | optional 필드만 추가, `toAgentSummary` 단일 변환점 |
| 로컬 DB에 Flyway 이력이 없어 V080 수동 적용 필요 | Medium | High | 메모리 레시피(`idt-local-db-and-run-repro`)대로 로컬 수동 적용 후 실런 스모크 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `agent_opener` | DB 테이블 | 신설 (V080), agent_definition CASCADE |
| `AgentDefinition`(도메인) | Domain Entity | `openers: list[str] \| None = None` 추가 (None = 미로드/미변경, middleware_types 관례 동일) |
| `CreateAgentRequest` / `UpdateAgentRequest` | API 스키마 | `openers: list[str] \| None` optional 추가 |
| `GetAgentResponse` / `MyAgentSummary` / `CreateAgentResponse` | API 스키마 | `openers: list[str] = []` additive |
| `AgentDefinitionRepository` | Repo | 오프너 로드·교체 (별도 `AgentOpenerRepository` 분리 여부는 Design에서 결정) |
| `ForkAgentUseCase` | Use case | 오프너 복사 |
| `AgentBuilderFormData` / `CreateBuilderAgentRequest` / `UpdateBuilderAgentRequest` | 프론트 타입 | `openers` 추가 |
| `MyAgent` / `AgentSummary` | 프론트 타입 | `openers?: string[]` optional |
| `AgentTestPanel` | 컴포넌트 | opener 탭 활성 + 콘텐츠 분기 |
| `SuggestionCards` / `EmptyAgentState` | 컴포넌트 | items optional prop, 분기 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `POST /api/v1/agents` | CREATE | `AgentBuilderPage.handleSave` · 위저드(`agent_create_pipeline`) · `auto_fork_service` · Fix 초안 적용 | None (optional, 미전달 = 없음) |
| `PATCH /api/v1/agents/{id}` | UPDATE | `AgentBuilderPage.handleSave`(edit) · 스케줄/스킬 탭은 별도 API | None (None = 변경 안 함) |
| `GET /api/v1/agents/{id}` | READ | 빌더 edit 프라임(`mapDetailToForm`) · 스토어 상세 모달 · 워크스페이스 페이지 · 지식 페이지 | None (필드 추가만, 기존 소비자 무시) |
| `GET /api/v1/agents/my` | READ | `AgentChatLayout`(사이드바·선택 에이전트) · 스토어 "내 에이전트" 탭 · 서브에이전트 후보? (확인 필요: `AGENT_AVAILABLE_SUB_AGENTS`는 별도 엔드포인트) | Needs verification — 응답 크기 증가·배치 조회 |
| `AgentDefinitionRepository.update()` | UPDATE | create/update/fork/auto_fork/스킬 동기화 등 다수 | Needs verification — `openers=None` 기본으로 기존 호출 경로 무변경 보장 |
| `AgentDefinitionRepository.find_by_id()` | READ | run_agent · get · list_my · fork · 스케줄 · 웹훅 등 광범위 | Needs verification — 실행 hot path(run_agent)에서 오프너를 불필요하게 로드하지 않도록 lazy/별도 조회 |
| `SuggestionCards` | RENDER | `MessageList.EmptyMessages`(일반 채팅) · `ChatPage.EmptyAgentState` | None (prop 미전달 시 기존 동작) |
| `toAgentSummary` | TRANSFORM | `AgentChatLayout` | None (optional 필드 전달) |
| 에이전트 삭제 | DELETE | `DELETE /api/v1/agents/{id}` (status=deleted 소프트 삭제?) | Needs verification — 소프트 삭제라면 CASCADE가 발동하지 않음, 행 잔존은 무해하나 Design에 명시 |

### 6.3 Verification

- [ ] 위 "Needs verification" 4건을 Design 단계에서 코드로 확정
- [ ] 인증/권한 변경 없음 (기존 can_edit 가드 그대로)
- [ ] 기존 쿼리·뮤테이션 무변경 (optional 추가만)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter | ☐ |
| Dynamic | ☐ |
| **Enterprise** (기존 — domain/application/infrastructure/api 계층 + DI) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 저장 구조 | JSON 컬럼 / 별도 테이블 | **별도 테이블 `agent_opener`** | 사용자 결정. 행 id·sort_order 보유로 후속(클릭 통계·개별 수정) 확장 여지 |
| 수정 의미론 | 개별 CRUD / 목표 상태 전체 교체 | **전체 교체** (`agent_skill` 동기화와 동일) | 저장 버튼 통합 결정과 정합, 순서는 배열 순서 |
| 리포지토리 배치 | AgentDefinitionRepository 확장 / 별도 AgentOpenerRepository | Design에서 결정 (기본안: 별도 리포지토리 + 포트, agent_skill 선례) | 실행 hot path `find_by_id`에 오프너 로드를 섞지 않음 |
| 도메인 엔티티 필드 | `openers: list[str] \| None` | None = 미로드/미변경 | `middleware_types` 관례 — update 시 None이면 동기화 생략 |
| 채팅 데이터 소스 | 목록 확장 / 상세 호출 | **`/agents/my` 응답 확장** | 사용자 결정. 추가 요청 0, 단 배치 조회 필수 |
| 클릭 동작 | 즉시 전송 / 입력창 채우기 | **즉시 전송** | 기존 `onSuggestionClick` 재사용 |
| 프론트 상태 | 폼 staged / 탭 내 즉시 저장 | **폼 staged + 상단 저장** | 설정 탭 선례, 생성 모드에서도 등록 가능 |
| 검증 위치 | 프론트만 / 백엔드만 / 양쪽 | **도메인 정책이 SoT + 프론트는 UX 가드** | 규칙 상수는 백엔드 `OpenerPolicy`, 프론트 `types/` 상수 1곳 |
| 테스트 | pytest / Vitest+RTL+MSW | 기존 그대로 | — |

### 7.3 Clean Architecture Approach

```
idt/
  db/migration/V080__create_agent_opener.sql
  src/domain/agent_builder/          OpenerPolicy (검증), AgentDefinition.openers
  src/domain/agent_opener/            (Design 선택 시) AgentOpenerRepositoryInterface
  src/infrastructure/agent_opener/    AgentOpenerModel, AgentOpenerRepository
  src/application/agent_builder/      schemas(openers), create/update/get/list_my/fork use case
  src/api/main.py                     DI
idt_front/src/
  types/agentBuilder.ts, types/agent.ts, constants/ (OPENER 상수)
  components/agent-builder/opener/OpenerPanel.tsx (+test)
  components/agent-builder/AgentTestPanel.tsx
  components/chat/MessageList.tsx (SuggestionCards items prop)
  pages/ChatPage/index.tsx (EmptyAgentState 분기)
  pages/AgentBuilderPage/index.tsx (페이로드·프라임)
  utils/agentDetailMapping.ts
  services/agentSubscriptionService.ts (toAgentSummary)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 3종 (루트·idt·idt_front) 코딩 규칙
- [x] ESLint / Prettier / tsconfig (idt_front)
- [x] pytest + `uv run python -m pytest` (idt, `uv run pytest`는 차단)
- [x] Flyway 마이그레이션 + DDL COMMENT 검사 테스트
- [x] TDD 공통 원칙 (테스트 선행)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| Naming | 존재 | 테이블 `agent_opener`, API 필드 `openers`, 프론트 폼 `openers`, 컴포넌트 `OpenerPanel` | High |
| 상수 위치 | 존재 (idt_front 규칙) | `OPENER_LIMITS = { MAX_COUNT: 12, MAX_LENGTH: 200 } as const` → `src/types/` 또는 `src/constants/`, 컴포넌트 파일 export 금지 | High |
| 마이그레이션 | 존재 | V080, COLLATE 미명시, COMMENT 최상위 콤마 금지 | High |
| 에러 처리 | 존재 | 422 detail은 기존 `ApiError(message,status,code)` 경로로 표시 | Medium |

### 8.3 Environment Variables Needed

없음 (신규 env 0).

### 8.4 Pipeline Integration

해당 없음 (PDCA 단일 기능 사이클).

---

## 9. Next Steps

1. [ ] `/pdca design agent-opener` — 리포지토리 분리 여부·소프트 삭제 확인·배치 조회 쿼리·OpenerPanel 구조 확정, Session Guide(module-1/2/3)
2. [ ] module-1 백엔드(TDD) → 로컬 V080 수동 적용 + 실런 스모크
3. [ ] module-2 빌더 탭 → module-3 채팅 빈 상태
4. [ ] `/pdca analyze agent-opener`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-24 | 초안 — 코드 조사 + 사용자 확정 결정 7건 반영 | 배상규 |
