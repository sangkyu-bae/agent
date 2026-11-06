# pii-masking-integration Planning Document

> **Summary**: 이미 구현된 가역 PII 마스킹 엔진을 대화 경로의 외부 LLM 경계에 배선한다. create_agent 경로는 미들웨어로, 직접 호출 경로는 같은 코어를 쓰는 공용 진입점으로 처리하고, MCP 호출·수신 시점의 PII를 검사한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-11-02
> **Status**: Draft
> **선행 사이클**: [pii-masking.plan.md](pii-masking.plan.md) · [report](../../04-report/pii-masking.report.md) (엔진 완료, 배선 범위 제외)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `pii_masking` 엔진은 2026-06에 완성됐지만 `config.py` 외에 참조하는 코드가 없어, 주민번호·계좌·연락처가 지금도 원문 그대로 외부 LLM으로 전송된다. |
| **Solution** | `PiiMaskingMiddleware`를 모든 create_agent 체인 맨 앞에 부착하고, 미들웨어를 지나지 않는 직접 호출(supervisor, final_answer, 파이프라인, 보조 LLM)은 같은 코어의 프록시로 처리한다. MCP 호출·수신 시점에 PII를 검사해 기록한다. vault는 런 범위로 둔다. |
| **Function/UX Effect** | 외부 LLM에는 `[PHONE_1]` 같은 placeholder만 전달된다. 사용자 답변, 도구 인자, 승인 초안, DB에는 원본이 유지되므로 화면과 도구 동작은 바뀌지 않는다. 기본은 shadow 모드이며, 오탐을 확인한 뒤 설정으로 on 전환한다. |
| **Core Value** | 금융 문서를 다루는 사내 에이전트가 고객 개인정보를 외부 LLM으로 보내지 않는다는 것을 코드와 계약 테스트로 보장한다. |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | 엔진은 있으나 배선이 없어 실효가 없다. 대화 경로의 PII가 외부 LLM으로 원문 전송된다. |
| **WHO** | P1(개인정보가 섞인 질문·문서를 다루는 사용자), P3(개인정보 처리를 통제해야 하는 관리자), P2(별도 설정 없이 보호받는 에이전트 소유자) |
| **RISK** | 미들웨어를 지나지 않는 경로의 누락, 숫자 오탐으로 인한 답변 품질 저하(날짜가 `[ACCOUNT_1]`로 치환), 스트리밍 중 placeholder 노출 |
| **SUCCESS** | 대화 경로의 모든 외부 LLM 호출 입력에서 원본 PII 0건, 사용자 화면·DB에 placeholder 0건, 코퍼스 오탐 기준 충족, shadow→on 전환이 설정만으로 가능 |
| **SCOPE** | 포함: 엔진 보정, 미들웨어, 직접 호출 경로, 대화 경로 보조 LLM, 스트리밍 원복, MCP 검사, shadow 관측. 제외: 외부 도구 인자 마스킹, 임베딩 API, 이미지, 이름·주소 탐지, vault 영속화, 프론트 UI |

---

## 1. Overview

### 1.1 Purpose

대화 경로의 외부 LLM 경계에서 개인정보를 가역 마스킹한다. 프로세스 내부(그래프 상태, 도구 실행, 승인, DB, 화면)는 원본으로 동작하고, 외부 LLM으로 나가는 전문에만 placeholder를 쓴다.

### 1.2 Background

선행 사이클의 후속 계획(report §4)을 2026-11-02 코드로 재검증했고, 전제 세 가지가 바뀌었다.

| 항목 | 선행 문서의 전제 | 현재 코드 | 이번 Plan의 결론 |
|------|-----------------|-----------|-----------------|
| 적용 방식 | production은 `create_react_agent`라 미들웨어를 쓸 수 없다 | langchain 1.3.16, 워커·일반 채팅이 `create_agent(middleware=[...])` 사용 (`workflow_compiler.py:973,1016`, `general_chat/use_case.py:320`) | 미들웨어를 기본 경로로 사용. `MiddlewareProvider`가 적용을 일괄 조립 |
| 빌트인 `PIIMiddleware` | custom detector만 주입하면 연동된다 | 전략이 block/redact/mask/hash뿐이고 `before_model`/`after_model` 훅만 제공. placeholder 원복과 도구 인자 복원을 지원하지 않음 | 사용하지 않고 커스텀 미들웨어 작성 |
| vault | session 단위 유지, Redis 영속화 + 암호화 | 원본은 이미 `conversation_message`에 있고 매 호출마다 전체 메시지를 다시 마스킹할 수 있음. 승인 재개 스냅샷도 원본 기준 | 런 범위 vault로 충분. 영속화·암호화 불필요, `TokenVaultRegistry`의 무한 증가 문제도 사라짐 |

엔진 품질도 그대로는 배선할 수 없다. 금융 문서 형식의 샘플 24건을 실제로 실행한 결과는 다음과 같다.

| 입력 | 결과 | 판정 |
|------|------|------|
| `2026-11-02` | ACCOUNT | 오탐. 규정 시행일을 LLM이 읽지 못함 |
| `123-45-67890` (사업자번호) | ACCOUNT | 오탐 (개인정보 아님) |
| `2026-001-0034` (문서번호), `2026110212345` (대출번호) | ACCOUNT | 오탐 또는 정책 결정 필요 |
| `110111-1234567` (법인등록번호) | RRN | 오탐 (재현율 우선 정책상 허용 여부 결정 필요) |
| `3333-01-1234567` (계좌) | 미탐지 | 누락. `\d{2,6}` 그룹 상한 때문 |
| `11-12-345678-90` (운전면허) | 일부만 ACCOUNT로 매칭 | 부분 치환 |

### 1.3 Related Documents

- 엔진: `docs/02-design/features/pii-masking.design.md` (§11.3의 연결 지점은 2026-06 기준이며 이 문서가 대체)
- 패턴: `docs/wiki/backend/patterns/prompt-injection-guard.md` (코퍼스 검증·기본 on 운영), `detachable-module-seam.md`, `ast-source-contract-tests.md`
- 패턴: `docs/wiki/backend/patterns/approval-gate-run-contract.md`, `grounding-rewrite-loop.md`, `mcp-runtime-tool-shape.md`
- 규칙: `docs/wiki/conventions/config-single-source-at-consumption.md`, `false-green-quality-gates.md`
- 참고: `docs/USER-SCENARIOS.md`, `docs/SOURCE-OF-TRUTH.md`, 비전 문서에 PII 항목이 없다. 사내 전용·금융 도메인 원칙에서 도출한 요구이며, 이 Plan이 범위를 정의한다.

---

## 2. Scope

### 2.1 In Scope

- [ ] **엔진 보정**: 코퍼스 기반 ACCOUNT·RRN 오탐/누락 수정, 런 범위 vault, 스트리밍용 분할 토큰 원복기
- [ ] **미들웨어**: `PiiMaskingMiddleware`, 컴파일러와 일반 채팅에서 체인 맨 앞에 부착
- [ ] **직접 호출 경로**: supervisor, final_answer, 전용 생성 노드, search/collect/action 파이프라인
- [ ] **대화 경로 보조 LLM**: 근거 판정, 대화 요약, 메모리 추출, 쿼리 재작성, 멀티쿼리, prompt guard 판정, 도구 선별 등
- [ ] **스트리밍**: 두 채팅 경로의 토큰 이벤트에서 placeholder 원복
- [ ] **MCP 검사**: 호출 인자·수신 결과의 PII 탐지·기록
- [ ] **운영 모드**: off/shadow/on, 기본 shadow, 탐지 집계 관측
- [ ] **우회 방지**: 대화 경로에 마스킹을 거치지 않는 LLM 호출이 새로 생기면 실패하는 계약 테스트
- [ ] **dead config 정리**: 소비 지점이 없던 `pii_masking_*` 키를 실제 소비 지점에 연결

### 2.2 Out of Scope (잔여 위험으로 명시)

| 항목 | 현재 상태 | 처리 |
|------|-----------|------|
| 외부 도구 인자 마스킹 (Tavily·Perplexity·외부 MCP) | 원본 인자가 전달됨 | 사용자 결정으로 제외. MCP는 검사·기록으로 위험 규모를 측정. 후속 사이클 입력 자료로 사용 |
| 임베딩 API (쿼리·문서) | 쿼리 원문이 외부 임베딩으로 전송됨 | 후속 |
| 이미지 첨부, 이미지 생성 입력 | 이미지 바이트는 텍스트 탐지 불가 | 후속. 텍스트 블록만 마스킹 |
| 문서 인제스트·평가·위키 환류·관리자 생성기의 LLM 호출 | 마스킹 미적용 | 대화 경로 외 범위. 계약 테스트의 허용 목록에 사유와 함께 기록 |
| 이름·주소·여권번호 탐지 | 정규식 5종만 지원 | 후속. NER 도입 필요. 이름은 계속 LLM에 전달됨 |
| vault 영속화 | 불필요 | 폐기. `TokenVaultStorePort` 제거 여부는 Design에서 결정 |
| 관리자 UI, 프론트 변경 | 없음 | 환경 설정으로 운영. API 스키마 변경 없음 |
| v2 `application/middleware_agent/` 레거시 경로 | 별도 모델 | 제외. 허용 목록에 기록 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `PiiMaskingMiddleware`는 모델 호출 직전에 system 포함 전체 메시지를 마스킹하고, 응답의 본문과 tool_calls 인자를 원복한다 | High | Pending |
| FR-02 | 마스킹은 그 호출의 요청에만 적용한다. 그래프 상태, 도구 실행, 승인 초안(`tool_args`), `conversation_message`, `ai_tool_call`에는 원본이 남는다 | High | Pending |
| FR-03 | 컴파일러가 미들웨어를 항상 체인 맨 앞에 부착해 에이전트 소유자가 해제할 수 없게 한다. 재시도·폴백보다 바깥에 둔다 (v0.2: 카탈로그 등록 제외, Design D-01) | High | Pending |
| FR-04 | 조립 실패 시 on 모드는 fail-closed로 실행을 중단한다 (`approval_gate` 선례). shadow 모드는 warning 후 계속한다 | High | Pending |
| FR-05 | supervisor, final_answer, 전용 생성 노드, search/collect/action 파이프라인의 직접 호출을 FR-01과 같은 코어로 처리한다. `with_structured_output` 결과도 원복한다 | High | Pending |
| FR-06 | 대화 경로 보조 LLM을 같은 코어로 처리한다. 대상 목록은 Design에서 파일 단위로 확정한다 | High | Pending |
| FR-07 | 대화 경로의 LLM 생성·호출 지점을 AST 계약 테스트로 검사하고, 허용 목록 외 우회가 추가되면 실패시킨다 | High | Pending |
| FR-08 | vault는 런 범위로 두고 런 안의 모든 워커·노드가 공유한다. 런 종료 시 폐기하며, 멀티턴 일관성은 매 호출 재마스킹으로 확보한다 | High | Pending |
| FR-09 | 두 채팅 경로의 토큰 이벤트에서 청크에 분할된 placeholder를 원복한다. 사용자에게 placeholder 조각이 노출되지 않아야 하며, 미완성 버퍼는 스트림 종료 시 내보낸다 | High | Pending |
| FR-10 | MCP 호출 시 인자, 수신 시 결과의 PII를 탐지해 타입·건수만 기록한다. 인자는 원본 그대로 전달하고, 결과는 다음 LLM 호출에서 마스킹한다 | High | Pending |
| FR-11 | 카테고리 파이프라인의 `tool.ainvoke`와 승인 후 집행(`mcp_executor`)을 포함해 FR-10이 MCP 호출 경로 전체에 적용된다. `wrap_tool_call`만으로 끝내지 않는다 | High | Pending |
| FR-12 | off/shadow/on 3모드를 지원하고 기본값은 shadow다. shadow는 탐지·기록만 하고 LLM 요청을 변경하지 않는다 | High | Pending |
| FR-13 | ai_run에 PII 스텝 또는 동등한 관측을 남긴다. 내용은 타입별 건수만 기록하고 원문·placeholder 매핑은 기록하지 않는다 | Medium | Pending |
| FR-14 | 탐지를 한국어 문장 기준으로 재작성한다. 조사가 붙은 PII를 탐지하고, 날짜·금액·표 숫자 오탐을 제거하며, 7자리 말미 계좌를 탐지한다. 사업자번호·문서번호·대출번호·법인등록번호 처리는 코퍼스에서 확정한다 | High | Pending |
| FR-15 | ~~사내 호스팅 모델 마스킹 생략~~ 이월. 폴백이 외부 모델로 넘어가면 우회되므로 사내 모델도 마스킹한다 (Design D-04) | Medium | Deferred |
| FR-16 | 멀티모달 content 블록은 텍스트만 마스킹하고 이미지 블록은 그대로 둔다 | Medium | Pending |
| FR-17 | LangSmith 추적이 켜진 환경에서도 추적 데이터에 원본 PII가 전송되지 않게 하거나, 불가능하면 on 모드와 추적 동시 사용을 기동 경고로 알린다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 보안 | 외부 전송 요청에 원본 PII 0건, 로그·ai_run에 원문·vault 값 0건 | 전송 직전 요청을 캡처하는 실런 테스트, 로그 패턴 검사 |
| 정확도 | 재현율 우선. 코퍼스에서 실제 PII 누락 0건, 날짜·금액·규정번호 오탐 0건 | `tests/fixtures/pii_masking/` 코퍼스 |
| 성능 | 호출당 마스킹 오버헤드 평균 20ms 미만 (수십 KB 컨텍스트 기준) | 단위 벤치 |
| 호환 | 기존 테스트 회귀 0건, API 스키마 변경 0건 | 정렬된 `FAILED` 목록 diff |
| 아키텍처 | domain→infrastructure 참조 금지. langchain 클래스 참조는 기존 격리 모듈 계약 준수 | `/verify-architecture`, AST 경계 테스트 |
| 로깅 | LOG-001 준수, 원본 미기록 | `/verify-logging` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-17 구현 및 테스트 통과
- [ ] 실런: 에이전트 경로(react 워커, MCP 파이프라인, 승인 재개)와 일반 채팅 경로에서 on 모드로 REST·WS 각 1회 이상 실행
- [ ] 실런 검증: 외부로 나간 요청에 원본 PII 없음, 답변·DB에 placeholder 없음, 도구는 원본 인자 수신
- [ ] 스모크: 사용자 입력의 이메일로 메일 도구 승인 흐름 실행 시 승인 화면과 집행 인자가 원본임을 확인
- [ ] 스트리밍 실런: 토큰 이벤트에 placeholder 조각 없음
- [ ] shadow→on 전환이 재배포 없이 설정 변경과 재기동만으로 가능
- [ ] `.env.example` 갱신, 배포 전 확인 사항을 Report에 기록 (bkit 정책으로 수기 반영이 필요할 수 있음)

### 4.2 Quality Criteria

- [ ] 신규·변경 모듈 커버리지 80% 이상
- [ ] 회귀 0건을 정렬된 `FAILED` 목록 diff로 증명
- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과
- [ ] 함수 40줄, if 중첩 2단계 규칙 준수
- [ ] fake 스트림 테스트만으로 완료 처리하지 않음 (compile된 그래프 실행 테스트 필수)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 미들웨어를 지나지 않는 경로로 PII 누출 | High | High | FR-05~07, 계약 테스트, 전송 직전 캡처 실런 |
| 숫자 오탐으로 답변 품질 저하 | High | High | 코퍼스 선행, shadow 관측 후 on 전환 |
| 스트리밍에 placeholder 조각 노출 | High | High | FR-09 버퍼형 원복기, 분할 경계 단위 테스트 |
| 도구 인자에 placeholder가 전달되어 오발송 | High | Medium | 응답 tool_calls 원복 필수, 고아 placeholder는 도구 실행 전 차단. 승인 스모크 |
| 근거 판정이 masked 답변과 원본 코퍼스를 비교해 오판 | Medium | Medium | 판정 입력을 같은 vault로 마스킹, 근거 판정 회귀 테스트 |
| 런 공유 vault가 동시 워커에서 경합 | Medium | Medium | `get_or_create`의 원자성 검토, 병렬 워커 테스트 |
| LLM이 placeholder를 변형 (`[phone_1]`, `PHONE_1`) | Medium | Medium | 변형 코퍼스 실측, 고아 처리 강화. on 전환 전 shadow 외 샘플 검증 |
| 모드 값 오타로 보호가 조용히 해제 | High | Low | 알 수 없는 값은 기동 실패 또는 on으로 처리. prompt guard G-10 재발 방지 |
| 외부 도구로 원본 PII 전달 | High | Medium | 이번 범위 밖으로 사용자 결정. FR-10 기록으로 규모 측정, Report 잔여 위험 명시 |
| 탐지 실패 fail-closed로 메시지 전체가 `[PII_MASKING_FAILED]`로 대체 | Medium | Low | 메시지 단위 격리, error 로그와 스택 기록 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `MiddlewareBuilder` | Application | `build_pii_masking` 정적 팩토리 추가 (카탈로그·마이그레이션 변경 없음, Design D-01) |
| `domain/pii_masking`, `application/pii_masking`, `infrastructure/pii_masking` | Module | 런 vault, 탐지 보정, 스트림 원복기, 검사 API |
| `Settings.pii_masking_*` | Config | 모드 추가, 소비 지점 연결 |
| `workflow_compiler.py`, `supervisor_nodes.py`, `*_pipeline.py` | Application | 직접 호출을 공용 코어로 전환 |
| `run_agent_use_case.py`, `general_chat/use_case.py` | Application | 토큰 원복, 런 vault 수명 |
| `MCPToolAdapter`, `approval/mcp_executor.py` | Infrastructure | PII 검사 추가 |
| 대화 경로 보조 LLM 어댑터 | Infrastructure | 공용 코어 적용 (목록은 Design) |
| `api/main.py` | DI | 서비스 조립, 주입 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `MiddlewarePlan.instantiate` | READ | `workflow_compiler.py:987,1021` 워커, `general_chat/use_case.py:475` | PII 미들웨어를 이 목록 앞에 부착. 목록 자체는 불변 |
| `ApprovalGateMiddleware` | WRAP | `workflow_compiler.py:988,1023` | 게이트보다 먼저 tool_calls가 원복되어야 함. 초안·`tool_args` 원본 검증 필요 |
| `llm.ainvoke` 직접 호출 | CALL | `supervisor_nodes.py:536`, `workflow_compiler.py:1812,1820,2246,2708`, `action_pipeline.py:152,154,242`, `collect_pipeline.py:211,255`, `search_pipeline.py:222,251,270` | 전환 대상 |
| `on_chat_model_stream` | READ | `run_agent_use_case.py:1446`, `general_chat/use_case.py:793` | 토큰 원복 추가, 기존 시퀀스 유지 |
| `tool.ainvoke` | CALL | `action_pipeline.py:325`, `collect_pipeline.py:239`, `search_pipeline.py:288` | `wrap_tool_call` 미경유. `MCPToolAdapter`에서 검사 |
| 승인 재개 | READ | `run_agent_use_case.py:1091`, `execute_scheduler.py:96`, `decide_use_case.py:251` | 새 vault로 시작. 스냅샷이 원본이므로 동작 유지 확인 |
| `resume_from_snapshot`, 백그라운드 잡, 웹훅 | CALL | `background_job/worker.py` 등 | 런 vault 생성 지점이 모든 진입점을 덮는지 확인 |
| `MiddlewareBuilder`의 v2 `PIIMiddleware` | READ | `application/middleware_agent/` | 변경 없음 |

### 6.3 Verification

- [ ] 위 소비처가 변경 후 정상 동작
- [ ] 미들웨어 맨 앞 부착이 기존 체인 순서와 충돌하지 않음
- [ ] API 응답 스키마 변경 없음 (프론트 수정 불필요)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation, DI | 복잡한 아키텍처 | ☑ (Thin DDD) |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 적용 구조 | 모델 래퍼 / 미들웨어 / 지점별 호출 | **미들웨어 + 직접 호출용 공용 코어** | 사용자 결정. 기존 미들웨어 체계로 운영하고, 미들웨어가 닿지 않는 직접 호출은 같은 코어로 보완 |
| MCP 검사 | 인자 마스킹 / 탐지·기록 | **인자·결과 탐지·기록, 결과는 다음 LLM 호출에서 마스킹** | "MCP 호출·수신 시 검사"와 "이번엔 LLM만" 두 결정을 함께 만족. 인자를 마스킹하면 메일 수신자 같은 실제 값이 깨짐 |
| LLM 범위 | Factory만 / 대화 경로 / 전체 | **대화 경로 전체** | 사용자 결정 |
| 출시 | shadow / 즉시 on / off | **shadow 후 on** | 사용자 결정 |
| vault 수명 | session+영속 / 런 범위 | **런 범위** | 원본이 이미 DB에 있어 영속화의 이득이 없고, 보안 표면만 늘어남 |
| 강제 수준 | 에이전트별 선택 / 항상 적용 | **항상 적용, 환경 설정으로만 해제** | 안전 기능이므로 P2가 해제할 수 없어야 한다. 카탈로그로 끄면 경계가 절반만 해제되어 제외 (v0.2) |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

domain/pii_masking/           패턴·정책 보정, 런 vault, 스트림 원복 규칙
application/pii_masking/      PiiMaskingService 확장 (메시지 mask/restore, 검사)
application/middleware/       MiddlewareBuilder에 PII 미들웨어 조립
infrastructure/pii_masking/   RegexPiiDetector 보정
infrastructure/mcp/           MCPToolAdapter 검사 이음매
```

```
요청 ─ 런 vault 생성
  ├ create_agent 워커·일반 채팅: PiiMaskingMiddleware → (재시도·폴백) → 외부 LLM
  ├ supervisor·final_answer·파이프라인: 공용 코어 → 외부 LLM
  └ 보조 LLM(판정·요약·메모리 등): 공용 코어 → 외부 LLM

외부 LLM 응답 → 원복 → 그래프 상태(원본) → 도구·승인·DB·화면
토큰 스트림 → 버퍼형 원복기 → TOKEN 이벤트
MCP 호출·수신 → 탐지·기록 (값 불변)
```

공용 코어의 형태(헬퍼, `Runnable` 래퍼, ContextVar 전달)와 `with_structured_output` 처리는 Design에서 3안 비교로 확정한다.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md`, `idt/CLAUDE.md` 코딩 규칙
- [x] `idt/docs/rules/` 로깅·테스트·도구 규칙
- [x] DDL COMMENT 검사 (`tests/db/test_migration_ddl_comments.py`)
- [x] 미들웨어 격리 계약 (langchain 클래스 참조는 builder·gate 모듈에 한정, D8)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **코퍼스** | prompt guard 방식 존재 | `tests/fixtures/pii_masking/{pii,benign}.txt`, 선의 문장 먼저 작성 | High |
| **허용 목록** | 없음 | 마스킹 제외 LLM 호출을 사유와 함께 선언 | High |
| **Environment variables** | `.env.example`에 3키 존재 | 모드 키 추가, 소비 지점을 docstring에 명기 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `PII_MASKING_ENABLED` | 전역 킬스위치 (기존, 소비 지점 신규 연결) | Server | ☐ |
| `PII_MASKING_MODE` | `shadow`(기본) 또는 `on` | Server | ☑ |
| `PII_MASKING_TYPES` | 활성 타입 (기존, 소비 지점 신규 연결) | Server | ☐ |
| `PII_MASKING_OUTPUT_REDACT` | 제거 (v0.2, Design D-05). `.env.example`에서도 삭제 | Server | ☐ |

### 8.4 Pipeline Integration

해당 없음. 이 프로젝트는 9-phase 파이프라인을 사용하지 않는다.

---

## 9. Next Steps

1. [ ] `/pdca design pii-masking-integration`: 공용 코어 3안 비교, 보조 LLM 파일 목록, 체인 순서, `with_structured_output`·스트림 처리 확정
2. [ ] 코퍼스 작성 후 탐지 보정 (module-1 우선, 배선 전 완료)
3. [ ] TDD 구현, 경로별 실런
4. [ ] 운영 shadow 집계 확인 후 on 전환
5. [ ] 잔여 위험(외부 도구, 임베딩, 이미지, 이름·주소)을 후속 Plan 후보로 등록

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | 초안. 2026-06 전제 재검증, 사용자 결정 4건 반영(미들웨어+MCP 검사, 대화 경로 전체, shadow, 외부 도구 제외) | 배상규 |
| 0.2 | 2026-11-02 | Design Option C 반영. 카탈로그·V082 제외(FR-03), FR-15 이월, `OUTPUT_REDACT` 제거, FR-14를 한국어 문장 기준 재작성으로 확대 | 배상규 |
