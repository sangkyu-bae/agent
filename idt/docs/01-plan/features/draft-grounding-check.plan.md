# draft-grounding-check Planning Document

> **Summary**: 외부 발송 **초안**과 채팅 **최종 답변**이 런 근거(에이전트 지침·위키·조회 결과·대화)에 없는 주장을 담지 않게 한다. 기존 `HallucinationEvaluator`(참/거짓 LLM 판정기)를 **근거 없는 주장 목록을 돌려주는 근거 판정기**로 확장하고, 판정 결과를 사유로 넣어 **재작성**한다(상한 N회, 초과 시 해당 문장 제거). 결정적 값 대조(전화·URL 등)는 판정기에 주는 **힌트**로만 쓰고 최종 판단은 판정기가 한다 — "어떤 질문에서는 나와도 되는 값" 을 맥락으로 판단하기 위함.
>
> **Project**: sangplusbot (idt)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-30
> **Status**: Draft (v0.2)
> **Depends on**: action-category-compose-node, approval-gate-run-termination, (기존) hallucination 모듈

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 실측(2026-09-30, 문의 63116): 초안 작성 노드와 final_answer 가 문의 원문·위키·지침 어디에도 없는 "대표번호: 1877-9900" 을 반복 생성. 기존 `HallucinationEvaluator` 는 리서치·엑셀 워크플로 전용이며 참/거짓만 돌려줘 "무엇을 고칠지" 알 수 없다. 규칙 기반(정해진 값 금지)은 값의 적절성이 질문마다 다르다는 점을 판단하지 못한다. |
| **Solution** | ① 기존 판정기 확장 — 질문·근거·생성문을 받아 **근거 없는 주장 목록(원문 구간·이유·심각도)** 반환(기존 참/거짓 API 하위호환). ② 공통 **근거 재작성 루프** — 생성 → 판정 → 사유 넣어 재작성(≤N) → 초과 시 해당 문장 제거. ③ 규칙 힌트 — 근거 문자열에서 찾지 못한 전화·URL·이메일·계좌·금리를 판정기에 참고로 전달. ④ 적용 — action 초안 작성 노드 + final_answer. ⑤ 판정·재작성 LLM 호출은 채팅 스트리밍에서 제외. |
| **Function/UX Effect** | 승인함 초안과 채팅 답변에서 근거 없는 주장이 빠지고 "고객센터로 문의해 주세요" 처럼 값 없이 안내한다. 근거에 있거나 질문 맥락상 적절한 값은 유지된다. 재작성이 일어나면 채팅 말풍선은 완료 시점에 최종본으로 교체된다. |
| **Core Value** | 특정 값·도구 하드코딩 없이 **맥락으로 판단**하는 일반 장치. 기존 판정기를 재사용·확장해 중복 구현이 없고, 승인자·사용자의 주의력에만 기대지 않는다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 초안·답변 LLM 이 근거 없는 사실(연락처 등)을 반복 생성 — 금융 고객 응대에 지어낸 정보가 섞일 위험. 값의 적절성은 질문마다 달라 고정 규칙으로는 판단 불가. |
| **WHO** | P2 — 에이전트 소유자·승인자, 채팅 사용자, 최종 수신 고객. |
| **RISK** | 판정기 LLM 비용·지연(답변마다 +1 호출) → 근거가 있는 런에만, 전역 토글. 판정기 오판(과검출로 정상 내용 삭제 / 미검출) → 규칙 힌트 병행, 심각도 high 만 재작성, 판정 실패 시 원문 유지(fail-open). 판정기 JSON 이 채팅에 새는 문제 → 내부 호출 태그로 스트리밍 제외. |
| **SUCCESS** | L3 "63116 답변 등록해줘" 초안·채팅 답변에 근거 없는 연락처 0 / 근거에 있는 값 유지 / 판정 실패 시 답변 정상 반환 / 판정·재작성 토큰이 채팅에 노출 0 / 기존 리서치·엑셀 워크플로 판정 회귀 0. |
| **SCOPE** | 판정기 확장(domain 포트·어댑터) → 공통 재작성 루프 → action 초안 적용 → final_answer 적용 → 스트리밍 필터 → 설정. |

---

## 1. Overview

### 1.1 Purpose
외부 발송 초안과 채팅 최종 답변을 **근거 판정 → 재작성** 루프에 통과시켜, 근거 없는 주장이 사용자·고객에게 나가지 않게 한다.

### 1.2 Background
- 실측 런 `1686f0c2`(final_answer), `0a4a2629`(action 초안) 모두 "대표번호: 1877-9900" 포함 — 근거 어디에도 없음.
- 작성 프롬프트에 "없는 내용은 지어내지 않는다" 규칙이 이미 있으나 무력.
- 기존 자산: `domain/hallucination`(정책·결과 VO), `application/hallucination/use_case.py`, `infrastructure/hallucination/adapter.py`(관리자 유틸리티 LLM, 구조화 출력) — 리서치 에이전트 `check_hallucination` 노드와 엑셀 분석 워크플로가 사용. **에이전트 빌더 경로에는 미연결.**
- 기존 결함: `application/hallucination/use_case.py` 가 infrastructure 어댑터를 직접 import(레이어 위반) — 확장하며 domain 포트로 정리.
- v0.1(규칙 기반 결정적 차단)에서 사용자 피드백 "정해진 값이 어떤 질문에서는 나와도 된다" 로 v0.2 에서 LLM 근거 판정 + 규칙 힌트로 전환.

### 1.3 Related Documents
- `docs/01-plan/features/approval-gate-run-termination.plan.md`, 리포트 §4.1
- `src/claude/task/task-hallucination-evaluator.md` (기존 판정기 태스크)

---

## 2. Scope

### 2.1 In Scope
- [ ] **판정기 확장**: domain 포트 `GroundingJudgePort.judge(question, sources, generation, hints) -> GroundingVerdict`. VO: `GroundingVerdict(grounded, unsupported_claims)`, `UnsupportedClaim(span, reason, severity)`. 기존 어댑터에 구현 추가, 기존 `evaluate()`(참/거짓) 유지.
- [ ] **레이어 정리**: 기존 use case 가 infrastructure 를 직접 import 하던 것을 포트 경유로(동작 불변).
- [ ] **규칙 힌트**: 결정적 추출(전화·URL·이메일·계좌·금리%) 후 근거 문자열에서 찾지 못한 값을 `hints` 로 판정기에 전달. 차단 권한 없음.
- [ ] **공통 재작성 루프**: 생성 → 판정 → high 심각도 주장 있으면 사유 넣어 재작성(≤N) → 초과 시 해당 문장 제거. 판정 실패(예외·타임아웃) 시 원문 유지 + 경고(fail-open).
- [ ] **적용 1 — action 초안 작성 노드**: 외부 발송 초안(승인 게이트 경로 포함).
- [ ] **적용 2 — final_answer**: 근거(워커 산출)가 있는 런만.
- [ ] **스트리밍 필터**: 판정기·재작성 호출은 내부 태그 → 채팅 토큰 이벤트에서 제외. 재작성 시 최종 답변은 완료 이벤트로 교체.
- [ ] **설정**: 전역 `grounding_check_enabled`(기본 on), `grounding_max_retries`(기본 1~2, Design 확정).
- [ ] **관측**: 판정 결과(주장 수·심각도·재작성 횟수·문장 제거 수) 로그 — 주장 원문은 미기록.

### 2.2 Out of Scope
- 승인 화면 경고 배지(v0.1 Q-4 유지)
- 에이전트별 토글 UI(후속 — 전역 설정으로 시작)
- 리서치·엑셀 워크플로의 판정 방식 변경(기존 참/거짓 유지)
- 오프라인 평가(RAGAS) 연계

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | 판정기는 (질문, 근거, 생성문, 힌트)를 받아 근거 없는 주장 목록(생성문 **원문 구간**·이유·심각도 high/low)을 반환 | High |
| FR-02 | 질문 맥락상 적절한 일반 안내(예: "고객센터로 문의")는 주장으로 보지 않는다 — 판정 프롬프트 기준 | High |
| FR-03 | 규칙 힌트: 근거에서 찾지 못한 고위험 값 목록을 판정기에 전달, 판정은 판정기가 | High |
| FR-04 | high 주장이 있으면 사유(주장·이유)를 넣어 재작성, 최대 N회 | High |
| FR-05 | N회 후에도 남으면 해당 주장이 든 문장 제거. 제거 후 빈 본문이면 초안: 작성 실패 / 답변: 원문 유지 + 경고 | High |
| FR-06 | 판정 실패 시 원문 유지(fail-open) + 경고 로그 | High |
| FR-07 | action 초안 작성 노드에 적용 | High |
| FR-08 | final_answer 에 적용 — 워커 산출(근거)이 없는 런은 건너뜀 | High |
| FR-09 | 판정·재작성 LLM 토큰은 채팅 스트림에 노출하지 않음 | High |
| FR-10 | 기존 `evaluate()` 참/거짓 API·리서치·엑셀 사용처 불변 | High |
| FR-11 | 전역 설정 토글·재작성 상한 | Medium |
| FR-12 | 관측 로그(수치만) | Medium |

### 3.2 Non-Functional Requirements

| Category | Criteria |
|----------|----------|
| 비용 | 판정 1회/대상. 근거 없는 런·설정 off 는 추가 호출 0 |
| 지연 | 재작성 상한 N 으로 제한 |
| 안전 | 판정 실패가 답변·초안을 막지 않음 (fail-open) — 승인 게이트가 최종 방어선 |
| 아키텍처 | 포트는 domain, 어댑터는 infrastructure, 루프는 application — 기존 레이어 위반 해소 |

---

## 4. Success Criteria

- [ ] SC-1: L3 "63116 답변 등록해줘" ×3 — 승인 초안에 근거 없는 연락처 0
- [ ] SC-2: L3 채팅 답변(비게이트 질문) — 근거 없는 연락처 0
- [ ] SC-3: 근거(위키)에 대표번호가 있으면 유지 — 과검출 0
- [ ] SC-4: 판정기 예외 시 원문 유지, 런 성공
- [ ] SC-5: 판정기 JSON·재작성 토큰이 채팅 토큰 이벤트에 0
- [ ] SC-6: 리서치·엑셀 판정 테스트 회귀 0, 전체 회귀 상시 목록 외 실패 0

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 답변마다 +1 LLM 호출 | Medium | High | 근거 있는 런만, 전역 토글, 유틸리티 모델 |
| 판정기 과검출로 정상 내용 삭제 | High | Medium | high 만 재작성·제거, 일반 안내는 주장 아님(FR-02), 제거는 상한 후에만 |
| 판정기 미검출 | Medium | Medium | 규칙 힌트 병행 |
| 판정 JSON 채팅 누출 | High | High(무대응 시) | 내부 태그 + 스트림 필터(FR-09) |
| 재작성 시 채팅 말풍선이 바뀜 | Low | Medium | 완료 이벤트 교체 — 문서화 |
| 기존 판정기 변경이 리서치·엑셀 회귀 | Medium | Low | 신규 메서드 추가, 기존 메서드 불변 |

---

## 6. Impact Analysis

| Resource | Change | Consumers |
|----------|--------|-----------|
| `infrastructure/hallucination/adapter.py` | `judge()` 추가 | 리서치·엑셀(기존 `evaluate` 불변) |
| `application/hallucination/use_case.py` | 포트 경유 | 리서치 워크플로, 엑셀 워크플로 |
| `action_pipeline` 작성 단계 | 루프 적용 | 모든 action 워커 |
| `_create_final_answer_node` | 루프 적용 | 워커가 실행된 모든 런 |
| `run_agent_use_case._map_chat_stream` | 내부 태그 필터 | 채팅 스트림 |
| `WorkflowCompiler` / `main.py` / `config.py` | 판정기·설정 주입 | 컴파일 |

---

## 7. Architecture Considerations
- Thin DDD: 포트·VO·힌트 추출 = domain, 루프 = application, LLM 판정 = infrastructure.
- 판정기 주입: `WorkflowCompiler(grounding_judge=...)` — 미주입이면 루프 비활성(테스트·하위호환).
- DB 스키마 변경 없음.

---

## 8. Open Questions (Design 확정)

| # | 질문 | 기본안 |
|---|------|--------|
| Q-1 | 재작성 상한 N | 초안 2 / 답변 1 (답변은 지연 민감) |
| Q-2 | 문장 제거 단위 | 문장(마침표·줄바꿈 기준) — 판정기가 원문 구간을 인용 |
| Q-3 | final_answer 재작성 시 스트림 처리 | 첫 답변은 흘리고 완료 이벤트로 최종본 교체 vs 판정 끝날 때까지 답변 토큰 보류 |
| Q-4 | 판정 대상 근거 크기 상한 | 코퍼스 상한(자) — 초과 시 최근·관련 블록 우선 |

---

## 9. Next Steps
1. [ ] `/pdca design draft-grounding-check` (v0.2 재작성)
2. [ ] TDD 구현 + L3

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-30 | 규칙 기반 결정적 대조 + 재작성, 초안만 | 배상규 |
| 0.2 | 2026-09-30 | 사용자 피드백("정해진 값이 질문에 따라 나와도 됨")으로 전환 — 기존 HallucinationEvaluator 를 근거 판정기로 확장, 규칙은 힌트로, 적용 범위에 final_answer 추가(재작성 루프 포함), 스트리밍 필터 | 배상규 |
