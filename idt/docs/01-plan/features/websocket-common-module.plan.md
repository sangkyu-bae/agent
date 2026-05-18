# WebSocket Common Module Planning Document

> **Summary**: 백엔드 공통 WebSocket 모듈 — Agent 스트리밍, RAG 채팅, 문서 처리 진행률 등 다양한 피처에서 재사용 가능한 WebSocket 인프라
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-15
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | Agent 실행, RAG 채팅, 문서 인제스트 등 여러 기능에서 실시간 스트리밍이 필요하지만, 백엔드에 WebSocket 엔드포인트가 전혀 없어 실시간 응답이 불가능하다 |
| **Solution** | FastAPI WebSocket 기반 공통 모듈(ConnectionManager + 메시지 프로토콜 + 토큰 인증)을 infrastructure 레이어에 구현하고, 피처별 핸들러만 추가하면 되는 구조 제공 |
| **Function/UX Effect** | 토큰 단위 스트리밍 응답, Agent 스텝별 실시간 진행 표시, 문서 처리 진행률 알림으로 사용자 체감 응답 속도 대폭 개선 |
| **Core Value** | 한 번 구축으로 모든 실시간 피처에 재사용 가능한 WebSocket 인프라 확보, 프론트엔드 useWebSocket 훅과 즉시 연동 가능 |

---

## 1. Overview

### 1.1 Purpose

Agent 실행 스트리밍, RAG 채팅 토큰 스트리밍, 문서 처리 진행률 알림 등 여러 피처에서 공통으로 사용할 수 있는 FastAPI WebSocket 모듈을 구현한다. 현재 백엔드에 WebSocket 엔드포인트가 전혀 없으므로, 인프라 레이어에 범용 WebSocket 모듈을 만들고 각 피처에서 확장하여 사용하는 구조를 목표로 한다.

### 1.2 Background

- **프론트엔드**: `useWebSocket` 훅이 이미 구현되어 있으며 (reconnect, JSON 파싱, 상태 관리 포함), 백엔드 엔드포인트만 있으면 즉시 연동 가능
- **백엔드**: FastAPI 기반이지만 WebSocket/SSE/Streaming 엔드포인트가 전혀 없음. 모든 응답이 HTTP 요청-응답 패턴
- **인증 체계**: JWT 기반 인증(`get_current_user`, `JWTAdapterInterface`)이 이미 구축되어 있어, 쿼리 파라미터 토큰 검증에 재사용 가능
- **Agent 프레임워크**: LangGraph/LangChain에 `astream_events`/`stream_events` 지원이 있어 WebSocket 연동 적합

### 1.3 Related Documents

- 프론트엔드 WS 훅: `idt_front/src/hooks/useWebSocket.ts`
- WS 완료 보고서: `idt_front/src/claude/report-zustand-ws.md`
- 인증 모듈: `idt/src/interfaces/dependencies/auth.py`
- Agent 실행: `idt/src/application/agent_builder/run_agent_use_case.py`

---

## 2. Scope

### 2.1 In Scope

- [ ] **ConnectionManager**: 연결 관리, 방(room) 기반 그룹핑, 연결 수명주기
- [ ] **메시지 프로토콜**: 공통 JSON 메시지 스키마 (type, data, metadata)
- [ ] **쿼리 파라미터 토큰 인증**: `ws://host/ws?token=xxx` 방식의 JWT 검증
- [ ] **WebSocket 라우터 기반 구조**: 피처별 핸들러를 쉽게 등록할 수 있는 라우터 패턴
- [ ] **에러 핸들링/Heartbeat**: 연결 유지 ping/pong, 에러 메시지 전송 규격

### 2.2 Out of Scope

- 프론트엔드 `useWebSocket` 훅 수정 (이미 완성됨)
- 프론트엔드 WS_ENDPOINTS 상수, wsUrl 빌더 (별도 피처)
- 특정 피처(Agent, RAG, Ingest)의 실제 WebSocket 핸들러 구현 (이 모듈 위에 별도로 구현)
- Redis Pub/Sub 등 다중 서버 스케일아웃 (단일 서버 기준)
- WebSocket 부하 테스트/성능 최적화

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | ConnectionManager: connect/disconnect/broadcast/send_to_room 메서드 제공 | High | Pending |
| FR-02 | 공통 메시지 스키마: `{ type: string, data: any, timestamp: string, metadata?: any }` | High | Pending |
| FR-03 | 쿼리 파라미터 토큰 인증: WebSocket 연결 시 `?token=` JWT 검증, 실패 시 즉시 close(4001) | High | Pending |
| FR-04 | Room 기반 메시지 전송: run_id, session_id 등으로 그룹화하여 해당 room에만 브로드캐스트 | Medium | Pending |
| FR-05 | Heartbeat: 서버 → 클라이언트 ping 주기적 전송, 응답 없으면 연결 해제 | Medium | Pending |
| FR-06 | 에러 메시지 규격: `{ type: "error", data: { code: string, message: string } }` | High | Pending |
| FR-07 | 피처별 핸들러 등록 패턴: 새 피처 추가 시 핸들러 함수만 작성하면 되는 구조 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 동시 연결 100개 이상 지원 | 수동 테스트 |
| Security | JWT 토큰 만료/위변조 시 연결 거부 | 단위 테스트 |
| Reliability | 비정상 종료 시 연결 리소스 정리 보장 | 코드 리뷰 |
| Compatibility | 프론트엔드 useWebSocket 훅과 프로토콜 호환 | 통합 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] ConnectionManager 구현 및 단위 테스트 통과
- [ ] 메시지 스키마(Pydantic) 정의 완료
- [ ] 쿼리 파라미터 JWT 인증 구현 및 테스트
- [ ] WebSocket 라우터 등록 및 echo 핸들러로 연결 검증
- [ ] 프론트엔드 useWebSocket 훅과 연동 확인 (수동)

### 4.2 Quality Criteria

- [ ] 단위 테스트 커버리지 80% 이상
- [ ] mypy/ruff 에러 없음
- [ ] DDD 레이어 규칙 준수 (domain에 외부 의존성 없음)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| FastAPI WebSocket과 LangGraph astream 통합 복잡성 | Medium | Medium | 이 모듈에서는 전송 인프라만 제공, LangGraph 통합은 피처별 핸들러에서 처리 |
| 동시 연결 수 증가 시 메모리 이슈 | Medium | Low | ConnectionManager에 최대 연결 수 제한 옵션 제공 |
| 토큰 만료 후 기존 연결 처리 | Low | Medium | Heartbeat 시 토큰 재검증 또는 연결 시점 1회 검증으로 단순화 (첫 버전) |
| 프론트엔드 메시지 포맷 불일치 | High | Low | 프론트엔드 WebSocketMessage 인터페이스와 백엔드 스키마를 동일 구조로 설계 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic systems | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| WebSocket 프레임워크 | FastAPI 내장 / Socket.IO / Starlette raw | FastAPI 내장 WebSocket | 프레임워크 일관성, 추가 의존성 불필요 |
| 메시지 직렬화 | JSON / MessagePack / Protobuf | JSON | 프론트엔드 useWebSocket 훅이 JSON.parse 기반, 디버깅 용이 |
| 인증 방식 | 쿼리 파라미터 토큰 / 첫 메시지 토큰 / 쿠키 | 쿼리 파라미터 토큰 | 브라우저 WebSocket API가 커스텀 헤더 미지원, 가장 보편적 |
| 연결 관리 | 글로벌 싱글턴 / DI 주입 | DI 주입 (lifespan) | 테스트 용이성, 기존 프로젝트 DI 패턴과 일관성 |
| 레이어 배치 | infrastructure / interfaces | infrastructure + interfaces | ConnectionManager는 infra, 라우터는 interfaces |

### 6.3 Clean Architecture Approach

```
Enterprise Level (기존 프로젝트 구조 유지):

src/
├── domain/websocket/
│   ├── schemas.py          # 메시지 스키마 (Pydantic VO)
│   └── interfaces.py       # ConnectionManagerInterface (ABC)
├── infrastructure/websocket/
│   ├── connection_manager.py  # ConnectionManager 구현체
│   └── auth.py               # WS 토큰 인증 헬퍼
├── api/routes/
│   └── ws_router.py          # WebSocket 라우터 (echo 핸들러 포함)
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section
- [x] DDD 레이어 규칙 정의됨 (domain → application → infrastructure)
- [x] JWT 인증 체계 구축됨 (`JWTAdapterInterface`, `get_current_user`)
- [x] Pydantic 기반 스키마 정의 관행
- [x] StructuredLogger 사용 필수

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **WS 메시지 타입 네이밍** | missing | `snake_case` 타입명 규칙 (e.g., `agent_step`, `error`) | High |
| **WS 라우터 경로 패턴** | missing | `/ws/{feature}/{id}` 패턴 표준화 | High |
| **WS 에러 코드 체계** | missing | 4001(인증실패), 4002(권한부족), 4003(리소스없음) 등 | Medium |
| **로깅 규칙** | exists | WS connect/disconnect/error 로깅 포맷 | Medium |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `WS_HEARTBEAT_INTERVAL` | Heartbeat 주기 (초) | Server | ☑ (기본값 30) |
| `WS_MAX_CONNECTIONS` | 최대 동시 연결 수 | Server | ☑ (기본값 100) |

기존 환경변수 재사용:
- `JWT_SECRET_KEY`: 토큰 검증에 사용 (기존 JWTAdapter 재사용)

---

## 8. Implementation Guide

### 8.1 구현 순서

```
1. domain/websocket/schemas.py         # 메시지 VO 정의
2. domain/websocket/interfaces.py      # ConnectionManagerInterface ABC
3. infrastructure/websocket/connection_manager.py  # 구현체
4. infrastructure/websocket/auth.py    # WS 토큰 인증
5. api/routes/ws_router.py            # 라우터 + echo 핸들러
6. api/main.py                        # 라우터 등록
```

### 8.2 메시지 프로토콜 설계

```json
// 서버 → 클라이언트 (공통 envelope)
{
  "type": "agent_step | chat_token | ingest_progress | error | ping",
  "data": { /* 피처별 페이로드 */ },
  "timestamp": "2026-05-15T10:30:00Z",
  "metadata": {
    "room_id": "run_abc123",
    "seq": 42
  }
}

// 클라이언트 → 서버
{
  "type": "subscribe | unsubscribe | pong | chat_message",
  "data": { /* 피처별 페이로드 */ }
}
```

### 8.3 인증 플로우

```
1. 클라이언트: ws://host/ws/agent/{run_id}?token=eyJhbGc...
2. 서버: 쿼리 파라미터에서 token 추출
3. 서버: JWTAdapter.decode(token) → TokenPayload
4. 검증 실패 시: await ws.close(code=4001, reason="Invalid token")
5. 검증 성공 시: ConnectionManager.connect(ws, user_id, room_id)
```

---

## 9. Next Steps

1. [ ] Write design document (`websocket-common-module.design.md`)
2. [ ] 구현 시작 (domain 스키마 → infra 구현체 → 라우터 순)
3. [ ] 프론트엔드 WS_ENDPOINTS 상수 추가 (별도 피처)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-15 | Initial draft | 배상규 |
