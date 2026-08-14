---
template: plan
version: 1.3
feature: agent-create-entry
---

# agent-create-entry Planning Document

> **Summary**: 사이드바 `+새 에이전트`를 빈 스튜디오가 아닌 "무엇을 만들고 싶은지 설명하는" 전용 진입 화면(`/agent-builder/new`)으로 연결하고, 그 설명을 기존 compose API로 초안화해 스튜디오에 프리필한다.
>
> **Project**: sangplusbot (idt_front)
> **Author**: tkdrb136@gmail.com
> **Date**: 2026-08-12
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `+새 에이전트`를 누르면 곧바로 내 에이전트 목록(그리고 `새로 만들기` → 빈 스튜디오)이 나온다. 처음 만드는 사용자는 이름·지침·도구·모델을 스스로 채워야 하고, 이를 대신해 주는 자연어 조합(compose)은 스튜디오 안쪽 `Fix 에이전트` 탭에 숨어 있어 발견되지 않는다. |
| **Solution** | 전용 진입 화면 `/agent-builder/new`를 신설한다. 히어로 + 설명 입력창(전송) + `에이전트 직접 만들기` / `에이전트 가져오기(준비 중)` 2개 카드. 전송 시 기존 `POST /api/v1/agents/compose`를 호출해 HITL 질문에 답하고, 초안이 나오면 스튜디오 폼에 프리필한 상태로 진입한다. **백엔드 신규 개발 없음.** |
| **Function/UX Effect** | 첫 화면이 "빈 폼"에서 "한 문장 설명"으로 바뀐다. 이미 존재하는 compose·HITL·초안 적용 로직이 발견 가능한 위치로 승격되어, 신규 사용자의 첫 에이전트 생성까지 걸리는 입력 부담이 크게 줄어든다. |
| **Core Value** | 이미 만들어 둔 자연어 조합 파이프라인의 **발견성**을 확보한다 — 새 기능을 만드는 게 아니라, 묻혀 있던 기능을 진입점으로 끌어올리는 작업. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 생성 진입점이 빈 폼이라 초보 사용자가 막히고, 이미 구현된 자연어 조합(compose+HITL)이 스튜디오 내부 탭에 묻혀 있다 |
| **WHO** | P2(에이전트 소유자/KB 운영자) 중 **처음 에이전트를 만드는 사용자**. 기존 숙련 사용자는 기존 경로(목록 → 새 에이전트)가 그대로 유지되어 영향 없음 |
| **RISK** | 진입 화면(신규 라우트)과 스튜디오(`AgentBuilderPage` 내부 `view` 상태) 사이의 **초안 전달(state handoff)** — 여기서 상태를 잃거나 이중 소스가 생기면 기존 저장 경로까지 깨진다 |
| **SUCCESS** | 사이드바 `+새 에이전트` → 설명 1문장 → (필요 시 HITL 1라운드) → 이름/지침/도구/모델이 채워진 스튜디오 도달. 기존 목록/편집/저장 회귀 0건 |
| **SCOPE** | 프론트 전용 3모듈: (1) 라우트+진입 화면 셸, (2) compose 연동 + HITL 답변, (3) 초안 → 스튜디오 핸드오프. Import는 UI만 비활성 노출 |

---

## 1. Overview

### 1.1 Purpose

에이전트 생성의 **첫 화면**을 "빈 설정 폼"에서 "만들고 싶은 것을 설명하는 화면"으로 바꾼다. 설명은 기존 `POST /api/v1/agents/compose`로 보내 초안(system_prompt / tool_ids / workers / model / temperature)을 받고, 사용자가 검토·저장할 수 있도록 스튜디오에 프리필한다.

### 1.2 Background

현재 코드 기준 사실관계 (구현 전 확인 완료):

| 항목 | 현재 상태 | 위치 |
|------|-----------|------|
| 사이드바 `+새 에이전트` | `navigate('/agent-builder')` — 목록 뷰로 이동 | `idt_front/src/components/layout/AppSidebar.tsx:97` |
| `/agent-builder` | 단일 컴포넌트가 `view: 'list' \| 'create' \| 'edit'` 내부 상태로 목록/스튜디오를 전환 (라우트 분리 없음) | `pages/AgentBuilderPage/index.tsx:29,63` |
| 자연어 조합 | `POST /api/v1/agents/compose` — **무저장 초안**, `status: draft \| needs_clarification`, `coverage: full \| partial \| none` | `idt/src/api/routes/agent_composer_router.py:29`, `idt/src/application/agent_composer/schemas.py:69` |
| compose 노출 위치 | 스튜디오 안 `Fix 에이전트` 탭에서만 | `components/agent-builder/AgentTestPanel.tsx:58`, `fix/FixAgentPanel.tsx` |
| HITL 질문 UI | **이미 구현됨** (선택지 + 자유입력 + 건너뛰기) | `fix/ClarifyQuestionCard.tsx` (120줄) |
| 초안 → 폼 반영 | **이미 구현됨** (`handleApplyDraft` — 도구 ID 매핑·RAG 설정·빌트인 제외 부수효과 처리 포함) | `pages/AgentBuilderPage/index.tsx:371` |
| 에이전트 Import/Export | **존재하지 않음** (백엔드·프론트 모두) | — |
| 목록 접근 경로 | 사이드바 `에이전트 템플릿` → `/agent-builder` 로 별도 유지 | `AppSidebar.tsx:20` |

즉 이 작업은 **신규 기능 개발이 아니라 기존 자산의 재배치**다. compose·HITL·초안 적용은 이미 동작하며, 부족한 것은 (a) 전용 진입 화면과 (b) 진입 화면 → 스튜디오 초안 전달 경로뿐이다.

### 1.3 Related Documents

- 참조 화면: `docs/img/create_agent.png`
- 선행 기능: `fix-agent-composer`(compose 도입), `fix-agent-planner-hitl`(HITL 왕복), `compose-tool-instructions`(도구 ID 매핑)
- SoT: `docs/SOURCE-OF-TRUTH.md`, 규칙: `idt_front/CLAUDE.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] 신규 라우트 `/agent-builder/new` 등록 (`App.tsx` — `AgentChatLayout` 하위, ProtectedRoute 내부)
- [ ] 진입 화면 UI: 히어로(로고 + "생성하려는 에이전트에 대해 알려주세요" + 서브카피), 설명 textarea + 전송(▷) 버튼, 하단 카드 2개
- [ ] 사이드바 `+새 에이전트`(`AppSidebar.tsx:97`) → `/agent-builder/new` 로 변경
- [ ] 전송 시 `useComposeAgent`(기존 훅) 호출 + 로딩/에러 상태 표현
- [ ] `status === 'needs_clarification'` 시 **진입 화면에서** 질문 카드 렌더 → 답변 → 재-compose (`clarification_answers`, `clarification_round` 증가). 기존 `ClarifyQuestionCard` 재사용
- [ ] `status === 'draft'` 시 초안을 스튜디오 create 모드에 프리필하여 진입
- [ ] `coverage === 'none'` / compose 실패 시 진입 화면에 머물며 `missing_capabilities`·`notes` 안내 + `[다시 설명하기]` / `[그래도 직접 만들기]` 제공
- [ ] `에이전트 직접 만들기` 카드 → 빈 스튜디오(create 모드) 진입 (= 현재 `handleNew` 동작)
- [ ] `에이전트 가져오기` 카드 → **비활성(disabled) + "준비 중" 표기**로 노출만
- [ ] 스튜디오 `[취소]`: 진입 화면을 거쳐 왔으면 `/agent-builder/new`로, 목록에서 들어온 편집이면 기존대로 목록으로
- [ ] 테스트: 진입 화면 컴포넌트 테스트 + compose/HITL MSW 시나리오 + 핸드오프 회귀 테스트

### 2.2 Out of Scope

- **에이전트 Import/Export 실제 구현** (JSON 스키마 정의, 내보내기 버튼, 업로드/검증/ID 미존재 처리) — 별도 기능으로 분리
- 백엔드 변경 일체 (compose 스키마·프롬프트·플래너 로직 무수정)
- 목록 헤더 `+새 에이전트`(`index.tsx:458`), 목록 빈 상태 `새 에이전트 만들기`(`index.tsx:602`), 사이드바 빈 상태 `에이전트 만들기`(`AppSidebar.tsx:173`) — **기존 동작(빈 스튜디오 직행) 유지**
- 스튜디오 내 `Fix 에이전트` 탭 제거/변경 (진입 화면과 병존)
- 목록 뷰 UI 리뉴얼, `/agent-store` 변경
- 진입 화면에서의 모델 선택 UI (compose가 `llm_model_id` 미전송 시 서버 기본값 사용)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `/agent-builder/new` 라우트가 인증 사용자에게 스크린샷 레이아웃의 진입 화면을 렌더한다 | High | Pending |
| FR-02 | 사이드바 `+새 에이전트`는 `/agent-builder/new`로 이동한다 (다른 3개 진입 버튼은 불변) | High | Pending |
| FR-03 | 설명 textarea는 공백만 입력 시 전송 비활성, 1~1000자만 허용 (백엔드 `max_length=1000`과 일치) | High | Pending |
| FR-04 | 전송 시 `POST /api/v1/agents/compose`를 호출하고 진행 중 로딩 상태를 표시한다 (중복 전송 차단) | High | Pending |
| FR-05 | `status='needs_clarification'` 응답 시 질문 카드를 진입 화면에 표시하고, `[계속]`으로 답변을 `clarification_answers`에 담아 재-compose 한다 (`clarification_round` +1) | High | Pending |
| FR-06 | `[건너뛰기]`는 빈 answer로 재-compose 하여 초안을 강제한다 (기존 `ClarifyQuestionCard` 계약 준수) | Medium | Pending |
| FR-07 | `status='draft'`이고 `coverage!=='none'`이면 초안을 create 모드 폼에 반영한 상태로 스튜디오에 진입한다. 반영 규칙은 기존 `handleApplyDraft`와 **동일 로직을 공유**한다 (중복 구현 금지) | High | Pending |
| FR-08 | `coverage='none'` 또는 compose 실패(4xx/5xx/네트워크) 시 진입 화면 유지 + `missing_capabilities`/`notes` 안내 + `[다시 설명하기]`/`[그래도 직접 만들기]` 제공 | High | Pending |
| FR-09 | `에이전트 직접 만들기` 카드는 빈 스튜디오(create)로 진입한다 | High | Pending |
| FR-10 | `에이전트 가져오기` 카드는 disabled 상태로 "준비 중"을 명시하며 클릭해도 아무 동작 없음 | Medium | Pending |
| FR-11 | 스튜디오 `[취소]`는 진입 화면 경유 시 `/agent-builder/new`, 목록 경유 시 `/agent-builder`로 돌아간다 | Medium | Pending |
| FR-12 | 진입 화면에서 초안 프리필로 진입해도 **저장은 사용자가 `[저장]`을 눌러야만** 발생한다 (자동 생성 금지) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 회귀 안전성 | 기존 목록/생성/편집/삭제/저장 경로 무변경 | `AgentBuilderPage/index.test.tsx`, `AgentBuilderStudio.test.tsx` 전량 통과 |
| 테스트 | 신규 컴포넌트/훅 커버리지 확보, compose 성공·HITL·coverage none·실패 4시나리오 MSW 테스트 | Vitest + RTL + MSW |
| 접근성 | textarea 라벨, 버튼 `aria-disabled`, 로딩 시 상태 안내 텍스트 | 수동 확인 + RTL 쿼리(role/name) |
| 성능 | compose 대기 중 UI 블로킹 없음, 응답 지연 시 취소 가능(선택) | 수동 확인 |
| 일관성 | violet-600 계열 기존 토큰·라운드(rounded-2xl)·Tailwind 클래스 컨벤션 준수 | 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-12 모두 구현
- [ ] 신규 코드 TDD (테스트 선작성 → 실패 확인 → 구현)
- [ ] 기존 `AgentBuilderPage`/`StudioLayout` 테스트 전량 통과 (회귀 0)
- [ ] 사이드바 `+새 에이전트` → 설명 입력 → 스튜디오 프리필 → 저장까지 수동 E2E 1회 성공
- [ ] `docs/SOURCE-OF-TRUTH.md` 화면 총람에 `/agent-builder/new` 반영 필요 여부 확인 후 사용자에게 보고

### 4.2 Quality Criteria

- [ ] `npm run lint` 0 에러
- [ ] `npm run build` (tsc 포함) 성공
- [ ] `npm run test` 전량 통과
- [ ] 백엔드 변경 파일 0개 (`git diff --stat idt/` 가 비어 있음)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **초안 핸드오프 파손** — 진입 화면은 라우트, 스튜디오는 `AgentBuilderPage` 내부 `view` 상태라 경계를 넘겨야 함. 잘못 설계하면 새로고침 시 초안 유실 또는 폼 상태 이중 소스 발생 | High | High | Design 단계에서 3안 비교(① 같은 페이지 컴포넌트가 라우트만 분리 ② `navigate(state)` 전달 ③ 전역 스토어)로 **명시 결정**. 초안은 휘발성으로 정의하고 새로고침 시 진입 화면으로 복귀(빈 상태)를 정상 동작으로 규정 |
| `handleApplyDraft` 로직 중복 구현 — 진입 화면에서 별도로 초안→폼 변환을 짜면 도구 ID 매핑·RAG 설정·빌트인 제외 부수효과가 어긋남 | High | Medium | 변환 함수를 `utils`로 추출해 **단일 구현을 양쪽이 공유**. 추출 전후로 기존 테스트 통과 확인 |
| HITL 라운드 상태(`clarification_round`, 이전 Q/A 에코백)를 진입 화면에서 잘못 관리해 무한 질문 루프 | Medium | Medium | 서버가 정책으로 clamp(`le=10`)하지만 클라이언트도 최대 라운드 상한 + `[건너뛰기]` 항상 노출로 탈출구 보장 |
| 진입점 변경으로 기존 사용자가 목록을 못 찾음 | Medium | Low | 사이드바 `에이전트 템플릿` → `/agent-builder`(목록) 경로 유지 확인 완료. 진입 화면에도 목록으로 가는 링크 배치 검토 |
| compose 응답 지연(LLM 호출)으로 사용자가 멈춘 것으로 오인 | Medium | Medium | 로딩 상태를 진행 문구와 함께 명시, 중복 전송 차단, 실패 시 재시도 버튼 |
| `에이전트 가져오기` 비활성 버튼이 "곧 됨"으로 오인 | Low | Medium | "준비 중" 문구 명시, disabled 스타일 적용 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `idt_front/src/App.tsx` | Route | `/agent-builder/new` 라우트 추가 (기존 라우트 무변경) |
| `idt_front/src/components/layout/AppSidebar.tsx:97` | UI | `+새 에이전트` 목적지 `/agent-builder` → `/agent-builder/new` |
| `idt_front/src/pages/AgentBuilderPage/index.tsx` | Page | 초안 프리필 진입 수용 + `[취소]` 복귀 지점 분기. `handleApplyDraft` 변환부 추출 |
| `idt_front/src/pages/AgentCreateEntryPage/*` (신규) | Page/Component | 진입 화면 셸 + compose 연동 + HITL 렌더 |
| `idt_front/src/hooks/useAgentComposer.ts` | Hook | 신규 소비자 추가 (코드 변경은 없을 전망) |
| **백엔드 (`idt/`)** | — | **변경 없음** |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `/agent-builder` 라우트 | READ | `AppSidebar.tsx:20` (에이전트 템플릿), `AppSidebar.tsx:173` (빈 상태 버튼) | None — 목록 뷰 유지 |
| `AppSidebar` `+새 에이전트` | NAV | `AppSidebar.tsx:97` | **Breaking(의도된 변경)** — 목적지 변경 |
| `AgentBuilderPage.view='create'` | CREATE | `handleNew()` (`index.tsx:111`), 목록 헤더 버튼(`:458`), 빈 상태 버튼(`:602`) | Needs verification — 진입 경로가 하나 늘어남, 기존 3경로는 동작 불변이어야 함 |
| `handleApplyDraft` | UPDATE(form) | `StudioLayout` → `AgentTestPanel` → `FixAgentPanel` → `onApplyDraft` (`index.tsx:496`) | Needs verification — 변환 로직 추출 리팩터링 대상. 기존 호출부 시그니처 유지 필수 |
| `POST /api/v1/agents/compose` | CREATE(draft) | `useComposeAgent` → `FixAgentPanel.tsx` | Needs verification — 소비자 2개로 증가. 서버 계약 무변경 |
| `POST /api/v1/agents` (저장) | CREATE | `handleSave` (`index.tsx:~194`) | None — 저장 경로 무변경 |
| MSW 핸들러 | TEST | `__tests__/mocks/handlers.ts:993` | Needs verification — HITL/coverage none 시나리오 핸들러 추가 필요 |

### 6.3 Verification

- [ ] 목록 헤더·목록 빈 상태·사이드바 빈 상태 3개 버튼이 여전히 빈 스튜디오로 직행하는지 테스트
- [ ] `FixAgentPanel`의 초안 적용이 리팩터링 후에도 동일 결과(도구 매핑/RAG/빌트인 제외)인지 기존 테스트로 검증
- [ ] 편집 모드 진입/취소/저장 흐름 무변경 확인
- [ ] 비인증 사용자의 `/agent-builder/new` 직접 접근이 로그인으로 리디렉트되는지 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| Starter | — | ☐ |
| **Dynamic** | Feature 기반 모듈 + 자체 FastAPI 백엔드 | ☑ |
| Enterprise | — | ☐ |

프론트엔드 단독 변경이며 기존 `idt_front` 구조(`pages/`, `components/`, `hooks/`, `services/`, `types/`)를 그대로 따른다.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 진입 방식 | 목록 뷰 대체 / 별도 라우트 / 목록 상단 히어로 | **별도 라우트 `/agent-builder/new`** | 기존 목록·편집 경로를 건드리지 않고 스크린샷의 전체화면 집중형 UX 확보 |
| 전송 후 동작 | 초안→프리필(무저장) / 즉시 생성 / 대화형 지속 | **초안 → 스튜디오 프리필(무저장)** | compose가 이미 무저장 계약이며, 검토 없이 저장하면 목록 오염 |
| Import 범위 | 이번 포함 / 제외 | **제외 (버튼 비활성 노출)** | export가 없어 실사용성이 없고 백엔드 신규 엔드포인트가 필요 |
| HITL 위치 | 진입 화면 / 스튜디오 Fix 탭 | **진입 화면** | "설명하면 단계별로 안내해 드리겠습니다" 카피와 일치. `ClarifyQuestionCard` 재사용 |
| 실패 처리 | 진입 화면 유지 / 그대로 진입 | **진입 화면 유지 + 안내** | 빈 스튜디오로 떨어지면 사용자가 이유를 모름 |
| 취소 복귀 | 진입 화면 / 항상 목록 | **경유 경로에 따라 분기** | 설명을 다시 쓰려는 사용자의 자연스러운 되돌아가기 |
| 초안 전달 방식 | 동일 컴포넌트 / router state / 전역 스토어 | **Design 단계에서 결정** | 최대 리스크 지점 — 3안 비교 후 확정 |
| State/API/Style/Test | Zustand / TanStack Query / Tailwind / Vitest+RTL+MSW | 기존 스택 유지 | `idt_front/CLAUDE.md` 준수 |

### 7.3 Clean Architecture Approach

```
idt_front/src/
├── App.tsx                          # + /agent-builder/new
├── pages/
│   ├── AgentCreateEntryPage/        # (신규) 진입 화면
│   │   └── index.tsx                #   히어로 · 입력 · 카드 2개 · HITL · 실패 안내
│   └── AgentBuilderPage/index.tsx   # 초안 수용 + 취소 복귀 분기
├── components/agent-builder/fix/
│   └── ClarifyQuestionCard.tsx      # (재사용, 무변경)
├── hooks/useAgentComposer.ts        # (재사용)
└── utils/
    └── composeDraftToForm.ts        # (신규 추출) handleApplyDraft 변환 로직 단일화
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] 루트 `CLAUDE.md` + `idt_front/CLAUDE.md` 존재
- [x] TypeScript / ESLint / Vite 설정 존재
- [x] Vitest + RTL + MSW 테스트 인프라 존재
- [x] API 엔드포인트 상수 `src/constants/api.ts` (`AGENT_COMPOSE` 이미 등록됨)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| Naming | exists | 신규 페이지 `AgentCreateEntryPage` (PascalCase 디렉토리 + index.tsx) | High |
| Folder structure | exists | 진입 화면 전용 하위 컴포넌트는 `pages/AgentCreateEntryPage/components/` | Medium |
| Error handling | exists | compose 실패 UI 문구 규격(재시도/우회) | Medium |
| Route naming | exists | `/agent-builder/new` — 기존 `/collections/:id/documents` 등 중첩 패턴과 일치 | Low |

### 8.3 Environment Variables Needed

없음 (기존 `VITE_API_BASE_URL` 사용).

---

## 9. Next Steps

1. [ ] 본 Plan 검토·승인
2. [ ] `/pdca design agent-create-entry` — 특히 **초안 핸드오프 3안 비교**가 핵심 산출물
3. [ ] TDD 구현 (`/pdca do agent-create-entry`)
4. [ ] Gap 분석 (`/pdca analyze agent-create-entry`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-12 | 초안 작성 (사용자 확정 7개 결정 반영) | tkdrb136@gmail.com |
