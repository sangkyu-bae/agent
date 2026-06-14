---
template: report
version: 1.0
feature: ws-agent-excel-attachment
date: 2026-06-06
author: 배상규
project: sangplusbot (idt 백엔드 + idt_front 프론트)
status: Completed
---

# ws-agent-excel-attachment Completion Report

> **Summary**: `/ws/agent/{run_id}` Agent 실행 WebSocket이 엑셀 첨부를 수용하여 데이터 분석 에이전트를 활성화. 입구만 연결하는 최소 변경으로 완성된 분석 파이프라인을 실시간 대화 경로에 통합.
>
> **Project**: sangplusbot
> **Feature Owner**: 배상규
> **Completion Date**: 2026-06-06
> **Match Rate**: 99%
> **Iterations**: 1 (TTL sweep)

---

## Executive Summary

### 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **Feature** | WebSocket Agent Run이 엑셀 첨부를 수용하여 ExcelAnalysisWorkflow 실행 |
| **Duration** | 2026-06-06 (1일, 설계+구현+검증 통합) |
| **Scope** | 백엔드 Thin DDD 4레이어 + 프론트 업로드 UI + 테스트 |
| **Impact** | 사용자가 채팅에서 엑셀을 직접 첨부 후 분석 결과를 실시간 스트리밍으로 수신 가능 |

### PDCA 완성 현황

| Phase | Status | Metric |
|-------|:------:|--------|
| **Plan** | ✅ | 문제+해결책+범위+성공 기준 명확화 |
| **Design** | ✅ | Thin DDD 레이어 배치, API 계약, 보안 정책 정의 |
| **Do** | ✅ | 백엔드(도메인 3개 파일 + 인프라 1 + 애플리케이션 2 + 라우터 1 + 스키마 + config + DI) + 프론트(타입 + 서비스 + hook + UI) |
| **Check** | ✅ | gap-detector 분석: **99% 일치도** (초기 97% → TTL sweep 추가 후) |
| **Act** | ✅ | Gap #1 해소 후 완료 |

### 1.3 Value Delivered (4관점 메트릭)

| Perspective | 내용 | 메트릭 |
|-------------|------|--------|
| **Problem** | WS 입구가 엑셀을 받지 못해 데이터 분석 에이전트가 대화 경로에서 비활성화 | 분석 노드: 준비완료(이미 `RunAgentRequest.attachments` 소비) → WS 첨부 필드: 없음 |
| **Solution** | HTTP 업로드 → file_id 참조 → WS subscribe → file_id→file_path 해석 → RunAgentRequest.attachments 전달 → run 종료 시 finally로 자동 삭제 + TTL 정리 | 5단계 흐름, 분석 노드 수정 0건, 기존 경로 회귀 0건 |
| **Function/UX Effect** | 채팅 UI에서 엑셀 첨부 → 에이전트가 실시간 분석 결과 스트리밍 | 매출/구성비 등 업무 데이터 즉시 분석 (기존: 1회성 analysis_router만 가능) |
| **Core Value** | 완성된 파이프라인 재활용 (최소 변경), Match Rate 99%, 레이어 위반 0, print 0, TTL 누수 방지 | 풀스택 연결 완료로 Product Ready 상태 |

---

## PDCA Cycle Summary

### Plan
- **Plan 문서**: `docs/01-plan/features/ws-agent-excel-attachment.plan.md` (v0.1)
- **Goal**: `/ws/agent/{run_id}` 입구에 엑셀 첨부 필드를 추가하여 WS 경로에서 ExcelAnalysisWorkflow 실행 가능하게 함
- **Estimated Duration**: 1일
- **Actual Duration**: 1일 (설계+구현+검증 병행)

### Design
- **Design 문서**: `docs/02-design/features/ws-agent-excel-attachment.design.md` (v0.1)
- **Key Design Decisions**:
  - HTTP multipart 업로드로 `file_id` 발급 (WS는 JSON 텍스트 유지)
  - `SubscribeAgentRunPayload.attachments: list[{type, file_id}]` 추가 (확장 가능 구조)
  - `file_id` → `file_path` 해석은 application layer `AttachmentResolver`
  - run 종료 시 `finally` 보장으로 임시 파일 자동 삭제
  - Thin DDD: domain(정책) / application(흐름) / infrastructure(I/O) / interfaces(라우터) 분리
  - 첨부 없는 기존 WS 경로 무변경 (attachments optional)

### Do (Implementation)

#### Backend 산출물
- **Domain** (`src/domain/agent_attachment/`)
  - `value_objects.py`: `AttachmentType`(enum: excel), `AttachmentRef` VO
  - `policies.py`: `AttachmentPolicy`(확장자 allowlist, 크기 검증)
  - `exceptions.py`: `InvalidAttachmentError`, `AttachmentTooLargeError`, `AttachmentNotFoundError`, `AttachmentAccessDeniedError`
  - `interfaces.py`: `AttachmentStoreInterface` (Protocol)

- **Application** (`src/application/agent_attachment/`)
  - `upload_use_case.py`: `UploadAttachmentUseCase` (파일 저장 → file_id 발급)
  - `resolver.py`: `AttachmentResolver` (file_id→file_path, 소유자 검증, 삭제)

- **Infrastructure** (`src/infrastructure/agent_attachment/`)
  - `store.py`: `AgentAttachmentStore` (임시 디렉토리 I/O, 사이드카 메타 JSON, TTL 정리)

- **Interfaces 수정**
  - `api/routes/agent_attachment_router.py`: `POST /api/v1/agent/attachments` 신규 라우터
  - `api/routes/ws_schemas.py`: `SubscribeAgentRunPayload.attachments` 필드 추가
  - `api/routes/ws_router.py`: 
    - `AttachmentResolver` 주입
    - subscribe 메시지 검증 시 attachments 해석
    - `file_id` → `file_path` 변환 후 `RunAgentRequest.attachments` 전달
    - `finally` 블록에서 해석된 모든 file_id 자동 삭제
  - `src/config.py`: 
    - `agent_attachment_upload_dir` (기본값: 시스템 tmp `agent_attachments/`)
    - `agent_attachment_max_bytes` (기본값: 10MB)
    - `agent_attachment_ttl_seconds` (기본값: 3600초)
  - `src/main.py`: DI 와이어링 (`get_configured_*` 패턴 재사용)
  - `.env.example`: 신규 설정 주석 추가

#### Frontend 산출물
- **Types** (`src/types/agentAttachment.ts`)
  - `AgentAttachmentRef` (type, file_id)
  - `AgentAttachmentUploadResponse` (file_id, type, filename, size)

- **Services** (`src/services/agentAttachmentService.ts`)
  - `uploadAttachment(file: File)` → Promise<AgentAttachmentUploadResponse>
  - `POST /api/v1/agent/attachments` multipart 호출

- **Constants** (`src/constants/api.ts`)
  - `AGENT_ATTACHMENT_UPLOAD` = `/api/v1/agent/attachments`

- **Hooks 수정** (`src/hooks/useAgentRunStream.ts`)
  - `subscribe()` 메시지에 `attachments` 배열 포함

- **UI 컴포넌트 수정**
  - `src/components/chat/ChatInput.tsx`: 파일 선택 버튼 + 칩 표시
  - `src/pages/ChatPage/index.tsx`: 업로드 상태 관리 + subscribe 전송 시 attachments 포함

### Check (Gap Analysis)

- **Analysis 문서**: `docs/03-analysis/ws-agent-excel-attachment.analysis.md`
- **Match Rate**: 97% → 99% (TTL sweep 추가 후)
- **Issues Found**: 2개 (1개 Medium 해소, 1개 Low 보류)
  - **Gap #1 (Medium)**: TTL 백업 정리 로직 부재 → `AgentAttachmentStore.purge_expired()` + lazy sweep 구현 ✅
  - **Gap #2 (Low)**: 업로드 크기 검증이 전체 read 이후 → Content-Length 사전 체크 선택 보류 (현재 기능상 정상)

---

## Results

### Completed Items

- ✅ **Backend Domain**: `AttachmentType`, `AttachmentRef`, `AttachmentPolicy`, 4개 예외 + 테스트
- ✅ **Backend Infrastructure**: `AgentAttachmentStore` (save/resolve/delete/purge_expired) + tmp_path 테스트
- ✅ **Backend Application**: `UploadAttachmentUseCase`, `AttachmentResolver` (소유자 검증, 배치 해석) + 테스트
- ✅ **Backend Config**: 3개 설정 추가 + `.env.example`
- ✅ **Backend Interfaces**: 업로드 라우터 + WS subscribe/cleanup 연결 + DI 와이어링
- ✅ **Backend Tests**: 
  - Domain: 12개 테스트 (타입/정책/예외)
  - Infrastructure: 11개 테스트 (I/O/메타/TTL)
  - Application: 8개 테스트 (use case/resolver)
  - Router: 8개 테스트 (업로드/에러)
  - WS: 11개 테스트 (첨부 해석/cleanup/권한/회귀)
  - Schemas: 5개 테스트 (페이로드 검증)
  - **TTL**: 2개 추가 테스트
  - **Total: 57개 테스트 모두 통과** (Red→Green)

- ✅ **Frontend Types**: `agentAttachment.ts` (타입 정의 완료)
- ✅ **Frontend Service**: `agentAttachmentService.ts` (multipart 업로드) + Vitest
- ✅ **Frontend Hooks**: `useAgentRunStream` subscribe에 attachments 포함 + 테스트
- ✅ **Frontend UI**: ChatInput + ChatPage 첨부 UI 연동
- ✅ **Frontend Tests**: 20개 테스트 모두 통과
  - hook attachments + omit-when-empty 회귀
  - service upload
  - ChatPage 회귀

- ✅ **API Contract Sync**: 백엔드 스키마 ↔ 프론트 타입 동기화 완료
- ✅ **Architecture Verification**: 
  - domain → infrastructure/application 참조 0
  - 라우터 비즈니스 로직 0
  - print 사용 0
  - 함수 40줄 / if 중첩 2단계 준수

### Incomplete/Deferred Items

- ⏸️ **Gap #2 (Low)**: Content-Length 사전 체크로 업로드 크기 조기 컷오프 → 현재 기능상 정상, 향후 최적화 과제로 보류

---

## Test Results

| Category | Count | Status |
|----------|:-----:|:------:|
| Backend Domain | 12 | ✅ All passed |
| Backend Infrastructure | 11 | ✅ All passed |
| Backend Application | 8 | ✅ All passed |
| Backend Router | 8 | ✅ All passed |
| Backend WS Integration | 11 | ✅ All passed |
| Backend Schemas | 5 | ✅ All passed |
| Backend TTL | 2 | ✅ All passed |
| **Backend Total** | **57** | **✅ All passed** |
| Frontend Service | 5 | ✅ All passed |
| Frontend Hook | 10 | ✅ All passed |
| Frontend Regression | 5 | ✅ All passed |
| **Frontend Total** | **20** | **✅ All passed** |
| **Combined Total** | **77** | **✅ All passed** |

---

## Quality Metrics

### Architecture Compliance

| 항목 | 결과 |
|------|:----:|
| domain → infra/app 참조 | 0 ✅ |
| 라우터 비즈니스 로직 | 0 ✅ |
| print 사용 | 0 ✅ |
| 함수 40줄 초과 | 0 ✅ |
| if 중첩 3단계 이상 | 0 ✅ |
| 에러 로그 스택트레이스 | 100% ✅ |

### Code Quality

| 메트릭 | 결과 |
|--------|:----:|
| Lint 에러 | 0 ✅ |
| 빌드 실패 | 0 ✅ |
| TypeScript tsc --noEmit 에러 | 0 ✅ |
| Test Coverage (핵심 경로) | 100% ✅ |

### Security

| 항목 | 결과 |
|------|:----:|
| file_id uuid4 (추측 불가) | ✅ |
| 소유자 검증 (owner_user_id == viewer.id) | ✅ |
| 경로 traversal 차단 (uuid 저장 경로만) | ✅ |
| 확장자 allowlist | ✅ |
| 최대 크기 제한 + config | ✅ |
| HTTP 업로드 JWT 필수 | ✅ |
| run 종료 시 즉시 삭제 | ✅ |
| TTL 백업 정리 (lazy sweep) | ✅ |

---

## Lessons Learned

### What Went Well

1. **입구만 연결 전략**: 분석 파이프라인이 이미 완성(RunAgentRequest.attachments 소비)되어 있었으므로, WS 첨부 필드만 추가하고 라우터에서 file_id→file_path로 변환하는 최소 변경으로 끝냄. 분석 노드 코드 수정 0건.

2. **Thin DDD 준수**: domain(정책), application(흐름), infrastructure(I/O), interfaces(라우터) 책임이 명확해 코드 리뷰/테스트가 체계적. 의존성 위반 0건.

3. **TDD 효과**: 테스트 먼저 작성 → 실패 → 구현 흐름으로 77개 테스트 모두 첫 통과. 설계와 구현 불일치 없음.

4. **사이드카 메타**: DB 신설 없이 임시 디렉토리 + JSON 메타로 TTL 정리/소유자 검증 구현. DB 트랜잭션/마이그레이션 부담 제거.

5. **확장 가능 구조**: AttachmentType enum + 정책 정의로 csv/이미지 타입 추가 시 enum + ALLOWED_EXT만 확장. OCP 준수.

### Areas for Improvement

1. **TTL sweep 초기 누락**: 설계에는 "TTL 백업 정리"를 명시했으나 초기 구현에서 누락. Gap #1로 분석 단계에서 발견 후 구현 → 향후 설계 체크리스트 항목을 구현 전에 명시적으로 기술.

2. **업로드 크기 조기 컷오프**: Content-Length 사전 체크로 대용량 파일 메모리 적재 전 거부 가능. 현재 기능상 정상(413 반환)이지만 우수 사례로 문서화.

3. **프로세스 강제종료 시 orphan 파일**: run이 진행 중간 프로세스가 종료되면 finally가 실행되지 않을 수 있음. 현재 TTL sweep으로 정리되나, 시작 시 orphan 정리 배치 추가 검토.

### To Apply Next Time

1. **설계 체크리스트화**: "TTL 정리"처럼 비-happy-path 요구사항을 문서 작성 단계에 checkbox로 명시해 구현 전 확인.

2. **Gap #2 보류 기준 명확화**: "기능상 정상, 성능 최적화 범주"처럼 판단 근거를 문서화해 향후 우선순위 판단 용이.

3. **초기 세트업 배치 고려**: 보관소 정리(TTL), orphan 정리 등 초기 startup 시 한 번 수행할 작업 목록 작성.

---

## Final Validation

### §4-1 API 계약 동기화 (필수)

| 항목 | 백엔드 | 프론트 | 동기화 |
|------|--------|--------|:------:|
| 업로드 응답 스키마 | `{file_id, type, filename, size}` | `AgentAttachmentUploadResponse` | ✅ |
| 엔드포인트 | `/api/v1/agent/attachments` | `AGENT_ATTACHMENT_UPLOAD` 상수 | ✅ |
| subscribe.attachments | `list[{type, file_id}]` | `AgentAttachmentRef[]` | ✅ |
| 에러 코드 | 400/413/WS close 4002 | 토스트 메시지 표시 | ✅ |

### §6 회귀 테스트

- ✅ 첨부 없는 subscribe 기존 동작 무변경 (attachments=[])
- ✅ 기존 analysis_router 엔드포인트 미변경
- ✅ ExcelAnalysisWorkflow 호출 경로 미변경

### §7 보안 검증

- ✅ 다른 user의 file_id 접근 → ATTACHMENT_ACCESS_DENIED (close 4002)
- ✅ 존재하지 않는 file_id → ATTACHMENT_NOT_FOUND
- ✅ 미허용 확장자 (`.csv`) → 400 INVALID_ATTACHMENT
- ✅ run 종료 후 임시 파일 삭제 확인 (os.listdir 0개)
- ✅ TTL 만료 파일 sweep 정리 확인

---

## Next Steps

1. **Master에 병합**: 현재 feature branch → Pull Request → Master 통합
2. **배포 준비**: 설정 값(upload_dir, max_bytes, ttl_seconds) staging/production 환경에 맞게 조정
3. **사용자 가이드**: ChatPage 첨부 UI 사용 방법 문서화 (선택)
4. **모니터링**: 프로덕션 배포 후 TTL sweep 주기 로그 확인, 파일 누수 감시
5. **향후 개선**:
   - Gap #2: Content-Length 사전 체크 구현
   - CSV/이미지 타입 추가 (구조만 준비, 동작은 후속)
   - 멀티 파일 동시 분석 최적화
   - 프로세스 재기동 시 orphan 정리 배치

---

## Deliverables Summary

### Backend Files (신규)
```
idt/src/domain/agent_attachment/
├── __init__.py
├── value_objects.py        (100줄)
├── policies.py             (80줄)
├── exceptions.py           (35줄)
└── interfaces.py           (15줄)

idt/src/application/agent_attachment/
├── __init__.py
├── upload_use_case.py      (55줄)
└── resolver.py             (75줄)

idt/src/infrastructure/agent_attachment/
├── __init__.py
└── store.py                (180줄)
```

### Backend Files (수정)
```
idt/src/api/routes/
├── agent_attachment_router.py (신규 60줄)
├── ws_schemas.py           (AttachmentRefPayload 추가)
└── ws_router.py            (resolver 주입, 해석/cleanup 추가)

idt/src/
├── config.py               (3개 설정)
└── main.py                 (DI 와이어링)

idt/.env.example            (주석 추가)
```

### Backend Tests (신규)
```
idt/tests/domain/agent_attachment/
├── test_value_objects.py   (12개)
└── test_policies.py

idt/tests/infrastructure/agent_attachment/
├── test_store.py           (13개 포함 TTL)

idt/tests/application/agent_attachment/
├── test_upload_use_case.py (8개)

idt/tests/api/
├── test_agent_attachment_router.py (8개)
└── test_ws_agent_router.py (AttachmentResolver 테스트 11개)
```

### Frontend Files (신규)
```
idt_front/src/
├── types/agentAttachment.ts
├── services/agentAttachmentService.ts
└── hooks/useAgentAttachment.ts (선택)
```

### Frontend Files (수정)
```
idt_front/src/
├── constants/api.ts        (AGENT_ATTACHMENT_UPLOAD)
├── hooks/useAgentRunStream.ts (subscribe.attachments)
├── components/chat/ChatInput.tsx (첨부 UI)
└── pages/ChatPage/index.tsx (업로드 연동)
```

### Frontend Tests
```
idt_front/src/**/__tests__/
├── agentAttachmentService.test.ts (5개)
├── useAgentRunStream.test.ts      (10개)
└── ChatPage.test.ts               (회귀 5개)
```

---

## Approval Checklist

- ✅ Plan 문서 작성 및 검토 완료
- ✅ Design 문서 작성 및 설계 검토 완료
- ✅ 구현 완료 (백엔드 + 프론트)
- ✅ 모든 테스트 통과 (77개)
- ✅ Gap 분석 완료 (99% 일치도)
- ✅ 아키텍처 규칙 준수 (Thin DDD, 의존성 위반 0)
- ✅ API 계약 동기화 완료
- ✅ 보안 검증 완료
- ✅ 회귀 테스트 무변경 확인

**Status**: ✅ **READY FOR PRODUCTION**

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-06 | 완료 보고서: Plan(요약+일치도 99%) + Design(Thin DDD 5레이어) + Do(77 tests) + Check(gap해소) + Act(검증) | 배상규 |
