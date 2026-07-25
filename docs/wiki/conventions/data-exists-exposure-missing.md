---
title: "데이터는 있고 노출 경로만 없다" 패턴 — 신규 계산 전 기존 산출물 노출 여부 먼저 확인
status: draft
source_type: conversation
source_refs:
  - idt/docs/archive/2026-07/expose-user-department/expose-user-department.report.md (Lessons 2)
  - idt/docs/archive/2026-07/agent-eval-gate/agent-eval-gate.report.md (§6 학습 포인트)
  - 커밋 7a558832 (idt/src/application/general_chat/use_case.py — _persist_messages 반환 id 캡처)
  - 커밋 13dde254 (/auth/me MeResponse — AuthContext가 이미 조립하던 부서 정보 노출)
confidence: 0.9
version: 1
created: 2026-07-20
updated: 2026-07-20
verified_at: 6cc25656
---

# "데이터는 있고 노출 경로만 없다" 패턴

## 문제

기능 요구가 "X를 보여달라/쓰게 해달라"일 때, X를 새로 계산·저장하는 설계로 직행하면
과잉 구현이 된다. sangplusbot에서는 **X가 이미 내부에서 계산되고 있는데 응답/이벤트로
노출만 안 되던 경우**가 반복적으로 확인됐다.

## 검증된 사실 (동형 사례 4건)

| 사이클 | 이미 있던 데이터 | 없던 것 = 실제 작업 |
|--------|------------------|---------------------|
| retrieval-observability | 검색 파이프라인 실행 정보 | 관측 노출 경로 |
| agent-workspace-view | 에이전트 구성 데이터 (백엔드 diff 0) | 폴더형 열람 뷰 |
| expose-user-department | AuthContext가 조립하는 부서 정보 (`find_departments_by_user`) | `/auth/me` 응답 필드 (UserResponse가 잘라내고 있었음) |
| agent-eval-gate | `_persist_messages` 내 `save()` 반환 message id (받고서 버리고 있었음) | ANSWER_COMPLETED payload의 `assistant_message_id` |

특히 agent-eval-gate에서는 **폐기되던 반환값을 캡처하는 것만으로** 스트리밍 답변에
즉시 평가를 부착할 수 있었다(신규 계산 0).

## 다음에 적용하는 법

1. "노출/연동" 성격의 요구를 받으면, 설계 전에 다음을 먼저 검색한다.
   - 백엔드: 해당 데이터를 이미 계산·조회·저장하는 UseCase/Repository가 있는가
   - 반환값이 받아지고도 버려지는 곳(`_ = save(...)` 류)이 있는가
   - 응답 스키마가 내부 객체보다 좁게 잘라 반환하고 있는가
2. 있다면 작업 범위는 "노출 경로 추가"(additive 필드, 신규 응답 타입, 이벤트 payload 확장)로
   좁힌다. 마이그레이션 0, 회귀 0으로 끝나는 경우가 많다.
3. PDCA Plan 단계에서 이 확인 결과를 명시하면 Match Rate가 높게 나온다
   (expose-user-department 100%, agent-eval-gate 97%).
