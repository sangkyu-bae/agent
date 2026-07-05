# LLM Wiki 기반 지식베이스 도입 분석 레포트

> **작성일**: 2026-06-28
> **대상**: sangplusbot AI Agent 플랫폼 (`idt/` 백엔드 + `idt_front/` 프론트엔드)
> **목적**: 현재 RAG/웹서치 중심 지식베이스의 "지속 발전 한계"를 진단하고,
> "LLM Wiki" 방식의 3가지 해석을 비교하여 우리 프로젝트에 맞는 도입 방향을 설계한다.
> **성격**: 기술 설계 검토(PDCA Plan 입력) + 포트폴리오용 심층 분석 겸용

---

## 0. Executive Summary

| 항목 | 내용 |
|------|------|
| **문제** | 현재 에이전트 지식은 **Pull-only**(추론 시 읽기 전용)다. 대화·검색에서 얻은 지식이 **어디에도 축적되지 않아** 시간이 지나도 시스템이 똑똑해지지 않는다 (= 지속 발전 어려움). |
| **핵심 진단** | RAG/웹서치/MCP는 모두 "외부 소스를 그때그때 가져오는" 구조. **쓰기 루프(write-back)가 없다.** 대화 요약조차 KB로 환류되지 않음(코드/메모리상 확인). |
| **LLM Wiki 정의** | (A) 자가 진화 지식베이스, (B) LLM의 문서 위키화(정제 정적층), (C) 사람+LLM 협업 위키 — 세 해석은 **배타적이지 않고 레이어로 결합 가능**. |
| **추천** | **B → A 단계적 도입, C는 거버넌스 게이트로 병행.** 1차로 "LLM 위키화 정적층"(B)을 RAG 위에 얹고, 2차로 검증 게이트가 붙은 "자가 진화"(A)를 추가한다. |
| **포트폴리오 가치** | GraphRAG·Self-RAG·MemGPT·HippoRAG 등 2024~2025 업계 핵심 흐름을 우리 DDD/LangGraph 구조에 녹여낸 "**Self-Improving RAG**" 사례로 차별화 가능. |

**한 줄 결론**: "검색을 더 잘하기"가 아니라 **"검색한 것을 기억하고 정제해 다음에 더 잘 답하기"** 로 패러다임을 옮기는 작업이다. 우리 아키텍처(DDD + LangGraph + 관측 테이블)는 이를 받기에 이미 절반쯤 준비돼 있다.

---

## 1. 문제 정의 — 왜 "지속 발전이 어렵다"고 느끼는가

사용자의 직관("웹서치나 RAG에서 가져오기만 하면 지속 발전이 어렵다")은 정확하다. 코드 레벨에서 그 이유를 구조적으로 정리하면:

### 1-1. 현재는 Pull-only 아키텍처 (쓰기 루프 부재)

탐색 결과, 우리 시스템의 지식 흐름은 **단방향 읽기**다.

- **벡터 스토어는 추론 중 읽기 전용**이다. 쓰기는 오직 명시적 문서 인제스트(`idt/src/application/ingest/ingest_use_case.py`)로만 발생한다.
- **대화 요약은 KB로 환류되지 않는다.** `idt/src/application/conversation/use_case.py`는 6턴 초과 시 LLM 요약을 만들지만, 그 요약은 **벡터화되지 않고 KB에 추가되지 않는다** (탐색에서 "Chat summaries are not vectorized or added to knowledge base"로 확인, 메모리 노트 `chart-rendering-general-chat-only` 등과 동일 맥락의 보수적 설계).
- **웹서치 결과는 1회성**이다. `idt/src/infrastructure/web_search/tavily_tool.py`로 가져온 결과는 응답 생성에만 쓰이고, `ai_retrieval_source` 테이블에 **감사 로그로만** 남는다(collection_name='tavily_web'). 다음 질문에서 재활용되지 않는다.

```
[현재] 질문 → (RAG/웹서치/MCP에서 Pull) → 답변 → 끝
                                              ↑
                            얻은 지식이 여기서 증발한다
```

### 1-2. 그래서 생기는 구체적 증상

| 증상 | 근본 원인 |
|------|-----------|
| 같은 질문을 반복해도 매번 동일 비용의 웹서치/검색 발생 | 검색 결과 캐싱·환류 없음 |
| 어제 웹서치로 알아낸 사실을 오늘 또 모름 | 휘발성 컨텍스트 |
| 문서가 늘수록 검색 노이즈 증가, 정제된 "정답 요약" 부재 | 원본 청크만 존재, 합성·정제층 없음 |
| 사용자가 "이건 이렇게 답해"라고 알려줘도 학습 안 됨 | 피드백 → KB 반영 경로 없음 |
| 여러 문서에 흩어진 사실을 연결한 답을 못 함 | 청크 단위 검색, 엔티티/관계 그래프 없음 |

이것이 "지속 발전이 어렵다"의 정체다. **시스템이 경험으로부터 학습(축적)하지 않는다.**

---

## 2. 현재 아키텍처 정밀 진단 (LLM Wiki 도입의 출발점)

새 구조를 얹으려면 기존 구조를 정확히 알아야 한다. 탐색으로 확인한 현 지식 소싱 스택:

### 2-1. 지식 소스 인벤토리

| 소스 | 접근 방식 | 구현 위치 | 쓰기 가능? |
|------|-----------|-----------|:---:|
| 내부 문서(RAG) | `internal_document_search` 툴 | `idt/src/application/hybrid_search/use_case.py` (BM25+Vector RRF 융합) | 인제스트만 |
| 웹 (Tavily) | `tavily_search` 툴 | `idt/src/infrastructure/web_search/tavily_tool.py` | ❌ (로그만) |
| 대화 이력 | LangGraph state | `idt/src/application/conversation/use_case.py` (6턴↑ 요약) | 세션 한정 |
| Excel 분석 | analysis worker | `workflow_compiler.py` | ❌ (요청 1회성) |
| MCP 외부 툴 | 동적 로딩 | `idt/src/infrastructure/mcp_registry/mcp_tool_loader.py` | 외부 의존 |
| 코드 실행 | `python_code_executor` | sandboxed | ❌ |

### 2-2. 강점 — LLM Wiki를 받을 준비가 된 부분

우리 구조에는 이미 자가 진화 KB의 **토대가 절반 깔려 있다**:

1. **하이브리드 검색 + RRF 융합** (`hybrid_search/use_case.py`): 위키 정제층을 추가해도 동일 인터페이스로 검색 가능. `RagToolConfig`의 `collection_name`/`search_mode`/`metadata_filter`만 확장하면 됨 (`idt/src/domain/agent_builder/rag_tool_config.py`).
2. **관측 인프라** (`ai_retrieval_source`, `ai_run_step`, RunTracker): "어떤 지식이 실제로 답에 기여했는가"를 이미 추적 중 → **위키 환류의 신호원으로 그대로 재활용 가능**(M4/M5 추적).
3. **DDD 레이어 분리**: ingest ≠ retrieval 분리가 명확 → 새로운 "wiki write-back" use case를 application 레이어에 깔끔히 추가 가능. `verify-architecture` 스킬로 의존성 규칙 검증도 가능.
4. **LangGraph 동적 그래프** (`workflow_compiler.py`): 노드 추가(예: `wiki_writer` 노드)가 구조적으로 자연스러움.
5. **임베딩/벡터 팩토리 추상화** (`embedding_factory.py`, `qdrant_vectorstore.py`): 새 컬렉션(위키 전용) 추가가 저비용.

### 2-3. 공백 — 새로 만들어야 하는 것

- 추론 결과/대화/검색을 **KB로 되돌리는 write-back 경로** (현재 전무)
- 환류된 지식의 **검증·중복제거·버전 관리** (거버넌스)
- 정제된 지식의 **신뢰도/출처/만료(TTL) 메타데이터**
- 엔티티-관계 그래프 (선택, GraphRAG 방향일 때)

---

## 3. "LLM Wiki" 3가지 해석 — 정의와 정밀 비교

"LLM Wiki"는 단일 정의가 아니다. 세 가지로 해석되며, **레이어로 보면 상호 보완적**이다.

### 3-A. 자가 진화 지식베이스 (Self-Curating / Self-Evolving KB)

> 에이전트가 대화·검색·추론 결과를 **스스로 구조화된 위키 문서로 누적·갱신**한다. 시간이 지날수록 지식이 성장한다.

- **업계 대응**: MemGPT/Letta(계층적 메모리), Self-RAG(자기 반성 검색), Reflexion(경험 메모), HippoRAG(해마형 인덱싱), Generative Agents(메모리 스트림+reflection).
- **메커니즘**: `대화/검색 → LLM이 "기억할 가치" 판단 → 위키 항목 생성/병합 → 임베딩 → 다음 검색에 노출`
- **우리 적용**: LangGraph에 `wiki_writer` 노드 추가, 별도 `wiki_knowledge` Qdrant 컬렉션 + ES 인덱스, `ai_retrieval_source` 신호로 "유용했던 검색"을 환류.

| 평가 | 내용 |
|------|------|
| 👍 장점 | 진짜 "지속 발전". 반복 질문 비용↓, 시간이 지날수록 강해짐. 포트폴리오 임팩트 최고. |
| 👎 단점 | **환각 누적 위험**(잘못된 지식이 KB에 박히면 증폭), 중복·모순 관리 난이도, 검증 게이트 필수. |
| 적합도 | ★★★★☆ — 우리 관측 인프라 덕에 신호 확보가 쉬움. 단, 거버넌스(3-C) 없이는 위험. |

### 3-B. LLM의 문서 위키화 (정제 정적층 / Distillation Layer)

> 원본 문서·웹서치 결과를 LLM이 **정제·요약·구조화하여 일관된 위키 아티클로 변환**하고, 검색 시 원본 청크 대신(또는 함께) 이 정제층을 사용한다.

- **업계 대응**: RAPTOR(재귀 요약 트리), GraphRAG의 community summary, "proposition-based indexing"(명제 단위 색인), 문서 → Q&A 합성.
- **메커니즘**: `인제스트 시 또는 배치로 → 원본 청크 군집 → LLM 요약/명제화 → 위키 아티클 컬렉션 생성`
- **우리 적용**: 기존 `chunk_and_index/use_case.py` 파이프라인 뒤에 **합성 단계** 추가. 검색은 `RagToolConfig.search_mode`에 "wiki" 모드를 더하거나, 위키 컬렉션을 우선 검색 후 원본으로 폴백.

| 평가 | 내용 |
|------|------|
| 👍 장점 | **저위험**(사람이 넣은 원본 기반, 환각 누적 없음). 검색 노이즈↓, 답변 일관성↑. 즉시 가치. |
| 👎 단점 | "진화"는 아님(인제스트 시점 정제에 가까움). 합성 비용(LLM 토큰), 원본 변경 시 재합성 필요. |
| 적합도 | ★★★★★ — 기존 파이프라인 확장만으로 가능. **가장 빠른 ROI, 1차 도입 1순위.** |

### 3-C. 사람+LLM 협업 위키 (Governed / Human-in-the-loop Wiki)

> 운영자/사용자가 편집하는 내부 위키를 권위 있는(authoritative) 지식 소스로 두고, LLM은 초안 작성·검증·갱신 제안을 보조한다.

- **업계 대응**: Notion AI/Glean 류 엔터프라이즈 지식관리, RLHF의 KB판, "human approval gate"(LangChain HumanInTheLoopMiddleware).
- **메커니즘**: `LLM 초안 제안 → 사람 승인/편집 → 승인된 항목만 KB 반영` (A의 안전장치 역할도 겸함)
- **우리 적용**: 위키 항목에 `status`(draft/approved/deprecated) + `editor`/`reviewer` 메타. 프론트에 위키 관리 UI(기존 `RagConfigPanel.tsx`, `ToolPickerModal.tsx`와 유사 패턴). 금융/정책 도메인(우리 도메인)에서 **특히 중요** — 보수적 동작 원칙과 정합.

| 평가 | 내용 |
|------|------|
| 👍 장점 | **신뢰성 최고**(승인된 지식만). 금융/정책 규제 친화. A의 환각 위험을 게이트로 차단. |
| 👎 단점 | 사람 운영 비용, 자동화·속도 희생. UI/RBAC 추가 개발(단, 우리 RBAC는 이미 있음). |
| 적합도 | ★★★★☆ — A의 필수 안전장치로서 가치. 단독으로는 "자동 발전" 욕구를 못 채움. |

### 3-D. 세 방식 종합 비교표

| 기준 | A. 자가 진화 | B. 위키화 정적층 | C. 협업 위키(거버넌스) |
|------|:---:|:---:|:---:|
| 지속 발전성 | ★★★★★ | ★★☆ | ★★★ |
| 도입 난이도(낮을수록↑) | ★★ | ★★★★★ | ★★★ |
| 환각/오류 위험(낮을수록↑) | ★★ | ★★★★ | ★★★★★ |
| 즉시 ROI | ★★ | ★★★★★ | ★★★ |
| 금융/정책 도메인 적합 | ★★★ | ★★★★ | ★★★★★ |
| 운영 비용(낮을수록↑) | ★★★ | ★★★★ | ★★ |
| 기존 코드 재사용도 | ★★★★ | ★★★★★ | ★★★★ |
| 포트폴리오 차별성 | ★★★★★ | ★★★ | ★★★ |

**결론**: 세 방식은 **트레이드오프 축이 다르다**(발전성 vs 안전성 vs 비용). 우리에게 최적은 **레이어로 결합**하는 것.

---

## 4. 추천 아키텍처 — "Self-Improving RAG" (B+A+C 결합)

### 4-1. 단계적 도입 전략

```
Phase 1 (B)        Phase 2 (C 게이트)        Phase 3 (A)
정제 정적층    →   거버넌스 게이트 추가   →   자가 진화 루프 활성화
(저위험·즉시ROI)    (승인 워크플로)            (write-back + 검증)
```

핵심 원칙: **A(자가 진화)는 절대 C(검증 게이트) 없이 켜지 않는다.** 금융/정책 도메인의 보수적 동작 원칙(CLAUDE.md §1)과 직결.

### 4-2. 목표 아키텍처 다이어그램

```
                          ┌─────────────────────────────────┐
   사용자 질문 ──────────▶│   LangGraph Supervisor (기존)    │
                          └─────────────────────────────────┘
                                    │ worker 라우팅
                ┌───────────────────┼────────────────────┐
                ▼                   ▼                    ▼
        ┌──────────────┐   ┌──────────────┐    ┌──────────────┐
        │ WikiSearch   │   │ internal_doc │    │ tavily_web   │
        │ (NEW, 우선)  │   │ _search(기존)│    │ search(기존) │
        └──────┬───────┘   └──────┬───────┘    └──────┬───────┘
               │   (miss 시 폴백)   │                   │
               └───────────────────┴───────────────────┘
                                    │ 답변 생성
                                    ▼
                          ┌─────────────────────┐
                          │  wiki_writer 노드    │ ← Phase 3 (A)
                          │  "기억할 가치?" 판단 │
                          └─────────┬───────────┘
                                    │ 후보 생성
                                    ▼
                          ┌─────────────────────┐
                          │  Governance Gate     │ ← Phase 2 (C)
                          │  draft→review→approve│
                          └─────────┬───────────┘
                                    │ 승인분만
                                    ▼
                          ┌─────────────────────┐
                          │  wiki_knowledge      │ ← Phase 1 (B)
                          │  컬렉션(Qdrant+ES)   │  ← 정제층 + 진화분
                          └─────────────────────┘
```

### 4-3. 위키 항목 데이터 모델 (제안)

DDD 도메인 엔티티로 신설 (`idt/src/domain/wiki/`):

```python
# 개념 스케치 — 실제 구현은 TDD(idt:tdd 스킬)로 진행
class WikiArticle:
    id: str
    title: str                    # 위키 항목 제목 (검색 키)
    content: str                  # 정제된 본문 (명제 단위 권장)
    source_type: str              # "distilled" | "conversation" | "websearch" | "human"
    source_refs: list[str]        # 원본 추적 (ai_retrieval_source FK, doc id 등)
    status: str                   # "draft" | "approved" | "deprecated"  ← 거버넌스
    confidence: float             # 0~1, 환류 신호 기반
    editor_id / reviewer_id: str  # 사람 승인 추적
    valid_until: datetime | None  # TTL (웹서치 출처는 만료 권장)
    embedding: list[float]        # wiki_knowledge 컬렉션
    version: int                  # 버전 관리
    created_at / updated_at
```

이 모델이 세 방식을 **하나로 통합**한다: `source_type`이 B/A/C를 구분, `status`가 C 게이트, `confidence`/`valid_until`이 A의 안전장치.

### 4-4. 환각 누적 방지 장치 (A의 핵심 리스크 대응)

1. **검증 게이트**: 자동 생성분은 `status=draft`로만 시작 → 승인 전 검색 노출 안 함(또는 confidence 가중치↓).
2. **출처 추적 필수**: `source_refs` 없는 항목은 KB 진입 금지.
3. **TTL/만료**: 웹서치 기반 항목은 `valid_until` 설정, 만료 시 재검증.
4. **모순 탐지**: 신규 항목 인입 시 기존 항목과 의미 충돌 검사(임베딩 유사도 + LLM 판정).
5. **신뢰도 감쇠**: `ai_retrieval_source`에서 "실제 답에 기여했고 사용자 만족"한 항목만 confidence↑. 안 쓰이면 감쇠.

### 4-5. 기존 코드 변경 지점 (최소 침습)

| 영역 | 변경 내용 | 파일 |
|------|-----------|------|
| 도메인 | `WikiArticle` 엔티티 + 정책 신설 | `idt/src/domain/wiki/` (신규) |
| 애플리케이션 | `DistillToWikiUseCase`(B), `WikiWriteBackUseCase`(A), `WikiReviewUseCase`(C) | `idt/src/application/wiki/` (신규) |
| 검색 | `search_mode`에 "wiki" 추가 또는 위키 우선 검색 | `idt/src/domain/agent_builder/rag_tool_config.py` (확장) |
| 그래프 | `wiki_writer` 노드 추가 | `idt/src/application/agent_builder/workflow_compiler.py` (확장) |
| 인프라 | `wiki_knowledge` Qdrant 컬렉션 + ES 인덱스, 리포지토리 | `idt/src/infrastructure/wiki/` (신규) |
| 마이그레이션 | `wiki_article` 테이블 | `db/migration/` (`db-migration` 스킬 활용) |
| 프론트 | 위키 관리/승인 UI | `idt_front/src/components/wiki/` (신규, `RagConfigPanel` 패턴 재사용) |
| API 계약 | 스키마 동기화 | `api-cotract` 스킬 (CLAUDE.md §4-1 필수) |

---

## 5. 트레이드오프 & 리스크 정리

| 리스크 | 영향 | 완화책 |
|--------|------|--------|
| **환각 누적** (A) | 잘못된 지식이 증폭되어 답변 신뢰도 붕괴 | C 게이트 + 출처 필수 + 모순 탐지 (4-4) |
| **합성 비용** (B) | 인제스트/배치 시 LLM 토큰 비용↑ | 변경분만 증분 재합성, 저빈도 배치 |
| **운영 부담** (C) | 사람 승인 병목 | 고신뢰 자동승인 + 저신뢰만 사람 검토 (하이브리드) |
| **검색 혼란** | 위키 vs 원본 중복 노출 | RRF 가중치 조정, 위키 우선+원본 폴백 |
| **저장 비용** | 컬렉션 2배 | TTL/deprecated 정리 배치 |
| **테스트 복잡도** | 환류 루프 검증 어려움 | TDD 강제(`idt:tdd`), `zero-script-qa`로 로그 기반 검증 |
| **도메인 규제** | 금융/정책 오답 리스크 | 보수적 기본값(draft 우선), 감사 로그(이미 보유) |

---

## 6. 포트폴리오 관점 — 차별화 포인트

> 사용자는 저축은행 여신 개발 3년10개월 경력으로 AI/RAG 포트폴리오를 준비 중(메모리 `user_profile`). 이 기능은 강력한 차별화 소재다.

### 6-1. 왜 임팩트가 큰가

- 대부분의 RAG 포트폴리오는 "검색 → 생성"에서 멈춘다. **"학습하는 RAG(Self-Improving)"는 한 단계 위 서사**다.
- 2024~2025 업계 핵심 흐름(GraphRAG, Self-RAG, RAPTOR, MemGPT, HippoRAG)을 **실제 프로덕션급 DDD/LangGraph 구조에 녹였다**는 점이 강점.
- 금융/정책 도메인의 **거버넌스(C)** 를 설계에 포함 → "규제 산업을 아는 개발자"라는 본인 강점과 직결.

### 6-2. 이력서/면접용 한 문장

> "웹서치·RAG 결과가 휘발되던 Pull-only 구조를, **검증 게이트가 달린 자가 진화 지식베이스(Self-Improving RAG)** 로 전환해 반복 질의 비용을 낮추고 답변 일관성을 높였습니다. 관측 테이블(`ai_retrieval_source`)의 기여도 신호를 환류 신호로 재활용하고, 금융 도메인 특성상 자동 생성 지식은 human-in-the-loop 승인 게이트를 거치도록 설계했습니다."

### 6-3. 참고 업계 사례 (포트폴리오 레퍼런스)

| 기법 | 한 줄 | 우리 매핑 |
|------|-------|-----------|
| **RAPTOR** | 청크 재귀 요약 트리 | B 정제층의 합성 알고리즘 |
| **GraphRAG** (Microsoft) | 엔티티-관계 그래프 + community summary | B+A의 그래프 확장(선택) |
| **Self-RAG** | 자기 반성으로 검색 필요/품질 판단 | A의 "기억할 가치" 판단 노드 |
| **MemGPT/Letta** | 계층적 장기 메모리 | A의 write-back + 신뢰도 감쇠 |
| **HippoRAG** | 해마형 단일-스텝 다중홉 인덱싱 | A의 항목 연결(고도화) |
| **Reflexion** | 경험을 언어 메모리로 누적 | A의 대화 환류 |

---

## 7. 결론 & 다음 단계

### 7-1. 결론

"LLM Wiki" 도입은 **할 가치가 충분하다.** 단, "위키"라는 단어를 어떻게 해석하든 **공통 본질은 "쓰기 루프(write-back)의 부재를 메우는 것"** 이다. 우리 아키텍처(DDD + LangGraph + 관측 테이블)는 이를 받을 토대가 절반 이상 갖춰져 있어 ROI가 높다.

권장은 **단일 방식이 아니라 레이어 결합**:
1. **Phase 1 — B(정제 정적층)**: 저위험·즉시 ROI. 기존 인제스트 파이프라인 확장만으로 검색 품질·일관성 즉시 개선.
2. **Phase 2 — C(거버넌스 게이트)**: A를 안전하게 켜기 위한 필수 안전장치. 금융 도메인 정합.
3. **Phase 3 — A(자가 진화)**: 진정한 "지속 발전". 게이트가 갖춰진 뒤에만 활성화.

### 7-2. 다음 단계 (PDCA 연결)

이 레포트는 **분석/탐색(Plan 입력)** 단계다. 권장 진행:

```
/pdca plan llm-wiki-knowledge-base      # 이 레포트를 근거로 Plan 문서화
   → /pdca design llm-wiki-knowledge-base   # 도메인 모델·노드·마이그레이션 상세 설계
      → idt:tdd 로 Phase 1(B)부터 Red→Green 구현
         → api-cotract 로 프론트 타입 동기화
            → db-migration 으로 wiki_article 테이블 생성
```

**우선 결정 필요 사항** (Plan에서 확정):
- Phase 1 범위: 전체 컬렉션 정제 vs 특정 에이전트 한정 파일럿?
- 정제 단위: 문서 요약 vs 명제(proposition) 색인 vs RAPTOR 트리?
- 그래프 확장(GraphRAG) 포함 여부 — MVP에서는 제외 권장.

---

### 부록 A. 현재 핵심 파일 레퍼런스 (탐색 확인)

| 영역 | 파일 |
|------|------|
| 하이브리드 검색 | `idt/src/application/hybrid_search/use_case.py` |
| RAG 설정 VO | `idt/src/domain/agent_builder/rag_tool_config.py` |
| 인제스트 | `idt/src/application/ingest/ingest_use_case.py` |
| 청킹/색인 | `idt/src/application/chunk_and_index/use_case.py` |
| 벡터 스토어 | `idt/src/infrastructure/vector/qdrant_vectorstore.py` |
| 웹서치 | `idt/src/infrastructure/web_search/tavily_tool.py` |
| 대화 메모리 | `idt/src/application/conversation/use_case.py` |
| 그래프 컴파일 | `idt/src/application/agent_builder/workflow_compiler.py` |
| 에이전트 실행 | `idt/src/application/agent_builder/run_agent_use_case.py` |
| 프론트 RAG 패널 | `idt_front/src/components/agent-builder/RagConfigPanel.tsx` |
| 관측 테이블 | `ai_retrieval_source`, `ai_run_step` (RunTracker) |
