# answer-citation-verification Design Document

> **Summary**: 검색 청크에 실행 단위 번호를 붙여 답변 모델이 `[n]`으로 인용하고, 기존 근거 판정 호출 안에서 인용을 검증해 저장한다. 칩·원문 뷰어는 저장된 인용만 보여 준다
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-20
> **Status**: Draft
> **Planning Doc**: [answer-citation-verification.plan.md](../../01-plan/features/answer-citation-verification.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| 근거 칩 | `docs/archive/*/agent-run-source-citations` | ✅ (PR #86) |
| 원문 뷰어 | `docs/archive/2026-11/source-passage-viewer` | ✅ (PR #124) |
| 근거 판정 루프 | `docs/wiki/backend/patterns/grounding-rewrite-loop.md` | ✅ |
| 탈착형 이음매 | `docs/wiki/backend/patterns/detachable-module-seam.md` | ✅ |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 칩이 "검색한 것"만 보여 주고 "답변에 쓴 것"을 보여 주지 않아 신뢰 근거가 되지 못한다 |
| **WHO** | 채팅에서 RAG 답변을 받는 사용자, 답변 근거를 점검하는 에이전트 소유자(P2), 판정 모델을 고르는 관리자 |
| **RISK** | 판정 프롬프트 확장이 기존 근거 판정 품질(gpt-4o 벤치 결과)을 떨어뜨린다. 모델이 인용 표시를 빠뜨리면 "근거 확인 안 됨"이 남발된다 |
| **SUCCESS** | 스위치 off면 기존과 동일. on이면 인용 정확도 90% 이상, 지어낸 인용 제거 100%, 추가 LLM 호출 0회, 신규 업로드 문서의 인용 100%에 쪽 번호, 재진입 시 같은 인용 |
| **SCOPE** | 백엔드: 청킹 U+FFFD 수정, ES page 메타, 검색 결과 번호 부여, 판정기 확장, 인용 저장(V093), 판정 모델 관리자 설정(V094). 프론트: `[n]` 렌더, 칩 정리, 문장 단위 음영, 관리자 판정 모델 카드. 웹 검색·MCP 결과 인용과 기존 문서 재청킹은 제외 |

---

## 1. Overview

### 1.1 Design Goals

1. 인용 1건 = (답변 문장, 청크, 청크 안 근거 문장) 쌍이고, 화면에는 검증을 통과한 쌍만 나간다.
2. 근거 판정이 켜진 상태에서 LLM 호출 수가 늘지 않는다(같은 판정 호출에 인용 검증을 싣는다).
3. 스위치 off, 초안(action) 경로, 인용이 없는 답변의 판정 프롬프트는 **한 글자도 바뀌지 않는다**.
4. 실시간 화면과 재진입 화면이 같은 저장소(DB)를 같은 서비스로 읽는다.
5. 판정 모델은 관리자가 고르고, 설정이 없거나 깨지면 `.env`로 돌아간다(인용 스위치와 독립).

### 1.2 Design Principles

- **탈착형 이음매**: 인용 모듈은 duck-typed 협력자 4곳(검색 도구 라벨러, 답변 노드 서비스, 근거 칩 enricher, DI)으로만 붙는다. 주입이 None이면 기존 코드 경로 그대로.
- **결정적 검증 우선**: 번호 존재, 근거 문장의 청크 내 실재 여부는 LLM이 아니라 코드가 확인한다(위키: LLM 출력 신뢰 경계).
- **fail-open**: 판정·저장·조회 실패는 답변을 막지 않는다. 인용은 `none`(검증 실패)으로 남기거나 칩을 기존처럼 보여 준다.
- **선행 수정은 버그 수정으로 취급**: U+FFFD·ES page는 스위치 없이 새 업로드부터 적용한다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | A: 최소 변경 | B: 분리 극대화 | C: 실용 균형 |
|----------|:-:|:-:|:-:|
| 구조 | 답변 노드·판정 어댑터·검색 도구에 직접 추가 | 인용 검증 전용 포트·노드 + 별도 판정 호출 | `answer_citation` 탈착 모듈 + 기존 판정 호출에 선택 인자 |
| 추가 LLM 호출 | 0 | +1/답변 | 0 |
| 기존 판정 프롬프트 영향 | 모든 답변 | 없음 | 인용 있는 답변만 |
| 떼어 내기 | 어려움 | 쉬움 | 쉬움 |
| 작업량 | 작음 | 큼 | 중간 |
| Recommendation | 빠른 실험 | 품질 최우선·비용 무관 | **기본** |

**Selected**: **C — 실용 균형** (2026-11-20 사용자 선택)
**Rationale**: 사용자 결정(추가 호출 없음)과 탈착형 요구를 함께 만족한다. 판정 확장이 기존 품질을 떨어뜨리면(벤치 실패) 같은 포트 뒤에서 B(별도 호출)로 바꿀 수 있게 `GroundedGenerator.verify_citations`를 독립 메서드로 둔다(§2.2 D-05).

### 2.1 Component Diagram

```
[업로드]  BaseTokenChunker(U+FFFD 경계 보정) ─→ unified_upload ES 본문(+page)

[실행]
 InternalDocumentSearchTool._format_results
   └─ citation_labeler?  ──→ CitationRegistry(run_id → n ↔ chunk)     (application/answer_citation)
        "[출처 3: 파일 · 5쪽]\n본문"
 final_answer_node
   ├─ 인용 지시 블록(라벨이 1건 이상일 때)
   ├─ GroundedGenerator.run(citations=builder)   ── 같은 judge 호출 ──→ HallucinationEvaluatorAdapter
   │        (근거 판정 off면 verify_citations 1회)                     (확장 프롬프트·스키마)
   └─ citation_service.finalize_and_save(run_id, final_text, verdict)
          CitationFinalizePolicy(탈락 제거·1부터 재번호) → ai_answer_citation(V093)

[근거 칩]  RunSourcesService.build_for_runs
   └─ citation_enricher?.enrich_runs(built)  ← ai_answer_citation + retrievals(page)
        document item.citation = {status, entries[]}

[판정 모델]  AdminConfiguredJudgeLlmProvider.get()
   ├─ grounding_judge_setting(V094).judge_llm_model_id → 활성 모델
   └─ 없음/비활성/오류 → 기존 env 공급자(GROUNDING_JUDGE_MODEL)

[프론트]  MarkdownRenderer(remarkCitationRefs) · SourceCitation(인용 행/미사용 접힘/근거 확인 안 됨)
          SourceViewer(target.focus → 근거 문장 진하게) · AdminLlmModelsPage(근거 판정 모델 카드)
```

### 2.2 Data Flow & Key Decisions

```
검색 → 라벨·레지스트리 기록 → 답변 생성([n]) → 판정(주장+인용 쌍) → 재작성/문장 제거
     → 최종 본문 기준 정리(탈락 [n] 제거·재번호) → 저장 → 답변 이벤트 직전 칩 조회 → 화면
```

| ID | 결정 | 이유 |
|----|------|------|
| D-01 | 번호 레지스트리는 **프로세스 메모리**의 run_id 키 사전(TTL 30분·최대 1,000 런 LRU). RunContext는 바꾸지 않는다 | 검색 도구와 답변 노드가 같은 프로세스·같은 run_id를 본다. RunContext·RunAgentUseCase 수정 없이 붙어 탈착성이 유지된다 |
| D-02 | 같은 chunk_id는 같은 번호. 번호는 실행 안에서 1부터 증가 | 검색을 여러 번 해도 번호가 겹치지 않는다 |
| D-03 | 인용 검증 입력은 판정 코퍼스(24,000자 절단)와 별도로 `<cited_sources>`에 **인용된 청크만** 원문 그대로 싣는다 | 절단으로 인용 청크가 잘려 오판하는 것을 막는다. 인용되지 않은 청크는 싣지 않아 토큰을 아낀다 |
| D-04 | 확장 프롬프트·스키마는 `citations` 인자가 있을 때만 쓴다. 없으면 기존 체인 그대로 | 초안 경로·스위치 off·인용 없는 답변의 판정 품질 불변(SC-10) |
| D-05 | `GroundedGenerator.verify_citations()`를 독립 메서드로 둔다(재작성 없이 1회 판정) | 근거 판정 off + 인용 on 경로, 그리고 벤치 실패 시 B안(별도 호출) 전환 지점 |
| D-06 | 인용 검증 결과는 **마지막으로 성공한 판정**을 쓴다. 문장 제거 후 본문은 정리 단계에서 다시 파싱한다 | 판정 루프의 마지막 판정은 항상 최종 본문(제거 전)에 대한 것이다. 제거된 문장의 인용은 파싱에서 자연히 빠진다 |
| D-07 | 검증 통과 조건: 번호가 레지스트리에 있음 ∧ `supported=true` ∧ **근거 문장이 지정 청크엔 없고 다른 청크에만 있는 경우가 아님**(v0.3 보강 — 번호가 틀린 인용). 근거 문장이 어느 청크에서도 안 찾아지면 인용은 유지하되 `evidence=null`(청크 전체 음영) | 판정기는 뒷받침을 판단했지만 복사만 틀린 경우를 과삭제하지 않는다. 벤치에서 판정기가 틀린 번호에 다른 청크 문장을 근거로 댄 사례를 결정적으로 걸러낸다 |
| D-08 | 탈락 `[n]`은 본문에서 지우고, 통과한 번호는 등장 순서대로 1부터 다시 매긴다(사용자 결정). 레지스트리 번호에 없는 `[n]` 글자는 건드리지 않는다 | 화면 번호가 1, 2, 3으로 이어진다. 인용과 무관한 대괄호 숫자를 지우지 않는다 |
| D-09 | 코드 블록(```` ``` ````) 안의 `[n]`은 인용으로 보지 않는다. `[1, 3]`·`[1,3]`은 `[1][3]`으로 정규화한다 | 모델 표기 편차 흡수 |
| D-10 | 이전 대화의 assistant 메시지에 남은 `[n]`은 답변 프롬프트에 넣을 때 지운다(스위치 on일 때만) | 지난 턴 번호가 이번 턴 번호와 섞이는 것을 막는다 |
| D-11 | 저장은 실행당 1행(`ai_answer_citation`, run_id PK, 인용은 JSON 배열) | 쓰기 1회, 재진입 조회 1회. 감사·통계는 JSON으로 충분 |
| D-12 | 행이 없으면 `not_applicable` — 칩은 기존 그대로. 행이 있고 인용 0건이면 `none` — "근거 확인 안 됨" | supervisor 밖 경로·스위치 off를 "근거 없음"으로 오해시키지 않는다 |
| D-13 | 칩 계약은 문서 칩마다 `citation: {status, entries[]}`를 싣는다. 실행 단위 상태를 별도 필드로 만들지 않는다 | `RunSourcesReaderPort`·세션 소스 API 반환 형태를 바꾸지 않는다(원문 뷰어 `viewer`와 같은 방식) |
| D-14 | 인용된 문서가 칩 상한(`max_items`)으로 잘렸으면 enricher가 검색 기록으로 문서 칩을 덧붙인다 | 인용이 있는데 칩이 없는 상태 방지 |
| D-15 | 판정 모델 설정은 인용 스위치와 **독립된 상시 기능**. 기존 근거 판정(답변·초안)과 인용 검증이 같은 모델을 쓴다 | 사용자 요구("관리자가 유연하게 선택"). 판정 호출이 하나라 모델도 하나 |
| D-16 | 판정 모델 해석 순서: 관리자 설정 모델(활성) → env `GROUNDING_JUDGE_MODEL` → 기본 모델. 설정 테이블 조회 실패도 env로 폴백 | 마이그레이션 전·오류 시에도 기존 동작 |

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `CitationLabeler` | `CitationRegistry`, `get_current_run_context()` | 라벨 생성·번호 기록 |
| `CitationService` | `CitationRegistry`, `CitationFinalizePolicy`, `AnswerCitationRepository`(세션 범위) | 지시 블록·검증 요청 생성·정리·저장 |
| `HallucinationEvaluatorAdapter` | `CitationCheckRequest` VO(domain/hallucination) | 확장 판정 |
| `CitationEnricher` | `AnswerCitationRepository`, `RunEvidence` | 칩에 인용 덧붙임 |
| `AdminConfiguredJudgeLlmProvider` | `GroundingJudgeSettingRepository`, `LlmModelRepository`, env 공급자 | 판정 모델 해석 |

---

## 3. Data Model

### 3.1 Entity / VO Definition

```python
# domain/hallucination/citation_check.py  (포트가 쓰는 VO — 인용 모듈에 의존하지 않는다)
@dataclass(frozen=True)
class CitationPair:          # 답변 문장 1개 × 인용 번호 1개
    pair_id: str             # "c1", "c2" …
    marker: int              # 레지스트리 번호
    sentence: str            # 답변 원문 그대로

@dataclass(frozen=True)
class CitationCheckRequest:
    pairs: tuple[CitationPair, ...]
    cited_sources: Mapping[int, str]     # 번호 → 청크 본문(모델이 본 그대로)

@dataclass(frozen=True)
class CitationCheck:
    pair_id: str
    supported: bool
    evidence: str            # 판정기가 청크에서 복사한 근거 문장(없으면 "")

# GroundingVerdict 에 필드 추가 (기본값 () — 기존 생성 지점 호환)
    citation_checks: tuple[CitationCheck, ...] = ()
```

```python
# domain/answer_citation/models.py
CitationStatus = Literal["verified", "none"]
NoneReason = Literal["no_markers", "all_rejected", "judge_failed"]

@dataclass(frozen=True)
class RegisteredChunk:       # 레지스트리 항목
    marker: int
    chunk_id: str
    document_id: str | None
    page: int | None
    text: str                # 모델이 본 본문

@dataclass(frozen=True)
class AnswerCitation:        # 저장·표시 단위
    no: int                  # 화면 번호(1부터 재번호)
    marker: int              # 레지스트리 번호(감사용)
    chunk_id: str
    document_id: str | None
    page: int | None
    evidence: str | None     # D-07: 청크에서 못 찾으면 None
    sentence: str            # 인용한 답변 문장

@dataclass(frozen=True)
class CitationOutcome:
    text: str                                # 정리된 최종 본문
    status: CitationStatus
    citations: tuple[AnswerCitation, ...]
    none_reason: NoneReason | None = None
```

### 3.2 Domain Policies (순수 함수, 테스트 대상)

| Policy | 입력 → 출력 | 규칙 |
|--------|------------|------|
| `CitationMarkerParser.pairs(text, known)` | 본문, 레지스트리 번호 집합 → `CitationPair` 목록 | 코드 블록 제외(D-09), `[1, 3]` 정규화, 문장 경계는 `GroundingEditPolicy._boundaries`(문장 종결·번호 목록·문단 경계) 규칙을 공개 정적 메서드 `sentence_spans()`로 꺼내 재사용(문장 제거와 같은 경계 → D-06 일치), `known`에 없는 번호는 무시 |
| `CitationFinalizePolicy.finalize(text, checks, registry, judged)` | 최종 본문, 판정 결과 → `CitationOutcome` | 통과 = 번호 존재 ∧ supported(D-07). 탈락 표시 제거, 등장 순서 재번호(D-08). `judged=False`면 `none/judge_failed`, 표시 0개면 `none/no_markers`, 통과 0개면 `none/all_rejected` |
| `EvidenceLocator.find(evidence, chunk_text)` | → bool | 공백 전부 제거 + U+FFFD 제거 + NFKC 후 부분 문자열 (원문 뷰어 매칭과 같은 기준, Do module-5 확정) |
| `CitationMarkerParser.normalize(text)` | → 본문 | `[1, 3]`→`[1][3]`, `문장.[1]`→`문장[1].` (종결 부호 뒤 공백을 요구하는 문장 경계 규칙 때문에 옮기지 않으면 두 문장이 합쳐짐 — Do module-5 확정). 코드 블록 제외 |
| `CitationMarkerParser.strip_all(text)` | → 본문 | D-10 이전 대화 정리용 |

### 3.3 Database Schema

```sql
-- V093__create_ai_answer_citation.sql
CREATE TABLE ai_answer_citation (
    run_id        VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT 'ai_run.id 소프트 참조 — 실행당 1행',
    status        VARCHAR(16)  NOT NULL COMMENT '검증 결과 verified 또는 none',
    none_reason   VARCHAR(32)  NULL COMMENT 'none 사유 no_markers 또는 all_rejected 또는 judge_failed',
    citations     JSON         NOT NULL COMMENT '검증된 인용 목록 no와 chunk_id와 page와 evidence와 sentence',
    judge_model   VARCHAR(100) NULL COMMENT '판정에 쓴 모델 이름 — 감사용',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각'
) ENGINE=InnoDB COMMENT='답변 인용 검증 결과 — 실행당 1행';

-- V094__create_grounding_judge_setting.sql
CREATE TABLE grounding_judge_setting (
    id                 VARCHAR(36) NOT NULL PRIMARY KEY COMMENT '고정 단일 행 식별자',
    judge_llm_model_id VARCHAR(36) NULL COMMENT 'llm_model.id 소프트 참조 — NULL이면 env 설정 사용',
    updated_by         VARCHAR(36) NULL COMMENT '마지막으로 바꾼 관리자 user_id',
    created_at         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각'
) ENGINE=InnoDB COMMENT='근거 판정 모델 전역 설정 — 단일 행';
INSERT INTO grounding_judge_setting (id) VALUES ('c0000000-0000-4000-8000-000000000094');
```

- CHARSET/COLLATE 명시 금지, COMMENT 안 콤마 금지(V086 선례). SQLAlchemy 모델에 같은 `comment=`.
- FK 없음(소프트 참조 선례). 실행 삭제 시 고아 행은 무해(조회 키가 run_id).

### 3.4 ES 색인 변경

- `unified_upload/use_case.py` ES 본문: `if "page" in chunk.metadata: body["page"] = int(chunk.metadata["page"])`.
- `es_index_mappings.py` `DOCUMENTS_INDEX_MAPPINGS`에 `"page": {"type": "integer"}` 추가(새 인덱스). 기존 인덱스는 dynamic 매핑이라 새 필드가 자동 생성된다(재색인 없음).
- BM25 결과는 `_source` 전 필드를 문자열 metadata로 넘기므로(`hybrid_search/use_case.py:137`) 추가 코드 없이 `metadata["page"]="3"`이 실린다. 라벨러·enricher는 `int()` 변환을 방어적으로 한다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/admin/grounding-judge/settings` | 판정 모델 설정·실제 적용 모델 조회 | 관리자 |
| PUT | `/api/v1/admin/grounding-judge/settings` | 판정 모델 지정/해제 | 관리자 |
| (변경) | 답변 완료 이벤트 `sources[]` | 문서 칩에 `citation` 선택 필드 | 기존 |
| (변경) | `GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/sources` | 같은 `citation` 필드 | 기존 |

### 4.2 Detailed Specification

#### `GET /api/v1/admin/grounding-judge/settings`

```json
{
  "judge_llm_model_id": "6c58e7e9-…",
  "effective": { "model_id": "6c58e7e9-…", "model_name": "gpt-4o", "source": "admin" }
}
```
`source`: `admin`(설정 모델 적용) · `env`(설정 없음/비활성 → `GROUNDING_JUDGE_MODEL`) · `default`(env 이름도 못 찾음 → 기본 모델). 해석 실패 시 `effective`는 `null`.

#### `PUT /api/v1/admin/grounding-judge/settings`

요청 `{ "judge_llm_model_id": "uuid" | null }` → 응답은 GET과 같다.

| Status | Code | 조건 |
|--------|------|------|
| 200 | — | 저장 + 공급자 캐시 무효화 |
| 403 | — | 관리자 아님 |
| 422 | `JUDGE_MODEL_NOT_FOUND` | 존재하지 않거나 비활성 모델 |
| 422 | `JUDGE_MODEL_KIND_INVALID` | 채팅 모델이 아님(임베딩 등) |

#### 칩 `citation` 필드 (문서 칩 전용, 행이 있을 때만)

```json
{
  "kind": "document", "source": "household_debt_250627.pdf", "content": "…", "chunk_id": "…",
  "viewer": { "...": "원문 뷰어 기존 계약" },
  "citation": {
    "status": "verified",
    "entries": [
      { "no": 1, "chunk_id": "17cafdba-…", "page": 2, "evidence": "총량 목표를 경상성장률 이내로 …" }
    ]
  }
}
```
- `status=verified`이고 `entries=[]`인 문서 칩 = 검색했지만 답변에 쓰지 않은 문서.
- `status=none`이면 모든 문서 칩이 `entries=[]`.
- 행이 없으면(`not_applicable`) 키를 싣지 않는다 → 기존 렌더.
- 재진입 DTO `SourceItemDto.citation: Optional[dict]`(원문 뷰어 `viewer`와 같은 방식, null 허용).

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌ 답변 ────────────────────────────────────────────┐
│ 가계대출 총량 목표를 경상성장률 이내로 관리합니다¹.   │
│ 수도권 주담대 한도는 6억 원으로 제한됩니다².          │
├ 근거 ─────────────────────────────────────────────┤
│ ① household_debt.pdf · 2쪽 · "총량 목표를 경상…"  [원문 보기] │
│ ② household_debt.pdf · 4쪽 · "주택담보대출 최대…" [원문 보기] │
│ ▸ 검색했지만 답변에 쓰지 않은 구절 3건                │
└──────────────────────────────────────────────────┘

status=none:
│ ⚠ 근거 확인 안 됨 — 이 답변은 검색 문서로 확인된 인용이 없습니다 │
│ ▸ 검색된 구절 5건                                     │
```

관리자 — LLM 모델 관리 페이지 상단 카드:
```
┌ 근거 판정 모델 ───────────────────────────────────┐
│ [ gpt-4o            ▼ ]  [저장]   현재 적용: gpt-4o (관리자 설정) │
│ 답변 근거 판정과 인용 검증에 함께 쓰입니다. 판정 품질은 모델에 따라 │
│ 크게 달라집니다(gpt-4o-mini는 정상 문장을 근거 없음으로 오판한 기록). │
└──────────────────────────────────────────────────┘
```

### 5.2 User Flow

답변 수신 → 본문 `¹` 클릭 또는 인용 행 [원문 보기] → 원문 패널이 그 청크 위치로 열림 → 근거 문장 진한 음영, 같은 청크 나머지 옅은 음영 → ◀▶는 인용 순서대로 이동.

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `remarkCitationRefs` | `idt_front/src/utils/remarkCitationRefs.ts` | 텍스트 노드의 `[n]`(인용 목록에 있는 n만)을 `citation-ref` 요소로 변환, 코드 블록 제외 |
| `CitationRef` | `components/chat/CitationRef.tsx` | 위첨자 번호 버튼 → 해당 인용 원문 열기 |
| `CitationList` | `components/chat/CitationList.tsx` | 인용 행(번호·파일·쪽·근거 문장·원문 보기) |
| `UnusedSourcesDisclosure` | `components/chat/UnusedSourcesDisclosure.tsx` | 미사용 구절 접힘 목록(기존 칩 재사용) |
| `CitationNoneBadge` | `components/chat/CitationNoneBadge.tsx` | "근거 확인 안 됨" |
| `SourceCitation` (수정) | `components/chat/SourceCitation.tsx` | `citation` 유무로 분기 — 없으면 기존 렌더 그대로 |
| `MarkdownRenderer` (수정) | `components/chat/MarkdownRenderer.tsx` | 선택 prop `citations`가 있을 때만 플러그인 추가 |
| `GroundingJudgeModelCard` | `pages/AdminLlmModelsPage/GroundingJudgeModelCard.tsx` | 판정 모델 선택·현재 적용 표시 |
| `buildCitationView` | `utils/citationView.ts` | 메시지 sources → {status, rows, unused, others} 파생(순수 계산). Do module-8: 상태가 없어 훅 대신 순수 함수 |
| `citationViewerTarget` | `utils/citationViewerTarget.ts` | 인용 번호 → 원문 뷰어 대상(그 문서의 인용 구절만, focus=근거 문장, 시작 index) |
| `highlightWithFocus`·`setCurrentWithFocus` | `utils/domHighlight.ts` | 근거 문장을 추가 구절로 함께 칠하고 `data-spv-focus`, 현재 위치는 근거 문장(없으면 청크) |
| `useGroundingJudgeSetting` | `hooks/useGroundingJudgeSetting.ts` | GET/PUT TanStack Query |

### 5.4 Page UI Checklist

#### 채팅 답변 (citation 있음)
- [ ] 본문 인용 표시: 위첨자 번호, 인용 목록에 있는 번호만 버튼, 키보드 포커스 가능, `aria-label="근거 n 원문 보기"`
- [ ] 인용 행: 번호 · 파일명(말줄임) · `N쪽`(page null이면 생략) · 근거 문장(2줄 말줄임, evidence null이면 청크 앞부분) · [원문 보기](viewer 없으면 숨김)
- [ ] 미사용 구절: 접힌 상태 기본, 건수 표시, 펼치면 기존 칩 형태
- [ ] status=none: 경고 톤 배지 + 문구, 검색 구절 접힘 목록
- [ ] citation 없음: 기존 칩 렌더(회귀 없음)

#### 원문 뷰어
- [ ] 근거 문장 진한 음영 + 청크 나머지 옅은 음영, 매칭 실패 시 청크 전체 음영
- [ ] 인용 순서 ◀▶, 시작 위치는 클릭한 인용

#### 관리자 LLM 모델 페이지
- [ ] 활성 채팅 모델 드롭다운 + "설정 안 함(env 사용)" 선택지
- [ ] 저장 버튼(변경 없으면 비활성), 저장 중 표시, 422 메시지 노출
- [ ] 현재 적용 모델 + 출처(관리자/env/기본) 표시, 모델 품질 안내 문구

---

## 6. Error Handling

| 상황 | 처리 | 결과 |
|------|------|------|
| 레지스트리 조회 실패·run context 없음 | 라벨러가 기존 형식 `[출처: 파일]` 반환 | 인용 비적용(`not_applicable`) |
| 판정 예외·타임아웃 | `GroundedGenerator`가 기존처럼 warning(타입·스택) | `none/judge_failed` 저장 |
| 구조화 출력에 `citation_checks` 누락 | 빈 튜플로 간주 | `none/all_rejected` |
| 정리·저장 실패 | warning, 정리된 본문은 그대로 반환. 저장 실패 시 본문의 `[n]`은 남지만 칩이 없어 프론트는 플러그인을 켜지 않음(글자 그대로 표시) | 답변 정상 |
| enricher 조회 실패 | warning, 기존 칩 반환 | 기존 화면 |
| 판정 모델 설정 조회 실패 | env 공급자로 폴백, warning 1회/TTL | 기존 판정 |
| 관리자 PUT 잘못된 모델 | 422 코드(§4.2) | 저장 안 함 |

로그 규칙: 주장·근거 문장·답변 문장 원문은 로그에 싣지 않는다(건수·사유·run_id만).

---

## 7. Security Considerations

- [ ] 칩 `citation`은 기존 근거 칩과 같은 조회 권한 경로(실행 소유자·세션 접근)로만 나간다. 새 조회 API 없음
- [ ] 근거 문장(`evidence`)은 사용자가 이미 받은 검색 청크의 부분 문자열만 허용(D-07 결정적 확인) — 다른 문서 내용이 새지 않는다
- [ ] 관리자 API는 기존 관리자 의존성(`admin_graph_rag_router`와 같은 가드)
- [ ] 판정 프롬프트: `<cited_sources>`·`<citations>` 안의 지시를 따르지 말라는 문구 유지(인젝션 방어 기존 원칙)
- [ ] 프론트 렌더: 근거 문장은 텍스트 노드로만 렌더(HTML 주입 없음)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0 단위 | 정책·파서·청커·라벨러·enricher·공급자 | pytest / vitest | Do |
| L0 계약 | AST 경계, 스위치 off 프롬프트 동일성, DDL COMMENT | pytest | Do |
| L1 API | 관리자 설정 GET/PUT, 세션 소스 API citation 필드 | pytest TestClient | Do/Check |
| L2 UI | 인용 표시·접힘·배지·관리자 카드 | vitest + RTL + MSW | Do |
| L3 E2E | 업로드→질문→칩→원문→재진입 | 라이브(8011/5175 레시피) | Check |
| 벤치 | 판정 확장 품질 | pytest `-m llm` | Do(M5 끝) |

### 8.2 핵심 단위 테스트

| # | 대상 | 시나리오 |
|---|------|---------|
| U1 | `split_by_tokens` | 한글 문단을 작은 chunk_size로 잘라도 U+FFFD 0건, 청크 토큰 수 ≤ chunk_size, 이어 붙이면 원문 포함 |
| U2 | ES 본문 | page 있는 청크 → body.page 정수, 없는 청크 → 키 없음 |
| U3 | 라벨러 | 같은 chunk_id 재등장 시 같은 번호, run context 없으면 기존 형식, 쪽 없으면 `· N쪽` 생략 |
| U4 | 파서 | `[1, 3]`·`[1][3]`·코드 블록·레지스트리 밖 번호 |
| U5 | 정리 정책 | 탈락 제거·재번호(`[2][4][5]`, 4 탈락 → `[1][2]`), 같은 번호 반복, 0건 사유 3종 |
| U6 | 판정 어댑터 | citations 없으면 기존 체인·기존 프롬프트 문자열 동일(스냅샷), 있으면 확장 체인 |
| U7 | GroundedGenerator | 재작성 후 마지막 판정 사용, 문장 제거 후 인용 정리, 판정 실패 → judge_failed, 근거 판정 off → verify_citations 1회 |
| U8 | 답변 노드 | 스위치 off → 프롬프트 동일·저장 호출 0, on + 라벨 0건 → 지시 블록 없음, 이전 대화 `[n]` 제거 |
| U9 | enricher | 행 없음 → 키 없음, verified/none 분배, 상한으로 잘린 인용 문서 덧붙임 |
| U10 | 판정 모델 공급자 | 설정 모델 활성 → 그 모델, 비활성/없음/조회 예외 → env 공급자, 캐시 무효화 |
| U11 | AST 경계 | `answer_citation` 소비자 = {`answer_citation_di.py`}, DI 소비자 = {`main.py`} |
| F1 | `remarkCitationRefs` | 목록에 있는 번호만 변환, 코드 블록·인라인 코드 제외 |
| F2 | `useCitationView` | verified/none/없음 분기, 행 정렬, 미사용 계산 |
| F3 | `SourceCitation` | citation 없으면 기존 스냅샷 동일 |
| F4 | 원문 뷰어 | focus evidence 진한 음영, 매칭 실패 시 청크 음영 |
| F5 | 관리자 카드 | 로드·변경·저장·422 메시지 |

### 8.3 판정 확장 미니 벤치 (M5 종료 조건)

| 세트 | 구성 | 통과 기준 |
|------|------|----------|
| 기존 근거 판정 | 가상 정책 청크 5개 기반 정상 7 + 날조 3(원 벤치 픽스처가 저장소에 없어 재구성) | **확장 후 정상 오판 ⊆ 확장 전 오판**(새 오판 0), 날조 3/3 검출 유지 — v0.3 개정 |
| 인용 정상 | 같은 청크 기반 올바른 인용 10쌍 | 9/10 이상 supported, evidence 실재 9/10 이상 |
| 인용 양성 대조군 | 번호 뒤바꿈 4 + 값 변조 1 | **최종 정책 적용 후** 5/5 탈락 |

실패 시: D-05 지점에서 B안(별도 호출)으로 전환하고 Plan SC-6 비용 기준을 사용자와 재합의한다.

**실측 (2026-11-21, gpt-4o, `tests/infrastructure/hallucination/test_citation_judge_bench.py -m llm`)**

| 항목 | 결과 |
|------|------|
| 근거 판정 정상 오판 | 확장 전 4/7 → 확장 후 1/7 (새 오판 0). 확장 전 오판은 기존 판정기 성향(말을 바꾼 정상 문장을 근거 없음으로 판정, 2회 반복 동일) — 이 기능 범위 밖 |
| 날조 검출 | 확장 전후 3/3 |
| 올바른 인용 | supported 9/10, evidence 실재 9/10 |
| 틀린 인용 | 판정기 raw supported 3/5 → 정책 적용 후 남은 인용 0/5 |

벤치 1차에서 발견한 두 가지로 설계를 보강했다(v0.3):
1. 판정기가 틀린 번호 인용에 **실제 근거 청크의 문장**을 대며 supported 로 답한다 → D-07 보강(다른 청크에서만 발견되면 탈락).
2. 틀린 번호 인용이 근거 판정(unsupported_claims)으로 새어 맞는 문장이 "근거 없음"이 될 수 있다 → 확장 프롬프트에 "인용 번호가 틀렸다는 이유만으로 주장에 올리지 말 것", "evidence 는 지정 번호 청크에서만 복사"를 명시.
기준 개정 사유: 원래 기준(정상 오판 0, 결과 동일)은 확장 전 판정기가 이미 4/7 오판이라 확장의 영향을 가를 수 없다. 이 기능의 책임 범위는 "판정을 나쁘게 만들지 않는다"이다.

### 8.4 L3 E2E 시나리오

| # | Scenario | Expected |
|---|----------|----------|
| E1 | 스위치 on, 가계부채 PDF 새 업로드 → 질문 4종 | 본문 `[n]`, 인용 행에 쪽, 원문 보기에서 근거 문장 진한 음영 |
| E2 | 같은 대화 재진입 | E1과 같은 인용 |
| E3 | KB와 무관한 질문 | 인용 0 → "근거 확인 안 됨" 또는 검색 0이면 칩 없음 |
| E4 | 스위치 off 재시작 | 기존 칩·본문(번호 없음) |
| E5 | 관리자 카드에서 판정 모델 변경 | 다음 실행의 `judge_model`이 바뀜 |
| E6 | `ai_run.llm_call_count` on/off 비교 | 차이 0 (근거 판정 on 기준) |

### 8.5 Seed Data

| Entity | Count | Key |
|--------|:-:|-----|
| KB + 가계부채 PDF(새 업로드) | 1 | page 메타 포함 |
| 에이전트(내부 문서 검색, hybrid) | 1 | 지침 문장 |
| 활성 채팅 모델 | 2+ | 관리자 카드 드롭다운 |

---

## 9. Clean Architecture

### 9.1 Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `CitationPair`·`CitationCheckRequest`·`CitationCheck` | Domain | `idt/src/domain/hallucination/citation_check.py` |
| 인용 모델·파서·정리 정책·저장 포트 | Domain | `idt/src/domain/answer_citation/{models,parser,policy,ports}.py` |
| 판정 설정 VO·포트 | Domain | `idt/src/domain/grounding_judge_setting/{models,ports}.py` |
| 레지스트리·라벨러·서비스·enricher | Application | `idt/src/application/answer_citation/{registry,labeler,service,enricher}.py` |
| 판정 모델 공급자·설정 유스케이스 | Application | `idt/src/application/grounding_judge_setting/{provider,use_cases}.py` |
| 인용 저장소(V093) | Infrastructure | `idt/src/infrastructure/answer_citation/{models,repository}.py` |
| 판정 설정 저장소(V094) | Infrastructure | `idt/src/infrastructure/grounding_judge_setting/{models,repository}.py` |
| 판정 프롬프트·스키마 확장 | Infrastructure | `idt/src/infrastructure/hallucination/{prompts,schemas,adapter}.py` |
| 조립 | API | `idt/src/api/answer_citation_di.py`, `idt/src/api/grounding_judge_di.py` |
| 관리자 라우터 | Interfaces | `idt/src/api/routes/admin_grounding_judge_router.py` |

### 9.2 Seams (기존 파일 수정 지점 — 이 표 밖 수정 금지)

| # | 파일 | 변경 | off일 때 |
|---|------|------|---------|
| S1 | `infrastructure/chunking/base_token_chunker.py` | 경계 보정 | (상시) |
| S2 | `application/unified_upload/use_case.py`, `infrastructure/elasticsearch/es_index_mappings.py` | page 필드 | (상시) |
| S3 | `application/rag_agent/tools.py` | `citation_labeler: Any = None` 필드, `_format_results`·`_format_routed_results` 머리말 생성 1곳 | None → 기존 문자열 |
| S4 | `infrastructure/agent_builder/tool_factory.py` | 생성자 인자 `citation_labeler=None` 전달 | None |
| S5 | `domain/hallucination/grounding.py` | `GroundingVerdict.citation_checks=()`, `judge(..., citations=None)` | 기본값 |
| S6 | `infrastructure/hallucination/{adapter,prompts,schemas}.py` | 확장 체인(citations 있을 때만) | 기존 체인 |
| S7 | `application/hallucination/grounded_generation.py` | `run(..., citations=None)`·`GroundedResult.verdict`·`verify_citations()` | 기존 경로 |
| S8 | `application/agent_builder/workflow_compiler.py` | 생성자 `citation_service=None`, final_answer 지시 블록·이전 대화 정리·정리/저장 호출 | None → 기존 |
| S9 | `application/agent_run/run_sources.py` | `citation_enricher=None`, `build_for_runs` 에서 실행 묶음당 `load` 1회 + 실행마다 `apply`(Do module-7 확정 — `enrich_runs` 단일 호출 대신, 문서 칩 보충에 실행별 evidence 가 필요) | None |
| S9b | `domain/agent_run/source_policy.py` | `RunSourceItem.citation` + payload `citation` 키 (원문 뷰어 `viewer` 와 같은 방식, Do module-7 추가 — 초판 표 누락) | 키 없음 |
| S10 | `interfaces/schemas/agent_run_response.py` | `SourceItemDto.citation` | null |
| S10b | `domain/hallucination/grounding_edit.py` | `_boundaries` → 공개 `sentence_spans()` (동작 불변, 기존 호출부 그대로) | (상시) |
| S11 | `api/main.py` | DI 조립 2곳(인용·판정 모델), 판정 공급자 교체, 관리자 라우터 include | 스위치 off → None |
| S12 | `config.py`, `.env.example` | 키 3개 | 기본 off |
| F-S1 | `idt_front/src/types/chat.ts`, `types/sourceViewer.ts` | `citation` 타입, `SourceViewerTarget.focus` | 선택 필드 |
| F-S2 | `components/chat/{SourceCitation,MarkdownRenderer,MessageBubble}.tsx` | 분기·플러그인 prop | 기존 렌더 |
| F-S3 | `components/sourceViewer/*`, `utils/domHighlight.ts`, `store/sourceViewerStore.ts` | 진한 음영 클래스·focus | 기존 음영 |
| F-S4 | `pages/AdminLlmModelsPage/index.tsx`, `constants/api.ts`, `lib/queryKeys.ts` | 카드 삽입·엔드포인트·키 | — |

### 9.3 Dependency Rules

- `domain/answer_citation`은 `domain/hallucination/citation_check.py`만 참조한다(표준 라이브러리 외).
- 판정 포트(`domain/hallucination`)는 `answer_citation`을 모른다 — 인용 모듈을 떼어도 판정기는 컴파일된다.
- `application/answer_citation`의 소비자는 `api/answer_citation_di.py` 하나(AST 테스트). seam 파일은 duck typing으로만 호출한다.

---

## 10. Coding Convention Reference

### 10.1 Environment Variables

| Variable | Default | 소비 지점 |
|----------|---------|----------|
| `ANSWER_CITATION_ENABLED` | `false` | `api/answer_citation_di.py` `build_answer_citation()` — false면 라벨러·서비스·enricher 모두 None |
| `ANSWER_CITATION_REGISTRY_TTL_SECONDS` | `1800` | `application/answer_citation/registry.py` 생성자 |
| `ANSWER_CITATION_REGISTRY_MAX_RUNS` | `1000` | 같은 곳 |
| (기존) `GROUNDING_JUDGE_MODEL` | `gpt-4o` | 판정 모델 폴백(D-16) |

### 10.2 This Feature's Conventions

| Item | Convention |
|------|-----------|
| 라벨 형식 | on: `[출처 {n}: {filename} · {page}쪽]` (page 없으면 ` · {page}쪽` 생략) / off: 기존 `[출처: {source}]` |
| 인용 지시 문구 | `FinalAnswerCitationPolicy.instruction()` 한 곳(문구 SoT) |
| 판정 확장 문구 | `prompts.py` `GROUNDING_CITATION_ADDENDUM` 한 곳 |
| 코드 주석 | `# Design Ref: answer-citation-verification §x` |
| 프론트 상수 | `CITATION_STATUS`는 `src/types/chat.ts`에 `as const`(컴포넌트 파일 export 금지) |
| main.py | `ruff format` 전체 금지, Edit로만 |

---

## 11. Implementation Guide

### 11.1 File Structure (신규)

```
idt/
  db/migration/V093__create_ai_answer_citation.sql
  db/migration/V094__create_grounding_judge_setting.sql
  src/domain/hallucination/citation_check.py
  src/domain/answer_citation/{__init__,models,parser,policy,ports}.py
  src/domain/grounding_judge_setting/{__init__,models,ports}.py
  src/application/answer_citation/{__init__,registry,labeler,service,enricher}.py
  src/application/grounding_judge_setting/{__init__,provider,use_cases}.py
  src/infrastructure/answer_citation/{__init__,models,repository}.py
  src/infrastructure/grounding_judge_setting/{__init__,models,repository}.py
  src/api/answer_citation_di.py
  src/api/grounding_judge_di.py
  src/api/routes/admin_grounding_judge_router.py
  tests/... (모듈별 미러 + test_module_boundaries.py + llm 벤치)
idt_front/src/
  utils/remarkCitationRefs.ts
  hooks/{useCitationView,useGroundingJudgeSetting}.ts
  services/groundingJudgeService.ts
  types/groundingJudge.ts
  components/chat/{CitationRef,CitationList,UnusedSourcesDisclosure,CitationNoneBadge}.tsx
  pages/AdminLlmModelsPage/GroundingJudgeModelCard.tsx
```

### 11.2 Implementation Order

1. [ ] M1 청킹 U+FFFD → M2 ES page (버그 수정, 상시)
2. [ ] M3 판정 모델 설정 백엔드 → M4 판정 모델 카드 프론트
3. [ ] M5 인용 도메인·레지스트리·라벨러(S3·S4)
4. [ ] M6 판정 확장·답변 노드 결선·저장(S5~S8, V093) + 벤치
5. [ ] M7 칩 계약·enricher·DI·AST(S9~S12)
6. [ ] M8 프론트 인용 표시 → M9 문장 단위 음영
7. [ ] L3 라이브 확인(Check 단계)

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | 주요 파일 | 예상 |
|--------|-----------|-------------|----------|:----:|
| 청킹 U+FFFD | `module-1` | 토큰 경계를 UTF-8 글자 경계로 보정 | S1 + 테스트 | 小 |
| ES page | `module-2` | ES 본문·매핑에 page | S2 + 테스트 | 小 |
| 판정 모델 설정 BE | `module-3` | V094·VO·저장소·공급자·관리자 API·DI | §9.1 grounding_judge_setting | 中 |
| 판정 모델 카드 FE | `module-4` | 서비스·훅·카드 | F-S4 | 小 |
| 인용 도메인·라벨 | `module-5` | VO·파서·정리 정책·레지스트리·라벨러, S3·S4 | answer_citation domain/app | 中 |
| 판정 확장·결선 | `module-6` | S5~S8, 서비스·V093 저장소, 미니 벤치 | hallucination·workflow_compiler | 大 |
| 칩 계약·DI | `module-7` | enricher·S9~S12·AST 경계 | run_sources·main | 中 |
| 인용 표시 FE | `module-8` | 타입·remark·칩 정리·배지 | F-S1·F-S2 | 中 |
| 문장 음영 FE | `module-9` | focus·진한 음영 | F-S3 | 中 |

#### Recommended Session Plan

| Session | Phase | Scope | 비고 |
|---------|-------|-------|------|
| 1 | Do | `--scope module-1,module-2` | worktree 생성, 커밋 2개 |
| 2 | Do | `--scope module-3,module-4` | 판정 모델 풀스택(인용과 독립, 먼저 머지 가능) |
| 3 | Do | `--scope module-5` | |
| 4 | Do | `--scope module-6` | OpenAI 크레딧 필요(벤치). 벤치 실패 시 D-05로 B안 협의 |
| 5 | Do | `--scope module-7` | 백엔드 전체 회귀 |
| 6 | Do | `--scope module-8,module-9` | 프론트 전체 회귀 |
| 7 | Check | `/pdca analyze` + L3 | 라이브 E2E |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-20 | 최초 작성 — C안 선택, 재번호·관리자 카드 위치 확정 | 배상규 |
| 0.2 | 2026-11-20 | Do module-5: 정규화(종결 부호 뒤 번호 이동)·근거 문장 비교 기준 확정 | 배상규 |
| 0.3 | 2026-11-21 | Do module-6 벤치: D-07 보강(다른 청크 근거 탈락), 확장 프롬프트 2문장, §8.3 기준 개정·실측 기록. 저장 judge_model 은 미기록(None) — 판정 모델 이름을 노출하는 경로가 없어 이월 | 배상규 |
| 0.4 | 2026-11-21 | Do module-7: S9 호출 형태(load/apply) 확정, S9b(source_policy) 이음매 추가. main.py 새 import 의 E402 는 파일 구조상 기존 import 와 동일(수용) | 배상규 |
| 0.5 | 2026-11-21 | Do module-8·9: useCitationView→순수 유틸, 위첨자 원문 열기는 원문 뷰어(viewer) 있을 때만, 근거 문장 음영은 추가 구절 + data-spv-focus 방식(현재 위치=근거 문장, 청크는 옅게) | 배상규 |
