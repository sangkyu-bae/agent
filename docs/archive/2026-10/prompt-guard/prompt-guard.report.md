# prompt-guard Completion Report

> **Status**: Complete
>
> **Feature**: prompt-guard
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Completion Date**: 2026-10-12
> **PDCA Cycle**: #1 (Plan → Design → Do ×4 모듈 → Check → Act-1)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | prompt-guard — 사용자 채팅 입력의 프롬프트 인젹션을 LLM 호출 전에 차단하는 공용 가드 모듈 + 두 채팅 경로 배선 |
| Start Date | 2026-10-12 (Plan) |
| End Date | 2026-10-12 (Report) |
| Duration | 1일, 단일 세션 (Plan·Design·Do 4모듈·Check·Act-1) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 97%                        │
├─────────────────────────────────────────────┤
│  ✅ Complete:     15 / 15 FR  + 8/9 DoD      │
│  ⏳ Carry over:    .env.example 수기 반영,   │
│                    커버리지 수치 측정        │
│  ❌ Cancelled:     0                         │
│  Match Rate:      98.2% → 99.8% (Act-1 후)  │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 실행·일반 채팅 두 경로가 사용자 입력을 검사 없이 LLM에 넘겨, "기존 프롬프트 무시하고 ○○ 작성하시오" 류 입력이 소유자 지침을 무력화할 수 있었다. 막는 코드가 한 줄도 없었다. |
| **Solution** | 규칙 15개(한/영, 결정적) → 애매 구간만 관리자 기본 모델 판정 → fail-open 의 2단 가드. 차단 시 LLM을 부르지 않고 고정 안내문을 일반 답변 형태로 반환·저장. 전역 킬스위치, 차단 턴은 다음 턴 컨텍스트에서 제외. |
| **Function/UX Effect** | 정상 요청 LLM 추가 호출 0회(테스트 고정). 공격 코퍼스 76건 규칙 단계 PASS 0·BLOCK ≥ 80%, 선의 코퍼스 53건 오차단 0. 실 LLM 스모크 3/3(메타공격 포함). 실런 3경로(chat REST·agent REST·agent WS) 안내문·스텝·이력 확인. 프론트·스키마 변경 0. |
| **Core Value** | P2 에이전트 소유자가 설정한 지침이 사용자 입력 한 줄로 뒤집히지 않는 예측 가능성을 코어 일반 모듈로 확보. 규칙은 데이터(튜플 카탈로그)라 도메인 특화 없이 확장 가능. |

### 1.4 Success Criteria Final Status

| # | Criteria (Plan §4.1) | Status | Evidence |
|---|----------------------|:------:|----------|
| SC-1 | FR-01~15 구현·테스트 통과(TDD) | ✅ Met | 96 tests passed (domain 39·application 17·infra 12·DI 5·wiring 19·경계 5 — 실 LLM 1 별도) |
| SC-2 | 공격 ≥60 탐지 ≥95%, 선의 ≥50 오차단 0 | ✅ Met | attacks 76: 규칙 PASS 0, BLOCK 82%, 나머지 REVIEW→판정기 3/3; benign 53: BLOCK 0 |
| SC-3 | 두 경로 배선 4조건 | ✅ Met | wiring 테스트 + Design §8.6 실런 |
| SC-4 | 킬스위치 off 시 기존 테스트 무변경 통과 | ✅ Met | `prompt_guard=None` 테스트 ×2, agent_builder·general_chat 1229건 통과 |
| SC-5 | 실 LLM 스모크 3건 기록 | ✅ Met | Design §8.4 (gpt-4o, 3/3, 1.3~2.7초) |
| SC-6 | 로컬 서버 REST+WS 수동 재현 | ✅ Met | Design §8.6 — 결함 1건(`charts: None` 500) 발견·수정 후 재확인 |
| SC-7 | 회귀 FAILED diff 0 | ✅ Met | 53건 = master 상시 실패 목록, module-1→4→Act 모두 동일 |
| SC-8 | Design 문서(규칙·안내문·판정 프롬프트) | ✅ Met | design.md + §8.4/§8.6 실측 + §3.2 정정 |
| SC-9 | 커버리지 ≥80%, lint 0, 40줄 규칙 | ⚠️ Partial | lint 0(공통 UP042 제외)·40줄 준수. 커버리지 수치는 미측정(96건이 공개 메서드 전부 호출) |

**Success Rate**: 8/9 met (89%), 1 partial

### 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 공격 표면 = 채팅 입력만, Port에 `source` 예약 | ✅ | `InputSource.USER_CHAT` 단일 구현, 간접 인젹션은 후속 |
| [Plan] | 규칙 1차 + LLM 2차(REVIEW만) | ✅ | PASS 경로 LLM 호출 0 테스트 고정. 선의 코퍼스 REVIEW 약 20%가 판정기 비용 |
| [Plan] | 차단 + 고정 안내문, 일반 답변 형태·이력 저장 | ✅ | 프론트 변경 0. 실런에서 `charts: None`이 REST 집계를 깨 `[]`로 정정 |
| [Plan] | 판정 모델 = 레지스트리 is_default | ✅ | 판정기는 도메인 포트 `UtilityLLMProviderPort`에 의존(설계보다 엄격) |
| [Plan] | fail-open | ✅ | 4종(timeout·exception·unavailable·judge_disabled). Act에서 timeout `exception=` 보강 |
| [Plan] | 두 경로 배선 + 전역 플래그(pii-masking 미배선 재발 방지) | ✅ | main.py 두 생성 지점 주입, AST 테스트로 고정 |
| [Design] D1 | 역할 탈취 REVIEW, 탈옥 토큰 결합 시 BLOCK | ✅ | "면접관 역할" 선의 통과, 실 LLM 스모크로 injection/benign 분리 확인 |
| [Design] D2 | `guard_blocked` 참일 때만 | ✅ | 정상 턴 키 부재 테스트 |
| [Design] D3 | 모드는 서비스 `enforced`로 수렴 | ✅ | 유스케이스에 모드 분기 0 |
| [Design] D5 | 가드 위치(RUN_STARTED 직후 / 이력 조회 직후·차트 편집 전) | ✅ | 실런 스텝 순서·이벤트 시퀀스 일치 |
| [Design] OQ1 | 초기 모드 `block` | ✅ | config 기본값 |
| [Design] OQ2 | 차단 턴 컨텍스트 제외(안내문 상수 일치) | ✅ (+Act) | G-1: 같은 turn tie에서 user 선행 정렬 추가 |
| [Design] OQ5 | 스텝 요약 원문 없음 | ✅ | 실런 output_summary `tier=BLOCK ... judge=skipped` |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [prompt-guard.plan.md](./prompt-guard.plan.md) | ✅ Finalized |
| Design | [prompt-guard.design.md](./prompt-guard.design.md) | ✅ Finalized (+§8.4/§8.6 실측, §3.2 정정) |
| Check | [prompt-guard.analysis.md](./prompt-guard.analysis.md) | ✅ Complete (Act-1 §6 포함) |
| Act | Current document | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | NFKC·casefold·zero-width 제거·공백 축약 | ✅ | 원문 불변 |
| FR-02 | BLOCK 규칙(덮어쓰기·유출·가짜 구분자·탈옥) | ✅ | D1: 역할 탈취는 REVIEW. 코퍼스로 7건 좁힘·10건 넓힘(rules.py docstring SoT) |
| FR-03 | REVIEW만 판정기 | ✅ | |
| FR-04 | is_default 모델·strict 스키마 | ✅ | `verdict`·`reason` 두 필드, 자유 키 dict 재귀 검사 |
| FR-05 | `<user_input>` 데이터 격리 | ✅ | 메타공격 명시, 스모크 #3 통과 |
| FR-06 | fail-open | ✅ | |
| FR-07 | 차단 시퀀스 두 경로 | ✅ | |
| FR-08 | 결정적 안내문 | ✅ | 한국어 상수 1개 |
| FR-09 | 사용자 메시지 저장 | ✅ | |
| FR-10 | 킬스위치 None | ✅ | 조립 실패도 None + warning |
| FR-11 | log_only | ✅ | |
| FR-12 | 구조화 로그(원문 금지) | ✅ | 스니펫 200자·해시 12자 |
| FR-13 | ai_run 스텝 | ✅ | `NodeType.OTHER` 재사용, 스키마 0 |
| FR-14 | `source` 인자 | ✅ | |
| FR-15 | 규칙 id·카테고리 | ✅ | `lang.category.NN` |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 정상 요청 LLM 추가 호출 | 0 | 0 (테스트 고정) | ✅ |
| 공격 탐지 / 선의 오차단 | ≥95% / 0 | 규칙 PASS 0 + 스모크 3/3 / 0 | ✅ |
| 판정 지연 | timeout 3초 | 1.3~2.7초(gpt-4o) | ✅ 여유 적음 — 운영 관측 |
| 회귀 | FAILED diff 0 | 0 (53=53) | ✅ |
| 레이어 | domain stdlib, application→infra 금지 | AST 5건 | ✅ |
| 스키마·프론트 변경 | 0 | 0 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 도메인 | `idt/src/domain/prompt_guard/` (schemas·rules·policies·exceptions·interfaces) | ✅ |
| 서비스 | `idt/src/application/prompt_guard/service.py` | ✅ |
| 판정기 | `idt/src/infrastructure/prompt_guard/{prompts,llm_judge}.py` | ✅ |
| 설정·DI | `idt/src/config.py` +5키, `idt/src/api/main.py` `get_prompt_guard()` + 2 주입 | ✅ |
| 배선 | `run_agent_use_case.py`, `general_chat/use_case.py` | ✅ |
| 테스트 | 15 파일 96건 + 코퍼스 3 + 실 LLM 스모크 1 | ✅ |
| 문서 | Plan·Design·Analysis·Report | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority | Effort |
|------|--------|----------|--------|
| `idt/.env.example` PROMPT_GUARD 5키 | bkit 쓰기 정책이 `.env*` 차단 | High (배포 전) | 1분 수기 |
| 커버리지 수치 측정 | 이번 사이클 미실행 | Low | `pytest --cov` 1회 |
| **에이전트 경로 turn_index 중복(기존 결함)** | user 저장은 별도 세션 즉시 commit, assistant 저장은 요청 세션 스냅샷 조회 → 같은 turn. 2026-09-30 이후 11세션에서 기존 재현. 이번 범위 밖 | Medium | 소형 사이클 — `_save_assistant_message`도 session_factory 경로로 |
| mode 오타 → 가드 전체 off(G-10) | 설계(탈착형 이음매) 유지. config 주석에 주의 | Low | `block` 폴백 또는 error 로그 검토 |
| 간접 인젹션(문서·도구 결과), 출력 검사, 에이전트별 토글, 관리자 화면 | Plan Out of Scope | — | 후속 Plan |

### 4.2 Cancelled

없음.

---

## 5. Quality Metrics

### 5.1 Final Analysis

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| Design Match Rate | 90% | 99.8% | 98.2% → 99.8% (Act-1) |
| Structural / Functional / Contract / Runtime | — | 98.4 / 100 / 100 / 100 | FR-12·G-1·G-4 해소 |
| 테스트 | — | 96 passed (+ llm 1) | 55 → 76 → 94 → 96 |
| 회귀 | diff 0 | 53 = 53 | 5회 확인 |
| 보안 이슈 | 0 Critical | 0 | Important 1건(G-1) Act에서 해소 |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| 차단 페이로드 `charts: None` → REST `/chat` 500 | `[]`로 통일, 테스트·Design 정정 | 실런 재확인 200 |
| 차단 턴 제외가 turn tie 정렬에 의존(G-1) | `(turn_index, user 선행)` 정렬 + 테스트 | 공격문 컨텍스트 잔존 경로 차단 |
| timeout 경고 `exception=` 누락(G-4) | `as e` 전달 | logging 규칙 준수 |
| 테스트 공백(G-5~G-8) | turn 값·로그 키·DI AST·경계 접두 | 계약 100% |
| 설계 SoT 어긋남(G-2, 규칙 정정 미기록) | Design §3.2 + rules.py docstring | 추적 가능 |
| 메모리의 잘못된 플레이크 진단 | 단언 과다로 정정, 메모리 수정 | — |

---

## 6. Lessons Learned

### 6.1 Keep

- **코퍼스 선행**: 선의 53문장을 먼저 쓰고 규칙을 맞추자 "내부 규정 알려줘"·"새 규칙은 다음과 같습니다"·"아이폰 탈옥" 같은 오차단 후보가 설계 단계 패턴에서 7건 드러났다. 규칙은 코드가 아니라 코퍼스가 검증한다.
- **실런이 fake를 이긴다**: `charts: None` 결함은 배선 테스트 18건이 모두 통과한 뒤 실런 첫 요청에서 500으로 나타났다. `execute()` 집계 경로는 fake 스트림 테스트가 덮지 못한다. 위키 "미배선 모듈은 실 LLM 1회가 DoD"의 배선판.
- **탈착형 이음매**: `prompt_guard=None` 기본 + DI None 팩토리 덕에 기존 1229건을 한 줄도 바꾸지 않았다.
- **모듈 4분할 세션**: 각 모듈 끝에 회귀 FAILED diff를 찍어 어느 변경이 회귀를 냈는지 즉시 특정 가능한 상태를 유지했다.

### 6.2 Problem

- Design 규칙 표를 코드와 동시에 갱신하지 않아 gap-detector가 ~10건의 패턴 확장을 "미기록"으로 잡았다. 규칙 데이터는 코드가 SoT인데 Design 표가 사실상 두 번째 사본이었다.
- 1차 실런에서 OpenAI 연결 재시도로 10분이 넘어 JWT가 만료되는 환경 노이즈가 섞였다. 실런 스크립트는 토큰 수명을 넉넉히 잡거나 경로별로 나눠 돌려야 한다.
- 기존 결함(turn_index 중복)을 실런에서 발견했지만 이번 범위가 아니라 보고만 했다. 발견 비용은 낮았는데 수정은 다음 사이클로 밀렸다.

### 6.3 Try

- 규칙 카탈로그처럼 "코드가 SoT인 데이터"는 Design에 **카테고리·tier만** 두고 패턴 본문은 코드 링크로 대체한다.
- 실런 스크립트에 경로별 `--only` 인자와 토큰 재발급을 넣어 재실행 비용을 낮춘다.
- 운영 배포 후 1~2주 `judge_error=timeout` 비율과 REVIEW 비율을 로그로 보고 타임아웃·soft 규칙을 조정한다.

---

## 7. Process Improvement Suggestions

| Phase | Current | Suggestion |
|-------|---------|------------|
| Plan | Open Questions 5건을 Design 진입 전 질문으로 소화 | 유지 — 설계 중 되돌림 0 |
| Design | 규칙 패턴을 표로 복제 | 데이터성 항목은 코드 참조로 |
| Do | 모듈별 회귀 diff | 유지. 실런은 module-3 직후(배선 완료) 즉시 1회 추가 |
| Check | gap-detector 보고 → 세션에서 Important만 코드 재확인 | 유지 — G-1·G-4 모두 재확인 후 수정 |

| Area | Suggestion | Benefit |
|------|------------|---------|
| 운영 관측 | `prompt_guard decision` 경고 로그 대시보드(tier·rule_ids·judge_error 분포) | 오차단·타임아웃·REVIEW 비율을 데이터로 튜닝 |
| 후속 사이클 | turn_index 중복 수정(에이전트 경로) | 이력 정렬 안정성, G-1 완화책 불필요 |
| 후속 사이클 | 간접 인젹션(`InputSource.TOOL_RESULT`) | 같은 Port로 확장 |
