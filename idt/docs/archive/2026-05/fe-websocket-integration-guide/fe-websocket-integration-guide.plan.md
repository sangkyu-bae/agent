# Frontend WebSocket Integration Guide — Planning Document

> **Summary**: 이미 구축된 백엔드 WebSocket 인프라(`/ws/echo`, `ConnectionManager`, JWT query-token auth)와 프론트엔드 `useWebSocket` 훅을 **실제로 어떻게 연결해서 사용하는지** 정립하는 가이드 및 첫 사용 사례 Plan
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-25
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | WebSocket 인프라(백엔드 `ConnectionManager`/`/ws/echo`, 프론트 `useWebSocket` 훅)는 이미 구축돼 있으나, **실제로 둘을 어떻게 연결해 사용하는지에 대한 가이드와 사용처가 0건**이다. 정의된 메시지 타입(`agent_step`/`chat_token`/`ingest_progress`)에 대한 publisher와 consumer가 모두 없다. |
| **Solution** | (1) WS URL 빌더 + 토큰 첨부 + 엔드포인트 상수의 표준 연동 패턴을 정의한 가이드 문서를 작성하고, (2) 가장 우선순위 높은 첫 사용 사례인 **Agent 실행 실시간 진행률 스트리밍(`/ws/agent/{run_id}`)** 을 PoC로 구현한다. |
| **Function/UX Effect** | 사용자가 Agent를 실행할 때 토큰/스텝 단위 진행 상황을 실시간으로 받아볼 수 있고, 이후 RAG 채팅·인제스트 진행률 등 다른 실시간 기능도 동일한 패턴으로 빠르게 추가 가능하다. |
| **Core Value** | "인프라는 있는데 아무도 안 쓰는" 상태를 해소하고, **한 번 정립한 표준 패턴으로 후속 실시간 기능을 1~2일 내 추가**할 수 있는 재사용 자산을 확보한다. |

---

## 1. Overview

### 1.1 Purpose

백엔드(`idt/`)와 프론트엔드(`idt_front/`)에 이미 존재하는 WebSocket 인프라를 **실제 프로덕션에서 사용**하기 위한 표준 연동 가이드를 만들고, 첫 번째 사용 사례를 PoC로 구현한다.

본 Plan은 두 가지를 동시에 다룬다.

1. **가이드(문서)** — 신규 실시간 기능을 추가할 때 따라야 할 표준 연결/인증/메시지 규약/에러 처리 패턴
2. **첫 사용 사례(코드)** — Agent 실행 실시간 진행률 스트리밍 (`/ws/agent/{run_id}`)

### 1.2 Background — 현재 인프라 현황 (As-Is)

#### 백엔드 (`idt/`)
| 영역 | 파일 | 현황 |
|------|------|------|
| Domain | `src/domain/websocket/interfaces.py` | `ConnectionManagerInterface` ABC 정의됨 |
| Domain | `src/domain/websocket/schemas.py` | `WSMessage`, `WSCloseCode`(1000/4001~4500), `WSConnection`, `WSMessageType` enum 정의됨 |
| Infra | `src/infrastructure/websocket/connection_manager.py` | `ConnectionManager` 구현 (개별/Room/Broadcast 송신, 최대 100 connections, dead-connection cleanup) |
| Infra | `src/infrastructure/websocket/auth.py` | `verify_ws_token` — query param `?token=` JWT 검증 (access token 전용) |
| API | `src/api/routes/ws_router.py` | `/ws/echo` 엔드포인트만 존재 (인증 + echo 동작 검증용) |
| Wiring | `src/api/main.py:2258-2259, 2501` | `ConnectionManager` 싱글톤 DI 등록 + 라우터 include 완료 |
| Tests | `tests/infrastructure/websocket/`, `tests/domain/websocket/` | 단위 테스트 존재 |

#### 프론트엔드 (`idt_front/`)
| 영역 | 파일 | 현황 |
|------|------|------|
| Hook | `src/hooks/useWebSocket.ts` | 범용 React hook — connect/disconnect/send, 지수 backoff 자동 재연결, `WebSocketStatus` 상태 관리 |
| Env | `.env.local.example` | `VITE_WS_URL=ws://localhost:8000` 정의됨 |
| Constants | `src/constants/api.ts` | HTTP 엔드포인트만 정의됨, **`WS_ENDPOINTS` 없음** |

#### 정의됐지만 미사용 자원
- `WSMessageType` enum: `PING`, `PONG`, `AGENT_STEP`, `AGENT_DONE`, `CHAT_TOKEN`, `CHAT_DONE`, `INGEST_PROGRESS`, `INGEST_DONE` → **publisher/consumer 모두 0**
- `ConnectionManager.send_to_room`, `broadcast`, `room_id` → 호출처 0
- `useWebSocket` 훅 → 임포트 컴포넌트 0

### 1.3 Gap 요약 (Why this Plan)

| Gap | 영향 |
|-----|------|
| `/ws/echo` 외의 실제 도메인 WebSocket 엔드포인트 없음 | 정의된 메시지 타입들이 dead code |
| 프론트에서 `useWebSocket` 호출하는 컴포넌트 0개 | 인프라 투자가 회수되지 않음 |
| `VITE_WS_URL` + access token 첨부 패턴이 코드로 정립되지 않음 | 매번 ad-hoc 작성 → 일관성 깨짐 |
| `WS_ENDPOINTS` 상수, `wsUrl(...)` 빌더 유틸 없음 | typo·환경별 분기 위험 |
| Zustand 스토어와 WS 메시지 결합 패턴 정립 안 됨 | 컴포넌트 unmount 시 메시지 손실 |

### 1.4 Related Documents / Code
- 백엔드 인프라 완료 보고서: `docs/04-report/websocket-common-module.report.md`
- 프론트 hook 정의 메모: `idt_front/src/claude/task/task-websocket.md`
- 프론트 Zustand+WS 통합 보고서: `idt_front/src/claude/report-zustand-ws.md`
- 인증 어댑터: `idt/src/interfaces/dependencies/auth.py`
- 토큰 발급: `idt/src/api/routes/auth_router.py` (JWT access token, 1h)
- 첫 사용 사례 대상: `idt/src/application/agent_builder/run_agent_use_case.py`

---

## 2. Scope

### 2.1 In Scope

#### (A) 표준 연동 가이드 정립
- [ ] WS URL 빌더 유틸 (`utils/wsUrl.ts`) — `VITE_WS_URL` + path + token 조합
- [ ] `WS_ENDPOINTS` 상수 — `constants/api.ts`에 추가 (HTTP 옆에 배치)
- [ ] 메시지 타입 TS 정의 — 백엔드 `WSMessageType` enum과 1:1 매칭되는 union type
- [ ] 표준 사용 패턴(헬퍼 hook) — `useAgentRunStream(runId)` 형태의 도메인 hook 예시
- [ ] 가이드 문서 — 신규 WS 기능 추가 시 따라야 할 5단계 체크리스트

#### (B) 첫 사용 사례 PoC — Agent 실행 실시간 진행률
- [ ] 백엔드: `/ws/agent/{run_id}` 엔드포인트 신설 (run_id를 room_id로 사용)
- [ ] 백엔드: `run_agent_use_case` 내부에서 LangGraph `astream_events` 결과를 `ConnectionManager.send_to_room`으로 push
- [ ] 프론트: `useAgentRunStream(runId)` hook 구현 (useWebSocket 래퍼)
- [ ] 프론트: Agent 실행 화면에서 토큰/스텝 단위 진행률 실시간 표시 (1개 컴포넌트)

### 2.2 Out of Scope (별도 후속 Plan으로 분리)
- RAG 채팅 토큰 스트리밍(`chat_token`/`chat_done`) — Agent 실행 PoC 검증 후 동일 패턴으로 추가
- 문서 인제스트 진행률(`ingest_progress`/`ingest_done`) — 별도 Plan
- Heartbeat ping/pong 자동화 (현재는 클라가 닫으면 끝) — 인프라 보강 Plan으로 분리
- Redis Pub/Sub 기반 멀티 인스턴스 확장
- WebSocket 부하 테스트, 동시 접속 100 초과 시 백프레셔 전략
- 백엔드 인증 방식 변경 (현재 query param 토큰 유지 — Subprotocol 방식 검토는 후속)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `WS_ENDPOINTS` 상수 정의 — 최소 `WS_AGENT_RUN(runId)` 포함 | High | Pending |
| FR-02 | `wsUrl(path, token?)` 유틸 — `VITE_WS_URL` + path + `?token=` 결합 | High | Pending |
| FR-03 | 프론트 메시지 타입 정의 — `AgentStepMessage`, `AgentDoneMessage`, `WSErrorMessage` 등 union type | High | Pending |
| FR-04 | `useAgentRunStream(runId)` hook — `useWebSocket` 래퍼, 자동 토큰 첨부, 메시지 → state 매핑 | High | Pending |
| FR-05 | 백엔드 `/ws/agent/{run_id}` 엔드포인트 신설 — 인증 + room_id 등록 + 메시지 push | High | Pending |
| FR-06 | `run_agent_use_case`에서 LangGraph 이벤트를 `agent_step`/`agent_done` 메시지로 변환·송신 | High | Pending |
| FR-07 | Agent 실행 화면에 실시간 진행 표시 컴포넌트 1개 통합 | Medium | Pending |
| FR-08 | 가이드 문서(`docs/guides/websocket-integration.md`) — 5단계 체크리스트 + 첫 사용 사례를 예제로 인용 | Medium | Pending |
| FR-09 | 토큰 만료/4001 close 시 프론트가 `auth/refresh` 후 재연결 시도 (1회) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Compatibility | 백엔드 `WSMessage` 스키마와 프론트 type 정의 1:1 일치 | 수동 코드 리뷰 + 타입 체크 |
| Reliability | 컴포넌트 unmount 시 WS 연결·재연결 타이머 모두 정리 | 메모리 누수 수동 확인 (DevTools) |
| Security | 토큰 없이 연결 시도 시 4001 close, 만료 토큰도 동일 | 백엔드 단위 테스트 (이미 존재) + 프론트 통합 수동 |
| Maintainability | 신규 WS 기능 추가 시 가이드만 보고 1일 내 통합 가능 | 가이드 적용해 RAG 채팅 추가 시 측정 (후속 Plan에서) |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `WS_ENDPOINTS`, `wsUrl()`, 메시지 type 정의 추가 및 빌드 통과
- [ ] 백엔드 `/ws/agent/{run_id}` 엔드포인트 동작 (수동: 토큰 포함 시 connected, 미포함 시 4001)
- [ ] Agent 실행 1건 트리거 시 프론트에서 `agent_step` 메시지 N건, `agent_done` 1건 수신 확인
- [ ] Agent 실행 화면에서 진행률이 토큰/스텝 단위로 갱신되는 것이 육안 확인 가능
- [ ] 가이드 문서가 작성되고, "RAG 채팅 토큰 스트리밍을 추가하려면?"에 답할 수 있음
- [ ] 기존 HTTP 기반 Agent 실행 흐름이 회귀하지 않음 (기존 테스트 통과)

### 4.2 Out of Scope for DoD
- 자동화 E2E 테스트 (수동 검증으로 충분)
- 토큰 자동 갱신 후 재연결까지의 자동화 테스트 (FR-09는 best-effort)

---

## 5. Approach (High-Level)

### 5.1 표준 연동 5단계 패턴 (가이드 문서에 들어갈 내용)

```
[1] 백엔드: src/api/routes/ws_router.py에 새 엔드포인트 추가
    @router.websocket("/ws/{feature}/{room_id}")
    → verify_ws_token → manager.connect(ws, user.id, room_id)

[2] 백엔드: 도메인 UseCase에서 진행 이벤트가 발생할 때마다
    manager.send_to_room(room_id, WSMessage(type=..., data=...).model_dump(mode="json"))

[3] 프론트: constants/api.ts의 WS_ENDPOINTS에 path 추가
    WS_AGENT_RUN: (runId) => `/ws/agent/${runId}`

[4] 프론트: types/websocket.ts에 메시지 union type 추가
    type AgentStepMessage = { type: "agent_step"; data: {...} }

[5] 프론트: 도메인 hook 작성 (useAgentRunStream 등)
    useWebSocket을 래핑, connect 시 wsUrl(path, accessToken) 사용
```

### 5.2 첫 사용 사례 — `/ws/agent/{run_id}` 구현 순서

1. 백엔드 엔드포인트 추가 → `/ws/echo` 패턴 복제
2. `run_agent_use_case`에 `connection_manager` 의존성 주입 (`Depends`로 wiring)
3. LangGraph `astream_events` 이벤트 핸들러에서 `send_to_room` 호출
4. 프론트 hook 작성 후 Agent 실행 페이지에 통합
5. 수동 통합 확인 (Chrome DevTools Network → WS 탭)

### 5.3 Architecture Decisions

| 결정 | 선택 | 근거 |
|-----|------|------|
| Run ID → Room 매핑 | `room_id = run_id` (1:1) | 한 run을 여러 탭/디바이스에서 동시에 볼 가능성을 위해 broadcast 가능 구조 유지 |
| 토큰 전달 방식 | query param 유지 (`?token=`) | 백엔드 `verify_ws_token`이 이미 query param 방식 — 변경 비용 회피 |
| 새 hook vs 기존 hook 확장 | 도메인별 새 hook(`useAgentRunStream`) | `useWebSocket`은 generic 유지, 도메인 로직은 래퍼에 분리 |
| 백엔드 publisher 위치 | UseCase 레이어 | Application이 흐름 제어를 담당한다는 CLAUDE.md 규칙 준수 |
| 메시지 직렬화 | `WSMessage(...).model_dump(mode="json")` | 기존 `/ws/echo` 컨벤션과 일치 |

---

## 6. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| `astream_events` 호출 빈도가 높아 WS send에 백프레셔 발생 | Medium | Medium | 토큰 단위가 너무 잦으면 N개씩 배치 송신으로 폴백 (PoC 후 측정 후 결정) |
| 토큰이 만료된 채로 장시간 실행되는 Agent run | Medium | Low | FR-09로 1회 자동 재연결, 실패 시 사용자 토스트 |
| Agent 실패 시 `agent_done` 미발송 → 프론트 무한 대기 | Medium | High | finally 블록에서 `error`/`agent_done` 반드시 송신 보장 |
| 다중 탭에서 같은 run을 구독할 때 메시지 중복 | Low | Low | room broadcast로 이미 동일 메시지 전송됨 — 클라가 idempotent하게 처리 |
| 프론트 unmount 직후 늦게 도착하는 메시지 | Medium | Low | hook cleanup에서 disconnect 호출 (`useWebSocket` 이미 처리) |
| Reverse proxy(nginx 등)에서 WS upgrade 미설정 | Low | High | 로컬 dev는 직접 8000 포트 — 배포 단계에서 별도 검토 (Out of Scope) |

---

## 7. Dependencies

| Dependency | Type | Notes |
|-----------|------|-------|
| 백엔드 WebSocket 인프라 | Internal | ✅ 완료 (`websocket-common-module`) |
| 프론트 `useWebSocket` hook | Internal | ✅ 완료 (`WS-001`) |
| JWT access token 발급 | Internal | ✅ 완료 (`auth_router.py`) |
| LangGraph `astream_events` | External | 이미 `langchain-langgraph` 의존성에 포함 |
| `agent_builder.run_agent_use_case` | Internal | 본 Plan에서 일부 수정 (이벤트 publisher 추가) |

---

## 8. Estimated Effort

| Item | Estimate |
|------|---------:|
| 가이드 문서(FR-08) 작성 | 0.5 day |
| 프론트 공통 자산(FR-01~04) | 0.5 day |
| 백엔드 `/ws/agent/{run_id}` 및 UseCase 통합(FR-05~06) | 1 day |
| 프론트 컴포넌트 통합(FR-07) | 0.5 day |
| 토큰 만료 시 재연결(FR-09) | 0.5 day |
| 수동 통합 검증 | 0.5 day |
| **합계** | **~3.5 days** |

---

## 9. Next Steps

1. 본 Plan 검토 및 승인
2. `/pdca design fe-websocket-integration-guide`로 Design 문서 작성
   - 백엔드 라우터 시그니처/DI 와이어링 상세
   - LangGraph 이벤트 → WSMessage 매핑 표
   - 프론트 hook API 정의 및 상태 모델
3. `/pdca do fe-websocket-integration-guide`로 구현 진입

---

## 10. Open Questions

| # | Question | Owner |
|---|----------|-------|
| Q1 | Agent 한 run에서 `agent_step` 메시지를 토큰 단위로 보낼지, 노드 단위로 보낼지? | 배상규 |
| Q2 | 동일 run에 대한 다중 탭 구독을 허용할지(=room broadcast 유지) vs 단일 구독 강제? | 배상규 |
| Q3 | 가이드 문서를 `idt/docs/guides/`에 둘지, 루트 `docs/`에 둘지? (cross-project 성격) | 배상규 |
| Q4 | FR-09(자동 재연결)을 본 Plan 범위에 포함할지, 후속 인프라 Plan으로 분리할지? | 배상규 |

---

**Plan Document Created**: 2026-05-25
**PDCA Phase**: Plan
**Next Phase**: Design (after review/approval)
