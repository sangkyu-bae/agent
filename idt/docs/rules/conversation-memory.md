# Multi-Turn Conversation Memory Rules

> 원본: CLAUDE.md §7

---

## 기본 원칙

- 모든 대화는 **user_id + session_id** 기준으로 관리한다
- 대화 기록은 **MySQL(RDB)** 에 저장한다
- Vector DB에 대화 원문 저장 ❌ (문서용과 분리)

---

## Conversation Table (개념 설계)

### conversation_message

| 컬럼 | 설명 |
|------|------|
| id (pk) | |
| user_id | |
| session_id | |
| role | user \| assistant |
| content | |
| created_at | |
| turn_index | |

### conversation_summary

| 컬럼 | 설명 |
|------|------|
| user_id | |
| session_id | |
| summary_content | |
| summarized_until_turn | |
| updated_at | |

---

## 요약 트리거 규칙 (강제)

- 한 세션에서 **대화 턴이 6개를 초과하면** → 반드시 **요약을 수행한다**

요약 방식:
1. turn_index 1 ~ N-3 까지 요약
2. 요약 결과를 `conversation_summary`에 저장
3. 기존 메시지는 유지하되, 다음 질의 시 **요약본 + 최근 3턴만 컨텍스트로 사용**

❌ 전체 대화를 그대로 LLM에 전달 금지  
❌ 요약 없이 무한 누적 금지

---

## 요약 정책

- 요약은 사실 중심
- 결정사항 / 사용자 의도 / 중요한 제약 포함
- 질문/답변 스타일 요약 금지

요약은 다음 질문의 **system/context**로만 사용한다.

---

## 차트 메타 컨텍스트 규칙 (D7-rev1, chart-context-continuity 2026-06-10)

`conversation_message.charts`(표시 전용 차트 메타)의 LLM 컨텍스트 투입 규칙:

- ❌ **full config(JSON)는 LLM 컨텍스트에 투입 금지** (토큰 폭증 방지 — 기존 D7 유지)
- ✅ **캡션 1줄만 투입 허용**: charts 부속 assistant 메시지를 컨텍스트로 변환할 때
  `ChartCaptionPolicy`가 생성한 캡션(예: `[생성된 차트: bar "제목" (labels: ... | series: ...)]`,
  메시지당 ≤ 200자)을 content 뒤에 부착한다
- 캡션은 **컨텍스트 윈도우 내에서만** 유효 (전체 컨텍스트 시 전부, 요약 시 최근 3턴)
- ❌ **요약 본문에는 미포함** — summarizer 입력은 content만 사용 (기존과 동일)
- 차트 편집 후속 질문(`ChartFollowupPolicy` EDIT 판정) 시에만 저장된 charts를
  DB에서 로드해 `ChartTransformerInterface` 전용 경로로 처리한다 (일반 컨텍스트 미경유)

> 개정 이력: D7("LLM 컨텍스트 미투입") → D7-rev1("full config 미투입, 캡션은 투입").
> 근거: `docs/02-design/features/chart-context-continuity.design.md` §1/§3.

---

## 분석 데이터 스냅샷 규칙 (analysis-data-continuity 2026-07-06)

`conversation_message.analysis_data`(분석 원천 데이터 스냅샷)의 컨텍스트 투입 규칙:

- ✅ 다음 턴 컨텍스트 빌드 시 최신 N개(config `analysis_snapshot_retention`)를 재주입한다
  (agent: 검색결과 규약 AIMessage / chat: `[이전 분석 데이터]` system 블록).
  **재주입 메시지는 저장하지 않는다** (컨텍스트 빌드 산출물 — compact 이중 비대 루프 차단)
- ✅ 복원은 최근 윈도우가 아니라 **세션 전체 히스토리에서 조회**한다 (요약 발동과 무관)
- ❌ 요약(summarizer) 입력에 포함 금지 — 입력은 content만 사용 (기존과 동일)
- ❌ 재주입분 재캡처 금지 — `REINJECTED_MARKER`로 식별해 수집에서 제외
- 크기 상한: 항목/총량 config (`analysis_snapshot_*`) — 하드코딩 금지

> 근거: `docs/02-design/features/analysis-data-continuity.design.md` §3/§4.
> 정책 구현: `src/domain/conversation/analysis_snapshot_policy.py`

---

## 분석 원천 데이터 규칙 (analysis-source-preservation 2026-07-07)

- 엑셀 분기 스냅샷은 결과 텍스트(`kind="excel"`, 선행 analysis-data-continuity의 워커 산출)와
  원천 표(`kind="raw_source"`)를 **병행** 저장한다.
- `raw_source`는 압축 표 텍스트로 직렬화하며, 행 초과 시 샘플링 + 총행수를 표기한다.
- `raw_source`는 비-raw 항목과 **독립 budget**(config `analysis_snapshot_raw_source_*`)으로 상한한다
  — 기존 analysis-data-continuity 항목 상한(item/total)을 잠식하지 않는다.
- 원천은 메시지가 아니라 `SupervisorState.analysis_source` 채널(charts 동형)로 전달된다.
- 재주입/재분석은 기존 검색결과 규약·`_analyze_context` context 분기를 재사용(신규 경로 없음).
- 검색/MCP는 이미 원천 원문을 저장하므로 대상 아님(엑셀 분기 한정).

> 근거: `docs/02-design/features/analysis-source-preservation.design.md` §3.
> 정책 구현: `AnalysisSnapshotPolicy.render_raw_source` + kind별 budget.
