# SUPERVISOR-ATTACHMENT-ROUTING: 갭 분석 (Check)

> 상태: Check
> Design 참조: docs/02-design/features/supervisor-attachment-routing.design.md
> Plan 참조: docs/01-plan/features/supervisor-attachment-routing.plan.md
> 연관 Task: SUP-ATTACH-001
> 작성일: 2026-06-07
> **Match Rate: 100%** (설계 명시 범위 기준)

---

## 1. 분석 개요

| 항목 | 값 |
|------|-----|
| 구현 파일 | `src/application/agent_builder/{supervisor_hooks.py, supervisor_nodes.py, workflow_compiler.py}` |
| 테스트 | `tests/application/agent_builder/test_supervisor_attachment.py` |
| 검증 결과 | supervisor_attachment + supervisor_nodes + supervisor_hooks 39 passed / workflow_compiler + sub_agent + analysis_node 41 passed |

---

## 2. 설계 항목별 대조 (C-1 / C-2 / C-3)

| 설계 항목 | 설계 §  | 구현 위치 | 상태 |
|-----------|--------|-----------|:----:|
| `_render_attachment_block` 모듈 헬퍼(순수 함수) | §3-3 | `supervisor_nodes.py:14-31` | ✅ Match |
| - empty/None → `""` | §3-3 | `if not attachments: return ""` | ✅ |
| - file_name 있으면 `kind(name)`, 없으면 `kind`만(임시경로 비노출) | §3-2, §3-4 | line 22-25 | ✅ |
| - 블록 문구 `[첨부된 데이터]` + `거부하지 말고 반드시 그 워커로 라우팅` | §3-3 | line 27-31 | ✅ |
| decision prompt에 첨부 블록 주입 | §3-2 | `supervisor_nodes.py` prompt 조립 | ✅ |
| 거부 억제 문구(`처리 가능한 워커가...거부하지 말고`) | §3-2 | prompt line | ✅ |
| FINISH 축소(`어떤 워커로도 처리할 수 없을 때만 FINISH`) | §3-2 | prompt line | ✅ |
| `AttachmentRoutingHooks` 신규(DefaultHooks 보존) | §2-2 | `supervisor_hooks.py:20-50` (DefaultHooks 12-17 유지) | ✅ |
| `_ROUTABLE_TYPES = ("excel",)` | §2-2 | line 29 | ✅ |
| `force_worker`: 빈 analysis_worker_ids → None | §2-2 | line 35-36 | ✅ |
| `force_worker`: routable 첨부 없음 → None | §2-2 | line 37-42 | ✅ |
| `force_worker`: `last_worker_id == target` 가드 → None | §2-2 | line 44-46 | ✅ |
| `force_worker`: else → `analysis_worker_ids[0]` | §2-2 | line 43, 47 | ✅ |
| `skip_workers` → `[]` | §2-2 | line 49-50 | ✅ |
| 컴파일러: `isinstance(DefaultHooks)` + analysis_worker_ids 가드 | §4-2 | `workflow_compiler.py` compile() | ✅ |
| 컴파일러: `AttachmentRoutingHooks(sorted(...))` | §4-2 | compile() | ✅ |
| 컴파일러: `effective_hooks`를 create_supervisor_node에 전달 | §4-2 | compile() | ✅ |
| import 추가 | §4-3 | `workflow_compiler.py:7-11` | ✅ |

**중요 정합성 포인트**: `analysis_worker_ids`는 `set`(workflow_compiler.py:140,170)이므로 `sorted()`가 `[0]` 결정성 보장에 필수 — 설계·구현 모두 정확히 처리됨.

---

## 3. 테스트 커버리지 (TC-1 ~ TC-6)

| TC | 설계 의도 | 구현 | 상태 |
|----|----------|------|:----:|
| TC-1 | `_render_attachment_block` (excel/empty/no-filename) | `TestRenderAttachmentBlock` (3) | ✅ |
| TC-2 | `force_worker` 4분기 | `TestAttachmentRoutingHooks` | ✅ + 추가 |
| TC-3 | force 시 LLM 우회 + analysis 라우팅 | `test_force_skips_llm_and_routes` | ✅ |
| TC-4 | DefaultHooks 경로 prompt 블록 주입 | `test_includes_attachment_block_in_prompt` | ✅ |
| TC-5 | 첨부 없을 때 회귀(FINISH 보존, 블록 미삽입) | `test_no_attachment_behaves_as_before` | ✅ |
| TC-6 | 컴파일러 통합(graph가 analysis_node 진입) | **미구현** | ⚠️ 의도된 갭 |

- **TC-2 잉여**: `test_skip_workers_empty` 추가(가산적, 충돌 없음).
- **TC-3 검증 방식 차이(비이슈)**: 설계 `call_count == 0` → 구현 `with_structured_output.assert_not_called()`. 의미상 동등(더 강함).
- **TC-4/5 헬퍼 차이(비이슈)**: 설계 `_FakeStructuredLLM` → 구현 `MagicMock` + `ainvoke.call_args.args[0]`. 동일 검증 대상.

---

## 4. 아키텍처/시그니처 불변 제약 (설계 §7)

| 제약 | 판정 |
|------|:----:|
| `create_supervisor_node` 시그니처 불변 | ✅ Pass |
| `SupervisorHooks` 프로토콜 불변 | ✅ Pass |
| `DefaultHooks` 보존 | ✅ Pass |
| 외부 주입 hooks 존중(`isinstance(DefaultHooks)` 게이트) | ✅ Pass |
| 첨부 없는 경로 불변(block="", force=None) | ✅ Pass (TC-5) |
| DB 스키마/API 스펙 변경 없음 | ✅ Pass |
| CLAUDE.md §3 함수 길이/헬퍼 분리 | ✅ Pass |

위반 없음.

---

## 5. 점수 요약

```
Overall Match Rate: 100%
  설계 일치 (C-1/C-2/C-3): 100% (18/18)
  테스트 일치 (TC-1~TC-5): 100% (5/5 + 잉여 1)
  TC-6 (통합):             의도적 보류 (설계상 pseudocode stub)
  아키텍처 준수:            100% (7/7)
```

---

## 6. Gap 목록

| # | 유형 | 항목 | 심각도 | 비고 |
|---|------|------|:------:|------|
| G-1 | 커버리지(의도적) | TC-6 컴파일러 통합 테스트 부재 | Low | 설계가 TC-6을 pseudocode로만 제시. 단위 우회(TC-3) + 컴파일러 결선(정적 검증)으로 경로는 이미 커버. |

---

## 7. 권장 조치

**선택(보고서 진행 비차단)**:
1. end-to-end 보강이 필요하면 TC-6 구현 — `data_analysis` 워커 + 엑셀 첨부가 컴파일된 그래프에서 실제 `analysis_node`에 도달하는지 `last_worker_id`로 검증(설계 §5에 가짜 ExcelAnalysisWorkflow getter 방식 스케치 존재).
2. dev 서버에서 대상 에이전트(`0605a131…`)로 엑셀 첨부 수동 1회 재현.

**설계 문서 갱신 불필요** — 구현이 설계와 일치. 잉여 `test_skip_workers_empty`는 설계 §5 TC-2에 백필하면 완전하나 불일치는 아님.

**판정**: Match Rate ≥ 90% → `/pdca report supervisor-attachment-routing` 진행 가능. 윈도우 이벤트루프 flakiness 대비 테스트 파일 격리 실행 권장.
