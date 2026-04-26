# 커스텀 RAG 도구 — 기능 상세 설명서

> Feature ID: CUSTOM-RAG-TOOL-001  
> 작성일: 2026-04-21  
> 대상 시스템: sangplusbot AI Agent Platform (idt 백엔드 + idt_front 프론트엔드)

---

## 1. 이 기능은 무엇인가

에이전트 빌더에서 RAG(Retrieval-Augmented Generation) 도구의 **검색 범위와 동작 방식을 에이전트별로 커스텀 설정**할 수 있는 기능이다.

쉽게 말해, 기존에는 에이전트를 만들 때 "내부 문서 검색" 도구를 붙이면 **시스템에 등록된 모든 문서**를 대상으로 검색했다. 이 기능을 통해 "**금융 부서 문서만 검색하는 에이전트**", "**기술 매뉴얼만 검색하는 에이전트**"처럼 검색 대상을 좁히고 검색 방식을 조정할 수 있게 된다.

---

## 2. 왜 필요한가

### 2-1. 기존 시스템의 한계

sangplusbot 플랫폼에서 에이전트를 생성할 때 `internal_document_search` 도구를 선택하면, 아래와 같이 동작한다:

```
사용자 질문: "올해 금융 투자 한도 정책이 뭐야?"

기존 동작:
  → Elasticsearch 전체 인덱스 검색 (모든 부서, 모든 카테고리)
  → Qdrant 전체 컬렉션 벡터 검색 (모든 문서)
  → 결과 5개 반환 (고정)
  → 하이브리드 모드 (고정)
```

이 방식의 문제점:

| 문제 | 구체적 상황 | 영향 |
|------|-----------|------|
| **검색 범위를 좁힐 수 없음** | 금융팀 에이전트인데 HR 문서, 기술 매뉴얼까지 검색 결과에 포함됨 | 불필요한 정보가 LLM 컨텍스트를 차지하여 답변 품질 저하 |
| **파라미터 조정 불가** | 간단한 질문에도 top_k=5로 고정, 정밀 검색이 필요해도 BM25를 끌 수 없음 | 비용 낭비 (불필요한 임베딩 연산) 또는 검색 정확도 저하 |
| **다중 검색 범위 불가** | "금융 문서에서 정책을 찾고, 기술 매뉴얼에서 절차를 찾아줘" 같은 요청 불가 | 하나의 에이전트가 여러 문서 영역을 구분하여 검색할 수 없음 |
| **도구 이름/설명 고정** | 모든 에이전트에서 도구 이름이 "내부 문서 검색"으로 동일 | LLM이 여러 RAG 도구 중 맥락에 맞는 것을 선택하지 못함 |

### 2-2. 실제 업무 시나리오에서의 필요성

이 플랫폼은 **금융/정책 문서에 특화된 RAG 기반 질의응답 시스템**이다. 실제 사용 환경에서는 다음과 같은 요구가 발생한다:

**시나리오 1: 부서별 전문 에이전트**
```
금융팀 관리자가 "금융 규제 정책 전문 에이전트"를 만들고 싶다.
→ 검색 대상: finance_docs 컬렉션만
→ 메타데이터 필터: department=finance, category=policy
→ top_k: 10 (정책 문서는 많은 맥락이 필요)
→ 도구 이름: "금융 규제 정책 검색"
→ 도구 설명: "금융 규제 및 투자 한도 관련 내부 정책을 검색합니다"
```

**시나리오 2: 다중 문서 영역 에이전트**
```
고객 지원팀이 "종합 문의 응대 에이전트"를 만들고 싶다.
→ RAG 도구 1: "상품 정보 검색" (collection=products, metadata={category: info})
→ RAG 도구 2: "약관/규정 검색" (collection=regulations, metadata={type: terms})
→ LLM이 질문 맥락에 따라 적절한 도구를 선택
```

**시나리오 3: 자동 에이전트 빌더 연동**
```
사용자: "금융 관련 문서만 검색하는 에이전트 만들어줘"
→ LLM이 자동으로 metadata_filter={department: finance} 추론
→ tool_name="금융 문서 검색" 자동 생성
→ 사용자가 수동으로 설정할 필요 없음
```

---

## 3. 무엇이 변경되었는가

### 3-1. 변경 전후 비교

| 항목 | 변경 전 | 변경 후 |
|------|--------|---------|
| 검색 대상 | 시스템 전체 문서 (고정) | 에이전트별 컬렉션/메타데이터로 제한 가능 |
| top_k | 5 (하드코딩) | 1~20 범위에서 에이전트별 설정 |
| 검색 모드 | hybrid (고정) | hybrid / vector_only / bm25_only 선택 |
| RRF 파라미터 | 60 (하드코딩) | 에이전트별 조정 가능 |
| 도구 이름 | "내부 문서 검색" (고정) | 에이전트별 커스텀 (예: "금융 정책 검색") |
| 도구 설명 | 범용 설명 (고정) | 에이전트 목적에 맞는 설명으로 커스텀 |
| 같은 도구 복수 사용 | 불가 (unique 제약) | 가능 (worker_id 기준 unique로 변경) |
| 자동 빌더 | RAG 설정 추론 불가 | 사용자 요청에서 검색 범위 자동 추론 |

### 3-2. 변경된 시스템 구성 요소

```
[에이전트 생성 요청]
     │
     │  tool_configs: {                    ← 신규: 도구별 설정
     │    "internal_document_search": {
     │      collection_name: "finance_docs",
     │      metadata_filter: {department: "finance"},
     │      top_k: 10,
     │      search_mode: "hybrid",
     │      tool_name: "금융 정책 검색",
     │      tool_description: "금융 관련 정책을 검색합니다"
     │    }
     │  }
     ▼
[CreateAgentUseCase]
     │  tool_configs를 WorkerDefinition.tool_config에 매핑
     ▼
[DB 저장: agent_tool.tool_config (JSON)]    ← 신규 컬럼
     │
     ▼
[에이전트 실행 요청]
     │
     ▼
[WorkflowCompiler]
     │  WorkerDefinition.tool_config → ToolFactory.create()
     ▼
[ToolFactory]
     │  tool_config → RagToolConfig VO로 변환
     │  RagToolConfig의 값으로 InternalDocumentSearchTool 생성
     ▼
[InternalDocumentSearchTool]
     │  search_mode에 따라 검색 방식 분기:
     │    hybrid    → BM25 + Vector 병렬 실행
     │    vector_only → Vector만 실행 (bm25_top_k=0)
     │    bm25_only  → BM25만 실행 (vector_top_k=0)
     │
     │  metadata_filter를 HybridSearchRequest에 전달
     ▼
[HybridSearchUseCase]
     │  metadata_filter → ES: bool/filter 쿼리
     │  metadata_filter → Qdrant: SearchFilter
     ▼
[검색 결과 반환 (필터링된 문서만)]
```

---

## 4. 구현된 세부 기능

### 4-1. RagToolConfig (검색 설정 객체)

에이전트별 RAG 도구 설정을 담는 불변 Value Object이다.

| 필드 | 타입 | 기본값 | 용도 |
|------|------|--------|------|
| `collection_name` | string \| null | null (전체) | 검색할 Qdrant 컬렉션 지정 |
| `es_index` | string \| null | null (시스템 기본) | 검색할 Elasticsearch 인덱스 지정 |
| `metadata_filter` | dict[str, str] | {} (필터 없음) | 메타데이터 기반 문서 필터링 |
| `top_k` | int (1~20) | 5 | 반환할 검색 결과 수 |
| `search_mode` | hybrid \| vector_only \| bm25_only | hybrid | 검색 엔진 선택 |
| `rrf_k` | int (>=1) | 60 | RRF(Reciprocal Rank Fusion) 병합 파라미터 |
| `tool_name` | string (<=100) | "내부 문서 검색" | LLM이 보는 도구 이름 |
| `tool_description` | string (<=500) | (범용 설명) | LLM이 도구 선택 시 참고하는 설명 |

**검증 규칙 (RagToolConfigPolicy)**:
- 메타데이터 필터 최대 10개
- 도구 이름 최대 100자
- 도구 설명 최대 500자

### 4-2. 메타데이터 필터링

`metadata_filter`는 `{key: value}` 형태의 딕셔너리로, 검색 시 두 검색 엔진에 각각 적용된다:

**Elasticsearch (BM25):**
```json
{
  "bool": {
    "must": [{"match": {"content": "사용자 질문"}}],
    "filter": [
      {"term": {"department": "finance"}},
      {"term": {"category": "policy"}}
    ]
  }
}
```
→ `department=finance`이고 `category=policy`인 문서 중에서만 BM25 텍스트 매칭

**Qdrant (Vector):**
```python
SearchFilter(metadata={"department": "finance", "category": "policy"})
```
→ 동일 조건으로 벡터 검색 범위 제한

### 4-3. 검색 모드 (search_mode)

각 모드의 동작 방식과 적합한 사용 시나리오:

| 모드 | 동작 | 적합한 상황 |
|------|------|-----------|
| `hybrid` (기본) | BM25 + Vector → RRF 병합 | 일반적인 문서 검색. 키워드 매칭과 의미 검색을 함께 활용 |
| `vector_only` | Vector 검색만 실행 (bm25_top_k=0) | 의미적 유사도가 중요한 경우. 예: "비슷한 정책 찾기", 질문이 문서와 다른 표현을 쓰는 경우 |
| `bm25_only` | BM25 검색만 실행 (vector_top_k=0) | 정확한 키워드 매칭이 중요한 경우. 예: 법률 용어, 고유명사, 코드명 검색 |

### 4-4. 다중 RAG 도구

DB의 `agent_tool` 테이블 유니크 제약을 `(agent_id, tool_id)` → `(agent_id, worker_id)`로 변경하여, 같은 `internal_document_search` 도구를 서로 다른 설정으로 복수 등록할 수 있다.

```
에이전트: "종합 문의 응대"
├── worker_id: "rag_worker_1"
│   tool_id: internal_document_search
│   tool_config: {tool_name: "상품 정보 검색", metadata_filter: {category: "product"}}
│
└── worker_id: "rag_worker_2"
    tool_id: internal_document_search
    tool_config: {tool_name: "약관 검색", metadata_filter: {category: "terms"}}
```

LLM은 각 도구의 `tool_name`과 `tool_description`을 보고 질문 맥락에 맞는 도구를 선택한다:
- "이 상품의 수수료는?" → "상품 정보 검색" 도구 호출
- "해지 위약금 규정은?" → "약관 검색" 도구 호출

### 4-5. 자동 에이전트 빌더 연동

사용자가 자연어로 에이전트를 요청하면, LLM이 RAG 설정을 자동 추론한다:

```
사용자: "금융팀 정책 문서만 검색하는 에이전트 만들어줘"

LLM 추론 결과:
{
  "tool_ids": ["internal_document_search"],
  "tool_configs": {
    "internal_document_search": {
      "metadata_filter": {"department": "finance"},
      "tool_name": "금융 정책 검색",
      "tool_description": "금융팀의 내부 정책 문서를 검색합니다."
    }
  },
  "confidence": 0.85
}
```

추론에 확신이 부족하면 (`confidence < 0.8`) 명확화 질문을 생성한다:
- "어떤 문서를 검색 대상으로 할까요? (전체 / 금융 / 기술 / HR)"
- "검색 결과는 몇 개를 반환할까요? (기본: 5개)"

### 4-6. 컬렉션/메타데이터 조회 API

프론트엔드에서 RAG 설정 UI를 구성하기 위한 조회 API:

| API | 용도 |
|-----|------|
| `GET /api/v1/rag-tools/collections` | 사용 가능한 Qdrant 컬렉션 목록 + 표시명 + 문서 수 |
| `GET /api/v1/rag-tools/metadata-keys?collection_name=...` | 해당 컬렉션에서 필터링 가능한 메타데이터 키 + 샘플 값 |

이를 통해 사용자가 어떤 컬렉션과 메타데이터가 있는지 직접 확인하고 선택할 수 있다.

---

## 5. 기대 효과

### 5-1. 검색 품질 향상

| 지표 | 개선 메커니즘 |
|------|-------------|
| **정확도** | 불필요한 문서가 검색 결과에서 제외되어 LLM이 참조하는 맥락이 정확해짐 |
| **응답 관련성** | 도구 이름/설명이 구체적이므로 LLM이 올바른 도구를 선택할 확률 증가 |
| **노이즈 감소** | 금융 에이전트에 HR 문서가 섞이지 않아 hallucination 위험 감소 |

### 5-2. 운영 효율

| 지표 | 개선 메커니즘 |
|------|-------------|
| **비용 절감** | `bm25_only` 모드 사용 시 임베딩 API 호출 불필요 → 벡터 연산 비용 절약 |
| **응답 속도** | 검색 범위가 좁아져 Qdrant/ES 검색 시간 단축 |
| **관리 용이성** | 부서별 에이전트를 독립적으로 관리, 각 에이전트의 검색 범위를 명확하게 파악 |

### 5-3. 사용자 경험

| 개선점 | 설명 |
|--------|------|
| **직관적 설정** | 에이전트 생성 시 검색 범위를 시각적으로 설정 (드롭다운, 필터 입력) |
| **자동 추론** | 자동 빌더에서 "금융 문서만"이라고 말하면 자동으로 설정됨 |
| **하위 호환** | 기존 에이전트는 아무 변경 없이 이전과 동일하게 동작 |

---

## 6. 하위 호환성

이 기능은 기존 시스템에 **파괴적 변경 없이** 추가된다:

| 항목 | 호환 방식 |
|------|----------|
| 기존 에이전트 | `tool_config = NULL` → `RagToolConfig()` 기본값 사용 → 전체 문서 검색, top_k=5, hybrid 모드 |
| 기존 API 요청 | `CreateAgentRequest.tool_configs`는 Optional → 기존 요청 body 그대로 동작 |
| 기존 API 응답 | `WorkerInfo.tool_config`는 Optional → 기존 파서가 무시 가능 |
| DB 마이그레이션 | `tool_config` 컬럼은 `DEFAULT NULL` → 기존 행에 영향 없음 |
| 유니크 제약 변경 | `(agent_id, tool_id)` → `(agent_id, worker_id)` — 기존 데이터는 worker_id가 이미 고유하므로 제약 위반 없음 |

---

## 7. 구현 범위와 아키텍처 레이어별 변경

### 7-1. Domain Layer (비즈니스 규칙)

| 파일 | 변경 내용 | 목적 |
|------|----------|------|
| `rag_tool_config.py` (신규) | RagToolConfig VO + RagToolConfigPolicy | 검색 설정의 유효성 규칙을 도메인에서 보장 |
| `schemas.py` | WorkerDefinition에 `tool_config` 필드 추가 | 에이전트 도구에 설정을 연결 |
| `hybrid_search/schemas.py` | HybridSearchRequest에 `metadata_filter` 추가 | 검색 요청에 필터 조건 전달 |
| `auto_agent_builder/schemas.py` | AgentSpecResult에 `tool_configs` 추가 | 자동 추론 결과에 RAG 설정 포함 |

### 7-2. Infrastructure Layer (DB, 외부 연동)

| 파일 | 변경 내용 | 목적 |
|------|----------|------|
| `models.py` | AgentToolModel에 `tool_config` JSON 컬럼 | 설정을 DB에 영구 저장 |
| `agent_definition_repository.py` | save/to_domain에 tool_config 매핑 | 도메인 ↔ DB 변환 |
| `tool_factory.py` | create()에 tool_config 파라미터 + `_parse_rag_config()` | 설정 기반으로 도구 인스턴스 생성 |
| DB 마이그레이션 (V009, V010) | tool_config 컬럼 추가 + 유니크 제약 변경 | 스키마 확장 |

### 7-3. Application Layer (유즈케이스, 도구)

| 파일 | 변경 내용 | 목적 |
|------|----------|------|
| `tools.py` | InternalDocumentSearchTool에 search_mode 분기 + 신규 필드 | 검색 모드별 동작 구현 |
| `use_case.py` | HybridSearchUseCase에 metadata_filter 적용 | ES/Qdrant 검색 시 필터 반영 |
| `create_agent_use_case.py` | tool_configs를 WorkerDefinition에 매핑 | 에이전트 생성 시 설정 저장 |
| `workflow_compiler.py` | tool_config을 ToolFactory에 전달 | 에이전트 실행 시 설정 적용 |
| `agent_spec_inference_service.py` | 프롬프트에 RAG config 옵션 추가 + 파싱 | 자동 빌더 연동 |
| `auto_build_use_case.py` | spec.tool_configs 전달 | 자동 빌더 → 에이전트 생성 흐름 |

### 7-4. Interfaces Layer (API)

| 파일 | 변경 내용 | 목적 |
|------|----------|------|
| `schemas.py` | RagToolConfigRequest, ToolMetaResponse 확장 | API 요청/응답 스키마 |
| `rag_tool_router.py` (신규) | collections, metadata-keys 엔드포인트 | 프론트엔드 설정 UI 지원 |
| `agent_builder_router.py` | config_schema 전달 | 도구 목록에 설정 스키마 포함 |

---

## 8. 테스트 커버리지

| 테스트 파일 | 테스트 수 | 검증 항목 |
|------------|----------|----------|
| `test_rag_tool_config.py` | 16 | VO 생성, 유효성 검증, 불변성, Policy 제한 |
| `test_tool_factory.py` | 12 | config 기반 도구 생성, 기본값, 부분 config, 잘못된 config |
| `test_hybrid_search_use_case.py` | 11 | 메타데이터 필터 ES/Qdrant 적용, 필터 없는 경우 하위 호환 |
| `test_rag_tool_router.py` | 6 | 컬렉션 목록, display_name, 메타데이터 키 조회 |
| `test_internal_document_search_tool.py` | 6 | search_mode 분기 (hybrid/vector_only/bm25_only), 필터 전달 |
| **합계** | **51** | |

---

## 9. 용어 사전

| 용어 | 설명 |
|------|------|
| **RAG** | Retrieval-Augmented Generation. LLM이 답변 생성 전에 관련 문서를 검색하여 참조하는 기술 |
| **BM25** | 전통적인 텍스트 기반 검색 알고리즘. 키워드 빈도와 문서 길이를 고려하여 순위 결정 |
| **Vector Search** | 텍스트를 벡터(숫자 배열)로 변환 후 의미적 유사도로 검색하는 방식 |
| **Hybrid Search** | BM25 + Vector 검색을 동시 실행하고 RRF로 병합하여 양쪽 장점을 활용 |
| **RRF** | Reciprocal Rank Fusion. 여러 검색 결과를 순위 기반으로 병합하는 알고리즘. k값이 높을수록 순위 간 점수 차이가 줄어듦 |
| **Qdrant** | 오픈소스 벡터 데이터베이스. 문서 임베딩을 저장하고 벡터 검색 수행 |
| **Elasticsearch (ES)** | 분산 검색 엔진. BM25 기반 텍스트 검색에 사용 |
| **컬렉션** | Qdrant에서 벡터를 저장하는 단위. 용도별로 분리 가능 (예: finance_docs, tech_manuals) |
| **메타데이터 필터** | 문서에 부여된 속성(department, category 등)으로 검색 범위를 제한하는 조건 |
| **tool_config** | 에이전트 도구에 부여되는 JSON 형태의 설정. 도구 동작을 커스텀하는 데 사용 |
| **worker_id** | 에이전트 내에서 도구 인스턴스를 구분하는 고유 ID. 같은 tool_id의 도구를 여러 개 등록할 때 구분자 역할 |
