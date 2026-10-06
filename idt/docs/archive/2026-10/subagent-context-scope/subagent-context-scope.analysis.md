# subagent-context-scope Gap Analysis

> **Feature**: subagent-context-scope
> **Date**: 2026-10-04
> **Author**: 배상규
> **Analyzer**: gap-detector (정적) + 메인 세션 L3 실런·회귀 검증
> **Plan**: [subagent-context-scope.plan.md](../01-plan/features/subagent-context-scope.plan.md) (v0.3)
> **Design**: [subagent-context-scope.design.md](../02-design/features/subagent-context-scope.design.md) (v0.3)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 서브에이전트가 supervisor 지시를 받지 못해, 두 번째 이후 라우팅과 QG 재시도에서 과제를 모른 채 실행된다. 런타임 위임이 사실상 첫 라우팅에서만 올바르게 동작한다. |
| **WHO** | P2 — 서브에이전트를 조합해 에이전트를 만드는 KB 운영자·에이전트 소유자. |
| **RISK** | 참고자료를 자식 supervisor가 자기 워커 결과로 오인해 조기 FINISH / 토큰 증가. |
| **SUCCESS** | worker_task 3경로 포함 / QG 재시도 원 지시+피드백 / 상한 준수 / 전략 교체 가능 / 회귀 0. |
| **SCOPE** | domain Policy → 전략 → `_wrap_sub_agent` 연결 → QG 재시도 → 실행 이력 요약 → DI. (+ Do 중 추가 FR-10·11·12) |

---

## 1. Match Rate

| Axis | Score | 근거 |
|------|:-----:|------|
| Structural | 100 | Design §3·§9.4의 파일·클래스·함수 전부 존재, 시그니처 일치 (FR-10/11/12 포함) |
| Functional | 97 | R1~R8·FR-01~12 전부 구현. 감점은 Minor G1(로그 필드)·G2(로그 본문 미검증 테스트) |
| Contract | 100 | 서브에이전트 산출 계약 불변(AIMessage(name) 1건·토큰 합산·approval_pending 전파) + `STEP_OUTPUT_SUMMARY_KEY` 추가. domain → 외부 레이어 import 0 |
| Runtime (L3) | 100 | L3-1·2·3 통과 (Design §8.5.1) |
| **Overall (static)** | **98.8%** | 0.2·S + 0.4·F + 0.4·C |
| **Overall (runtime 포함)** | **99.25%** | 0.15·S + 0.25·F + 0.25·C + 0.35·R |

---

## 2. Strategic Alignment

- **핵심 문제 해결 여부 (WHY)**: ✅ — 서브에이전트 입력에 `[현재 작업]`(worker_task)이 항상 포함되고, 실런에서 부모 지침의 호출 방식(대상·기간)이 자식에 도달함을 확인 (run `41cc2367`).
- **Plan 범위 밖에서 드러난 더 큰 문제**: 서브에이전트 런타임이 운영에서 **한 번도 동작한 적이 없었다** — 3중 차단(FR-11 DI 누락 → FR-10 노드 래핑 회귀 → FR-12 name 패턴). 세 건 모두 사용자 승인 하에 범위 포함·수정. 이 기능의 실질 가치는 "문맥 확장"보다 "서브에이전트 런타임 복구"가 더 크다.
- **실효 제약**: `SupervisorConfig.quality_gate_enabled`는 운영 경로에서 항상 False — FR-05(QG 재시도 입력)는 QG가 켜졌을 때에만 효과가 있다.

---

## 3. Success Criteria

| SC | 내용 | 상태 | 근거 |
|----|------|:----:|------|
| SC-1 | worker_task 3경로 포함 | ✅ | S1·S2·S3, C1, L3-1(`41cc2367`) |
| SC-2 | QG 재시도 시 원 지시 + 피드백 | ✅ | P1·P9·S3, L3-3(`d6b5affc`, QG 강제 활성) |
| SC-3 | 참고자료 상한·절단 | ✅ | P5~P7, `sub_agent_context_policy.py` `_pick_within_budget` |
| SC-4 | 이전 턴·재주입·QG 피드백 제외 | ✅ | P1~P3 |
| SC-5 | 전략 교체가 컴파일러 수정 없이 가능 | ✅ | C2·C3 (생성자 주입 → `resolve_strategy` → 래퍼) |
| SC-6 | 산출 계약·승인 전파 회귀 0 | ✅ | C4, `test_gated_run_termination` 무수정 통과 |
| SC-7 | L3 실런 지시 수행·재수집 0 | ✅ | 자식 도구 호출 0건, 자식 supervisor "추가 검색 없이 3줄 요약" |

**Overall: 7/7 Met**

회귀: 전체 백엔드 53 failed / 10289 passed — HEAD 기준선과 실패 목록 동일(신규 0).

---

## 4. Decision Record Verification

D-01 ~ D-13 전부 준수, 이탈 없음. Do 중 추가된 D-10(function_node_ids), D-11(legacy_input), D-12(SessionScoped 저장소 DI), D-13(sanitize_llm_name)은 Design v0.2/0.3에 반영됨.

---

## 5. Gap List (Critical 0 / Important 0 / Minor 5)

| ID | 심각도 | 신뢰도 | 내용 | 근거 |
|----|:------:|:------:|------|------|
| G1 | Minor | 95% | 성공 info 로그가 Design §6의 개별 필드(has_origin, reference_count, reference_chars, truncated, retry, fallback) 대신 `blocks=…, summary=<문자열>`로 기록. 본문 값은 없음 | `workflow_compiler.py:2602-2605` |
| G2 | Minor | 90% | "sub_agent input built" 로그에 본문이 실리지 않음을 검증하는 테스트 없음 | `test_workflow_compiler_sub_agent.py` C4는 summary만 검증 |
| G3 | Minor | 70% | `_wrap_sub_agent`가 `self._logger`에 의존 — `__new__` 인스턴스는 `_logger`를 수동 설정해야 함. 현 `__new__` 테스트 3곳 모두 설정하므로 실패 없음 | `workflow_compiler.py:2597, 2602` |
| G4 | Minor | 60% | `_wrap_sub_agent` 64줄(중첩 클로저 포함). 기존 구조 그대로이며 이번 변경 증가분은 약 1줄 | `workflow_compiler.py:2608-2671` |
| G5 | Minor (문서) | 90% | Plan FR-07의 "입력 블록 수" 문구와 Design R8 형식 불일치 — 코드는 Design을 따름 | `plan.md:75` vs `design.md` §3.3 R8 |

---

### 5.1 조치 결과 (Checkpoint 5: "G1·G2·G5만 수정")

| ID | 조치 |
|----|------|
| G1 | Design §6 로깅 명세를 실제 형식(`blocks` + R8 `summary` 문자열)으로 갱신 — 정보가 요약 문자열에 이미 들어 있어 출처 단일화 |
| G2 | `test_C4b_입력_로그에는_본문이_없다` 추가 (기존 동작 고정용 가드, 통과) |
| G3 | 유지 — `__new__` 테스트 3곳 모두 `_logger` 설정 |
| G4 | 유지 — 기존 클로저 구조, 이번 증가분 약 1줄 |
| G5 | Plan FR-07 문구를 Design R8 형식에 맞춰 갱신 |

조치 후 Functional 97 → 100 (G1·G2 해소). Overall(static) **100%**, (runtime 포함) **100%**. 남은 Minor: G3·G4 (수용).

## 6. 범위 밖 관측 (후속 후보)

- 자식 그래프 step이 같은 run에 `supervisor`/`quality_gate` 이름으로 기록돼 부모·자식 구분 불가, 일부 latency 음수.
- `SubAgentAccessPolicy`(dead code)·`subscription_repo` 잔여 (agent-subagent-management D-1/D-2).
- 실행 시점 서브에이전트 권한 재확인 미구현 (Plan Out of Scope).
- `quality_gate_enabled` 운영 활성화 여부는 별도 결정 필요.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-10-04 | Gap 분석 — Match 98.8%(static) / 99.25%(runtime), Minor 5 | 배상규 |
