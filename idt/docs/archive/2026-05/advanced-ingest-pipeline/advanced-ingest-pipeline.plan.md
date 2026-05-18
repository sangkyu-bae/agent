# advanced-ingest-pipeline Planning Document

> **Summary**: 기존 개별 모듈(pdf-analyzer, pdf-routing, advanced-document-parser, table-retrieval-enhancer, morph-index)을 하나의 고도화 PDF Ingest API로 통합하는 파이프라인
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-16
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | pdf-analyzer, pdf-routing, advanced-document-parser, table-retrieval-enhancer, morph-index 5개 모듈이 독립적으로 존재하여 사용자가 순차 호출해야 하며, 기존 `/api/v1/ingest/pdf`는 단순 parse→chunk→embed→Qdrant 저장만 지원 — ES(BM25) 색인 및 레이아웃 분석/테이블 전처리 누락 |
| **Solution** | 5개 모듈을 하나의 LangGraph 파이프라인으로 오케스트레이션하는 `AdvancedIngestUseCase` + 별도 API 엔드포인트 `/api/v1/ingest/pdf/advanced` 제공 |
| **Function/UX Effect** | PDF 업로드 한 번으로 자동 유형 분석 → 최적 파서 선택 → 레이아웃 분석 → 테이블 의미 문장 변환 → 형태소 전처리 → Qdrant + ES 이중 색인 완료, 진행 상태 실시간 반환 |
| **Core Value** | 기존 구현된 5개 모듈의 통합 가치 실현 — 단일 API 호출로 금융 문서 특화 고품질 인덱싱, 벡터 검색 + BM25 하이브리드 검색 동시 지원 |

---

## 1. Overview

### 1.1 Purpose

기존에 개별 구현·머지된 5개 모듈을 하나의 end-to-end 파이프라인으로 연결하여, PDF 업로드 한 번으로 고품질 이중 색인(Qdrant + ES)을 완료하는 API를 제공한다.

### 1.2 Background

현재 상태:
- `pdf-analyzer`: PDF 유형 분류 (TEXT_HEAVY / TABLE_HEAVY / SCANNED / MIXED)
- `pdf-routing`: 유형 기반 최적 파서 자동 선택 (pymupdf / pymupdf4llm / llamaparser)
- `advanced-document-parser`: 7단계 좌표 기반 레이아웃 분석 (LayoutAnalyzer)
- `table-retrieval-enhancer`: 표 → 의미 문장 변환 (TableFlatteningPreprocessor)
- `morph-index`: Kiwi 형태소 분석 + Qdrant + ES 이중 색인 (MorphAndDualIndexUseCase)

문제:
- 각 모듈이 독립 실행 → 사용자가 순서를 알고 순차 호출해야 함
- 기존 ingest API(`/api/v1/ingest/pdf`)는 단순 파이프라인만 제공 (ES 미지원)
- 레이아웃 분석, 테이블 전처리가 ingest 흐름에 통합되지 않음

### 1.3 Related Documents

- Archive: `docs/archive/2026-05/pdf-analyzer/`
- Archive: `docs/archive/2026-05/advanced-document-parser/`
- Archive: `docs/archive/2026-05/table-retrieval-enhancer/`
- 기존 파이프라인: `src/infrastructure/pipeline/graph/document_processing_graph.py`
- Morph Index: `src/application/morph_index/use_case.py`

---

## 2. Scope

### 2.1 In Scope

- [ ] 기존 5개 모듈을 오케스트레이션하는 `AdvancedIngestUseCase` 구현
- [ ] LangGraph 기반 고도화 파이프라인 그래프 (`advanced_document_processing_graph.py`)
- [ ] 별도 API 엔드포인트 `POST /api/v1/ingest/pdf/advanced`
- [ ] 파이프라인 상태(PipelineState) 확장 — 라우팅/레이아웃/형태소 단계 추가
- [ ] Kiwi 형태소 전처리 + morph_text/morph_keywords 필드 생성 후 ES 색인
- [ ] Qdrant + ES 이중 저장 (store_node 확장)
- [ ] 단계별 처리 시간·에러 추적
- [ ] collection_name 기반 스코프 지원

### 2.2 Out of Scope

- 기존 `/api/v1/ingest/pdf` 수정 또는 제거 (유지)
- 프론트엔드 UI 변경 (별도 태스크)
- 새로운 파서 추가 (기존 파서 레지스트리 활용)
- WebSocket 실시간 진행률 스트리밍 (향후 고려)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | PDF 업로드 시 pdf-analyzer로 문서 유형(PDFDocumentType) 자동 분류 | High | Pending |
| FR-02 | pdf-routing으로 유형 기반 최적 파서(pymupdf/pymupdf4llm/llamaparser) 자동 선택 | High | Pending |
| FR-03 | 선택된 파서로 PDF 파싱 수행 | High | Pending |
| FR-04 | advanced-document-parser(LayoutAnalyzer)로 레이아웃 분석 수행 (TEXT_HEAVY 제외 유형) | High | Pending |
| FR-05 | table-retrieval-enhancer(TableFlatteningPreprocessor)로 표 의미 문장 변환 | High | Pending |
| FR-06 | 청킹 전략 선택 (full_token / parent_child / semantic) 및 청킹 수행 | High | Pending |
| FR-07 | Kiwi 형태소 분석으로 morph_keywords 추출 + morph_text 생성 | High | Pending |
| FR-08 | Qdrant에 임베딩 벡터 + 메타데이터 저장 | High | Pending |
| FR-09 | ES에 nori_analyzer 기반 BM25 색인 (content + morph_keywords) | High | Pending |
| FR-10 | 파이프라인 각 단계의 처리 시간 측정 및 결과 반환 | Medium | Pending |
| FR-11 | 레이아웃 분석 품질 점수 기반 fallback (score < 0.7 → 기본 파서로 재시도) | Medium | Pending |
| FR-12 | collection_name 파라미터로 Qdrant 컬렉션 + ES 인덱스 스코프 지정 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 10페이지 PDF 처리 시간 < 30초 (llamaparser 제외) | 파이프라인 processing_time_ms 측정 |
| Reliability | 개별 단계 실패 시 graceful degradation (fallback) | 에러 로그 + status 필드 확인 |
| Observability | 각 단계별 처리 시간, 에러, 품질 점수 로깅 | LOG-001 준수 (StructuredLogger) |
| Compatibility | 기존 ingest API 무중단 유지 | 기존 테스트 통과 확인 |

---

## 4. Architecture

### 4.1 파이프라인 흐름도

```
┌─────────────────────────────────────────────────────────────────────────┐
│                 Advanced Ingest Pipeline (LangGraph)                    │
│                                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐    │
│  │ analyze  │──▶│  route   │──▶│  parse   │──▶│ layout_analyze   │    │
│  │ (pdf-    │   │ (pdf-    │   │ (선택된   │   │ (advanced-doc-   │    │
│  │ analyzer)│   │ routing) │   │  파서)    │   │  parser)         │    │
│  └──────────┘   └──────────┘   └──────────┘   └────────┬─────────┘    │
│                                                         │              │
│                                                         ▼              │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐    │
│  │ dual_    │◀──│  morph   │◀──│  chunk   │◀──│ table_preprocess │    │
│  │ store    │   │ (Kiwi    │   │ (청킹    │   │ (table-retrieval │    │
│  │ (Qdrant  │   │  형태소)  │   │  전략)   │   │  -enhancer)      │    │
│  │  + ES)   │   │          │   │          │   │                  │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────────┘    │
│       │                                                                │
│       ▼                                                                │
│  ┌──────────┐                                                          │
│  │ complete │                                                          │
│  └──────────┘                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 레이어 배치

```
domain/advanced_ingest/
├── schemas.py                    # AdvancedIngestRequest, AdvancedIngestResult
└── interfaces.py                 # AdvancedIngestPipelineInterface (선택)

application/advanced_ingest/
├── schemas.py                    # API 계층 스키마
└── use_case.py                   # AdvancedIngestUseCase (오케스트레이터)

infrastructure/pipeline/
├── graph/
│   └── advanced_processing_graph.py   # LangGraph 워크플로우 (신규)
└── nodes/
    ├── analyze_node.py                # pdf-analyzer 호출 (신규)
    ├── route_node.py                  # pdf-routing 호출 (신규)
    ├── layout_analyze_node.py         # LayoutAnalyzer 호출 (신규)
    ├── table_preprocess_node.py       # TableFlatteningPreprocessor 호출 (신규)
    ├── morph_node.py                  # Kiwi 형태소 분석 (신규)
    └── dual_store_node.py             # Qdrant + ES 이중 저장 (신규)

api/routes/
└── advanced_ingest_router.py          # POST /api/v1/ingest/pdf/advanced (신규)
```

### 4.3 기존 모듈 재사용 매핑

| 파이프라인 단계 | 재사용 모듈 | 호출 방식 |
|----------------|------------|----------|
| analyze | `PDFAnalyzerInterface` → `PyMuPDFAnalyzer` | `analyzer.analyze_bytes()` |
| route | `ParserRouterInterface` → `DefaultParserRouter` | `router.route(analysis_result)` |
| parse | `PDFParserInterface` → 파서 레지스트리 | `parsers[parser_type].parse_bytes()` |
| layout_analyze | `LayoutAnalyzer` | `layout_analyzer.analyze(pdf_doc)` |
| table_preprocess | `TableFlatteningPreprocessor` | `preprocessor.process(text, title)` |
| chunk | `ChunkingStrategy` → `ChunkingStrategyFactory` | `strategy.chunk(documents)` |
| morph | `MorphAnalyzerInterface` → `KiwiMorphAnalyzer` | `morph.analyze(text)` |
| dual_store | `VectorStoreInterface` + `ElasticsearchRepositoryInterface` | 기존 인터페이스 활용 |

### 4.4 PipelineState 확장

기존 `PipelineState`에 추가되는 필드:

```python
# Analyze Node
document_type: Optional[str]          # PDFDocumentType.value
analysis_confidence: float
analysis_metrics: dict                 # SummaryMetrics 요약

# Route Node
routed_parser_type: str               # 라우팅으로 선택된 파서
routing_reason: str                   # RoutingReason.value
is_fallback: bool

# Layout Analyze Node
layout_quality_score: float           # 레이아웃 분석 품질 점수
layout_applied: bool                  # 레이아웃 분석 적용 여부

# Table Preprocess Node
table_count: int                      # 감지된 표 개수
table_flattened: bool                 # 표 평탄화 적용 여부

# Morph Node
morph_applied: bool
morph_keywords_count: int

# Dual Store Node
qdrant_stored_count: int
es_stored_count: int
es_index_name: str

# Timing (단계별)
step_timings: dict                    # {"analyze": 150, "route": 5, ...}
```

---

## 5. API 설계

### 5.1 엔드포인트

```
POST /api/v1/ingest/pdf/advanced
Content-Type: multipart/form-data
```

### 5.2 요청 파라미터

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| file | UploadFile | (필수) | PDF 파일 |
| user_id | str | (필수) | 사용자 ID |
| collection_name | str | "documents" | Qdrant 컬렉션 + ES 인덱스 이름 |
| chunking_strategy | str | "parent_child" | 청킹 전략 (full_token / parent_child / semantic) |
| chunk_size | int | 500 | 청크 크기 (토큰) |
| chunk_overlap | int | 50 | 청크 오버랩 |
| enable_layout_analysis | bool | true | 레이아웃 분석 활성화 여부 |
| enable_table_flattening | bool | true | 표 의미 문장 변환 활성화 여부 |
| sample_pages | int | 3 | pdf-analyzer 샘플 페이지 수 |

### 5.3 응답 스키마

```python
class AdvancedIngestResponse:
    document_id: str
    filename: str
    user_id: str
    total_pages: int
    
    # 분석 결과
    document_type: str              # "text_heavy" | "table_heavy" | ...
    routed_parser: str              # 실제 사용된 파서
    
    # 전처리 결과
    layout_quality_score: float     # 레이아웃 품질 (0.0~1.0)
    table_count: int                # 감지된 표 수
    
    # 색인 결과
    chunk_count: int
    qdrant_indexed: int
    es_indexed: int
    chunking_strategy: str
    
    # 성능
    processing_time_ms: int
    step_timings: dict              # 단계별 소요 시간
    
    # 메타
    collection_name: str
    request_id: str
```

---

## 6. 조건부 실행 로직

### 6.1 레이아웃 분석 적용 조건

| document_type | layout_analysis | 동작 |
|---------------|----------------|------|
| TEXT_HEAVY | enable=true | LayoutAnalyzer 실행 (경량) |
| TABLE_HEAVY | enable=true | LayoutAnalyzer 실행 (표 집중) |
| SCANNED | enable=true | LayoutAnalyzer 스킵 → llamaparser 결과 직접 사용 |
| MIXED | enable=true | LayoutAnalyzer 실행 |
| * | enable=false | 모든 유형 스킵, 기본 파서 결과 사용 |

### 6.2 품질 기반 Fallback

```
LayoutAnalyzer 결과 quality_score < 0.7
  → 기본 파서(pymupdf)로 재파싱
  → layout_applied = false 기록
  → 기본 텍스트 추출 결과로 후속 파이프라인 진행
```

### 6.3 표 전처리 적용 조건

```
enable_table_flattening=true AND 문서에 표 존재
  → TableFlatteningPreprocessor 실행
  → parent=원본 markdown, child=의미 문장
enable_table_flattening=false OR 표 없음
  → 스킵, 원본 텍스트 그대로 청킹
```

---

## 7. Success Criteria

### 7.1 Definition of Done

- [ ] `AdvancedIngestUseCase` 구현 및 5개 모듈 통합 완료
- [ ] LangGraph 파이프라인 8노드 (analyze→route→parse→layout→table→chunk→morph→dual_store) 동작
- [ ] `POST /api/v1/ingest/pdf/advanced` 엔드포인트 정상 응답
- [ ] Qdrant + ES 이중 색인 확인
- [ ] 기존 `/api/v1/ingest/pdf` 무중단 유지
- [ ] 단위 테스트 작성 및 통과

### 7.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상 (신규 모듈)
- [ ] 기존 테스트 전체 통과
- [ ] LOG-001 로깅 규칙 준수
- [ ] DDD 레이어 규칙 준수 (domain ← application ← infrastructure)

---

## 8. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| LayoutAnalyzer + 표 전처리 동시 실행 시 처리 시간 과다 | Medium | Medium | enable 플래그로 선택적 비활성화, 단계별 타이밍 모니터링 |
| llamaparser 호출 시 외부 API 응답 지연 | High | Medium | timeout 설정 + fallback to pymupdf |
| ES 색인 실패 시 Qdrant만 저장된 불일치 상태 | High | Low | dual_store_node에서 트랜잭션적 처리, 실패 시 롤백 로직 |
| 기존 PipelineState 확장 시 하위 호환 깨짐 | Medium | Low | 새로운 AdvancedPipelineState TypedDict 별도 정의 |
| Kiwi 형태소 분석기 메모리 사용량 | Low | Low | 청크 단위 처리, 배치 크기 제한 |

---

## 9. Implementation Order

| 순서 | 항목 | 의존성 | 예상 크기 |
|------|------|--------|----------|
| 1 | `domain/advanced_ingest/schemas.py` — 요청/응답 스키마 | 없음 | S |
| 2 | `AdvancedPipelineState` 정의 | 기존 PipelineState 참조 | S |
| 3 | `analyze_node.py` + `route_node.py` — 분석/라우팅 노드 | pdf-analyzer, pdf-routing 모듈 | M |
| 4 | `layout_analyze_node.py` — 레이아웃 분석 노드 | LayoutAnalyzer | M |
| 5 | `table_preprocess_node.py` — 표 전처리 노드 | TableFlatteningPreprocessor | S |
| 6 | `morph_node.py` — 형태소 분석 노드 | KiwiMorphAnalyzer | S |
| 7 | `dual_store_node.py` — 이중 저장 노드 | Qdrant + ES 인터페이스 | M |
| 8 | `advanced_processing_graph.py` — LangGraph 워크플로우 조립 | 모든 노드 | M |
| 9 | `AdvancedIngestUseCase` — 오케스트레이터 | 그래프 + DI | M |
| 10 | `advanced_ingest_router.py` — API 엔드포인트 | UseCase | S |
| 11 | `create_app()` DI 등록 | 모든 컴포넌트 | S |

---

## 10. Architecture Considerations

### 10.1 Project Level

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| **Starter** | Simple structure | ☐ |
| **Dynamic** | Feature-based modules, BaaS | ☐ |
| **Enterprise** | Strict layer separation, DI | ☑ |

### 10.2 Key Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 파이프라인 프레임워크 | LangGraph / 수동 체이닝 | LangGraph | 기존 파이프라인과 일관성, 상태 관리 + 조건부 분기 지원 |
| API 구조 | 기존 확장 / 별도 엔드포인트 | 별도 엔드포인트 | 기존 API 무중단 유지, 명확한 책임 분리 |
| State 설계 | 기존 확장 / 별도 정의 | 별도 AdvancedPipelineState | 기존 파이프라인 하위 호환 보장 |
| 이중 저장 | 동기 순차 / 비동기 병렬 | 비동기 병렬 (asyncio.gather) | Qdrant + ES 독립적이므로 병렬 처리 가능 |

---

## 11. Convention Prerequisites

### 11.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section
- [x] DDD 레이어 규칙 준수 (domain → application → infrastructure)
- [x] LOG-001 로깅 규칙 준수
- [x] TDD 필수 (테스트 먼저 작성)

### 11.2 Environment Variables

| Variable | Purpose | Scope | Status |
|----------|---------|-------|:------:|
| `QDRANT_URL` | Qdrant 연결 | Server | 기존 |
| `QDRANT_API_KEY` | Qdrant 인증 | Server | 기존 |
| `OPENAI_API_KEY` | 임베딩 생성 | Server | 기존 |
| `ES_URL` | Elasticsearch 연결 | Server | 기존 |
| `ES_API_KEY` | Elasticsearch 인증 | Server | 기존 |

---

## 12. Next Steps

1. [ ] Design 문서 작성 (`advanced-ingest-pipeline.design.md`)
2. [ ] 팀 리뷰 및 승인
3. [ ] 구현 시작 (Implementation Order 순서)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-16 | Initial draft | 배상규 |
