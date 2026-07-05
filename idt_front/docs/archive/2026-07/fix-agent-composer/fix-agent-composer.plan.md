# fix-agent-composer Planning Document

> **Summary**: /agent-builder 우측 패널의 'Fix 에이전트' 탭을 활성화하여, 채팅으로 자연어 요청 → compose API 응답(초안 카드)을 [적용하기]로 좌측 폼에 셋팅하는 풀스택 기능. 백엔드 compose API에 `current_config`/`history` 확장을 포함한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-07-04
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 폼(이름/프롬프트/도구/모델/온도)을 사용자가 직접 채워야 하며, nl-agent-composer 백엔드(compose API)는 완성됐지만 프론트 진입점이 없다. 특히 "만든 설정에 tavily 도구 추가해줘" 같은 증분 수정은 현재 API가 현재 설정을 몰라 지원 불가. |
| **Solution** | Fix 에이전트 탭에 채팅 UI를 붙이고, compose API를 `current_config`(현재 폼 스냅샷)·`history`(이전 대화) 확장. 응답은 채팅 내 초안 카드(이름/도구/coverage/미커버 역량)로 보여주고 [적용하기] 클릭 시에만 좌측 폼에 반영. |
| **Function/UX Effect** | 자연어 한 문장으로 폼 프리필 + 대화를 이어가며 증분 수정("검색 도구 추가해줘")이 가능. 실수로 폼이 덮어써지지 않도록 명시적 적용 단계 제공. MCP 도구도 폼→저장까지 일관 지원(기존 전송 제외 필터 제거). |
| **Core Value** | 에이전트 생성 진입 장벽을 "폼 작성"에서 "대화 한 줄"로 낮추고, 이미 구축된 nl-agent-composer 백엔드 투자를 실제 UI 가치로 전환. |

---

## 1. Overview

### 1.1 Purpose

`/agent-builder` 스튜디오 우측 패널의 **Fix 에이전트 탭**(현재 `enabled: false` placeholder)을 활성화한다.
사용자가 채팅으로 자연어 요청을 보내면 `POST /api/v1/agents/compose` 응답으로 **좌측 폼 값들(name, systemPrompt, tools, model, temperature)을 셋팅**한다. 시안: `docs/img/fix_agent.png`.

### 1.2 Background

- 백엔드 **nl-agent-composer**(compose API)는 2026-07 완료·아카이브됨 (`idt/docs/archive/2026-07/nl-agent-composer/`). 그러나 프론트에서 이를 호출하는 화면이 없어 기능이 사장된 상태.
- 현재 compose API는 `user_request`만 받는 **무상태 단발성**이라, 시안의 예시("tavily 검색 도구 추가해줘")처럼 **현재 폼 설정에 대한 증분 수정**을 표현할 수 없다.
- 사용자 결정사항 (2026-07-04 확정):
  1. **풀스택** — compose API에 `current_config` 확장을 포함해 증분 수정을 정식 지원
  2. 응답은 **초안 카드 + [적용하기] 버튼** — 클릭 시에만 폼 반영
  3. **멀티턴** — 이전 대화 맥락 포함, '새 대화' 버튼으로 초기화
  4. 프론트 생성 로직의 **MCP 도구 전송 제외 필터 제거** 포함 (저장 API가 `mcp_{server_id}`를 이미 수용)

### 1.3 Related Documents

- API 스펙: `idt_front/docs/api/nl-agent-composer.md` (이번 확장분 반영 갱신 필요)
- 백엔드 선행 기능 문서: `idt/docs/archive/2026-07/nl-agent-composer/` (plan/design/analysis/report)
- UI 시안: `idt_front/docs/img/fix_agent.png`
- 유사 UI 선례: `src/components/agent-builder/TestChatView.tsx` (우측 패널 채팅), `src/components/agent-builder/schedule/SchedulePanel.tsx` (탭 콘텐츠 + 콜백 배선)

---

## 2. Scope

### 2.1 In Scope

**백엔드 (idt/)**

- [ ] `ComposeAgentRequest` 확장: `current_config`(현재 폼 스냅샷, nullable) + `history`(이전 대화 턴, nullable)
- [ ] `AgentComposer` 시스템 프롬프트 확장: 현재 설정 블록 주입 + 증분 수정 규칙(요청된 변경만 적용, 나머지 유지)
- [ ] `compose_agent_use_case`: current_config 통과 배선, 기존 서버 보정(환각 tool_id 제거·상한 절단·coverage 재산정) 유지
- [ ] pytest 테스트 (스키마 검증, 증분 수정 프롬프트 구성, 유스케이스)

**프론트엔드 (idt_front/)**

- [ ] `src/types/agentComposer.ts` — Request/Response 타입 (백엔드 스키마 동기화)
- [ ] `src/constants/api.ts` — `AGENT_COMPOSE` 엔드포인트 상수
- [ ] `src/services/agentComposerService.ts` — `composeAgent()` (authClient 사용)
- [ ] `src/hooks/useAgentComposer.ts` — `useComposeAgent` mutation (TanStack Query)
- [ ] `src/components/agent-builder/fix/FixAgentPanel.tsx` — 채팅 UI (시안 준수: 빈 상태 아이콘+예시 프롬프트, 하단 입력창 "에이전트를 어떻게 수정할지 설명하세요...", Enter 전송/Shift+Enter 줄바꿈, 우상단 '새 대화' 버튼)
- [ ] `src/components/agent-builder/fix/ComposeDraftCard.tsx` — 초안 카드 (이름/도구 목록/coverage 뱃지/missing_capabilities/flow_hint/notes + [적용하기]·[무시] 버튼)
- [ ] `AgentTestPanel.tsx` — `fix` 탭 `enabled: true` 전환 + FixAgentPanel 렌더 + `onApplyDraft` 콜백 배선 (StudioLayout → AgentBuilderPage)
- [ ] `AgentBuilderPage/index.tsx` — 초안 적용 핸들러: `name`/`systemPrompt`/`tools`/`temperature` 반영, `llm_model_id`→`model_name` 매핑(useLlmModels 목록 기준)
- [ ] MCP 필터 제거 — `handleSave`의 `source !== 'mcp'` 전송 제외 로직 삭제 + 저장 422("등록되지 않았거나 비활성화된 MCP 도구...") 에러 메시지 노출
- [ ] Vitest + MSW 테스트 (compose 핸들러, FixAgentPanel, ComposeDraftCard, 폼 반영 통합)
- [ ] `docs/api/nl-agent-composer.md` 확장분 갱신

### 2.2 Out of Scope

- **edit 모드에서 도구 변경 저장** — `PUT` UpdateBuilderAgentRequest가 `tool_ids`를 지원하지 않음. Fix 탭 자체는 create/edit 모두 노출하되, edit 모드 초안 적용 시 도구 변경분은 폼에 반영해도 저장되지 않으므로 카드에 안내 문구 표시. tool_ids 업데이트 API는 후속 과제.
- MCP 서버의 **개별 도구 필터링** (compose는 서버 단위 `mcp_{server_id}` — 백엔드 후속 과제로 이미 명시됨)
- compose 응답의 `workers`/`tool_config`를 폼의 `toolConfigs`로 매핑 (RAG 세부 설정 등은 사용자가 폼에서 직접 구성)
- 초안 자동 저장, 대화 서버 영속화 (대화는 로컬 state — TestChatView와 동일 정책)
- 스트리밍 응답 (compose는 단건 JSON 응답 유지)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | **compose API 확장**: `current_config: { name, system_prompt, tool_ids, llm_model_id, temperature } \| null`, `history: [{ role: "user"\|"assistant", content }] \| null`(최근 최대 6턴, 턴당 500자 서버 절단) 추가. 기존 필드·응답 스키마는 하위호환 유지 | High | Pending |
| FR-02 | **증분 수정 조합**: `current_config`가 있으면 LLM 프롬프트에 현재 설정 블록을 주입하고 "요청된 변경만 적용, 나머지 설정 유지" 규칙 적용. 기존 서버 보정(환각 제거/최대 5개 도구/4000자 프롬프트/coverage 재산정)은 확장 후에도 동일 적용 | High | Pending |
| FR-03 | **Fix 탭 활성화 + 채팅 UI**: 시안(fix_agent.png) 레이아웃 — 빈 상태(렌치 아이콘, "새 에이전트 수정", 예시 프롬프트 3개 — 클릭 시 입력창 삽입), 하단 입력창, Enter 전송/Shift+Enter 줄바꿈, 로딩 인디케이터 | High | Pending |
| FR-04 | **초안 카드**: compose 응답을 assistant 메시지로 렌더 — 이름, 도구 칩(내부/MCP 구분), coverage 뱃지(full/partial/none), missing_capabilities 목록, flow_hint, notes. [적용하기] 클릭 시에만 좌측 폼 반영, [무시] 시 카드 유지·미적용 | High | Pending |
| FR-05 | **폼 반영 매핑**: name→`form.name`, system_prompt→`form.systemPrompt`, tool_ids→`form.tools`, temperature→`form.temperature`, llm_model_id→models 목록에서 `model_name` 역매핑 후 `form.model`(미등록 id면 모델은 미변경 + 카드에 표시) | High | Pending |
| FR-06 | **멀티턴 + 새 대화**: 매 요청에 현재 폼 스냅샷(`current_config`)과 이전 대화(`history`)를 함께 전송. '새 대화' 클릭 시 메시지·history 초기화 (폼은 유지) | High | Pending |
| FR-07 | **coverage 분기**: `none`이면 초안 카드 대신 안내 메시지 + missing_capabilities/notes 표시([적용하기] 미노출). `partial`이면 카드에 미커버 역량 경고 표시 | Medium | Pending |
| FR-08 | **MCP 필터 제거**: `AgentBuilderPage` handleSave의 MCP 전송 제외 필터 삭제, ToolPickerModal의 MCP 선택 차단(존재 시) 해제, 저장 422 에러 메시지를 결과 다이얼로그에 노출 | Medium | Pending |
| FR-09 | **에러 처리**: compose 422/500 시 채팅에 에러 메시지 버블 표시(대화 유지, 재시도 가능). 요청 중 중복 전송 방지 | Medium | Pending |
| FR-10 | **edit 모드 제약 안내**: edit 모드에서 초안의 tool_ids가 현재 폼과 다르면 카드에 "도구 변경은 수정 화면에서 저장되지 않습니다" 안내 표시 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 성능 | compose 응답까지 UI 블로킹 없음 (mutation pending 상태 표시) | 수동 확인 + 테스트 |
| 하위호환 | `current_config`/`history` 미전송 시 기존 compose 동작과 동일 (기존 pytest 전체 통과) | pytest 회귀 |
| 보안 | Bearer JWT(authClient) 경유, API 키 등 비밀값 프론트 미노출 | 코드 리뷰 |
| 테스트 | 프론트 훅/유틸 80%+, 컴포넌트 60%+ (프로젝트 기준) | `npm run coverage` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-09 구현 완료 (FR-10은 Low — 여유 시)
- [ ] TDD 사이클 준수: 백엔드 pytest / 프론트 Vitest+RTL+MSW 테스트 선행 작성
- [ ] `npm run type-check`·`npm run lint` 통과, 프론트 테스트 `--pool=threads`로 통과
- [ ] `docs/api/nl-agent-composer.md` 확장분 반영
- [ ] 수동 검증: 새 에이전트 생성 흐름에서 "채팅 → 초안 카드 → 적용 → 저장" E2E 1회 성공

### 4.2 Quality Criteria

- [ ] 기존 compose·agent 생성 테스트 회귀 없음 (사전 실패 목록 제외 — memory 참조)
- [ ] 폼 반영은 [적용하기] 클릭 시에만 발생 (자동 덮어쓰기 없음을 테스트로 보증)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| LLM이 증분 수정 시 기존 설정을 유지하지 않고 전체 재설계 | Medium | Medium | 프롬프트에 "변경 요청 외 설정 유지" 규칙 명시 + current_config 포함 케이스 pytest로 프롬프트 구성 검증. 서버 보정은 기존 로직 재사용 |
| `history` 추가로 요청 크기/토큰 증가 | Low | Medium | 최근 6턴·턴당 500자 서버 절단 (FR-01), 초안 카드 원문(JSON)은 history에 미포함 — assistant 턴은 요약 텍스트만 |
| edit 모드에서 도구 변경이 저장되지 않아 사용자 혼란 | Medium | High | FR-10 안내 문구 + Out of Scope 명시. tool_ids 업데이트 API는 후속 plan |
| MCP 필터 제거 후 비활성 MCP 도구로 저장 시 422 | Medium | Medium | 저장 에러 메시지를 결과 다이얼로그에 그대로 노출(백엔드가 한국어 메시지 제공), 초안 카드에서 MCP 도구를 시각 구분 |
| `llm_model_id` ↔ 폼 `model`(model_name) 불일치 매핑 실패 | Low | Medium | FR-05: 역매핑 실패 시 모델 필드 미변경 + 카드에 표시 (silent 실패 금지) |
| compose 지연(LLM 1회 호출)이 길 때 사용자 이탈 | Low | Low | 채팅 로딩 인디케이터(TypingIndicator 패턴 재사용) + 전송 버튼 비활성화 |

---

## 6. Architecture Considerations

### 6.1 Project Level

기존 워크스페이스 구조 유지 — **Dynamic** (프론트 SPA + FastAPI 백엔드). 신규 레벨 결정 없음.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 증분 수정 지원 방식 | 프론트 텍스트 합성 우회 / **백엔드 `current_config` 확장** | 백엔드 확장 | 사용자 결정(풀스택). 1000자 제한·파싱 취약성 회피, 구조화된 컨텍스트로 LLM 정확도 확보 |
| 대화 맥락 전달 | 프론트 user_request 합성 / **구조화 `history` 필드** | `history` 필드 | current_config 확장과 함께 요청 스키마를 한 번에 확장하는 편이 하위호환·검증 측면에서 깔끔 |
| 폼 반영 시점 | 즉시 자동 반영 / **초안 카드 + [적용하기]** | 초안 카드 | 사용자 결정. 편집 중 값 보호 |
| 채팅 상태 | 서버 영속 / **로컬 state** | 로컬 state | TestChatView와 동일 정책, compose 무저장 원칙 유지 |
| API 클라이언트 | client / **authClient** | authClient | compose는 `get_current_user` 인증 필수 |
| 상태관리 | Zustand / **TanStack Query mutation + 로컬 useState** | 후자 | 서버 상태는 단발 mutation, 대화는 패널 로컬 상태로 충분 (전역 공유 불필요) |
| 신규 라우터 여부 | 신규 / **기존 `agent_composer_router` 확장** | 기존 확장 | 엔드포인트 동일(`POST /compose`), 요청 스키마만 확장 |

### 6.3 변경 지점 요약

```
백엔드 (idt/):
  src/application/agent_composer/schemas.py      ← current_config/history 필드 추가
  src/application/agent_composer/composer.py     ← 프롬프트에 현재 설정/대화 블록 주입
  src/application/agent_composer/compose_agent_use_case.py ← 배선
  tests/... (agent_composer 관련)                 ← 확장 케이스 추가

프론트 (idt_front/):
  src/types/agentComposer.ts                     ← 신규
  src/constants/api.ts                           ← AGENT_COMPOSE 추가
  src/services/agentComposerService.ts           ← 신규
  src/hooks/useAgentComposer.ts                  ← 신규
  src/components/agent-builder/fix/FixAgentPanel.tsx      ← 신규 (채팅 UI)
  src/components/agent-builder/fix/ComposeDraftCard.tsx   ← 신규 (초안 카드)
  src/components/agent-builder/AgentTestPanel.tsx         ← fix 탭 활성화 + 배선
  src/components/agent-builder/StudioLayout.tsx           ← onApplyDraft 프로퍼티 전달
  src/pages/AgentBuilderPage/index.tsx                    ← 적용 핸들러 + MCP 필터 제거
  src/__tests__/mocks/handlers.ts                         ← compose 핸들러
```

---

## 7. Convention Prerequisites

- 기존 컨벤션 준수: `idt_front/CLAUDE.md` (컴포넌트/타입/서비스/훅 레이어링, queryKeys 팩토리, 디자인 토큰), `idt/CLAUDE.md` (클린 아키텍처 레이어)
- 신규 환경변수 없음
- 테스트: 프론트 vitest는 Windows에서 `--pool=threads` 사용 (알려진 forks 타임아웃 이슈)

---

## 8. Next Steps

1. [ ] Design 문서 작성 — `/pdca design fix-agent-composer` (요청/응답 스키마 확정, 프롬프트 블록 설계, 컴포넌트 계약, 폼 매핑 표)
2. [ ] 백엔드 → 프론트 순 구현 (TDD)
3. [ ] `/pdca analyze fix-agent-composer` gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-04 | Initial draft — 사용자 결정 4건(풀스택/초안카드/멀티턴/MCP필터제거) 반영 | 배상규 |
