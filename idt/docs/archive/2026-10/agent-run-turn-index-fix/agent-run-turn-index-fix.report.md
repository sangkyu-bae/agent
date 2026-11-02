# agent-run-turn-index-fix Completion Report

> **Status**: Complete (코드 미커밋, 브랜치 `feature/agent-run-turn-index-fix`)
>
> **Project**: sangplusbot — idt (백엔드)
> **Version**: 기준 커밋 3578c1d + 워킹트리
> **Author**: 배상규 + Claude
> **Completion Date**: 2026-10-30
> **PDCA Cycle**: #1 (Plan → Design → Do → Check 97% → Act-1 → 98%)
> **원천**: `docs/proposals/2026-10-15.md` 후보 #1 · prompt-guard 사이클 이월

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | agent-run-turn-index-fix — 에이전트 실행 경로 turn_index 중복 결함 수정 |
| Start Date | 2026-10-30 |
| End Date | 2026-10-30 |
| Duration | 1일(단일 세션) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 98% (Match Rate, 런타임 포함) │
├─────────────────────────────────────────────┤
│  ✅ FR Met:        9 / 9                      │
│  실런: R1(신규 런 1/2)·R2(과거 행 폴백) 통과  │
│  Critical 0 · Important 0 · 이터레이션 1     │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 실행 런은 user 메시지를 별도 세션에서 commit하고 assistant 메시지는 요청 세션 스냅샷으로 turn을 계산해 두 행이 같은 turn_index로 저장됐다(2026-09-30 이후 재현). 👎 환류의 질문 복원이 에이전트 경로에서 실패했다. |
| **Solution** | `_persist_message` 공용 헬퍼로 user·assistant 저장을 통일(별도 세션, 최신 commit 기준 `len+1`). `EvalPolicy.find_question` 순수 함수가 `turn-1` USER 우선, 과거 중복 행은 같은 turn USER로 폴백. |
| **Function/UX Effect** | 실런: 신규 런이 `user 1 / assistant 2`로 저장되고, 과거 중복 세션(user 1 / assistant 1)에서도 질문이 복원된다. 사용자 화면·API·DB 변경 없음. |
| **Core Value** | growing-agent Phase 2 "피드백 수집"을 주 경로에서 여는 기반 결함 제거. 후속 #2 `agent-run-feedback-wiring`의 선행 조건 충족. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| FR-01 | 별도 세션, 최신 commit 기준 len+1, 즉시 commit | ✅ Met | `_persist_message` · T1/T3(begin 안에서 save) |
| FR-02 | user N → assistant N+1 | ✅ Met | T1/T2 · 실런 R1 `[(492,'user',1),(493,'assistant',2)]` |
| FR-03 | 호출 4곳·시그니처 무변경, persist=False 건너뜀 | ✅ Met | `:379/:575/:630/:1031` 동일 · T4 |
| FR-04 | session_factory 미주입 legacy 경로 | ✅ Met | T5 |
| FR-05 | turn-1 USER 우선 → 같은 turn 폴백 → None | ✅ Met | P1/P2/P5/P6 · E1 · 실런 R2 |
| FR-06 | 2건 이상이면 None | ✅ Met | P3/P4 |
| FR-07 | charts·analysis_data 보존 | ✅ Met | T6 |
| FR-08 | 저장 실패 전파 | ✅ Met | 헬퍼에 try/except 없음, `begin()` 롤백 |
| FR-09 | 일반 채팅·conversation·repo 무수정 | ✅ Met | 변경은 src 3파일뿐 |

**Success Rate**: 9/9 (100%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | assistant도 session_factory 경로 (user turn 힌트 전달 안 함) | ✅ | 시그니처 0 변경, 호출 4곳 무수정 |
| [Plan] | 과거 중복 행은 읽기 폴백(리넘버링 없음) | ✅ | 데이터 무변경, 실런 R2로 실증 |
| [Plan] | `_save_assistant_message` id 반환은 #2 | ✅ | None 반환 유지, 주석 명기 |
| [Design] | Option C: `_persist_message` + `EvalPolicy.find_question` | ✅ | turn 계산 1곳, 규칙은 repo 없이 테스트 |
| [Design] | legacy fallback 유지(테스트 전용) | ✅ | `__new__` 픽스처 무수정 또는 1줄 보정 |
| [Design] | §9.3 T7 픽스처 1줄 보정 허용 | ✅ | `approval/test_resume.py` `uc._session_factory = None` |
| [Check] | 사용자 결정 "Low 2건 보강" | ✅ | T8(승인 재개 + session_factory)·T3 정밀화 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [agent-run-turn-index-fix.plan.md](../01-plan/features/agent-run-turn-index-fix.plan.md) | ✅ |
| Design | [agent-run-turn-index-fix.design.md](../02-design/features/agent-run-turn-index-fix.design.md) | ✅ |
| Check | [agent-run-turn-index-fix.analysis.md](../03-analysis/agent-run-turn-index-fix.analysis.md) | ✅ v0.2 (97% → 98%) |
| Act | Current document | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

§1.4 참조. 9/9 Met.

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 세션 규칙 | repo 내 commit 금지 · `session.begin()` | 헬퍼가 `begin()` 안에서 save, T3/T8이 `saved_inside_begin == [True]` 검증 | ✅ |
| 락 | ai_run FK와 락 대기 없음 | 실런 R1 status 200, 행 2건 정상 | ✅ |
| 회귀 | 기존 스위트 통과 | 1493 passed + 보강 후 273 passed | ✅ |
| 데이터 | 과거 행 무변경 | 마이그레이션·스크립트 0 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Change |
|-------------|----------|--------|
| 저장 헬퍼 | `src/application/agent_builder/run_agent_use_case.py` | `_persist_message` 추가, 두 저장 메서드 빌더+위임으로 교체 |
| 질문 복원 규칙 | `src/domain/eval/policies.py` | `EvalPolicy.find_question` 추가 |
| eval 위임 | `src/application/eval/use_cases.py` | `_find_question` 위임, 미사용 import 제거 |
| 테스트 | `tests/domain/eval/test_eval_policy_find_question.py`(P1~P7) · `tests/application/agent_builder/test_run_agent_turn_index.py`(T1~T6, T8) · `tests/application/eval/test_use_cases.py`(E1) · `tests/application/approval/test_resume.py`(픽스처 1줄) | 신규 2파일 |
| 문서 | Plan · Design · Analysis v0.2 · 본 Report | — |
| 마이그레이션 / 프론트 / API | — | **0** |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority |
|------|--------|----------|
| 위키 `docs/wiki/backend/db/erd-conversation-eval.md` v2 각주("근본 수정 이월") 갱신 + CLAUDE.md "UseCase 내 서로 다른 세션 금지" 규칙의 승인된 예외(G4) 기록 | 위키 갱신은 `/wiki update` 호출 시 | Medium |
| 실런 R3(같은 세션 2턴째 3·4)·R4(승인 재개 실런) | 단위 T2·T8로 대체, LLM 비용·게이트 픽스처 부재 | Low |
| `conversation_message (session_id, turn_index, role)` 유니크 제약 | 스키마 변경 금지 원칙 — 후속 후보 | Low |
| 과거 중복 행 리넘버링 | 사용자 결정으로 범위 밖(읽기 폴백으로 호환) | — |
| 코드 커밋·PR | 사용자 지시 시 | — |

### 4.2 후속

| Item | Note |
|------|------|
| `agent-run-feedback-wiring`(#2) | `_save_assistant_message` id 반환 + ANSWER_COMPLETED payload. 이번 사이클이 선행 조건 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Check | Act-1 후 |
|--------|-------|---------|
| Structural | 100% | 100% |
| Functional | 97% | 99% |
| Contract | 100% | 100% |
| Runtime | 95% (R1·R2) | 95% |
| **Overall** | **97%** | **98%** |
| Critical / Important | 0 / 0 | 0 / 0 |

### 5.2 Resolved Issues

| Issue | Resolution |
|-------|------------|
| G1 승인 재개 + session_factory 테스트 부재 | T8 추가 — `resume_from_snapshot` 경로가 assistant turn=N+1, begin 안에서 save |
| G2 T3가 "begin 안에서 save"를 증명 못 함 | 가짜 세션 `in_begin` 플래그 + repo.save 기록 |
| G3 `_save_assistant_message` 40줄 경계 | 수용(실행부 ~20줄) |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **Red가 결함 경로를 그대로 보여줬다**: assistant 저장 테스트가 "MagicMock을 await할 수 없음"으로 실패한 것이 요청 세션 `_message_repo` 경로의 증거였다.
- **실런 R2가 폴백을 실데이터로 증명**: 과거 중복 세션을 실 저장소로 읽어 `find_question`이 USER를 돌려주는 것을 확인 — 단위 테스트의 MagicMock 픽스처만으로는 못 얻는 확신.
- **지난 사이클 교훈 적용**: Plan 단계에서 `__new__` 픽스처 보정 허용을 미리 적어 Do에서 픽스처 1줄 추가가 편차가 아닌 계약이 됐다.

### 6.2 What Needs Improvement (Problem)

- Plan §5 위험표의 "승인 재개 테스트 1건 추가" 약속이 Design §9 테스트 플랜에서 빠졌다. 위험표 완화책은 테스트 플랜 표에 1:1로 옮겨 적어야 한다.
- T3가 횟수만 세는 약한 검증이었다. "컨텍스트 안에서 실행됨"은 플래그 기록으로 직접 검증해야 한다.

### 6.3 What to Try Next (Try)

- Plan §5 위험표의 Mitigation에 "테스트 ID"를 적고 Design §9가 그 ID를 그대로 받게 한다.
- 가짜 세션/저장소 픽스처(`_Store`·`_FakeRepo`·`_session_factory`)는 재사용 가치가 있다 — #2에서 그대로 쓴다.

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement |
|-------|---------|-------------|
| Plan→Design | 위험 완화책이 테스트 플랜으로 자동 승계되지 않음 | 완화책마다 테스트 ID 부여 |
| Check | 실런 스크립트를 매번 새로 작성 | `TestClient` + `portal.call` + asyncmy 정리 패턴을 스크래치 템플릿으로 유지 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 커밋·PR(사용자 지시 시): src 3 + tests 4 + docs 4
- [ ] `/pdca archive agent-run-turn-index-fix`
- [ ] `/wiki update`(사용자 호출 시): erd-conversation-eval 각주, 세션 규칙 예외

### 8.2 Next PDCA Cycle

| Item | Priority |
|------|----------|
| `agent-run-feedback-wiring`(#2) | High — 이번 사이클이 선행 조건 |

---

## 9. Changelog

### v1.0.0 (2026-10-30)

**Added:**
- `RunAgentUseCase._persist_message` — user·assistant 공용 저장 헬퍼(별도 세션, 최신 commit 기준 turn)
- `EvalPolicy.find_question` — turn-1 USER 우선, 같은 turn USER 폴백, 모호 시 None
- 테스트 P1~P7, T1~T6, T8, E1

**Changed:**
- `_save_user_message`·`_save_assistant_message` → 빌더 + 헬퍼 위임(시그니처 불변)
- `SubmitFeedbackUseCase._find_question` → 규칙 위임
- `tests/application/approval/test_resume.py` 픽스처 `uc._session_factory = None`

**Fixed:**
- 에이전트 실행 경로 user/assistant 동일 turn_index 저장 결함

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-10-30 | Completion report | 배상규 + Claude |
