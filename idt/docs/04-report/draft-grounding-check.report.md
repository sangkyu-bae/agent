# draft-grounding-check Completion Report

> **Status**: Complete (L3 재확인 1건 이월)
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Completion Date**: 2026-10-01
> **PDCA Cycle**: Plan v0.2 → Design v0.3 → Do (module-1~4) → Check 89.8% → Act-1 92.5%

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | draft-grounding-check — 외부 발송 초안·채팅 최종 답변의 근거 판정 + 재작성 루프 |
| Start Date | 2026-09-30 |
| End Date | 2026-10-01 |
| Duration | 2일 (Plan v0.1 → 사용자 피드백으로 v0.2 전환 포함) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 92.5%  (Check 89.8% → Act-1)    │
├─────────────────────────────────────────────┤
│  ✅ SC Met:      5 / 6                       │
│  ⚠️ SC Partial:  1 / 6 (SC-3 과검출)         │
│  ❌ SC Not Met:  0                           │
│  FR: 12 / 12 구현                            │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 문의 63116 초안·채팅 답변이 근거 어디에도 없는 "대표번호: 1877-9900" 을 반복 생성. 기존 HallucinationEvaluator 는 참/거짓만 돌려줘 무엇을 고칠지 몰랐고 에이전트 빌더 경로에 미연결. 고정 규칙은 "질문에 따라 나와도 되는 값" 을 판단 못 함. |
| **Solution** | 기존 판정기를 **주장 단위 근거 판정기**(원문 구간·이유·high/low)로 확장하고, 초안·답변이 같은 **재작성 루프**(판정 → 사유 넣어 재작성 ≤2/1 → 초과 시 문장 제거)를 통과. 규칙은 판정기 힌트로만. 판정 전용 모델 gpt-4o 분리, 원문 그대로 근거에 있는 지적은 결정적 제외. |
| **Function/UX Effect** | L3: 초안 5건 근거 없는 연락처 **0**(이전 3/3 포함), 채팅 요약 2/2 근거 값(제목·이름·금액·상품명) 유지, 판정 JSON·중간 재작성 토큰 채팅 노출 **0**. 근거 없는 값 대신 "고객센터로 문의" 식 무값 안내로 대체. |
| **Core Value** | 특정 값·도구 하드코딩 없이 맥락으로 판단하는 일반 장치(P2 KB 운영자 시나리오의 "일반화가 이긴다" 원칙). 판정 실패해도 답변을 막지 않는 fail-open + 승인 게이트가 최종 방어선. 기존 레이어 위반(use case → infrastructure) 동시 해소. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | L3 "63116 답변 등록해줘" 초안 근거 없는 연락처 0 | ✅ Met | gpt-4o 판정기 런 초안 5건 phones=[]. 실패 1건은 인자 조립(선택 인자 approver) — 범위 밖 |
| SC-2 | L3 채팅 답변 근거 없는 연락처 0 | ✅ Met | WS 2/2 answer_phones=[] |
| SC-3 | 근거에 있는 값 유지(과검출 0) | ⚠️ Partial | 채팅 요약 근거 값 유지, D-13 원문 그대로 제외(양성 대조군 0/3 오제외). 단 gpt-4o 도 값 없는 채널 안내("영업점 방문")를 high 로 잡아 초안이 보수적. 위키 대표번호 시나리오 미수행 |
| SC-4 | 판정기 예외 시 원문 유지, 런 성공 | ✅ Met (unit) | test_grounded_generation G5, 로그 타입·스택만 |
| SC-5 | 판정 JSON·재작성 토큰 채팅 노출 0 | ✅ Met | `_map_chat_stream` 태그 필터 + 테스트, L3 WS JSON 0 |
| SC-6 | 리서치·엑셀 회귀 0, 상시 목록 외 실패 0 | ✅ Met | 전체 53 failed(상시 목록 동일) / 10218 passed |

**Success Rate**: 5/6 (83%) Met, 1 Partial

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| Plan v0.1→v0.2 | 규칙 기반 차단 → LLM 근거 판정 + 규칙 힌트 (사용자: "정해진 값이 어떤 질문에서는 나와도 된다") | ✅ | 맥락 판단 가능. 대신 판정기 품질이 결과를 좌우 — D-11 로 이어짐 |
| Design D-02/D-03 | 초안+답변 모두, 재작성 2/1 | ✅ | 초안은 재작성만으로 수렴한 사례 발생(5번째 판정 주장 0) |
| Design D-04 | 루프 토큰 보류, 완료 이벤트로 최종본 | ✅ | 채팅 JSON 누출 0. 대신 final_answer 실시간 타이핑 효과 사라짐 |
| Design D-06 | fail-open | ✅ | 크레딧 소진(429) 상황에서도 판정 단계가 런을 막지 않음 |
| Design C (Option) | 공통 루프 + 포트 | ✅ | 초안·답변 중복 구현 0, 그래프 변경 0 |
| Do D-11 | 판정 전용 모델 gpt-4o (사용자 선택) | ✅ | 벤치: 4o-mini 정상 7/7 오판, 4.1-mini 대표번호 누락, 4o 날조 3/3·오판 최소. 비용 판정당 약 15배 |
| Do D-12 | 프롬프트 태그 경계·품질 비판정 | ✅ | `[현재 날짜]` 헤더로 근거 섹션이 무너지던 문제 해소 |
| Do D-13 | 원문 그대로 지적 결정적 제외 | ✅ | 원문 인용형 오판 제거, 과삭제 위험 0 |
| Do D-14 | 글 단위 문장 경계·공백 흡수 | ✅ | "가능 여부는" 조각·지시어 잔존 해소 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [draft-grounding-check.plan.md](../01-plan/features/draft-grounding-check.plan.md) | ✅ v0.2 |
| Design | [draft-grounding-check.design.md](../02-design/features/draft-grounding-check.design.md) | ✅ v0.3 |
| Check | [draft-grounding-check.analysis.md](../03-analysis/draft-grounding-check.analysis.md) | ✅ v0.2 (Act-1) |
| Report | Current document | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|:------:|-------|
| FR-01 | 주장 목록(원문 구간·이유·심각도) 판정 | ✅ | `GroundingJudgePort`, adapter `judge()` |
| FR-02 | 일반 안내는 주장 아님 | ✅ | 프롬프트 예시 + 품질 비판정 (D-12) |
| FR-03 | 규칙 힌트 | ✅ | `GroundingHintPolicy` (전화·URL·이메일·계좌·금리) |
| FR-04 | high 재작성 ≤N | ✅ | `GroundedGenerator`, `GroundingEditPolicy.feedback` |
| FR-05 | 상한 초과 문장 제거·빈 결과 처리 | ✅ | 초안 빈 → 작성 실패, 답변 빈 → 원문 유지 |
| FR-06 | fail-open | ✅ | 로그 1곳, 타입·스택만 |
| FR-07 | action 초안 적용 | ✅ | `_compose_grounded` |
| FR-08 | final_answer 적용(워커 산출 없으면 skip) | ✅ | `_generate_final_answer`, 차트 단독 skip |
| FR-09 | 루프 토큰 비노출 | ✅ | `INTERNAL_LLM_TAG` 필터 |
| FR-10 | 기존 evaluate 불변 | ✅ | 리서치·엑셀 테스트 회귀 0 |
| FR-11 | 전역 토글·상한 | ✅ | 설정 5종 |
| FR-12 | 수치만 로그 | ✅ | 주장 원문 미기록 테스트(G9, G-2) |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|:------:|
| 비용 | 근거 없는 런·off 시 추가 호출 0 | skip 3사유(disabled/no_judge/no_sources) 판정 0회 | ✅ |
| 지연 | 상한으로 제한 | 초안 최대 판정 3·생성 3, 답변 판정 2·생성 2 (판정 1회 ≈ 3~6초 실측) | ✅ |
| 안전 | 판정 실패가 막지 않음 | fail-open, 승인 게이트 유지 | ✅ |
| 아키텍처 | 포트 domain / 루프 application / 판정 infrastructure | domain 은 외부 import 0, use case 포트 경유 | ✅ |

### 3.3 Deliverables

| Deliverable | Location |
|-------------|----------|
| Domain | `src/domain/hallucination/{grounding,grounding_hints,grounding_edit}.py` |
| Application | `src/application/hallucination/grounded_generation.py`, `use_case.py`(포트) |
| Infrastructure | `src/infrastructure/hallucination/{adapter,prompts,schemas}.py` |
| Wiring | `action_pipeline.py`, `workflow_compiler.py`, `run_agent_use_case.py`, `config.py`, `main.py` |
| Tests | domain 31 / loop 25 / adapter·prompt 10 / wiring 13 / stream 1 (신규·추가) |
| Docs | plan v0.2, design v0.3, analysis v0.2, 본 리포트 |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority |
|------|--------|----------|
| L3 재확인 (D-13·D-14 실런, SC-3 위키 대표번호, SC-4 판정기 장애 주입) | OpenAI 크레딧 소진(429 insufficient_quota) | High |
| 판정 과보수성 — 값 없는 채널 안내("영업점 방문", "고객센터 전화")를 high 로 잡음 | 판정 기준 튜닝 또는 위키에 채널 안내를 근거로 등록 | Medium |
| 인자 조립 LLM 이 선택 인자(approver)를 필수로 보고 `grounded=false` | approval-gate-run-termination 이월 G1 계열 | Medium |
| SSE `/run/stream` 쿼리 토큰 인증 미배선 (항상 401) | 기존 결함, 상시 실패 테스트 | Low |
| G-6·G-7 기존 규칙 위반(함수 길이, 스택 없는 compose 실패 로그), G-8 레거시 폴백 모델, G-9 | 범위 밖·저빈도 | Low |
| 63116 중복 승인 대기 정리 (L3 로 약 7건 누적) | 운영 데이터 | Low |

### 4.2 Cancelled/On Hold Items

| Item | Reason |
|------|--------|
| 승인 화면 경고 배지 | Plan Out of Scope |
| 에이전트별 토글 UI | 전역 설정으로 시작 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Check | Act-1 |
|--------|:-----:|:-----:|
| Structural | 97 | 98 |
| Functional | 92 | 96 |
| Contract | 90 | 96 |
| Runtime | 85 | 85 |
| **Match Rate** | 89.8 | **92.5** |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|:------:|
| L3: 재작성 3/3 미수렴 → 문장 제거로 초안 파손 | D-11 판정 모델, D-12 프롬프트 | ✅ |
| 판정기가 근거 섹션을 비어있다고 읽음 | `<sources>` 태그 경계 | ✅ |
| 줄 단위 제거가 문장 조각 남김 / 공백 인용 불일치 | D-14 | ✅ |
| gpt-4o 원문 인용형 오판 | D-13 | ✅ |
| G-4 코퍼스 오래된 순 / G-3 차트 단독 활성 | 최신 우선, 워커 산출 기준 | ✅ |
| G-2·G-12 실패 로그 원출력 노출 가능·이중 로깅 | 루프 1곳, 타입·스택만 | ✅ |
| G-1 skip 사유 / G-5 메타 유실 / G-11 문서 표류 | reason 필드, model_copy, 설계 v0.3 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)
- **실런으로 판정기 입출력을 기록**(스크립트 몽키패치, 코드 무변경) → 과검출 원인을 추측이 아닌 근거로 분리(모델 품질 vs 프롬프트 구조 vs 제거 알고리즘).
- **모델 벤치에 양성 대조군**(날조 3건)을 넣어 "관대함"과 "정확함"을 구분 — gpt-4.1-mini 의 0 오판이 사실은 미검출임을 잡아냄.
- 공통 루프(Option C)로 초안·답변을 한 번에 다뤄 Do 중 보정이 양쪽에 동시 반영.

### 6.2 What Needs Improvement (Problem)
- 설계 단계에서 **판정 모델 품질을 가정**(유틸리티 모델로 충분) — L3 에서야 드러남. 판정기 같은 품질 민감 컴포넌트는 Design 에서 소규모 벤치를 먼저.
- 근거 코퍼스에 대괄호 헤더가 섞이는 구조를 프롬프트 템플릿이 고려하지 못함.
- 외부 API 크레딧이 L3 도중 소진 — 실런 예산을 사전 확인하지 않음.

### 6.3 What to Try Next (Try)
- 판정기 회귀용 **골든셋**(정상 7 + 날조 3) 을 오프라인 테스트로 고정 — 모델·프롬프트 변경 시 재생.
- 판정 비용·지연 메트릭(판정 횟수/런) 수집.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Design | LLM 컴포넌트 모델 선택을 가정 | LLM 판정류는 Design 에 미니 벤치 단계 추가 |
| Do | L3 는 module 마지막 | 판정기 단독 L3(입출력 기록)를 연결 전 먼저 |
| Check | gap-detector 턴 한도 도달 | 정적 분석 범위를 파일 목록으로 좁혀 전달 |

### 7.2 Tools/Environment

| Area | Improvement Suggestion |
|------|------------------------|
| 실런 | OpenAI 크레딧 잔량 사전 점검 스크립트 |
| 관측 | `grounding judged` 로그(high/literal_dropped) 대시보드화 |

---

## 8. Next Steps

### 8.1 Immediate
- [ ] OpenAI 크레딧 충전 후 L3 재실행 (초안 ×3, 채팅 ×2, 위키 대표번호 시나리오)
- [ ] 63116 중복 승인 대기 정리
- [ ] 커밋·PR 범위 결정 (현재 approval-gate-run-termination 과 함께 `feature/approval-edit-before-approve` 에 미커밋)

### 8.2 Next PDCA Cycle

| Item | Priority |
|------|----------|
| 판정 골든셋 회귀 테스트 + 채널 안내 과보수성 튜닝 | Medium |
| 인자 조립 선택 인자 오판(approver) | Medium |

---

## 9. Changelog

### v1.0.0 (2026-10-01)

**Added:**
- 주장 단위 근거 판정(`GroundingJudgePort`, `GroundingVerdict`, `UnsupportedClaim`) + 규칙 힌트 + 재작성 사유·문장 제거 정책
- 공통 근거 재작성 루프 `GroundedGenerator` (fail-open, skip 사유, 원문 그대로 지적 제외)
- action 초안·final_answer 연결, 채팅 스트림 내부 태그 필터
- 설정: `grounding_check_enabled`, `draft/answer_grounding_max_retries`, `grounding_corpus_max_chars`, `grounding_judge_model`

**Changed:**
- `HallucinationEvaluatorUseCase` 가 domain 포트에 의존 (레이어 위반 해소, 동작 불변)
- 판정 전용 LLM 공급자 (gpt-4o, 유틸리티 모델과 분리)

**Fixed:**
- 초안·채팅 답변의 근거 없는 연락처 생성 (실측 1877-9900)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-10-01 | Completion report created | 배상규 |
