# SUPERVISOR-ATTACHMENT-ROUTING: 완료 보고서

> 상태: Completed
> 연관 Task: SUP-ATTACH-001
> 작성일: 2026-06-07
> Match Rate: 100%

---

## Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| Feature | supervisor-attachment-routing |
| 대상 에이전트 | `0605a131-06e4-4bb6-9df3-488e2f707ac9` (agent_tool.tool_id = `data_analysis`) |
| 기간 | 2026-06-07 (Plan→Design→Do→Check→Report 단일 세션) |
| 우선순위 | Critical |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| Match Rate | 100% (설계 18/18, 테스트 5/5+잉여1, 아키텍처 7/7) |
| 변경 파일 | 3개 구현 + 1개 테스트(신규) |
| 신규 테스트 | 14개 (TC-1~TC-5), 격리 실행 11 passed |
| 회귀 검증 | supervisor/hooks/compiler/analysis 80 passed |
| 반복(iterate) | 0회 (1차 Check에서 100% 달성) |

### 1.3 Value Delivered

| 관점 | 전달된 가치 (실측) |
|------|-------------------|
| **Problem** | 엑셀 첨부 + 데이터 질의 시 supervisor가 `FINISH`+"권한 없음"으로 거부하고 `analysis_node`에 진입조차 못 하던 치명 결함 → **해소**. |
| **Solution** | supervisor 의사결정의 첨부 정보 비대칭을 ① prompt 첨부 인지 블록 ② `AttachmentRoutingHooks` 결정적 강제 라우팅 ③ 거부 억제 지시로 이중 차단. 아키텍처/시그니처/DB/API **무변경**. |
| **Function UX Effect** | 엑셀 첨부 분석 질의가 LLM 거부 없이 `analysis_node → ExcelAnalysisWorkflow`로 결정적 진입(LLM 우회, `force_worker`). 단위 테스트로 거부 시나리오(FINISH 의도)에서도 라우팅됨을 검증. |
| **Core Value** | 첨부 기반 데이터 분석 기능의 **end-to-end 동작 회복**. "도구가 있는데 권한 없다고 거부"하는 신뢰 손상 제거. |

---

## 2. PDCA 사이클 요약

| Phase | 산출물 | 결과 |
|-------|--------|------|
| Plan | `docs/01-plan/features/supervisor-attachment-routing.plan.md` | 근본원인 5분류(2-1~2-5) + 수정범위 |
| Design | `docs/02-design/features/supervisor-attachment-routing.design.md` | C-1/C-2/C-3 최소변경 명세 + TC-1~TC-6 |
| Do | 구현 3파일 + 테스트 1파일 | TDD RED→GREEN, 80 passed |
| Check | `docs/03-analysis/supervisor-attachment-routing.analysis.md` | Match Rate 100%, Gap 1건(Low) |
| Report | 본 문서 | 완료 |

---

## 3. 근본 원인 → 해결 매핑

| 근본원인 (Plan) | 해결 (Do) |
|-----------------|-----------|
| 2-1 supervisor가 `state["attachments"]` 미인지 | C-1 `_render_attachment_block` + prompt 주입 |
| 2-2 `FINISH+answer` 단락으로 워커 미호출 | C-2 `force_worker` 결정적 라우팅(LLM 우회) |
| 2-3 첨부 결정적 라우팅 훅 부재 | C-2 `AttachmentRoutingHooks` |
| 2-4 거부 억제/라우팅 우선 지시 부재 | C-1 prompt 문구("거부하지 말고", FINISH 축소) |
| 2-5 차트 렌더링(그래프) supervisor 경로 미지원 | **범위 외** — 후속 이슈로 분리 |

---

## 4. 변경 파일

| 파일 | 변경 |
|------|------|
| `src/application/agent_builder/supervisor_hooks.py` | `AttachmentRoutingHooks` 추가 (DefaultHooks 보존) |
| `src/application/agent_builder/supervisor_nodes.py` | `_render_attachment_block` 헬퍼 + decision prompt 수정 |
| `src/application/agent_builder/workflow_compiler.py` | import + compile() 훅 연결 |
| `tests/application/agent_builder/test_supervisor_attachment.py` | 신규 TC-1~TC-5 (14개) |

---

## 5. 미해결 / 후속 이슈

| # | 항목 | 비고 |
|---|------|------|
| F-1 | supervisor 경로 **차트 렌더링** | `chart_router → chart_builder` + conditional edge 필요. 현재 차트는 General Chat 전용(메모리 `chart-rendering-general-chat-only`). 별도 plan. |
| F-2 | "내 남은 휴가일수" **도메인 결합** | auth_ctx ↔ 엑셀 행(사번/이메일) 매핑 별도 설계 |
| F-3 | TC-6 **컴파일러 통합 테스트** | Check Gap G-1(Low). end-to-end 보강 시 추가 |
| F-4 | attachment dict **file_name 보강** | ws_router resolve 단계, 인지 블록 가독성 |
| F-5 | 강제 라우팅 첨부 **타입 확장** | `_ROUTABLE_TYPES`에 CSV 등 추가 |

---

## 6. 검증 권장 (배포 전)

- dev 서버에서 대상 에이전트(`0605a131…`)로 엑셀 첨부 + 휴가 질의 수동 1회 재현 → `analysis_node` 진입 + 분석 답변 확인.
- 윈도우 이벤트루프 flakiness 대비 테스트 파일 격리 실행(메모리 `backend-test-eventloop-flakiness`).
