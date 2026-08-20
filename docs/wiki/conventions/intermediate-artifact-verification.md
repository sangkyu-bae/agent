---
title: 중간 산출물도 검증 대상 — Design의 FR 유실 + 검사 에이전트 판정의 실측 반증
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.analysis.md (G-04 에코백 유실, G-06 403 판정 반증, §8.1)
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.report.md (§6.2, §7 프로세스 개선 제안)
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.plan.md (FR-03 — 미지 tool_id 에코백 원요구)
  - idt/tests/api/test_agent_pipeline_router.py:400 (test_unknown_tool_ids_are_echoed — 복원 검증)
confidence: 0.8
version: 1
created: 2026-08-19
updated: 2026-08-19
verified_at: 7c3ffdd
---

# 중간 산출물도 검증 대상 — FR 역추적 + 판정 실측

## 문제

PDCA에서 구현은 Design을 따르고, gap 분석은 에이전트(gap-detector)가 수행한다.
이 중간 산출물들을 맹신하면 두 종류의 조용한 결함이 생긴다는 것이
agent-create-pipeline 사이클에서 실증됐다:

1. **Design은 Plan의 손실 압축일 수 있다** — Plan의 요구가 Design에서 빠지면,
   Design에 충실한 구현은 그 요구를 "성실하게" 누락한다.
2. **검사 에이전트의 판정도 틀린다** — 확신도가 높아도, 특히 "라이브러리 기본 동작"
   류 주장은 버전 의존적이라 실측과 다를 수 있다.

## 검증된 사실

### 1. Plan FR → Design 유실 (G-04)

Plan FR-03의 "미지 tool_id 에코백" 요구가 Design §4.3 응답 필드 목록에서 빠졌다.
구현은 Design에 충실했고 — `unknown_tool_ids`가 **계산까지 되고도 응답에서
버려졌다**. 테스트도 Design 기준으로 짜였으니 아무것도 실패하지 않았다.
gap 분석이 Plan까지 거슬러 대조해서야 적발됐고, Act-1에서 응답 필드로 복원
(`test_unknown_tool_ids_are_echoed`).

교훈: **구현·테스트가 Design에 정합해도 Plan 요구는 누락될 수 있다.** 정합성
검사의 비교 대상은 바로 위 단계가 아니라 원 요구다.

### 2. 검사 에이전트 판정의 실측 반증 (G-06)

gap-detector가 "FastAPI HTTPBearer의 무인증 기본 응답은 403인데 Design은 401만
명시했다"고 판정했다 (확신도 85%). 판정을 믿고 문서를 고치는 대신 **테스트를
`== 401`로 조여 실측**하자 — 이 FastAPI 버전에서는 401이 맞았고 Design이 처음부터
옳았다. 판정을 그대로 수용했다면 정확한 문서를 틀리게 고칠 뻔했다.

교훈: 에이전트 분석의 "기본 동작·기본값" 류 주장은 확신도와 무관하게 **런타임
테스트로 못박아 검증**한다. 부수 효과로 느슨한 단언(`in (401, 403)` 류)이 정확한
단언으로 조여진다.

## 다음에 적용하는 법

1. **Design 작성 시 "Plan FR → Design 절 매핑 표"를 둔다** — 모든 FR이 Design의
   어느 절에 착지했는지 1:1로 채운다. 빈 칸이 곧 유실이다 (report §7 채택 제안).
2. gap 분석 시 Design 정합만 보지 말고 **Plan FR 목록을 별도 축으로 재대조**한다
   (구현↔Design 97%여도 Plan 요구가 빠져 있을 수 있다).
3. 검사 에이전트가 낸 gap 중 "라이브러리/프레임워크의 기본 동작" 주장은 코드 수정
   전에 **재현 테스트부터 작성**한다 — 판정이 맞으면 그 테스트가 수정의 회귀 방지가
   되고, 틀리면 반증 증거가 된다.
4. 이 문서는 [[false-green-quality-gates]]와 짝이다 — 그쪽은 "초록 신호를 믿지
   말라", 이쪽은 "중간 문서·판정을 믿지 말라".
