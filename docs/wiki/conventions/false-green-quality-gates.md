---
title: 거짓 초록 — 통과했는데 검증되지 않은 품질 게이트
status: approved
source_type: conversation
source_refs:
  - idt_front/package.json:6-15 (build="tsc -b && vite build" vs type-check="tsc --noEmit")
  - idt_front/src/hooks/useLlmModels.ts:22 (select: (data) => data.models)
  - docs/archive/2026-08/agent-create-entry/agent-create-entry.report.md (§1.4 QC-1~3, §6.2)
  - docs/archive/2026-08/intent-analyzer/intent-analyzer.report.md (SC-2 baseline 58건, §6.2)
  - docs/archive/2026-08/tool-recommender/tool-recommender.report.md (§6.1 픽스처가 설계 가정을 따라간 사례)
  - docs/archive/2026-08/prompt-composer/prompt-composer.analysis.md (SC-01 — FAILED 목록 byte-identical 대조)
  - idt/docs/archive/2026-10/subagent-context-scope/subagent-context-scope.report.md (§1.3, §6.2~6.3 — v3)
  - 커밋 fe184dd (WorkflowCompiler 저장소 DI 누락 → TestRuntimeSubAgentWiring) — v3
  - 커밋 49b2f41 (AsyncMock이 가린 function_node_ids 회귀 → C0) — v3
  - idt/tests/api/test_runtime_tool_factory_wiring.py (배선 계약 테스트) — v3
  - idt/docs/04-report/approval-gate-run-termination.report.md (§6.1 — 단위 초록 상태에서 L3가 결함 2건) — v3
  - docs/archive/2026-11/stock-analysis-agents/stock-analysis-agents.analysis.md (G2 — MSW 목 소문자 'holiday'가 서버 대문자 값 불일치를 가림) — v4
  - 커밋 8bb4c3c (LlmModelRepository.update()가 단가 3필드를 옮기지 않아 PATCH 200인데 DB 미저장) — v4
  - docs/archive/2026-11/stock-analysis-agents/stock-analysis-agents.report.md (§6.2~6.3) — v4
confidence: 0.85
version: 4
created: 2026-08-14
updated: 2026-11-27
reviewer: 배상규
verified_at: bcf64b0
---

# 거짓 초록 — 통과했는데 검증되지 않은 품질 게이트

> v4 (2026-11-27): §4(c) 목 enum 값 불일치, §7(쓰기 API 200은 저장 증거가 아니다) 추가. 에이전트 갱신이라 approved → draft 강등.
>
> v3 (2026-10-06): §6(모킹·앱 싱글톤 배선이 런타임 경로를 가림) 추가. 제목의 "4종" 제거.
> 에이전트 갱신이므로 approved → draft 강등 (재승인 필요).

## 문제

세 개의 PDCA 사이클(agent-create-entry / intent-analyzer / tool-recommender)이
서로 다른 방식으로 **"게이트는 통과했는데 실제로는 검증되지 않은"** 상태를 만들었다.
전부 사후에 발견됐고, 전부 사전에 막을 수 있었다.

## 검증된 사실

### 1. 전역 기준 품질 게이트는 단일 기능 사이클에서 달성 불가

`npm run lint 0 에러`, `npm run build 성공`을 DoD로 잡았으나 착수 시점에 이미
전역 lint 35건 / `tsc -b` 18건이 존재했다. 이 기능의 기여분은 0건이었는데도
DoD는 "미충족"으로 기록됐다 — **기준 설정 오류**다.

백엔드도 같다: `pytest` 전체에 baseline 실패 58건(parser 21 / agent_builder_stream 9
/ retriever 7 / general_chat 7 …)이 상시 존재하며, 원인은 라이브러리 버전 드리프트다.
(v3: 2026-09~10 사이클 보고서 기준 상시 실패는 **53건**으로 줄었다 — 숫자는 변하므로 매번 목록 diff로 확인.)

> **관행**: 품질 기준은 **"변경 파일 기준"과 "전역 기준"을 분리 표기**한다.
> 전역 부채는 별도 정리 사이클로 뺀다.

### 2. baseline 스냅샷을 안 뜨면 "내가 깬 것"과 구분할 수 없다

`git stash`(프론트) 또는 착수 전 `pytest -q | tail -1`(백엔드)로 **기존 실패
목록을 파일별 개수까지** 떠 두면, Check 단계에서 오귀속 조사에 드는 시간이 0이 된다.
intent-analyzer는 이걸 안 해서 "58건이 baseline인지 내 탓인지" 확인에 추가 시간을 썼다.

### 2-1. 회귀 0건은 **pass/fail 개수가 아니라 실패 목록 diff**로 증명한다 (v2)

baseline 실패 58건이 상시 존재하는 저장소에서 `"N passed, 58 failed"` 는 회귀
여부를 **전혀 말해주지 않는다** — 내가 1건을 깨고 기존 1건이 우연히 고쳐져도 숫자는
같다. 개수 대신 **정렬된 실패 목록을 문자열로 대조**한다.

```bash
pytest -q --ignore=tests/<내_모듈> 2>&1 | grep '^FAILED' | sort > /tmp/base.txt
pytest -q                            2>&1 | grep '^FAILED' | sort > /tmp/after.txt
diff /tmp/base.txt /tmp/after.txt    # 비어 있으면 회귀 0건
```

prompt-composer 사이클이 이 방식으로 SC-01(회귀 0건)을 **byte-identical**로 증명했다.
`--ignore` 실행이 baseline 역할을 하므로 착수 전 스냅샷을 놓쳤어도 사후 복구가 된다
(단, 기존 파일을 수정했다면 `git stash` 대조가 여전히 필요하다).

> **관행**: Check 단계 증거로 "N passed"를 적지 않는다. `diff` 결과(빈 출력) 또는
> 신규 FAILED 항목 목록을 적는다.

### 3. `tsc --noEmit`과 `tsc -b`는 검사 범위가 다르다

```json
"build":      "tsc -b && vite build",   // ← CI가 실제로 돌리는 것
"type-check": "tsc --noEmit"            // ← 이것만 돌리면 통과할 수 있다
```

`type-check`만 돌려 "클린"으로 보고했으나 `tsc -b`가 테스트 파일 2건의 타입 에러를
잡았다. **품질 게이트는 CI가 실제로 실행하는 명령과 문자 그대로 같아야 한다.**
프론트 Do 종료 게이트는 `npm run build`로 통일.

### 4. 모킹·픽스처가 "내 가정"을 따라가면 테스트는 항상 통과한다

두 가지 형태로 나타났다.

**(a) MSW 핸들러 응답 형태가 훅의 `select`와 어긋남**
`useLlmModels`는 `select: (data) => data.models`로 꺼내는데 핸들러가 배열을 그대로
반환하면, 모델 역매핑이 **에러 없이 조용히 실패**한다. 기존
`AgentBuilderPage/index.test.tsx`도 같은 실수를 갖고 있으나 모델을 단언하지 않아
드러나지 않는다 — **잠재적 위양성이 이미 리포지토리에 있다.**

**(b) 테스트 픽스처를 설계 가정에 맞춰 만듦**
`is_low_signal`은 실제 MCP 데이터에서 스텁을 하나도 못 잡는 상태였는데, 픽스처를
설계 가정대로 만들었기 때문에 테스트는 전부 통과했다. 실제 코드
(`tool_registry.py:83-90`)를 정독해서야 발견됐다.

**(c) 목의 enum 값을 손으로 적음** (v4)
시장 분석 건너뜀 사유는 서버가 `DISABLED·WEEKEND·HOLIDAY·BUSY`(대문자)를 보내는데, 화면 라벨 키와
MSW 목이 둘 다 소문자 `'holiday'`였다. 테스트는 통과했고 실화면에는 원래 코드가 그대로 보였다(G2).
목과 라벨이 **같은 틀린 가정을 공유**하면 테스트는 그 가정을 검증하지 못한다.

> **관행**: MSW 핸들러는 **대응 훅의 `select`/응답 타입을 먼저 확인**하고 작성한다.
> 목의 enum 문자열은 서버 StrEnum 값에서 복사하고, 가능하면 프론트 타입의 같은 상수에서 만든다.
> 데이터 형태를 다루는 로직의 픽스처는 **실제 데이터 표본 1건**에서 뜬다.

### 5. 커버리지는 Check가 아니라 Do 종료 조건이어야 한다

Do에서 ruff·pytest만 돌리고 넘어가, 설계 이탈로 추가한 코드 13 stmts가 통째로
미검증인 채 Check까지 갔다. 커버리지를 재자 갭 2건이 즉시 드러났고, 해소는
**프로덕션 코드 무수정 + 테스트 추가**만으로 끝났다.

관련: 설계 이탈 항목을 추가할 때 테스트를 같이 늘리지 않는 것이 직접 원인이었다 —
"이탈 항목 → 대응 테스트" 2열 표를 Do 산출물로 만들면 이탈을 적는 순간 테스트도 적게 된다.

### 6. 모킹과 앱 싱글톤 배선은 "한 번도 실행된 적 없는 런타임"을 초록으로 만든다 (v3)

subagent-context-scope 조사 중 **서브에이전트 런타임이 운영에서 한 번도 동작한 적이 없었다**는 사실이
드러났다. 3중 차단이 4개월 잠복했고, 단위·통합 테스트는 전부 초록이었다.

| 차단 | 왜 테스트가 못 잡았나 | 고정 장치 |
|------|------|------|
| sub_agent가 `function_node_ids` 누락 → `AttributeError` | 기존 테스트가 `_compile_sub_agent` 를 `AsyncMock` 으로 대체해 실제 노드 실행 경로를 안 탐 | 컴파일된 그래프에서 노드를 실제 실행하는 C0 테스트 |
| `WorkflowCompiler`(앱 싱글톤)에 `agent_repository`·`llm_model_repository` 미주입 → compile `ValueError` | 선택(optional) 의존성이라 생성은 성공, 단위 테스트는 직접 주입 | `test_runtime_tool_factory_wiring.py::TestRuntimeSubAgentWiring`(main.py 실제 싱글톤의 주입 단언) |
| worker_id 공백 → OpenAI name 400 | 단위 테스트는 실 LLM을 안 부름 | L3 실런 + `sanitize_llm_name` |

- 2·3번은 **L3 실런에서만** 드러났다. approval-gate-run-termination 사이클도 단위 초록 상태에서 L3가
  결함 2건(안내 문구 패배·인자 조립 파싱)을 드러냈다 — 두 사이클 연속 같은 패턴.
- 앱 싱글톤이 per-request 세션에 묶인 저장소를 써야 할 때는 `SessionScoped*Repository`(호출마다
  `session_factory()` 로 새 세션을 열어 위임) 어댑터를 main.py에서 주입한다 — 기존 7종+ 선례.
- "런타임 위임은 범위 외"로 넘긴 경로는 아무도 실행하지 않는다 — 이월 시 **L3 실런 항목**으로 백로그에 명시.

### 7. 쓰기 API의 200은 저장의 증거가 아니다 (v4)

`PATCH /llm-models/{id}/pricing`이 200과 바뀐 값을 돌려줬지만 `LlmModelRepository.update()`가 단가 3필드를
행에 옮기지 않아 **DB에는 남지 않았다**(커밋 8bb4c3c). 저장소 `update()`는 행을 다시 읽지 않고 **입력 도메인 객체를 그대로 반환**하므로(`return model`), 응답은
저장 여부와 무관하게 맞아 보였다. 같은 실측에서 공급사 응답 모델명이 날짜 붙은 스냅샷명(`gpt-5.1-2025-11-13`)이라
등록명과 매핑되지 않아 실행 비용이 0으로 남는 결함도 겹쳐 있었다(`ModelNameResolver`가 날짜 꼬리를 떼고 다시 찾도록 수정).

- 저장소 `update()`가 필드를 하나씩 옮기는 구현이면, 도메인에 필드를 추가할 때 `update()`도 같이 고쳐야 하고
  테스트는 **저장 후 새 세션으로 다시 읽어** 확인해야 잡힌다.

## 다음에 적용하는 법

1. Plan에서 품질 기준마다 **측정 범위(변경 파일 / 전역)** 를 명시한다.
2. 착수 전 **baseline 스냅샷**을 남긴다 — 개수 1줄이 아니라 **`FAILED` 목록 파일**
   (§2-1). 잊었다면 `--ignore=tests/<내_모듈>` 실행으로 대체한다.
3. 게이트 명령은 **CI 스크립트에서 복사해 붙인다** (`npm run build`, `pytest`).
4. 모킹 작성 전 **소비 측 코드(`select`, 파서, 정규화)를 먼저 읽는다.**
5. **Do 종료 조건에 커버리지 측정**을 넣고 미커버 라인을 눈으로 확인한다.
6. 외부 의존(LLM 실호출·MCP·실서버)이 필요한 검증은 수동 체크리스트로 미루면
   사이클이 끝나도록 미실행된다 — **Do 단계의 종료 조건**으로 못 박거나, 환경이
   없다면 그 사실 자체를 Plan 리스크로 올린다.
7. (v3) 새 노드·워커 유형은 **컴파일 그래프 실제 실행 테스트**를, 앱 싱글톤의 선택 의존성은
   **배선 계약 테스트**를 기본으로 둔다. 기존 경로에 처음 의존하는 기능이면 **module-1 전에 실런 스모크**로
   전제부터 확인한다 (기존 기능이 동작한다고 가정하지 말 것).
8. (v4) 쓰기 API 실측·테스트는 **"응답 확인 → DB(또는 GET) 재조회"** 2단계로 한다.

## 관련 문서

- 이월 처리 방침: `conventions/explicit-gap-carryover.md`
- 수동 검증 목록: `ops/e2e-carryover-checklist.md`
- 뮤테이션 버튼 가드 테스트의 위양성: `frontend/patterns/loading-button-pending-guard.md`
