# analysis-data-continuity Design Document

> **Summary**: 워커/도구가 수집한 분석 원천 데이터를 assistant 메시지 부속 JSON(`analysis_data`)으로 영속하고, 후속 턴에 검색결과 규약(agent)/system 블록(chat)으로 재주입 + supervisor 보유 데이터 인지 블록으로 재수집 라우팅을 유도하는 설계
>
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-07-06
> **Status**: Draft
> **Planning Doc**: [analysis-data-continuity.plan.md](../../01-plan/features/analysis-data-continuity.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. **스냅샷 영속**: 턴 종료 시 그 턴의 분석 원천 데이터(검색 워커 결과·엑셀 분석 산출·General Chat 도구 결과)를 assistant `conversation_message.analysis_data`(JSON)로 저장 — charts 부속 컬럼과 동형.
2. **무수정 복원**: 후속 턴 컨텍스트 빌드 시 스냅샷을 `format_search_result` 규약 AIMessage로 재주입 → `_analyze_context`/`final_answer_node`가 **코드 수정 없이** "검색 결과 있음" 분기로 동작.
3. **재수집 라우팅**: supervisor decision 프롬프트에 `[보유 분석 데이터]` 인지 블록 — 보유 범위 내 요청은 분석 워커 직행, 범위 밖 요청(나→전체 사용자)은 검색 워커 우선.
4. **compact 공존**: 스냅샷 복원은 최근 윈도우가 아닌 **세션 전체 히스토리 스캔**(`_find_recent_charts` 동형), summarizer 입력 미포함, 재주입 메시지 비영속 (Plan §2.1.B 3대 제약).

### 1.2 Design Principles

- 스냅샷 스키마·상한·선별·렌더 규칙은 domain(`AnalysisSnapshotPolicy`) 단일 정의 — 두 경로(agent/chat)가 공유
- 기존 메시지 규약(`is_search_result`/`is_worker_output`, `search_pipeline.py` 단일 출처)을 재사용 — 분석/최종답변 노드 무수정
- 저장·수집 실패는 graceful degrade (charts 선례) — 본 답변 흐름 불차단, 스택 트레이스 로깅
- 요약 트리거·최근 윈도우 규칙(`SummarizationPolicy`)은 **무변경**

### 1.3 사전 검증 결과 (코드 확인, 2026-07-06)

| 확인 항목 | 결과 | 설계 반영 |
|-----------|------|----------|
| `final_answer_node` 산출 메시지 | name 없는 AIMessage 반환 (`workflow_compiler.py:594`) → `is_worker_output` False | 워커 산출 수집 시 최종답변이 섞이지 않음 — 필터 불필요 |
| `is_search_result(dict)` | 항상 False (`search_pipeline.py:50`) | DB 복원 dict 히스토리는 검색결과로 오인되지 않음 → 재주입만 AIMessage 객체로 |
| 요약 발동 기준 | 메시지 6개 초과, 최근 **메시지 3개** 유지 (`policies.py:41,86`) | 복원은 전체 히스토리 스캔 필수 (윈도우 의존 금지) |
| charts 전체 스캔 선례 | `_find_recent_charts`가 turn_index 역순 전체 스캔 (`use_case.py:356`) | `select_recent`를 동형 구현 |
| summarizer 입력 | content만 사용 (D7-rev1 확인) | analysis_data는 요약에 자연 미포함 — 추가 방어 불필요 |
| General Chat 도구명 | `tavily_search`, `internal_document_search`, MCP 도구 | 제외 목록 기본값 `{"tavily_search"}` |

---

## 2. Architecture

### 2.1 변경 전후 흐름 (커스텀 에이전트 경로)

```
[변경 전]
턴1: search worker ─▶ AIMessage("[w1 검색결과]…")  (인메모리)
     analysis ─▶ chart ─▶ final_answer ─▶ DB 저장: user·assistant 텍스트만  ← 데이터 소실
턴2: _build_messages ─▶ [dict…] 검색결과 없음
     analysis ─▶ "(별도 검색 결과 없음)" ─▶ "데이터를 제공해주시면…"        ← 증상

[변경 후]
턴1: (동일 실행) ─▶ 턴 종료 시 final_messages에서 is_search_result 수집
     ─▶ AnalysisSnapshotPolicy.build_snapshot ─▶ assistant 메시지 analysis_data 저장
턴2: _build_messages ─▶ [dict…] + 재주입 AIMessage(format_search_result 규약, 비영속)
     supervisor ─▶ [보유 분석 데이터] 블록으로 재사용/재수집 판단
       ├─ 범위 내("월별로 다시") ─▶ analysis 직행: 재주입 데이터로 분석 → 차트
       └─ 범위 밖("전체 사용자") ─▶ search worker 재호출 → 새 데이터 → analysis → 차트
```

### 2.2 스냅샷 생명주기

```
수집(턴 종료) ─▶ 절단/상한(policy) ─▶ 저장(analysis_data JSON)
                                        │
다음 턴 ◀─ 재주입(비영속, 마커 부착) ◀─ select_recent(전체 히스토리 역순, 최신 N)
                                        │
재캡처 방지: 재주입 마커 포함 메시지는 수집 대상에서 제외 (§3.3)
```

---

## 3. Detailed Design

### 3.1 D1 — Domain: 엔티티 확장 + `AnalysisSnapshotPolicy`

**`src/domain/conversation/entities.py`** — charts 동형 부속 필드:

```python
@dataclass(frozen=True)
class ConversationMessage:
    ...
    charts: Optional[list[dict]] = None
    # analysis-data-continuity: 분석 원천 데이터 스냅샷 (None = 없음)
    analysis_data: Optional[dict] = None

    def __post_init__(self) -> None:
        ...
        if self.analysis_data is not None and not self.analysis_data.get("items"):
            raise ValueError("analysis_data must be None when it has no items")
```

**`src/domain/conversation/analysis_snapshot_policy.py`** (신규, 순수 도메인 — 외부 의존 0):

```python
REINJECTED_MARKER = "(이전 턴 수집 데이터)"  # 재캡처 방지 식별자

class AnalysisSnapshotPolicy:
    """분석 원천 데이터 스냅샷의 스키마·상한·선별·렌더 규칙."""

    def __init__(self, item_max_chars=4000, total_max_chars=8000, retention=2): ...

    def build_snapshot(self, question: str, items: list[dict]) -> dict | None:
        """items: [{"origin": str, "kind": "search"|"excel"|"tool", "content": str}]
        - 빈/공백 content 항목 제거, item_max_chars 절단(truncated=True 표기)
        - 누적 total_max_chars 도달 시 이후 항목 드롭
        - 유효 항목 0개면 None (엔티티 규칙과 일치)
        반환: {"version": 1, "question": question[:200], "items": [...]}"""

    def select_recent(self, messages: list[ConversationMessage]) -> list[dict]:
        """turn_index 역순 전체 스캔(_find_recent_charts 동형),
        analysis_data 부속 assistant 메시지에서 최신 retention개 수집.
        반환 순서: 오래된 것 → 최신 (컨텍스트 자연 순서)."""

    def render_reinjection_body(self, snapshot: dict, item: dict) -> str:
        """재주입 본문: f"{REINJECTED_MARKER} (질문: {snapshot['question']})\n{item['content']}"
        → format_search_result(item["origin"], body)로 감싸서 사용."""

    def render_context_block(self, snapshots: list[dict]) -> str:
        """General Chat용 [이전 분석 데이터] system 블록 (없으면 "").
        supervisor 인지 블록은 §3.5가 state 메시지에서 직접 요약한다."""

    def is_reinjected(self, content: str) -> bool:
        """REINJECTED_MARKER 포함 여부 — 재캡처 제외 판정."""
```

**결정 근거**
- 재주입분을 다시 캡처하면 스냅샷이 턴마다 앞으로 복사되어 DB 중복 증가 → 마커로 제외하고, 복원은 항상 원본 턴에서 전체 스캔으로 찾는다.
- supervisor 인지 블록(§3.5)은 본문을 싣지 않는다 — supervisor는 "무엇을 보유했는지"만 알면 되고, 실제 데이터는 재주입 메시지로 이미 컨텍스트에 있다.

### 3.2 D2 — 영속 계층

**마이그레이션 `db/migration/V039__alter_conversation_message_add_analysis_data.sql`** (V031 동형):

```sql
-- analysis-data-continuity: 분석 원천 데이터 스냅샷 (NULL=없음)
ALTER TABLE conversation_message
    ADD COLUMN analysis_data JSON NULL COMMENT '분석 원천 데이터 스냅샷 (analysis-data-continuity)';
```

**모델/매퍼** — `ConversationMessageModel.analysis_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)`, 매퍼 왕복에 필드 추가. Repository 시그니처 변경 없음(엔티티 부속).

### 3.3 D3 — 커스텀 에이전트 경로: 수집·저장 (`run_agent_use_case.py`)

`stream()`의 `_parse_result` 직후, `_save_assistant_message` 직전에 수집:

```python
def _collect_snapshot(self, request, question: str, final_messages: list) -> dict | None:
    """턴의 분석 원천 데이터 수집. 실패 시 None (graceful, 로깅)."""
    items = [
        {"origin": getattr(m, "name", ""), "kind": "search",
         "content": getattr(m, "content", "")}
        for m in final_messages
        if is_search_result(m)
        and not self._snapshot_policy.is_reinjected(getattr(m, "content", ""))
    ]
    if _has_excel(getattr(request, "attachments", None)):
        items += [
            {"origin": getattr(m, "name", ""), "kind": "excel",
             "content": getattr(m, "content", "")}
            for m in final_messages
            if is_worker_output(m) and not is_search_result(m)
        ]
    return self._snapshot_policy.build_snapshot(question, items)
```

- **search 항목**: `is_search_result` 전부 (재주입 마커 제외 — §3.1)
- **excel 항목**: 엑셀 첨부 턴에 한해 비검색 워커 출력(=분석 워커의 엑셀 산출 텍스트) 포함. final_answer는 name 없음이라 자연 제외(§1.3)
- `_save_assistant_message(..., analysis_data=snapshot)` — charts 파라미터와 동형 추가
- 수집/빌드 예외는 try/except로 None 처리 + `logger.error(exception=...)` (본 흐름 불차단)

### 3.4 D4 — 커스텀 에이전트 경로: 복원 (`_build_messages`)

```python
async def _build_messages(self, query, user_id, session_id, has_session) -> list:
    ...  # 기존 dict 히스토리 빌드 (전체 or 요약+최근3)
    snapshots = self._snapshot_policy.select_recent(existing)  # 전체 히스토리 스캔
    injected = [
        AIMessage(
            name=item["origin"],
            content=format_search_result(
                item["origin"],
                self._snapshot_policy.render_reinjection_body(snap, item),
            ),
        )
        for snap in snapshots for item in snap["items"]
    ]
    return [*history_messages, *injected, {"role": "user", "content": query}]
```

- **삽입 위치**: 히스토리 뒤·새 user 메시지 앞 — supervisor/분석/최종답변 모두에게 "직전 수집 데이터"로 보임
- **요약 경로**(`_build_summarized_context`)도 동일하게 마지막에 주입 — 요약본은 system 선두, 스냅샷은 후미(가장 신선한 위치)
- 재주입 메시지는 **저장하지 않음** (컨텍스트 빌드 산출물) — compact 이중 비대 루프 차단 (Plan 제약 2)
- `existing`은 이미 조회된 리스트 재사용 — 추가 DB 조회 0회
- LangGraph `add_messages`는 dict/AIMessage 혼용 수용 (기존 초기 state도 dict 사용 중)

### 3.5 D5 — Supervisor 보유 데이터 인지 블록 (`supervisor_nodes.py`)

`_render_attachment_block`/`_render_viz_guidance_block` 동형의 세 번째 블록:

```python
def _render_data_context_block(messages: list) -> str:
    """state 내 검색결과 메시지(현재 턴 수집분 + 재주입분) 요약 → 인지 블록.
    없으면 빈 문자열."""
    entries = [m for m in messages if is_search_result(m)]
    if not entries:
        return ""
    lines = ...  # origin + 본문 첫 줄(질문 라벨) + 크기, 항목당 1줄
    return (
        f"\n\n[보유 분석 데이터]\n{lines}\n"
        f"- 요청이 보유 데이터 범위 안이면 데이터 재수집 없이 분석 워커를 호출하세요.\n"
        f"- 요청이 보유 데이터 범위를 벗어나면(대상·기간·집단 확대 등) "
        f"먼저 검색 워커로 새 데이터를 수집한 뒤 분석 워커를 호출하세요."
    )
```

- `decision_prompt` 조립부에 `{attachment_block}{data_block}{viz_block}` 순으로 삽입
- 입력이 messages 뿐이므로 순수 함수 — 단위 테스트 용이
- 강제 라우팅 훅(②안)은 **도입하지 않음** — 인지 블록 + D6 안전망으로 시작, Gap 분석에서 오라우팅이 확인되면 `AttachmentRoutingHooks` 동형 훅을 후속 도입 (Plan §6.2 결정 유지)

### 3.6 D6 — 분석 노드 부족-명시 출력 규약 (`workflow_compiler.py` / `analysis_prompt.py`)

`_analyze_context`의 analysis_prompt에 1개 지시 추가 (`ANALYSIS_OUTPUT_GUIDE` 뒤):

```
데이터가 질문 범위에 부족하면 사용자에게 데이터 제공을 요청하지 마세요.
대신 (1) 현재 보유 데이터로 답할 수 있는 부분을 먼저 분석하고,
(2) 어떤 데이터가 부족한지와 무엇을 추가 수집해야 하는지를 명시하세요.
```

- "데이터를 제공해주시면…" 회피성 응답 제거 (FR-06). 그래프 배선 변경 없음(프롬프트만).

### 3.7 D7 — General Chat 경로 (`general_chat/use_case.py`)

**수집** (`stream()`의 `_persist_messages` 직전):

```python
items = [
    {"origin": getattr(m, "name", ""), "kind": "tool",
     "content": coerce_message_text(getattr(m, "content", ""))}
    for m in state.final_messages
    if isinstance(m, ToolMessage)
    and getattr(m, "name", "") not in self._snapshot_excluded_tools
]
snapshot = self._snapshot_policy.build_snapshot(request.message, items)
```

- 제외 목록 config 기본값 `{"tavily_search"}` — 웹 스니펫은 데이터성 낮음, MCP·internal_document_search 결과는 캡처 (보수 기본값이 필요해지면 config로 확대)
- `_persist_messages(..., analysis_data=snapshot)` — assistant 메시지에만 부속 (charts 동형)

**복원** (`_build_full_context` / `_build_summarized_context`):

```python
block = self._snapshot_policy.render_context_block(snapshots)
# "[이전 분석 데이터]\n(질문: …)\n<content>…" — 상한 적용된 원문 포함
if block:
    messages.append(SystemMessage(content=block))
messages.append(HumanMessage(content=new_message))
```

- ReAct 경로는 검색결과 메시지 규약이 없으므로 SystemMessage 블록으로 주입 (D7-rev1 캡션과 공존 — 캡션은 차트 형상, 블록은 데이터)
- `_SYSTEM_PROMPT`에 1줄 추가: `"[이전 분석 데이터] 블록이 있으면 후속 분석/차트 요청에 그 데이터를 재사용하고, 범위를 벗어난 요청이면 도구로 새 데이터를 수집하세요."`
- **chart_builder 컨텍스트 보강**: `_maybe_build_charts`의 `context = self._build_chart_context(sources)`가 빈 문자열이면 스냅샷 블록으로 대체 — 후속 턴 차트의 수치 근거 확보

### 3.8 D8 — Config + DI (`src/config.py`, `src/api/main.py`)

```python
# Analysis Snapshot (analysis-data-continuity)
analysis_snapshot_item_max_chars: int = 4000    # 항목당 절단 상한
analysis_snapshot_total_max_chars: int = 8000   # 스냅샷 총량 상한
analysis_snapshot_retention: int = 2            # 재주입할 최신 스냅샷 수
analysis_snapshot_excluded_tools: str = "tavily_search"  # 콤마 구분
```

- **상한 근거 (compact 후 총량 기준, Plan 제약 3)**: 요약(≤512자, `_SUMMARY_MAX_CHARS`) + 최근 메시지 3개 + 스냅샷 8k ≈ 재주입 후에도 검색 워커 1회 실행 턴의 컨텍스트보다 작음. Gap 분석에서 LangSmith 실측으로 재조정.
- `main.py`에서 `AnalysisSnapshotPolicy(config 값)` 생성 → `RunAgentUseCase`/`GeneralChatUseCase`에 주입. **미주입(None) 시 기능 비활성** — charts/transformer 선례의 하위호환 패턴.

---

## 4. 규칙 문서 개정안 (`docs/rules/conversation-memory.md` 추가 조항)

```markdown
## 분석 데이터 스냅샷 규칙 (analysis-data-continuity 2026-07-06)

`conversation_message.analysis_data`(분석 원천 데이터 스냅샷)의 컨텍스트 투입 규칙:

- ✅ 다음 턴 컨텍스트 빌드 시 최신 N개(config)를 재주입한다
  (agent: 검색결과 규약 AIMessage / chat: system 블록). 재주입 메시지는 저장하지 않는다
- ✅ 복원은 최근 윈도우가 아니라 세션 전체 히스토리에서 조회한다 (요약 발동과 무관)
- ❌ 요약(summarizer) 입력에 포함 금지 — 입력은 content만 사용 (기존과 동일)
- ❌ 재주입분 재캡처 금지 — REINJECTED_MARKER로 식별해 수집에서 제외
- 크기 상한: 항목/총량 config (`analysis_snapshot_*`) — 하드코딩 금지
```

---

## 5. Test Plan (TDD — Red 먼저 작성)

| # | 테스트 파일 | 케이스 |
|---|------------|--------|
| T1 | `tests/domain/conversation/test_analysis_snapshot_policy.py` (신규) | build: 절단·총량 드롭·빈 항목 제거·0개→None / select_recent: 역순 N개·analysis_data 없는 세션→[] / marker: is_reinjected / render_scope_lines 형식 |
| T2 | `tests/domain/conversation/test_entities.py` | analysis_data 빈 items 금지, None 허용 |
| T3 | `tests/infrastructure/persistence/test_conversation_mapper.py` | analysis_data 왕복 (None/dict) |
| T4 | `tests/application/agent_builder/test_run_agent_use_case*.py` | 검색결과 포함 런 → assistant 저장에 snapshot / 엑셀 첨부 턴 → excel 항목 포함 / 재주입 마커 메시지 재캡처 제외 / 수집 예외 → None + 본 흐름 정상 |
| T5 | 〃 | `_build_messages`: 스냅샷 세션 → 재주입 AIMessage(`is_search_result` True) + user-last / 요약 경로에서도 주입 / 스냅샷 없으면 기존과 동일 |
| T6 | `tests/application/agent_builder/test_supervisor_nodes*.py` | `_render_data_context_block`: 검색결과 有→블록 생성, 無→"" / decision_prompt 포함 |
| T7 | `tests/application/general_chat/test_use_case*.py` | ToolMessage 캡처(제외 목록 동작) / 복원 SystemMessage 블록 / chart context fallback / 미주입 시 비활성(하위호환) |
| T8 | 회귀 | 기존 agent_builder·general_chat·conversation 테스트 전체 (Windows 이벤트 루프 flaky는 격리 실행으로 판정) |

**시나리오 검증 (Do 완료 후 수동/통합)**: 턴1 "나의 휴가데이터 그래프" → 턴2 "월별로 다시"(재사용) / 턴2' "전체 사용자"(재수집 라우팅) / 7메시지째(요약 발동 후) 후속 분석.

---

## 6. Implementation Order

1. T1·T2 Red → `AnalysisSnapshotPolicy` + 엔티티 필드 (D1)
2. T3 Red → V039 마이그레이션 + 모델/매퍼 (D2)
3. T4 Red → agent 수집·저장 (D3)
4. T5 Red → agent 복원 재주입 (D4)
5. T6 Red → supervisor 인지 블록 (D5) + 분석 프롬프트 지시 (D6)
6. T7 Red → General Chat 수집/복원/chart fallback (D7)
7. config + main.py DI (D8) → T8 회귀 → `conversation-memory.md` 개정 (§4)

---

## 7. Plan 리스크 해소 매핑

| Plan §5 리스크 | 설계 해소 |
|----------------|----------|
| 토큰 비대 | 항목 4k/총량 8k/보존 2개 config (§3.8) + scope 블록은 요약만(§3.5) |
| 메모리 정책 금지 조항 | 요약 규칙 무변경, 규칙 문서 개정 조항 명문화 (§4) |
| PII 장기 보존 | 세션 스코프 + 절단. 마스킹은 pii-masking-integration 후속 (Plan 유지) |
| supervisor 분석 직행 | 인지 블록(§3.5) + 부족-명시 규약(§3.6) 2중 안전망. 강제 훅은 Gap 결과로 판단 |
| 저장 실패 전파 | 수집 try/except → None + 로깅 (§3.3) |
| 데이터성 판별 모호 | agent: `is_search_result` 규약 / chat: 제외 목록 config (§3.7) — 판별 LLM 호출 없음 |
| 요약본-스냅샷 불일치 착각 | 인지 블록이 "현재 보유분"만 나열 → 없으면 재수집 (§3.5) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-06 | Initial draft — D1~D8 상세 설계 + 사전 검증 6건 + 테스트 계획 | 배상규 |
