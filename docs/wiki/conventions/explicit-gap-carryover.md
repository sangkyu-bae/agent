---
title: PDCA gap은 억지로 메우지 말고 명시적 후속 태스크로 이월한다
status: draft
source_type: conversation
source_refs:
  - idt/docs/archive/2026-07/expose-user-department/expose-user-department.report.md (Lessons 1)
  - idt/docs/archive/2026-07/agent-memory-org-scope (G1로 남긴 원 사이클, Match 91%)
confidence: 0.8
version: 1
created: 2026-07-20
updated: 2026-07-20
verified_at: 6cc25656
---

# Gap 명시적 이월 패턴

## 문제

사이클 마감 시점에 남은 gap(예: "프론트에 부서 정보가 없어 UI를 완성 못 함")을
그 사이클 안에서 억지로 메우려 하면, 범위가 부풀고 사용자 결정 없이 임의 설계가
들어가 Match Rate가 떨어진다.

## 검증된 사실

- agent-memory-org-scope(91%)는 "프론트 부서 정보 부재"를 **G1으로 정직하게 이월**했다.
- 후속 소형 사이클 expose-user-department가 그 G1만을 범위로 잡아 사용자 지정
  결정 3건과 함께 **당일 완결, Match 100%, Act 0회, 회귀 0**으로 회수했다.
- 동형 선례: PII 마스킹(엔진 완성 → 배선은 pii-masking-integration으로 분리),
  agent-eval-gate의 agent 경로 평가 연동 이월.

## 다음에 적용하는 법

1. 사이클 범위 밖 의존성이 드러나면 스코프를 늘리지 말고 Report에 gap 번호(G1…)로
   기록하고 후속 기능명을 제안한다.
2. 후속 사이클은 그 gap **하나만** 범위로 잡는다 — 결정 지점이 적어 사용자 확인이
   빠르고, 100% 매칭 사이클이 나오기 쉽다.
3. 이월 항목은 PDCA Report의 "이월" 표에 반드시 남겨 추적 가능하게 한다
   (E2E·마이그레이션 배포도 동일 방식으로 이월 중).
