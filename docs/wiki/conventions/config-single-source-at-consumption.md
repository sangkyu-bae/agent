---
title: 운영 config는 소비 지점 기준 단일 출처 — dead config 함정
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.analysis.md (G-02/G-03, §8.1)
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.report.md (§1.5 Design D6→G-02, §6.2, §6.3)
  - idt/src/infrastructure/config/intent_config.py:32-38 (slot_limits() — 단일 출처 VO 변환) 
  - idt/src/api/main.py "Agent Create Pipeline DI" 블록 (_pipeline_limits 주입) — ⚠️ 미커밋
  - idt/tests/application/agent_create_pipeline/test_use_case.py:315 (test_round_is_reclamped_before_intent_call)
confidence: 0.8
version: 1
created: 2026-08-19
updated: 2026-08-19
verified_at: 7c3ffdd
---

# 운영 config는 소비 지점 기준 단일 출처 — dead config 함정

## 문제

새 기능(파이프라인)이 기존 모듈(intent)의 상한값을 쓰면서 "파이프라인 쪽에서
오버라이드 가능하게" 별도 config(`AGENT_PIPELINE_MAX_QUESTIONS` 등 3종)를 만들었다.
선의의 설계였지만 **실제 상한은 intent 어댑터가 자기 `INTENT_*` config에서 직접 읽고
있어** 오버라이드가 소비 지점에 도달하지 못했다 — 조립은 되지만 아무도 읽지 않는
**dead config**. 운영자가 값을 바꿔도 동작이 안 변하는, 발견이 매우 어려운 종류의
결함이다 (gap 분석 G-02/G-03에서야 적발).

## 검증된 사실

1. **config의 유효성은 "정의했는가"가 아니라 "소비 지점이 그 값을 읽는가"다.**
   같은 의미의 상한이 두 config에 존재하면, 둘 중 하나는 반드시 dead가 되거나
   두 소비 지점이 서로 다른 값으로 갈린다 (G-03: 파이프라인 clamp 기준 vs intent
   프롬프트 상한 불일치 가능).
2. **해법은 소비 지점 기준 단일 출처화** (Act-1): `AGENT_PIPELINE_MAX_*` 3종을
   삭제하고 `IntentConfig.slot_limits()`가 유일한 출처가 됐다. main.py가 이 VO를
   파이프라인에 주입하므로, 값이 하나뿐이라 어긋날 방법이 없다. domain이 env를 직접
   읽지 않도록 config→VO 변환 메서드를 거친다 (규약 C3).
3. **"오버라이드 가능성"은 요구가 생겼을 때 추가한다.** 이번 사례에서 오버라이드
   요구는 가정이었고, 가정을 위해 만든 이원화가 실결함을 낳았다. additive하게 나중에
   붙이는 편이 안전하다.

## 다음에 적용하는 법

1. 새 config 키를 추가하기 전에 **같은 의미의 값이 기존 config에 있는지** 먼저
   찾는다. 있으면 기존 config의 VO 변환 메서드(예: `slot_limits()`)를 주입받는
   형태로 재사용하고 새 키를 만들지 않는다.
2. 부득이 새 키를 만들면 **소비 지점 파일:라인을 config docstring에 명기**한다
   (report §6.3 Try 항목). "조립되지만 안 읽히는" 상태를 리뷰에서 잡을 수 있는
   유일한 단서다.
3. gap 분석·리뷰 시 체크: `main.py`에서 조립되는 config 값마다 "이 값을 최종
   소비하는 코드가 어디인가"를 한 번씩 추적한다. 추적이 안 되면 dead config다.
4. 상한·클램프 류는 테스트로 "주입된 한 출처의 값이 실제 동작을 바꾼다"를 고정한다
   (`test_round_is_reclamped_before_intent_call` 형태).
