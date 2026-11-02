# agent-run-turn-index-fix Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) — Check 정적 98% / 런타임 포함 97% → Act-1(Low G1·G2 테스트 보강) 후 98%
>
> **Project**: sangplusbot — idt (백엔드)
> **Version**: 기준 커밋 3578c1d + 브랜치 `feature/agent-run-turn-index-fix` 워킹트리
> **Analyst**: 배상규 + Claude (gap-detector 정적 분석 + 인프로세스 실런)
> **Date**: 2026-10-30
> **Design Doc**: [agent-run-turn-index-fix.design.md](../02-design/features/agent-run-turn-index-fix.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 경로 user/assistant가 같은 turn_index로 저장되어 👎 Q/A 복원·turn 페어링이 성립하지 않는다 |
| **WHO** | P1·P4(에이전트 대화 사용자의 👎 환류) · P3(관리자 피드백 데이터) · 후속 #2 구현자 |
| **RISK** | 저장 세션 분리가 ai_run FK·승인 재개 스냅샷 경로와 상호작용해 새 락 대기나 누락을 만들 가능성 |
| **SUCCESS** | 신규 런에서 user turn=N, assistant turn=N+1 · 과거 중복 행에서도 `_find_question` 성공 · 일반 채팅 무수정 · 기존 테스트 통과 |
| **SCOPE** | 백엔드 2파일(run_agent_use_case 저장 메서드 1 · eval 질문 복원 1) + 테스트. 마이그레이션 0 · 데이터 리넘버링 0 · 프론트 0 · id 반환은 #2 |

---

## Strategic Alignment Check

| Element | Expected | Status |
|---------|----------|:------:|
| Core Problem (WHY) | 에이전트 경로 turn_index 유일성 | ✅ 실런 R1: `[('user',1),('assistant',2)]` |
| RISK (세션 분리 상호작용) | 락 대기·누락 없음 | ✅ R1 status 200, 행 2건 정상 commit. 승인 재개 경로는 운영 DI가 항상 session_factory를 주입하므로 같은 헬퍼를 탄다 |
| 과거 행 호환 | 👎 질문 복원 | ✅ 실런 R2: 과거 중복 세션에서 `find_question` → USER turn=1 |

### Success Criteria Status (Plan FR-01~FR-09)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| FR-01 | 별도 세션 최신 commit 기준 len+1, 즉시 commit | ✅ | `run_agent_use_case.py` `_persist_message` (`sf() → begin() → find → save`) · T1/T3 |
| FR-02 | user N → assistant N+1 | ✅ | 양쪽 저장이 같은 헬퍼 · T1/T2 · 실런 R1 |
| FR-03 | 호출 4곳·시그니처 무변경, persist=False 건너뜀 | ✅ | `:379/:575/:630/:1031` 인자 동일 · T4 |
| FR-04 | session_factory 미주입 legacy 경로 | ✅ | 헬퍼 후반 분기 · T5 |
| FR-05 | turn-1 USER 우선, 같은 turn 폴백, 없으면 None | ✅ | `policies.py` `find_question` · P1/P2/P5/P6 · E1 · 실런 R2 |
| FR-06 | 2건 이상이면 None | ✅ | P3/P4 |
| FR-07 | charts·analysis_data 보존 | ✅ | T6 |
| FR-08 | 저장 실패 전파 | ✅ | 헬퍼에 try/except 없음, `begin()` 롤백, 스트림 핸들러가 `exception=`으로 로그 |
| FR-09 | 일반 채팅·conversation·repo 무수정 | ✅ | git status: 변경은 src 3파일뿐 |

**Success Rate**: 9/9 Met

### Decision Record Verification

| Source | Decision | Followed? | Note |
|--------|----------|:---------:|------|
| [Plan] | assistant도 session_factory 경로 | ✅ | 공용 헬퍼로 양쪽 통일 |
| [Plan] | 과거 행은 읽기 폴백 | ✅ | 데이터 무변경, R2로 실증 |
| [Plan] | id 반환은 #2 | ✅ | assistant 반환 None 유지(주석 명기) |
| [Design] | Option C `_persist_message` + `EvalPolicy.find_question` | ✅ | D1~D7 전부 준수 |
| [Design] | §9.3 T7 픽스처 1줄 보정 허용 | ✅ | `approval/test_resume.py` `uc._session_factory = None` |

---

## 1. Analysis Overview

- **Design**: `docs/02-design/features/agent-run-turn-index-fix.design.md`
- **Implementation**: `src/application/agent_builder/run_agent_use_case.py`, `src/domain/eval/policies.py`, `src/application/eval/use_cases.py`
- **Tests**: `tests/domain/eval/test_eval_policy_find_question.py`(P1~P7), `tests/application/agent_builder/test_run_agent_turn_index.py`(T1~T6), `tests/application/eval/test_use_cases.py`(E1)

---

## 2. Gap Analysis

### 2.3 Component Structure

| Design Component | Implementation | Status |
|------------------|----------------|--------|
| `_persist_message` (D1) | `run_agent_use_case.py` | ✅ 본문 9줄 |
| `_save_user_message` 위임 (D2) | 빌더 + 헬퍼, id 반환 | ✅ |
| `_save_assistant_message` 위임 (D3) | 빌더 + 헬퍼, None 반환 | ✅ 40줄(docstring 포함, 실행부 ~20줄) |
| `EvalPolicy.find_question` (D6) | `policies.py` domain-only import | ✅ |
| `_find_question` 위임 (D7) | 조회 1회 + 위임, 불필요 import 제거 | ✅ |
| §6.4 변경하지 않는 것 | general_chat·conversation·repo·DDL | ✅ |

### 2.4 Functional Depth

| File | Depth | Note |
|------|:-----:|------|
| run_agent_use_case.py (변경분) | 100 | placeholder 없음 |
| policies.py (변경분) | 100 | — |
| eval/use_cases.py (변경분) | 100 | — |

### 2.6 Contract Verification (내부 계약)

| # | Contract | Status |
|---|----------|:------:|
| 1 | 두 저장 메서드 시그니처·반환 불변 | ✅ |
| 2 | 호출 4곳 무수정 | ✅ |
| 3 | `find_question(messages, assistant)` 계약 · `_find_question` 조회 1회 | ✅ |
| 4 | API·DDL 무변경 | ✅ |

**Contract Match Rate**: 100%

### 2.7 Runtime Verification (인프로세스 `TestClient(app)`, 실 MySQL·OpenAI)

| # | 시나리오 | 결과 | 증거 |
|---|----------|:----:|------|
| R1 | REST run `persist_conversation=true`, 일회용 `session_id=turnfix-b5da5483` | ✅ | status 200 · `conversation_message` `[(492,'user',1),(493,'assistant',2)]` · 정리: `ai_run.user_message_id` NULL 후 2행 삭제, 잔여 0 |
| R2 | 과거 중복 turn 세션(`66c2d54c…`, user 1 / assistant 1)을 실 repo로 조회 → `EvalPolicy.find_question` | ✅ | `question=FOUND role=user turn=1` — 폴백 실증 |
| R3 | 같은 세션 2턴째 → (3, 4) | ⏭ 미실행 | T2가 공유 저장소로 동형 검증. LLM 호출 비용 절약 |
| R4 | 승인 재개 경로 실런 | ⏭ 미실행 | 운영 DI가 session_factory를 항상 주입 → 같은 헬퍼. 게이트 걸린 런 픽스처 필요(메일 MCP 미등록) |

부수 관찰: 대상 에이전트(`2110b539…`)의 action 워커 설정 오류 로그(`draft_arg_key` 비어 있음)가 스트림 중 찍혔으나 런은 200으로 완료됐다. 이번 변경과 무관한 기존 에이전트 설정 문제.

**Runtime Match Rate**: 실행 2/2 통과, 2건 단위 테스트로 대체 → 95%

### 2.8 Match Rate Summary

```
Check (Act 전):
  Structural 100% · Functional 97% (Low G1·G2) · Contract 100% · Runtime 95%
  정적 98% · 런타임 포함 97%

Act-1 후 (G1·G2 해소, G3 수용):
  Structural Match Rate:  100%
  Functional Match Rate:   99%  (G3 40줄 경계 수용)
  Contract Match Rate:    100%
  Runtime Match Rate:      95%  (R1·R2 통과, R3·R4 단위 대체 — T2·T8)
  Overall = 100×0.15 + 99×0.25 + 100×0.25 + 95×0.35 = 98%
```

---

## 3. Gap List

| # | Severity | Confidence | Gap | Action |
|---|----------|:---------:|-----|--------|
| G1 | Low | 85% | Plan §5 위험표가 약속한 "승인 재개 + session_factory 주입 테스트 1건"이 없다. Design §9는 T7(legacy 회귀)로만 커버. 코드 경로는 같은 헬퍼 | ✅ **Act-1 해소**: T8 `TestResumePath` — `resume_from_snapshot` + 가짜 session_factory(seed user 1) → assistant turn 2, begin 안에서 save |
| G2 | Low | 90% | T3는 `begin()` 진입·`save()` 횟수만 세고 "save가 begin 안에서" 실행됐는지는 증명하지 않음 | ✅ **Act-1 해소**: 가짜 세션이 `in_begin` 플래그를 유지하고 repo.save가 `saved_inside_begin`에 기록 → T3·T8이 `[True]` 검증 |
| G3 | Low | 80% | `_save_assistant_message` 40줄(docstring 포함) — Design §11 목표 ≤30 초과, CLAUDE.md 40줄 경계 | 수용 가능. docstring 축약 선택 |
| G4 | Info | 90% | CLAUDE.md §6 "한 UseCase 안에서 repository별 서로 다른 세션 사용 금지"와의 관계 — AGENT-OBS-001(user 저장)이 이미 쓰는 예외 패턴을 assistant로 확장한 것. Design Option C로 승인됨 | Design/위키에 명시적 예외로 기록(`/wiki update` 시) |

Critical 0 · Important 0 · Added(설계 밖 구현) 0.

---

## 4. Test Results

| Suite | Result |
|-------|--------|
| 신규 P1~P7 · T1~T6 · E1 + eval 기존 | 44 passed (구현 전 Red 확인 — assistant 경로가 요청 세션 repo를 await하다 실패한 것이 결함 경로 증거) |
| 회귀 agent_builder · approval · general_chat · conversation · domain/conversation · domain/prompt_guard · api/test_eval_router | 1493 passed |
| `import src.api.main` | OK |
| 실런 R1·R2 | 2/2 통과 |
| Act-1: 신규 T8 + T3 정밀화 + 관련 스위트(approval·eval·domain/eval·stream·identity·memory wiring) | 273 passed |

---

## 5. Recommendation

Check 97% → Act-1(사용자 결정 "Low 2건 보강")로 G1·G2 해소, **98%**. Critical·Important 0, 잔여는 G3(40줄 경계 수용)·G4(규칙 예외 기록, `/wiki update` 시). `/pdca report`로 진행한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-30 | 정적 98% + 실런 R1·R2 → 97%, Low 3 + Info 1 | 배상규 + Claude |
| 0.2 | 2026-10-30 | Act-1: T8(승인 재개 + session_factory) 추가, T3 begin-내부 검증 → 98% | 배상규 + Claude |
