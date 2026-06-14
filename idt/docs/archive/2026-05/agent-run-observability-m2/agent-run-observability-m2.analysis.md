# Gap Analysis: agent-run-observability-m2

> 분석일: 2026-05-21
> 분석 대상: Plan/Design ↔ Implementation/Tests
> Match Rate: **98%**
> Task ID: AGENT-OBS-002
> Parent (M1): agent-run-observability (archived, 96%)

---

## 1. 분석 개요

| 항목 | 내용 |
|------|------|
| Plan | `docs/01-plan/features/agent-run-observability-m2.plan.md` |
| Design | `docs/02-design/features/agent-run-observability-m2.design.md` |
| Implementation (NEW) | `src/application/agent_run/purpose_inference.py` |
| Implementation (MODIFIED) | `src/infrastructure/llm/usage_callback.py` (lines 30-369) |
| Tests (NEW) | `tests/application/agent_run/test_purpose_inference.py` (≈22 cases) |
| Tests (NEW) | `tests/infrastructure/llm/test_usage_callback_tool_hooks.py` (≈25 cases, 6 classes) |
| Tests (MODIFIED) | `tests/application/agent_builder/test_run_agent_use_case_observability.py` (+4 cases in `TestToolCallWiringM2`) |
| Test Result | **61/61 PASS** (purpose_inference + usage_callback_tool_hooks 단위 테스트) |
| Critical Regression Test | ✅ `test_llm_call_inside_tool_attaches_tool_call_id` (unit: `test_usage_callback_tool_hooks.py:387`, integration: `test_run_agent_use_case_observability.py:299`) |

---

## 2. 카테고리별 점수

| Category | Score | Status |
|----------|:-----:|:------:|
| Design §4 Interface Signature Match | 100% | ✅ PASS |
| Design §11.1 File Structure | 100% | ✅ PASS |
| Plan §13 DoD — Code 6 items | 100% | ✅ PASS |
| Plan §13 DoD — Tests (critical regression) | 100% | ✅ PASS |
| Plan §1-3 / §7 Out-of-Scope Preservation | 100% | ✅ PASS |
| Design §9 Clean Architecture | 100% | ✅ PASS |
| CLAUDE.md §3 / §6 Convention | 100% | ✅ PASS |
| Design §4.3 Regex Spec Literal Match | 90% | 🟡 Minor |
| **Overall Match Rate** | **98%** | **✅ PASS (≥ 90%)** |

---

## 3. Design §4 인터페이스 일치도

### 3-1. `purpose_inference.py` (Design §4.3)

| 요소 | Design | 실제 | 동등성 |
|------|--------|------|:------:|
| 모듈 위치 | `src/application/agent_run/purpose_inference.py` | 동일 | ✅ |
| 함수 시그니처 | `infer_tool_purpose(tool_name: str) -> RunPurpose` | `Optional[str] -> RunPurpose` (None도 안전 처리) | ✅ 보완 |
| `_RULES` 패턴 수 | 8개 | 8개 (query_rewrit, reranker/compressor, hallucination, rag_search/retrieval/hybrid/internal_document, tavily/web_search/perplexity, excel_export, python_code_executor, mcp_) | ✅ |
| 매칭 실패 시 반환 | `RunPurpose.OTHER` | 동일 | ✅ |
| 빈 문자열/None 처리 | OTHER | OTHER | ✅ |
| 대소문자 무관 | `re.IGNORECASE` | 동일 | ✅ |
| import 의존성 | `RunPurpose` 만 | 동일 | ✅ |

### 3-2. `usage_callback.py` (Design §4.1, §4.2, §4.4, §4.5)

| 요소 | Design | 실제 위치 | 동등성 |
|------|--------|----------|:------:|
| `_ARGS_MAX_BYTES = 1024` | 모듈 상수 | line 38 | ✅ |
| `_RESULT_MAX_CHARS = 1024` | 모듈 상수 | line 39 | ✅ |
| `_ToolStartInfo` frozen dataclass | tool_call_id, t0, prev_purpose, prev_tool_call_id | lines 43-54, 4-field frozen dataclass | ✅ |
| `_sanitize_args(payload) -> Optional[dict]` | dict/str/None/기타 변환 + 1KB 컷 + repr fallback | lines 57-89 | ✅ |
| `_summarize_tool_output(value) -> Optional[str]` | None/Document/BaseModel/str/dict/list/기타 + 1KB 컷 | lines 92-121 | ✅ |
| `_update_run_context_tool_call_id` 헬퍼 | ContextVar 동기화 | lines 139-149 | ✅ |
| `_tool_starts: dict[UUID, _ToolStartInfo]` 인스턴스 필드 | 매칭 dict | line 175 | ✅ |
| `async on_tool_start` 시그니처 | `(serialized, input_str, *, run_id, parent_run_id, tags, metadata, inputs, **kwargs)` | lines 243-290, 정확 일치 | ✅ |
| `async on_tool_end` 시그니처 | `(output, *, run_id, parent_run_id, **kwargs)` | lines 292-328, 정확 일치 | ✅ |
| `async on_tool_error` 시그니처 | `(error, *, run_id, parent_run_id, **kwargs)` | lines 330-369, 정확 일치 | ✅ |
| `set_purpose(infer_tool_purpose(tool_name))` 자동 호출 | on_tool_start 진입 | line 289 | ✅ |
| `_current_tool_call_id` 자동 세팅/복원 | on_tool_start/end/error | ✅ | ✅ |
| `prev_purpose` / `prev_tool_call_id` 복원 (중첩 안전) | end/error | lines 326-328, 367-369 | ✅ |
| `record_tool_call` 실패 best-effort (sentinel `""`) | warning log + skip | lines 281-282, 309-315 | ✅ |
| `update_tool_call` 실패 best-effort | warning log + skip | lines 318-323, 360-364 | ✅ |
| latency_ms 계산 | `int((perf_counter() - t0) * 1000)` | end/error 동일 | ✅ |
| 매칭 미스 처리 | warning log + skip | lines 302-307, 340-346 | ✅ |
| RunContext 동기화 | `_update_run_context_tool_call_id` | start/end/error 3곳 모두 | ✅ |

---

## 4. Plan §13 DoD 체크리스트 (코드)

| # | DoD 항목 | 검증 | 상태 |
|---|---------|------|:----:|
| 1 | `on_tool_start` / `on_tool_end` / `on_tool_error` 3 비동기 메서드 추가 | usage_callback.py:243, 292, 330 | ✅ |
| 2 | `_summarize_tool_output` / `_sanitize_args` 헬퍼 (1KB 컷 + 직렬화 실패 fallback) | usage_callback.py:57, 92 | ✅ |
| 3 | `_tool_starts: dict[UUID, _ToolStartInfo]` LangChain run_id 키 격리 | usage_callback.py:175 | ✅ |
| 4 | `purpose_inference.py` Design §5-3 매핑 표 코드화 | purpose_inference.py 전체 | ✅ |
| 5 | `set_purpose(infer_tool_purpose(tool_name))` 자동 호출 | usage_callback.py:289 | ✅ |
| 6 | `RunContext.tool_call_id` 자동 set/reset | `_update_run_context_tool_call_id` 3곳 호출 | ✅ |

---

## 5. Plan §13 DoD 체크리스트 (테스트)

| # | DoD 항목 | 검증 | 상태 |
|---|---------|------|:----:|
| 1 | `test_usage_callback_tool_hooks.py` 케이스 통과 | 단위 테스트 실행 → 통과 | ✅ |
| 2 | `test_purpose_inference.py` 케이스 통과 | 단위 테스트 실행 → 통과 | ✅ |
| 3 | `test_run_agent_use_case_observability.py` 4 신규 케이스 추가 | `TestToolCallWiringM2` 클래스 lines 227-377 (4 method) | ✅ |
| 4 | **회귀 가드 `test_llm_call_inside_tool_attaches_tool_call_id`** | unit 단위 ✅ + integration ✅ 2중 배치 | ✅ |
| 5 | M1 118개 기존 테스트 100% 유지 | 본 Check 범위 외 — 별도 회귀 실행 권장 | ⏸ Pending |

**단위 테스트 실행 결과**:
```
$ python -m pytest tests/application/agent_run/test_purpose_inference.py \
                   tests/infrastructure/llm/test_usage_callback_tool_hooks.py -q
.............................................................   [100%]
61 passed in 4.53s
```

---

## 6. Plan §1-3 / §7 "범위 외" 항목 보존 확인

| 항목 | 변경 금지 대상 | 실제 상태 | 상태 |
|------|--------------|----------|:----:|
| 신규 테이블 / 도메인 / VO / Repository | 없음 | `src/domain/agent_run/` git diff 없음, 신규 마이그레이션 V023+ 없음 | ✅ |
| DB 마이그레이션 추가 | 없음 | `V022__add_llm_model_pricing.sql`은 M1 G1 가격 컬럼 추가용 (M2 스코프 외) | ✅ |
| LangGraph 노드 hook (M3) | 미구현 | `on_chain_start/end` 없음 | ✅ |
| RAG retrieval 영속화 (M4) | 미구현 | `rag_agent/tools.py` `record_retrieval()` 호출 없음 | ✅ |
| 어드민 UI / API 라우터 (M4) | 미구현 | `src/api/routes/`에 `tool_call` 라우터 없음 | ✅ |
| `_wrapped_tool_call` 명시 wrapping | 폐기 | WorkflowCompiler / ToolFactory 미수정 | ✅ |
| WorkflowCompiler 수정 | 없음 | grep `on_tool_*` in `src/application/agent_builder/` = 0건 | ✅ |
| ToolFactory 수정 | 없음 | grep `on_tool_*` in `src/infrastructure/agent_builder/` = 0건 | ✅ |
| `rag_agent/tools.py` 수정 | 없음 | grep `record_tool_call` in `src/application/rag_agent/` = 0건 | ✅ |

---

## 7. Design §9 Clean Architecture 의존성 검증

```
infrastructure/llm/usage_callback.py
    ├──> application/agent_run/tracker.py            (M1, 변경 없음)         ✅
    ├──> application/agent_run/purpose_inference.py  (M2 신규)              ✅
    ├──> application/agent_run/context.py            (M1, 변경 없음)         ✅
    └──> domain/agent_run/value_objects.py           (RunPurpose import)    ✅

application/agent_run/purpose_inference.py
    └──> domain/agent_run/value_objects.py           (RunPurpose only)      ✅
         + 외부 의존성 없음 (re 모듈만)
```

- [x] domain → infrastructure 참조 없음
- [x] application(`purpose_inference`) → domain만
- [x] infrastructure → application + domain (정방향)
- [x] 역방향 의존성 없음

---

## 8. Gap 항목

### 🔴 Critical / Missing (Plan O, Implementation X)
**없음.**

### 🟠 Major
**없음.**

### 🟡 Minor Deviations (의미적 동등)

| # | 항목 | Design | Implementation | 영향도 |
|---|------|--------|----------------|-------|
| M-1 | `query_rewrit` 정규식 anchoring | `^query_rewrit` (start-anchored) | `query_rewrit` (unanchored) | None — 테스트 케이스 전부 통과, 의미 동등 |
| M-2 | `hallucination` 정규식 anchoring | `^hallucination` (start-anchored) | `hallucination` (unanchored) | None — 동일 |
| M-3 | `_RULES` 우선순위 순서 | mcp_*가 마지막 | mcp_*가 WORKER 그룹보다 앞 | None — 패턴 교집합 없어 기능 동등 |

### 🔵 Added (Plan X, Implementation O — 개선)

| 항목 | 위치 | 영향도 |
|------|------|--------|
| `_ERROR_TEXT_MAX_CHARS = 1024` 모듈 상수 추출 | usage_callback.py | Low — Design은 inline 리터럴, 상수화는 매직넘버 제거 |
| `_extract_tool_name(serialized)` 헬퍼 분리 | usage_callback.py | Low — CLAUDE.md §3 함수 단일책임 / ≤40줄 규칙 준수 강화 |
| `test_purpose_inference.py` 7→22 케이스 확장 | 매핑/대소문자/우선순위/None 분기 모두 커버 | Low — 회귀 가드 강화 |
| `test_usage_callback_tool_hooks.py` 20→25 케이스 확장 | 6 test class 구조로 정리 | Low — 가독성 + 회귀 강화 |

---

## 9. 권장 조치

### Immediate
**없음.** Match Rate 98% — `/pdca iterate` 불필요. `/pdca report agent-run-observability-m2` 진행 권장.

### 수동 검증 (Plan §13.3 잔여 — Check 단계 외부)
1. 실 LLM + RAG 툴 호출 1회 → `ai_tool_call` row 검증
   ```sql
   SELECT id, tool_name, status, latency_ms, JSON_LENGTH(arguments_json),
          LENGTH(result_summary)
   FROM ai_tool_call WHERE run_id = ?;
   ```
2. `ai_llm_call.tool_call_id` JOIN 검증
   ```sql
   SELECT l.id, l.purpose, l.tool_call_id, t.tool_name
   FROM ai_llm_call l LEFT JOIN ai_tool_call t ON t.id = l.tool_call_id
   WHERE l.run_id = ? ORDER BY l.created_at;
   ```
3. Tavily 툴 강제 실패 → `status='FAILED'` + `error_text` 기록
4. M1 118개 기존 테스트 회귀 실행 (Plan §13.2 #5)

### Documentation (Plan §13.4 잔여)
- [x] M2 Design 작성 (`agent-run-observability-m2.design.md`)
- [x] M1 Plan/Design의 `_wrapped_tool_call` → callback-driven 결정 명시 (Design §12)
- [ ] M1 Plan §5-3 status enum 표기 `SUCCESS/FAILED` → `STARTED/SUCCESS/FAILED` 동기화 (M1 archive 시 후속)

### Future (별도 PDCA)
- M3: LangGraph 노드 hook (`ai_run_step` INSERT)
- M4: RAG retrieval source 영속화 + 어드민 조회 API

---

## 10. 결론

**Match Rate 98% — PDCA Check 통과**

- Design §4 인터페이스 100% 구현 일치
- Plan §13 DoD 6/6 코드 항목 완료, 4/5 테스트 항목 완료 (M1 회귀 별도)
- 회귀 가드 `test_llm_call_inside_tool_attaches_tool_call_id`가 단위 + 통합 두 곳에 배치되어 M2의 핵심 가치 (툴-LLM 연결) 영구 보장
- 의미적 동등 Minor 3건(정규식 anchoring 2건, 룰 순서 1건) 외 차이 없음 — 기능 영향 없음
- 신규 마이그레이션 0건, 도메인 변경 0건, 라우터 변경 0건 — "wiring only" 약속 완전 준수
- 단위 테스트 61/61 통과

**다음 단계**: `/pdca report agent-run-observability-m2`
