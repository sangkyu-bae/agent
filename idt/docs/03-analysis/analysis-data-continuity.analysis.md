# analysis-data-continuity Gap Analysis

> **Feature**: analysis-data-continuity
> **Date**: 2026-07-06
> **Phase**: Check (Design ↔ Implementation Gap Analysis)
> **Design Doc**: [analysis-data-continuity.design.md](../02-design/features/analysis-data-continuity.design.md)
> **Match Rate**: **96%**

---

## 1. 요약

Design §3 D1~D8 전 항목이 구현되었고, §5 Test Plan T1~T7이 실제 테스트(38건)로 커버된다.
Plan §5 리스크와 3대 compact 공존 제약이 코드로 모두 지켜진다. 미충족 항목은 **라이브 E2E
시나리오 검증(§5, DB 마이그레이션 적용 후 수동/통합)** 1건으로, Do→Check 경계의 필연적 잔여
항목이다. 코드/구조 차원 Gap은 없다.

---

## 2. D 항목별 대조 (Design §3)

| ID | 설계 요구 | 구현 위치 | 상태 |
|----|-----------|-----------|------|
| D1 | `AnalysisSnapshotPolicy`(build/select_recent/render_reinjection_body/render_context_block/is_reinjected) + 엔티티 `analysis_data` 필드 + 빈 items 거부 | `src/domain/conversation/analysis_snapshot_policy.py`, `entities.py:59,65-66` | ✅ 완전 |
| D2 | V039 마이그레이션 + 모델/매퍼 왕복 | `db/migration/V039__...sql`, `models/conversation.py:32`, `mappers/conversation_mapper.py` (양방향) | ✅ 완전 |
| D3 | 턴 종료 시 검색결과/엑셀 산출 수집(재주입분 제외) | `run_agent_use_case.py` `_collect_snapshot`/`_snapshot_items` (L737-772) | ✅ 완전 |
| D4 | 후속 턴 검색결과 규약 AIMessage 재주입(전체 히스토리 스캔, 비영속) | `run_agent_use_case.py` `_inject_snapshot_messages`/`_build_messages` (L774-829) | ✅ 완전 |
| D5 | supervisor `[보유 분석 데이터]` 인지 블록 | `supervisor_nodes.py` `_render_data_context_block`/`_summarize_data_entry` + decision_prompt 삽입 | ✅ 완전 |
| D6 | 분석 노드 부족-명시 규약 | `analysis_prompt.py` `DATA_GAP_GUIDE` + `workflow_compiler.py` `_analyze_context` 삽입 | ✅ 완전 |
| D7 | General Chat 수집(제외목록)/복원(system 블록)/차트 컨텍스트 폴백/시스템 프롬프트 | `general_chat/use_case.py` `_collect_snapshot`/`_snapshot_block`/`_snapshot_context_messages`/`_maybe_build_charts`/`_persist_messages` | ✅ 완전 |
| D8 | config 4개 + main.py DI(두 UseCase, 미주입 시 비활성) | `config.py:90-99`(analysis_snapshot_*), `main.py` `_make_analysis_snapshot_policy`/`_analysis_snapshot_excluded_tools` + 양쪽 주입 | ✅ 완전 |
| §4 | 규칙 문서 개정 | `docs/rules/conversation-memory.md` 스냅샷 채널 조항 추가 | ✅ 완전 |

---

## 3. Test Plan 대조 (Design §5)

| T | 대상 | 파일 | 상태 |
|---|------|------|------|
| T1 | 정책 build/select_recent/marker/render | `tests/domain/conversation/test_analysis_snapshot_policy.py` | ✅ |
| T2 | 엔티티 analysis_data 검증 | 〃 `TestEntityAnalysisData` | ✅ |
| T3 | 매퍼 왕복(None/dict) | `tests/infrastructure/persistence/test_conversation_mapper.py` | ✅ |
| T4 | agent 수집(검색/엑셀/재캡처 제외/예외/미주입) | `tests/application/agent_builder/test_run_agent_snapshot.py` `TestSnapshotCollect` | ✅ |
| T5 | agent 재주입(규약/요약경로/미존재) | 〃 `TestSnapshotReinject` | ✅ |
| T6 | supervisor 블록 + 분석 프롬프트 지시 | `tests/application/agent_builder/test_supervisor_data_context.py` | ✅ |
| T7 | General Chat 수집/복원/차트폴백/하위호환 | `tests/application/general_chat/test_use_case_snapshot.py` | ✅ |
| T8 | 회귀 | 수동 실행 — agent_builder 388 / general_chat·conversation·visualization·mapper 145 / persistence 99 통과 | ✅ |
| — | **라이브 E2E 시나리오**(턴1→턴2 재사용/재수집, 7메시지 요약 후) | **미수행** (DB 마이그레이션 적용 + 실 LLM 필요) | ⚠️ 미충족 |

신규 테스트 격리 실행: **38 passed**.

---

## 4. Plan 3대 compact 공존 제약 검증 (집중 확인)

| 제약 | 코드 근거 | 판정 |
|------|-----------|------|
| ① 전체 히스토리 스캔 복원(최근 윈도우 비의존) | `_inject_snapshot_messages`가 `select_recent(existing)` 호출 — existing은 세션 전체. `select_recent`은 turn_index 역순 전체 스캔 | ✅ |
| ② summarizer 입력 미포함 + 재주입 비영속 | summarizer는 `get_turns_to_summarize`(ConversationMessage.content만) 입력. 재주입 메시지는 `_build_messages` 산출물로 graph에만 전달, `save` 미호출 | ✅ |
| ③ compact 후 총량 기준 상한 | `select_recent`에 total_max_chars 누적 컷 + `build_snapshot` 항목/총량 절단. config 기본 8k(=요약512+최근3+스냅샷 기준) | ✅ |

---

## 5. Plan §5 리스크 해소 확인 (Design §7 매핑)

| 리스크 | 해소 코드 | 판정 |
|--------|-----------|------|
| 토큰 비대 | 항목4k/총량8k/보존2 config + supervisor 블록은 요약만(본문 미포함) | ✅ |
| 메모리 정책 금지 조항 | 요약 규칙 무변경, `conversation-memory.md` 개정으로 정식화 | ✅ |
| supervisor 분석 직행 | `_render_data_context_block` + `DATA_GAP_GUIDE` 2중 안전망 | ✅ |
| 저장 실패 전파 | `_collect_snapshot` try/except → None + logger.error | ✅ |
| 데이터성 판별 모호 | agent: `is_search_result` 규약 / chat: 제외목록 config — 판별 LLM 없음 | ✅ |
| 요약본-스냅샷 착각 | 인지 블록이 state 실보유분만 나열 | ✅ |

---

## 6. Gap 목록

| # | Gap | 심각도 | 유형 | 조치 |
|---|-----|--------|------|------|
| G1 | 라이브 E2E 시나리오 미검증 (재현: 턴1 "나의 휴가데이터 그래프" → 턴2 "전체 사용자") | Low | 검증 경계 | V039 마이그레이션 적용 후 실 서버에서 QA. 단위/통합 테스트로 로직은 이미 보증됨 |
| G2 | 엑셀 kind 항목이 재주입 시 `format_search_result`로 감싸져 "검색결과"로 인식됨(kind 구분 소실) | Info | 설계 의도 내 | 분석 노드 무수정 목표(§3.4)에 부합 — 의도된 동작, 조치 불요 |
| G3 | Design §3.1 원안의 `render_scope_lines`가 구현에서 `render_context_block`(chat) + supervisor 직접 요약(§3.5)으로 분리됨 | Info | Do 중 설계 정합 | Design 문서 Do 단계에서 이미 반영(정합 완료) |

**코드/구조 차원 미충족 Gap: 0건.**

---

## 7. Match Rate 산정

| 항목 | 가중 | 달성 |
|------|------|------|
| D1~D8 구현 (8) | 80% | 80% |
| Test Plan T1~T8 (8) | 16% | 16% |
| 라이브 E2E 시나리오 | 4% | 0% |
| **합계** | **100%** | **96%** |

> 90% 이상 — Report 단계 진입 가능. 잔여 4%는 코드 수정이 아니라 배포 후 실행 검증 항목.

---

## 8. Next Steps

1. (배포 시) V039 마이그레이션 적용 → 실 서버에서 G1 재현 시나리오 QA
2. `/pdca report analysis-data-continuity` — 완료 보고서 생성
3. (선택) LangSmith 실측으로 스냅샷 상한(8k) 재조정 검토 — Design §3.8 명시
