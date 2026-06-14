# RAG Score Threshold Filter — Gap Analysis (Check Phase)

> **Feature**: rag-score-threshold-filter
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-06-04
> **Phase**: Check (Design ↔ Implementation Gap Analysis)
> **Design Doc**: [rag-score-threshold-filter.design.md](../02-design/features/rag-score-threshold-filter.design.md)
> **Plan Doc**: [rag-score-threshold-filter.plan.md](../01-plan/features/rag-score-threshold-filter.plan.md)

---

## 1. Match Rate: **100%**

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% | ✅ |
| Architecture Compliance | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| Test Coverage (Design §8.2) | 100% | ✅ |
| **Overall** | **100%** | ✅ |

> Gap analysis 수행: gap-detector agent (read-only). 6개 구현 파일 + 4개 테스트 파일 + 설계 컴포넌트/데이터플로우 사양 전수 검증.

---

## 2. Requirements Verification

| Req | Requirement | Impl? | Evidence (file:line) |
|-----|-------------|:-----:|----------------------|
| FR-01 | `Settings.rag_vector_score_threshold: float = 0.0` | ✅ | `src/config.py:33-36` |
| FR-02 | `RagToolConfig.score_threshold: float \| None = None` | ✅ | `src/domain/agent_builder/rag_tool_config.py:40` |
| FR-02 | `__post_init__` 범위 검증 (0.0~1.0, None 허용) | ✅ | `rag_tool_config.py:49-54` |
| FR-03 | `HybridSearchRequest.vector_score_threshold: float = 0.0` | ✅ | `src/domain/hybrid_search/schemas.py:24` |
| FR-04 | `_fetch_vector` 컷오프 `(doc.score or 0.0) >= threshold` | ✅ | `src/application/hybrid_search/use_case.py:151-161` |
| FR-04 | 컷오프 발생 시 debug 로그 | ✅ | `use_case.py:162-169` |
| FR-05 | `InternalDocumentSearchTool.score_threshold: float = 0.0` | ✅ | `src/application/rag_agent/tools.py:60` |
| FR-05 | `_single_query_search`에서 `vector_score_threshold` 전달 | ✅ | `tools.py:173` |
| FR-06 | `ToolFactory.create` 임계값 해석 + 주입 | ✅ | `src/infrastructure/agent_builder/tool_factory.py:68, 75` |
| FR-06 | `_resolve_score_threshold` 헬퍼 (에이전트값 else 전역) | ✅ | `tool_factory.py:144-154` |
| FR-07 | 기존 `create()` kwargs 보존 (무회귀) | ✅ | `tool_factory.py:69-87` |

### 설계 사양 교차 검증

| Spec | Expected | Actual | Status |
|------|----------|--------|:------:|
| 경계값 의미 | `>=` (포함) | `use_case.py:160` | ✅ |
| None 점수 처리 | `(doc.score or 0.0)` → 0.0 | `use_case.py:157, 160` | ✅ |
| 해석 우선순위 | 에이전트값(is not None) else 전역 | `tool_factory.py:150-154` | ✅ |
| Tool→UseCase float 계약 | 항상 확정 float (None은 상류 해석) | tool 기본 0.0, factory 해석 | ✅ |
| Env 변수명 | `RAG_VECTOR_SCORE_THRESHOLD` | pydantic auto-map (`config.py:5`) | ✅ |
| Domain purity | RagToolConfig/HybridSearchRequest 외부 의존 0 | 순수 dataclass | ✅ |
| 의존성 방향 | infra가 settings 읽음, domain 무관 | `tool_factory.py:152` 지역 import | ✅ |

---

## 3. Test Coverage (Design §8.2)

| Test file | Required cases | Status |
|-----------|---------------|:------:|
| `tests/domain/agent_builder/test_rag_tool_config.py` | default None, valid range, <0 raises, >1 raises, None allowed, from_dict | ✅ 6 cases |
| `tests/domain/hybrid_search/test_schemas.py` | default 0.0, explicit value | ✅ |
| `tests/application/hybrid_search/test_hybrid_search_use_case.py` | filters below, boundary inclusive, 0.0 keeps all, all-filtered→BM25, None=0.0 | ✅ 5 cases |
| `tests/infrastructure/agent_builder/test_tool_factory.py` | agent value, fallback global, explicit 0.0 overrides | ✅ 3+1 cases |

**테스트 실행 결과**: 신규 케이스 전수 통과. 교차 실행 시 나타나는 `ProactorEventLoop _ssock` teardown 에러는 단언 실패가 아닌 Windows 이벤트 루프 GC 노이즈(문서화된 기존 플래키니스), 단일 격리 실행 시 0 에러 확인.

---

## 4. Out-of-Scope Confirmation (정상적으로 미구현)

| Out-of-scope item | Status | Evidence |
|-------------------|:------:|----------|
| Multi-Query 임계값 전파 | ✅ 정상 부재 | `tools.py:136-145` `_multi_query_search`에 인자 없음 |
| BM25 점수 임계값 | ✅ 정상 부재 | `_fetch_bm25` (`use_case.py:88-134`) 필터 없음 |
| RRF 최종 점수 임계값 | ✅ 정상 부재 | `policies.py` threshold 매칭 없음, `merge()` 인자 없음 |

> 참고: `src/infrastructure/retriever/qdrant_retriever.py`의 `score_threshold`는 별개의 기존 LangChain retriever 파라미터로, 본 기능의 6파일 하이브리드 경로와 무관 (deviation 아님).

---

## 5. Gaps / Deviations

**없음.** 구현이 설계와 정확히 일치 — `None` vs `0.0` 의미 분리(None=전역 기본값, 0.0=명시적 비활성), 경계값 포함(`>=`), 단일 필터 지점 원칙(컷오프는 `_fetch_vector`에만, BM25/RRF/Multi-Query 미적용) 모두 준수.

### 후속 처리 (Check 단계에서 보완 완료)

- Design §11.2 step 16의 `.env.example` 문서화 — gap-detector가 미검증으로 표시 → **본 Check 단계에서 추가 완료** (`.env.example`에 `RAG_VECTOR_SCORE_THRESHOLD=0.0` 주석 포함 추가).

---

## 6. Recommended Action

Match Rate **100% (≥90%)** → 반복(iterate) 불필요. 다음 단계:

```
/pdca report rag-score-threshold-filter
```

(선택) 보고서 전 `/simplify`로 변경 코드 정리 검토 가능 — 단, 본 변경은 6개 파일 소규모 확장으로 정리 여지 낮음.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-04 | Gap analysis 완료 (Match Rate 100%) | 배상규 |
