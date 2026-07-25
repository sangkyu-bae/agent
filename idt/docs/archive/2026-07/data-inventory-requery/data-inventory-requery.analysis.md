# Design-Implementation Gap Analysis — data-inventory-requery

> **Target**: 시각화 강제 라우팅 재주입분 오탐 제거 (D1~D5)
> **Design**: `docs/02-design/features/data-inventory-requery.design.md`
> **Plan**: `docs/01-plan/features/data-inventory-requery.plan.md`
> **Analysis Date**: 2026-07-23
> **Analyzer**: gap-detector

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match (D1~D5) | 100% | ✅ |
| Test Spec Mapping (§7.1) | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| **Overall (E2E 제외)** | **100%** | ✅ |

---

## 항목별 판정

| # | 항목 | 판정 | 근거 파일:라인 | 비고 |
|---|------|:----:|----------------|------|
| 1 | D1 extract_reinjected_question — 왕복/괄호 보존/비재주입·형식불일치→"" | **Match** | `analysis_snapshot_policy.py:180-198` / 테스트 `test_analysis_snapshot_policy.py:184-209` | `is_reinjected` 가드 1단(중첩 준수), `tail.endswith(")")`로 마지막 괄호만 절단 → 괄호 포함 질문 보존 |
| 2 | D2 재주입분 트리거 제외 (is_reinjected 재사용·마커 미재정의·엑셀/viz_done/last_worker 가드 불변) | **Match** | `supervisor_hooks.py:14-21,94-106` (제외); `:66-78` (가드); `:80-82` (엑셀 불변) | 마커는 domain에서 import(이중 출처 없음), `_is_current_turn_search_result` 헬퍼로 40줄 회피 |
| 3 | D3 인벤토리 렌더 — 라벨/원 질문/마커 head 스킵/순회 지시+substring/1줄 | **Match** | `supervisor_nodes.py:42-91` | `_entry_head`가 `body_lines[1:]`로 재주입 마커 라인 건너뜀(:44), `범위를 벗어나면`·`검색 워커` 보존(:89-90), head `[:80]` 1줄 본문 미포함 |
| 4 | D4 스냅샷 저장/선별/재주입 코드 무변경 | **Match** | `run_agent_use_case.py:860-899` (기존 `is_reinjected`/`render_reinjection_body`/`select_recent`만 사용); `analysis_snapshot_policy.py` 기존 메서드 무변경 | `extract_reinjected_question`은 additive, D3 렌더에서만 소비 — 누적 경로 미접촉 |
| 5 | D5 optional logger 기본 None + 배선 + skip 로그 조건 | **Match** | `supervisor_hooks.py:57,63,100-105`; `workflow_compiler.py:273-276` | skip 로그 = `not has_current AND logger AND any(is_search_result)` = "검색결과 존재+전부 재주입"에만 info |
| 6 | FR-06/07 E2E 수동 검증 | **N/A (이월)** | Plan §3.1 FR-06/07, Design §7~8 | 코드 검증 불가 — 분모 제외. 3턴 시나리오(범위확대→search 경유 / 동일범위→재검색 없음) 실측 필요 |
| 7 | §7.1 TC 목록 ↔ 테스트 1:1 대응 | **Match** | 아래 매핑표 | 전 TC 존재, TC-A3b/TC-B2b 보너스 커버 |
| 8 | 코딩 규칙 (40줄/if 2단/하드코딩 config) | **Match** | 변경 함수 전부 ≤22줄, if 중첩 ≤2 | Low: `_entry_head`의 `[:80]` display 리터럴이 명명 상수 아님 |

### §7.1 TC 매핑 (항목 7 상세)

| TC | 설계 | 실제 테스트 | 상태 |
|----|------|------------|:----:|
| TC-A1 | 재주입분만 → force None | `test_tca1_no_force_with_reinjected_only` | ✅ |
| TC-A2 | 재주입분+현재턴 → 강제 | `test_tca2_force_with_reinjected_plus_current` | ✅ |
| TC-A3 | 재주입분만+logger → info 1회 / 미주입 무예외 | `test_tca3_logger_records_skip_reason` (+`test_tca3b`) | ✅ |
| TC-A4 | 재주입분만 → LLM 호출 (TC-8 역방향) | `test_tca4_reinjected_only_reaches_llm` | ✅ |
| TC-B1 | 재주입 항목 [이전 턴 보유]+원 질문 | `test_tcb1_재주입_항목은_이전턴_라벨과_원질문_노출` | ✅ |
| TC-B2 | 현재 턴 [이번 턴 수집]+head (마커 미포함) | `test_tcb2_...` (+`test_tcb2b`) | ✅ |
| TC-B3 | 순회 지시+`범위를 벗어나면`+`검색 워커` | `test_tcb3_순회_판단_지시_포함` | ✅ |
| TC-C1 | 정상/비재주입/형식불일치 | `TestExtractReinjectedQuestion` (4건) | ✅ |
| TC-D1 | 재검색분+이전 스냅샷 select_recent 동반 (기존 커버 확인) | `test_run_agent_snapshot.py` 기존 테스트 | ✅ 설계상 신규 불요 |

픽스처는 §7.1 요구대로 `render_reinjection_body`+`format_search_result` 경유 생성(하드코딩 금지 준수).

---

## Gap 목록

| 심각도 | 설명 | 권고 |
|:------:|------|------|
| Low | `_entry_head`(`supervisor_nodes.py:47`)의 head 절단 길이 `80`이 인라인 매직 리터럴 | ✅ **해소됨** (2026-07-23) — `_ENTRY_HEAD_MAX_CHARS = 80` 모듈 상수화 적용, 관련 테스트 32건 재통과 |

High/Medium Gap 없음.

---

## Match Rate 계산

- 검증 대상: 7개 (항목 6 E2E는 분모 제외)
- Match 7 + 0.5×Partial 0 = 7
- **Match Rate = 7/7 = 100%**
- 이월(E2E): FR-06(범위 확대→search 경유 차트), FR-07(동일 범위→재검색 없음) — `GET /agents/runs/{run_id}` step 실측 필요. 2턴 검색 0건 시 `rag-auth-payload-indexing` 트랙 이관(Plan Out of Scope)

---

## 종합 평가

D1~D5 설계 결정이 구현·테스트에 빠짐없이 반영되었고, §7.1 TC 9종이 실제 테스트와 1:1 대응하며 보너스 케이스(TC-A3b/B2b)까지 커버한다. domain 마커 단일 출처 재사용·additive optional logger·기존 스냅샷 경로 무변경 등 "구조 변경 0" 원칙이 코드에서 확인되며, 유일한 관찰은 head 절단 상수의 인라인 리터럴(Low)로 기능 영향이 없다. 코드 검증 범위에서 Match 100%이므로 Plan 품질기준(≥90%)을 충족하며, 남은 것은 E2E 수동 실측(FR-06/07) 이월뿐이다.

---

## 테스트 실행 결과 (2026-07-23, Do 단계 실측)

- `tests/application/agent_builder/` — 454 passed
- `tests/domain/conversation/` + `tests/application/conversation/` — 75 passed
- `tests/application/agent_run/` — 143 passed
- 신규 테스트 13개 전부 통과, 기존 테스트 무수정 통과
- verify-architecture / verify-logging / verify-tdd — 변경 파일 무위반 (Step3·4 히트는 사전 존재 위반)
