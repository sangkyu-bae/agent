# subagent-step-observability Gap Analysis

> **Feature**: subagent-step-observability
> **Date**: 2026-10-07
> **Author**: 배상규
> **Analyzer**: gap-detector (정적) + 메인 세션 L3 실런·회귀 검증
> **Plan**: [subagent-step-observability.plan.md](../01-plan/features/subagent-step-observability.plan.md)
> **Design**: [subagent-step-observability.design.md](../02-design/features/subagent-step-observability.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 서브에이전트 런의 실행 이력에서 부모·자식 step이 구분되지 않아 멀티 에이전트 디버깅이 불가능하고, 모든 step latency가 반올림 버그로 부정확(음수 포함)하다. |
| **WHO** | P2 — 멀티 에이전트를 조합·운영하며 실행 상세로 검수하는 KB 운영자·에이전트 소유자. |
| **RISK** | `_current_step_id` 복원 실패 시 무관한 step이 자식으로 묶임 → 실런 전수 검증으로 해소. |
| **SUCCESS** | 자식 step 100% 올바른 wrapper 아래 / 최상위 parent 없음 / tool·llm 귀속 / latency ≥ 0 / StepTree 트리 / 회귀 0. |
| **SCOPE** | M1 DB·모델 → M2 기록 → M3 API·프론트 → M4 L3. 스트리밍은 실측만. |

---

## 1. Match Rate

| Axis | Score | 근거 |
|------|:-----:|------|
| Structural | 98 | Design §3·§4·§5.2·§9·§11.1 전 항목 존재. §6 순환 승격 부분 구현(G-2) |
| Functional | 95 | best-effort·예외 경로 복원·latency OK. 순환 노드 유실(G-2), track_step 길이(기존) |
| Contract | 100 | API 필드 추가만, BE↔FE StepDto 일치, `/admin/usage/by-node` 무변경(D-09) |
| Runtime | 90 | L3 SC-1~4 통과(run `8863101d`), SC-5 화면 확인 대기 |
| **Overall (static)** | **97.6%** | 0.2·S + 0.4·F + 0.4·C |
| **Overall (runtime 포함)** | **95.0%** | 0.15·S + 0.25·F + 0.25·C + 0.35·R |

---

## 2. Success Criteria

| SC | 상태 | 근거 |
|----|:----:|------|
| SC-1 자식 step 전부 올바른 wrapper 아래 | ✅ | run `8863101d`: 분석가 내부 7 step → #2, 작성자 내부 2 step → #12, 모두 depth 1 |
| SC-2 최상위 parent NULL·depth 0 | ✅ | #1·#2·#10·#11·#12 |
| SC-3 자식 tool·llm call 귀속 | ✅ | tool 2건·llm call 전부 depth 1 자식 step |
| SC-4 latency ≥ 0 | ✅ | 14 step 전부 ≥ 0 (quality_gate 0ms·16ms), 단위 B8 |
| SC-5 StepTree 트리 렌더·접기 | ⚠️ | 컴포넌트 F4~F6 통과, 실제 화면 확인 대기 |
| SC-6 과거 런 평면 하위호환 | ✅ | 매퍼 None→0(B12), F6, buildStepTree F1 |
| SC-7 회귀 0 | ✅ | BE 신규 실패 0(blueprint 6건은 HEAD에서도 재현 — worktree에 미추적 샘플 PDF 부재), FE 9/4파일 기준선 동일, tsc 210 동일 |

**6/7 Met, 1 Partial (사용자 화면 확인)**

---

## 3. Decision Record

D-01~D-09 모두 준수. 이탈: Design §6 "순환 노드 최상위 승격" 불완전(G-2).

---

## 4. Gap List (Critical 0 / Important 1 / Minor 4)

| ID | 심각도 | 신뢰도 | 내용 | 근거 |
|----|:------:|:------:|------|------|
| G-1 | Important (문서) | 90% | Plan Q-D3(승인 재개 런 계층 기록) 결과가 Design에 없음 — Version History는 "Q-D1~D4 실측 확정"이라 기재. 실제로는 Design 단계에서 `resume_from_snapshot`이 같은 `compile(tracker=…)`→`_wrap_step` 경로임을 확인했으나 문서에 누락 | design.md 내 "재개/resume/Q-D3" 0건, `run_agent_use_case.py:804` |
| G-2 | Minor | 95% | `buildStepTree`가 자기참조만 승격 — 2개 이상 순환(A→B→A)이면 두 노드가 루트에서 닿지 않아 화면에서 사라짐 (이론상 불가 데이터, 무한루프는 없음) | `buildStepTree.ts:17-23`, design §6 |
| G-3 | Minor | 95% | H4 중 "ctx 있음 + ctx.step_id ≠ parent" 분기 테스트 없음 (B7은 ctx 없음만) | `step_tracking.py:223-226` |
| G-4 | Minor | 90% | StepTree에서 tool/llm call·orphan 블록 유지를 확인하는 테스트 없음 (픽스처가 빈 배열) | `StepTree.test.tsx` |
| G-5 | Minor (기존) | 90% | `track_step` 64줄(시그니처·docstring 포함) — master 65줄에서 소폭 감소, 신규 위반 아님 | `step_tracking.py:234-297` |

### 4.1 조치 결과 (Checkpoint 5: "G-1~G-4 수정")

| ID | 조치 |
|----|------|
| G-1 | Design §12 D-10에 Q-D3 실측(재개 경로 = 같은 compile·track_step 경로) 기록 |
| G-2 | `buildStepTree`에 `closesCycle`(방문 집합) 추가 — 순환·자기참조 모두 최상위 승격. 테스트 Red→Green |
| G-3 | `test_G3_컨텍스트가_다른_step을_가리키면_깊이_1로_폴백` 추가 (기존 동작 고정, 통과) |
| G-4 | `G-4: 자식 step 의 tool·LLM 호출과 orphan LLM 블록이 유지된다` 추가 (통과) |
| G-5 | 수용 — 기존 길이(65줄)에서 소폭 감소, 신규 위반 아님 |

조치 후: Structural 100 · Functional 98 · Contract 100 → **static 99.2%**, Runtime 90(SC-5 화면 확인 대기) 포함 **96.0%**. 화면 확인 후 Runtime 100이면 **99.5%**.

---

## 5. 범위 밖 관측

- **스트리밍(WS) 자식 노드 섞임** (FR-09 실측): 자식 `supervisor`·`quality_gate`가 부모와 같은 이름의 node 이벤트로 흐름, 계층 표식 없음 — 다음 사이클 후보.
- **SSE `/run/stream` 항상 401**: 인증 placeholder 미배선 (상시 실패 9건 원인), 프론트는 WS 사용.
- **`/admin/usage/by-node`**: node_name 집계라 자식 supervisor가 부모 버킷에 합산 (D-09 현행 유지).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-10-07 | Gap 분석 — 97.6%(static) / 95.0%(runtime), Important 1 · Minor 4 | 배상규 |
