# pii-masking-integration Completion Report

> **Status**: Complete (배포 전 확인 사항 있음, §8.1)
>
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Completion Date**: 2026-11-05
> **PDCA Cycle**: Plan v0.2 → Design v0.6 → Do 4모듈 → Check → Act-1
> **선행 사이클**: [pii-masking.report.md](../../../04-report/pii-masking.report.md) (엔진 완료, 배선 제외)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | pii-masking-integration |
| Start Date | 2026-11-02 |
| End Date | 2026-11-05 |
| Duration | 4일 |
| 작업 공간 | worktree `wt/pii-masking`, 브랜치 `feature/pii-masking-integration` (미커밋) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Design Match Rate: 95.8% (static)           │
├─────────────────────────────────────────────┤
│  ✅ FR 완료:      16 / 17                     │
│  ⏸ 이월:          1 / 17 (FR-15, D-04)       │
│  ✅ Success Criteria: 11 / 12                 │
│  ❌ 미충족:        1 / 12 (.env.example 수기) │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | `pii_masking` 엔진은 2026-06에 완성됐지만 참조하는 코드가 없어, 주민번호·계좌·연락처가 원문 그대로 외부 LLM으로 전송됐다. 엔진도 `\b` 경계 때문에 조사가 붙은 한국어 문장의 PII를 거의 탐지하지 못했다. |
| **Solution** | create_agent 경로는 `PiiMaskingMiddleware`를 체인 맨 앞에, 직접 호출(supervisor·final_answer·파이프라인)은 `GuardedLlm` 프록시를, 보조 LLM은 `PiiGuardedLLMFactory`를 거치게 했다. 셋은 같은 `PiiMessageMasker`와 런 범위 vault를 쓴다. 탐지 규칙은 한국어 문장 코퍼스 기준으로 다시 작성했다. |
| **Function/UX Effect** | on 모드 실런에서 에이전트·일반 채팅 REST·WS와 승인 흐름의 외부 LLM 요청 31건에 원본 PII가 0건이었다. 토큰 345건에 placeholder 조각이 0건이었고, 승인 화면과 집행 인자는 원본 주소였다. 기본값은 shadow라 배포만으로는 동작이 바뀌지 않는다. |
| **Core Value** | 고객 개인정보가 외부 LLM으로 나가지 않는다는 것을 코드 경계와 계약 테스트로 고정했다. 새 LLM 생성 지점이나 원본 팩토리 소비자가 생기면 테스트가 실패한다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | FR-01~FR-17 구현 및 테스트 통과 | ✅ | FR 16건 완료, FR-15 이월(D-04). PII 테스트 406건 통과 |
| SC-2 | 실런: 에이전트(react 워커·MCP 파이프라인·승인 재개)·일반 채팅, REST·WS 각 1회 이상 | ✅ | Design §8.6·§8.7·§8.8. 승인 재개는 Act-1에서 실행 |
| SC-3 | 외부 요청 원본 PII 0, 답변·DB placeholder 0, 도구는 원본 인자 | ✅ | 외부 요청 31건 원본 0건. 답변 `[REDACTED_]` 0건. 실제 PII가 든 MCP 결과는 미검증(§4.1) |
| SC-4 | 스모크: 이메일 → 메일 승인 화면·집행 인자가 원본 | ✅ | `tool_args.to`, 집행 인자 `to` 모두 `lee.test@example.com`. 실제 발송은 `call_tool` 가로채기로 막음 |
| SC-5 | 스트리밍 토큰에 placeholder 조각 없음 | ✅ | 토큰 345건 조각 0건 (module-4 실런 574건 포함 누적 919건) |
| SC-6 | shadow→on 전환이 설정 변경과 재기동만으로 가능 | ✅ | `PII_MASKING_MODE` (`config.py`) |
| SC-7 | `.env.example` 갱신 | ❌ | bkit 정책으로 세션에서 편집 불가. 수기 반영 필요(§8.1) |
| SC-8 | 신규·변경 모듈 커버리지 80% 이상 | ✅ | `pii_masking` 3계층 98% (589줄 중 13줄 미실행) |
| SC-9 | 회귀 0 (정렬 FAILED diff) | ✅ | 60 failed / 11,275 passed. 기준선 대비 추가 1건은 부하 중 시간 예산 테스트, 단독 3회 통과 |
| SC-10 | verify-architecture·logging·tdd 통과 | ✅ | 새 위반 0. 기존 위반 2종(domain LangChain 타입 1건, routes infrastructure import 10건) 유지 |
| SC-11 | 함수 40줄·중첩 2단계 | ✅ | 이번 변경으로 새로 초과한 함수 0. `mcp_executor._call`은 기존 초과(47→49) |
| SC-12 | compile된 그래프 실행 테스트 | ✅ | `test_pii_masking_compile.py`, `_scripted_model.py` |

**Success Rate**: 11/12 (92%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 미들웨어 + 직접 호출용 공용 코어 | ✅ | Design Option C(미들웨어 + `GuardedLlm`)로 구체화 |
| [Plan] | MCP는 인자·결과 탐지·기록, 값 불변 | ✅ | 3경로(어댑터·로더·집행기)에 `pii_inspector` 주입. 고아 placeholder만 차단 |
| [Plan] | 대화 경로 전체 LLM | ✅ | 보조 LLM은 팩토리 래핑(D-09). 대화 경로 밖은 허용 목록에 사유와 함께 고정 |
| [Plan] | shadow 후 on | ✅ | 기본 shadow. Act-1에서 shadow가 MCP 인자를 막던 부작용 제거(D-10 수정) |
| [Plan] | 런 범위 vault, 영속화 없음 | ✅ | `PiiRunScope`. 승인 재개는 새 scope로 재마스킹 |
| [Design] D-01 | 카탈로그 미사용, 항상 맨 앞 | ✅ | 계약 테스트 `test_compiler_create_agent_calls_prepend_pii_middleware` |
| [Design] D-05 | 출력 redact 제거 | ✅ | `PII_MASKING_OUTPUT_REDACT` 삭제 |
| [Design] D-08 | 구조화 출력 고아 보존, 도구 경계에서 차단 | ✅ | `[REDACTED_EMAIL]`로 MCP가 실행되는 결함 방지 |
| [Design] D-09 | 보조 LLM은 팩토리 래핑, compiler는 raw | ✅ | module-3에서 원본이 새던 근거 판정 LLM 해소 |
| [Design] D-11 (Act-1) | placeholder 안내를 system에 덧붙임 | ✅ | 승인 흐름 중단(G-13) 해소 |
| [Design] D-04 | FR-15 이월(사내 모델도 마스킹) | ✅ | 폴백 우회 없음 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [pii-masking-integration.plan.md](pii-masking-integration.plan.md) | ✅ v0.2 |
| Design | [pii-masking-integration.design.md](pii-masking-integration.design.md) | ✅ v0.6 |
| Check | [pii-masking-integration.analysis.md](pii-masking-integration.analysis.md) | ✅ v0.2 |
| Act | 현재 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 미들웨어가 요청 마스킹, 응답 본문·tool_calls 원복 | ✅ | 3가지 응답 형태 원복 |
| FR-02 | 마스킹은 요청에만. 상태·도구·승인 초안·DB는 원본 | ✅ | `request.override`만 사용. 승인 스모크로 초안 원본 확인 |
| FR-03 | 체인 맨 앞, 소유자가 해제 불가 | ✅ | D-01 |
| FR-04 | on 조립 실패는 fail-closed, shadow는 경고 | ✅ | `get_pii_masker()` |
| FR-05 | 직접 호출 경로, 구조화 출력 원복 | ✅ | `_guard_llm`, `_guard_like` |
| FR-06 | 대화 경로 보조 LLM | ✅ | UtilityLLMProvider 2곳, 요약기, 대화 LLM, 차트, 도구 선별기 |
| FR-07 | 우회 방지 계약 테스트 | ✅ | 직접 생성 23곳 + raw 팩토리 소비자 9곳 허용 목록, 변이 테스트 |
| FR-08 | 런 범위 vault, 서브에이전트 공유 | ✅ | |
| FR-09 | 두 채팅 경로 토큰 원복, 종료 시 flush | ✅ | 일반 채팅 STEP_REASONING 원복 포함 |
| FR-10 | MCP 인자·결과 타입별 건수 기록 | ✅ | 값 미기록 |
| FR-11 | 파이프라인 `tool.ainvoke`·승인 후 집행 포함 | ✅ | |
| FR-12 | off/shadow/on, 기본 shadow | ✅ | off는 `PII_MASKING_ENABLED=false` (D-03) |
| FR-13 | 관측: 타입별 건수만 | ✅ | ai_run 스텝(정상 종료) + 요약 로그(모든 종료 경로, D-12) |
| FR-14 | 한국어 문장 기준 탐지 재작성 | ✅ | 코퍼스 3종, 허용 오탐 7건 고정 |
| FR-15 | 사내 모델 마스킹 생략 | ⏸ 이월 | D-04 |
| FR-16 | 멀티모달은 텍스트 블록만 | ✅ | |
| FR-17 | LangSmith 추적 기동 경고 | ✅ | 마스킹 해제 시 경고하지 않도록 Act-1 수정 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 보안: 외부 요청 원본 PII | 0건 | 0건 (31건) | ✅ |
| 정확도: 코퍼스 PII 누락·날짜·금액 오탐 | 0건 | 0건 (허용 오탐 7건은 `known_fp.txt`로 고정) | ✅ |
| 성능: 호출당 마스킹 | 평균 20ms 미만 | 탐지기 50KB 14ms (module-1 측정, 168ms에서 개선). 호출 단위 벤치 미작성 | ⚠️ |
| 호환: 회귀·API 스키마 변경 | 0 | 0 | ✅ |
| 아키텍처: domain→infrastructure | 0 | 0 | ✅ |
| 로깅: LOG-001, 원본 미기록 | 준수 | 준수 (verify-logging) | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 도메인 (패턴·정책·vault·포트) | `idt/src/domain/pii_masking/` | ✅ |
| 공용 코어 (masker·middleware·GuardedLlm·팩토리·스트림 원복기) | `idt/src/application/pii_masking/` | ✅ |
| 배선 | `workflow_compiler.py`, `run_agent_use_case.py`, `general_chat/use_case.py`, MCP 3곳, `conversation/*`, `main.py` | ✅ |
| 코퍼스 | `idt/tests/fixtures/pii_masking/{pii_ko,benign_ko,known_fp}.txt` | ✅ |
| 계약 테스트 | `idt/tests/application/pii_masking/test_boundary_contract.py` | ✅ |
| 문서 | Plan v0.2, Design v0.6, Analysis v0.2, 현재 문서 | ✅ |

변경 규모: 수정 23개 파일, 신규 30개(문서·테스트 포함).

---

## 4. Incomplete Items

### 4.1 잔여 위험 (범위 밖 또는 미검증)

| Item | 현재 상태 | 처리 |
|------|-----------|------|
| 실제 PII가 담긴 MCP 결과 | 단위·그래프 테스트로만 검증. 고객 문의 MCP는 서버에서 연락처를 `010-****-4222`로 가려 반환 | 원본을 반환하는 MCP로 on 실런 1회 필요 |
| 외부 도구 인자 (Tavily·Perplexity·외부 MCP) | 원본 인자 전달. MCP는 건수 기록만 | 사용자 결정으로 제외. shadow 집계로 규모 측정 후 후속 Plan |
| 임베딩 API | 쿼리 원문 전송 | 후속 |
| 이미지 | 텍스트 블록만 마스킹 | 후속 |
| 이름·주소 | 정규식 5종만 | 후속 (NER 필요) |
| LangSmith 체인 추적 | 상태 원본 기록, 기동 경고만 | on 모드에서는 추적을 끄고 운영 |
| 대화 경로 밖 LLM | 허용 목록에 사유와 함께 기록 | 인제스트·평가·위키·관리자 생성기·RAG 독립 API |
| 모델 자체 안전장치 | on에서 원문을 못 보므로 주민번호 포함 질문 거부가 사라짐 (shadow 3회 중 2회 거부 → on 6회 모두 응답) | 운영 판단 필요 |

### 4.2 Minor (Analysis §5)

| ID | 내용 |
|----|------|
| G-5 | 런 안에서 이미 배정된 `[PHONE_1]`을 사용자가 직접 입력하면 응답에서 실제 번호로 원복된다 |
| G-7 | 에이전트 supervisor 추론 텍스트는 구조화 출력이라 고아 placeholder가 그대로 표시될 수 있다 |
| G-8 | shadow에서 `PII_MASKING_TYPES` 오타는 경고 후 관측·검사가 함께 꺼진다 |
| D-10 부작용 | on 모드에서 사용자가 직접 입력한 `[PHONE_1]` 형태 문자열은 MCP 인자에서 차단된다 |
| — | §8.4 `test_no_pii_in_logs` 미작성, 호출 단위 성능 벤치 미작성 |

### 4.3 이 기능과 무관하게 발견한 문제

- action 파이프라인 초안 생성기가 사용자가 지정한 본문 대신 다른 문장을 만든다. on("고객센터로 문의해 주세요.")과 shadow("메일을 보낼 수 없습니다.") 모두에서 재현된다. 별도 이슈로 다룬다.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| Design Match Rate (static) | 90% | 95.8% | Check 89.4% → Act-1 |
| Test Coverage (pii_masking) | 80% | 98% | |
| PII 관련 테스트 | — | 406 passed | |
| 새 회귀 | 0 | 0 | |
| Critical 잔존 | 0 | 0 | G-13 발견·해소 |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| 조사가 붙은 한국어 PII 미탐지 (`\b`) | 숫자·대시 lookaround, 코퍼스 선행 | ✅ |
| 날짜·금액·사업자번호 ACCOUNT 오탐 | 자릿수·단위·체크섬 규칙 | ✅ |
| 고아 placeholder를 redact하면 `[REDACTED_EMAIL]`로 도구 실행 | 인자는 알려진 것만 원복, 도구 경계에서 차단 (D-08) | ✅ |
| 근거 판정 LLM이 원본 수신 (module-3) | 보조 LLM 팩토리 래핑 (D-09) | ✅ |
| 일반 채팅 STEP_REASONING에 마스킹 원문 노출 | 원복 추가 | ✅ |
| shadow에서 MCP 인자 차단 (G-3) | on 모드에서만 차단 | ✅ |
| on에서 승인 흐름 중단 (G-13) | placeholder 안내 (D-11) | ✅ |
| 실패·재개·일반 채팅 집계 누락 (G-2) | 요약 로그 전 경로 (D-12) | ✅ |
| 팩토리 경유 우회 미검출 (G-1) | raw 팩토리 소비자 허용 목록 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- 코퍼스를 먼저 쓰고 탐지를 고쳤다. 선행 엔진은 합성 영문형 테스트 55건이 통과했지만 한국어 문장에서는 거의 동작하지 않았다.
- 전송 직전 요청(`ChatOpenAI._get_request_payload`)을 프로세스 안에서 기록하는 실런으로, 단위 테스트가 놓친 누출(근거 판정 LLM)과 기능 결함(승인 흐름 중단)을 찾았다.
- compile된 그래프 테스트가 미들웨어 단위 테스트로는 드러나지 않은 `[REDACTED_EMAIL]` 도구 실행을 잡았다.

### 6.2 What Needs Improvement (Problem)

- 실런을 조회 도구로만 해서 on 모드의 승인 흐름 중단(G-13)을 Check 단계에서야 발견했다. 마스킹은 "LLM이 값을 어떻게 판단하는가"를 바꾸므로, 값의 확인 여부를 판단하는 프롬프트(action 인자 작성)를 거치는 경로를 Do 단계 실런에 넣었어야 했다.
- shadow 모드의 부작용(G-3)은 "shadow는 아무것도 바꾸지 않는다"를 MCP 경계까지 테스트하지 않아 생겼다.

### 6.3 What to Try Next (Try)

- 마스킹·필터 계열 기능은 실런 시나리오에 쓰기 도구(승인 필요)를 1건 이상 넣는다. 실제 시스템과 연결된 도구는 전송 직전 계층(`call_tool`)을 가로챈다.
- 관측 모드(shadow)는 "요청·인자·결과 불변"을 모드별 테스트로 고정한다.

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Design | §8.3 시나리오에 승인 흐름이 그래프 테스트로만 있었다 | 실런 DoD에 "쓰기 도구 1건, 실제 전송 가로채기"를 명시 |
| Check | gap-detector가 30턴 한도로 중간에 멈췄다 | 범위가 큰 기능은 파일 묶음별로 나눠 맡긴다 |

---

## 8. Next Steps

### 8.1 Immediate (배포 전)

- [ ] `idt/.env.example`에 `PII_MASKING_MODE=shadow` 추가, `PII_MASKING_OUTPUT_REDACT` 삭제 (수기)
- [ ] 커밋·PR (`feature/pii-masking-integration`)
- [ ] 운영 배포는 shadow로 하고 `PII masking summary`·`MCP PII inspected` 로그로 탐지 건수와 오탐을 확인한 뒤 on 전환
- [ ] on 전환 시 LangSmith 추적(`LANGSMITH_TRACING`)을 끈다 (D-06)
- [ ] 실제 PII를 반환하는 MCP로 on 실런 1회 (§4.1)
- [ ] 로컬 DB의 실런 대화·승인 기록에 합성 PII(010-2345-6789, lee.test@example.com, 900101-1234567)가 남아 있음. 필요하면 정리

### 8.2 Next PDCA Cycle

| Item | Priority |
|------|----------|
| 외부 도구 인자 마스킹 (shadow 집계 결과 기반) | High |
| action 초안 본문이 요청 문구를 따르지 않는 문제 (§4.3) | Medium |
| 이름·주소 탐지 (NER) | Medium |
| 임베딩 API 쿼리 마스킹 | Low |

---

## 9. Changelog

### v1.0.0 (2026-11-05)

**Added:**
- 외부 LLM 경계 PII 마스킹: `PiiMaskingMiddleware`, `GuardedLlm`, `PiiGuardedLLMFactory`, `PlaceholderStreamRestorer`
- MCP 경계 PII 검사(건수 기록, on 모드 고아 placeholder 차단)
- `PII_MASKING_MODE` (shadow/on)
- 우회 방지 계약 테스트, 한국어 코퍼스

**Changed:**
- PII 탐지 규칙 한국어 문장 기준 재작성
- 런 범위 vault (`PiiRunScope`), `TokenVaultRegistry`·`TokenVaultStorePort` 삭제

**Removed:**
- `PII_MASKING_OUTPUT_REDACT`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-05 | Completion report created | 배상규 |
