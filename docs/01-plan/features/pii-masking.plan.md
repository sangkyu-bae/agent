# pii-masking Plan Document

> **Feature**: pii-masking
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-06-30
> **Status**: Plan
> **Type**: 신규 공용 모듈 (가역 PII 마스킹 엔진) — 파이프라인 전체 배선은 후속 plan

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 현재 LangGraph 경로(`create_react_agent`)에는 질문/검색 데이터에 섞인 개인정보를 외부 LLM으로 보내기 전 마스킹하는 단계가 없다. HTTP 로그 마스킹(`request_logging_middleware._mask_sensitive_data`)만 존재하고 LLM 입출력은 무방비다. |
| **Solution** | 프레임워크 독립적인 **가역 마스킹 엔진 모듈**(`domain/application/infrastructure/pii_masking`)을 먼저 만든다. 한국 PII(주민번호·휴대폰·이메일·계좌/카드)를 정규식으로 탐지해 `[RRN_1]` 같은 placeholder로 치환(`mask`)하고, 최종 응답에서 원복(`unmask`)한다. 미들웨어/훅 부착은 어댑터 인터페이스만 정의하고 실제 배선은 후속 plan으로 분리. |
| **Function/UX Effect** | 외부 LLM에는 원본 PII가 전달되지 않으면서도, placeholder 일관성 덕분에 모델이 "그 사람"·"그 계좌"를 추론할 수 있어 RAG 답변 품질이 유지된다. 사용자에게 보이는 최종 답변은 원본으로 복원된다. |
| **Core Value** | 금융/정책 문서 도메인에서 외부 LLM 호출 시 개인정보 유출 위험을 차단하는 재사용 가능한 단일 책임 모듈을 확보한다. |

---

## 1. Overview

### 1.1 Purpose

질문 데이터·검색 결과·LLM 응답에 포함된 개인정보(PII)를 **외부 LLM 경계에서** 가역적으로 마스킹/복원하는 공용 모듈을 만든다. 이번 범위는 **엔진 모듈 자체**이며, production 그래프 배선은 후속 작업으로 분리한다.

### 1.2 Background

- production 대화/Agent 경로는 `create_react_agent`(langgraph 0.2 prebuilt) 기반이다.
  - `src/application/general_chat/use_case.py:151`
  - `src/application/agent_builder/workflow_compiler.py:230`
- 이 경로는 langchain v1.0 `create_agent(middleware=[...])` 리스트를 받지 못한다. 따라서 빌트인 `PIIMiddleware`를 그대로 끼울 수 없다.
- 실험적 v2 경로(`src/application/middleware_agent/`)에는 `MiddlewareBuilder`가 `PIIMiddleware`를 조합하지만(`middleware_builder.py:49-54`), `langchain.agents.middleware`는 `pyproject.toml` 의존성에 없고 `try/except ImportError`로 None 처리되어 **실질적으로 비활성**이다.
- 빌트인 `PIIMiddleware`는 `email/credit_card/ip/mac_address/url`만 지원 → **한국 PII(주민번호·휴대폰·계좌)는 커스텀 detector 필수**.
- 결론: production 경로에 바로 쓸 수 있는 **프레임워크 독립 커스텀 모듈**이 필요하다. (사용자 결정)

### 1.3 Related Documents

- 미들웨어 에이전트 빌더 Task: `idt/src/claude/task/task-middleware-agent-builder.md` (AGENT-005)
- 관련 스킬: `langchain-middleware`, `langgraph`, `tdd`
- 기존 마스킹 참고: `src/infrastructure/logging/middleware/request_logging_middleware.py:215-235`

---

## 2. Scope

### 2.1 In Scope (이번 모듈)

- [ ] `domain/pii_masking`: `PiiType` enum, detector 인터페이스, `MaskingStrategy`, `MaskingResult`/`TokenMap` VO, 정책(`PiiMaskingPolicy`)
- [ ] 한국 PII detector (정규식): **주민등록번호, 휴대폰/전화번호, 이메일, 계좌/카드번호**
- [ ] `application/pii_masking`: `PiiMaskingService` — `mask(text) → (masked_text, token_map)`, `unmask(text, token_map) → text`
- [ ] **가역 마스킹**: placeholder 치환 + 요청 범위 토큰 매핑 + 응답 원복
- [ ] 동일 원본값 → 동일 placeholder (요청 내 일관성)
- [ ] 응답에서 매핑에 없는 신규 PII는 **단방향 redact**(방어적)
- [ ] 미들웨어/훅 부착용 어댑터 인터페이스 정의 (`PiiMaskingPort`)
- [ ] TDD 단위 테스트 (Red→Green→Refactor), 탐지 정확도/원복 정합성

### 2.2 Out of Scope (후속 plan)

- production `create_react_agent` 그래프에 `before_model`/`after_model` 훅으로 실제 배선
- `MiddlewareBuilder`의 `PIIMiddleware`에 custom detector 주입 배선
- 토큰 매핑의 멀티턴/세션 영속화(체크포인터 연동)
- NLP 기반 이름·주소 탐지(정규식으로 불충분한 항목)
- 프론트엔드 노출/설정 UI

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 주민등록번호/휴대폰·전화/이메일/계좌·카드번호를 정규식으로 탐지한다 (`PiiType`별 detector) | High | Pending |
| FR-02 | 탐지된 PII를 `[<TYPE>_<n>]` placeholder로 치환하고 `(masked_text, token_map)`을 반환한다 | High | Pending |
| FR-03 | 동일 원본값은 동일 placeholder로 매핑한다 (요청 범위 일관성) | High | Pending |
| FR-04 | `unmask(text, token_map)`이 placeholder를 원본으로 정확히 복원한다 (역치환 정합성) | High | Pending |
| FR-05 | 마스킹 대상 지점은 ①사용자 질문 입력 ②검색된 문서/tool 결과 ③LLM 응답 출력 3곳을 지원한다 (어댑터 진입점) | High | Pending |
| FR-06 | 응답 단계에서 token_map에 없는 신규 PII는 단방향 redact 처리한다 | Medium | Pending |
| FR-07 | 주민등록번호는 형식 외 생년월일/체크섬 등 약식 검증으로 오탐을 낮춘다 | Medium | Pending |
| FR-08 | 마스킹 on/off 및 타입별 활성화를 config로 제어한다 (하드코딩 금지) | Medium | Pending |
| FR-09 | token_map은 메모리 범위로만 다루고 영속 저장하지 않는다 (로그에도 원본 미기록) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 보안 | 외부 LLM 호출 경계에서 원본 PII 미전달, token_map 비영속·비로깅 | 코드 리뷰 + 로그 점검 |
| 정확도 | 대상 4종 탐지 재현율 우선(오탐<누락), 원복 round-trip 100% | pytest 픽스처 케이스 |
| 성능 | 평균 청크(수 KB) 마스킹 오버헤드 < 5ms (정규식, 외부호출 없음) | 단위 벤치 |
| 아키텍처 | domain→infrastructure 참조 금지, Thin DDD 레이어 준수 | `/verify-architecture` |
| 로깅 | `LoggerInterface` 사용, print 금지, PII 원본 미기록 | `/verify-logging` |
| 테스트 | 프로덕션 모듈 대비 테스트 존재 | `/verify-tdd` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-09 구현 및 단위 테스트 통과
- [ ] mask→unmask round-trip 정합성 테스트 통과
- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과
- [ ] 어댑터 인터페이스(`PiiMaskingPort`) 정의 — 후속 배선에서 import만 하면 되도록
- [ ] Design 문서(`pii-masking.design.md`) 작성

### 4.2 Quality Criteria

- [ ] 단위 테스트 커버리지 80% 이상 (모듈 한정)
- [ ] lint/타입 오류 0
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 정규식 오탐(정상 숫자를 PII로 마스킹) → 답변 왜곡 | High | Medium | 주민번호 체크섬·휴대폰 prefix 등 약식 검증(FR-07), 타입별 토글(FR-08) |
| 누락(탐지 실패) → PII 유출 | High | Medium | 재현율 우선 패턴, 응답단 2차 redact(FR-06), 케이스 픽스처 지속 보강 |
| placeholder가 LLM 응답에서 변형/소실되어 원복 실패 | Medium | Medium | 영숫자·대괄호 고정 포맷, unmask 시 정확 매칭, 미복원 placeholder 잔존 검출 테스트 |
| token_map 로깅/영속으로 인한 2차 유출 | High | Low | FR-09 강제, 로깅 시 키만 기록, 영속 계층 미연결 |
| 후속 배선 시 create_react_agent 훅 제약 | Medium | Medium | 본 plan은 엔진+포트까지만, 배선은 별도 plan에서 PoC |

---

## 6. Architecture Considerations

### 6.1 Project Level

| Level | Selected |
|-------|:--------:|
| Enterprise (Thin DDD: domain/application/infrastructure 분리, idt 백엔드 규칙) | ☑ |

### 6.2 모듈 구조 (신규 `pii_masking` sibling 모듈)

```
src/domain/pii_masking/
├── schemas.py        # PiiType(Enum), MaskingStrategy, PiiMatch, MaskingResult, TokenMap(VO)
├── detectors.py      # PiiDetectorInterface + 한국 PII 정규식 패턴 정의(규칙)
├── policies.py       # PiiMaskingPolicy (오탐 검증, 적용 타입 결정)
└── interfaces.py     # PiiMaskingPort (어댑터 진입점), LoggerInterface 사용

src/application/pii_masking/
├── schemas.py            # 요청/결과 DTO
└── pii_masking_service.py# mask()/unmask() 오케스트레이션 (흐름 제어만)

src/infrastructure/pii_masking/
└── regex_detectors.py    # 정규식 detector 구현체 (RRN/phone/email/account-card)
```

### 6.3 핵심 동작 (가역 마스킹)

```
[입력/검색결과]  --mask()-->  masked_text + token_map   --> 외부 LLM
                                   (요청 범위 누적)
[LLM 응답]      --unmask(token_map)-->  원복된 답변 --> 사용자
                 (+ 매핑에 없는 신규 PII는 redact)
```

- placeholder 포맷: `[RRN_1]`, `[PHONE_1]`, `[EMAIL_1]`, `[ACCOUNT_1]`, `[CARD_1]`
- 동일 원본 → 동일 placeholder (token_map 역인덱스로 보장)
- token_map 수명: 요청/세션 범위 메모리 (이번 모듈은 in-memory 컨테이너만, 영속 미연결)

---

## 7. Convention Prerequisites

### 7.1 기존 컨벤션

- [x] `idt/CLAUDE.md` Thin DDD 레이어 규칙
- [x] `docs/rules/logging.md` (LoggerInterface), `docs/rules/testing.md` (TDD)

### 7.2 환경변수

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `PII_MASKING_ENABLED` | 마스킹 전역 on/off | Server | ☑ |
| `PII_MASKING_TYPES` | 활성 PII 타입 목록(쉼표) | Server | ☑ |
| `PII_MASKING_OUTPUT_REDACT` | 응답단 미매핑 PII redact 여부 | Server | ☑ |

> 기본값은 `src/config.py`에 정의(하드코딩 금지). 실제 값은 `.env`/`.env.example` 반영.

---

## 8. Open Questions (Design 단계 전 확정 필요)

1. **계좌/카드 구분**: 카드번호는 빌트인 패턴 활용 + 한국 계좌(은행별 자릿수 상이)는 일반 숫자열 휴리스틱으로 갈지, 둘을 하나의 `ACCOUNT_CARD` 타입으로 합칠지.
2. **token_map 스코프 키**: request_id 단위로 충분한지, 멀티턴 대화에서 동일 PII 일관성을 위해 session_id까지 묶을지 (후속 영속화와 연결).
3. **응답 redact 표기**: 신규 PII redact 시 `[REDACTED_PHONE]` 형태로 타입 노출할지, 일괄 `[REDACTED]`로 할지.

---

## 9. Next Steps

1. [ ] Open Questions 1~3 확정
2. [ ] Design 문서 작성 (`/pdca design pii-masking`) — detector 정규식 명세·placeholder 규칙·포트 시그니처 확정
3. [ ] TDD 구현 (Red→Green→Refactor)
4. [ ] (후속 plan) production `create_react_agent` 경로 배선 + `PIIMiddleware` custom detector 연동

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-30 | 초안 (사용자 결정 반영: 커스텀 모듈·한국 PII 4종·가역 마스킹·3지점 적용) | 배상규 |
