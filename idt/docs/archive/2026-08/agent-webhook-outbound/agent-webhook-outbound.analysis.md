# Agent Webhook Outbound (M2) Gap Analysis (Check)

> **Feature**: agent-webhook-outbound
> **Date**: 2026-08-07
> **Analyzer**: gap-detector (48항목 정적 대조)
> **Design SoT**: `docs/02-design/features/agent-webhook-outbound.design.md`
> **Match Rate**: 1차 **92.7%** (44.5/48) → 즉시 조치 4건 반영 후 **93.8%** (45/48)
> **판정**: 임계 90% 통과 — 누락 기능 0건, Act 반복 불요

---

## 1. 요약

- **D11~D21 설계 결정 전부 구현 일치** — 싱글턴 디스패처(요청 세션 비의존·발송 구간 세션 미보유), 스케줄 인라인/invoke 비차단, 재시도 정책(4xx 즉시 중단), M1 동형 서명, fields_set 기반 PATCH, 전용 예외, INSERT-only 이력, 접힘 기본 조회.
- **금지 사항 전부 통과**: 시크릿·payload 로그 미전달, delivery 변경 경로 부재, repo commit 없음.
- **FR-17(M1 무회귀) 검증됨**: M1 테스트 무수정 통과(빈 body 422는 스키마 validator로 유지), `useUpdateWebhook` 호출부 반경 WebhookSection 단독 grep 확인.
- 유일한 기능적 리스크였던 **G1(create_task GC)** 포함 4건을 Check 직후 즉시 조치.

## 2. Check 직후 즉시 조치 (1차 92.7% → 93.8%)

| Gap | 조치 | 검증 |
|-----|------|------|
| **G1 (Medium)** `asyncio.create_task` 반환 태스크 미보유 — GC로 inbound 발송 유실 가능("Task was destroyed but it is pending") | `_background_tasks` set 보관 + `add_done_callback(discard)` (`invoke_webhook_agent_use_case.py`) | 백엔드 84 재통과 |
| **G2 (Medium)** 프론트 422 인라인 에러 테스트 부재 (Design §6 프론트 7케이스 중 1 누락) | `WebhookSection.test.tsx`에 "저장 실패 시 `role=alert` 서버 메시지 표출" 케이스 추가 | 프론트 재실행 통과 |
| **G8 (Low)** sender `_attempt`가 `httpx.HTTPError`만 포착 — InvalidURL 등은 이력 미기록으로 유출 | `except Exception`으로 확장 (사유 주석) | 백엔드 재통과 |
| **G9 (Trivial)** 테스트 데드코드 `_sync_spawn` | 제거 | — |

## 3. 잔여 Gap (코드 수정 불요 — 문서 정합·백로그)

| ID | Gap | 심각도 | 처리 방침 |
|----|-----|:--:|------|
| G3 | `OutboundResult` 위치: Design §4-3은 application, 구현은 domain — **구현이 옳음**(domain 인터페이스 반환 타입은 application 참조 불가, 코드에 사유 주석) | Low(문서) | Report에 설계 정정 기록 |
| G4 | 스케줄 훅 테스트가 `tests/application/agent_schedule/`가 아닌 `agent_webhook/test_outbound_hooks.py`에 위치 | Low(문서) | 훅 2곳을 한 파일에 모은 응집 선택 — 문서 정정 기록 |
| G5 | PATCH/invoke 훅 테스트를 기존 M1 파일 "추가"가 아닌 신규 파일로 분리 | Low(문서) | M1 파일 무수정 원칙과 정합 — 문서 정정 기록 |
| G6 | 훅 ②에 방어적 try/except 없음 (D16 본문 표현과 §4-4 표가 상이 — 구현은 §4-4 표 준수) | Info | dispatch 무raise 계약 + 코루틴 생성은 raise 불가 — 수용 |
| G7 | 모델 인덱스 단일 컬럼 vs DDL 복합 인덱스 | Low | 운영은 Flyway DDL 기준 — 무영향. 백로그 |
| G10 | `tests/*/agent_webhook/`에 `__init__.py` 부재 + 교차 import | Low | 현 pytest 모드에서 정상 동작 — 구조 변경은 회귀 리스크 대비 이득 낮아 백로그 |

## 4. 그룹별 결과 (1차 기준)

| 그룹 | 항목 | 일치 | 비고 |
|------|:--:|:--:|------|
| §2 D11~D21 | 11 | 10.5 | D16 훅② 이중화 표현 차이 0.5 |
| §3 V058 DDL/모델 | 6 | 5.5 | 모델 인덱스 형태 0.5 |
| §4 백엔드 (파일·sender·디스패처 tx·DI 순서) | 13 | 12.5 | OutboundResult 위치 0.5 |
| §5 프론트 | 10 | 10.0 | 전부 일치 |
| §6 테스트 | 8 | 6.0→7.0 | 위치 차이 3건 각 0.5 + 422 케이스(G2, 조치 후 회복) |
| §8 금지·FR-17 | 7 | 7.0 | 전부 통과 |

## 5. 판정·다음 단계

- 93.8% ≥ 90% → **Check 통과**, iterate 불요.
- 다음: `/pdca report agent-webhook-outbound`.
- 배포 전 필수: **V057+V058 적용** → E2E 수동 3종(수신 서버 왕복·서명 재현·다운 시 재시도 이력 — M1 G7과 일괄).
- 커밋/PR: M1+M2 워킹트리 누적 상태 — 커밋 분리 권장.
