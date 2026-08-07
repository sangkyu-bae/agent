# agent-webhook-outbound (M2) Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Author**: 배상규
> **Completion Date**: 2026-08-07
> **PDCA Cycle**: #1 (Plan → Design → Do → Check, Act 반복 0회 — Check 직후 즉시 조치 4건)
> **선행**: agent-webhook M1 (동일자 아카이브, 93.3%)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | agent-webhook-outbound — 실행 결과 외부 발송 (웹훅 M2) |
| Start / End | 2026-08-07 (단일 세션, M1에 연이어 진행) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 1차 92.7% → 조치 후 93.8%       │
├─────────────────────────────────────────────┤
│  ✅ 누락 기능:            0건                │
│  ✅ 금지사항·FR-17 무회귀: 전항 통과          │
│  ✅ 테스트: 백엔드 94+회귀 39 · 프론트 30+5  │
│  🔧 Check 즉시 조치: 4건 (G1·G2·G8·G9)      │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | M1으로 외부→에이전트 호출은 열렸지만 결과가 플랫폼 안에만 남았다 — 스케줄 실행 결과를 보려면 매번 들어와야 하고, V057의 outbound 컬럼은 예약 상태였다 |
| **Solution** | 앱 수명 싱글턴 디스패처가 스케줄·inbound 웹훅 실행 완료 시 등록 URL로 M1 동형 HMAC 서명 payload를 POST — 재시도 4회(4xx 즉시 중단)·완전 오류 격리·V058 발송 이력 + 설정 탭 outbound UI(URL·토글·접힘 이력) |
| **Function/UX Effect** | URL 하나 등록으로 "스케줄 요약이 사내 수신 엔드포인트로 자동 도착"하는 push 채널 완성. 발송 실패는 이력 화면에서 상태코드·시도 횟수·오류로 즉시 진단. 신규 마이그레이션 1(V058)·신규 파일 백 5+프론트 0(확장만)·M1 코드 무수정 원칙 유지(additive 훅 2곳) |
| **Core Value** | 웹훅 채널 양방향 완성(M1 호출 + M2 발송) — 에이전트가 결과를 사내 시스템에 밀어 넣는 자동화 컴포넌트로 확장. 발송 서명이 M1 검증 코드로 재현되는 왕복 테스트(FR-15)로 계약 일관성 보장 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | `docs/01-plan/features/agent-webhook-outbound.plan.md` | ✅ |
| Design | `docs/02-design/features/agent-webhook-outbound.design.md` | ✅ (정정 3건 §5.2) |
| Check | `docs/03-analysis/agent-webhook-outbound.analysis.md` | ✅ (92.7→93.8%) |
| Act | 본 문서 | ✅ |
| M1 맥락 | `docs/archive/2026-08/agent-webhook/` | 참조 |

---

## 3. Completed Items

### 3.1 Functional Requirements (Plan FR-10~17)

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-10 | outbound URL 등록·수정·해제(null)·토글, 비허용 스킴 422 | ✅ | fields_set으로 미지정 vs null 구분 (D17) |
| FR-11 | 스케줄·inbound 실행 성공 시 서명 POST (수동 UI 실행 제외) | ✅ | 훅 ① 인라인 / 훅 ② spawn 비차단 |
| FR-12 | 재시도 최대 4회(1/2/4s 백오프) + delivery 이력 기록 | ✅ | 4xx 즉시 중단·2xx만 성공 (D13) |
| FR-13 | 발송 실패의 실행 결과·스케줄 이력 완전 격리 | ✅ | dispatch 무raise 계약 + 훅 이중 방어, 계약 위반 시나리오까지 테스트 |
| FR-14 | 설정 탭 outbound URL·토글·이력(20건) | ✅ | 이력은 접힘 기본·펼침 시 fetch (D21) |
| FR-15 | 발송 서명 = M1 inbound 스킴 (수신측 동일 코드 검증) | ✅ | M1 `verify()` 왕복 테스트 단언 |
| FR-16 | 훅 optional 주입 — 미주입 무동작 하위호환 | ✅ | 스케줄 팩토리 기본값 None |
| FR-17 | M1 무회귀 (PATCH enabled 단독·빈 body 422·프론트 반경) | ✅ | M1 테스트 무수정 통과 (빈 body는 스키마 validator로 422 유지) |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 오류 격리 | 발송 예외 미전파 | sender/이력 기록 예외 주입 테스트 통과 | ✅ |
| 보안 | 시크릿·payload 본문 로그 미전달 | 분석 §8 확인 (url·status·attempts만) | ✅ |
| DDL | V058 COMMENT·FK CHARSET 금지 | 검사 통과 (콤마 함정 선회피) | ✅ |
| 세션 규칙 | HTTP 발송 구간 세션 미보유 | tx1 조회→닫음→발송→tx2 기록 구조 확인 | ✅ |
| additive | M1 계약·테스트 무수정 | FR-17 검증 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 마이그레이션 | `db/migration/V058__create_agent_webhook_delivery.sql` (FK=agent_definition — 채널 재발급 후 이력 보존) | ✅ (배포 전 적용 필수) |
| domain | `WebhookOutboundPolicy`·`WebhookDelivery`·sender/delivery 인터페이스·`OutboundResult` | ✅ |
| infrastructure | `HttpxOutboundSender`(transport/sleep 주입) + `AgentWebhookDeliveryRepository`(INSERT only) | ✅ |
| application | `DispatchOutboundWebhookUseCase`(싱글턴·무raise) + PATCH 확장 + `ListWebhookDeliveries` + `WebhookValidationError` | ✅ |
| 훅 | 스케줄 `_run_one` + invoke `_dispatch_outbound` (optional·태스크 참조 보유) | ✅ |
| interfaces | deliveries GET + 422 매핑 + main.py DI(웹훅→스케줄 순서) | ✅ |
| 프론트 | WebhookSection outbound 하위 섹션 + types/service/hook/상수/queryKeys 확장 | ✅ |
| 테스트 | 신규 백엔드 5파일+확장 · 프론트 7케이스 추가 | ✅ |

---

## 4. Incomplete Items (Carried Over)

| Item | Reason | Priority |
|------|--------|----------|
| **E2E 수동 3종** (수신 서버 왕복·서명 재현·다운 시 재시도 이력) — **M1 G7과 일괄**, V057+V058 적용 선행 | 로컬 DB 미적용 | High |
| **커밋/PR** — M1+M2 워킹트리 누적 (마일스톤별 커밋 분리 권장) | 사용자 지시 대기 | High |
| G7 모델 복합 인덱스 정합 / G10 테스트 패키지 `__init__.py` | 무영향 백로그 (분석 §3) | Low |
| delivery 이력 정리 배치·발송 테스트 버튼·rate limit | Plan Out of Scope 명시 | Low~Medium |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final |
|--------|--------|-------|
| Design Match Rate | ≥ 90% | **93.8%** (1차 92.7% + 즉시 조치 4건) |
| 누락 기능 | 0 | 0 |
| 테스트 | 설계 §6 전 케이스 | 백엔드 웹훅 94 + 스케줄 회귀 39 + 프론트 settings 30·페이지 5, tsc 클린 |

### 5.2 Resolved Issues (Check 즉시 조치)

| Issue | Resolution |
|-------|------------|
| **G1**: `create_task` 반환 태스크 미보유 → GC로 inbound 발송 유실 가능 (유일한 기능 리스크) | `_background_tasks` set 보관 + `add_done_callback(discard)` |
| **G2**: 프론트 422 인라인 에러 테스트 누락 | `role=alert` 단언 케이스 추가 |
| **G8**: sender가 `httpx.HTTPError`만 포착 — 기타 예외 시 이력 미기록 | `except Exception` 확장 (이력 일관성) |
| **G9**: 테스트 데드코드 | 제거 |

### 5.3 설계 문서 정정 기록 (코드가 정답 — G3·G4·G5)

- `OutboundResult`는 domain 인터페이스 반환 타입이므로 **domain에 정의** (Design §4-3의 application 표기는 레이어 규칙 위반 — 코드 주석에 사유 명시).
- 훅·PATCH 테스트는 M1 파일 무수정 원칙에 따라 **신규 파일 분리**(`test_manage_webhook_outbound.py`·`test_outbound_hooks.py` — 스케줄 훅 포함 응집 배치).

---

## 6. Lessons Learned

### 6.1 Keep

- **요청 수명 제약이 설계를 확정**: "inbound 비차단 태스크는 응답 후 실행 → 요청 세션 사용 불가"라는 코드 제약이 D11(싱글턴+session_factory)을 자연 확정 — 미확정 항목을 질문 없이 닫을 수 있었다.
- **선례 재사용 3연타**: DbScheduleRunSink(세션 팩토리 싱글턴)·agent-memory(optional 주입)·useScheduleRuns(펼침 조회) — 설계 결정 대부분이 기존 패턴 지목으로 끝남.
- **M1 교훈 즉시 반영**: DDL 콤마 함정 선회피, 전용 예외(G5→D19), M1 파일 무수정 원칙.

### 6.2 Problem

- **create_task 참조 보유 누락(G1)**: "dispatch는 무raise니 안전"에 집중해 태스크 수명(GC) 관점을 놓침 — 비차단 태스크 설계 시 예외 누수와 **참조 수명**은 별개 체크 항목.
- Design의 테스트 배치 문구("기존 파일에 추가")가 M1 무수정 원칙과 상충 — 설계 시점에 정합 확인 부족.

### 6.3 Try

- 비차단 백그라운드 작업 도입 시 체크리스트화: ① 예외 격리 ② 태스크 참조 수명 ③ 세션/자원 수명 ④ 테스트 주입점.

---

## 7. Next Steps

- [ ] **커밋/PR** (git-workflow — M1/M2 커밋 분리)
- [ ] 배포: **V057+V058 적용** → E2E 일괄 체크리스트 (M1 G7 + M2 3종)
- [ ] 후속 후보: 발송 테스트 버튼, 이력 정리 배치, rate limit 사이클

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-07 | Completion report created | 배상규 |
