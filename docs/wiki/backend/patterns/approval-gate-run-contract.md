---
title: 승인 게이트 런 계약 — fail-closed 기본 게이트·게이트 직후 종료·결정적 답변
status: approved
source_type: conversation
source_refs:
  - idt/docs/04-report/approval-gate-run-termination.report.md (§1.3, §1.5 Act-1/Act-2, §6)
  - 커밋 72b3632 (승인 게이트 런 종료 + 초안·답변 근거 판정 재작성 루프)
  - 커밋 dc14bdd (승인 필요 도구 배지 + draft_arg_key 입력)
  - idt/src/domain/approval/policies.py (ApprovalPolicy.effective_gate)
  - idt/src/domain/approval/notice_policy.py (ApprovalPendingNoticePolicy)
  - idt/src/application/agent_builder/supervisor_nodes.py (route_after_gated_worker, GatedWorkerHintPolicy 안내)
  - idt/src/application/agent_builder/action_pipeline.py (_assemble_arguments, _schema_without — 본문 키 제외)
  - idt/src/application/agent_builder/workflow_compiler.py (gated_worker_ids·sub_agent_worker_ids 조건부 간선)
  - idt/tests/application/agent_builder/test_gated_run_termination.py, test_gated_compile.py
  - idt/src/domain/agent_builder/policies.py GatedCategoryPolicy.promote (v2 — 암묵 승격 implicit=True)
  - idt/src/application/agent_builder/workflow_compiler.py (v2 — action 노드 None 시 암묵은 react 폴백, 명시는 failed_worker_ids)
  - docs/archive/2026-11/firewall-admin-console/firewall-admin-console.analysis.md · report.md (§4.1, §6.2 — block_ip에 action 지정 시 워커 제외) (v2)
  - docs/firewall-admin-setup.md (5-3 "카테고리는 미분류로 둔다") (v2)
  - docs/archive/2026-11/firewall-admin-console/firewall-admin-console.design.md (v0.5 — 승인 API가 재개까지 기다려 30초 초과) (v2)
confidence: 0.85
version: 2
created: 2026-10-06
updated: 2026-11-27
reviewer: 배상규
verified_at: bcf64b0
---

> v2 (2026-11-27): §6(본문 인자 없는 승인 도구에 `action` 명시 금지), §7(승인 API 응답 지연) 추가. 에이전트 갱신이라 approved → draft 강등.

# 승인 게이트 런 계약

## 문제

승인 필요(부작용) 도구가 붙은 에이전트에서 실측(2026-09-29)된 결함 5종:

1. 게이트가 차단한 뒤 그래프가 supervisor로 돌아가 **같은 워커를 최대 5회 반복 호출**.
2. 워커 LLM이 **지어낸 "성공 JSON"이 채팅 답변으로 저장**(실제 MCP 결과는 `reply: null`).
3. 도구 원문 설명("승인 전에 호출하지 마십시오")이 이겨서 "등록해줘"에도 **도구 미호출**.
4. 에이전트에 게이트 미들웨어 설정이 없으면 승인 필요 도구가 **무승인 실행**.
5. 미분류·search·collect 워커에 붙은 승인 필요 도구는 게이트 부착 판정에서 빠져 있었다(Act-2 G2).

## 검증된 사실

### 1. 게이트는 fail-closed — 설정 누락이 무승인 부작용이 되면 안 된다

- `ApprovalPolicy.effective_gate(applied, has_gated_workers=...)`: 적용 목록에 게이트가 **없어도**
  승인 필요 도구 워커가 있으면 도메인 기본 게이트(`GateSettings.from_config({})`)를 쓴다.
  기본값이 승인 측 해석과 같아 적재·승인이 자동 일치한다. 명시적 `off` 는 존중.
- 승인 필요 도구는 **노드 종류와 무관하게** 게이트 아래 있어야 한다. 미분류·search·collect에
  붙은 경우 초안 작성 노드(action)로 승격하고, 실패하면 react + 게이트로 폴백한다.
- 교훈: "모든 노드 종류 × 게이트 부착" 교차표를 Design에 두지 않아 기존 무승인 경로를 gap 분석에서야 발견했다.

### 2. 게이트 워커 직후 조건부 END — 되돌아가면 LLM이 성공을 지어낸다

- `route_after_gated_worker`: state에 `approval_pending` 이 오르면 supervisor·quality_gate
  재진입 없이 `END`. 런당 pending 1건 불변식의 **구조적** 강제다.
- 조건부 간선은 게이트 워커와 **서브에이전트 워커에만** 붙는다(자식 런의 승인 신호를 부모가 미리
  모르므로). 비게이트 그래프의 간선은 바이트 동일 — 회귀 0의 근거.

### 3. 승인 대기 런의 답변은 결정적 템플릿 — LLM 생성 금지

- `ApprovalPendingNoticePolicy.render()`: "담당자 승인함에 올렸습니다. 아직 실행되지 않았습니다"
  + 작업명 + 초안 미리보기(300자). 워커가 무엇을 출력했든 답변을 덮는다(`stream()` 1곳).
- 핵심 가치: **"시스템이 말하는 상태 = 실제 상태"**. 부작용 경로의 상태 보고는 LLM에 맡기지 않는다.

### 4. LLM이 읽는 문구는 서로 경쟁한다 — 접두 안내만으로는 도구 원문을 못 이긴다

- 플랫폼 안내를 도구 설명 **접두**로만 넣었을 때 L3 0/1 → **접미 + supervisor `[승인 게이트 규칙]`
  블록**을 추가해 3/3 호출로 전환(Act-1).
- [Supervisor 계약 §2](supervisor-graph-contracts.md)의 "목록 프레이밍이 방어 지시를 이긴다"와 같은 계열:
  프롬프트 효과는 **경쟁 문구(도구 원문 설명 등)와의 충돌**을 Risk로 적고 L3로 확인해야 한다.

### 5. "하지 말라"는 지시 대신 입력에서 제거한다

- 보조 LLM(인자 조립)에게 "본문 필드는 비워 두라"고 지시하는 설계가 실패(파싱 실패로 요청 소실, G1).
- 해결: `_schema_without(schema, draft_key)` 로 **스키마에서 본문 키를 제거**하고 파싱 실패만 재시도
  (`grounded=false` 는 정보 부족이라 재시도 안 함). L3 3/3, 재시도 0회.
- 본문 키는 `draft_arg_key`(기존 필드 재사용, 스키마 변경 0)로 지정한다 — 빌더 UI에 `본문 인자` 입력.

### 6. 본문 인자가 없는 승인 필요 도구에 `action` 카테고리를 **명시**하면 워커가 사라진다 (v2)

- 승격 경로와 명시 경로의 실패 처리가 다르다(`workflow_compiler.py`):
  - **미분류·search·collect + 승인 필요** → `GatedCategoryPolicy.promote`가 `("action", implicit=True)`로 승격.
    본문 키를 정할 수 없으면(초안 작성 노드 생성 실패) **react + 게이트로 폴백**한다.
  - **관리자가 `action`을 명시** → 같은 실패에서 **워커를 격리**(`failed_worker_ids`, fail-closed)한다. 그래프에서 워커가 빠진다.
- 실측(firewall-admin-console, `block_ip`): 차단 도구는 IP·TTL만 받고 초안 본문 인자가 없다. `action`을 지정하자 워커가
  실행에서 빠졌고, 에이전트는 **호출하지 않은 도구를 호출했다고 답했다**. 미분류로 바꾸자 react + 게이트로 정상 승인 요청이 올라왔다.
- 규칙: 승인 필요 MCP 도구는 **본문(초안)으로 보낼 인자가 있을 때만 `action`**(`draft_arg_key` 지정)으로, 그 외에는 **카테고리를 미분류로 둔다**.

### 7. 승인 API는 재개까지 기다린다 — 30초를 넘길 수 있다 (v2)

- 승인 결정 API는 승인 후 에이전트 재개·도구 집행이 끝날 때까지 응답을 잡고 있어 30초를 넘길 수 있다.
  프론트는 응답을 못 받으면(status 0) 실패로 단정하지 말고 "처리됐을 수 있음"으로 안내한 뒤 **목록을 다시 조회**한다
  (firewall-admin-console 승인 탭, 실건 승인에서 발견).
- 승인 즉시 응답 + 재개 비동기 분리는 후속 후보(Medium)로 남아 있다. 바뀌면 이 절을 갱신한다.

## 다음에 적용하는 법

1. 부작용 도구를 다루는 새 노드/워커 유형을 추가하면 `effective_gate` 경로를 타는지, 그리고
   **노드 종류 × 게이트 부착 표**에서 빈칸이 없는지 먼저 확인한다.
2. 상태를 사용자에게 알리는 문구(승인 대기·실행 안 됨 등)는 domain 템플릿 정책으로 만든다.
3. 게이트 신호를 내는 워커를 새로 만들면 직후 간선을 `route_after_gated_worker` 조건부로 둔다.
4. 프롬프트 계층 변경은 **L3 최소 3회**를 Do 완료 조건에 넣는다(단위 테스트 전부 초록 상태에서 L3가 결함 2건을 드러냈다).
5. LLM 제약은 지시문보다 **입력·스키마에서 불가능하게 만드는 쪽**을 기본으로 한다
   ([LLM 출력 신뢰 경계](llm-output-trust-boundary.md)와 같은 방향).
6. (v2) 승인 필요 도구를 등록할 때 본문 인자가 없으면 카테고리는 **미분류**. "에이전트가 도구를 호출했다는데 승인 요청이 없다"면
   먼저 그 도구의 카테고리가 `action`인지 본다.
7. (v2) 승인·거절 버튼의 응답 처리에 **타임아웃 = 미확정** 분기를 둔다.

## 관련 문서

- [Supervisor 그래프 계약](supervisor-graph-contracts.md) §5(c) — 서브에이전트 직후 조건부 간선
- [근거 판정 재작성 루프](grounding-rewrite-loop.md) — 승인 초안이 통과하는 근거 판정
