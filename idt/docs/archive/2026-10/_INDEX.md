# Archive Index — 2026-10

> 이 디렉토리는 PDCA 사이클이 완료된 피처 문서를 보관합니다.

| 피처 | 완료일 | Match Rate | 테스트 | 경로 |
|------|--------|-----------|--------|------|
| subagent-context-scope | 2026-10-04 | 100% (최초 98.8% → Minor G1·G2·G5 해소 · Structural/Contract/Runtime 100 · Critical 0 · Important 0 · 수용 Minor G3·G4 · 이터레이션 0 · SC 7/7 · FR 12/12(FR-10~12 Do 중 승인 추가)) | 신규 72(Policy 31 · Strategy 15 · SessionScoped 어댑터 10 · 컴파일러 C0~C6+C4b 8 · name 정규화 6 · 배선 계약 2) · 전체 백엔드 53 failed / 10289 passed — **master 기준선과 실패 목록 동일(신규 0)** · L3 실런 3/3(gpt-5.1, run `41cc2367`·`d6b5affc`) · PR #65 | `subagent-context-scope/` — **서브에이전트 입력을 `[원 질문]+[참고 자료(최신 우선 4000자)]+[현재 작업(+재시도 사유)]`로 조립**(domain `SubAgentContextPolicy` + application `SubAgentContextStrategy`, `resolve_strategy()`=연결별 context_mode 확장 지점). ★ 조사 중 **서브에이전트 런타임이 운영에서 한 번도 동작한 적 없음** 발견 — 3중 차단: FR-11 앱 싱글톤 `WorkflowCompiler`에 `agent_repository` 미주입(도입 이후, compile 단계 ValueError) → FR-10 `function_node_ids` 누락으로 `_wrap_worker`가 함수에 `.ainvoke`(회귀 `3a25eb7`) → FR-12 worker_id 공백이 OpenAI `messages[].name` 패턴 위반(서브 다음 supervisor 400·조기 종료). ★ 단위·통합 테스트가 모두 초록이었는데 FR-11·12는 **L3 실런에서만** 드러남 — 기존 테스트는 `_compile_sub_agent`를 AsyncMock으로 대체해 실제 노드 경로를 한 번도 안 탔다. ★ `quality_gate_enabled`는 운영 경로에서 항상 False — FR-05(QG 재시도 입력)는 QG 활성 시에만 실효. ★ 범위 밖 후속: 자식 그래프 step이 부모 run에 `supervisor` 이름으로 섞여 기록(음수 latency), 연결별 context_mode, 실행 시점 권한 재확인 |
