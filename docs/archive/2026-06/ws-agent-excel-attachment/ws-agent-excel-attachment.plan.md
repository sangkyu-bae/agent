---
template: plan
version: 1.2
feature: ws-agent-excel-attachment
date: 2026-06-06
author: 배상규
project: sangplusbot (idt 백엔드 + idt_front 프론트)
status: Draft
---

# ws-agent-excel-attachment Planning Document

> **Summary**: `/ws/agent/{run_id}` Agent 실행 WebSocket이 엑셀 첨부를 받아 데이터 분석 노드까지 전달하도록 입구를 연결한다 (업로드 → file_id 참조 방식).
>
> **Project**: sangplusbot
> **Author**: 배상규
> **Date**: 2026-06-06
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 데이터 분석 에이전트의 analysis 노드는 엑셀 `file_path`를 요구하지만, `/ws/agent/{run_id}` 입구가 첨부를 받지 못해 WS 경로로는 엑셀 분석이 불가능하다. |
| **Solution** | 엑셀을 HTTP multipart로 업로드해 `file_id`를 발급받고, WS `subscribe` 메시지에 `attachments`로 참조를 실어 보낸다. 라우터가 `file_id`→`file_path`로 해석해 `RunAgentRequest.attachments`(이미 존재)로 전달하고, run 종료 시 임시 파일을 자동 삭제한다. |
| **Function/UX Effect** | 사용자가 채팅 UI에서 엑셀을 첨부하면 에이전트가 실시간 스트리밍으로 데이터 분석 결과를 답한다. |
| **Core Value** | 이미 완성된 분석 파이프라인(ExcelAnalysisWorkflow)을 WS 대화 경로에 "입구만 연결"하여 최소 변경으로 핵심 기능을 활성화한다. |

---

## 1. Overview

### 1.1 Purpose

`/ws/agent/{run_id}` Agent 실행 스트리밍 엔드포인트가 엑셀 파일 첨부를 수용하여,
데이터 분석 에이전트(analysis 노드)가 실제 엑셀 데이터를 기반으로 분석하도록 한다.

### 1.2 Background

코드 추적 결과, **분석 파이프라인은 이미 엑셀을 받을 준비가 완료**되어 있고
끊긴 곳은 **WebSocket 입구 한 곳**뿐이다.

| 단계 | 위치 | 엑셀 지원 |
|------|------|:--------:|
| WS subscribe 페이로드 | `ws_schemas.py` `SubscribeAgentRunPayload` | ❌ 필드 없음 |
| WS 라우터 → 요청 조립 | `ws_router.py:171` `RunAgentRequest(...)` | ❌ attachments 미전달 |
| 요청 스키마 | `schemas.py:106` `RunAgentRequest.attachments` | ✅ 존재 |
| UseCase → 그래프 | `run_agent_use_case.py:461` | ✅ 전달 |
| 분석 노드 | `workflow_compiler.py:508~517` | ✅ excel 찾아 워크플로우 실행 |

분석 노드는 원본 바이트가 아니라 **서버 파일시스템의 `file_path`**
(`workflow_compiler.py:559`)를 요구하므로, WS(JSON 텍스트 채널) 직접 전송이 아닌
별도 업로드 경로가 필요하다.

### 1.3 Related Documents

- WS 라우터: `idt/src/api/routes/ws_router.py`
- 기존 엑셀 분석 1회성 엔드포인트(참조): `idt/src/api/routes/analysis_router.py`
- 분석 노드 attachments 소비: `idt/src/application/agent_builder/workflow_compiler.py`
- 프론트 WS 구독 hook: `idt_front/src/hooks/useAgentRunStream.ts`
- 프론트 업로드 패턴(참조): `idt_front/src/services/unifiedUploadService.ts`

---

## 2. Scope

### 2.1 In Scope

- [ ] 엑셀 업로드 HTTP 엔드포인트 신설 — 임시 저장 후 `file_id` 반환
- [ ] `SubscribeAgentRunPayload`에 `attachments`(확장 가능 구조) 필드 추가
- [ ] `ws_router.ws_agent_run`에서 `file_id`→`file_path` 해석 후 `RunAgentRequest.attachments`로 전달
- [ ] run 종료(정상/예외/disconnect) 시 임시 파일 자동 삭제 (`finally` 보장)
- [ ] attachment 검증 — 확장자/크기 (엑셀 한정, 구조는 타입 확장 가능)
- [ ] DI 와이어링 (`main.py` lifespan)
- [ ] 프론트: 엑셀 첨부 업로드 UI + `useAgentRunStream` subscribe에 attachments 포함
- [ ] 백엔드 pytest (Red→Green), 프론트 Vitest (업로드/구독)
- [ ] API 계약 동기화 (백엔드 스키마 ↔ 프론트 타입/서비스)

### 2.2 Out of Scope

- CSV·이미지 등 엑셀 외 타입의 실제 분석 처리 (구조만 확장 가능하게, 동작은 후속)
- 업로드 파일 영구 보관/재사용 (이번엔 run 단위 1회성 + 자동 삭제)
- 멀티 파일 동시 분석 최적화 (1차는 단일 엑셀 기준)
- Excel/Supervisor 외 경로의 차트 렌더링 (별도 트랙)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 엑셀 업로드 엔드포인트가 파일을 임시 저장하고 고유 `file_id`를 반환한다 | High | Pending |
| FR-02 | `SubscribeAgentRunPayload`가 `attachments: [{type, file_id}]`를 수용한다 (확장 가능) | High | Pending |
| FR-03 | WS 라우터가 `file_id`를 `file_path`로 해석해 `RunAgentRequest.attachments`로 전달한다 | High | Pending |
| FR-04 | 분석 노드가 전달된 엑셀로 ExcelAnalysisWorkflow를 실행하고 결과를 스트리밍한다 | High | Pending |
| FR-05 | run 종료 시(정상/예외/연결 끊김 포함) 임시 파일을 삭제한다 | High | Pending |
| FR-06 | 허용되지 않는 확장자/크기/존재하지 않는 file_id는 명확한 에러로 거부한다 | Medium | Pending |
| FR-07 | 프론트에서 엑셀을 첨부·업로드 후 에이전트 실행을 트리거한다 | High | Pending |
| FR-08 | attachment 디스패치 구조는 type 추가(csv 등)에 열려 있다 (OCP) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Security | 업로드 파일은 업로더 user_id에 귀속, file_id는 추측 불가(uuid), 경로 traversal 차단 | 코드 리뷰 + 테스트 |
| Reliability | 비정상 종료/disconnect 시에도 임시 파일 누수 없음 | `finally` 단위 테스트 |
| Architecture | Thin DDD 레이어 준수 (domain 규칙 / application 흐름 / infrastructure 저장 / interfaces 라우터) | `/verify-architecture` |
| Logging | print 금지, logger 사용, 스택트레이스 포함 에러 처리 | `/verify-logging` |
| Compatibility | 첨부 없는 기존 WS subscribe 동작 무변경 (attachments optional) | 회귀 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-08 구현 완료
- [ ] 백엔드 pytest / 프론트 Vitest 작성·통과 (TDD)
- [ ] 첨부 없는 기존 경로 회귀 무변경 확인
- [ ] API 계약 동기화(`/api-contract-sync`) 완료
- [ ] 임시 파일 누수 0 (run 종료 후 디렉토리 확인)

### 4.2 Quality Criteria

- [ ] `/verify-architecture` 통과 (레이어 의존성 위반 0)
- [ ] `/verify-logging` 통과
- [ ] 함수 40줄 / if 중첩 2단계 규칙 준수
- [ ] lint 에러 0, 빌드 성공

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 임시 파일 누수 (현 analysis_router는 `delete=False`로 잔존) | Medium | Medium | run 단위 cleanup을 `finally`로 보장 + 업로드 TTL 백업 정리(선택) |
| WS 연결과 업로드 HTTP의 user 불일치 | High | Low | file_id를 업로더 user_id에 귀속, WS 인증 user와 대조 후 거부 |
| 경로 traversal / 임의 파일 접근 | High | Low | file_id(uuid)→내부 매핑만 허용, 사용자 입력 경로 직접 사용 금지 |
| 대용량 엑셀로 인한 분석 지연/타임아웃 | Medium | Medium | 업로드 크기 제한 + 분석 노드 기존 max_attempts(3) 유지 |
| 분석 노드 getter 미주입 시 silent fallback(context 분석) | Medium | Low | DI 주입 검증 + 첨부 있는데 워크플로우 미주입이면 경고 로그 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| Starter | 단순 구조 | ☐ |
| Dynamic | 기능 모듈 + BaaS | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DI (현 idt 구조 = Thin DDD) | ☑ |

> idt 백엔드는 `domain/application/infrastructure/interfaces` Thin DDD를 따른다.
> 단, "과도한 추상화 금지" 규칙에 따라 얇게 구현한다.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 파일 전송 방식 | 인라인 base64 / **HTTP 업로드+file_id 참조** / 기존 analysis 재사용 | HTTP 업로드+file_id | WS는 JSON만 유지, 대용량·안정성 유리 (사용자 확정) |
| 파일 수명 | **run 종료 후 자동 삭제** / TTL 보관 / 영구 | run 후 삭제 | 1회성 분석, 디스크 누수 방지 (사용자 확정) |
| 첨부 스키마 | 단일 file_id / **구조화 list[{type,file_id}]** | 구조화 list | csv 등 타입 확장 가능 (사용자 확정) |
| 업로드 엔드포인트 | analysis_router 확장 / **신규 전용 엔드포인트** | 신규 전용 | 기존 1회성 분석과 책임 분리, file_id 발급 목적 명확 |
| file_id→path 저장소 | DB / **로컬 임시 디렉토리 + uuid 매핑** | 로컬 임시 | 1회성·자동삭제 정책에 충분, 과한 추상화 회피 |

### 6.3 레이어 배치 (Thin DDD)

```
interfaces/  : 신규 업로드 라우터 + SubscribeAgentRunPayload.attachments 확장
               ws_router 첨부 해석/cleanup 연결
application/ : 업로드 use case(파일 저장→file_id), file_id→file_path 해석 + cleanup
domain/      : Attachment VO / 허용 타입·크기 정책 (규칙만)
infrastructure/ : 임시 파일 저장 어댑터 (디렉토리 I/O)
```

> 라우터에 비즈니스 로직 금지 — 검증/저장/삭제는 application·domain·infrastructure로.

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` Thin DDD 규칙 / 금지 사항
- [x] `docs/rules/logging.md`, `docs/rules/db-session.md`, `docs/rules/testing.md`
- [x] TDD 필수 (pytest / Vitest)
- [x] API 계약 동기화 규칙 (루트 CLAUDE.md §4-1)

### 7.2 Conventions to Verify

| Category | To Define/Verify | Priority |
|----------|------------------|:--------:|
| 임시 파일 저장 경로 | 업로드 임시 디렉토리 위치/권한 (config화, 하드코딩 금지) | High |
| 파일 크기 제한 | 허용 최대 크기 상수 (config) | High |
| file_id 포맷 | uuid4 기반, 추측 불가 | Medium |
| 에러 코드 | INVALID_ATTACHMENT / FILE_NOT_FOUND 등 WSMessage 코드 | Medium |

### 7.3 Environment / Config Needed

| 항목 | 용도 | 위치 |
|------|------|------|
| 업로드 임시 디렉토리 | 엑셀 임시 저장 경로 | `idt/src/config.py` |
| 최대 업로드 크기 | 검증 임계값 | `idt/src/config.py` |
| 허용 확장자 목록 | `.xlsx/.xls` (확장 대비 set) | domain 정책 |

### 7.4 API 계약 동기화 (필수)

| 백엔드 (idt/) | 프론트엔드 (idt_front/) |
|---------------|------------------------|
| 신규 업로드 라우터 + `SubscribeAgentRunPayload` | `src/services/` 업로드 + `useAgentRunStream` subscribe |
| 업로드 응답 스키마(file_id) | `src/types/` 첨부 타입 |
| — | 엔드포인트 상수: `src/constants/api.ts`, `WS_ENDPOINTS` |

---

## 8. Open Questions (설계 단계 확정 필요)

- [ ] 업로드 엔드포인트 경로/prefix 컨벤션 (예: `/api/v1/agent/attachments`)
- [ ] 멀티 파일 허용 여부 (1차 단일 가정 → 구조는 list)
- [ ] 재접속/replay 시 첨부 처리 (이번 범위 외, run 1회성 전제)

---

## 9. Next Steps

1. [ ] 설계 문서 작성 (`/pdca design ws-agent-excel-attachment`)
2. [ ] 업로드 엔드포인트 ↔ file_id ↔ WS 첨부 ↔ cleanup 흐름 시퀀스 확정
3. [ ] TDD 구현 시작 (`/pdca do ...`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-06 | 코드 추적 기반 초안 작성 (입구 단절 확인 + 풀스택/자동삭제/확장구조 확정) | 배상규 |
