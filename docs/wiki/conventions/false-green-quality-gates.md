---
title: 거짓 초록 — 통과했는데 검증되지 않은 품질 게이트 4종
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt_front/package.json:6-15 (build="tsc -b && vite build" vs type-check="tsc --noEmit")
  - idt_front/src/hooks/useLlmModels.ts:22 (select: (data) => data.models)
  - docs/archive/2026-08/agent-create-entry/agent-create-entry.report.md (§1.4 QC-1~3, §6.2)
  - docs/archive/2026-08/intent-analyzer/intent-analyzer.report.md (SC-2 baseline 58건, §6.2)
  - docs/archive/2026-08/tool-recommender/tool-recommender.report.md (§6.1 픽스처가 설계 가정을 따라간 사례)
  - docs/archive/2026-08/prompt-composer/prompt-composer.analysis.md (SC-01 — FAILED 목록 byte-identical 대조)
confidence: 0.85
version: 2
created: 2026-08-14
updated: 2026-08-18
verified_at: 7c3ffdd
---

# 거짓 초록 — 통과했는데 검증되지 않은 품질 게이트 4종

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

> **관행**: MSW 핸들러는 **대응 훅의 `select`/응답 타입을 먼저 확인**하고 작성한다.
> 데이터 형태를 다루는 로직의 픽스처는 **실제 데이터 표본 1건**에서 뜬다.

### 5. 커버리지는 Check가 아니라 Do 종료 조건이어야 한다

Do에서 ruff·pytest만 돌리고 넘어가, 설계 이탈로 추가한 코드 13 stmts가 통째로
미검증인 채 Check까지 갔다. 커버리지를 재자 갭 2건이 즉시 드러났고, 해소는
**프로덕션 코드 무수정 + 테스트 추가**만으로 끝났다.

관련: 설계 이탈 항목을 추가할 때 테스트를 같이 늘리지 않는 것이 직접 원인이었다 —
"이탈 항목 → 대응 테스트" 2열 표를 Do 산출물로 만들면 이탈을 적는 순간 테스트도 적게 된다.

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

## 관련 문서

- 이월 처리 방침: `conventions/explicit-gap-carryover.md`
- 수동 검증 목록: `ops/e2e-carryover-checklist.md`
- 뮤테이션 버튼 가드 테스트의 위양성: `frontend/patterns/loading-button-pending-guard.md`
