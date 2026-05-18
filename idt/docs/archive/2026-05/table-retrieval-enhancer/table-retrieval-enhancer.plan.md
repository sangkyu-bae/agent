# table-retrieval-enhancer Planning Document

> **Summary**: Parent-Child 청킹에서 부모=원본 markdown 표 보존, 자식=의미 문장 변환으로 RAG 검색 recall 향상
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-14
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | pymupdf4llm이 PDF 표를 markdown(`\| A등급 \| 3.5% \|`)으로 변환하여 저장하면, "A등급 금리가 얼마야?" 같은 자연어 질문과 임베딩 유사도가 낮아 검색에 안 걸림. 현재 parent_child 전략은 부모/자식 모두 동일한 markdown 텍스트를 토큰 크기만 다르게 분할할 뿐, 검색 최적화된 변환을 하지 않음 |
| **Solution** | 표가 포함된 Document를 청킹할 때 **부모 chunk에는 원본 markdown 표를 그대로 보존**하고, **자식 chunk에는 표를 행 단위 의미 문장으로 풀어서 저장**. 기존 `TableHandler`의 의미 문장 생성 로직을 활용하되, `TableContentGenerator` 인터페이스로 추상화하여 규칙 기반 → LLM → 하이브리드로 교체 가능하게 설계 |
| **Function/UX Effect** | 금융 문서의 금리표, 수수료표, 한도표를 자연어로 질문하면 의미 문장으로 저장된 자식 chunk가 검색되고, 부모 chunk의 원본 표가 LLM 컨텍스트로 제공되어 정확한 답변 가능. 사용자는 기존과 동일하게 문서를 업로드하면 됨 |
| **Core Value** | Parent-Child 청킹의 "검색은 자식으로, 컨텍스트는 부모로" 구조를 표 데이터에 특화 적용. 원본 훼손 없이 검색 품질을 높이는 독립 모듈로, 기존 파이프라인 변경 최소화 |

---

## 1. Overview

### 1.1 Purpose

PDF 표 데이터의 RAG 검색 recall을 향상시키기 위해, parent_child 청킹 전략에 **표 전용 전처리 모듈**을 추가한다.

- **부모 chunk**: 원본 markdown 표 보존 (LLM 컨텍스트용)
- **자식 chunk**: 표를 행 단위 의미 문장으로 변환 (벡터 검색용)

### 1.2 Background — 현재 상태 분석

| 항목 | 현재 상태 | 문제 |
|------|----------|------|
| pymupdf4llm 파서 | 표를 markdown 형식으로 추출 | 정상 동작 |
| parent_child 전략 | 부모/자식 모두 동일 텍스트 토큰 분할 | **자식도 markdown 표 그대로 → 검색 안 걸림** |
| TableHandler | `infrastructure/parser/layout/`에 존재 | **청킹 파이프라인에 연결 안 됨** |
| Qdrant 저장 | `has_table`, `section_title` 메타데이터 있음 | 메타데이터만 있고 활용 안 됨 |

### 1.3 핵심 아이디어

```
현재:
  부모: "... | A등급 | 3.5% | 1억 | ..."  (원본 markdown)
  자식: "... | A등급 | 3.5% | 1억 | ..."  (동일한 markdown을 작게 자름)

개선 후:
  부모: "... | A등급 | 3.5% | 1억 | ..."  (원본 markdown 보존)
  자식: "대출 금리 기준표에서 등급은(는) A등급, 금리은(는) 3.5%, 한도은(는) 1억."
        (행 단위 의미 문장 → 자연어 질문과 임베딩 유사도 ↑)
```

### 1.4 Related Documents

| 문서 | 관계 |
|------|------|
| `docs/archive/2026-05/pymupdf4llm-parser/` | pymupdf4llm 파서 구현 (완료) |
| `docs/archive/2026-05/advanced-document-parser/` | 표 처리 상위 계획 (Phase 2 TableHandler) |
| `src/infrastructure/parser/layout/table_handler.py` | 기존 표 의미 문장 생성 모듈 (재활용) |

---

## 2. Scope

### 2.1 In Scope

| # | 항목 | 설명 | Phase |
|---|------|------|-------|
| 1 | **TableContentGenerator 인터페이스** | 표 → 검색용 텍스트 변환 추상화 (domain) | 1 |
| 2 | **RuleBasedTableContentGenerator** | 기존 TableHandler 로직 활용한 규칙 기반 구현체 (infrastructure) | 1 |
| 3 | **TableFlatteningPreprocessor** | markdown 텍스트에서 표를 감지/추출/변환하는 전처리기 (infrastructure) | 1 |
| 4 | **ParentChildStrategy 확장** | 표 감지 시 부모=원본, 자식=의미 문장으로 분리 처리 (infrastructure) | 2 |
| 5 | **ChunkingFactory 설정 확장** | `table_flattening=True/False` 옵션 추가 | 2 |
| 6 | **TDD 테스트** | 각 모듈별 단위 테스트 + 통합 테스트 | 1, 2 |

### 2.2 Out of Scope

| # | 항목 | 사유 |
|---|------|------|
| 1 | LLM 기반 의미 문장 생성 | Phase 2에서 인터페이스만 준비, 구현은 후속 |
| 2 | 리스트/정의 목록 변환 | MVP는 표만 집중 |
| 3 | section_aware 전략 통합 | parent_child에만 적용 |
| 4 | 프론트엔드 UI 변경 | 백엔드 파이프라인 변경만 |
| 5 | 기존 저장 데이터 재인덱싱 | 신규 업로드분부터 적용 |

---

## 3. Architecture

### 3.1 신규 도메인 인터페이스

```
domain/chunking/
├── interfaces.py              # 기존 ChunkingStrategy (변경 없음)
└── table_content_generator.py # ★ 신규: 표 → 검색 텍스트 변환 인터페이스
```

```python
# domain/chunking/table_content_generator.py
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TableConversionResult:
    """표 변환 결과."""
    original_markdown: str
    search_optimized_text: str
    metadata: dict  # columns, row_count, has_numeric_data 등


class TableContentGenerator(ABC):
    """표 콘텐츠를 검색 최적화 텍스트로 변환하는 인터페이스.

    규칙 기반 → LLM 기반 → 하이브리드로 교체 가능.
    """

    @abstractmethod
    def generate(
        self, table_markdown: str, section_title: str
    ) -> TableConversionResult:
        pass
```

### 3.2 인프라 레이어 구조

```
infrastructure/chunking/
├── base_token_chunker.py          # 기존 (변경 없음)
├── chunking_factory.py            # 수정: table_flattening 옵션
├── table_flattening/              # ★ 신규 패키지
│   ├── __init__.py
│   ├── preprocessor.py            # TableFlatteningPreprocessor
│   └── rule_based_generator.py    # RuleBasedTableContentGenerator
└── strategies/
    ├── parent_child_strategy.py   # 수정: 표 전처리 통합
    ├── full_token_strategy.py     # 변경 없음
    ├── semantic_strategy.py       # 변경 없음
    └── section_aware_strategy.py  # 변경 없음
```

### 3.3 데이터 흐름

```
[pymupdf4llm 파싱 결과]
  │  Document(page_content="... | A등급 | 3.5% | ...", metadata={has_table: true})
  │
  ▼
[ParentChildStrategy.chunk()]
  │
  ├── has_table=false → 기존 로직 그대로 (부모/자식 동일 텍스트 분할)
  │
  └── has_table=true → TableFlatteningPreprocessor 호출
       │
       ├── 1. 텍스트에서 markdown 표 영역 감지 (정규식)
       ├── 2. 표 영역 추출 + 전후 텍스트 분리
       ├── 3. TableContentGenerator.generate() 호출
       │      → TableConversionResult(original, search_optimized, metadata)
       │
       ├── 부모 Document: 원본 텍스트 그대로 (표 포함)
       │     └── 부모 chunk 토큰 분할
       │
       └── 자식 Document: 표 영역을 의미 문장으로 교체
             └── 자식 chunk 토큰 분할
                  metadata += {table_flattened: true, original_table_in_parent: parent_id}
```

### 3.4 의존성 흐름

```
ParentChildStrategy
    │
    ├── TableFlatteningPreprocessor
    │       │
    │       └── TableContentGenerator (인터페이스)
    │               ▲
    │               │
    │       RuleBasedTableContentGenerator (구현체)
    │               │
    │               └── 기존 TableHandler 로직 재활용
    │
    └── BaseTokenChunker (기존)
```

---

## 4. 핵심 설계 상세

### 4.1 TableFlatteningPreprocessor — 표 감지 + 분리

```python
# infrastructure/chunking/table_flattening/preprocessor.py

class TableFlatteningPreprocessor:
    """markdown 텍스트에서 표를 감지하고 검색 최적화 버전을 생성."""

    def __init__(self, generator: TableContentGenerator) -> None:
        self._generator = generator

    def process(self, text: str, section_title: str) -> PreprocessResult:
        """텍스트에서 표를 감지하여 원본/검색용 두 버전을 생성.

        Returns:
            PreprocessResult:
                parent_text: str   — 원본 텍스트 (표 보존)
                child_text: str    — 표를 의미 문장으로 교체한 텍스트
                table_count: int   — 감지된 표 개수
                metadata: dict     — 표 관련 메타데이터
        """
        tables = self._detect_tables(text)

        if not tables:
            return PreprocessResult(
                parent_text=text,
                child_text=text,
                table_count=0,
                metadata={},
            )

        child_text = text
        all_metadata: list[dict] = []

        # 뒤에서부터 교체해야 인덱스가 밀리지 않음
        for table_span in reversed(tables):
            table_md = text[table_span.start : table_span.end]
            result = self._generator.generate(table_md, section_title)

            child_text = (
                child_text[: table_span.start]
                + result.search_optimized_text
                + child_text[table_span.end :]
            )
            all_metadata.append(result.metadata)

        return PreprocessResult(
            parent_text=text,       # 원본 보존
            child_text=child_text,  # 표 → 의미 문장 교체
            table_count=len(tables),
            metadata=self._merge_table_metadata(all_metadata),
        )

    def _detect_tables(self, text: str) -> list[TableSpan]:
        """정규식으로 markdown 표 영역의 시작/끝 위치를 감지."""
        # | ... | ... | 패턴 + |---|---| 구분선이 있는 영역
        ...
```

### 4.2 RuleBasedTableContentGenerator — 규칙 기반 변환

```python
# infrastructure/chunking/table_flattening/rule_based_generator.py

class RuleBasedTableContentGenerator(TableContentGenerator):
    """규칙 기반 표 → 의미 문장 변환.

    기존 TableHandler의 로직을 재활용.
    인터페이스 교체만으로 LLM 기반으로 전환 가능.
    """

    def generate(
        self, table_markdown: str, section_title: str
    ) -> TableConversionResult:
        rows = self._parse_markdown_table(table_markdown)

        if not rows or len(rows) < 2:
            return TableConversionResult(
                original_markdown=table_markdown,
                search_optimized_text=table_markdown,
                metadata={"block_type": "table", "parse_failed": True},
            )

        headers = rows[0]
        data_rows = rows[1:]

        sentences = self._generate_sentences(headers, data_rows, section_title)

        return TableConversionResult(
            original_markdown=table_markdown,
            search_optimized_text="\n".join(sentences),
            metadata={
                "block_type": "table",
                "columns": headers,
                "row_count": len(data_rows),
                "has_numeric_data": self._has_numeric_data(data_rows),
            },
        )

    def _generate_sentences(
        self, headers, data_rows, section_title
    ) -> list[str]:
        """기존 TableHandler._generate_semantic_sentences()와 동일 로직."""
        prefix = f"{section_title}에서 " if section_title else ""
        sentences = []
        for row in data_rows:
            if len(row) != len(headers):
                continue
            parts = [
                f"{h}은(는) {v}" for h, v in zip(headers, row)
                if v and v.strip()
            ]
            if parts:
                sentences.append(prefix + ", ".join(parts) + ".")
        return sentences
```

### 4.3 ParentChildStrategy 확장

```python
# infrastructure/chunking/strategies/parent_child_strategy.py
# 변경 부분만 표시

class ParentChildStrategy(ChunkingStrategy):

    def __init__(
        self,
        parent_config: ChunkingConfig,
        child_config: ChunkingConfig,
        table_preprocessor: TableFlatteningPreprocessor | None = None,
    ):
        # ... 기존 초기화 ...
        self._table_preprocessor = table_preprocessor

    def _chunk_document(self, doc: Document) -> List[Document]:
        content = doc.page_content
        has_table = doc.metadata.get("has_table", False)

        # 표가 있고 전처리기가 설정된 경우 → 부모/자식 콘텐츠 분리
        if has_table and self._table_preprocessor:
            section_title = doc.metadata.get("section_title", "")
            preprocess = self._table_preprocessor.process(content, section_title)
            return self._chunk_with_table_flattening(doc, preprocess)

        # 기존 로직 그대로
        return self._chunk_default(doc)

    def _chunk_with_table_flattening(
        self, doc: Document, preprocess: PreprocessResult
    ) -> List[Document]:
        """부모=원본, 자식=의미 문장 버전으로 청킹."""
        result = []

        parent_texts = self._parent_chunker.split_by_tokens(preprocess.parent_text)

        for parent_idx, parent_text in enumerate(parent_texts):
            parent_id = self._generate_chunk_id()

            # 자식은 의미 문장 버전으로 분할
            child_source = preprocess.child_text
            # 부모 범위에 해당하는 자식 텍스트 추출 (토큰 기반 매핑)
            child_texts = self._child_chunker.split_by_tokens(child_source)

            children_ids = []
            child_docs = []

            for child_idx, child_text in enumerate(child_texts):
                child_id = self._generate_chunk_id()
                children_ids.append(child_id)
                child_metadata = self._parent_chunker.merge_metadata(
                    doc.metadata,
                    {
                        "chunk_type": "child",
                        "chunk_id": child_id,
                        "chunk_index": child_idx,
                        "total_chunks": len(child_texts),
                        "parent_id": parent_id,
                        "table_flattened": True,
                    },
                )
                child_docs.append(Document(page_content=child_text, metadata=child_metadata))

            parent_metadata = self._parent_chunker.merge_metadata(
                doc.metadata,
                {
                    "chunk_type": "parent",
                    "chunk_id": parent_id,
                    "chunk_index": parent_idx,
                    "total_chunks": len(parent_texts),
                    "children_ids": children_ids,
                    **preprocess.metadata,
                },
            )
            parent_doc = Document(page_content=parent_text, metadata=parent_metadata)
            result.append(parent_doc)
            result.extend(child_docs)

        return result
```

---

## 5. Phase 별 구현 계획

### Phase 1: 독립 모듈 구현 (3~4h)

> 목표: 표 감지 → 의미 문장 변환 모듈을 독립적으로 구현 + 테스트

| # | Task | 파일 | 예상 시간 | 선행 |
|---|------|------|-----------|------|
| 1-1 | `TableContentGenerator` 인터페이스 정의 | `domain/chunking/table_content_generator.py` | 30m | - |
| 1-2 | `TableConversionResult`, `PreprocessResult`, `TableSpan` VO 정의 | `domain/chunking/table_content_generator.py` | 30m | - |
| 1-3 | TDD: `RuleBasedTableContentGenerator` 테스트 작성 | `tests/infrastructure/chunking/table_flattening/test_rule_based_generator.py` | 30m | 1-1 |
| 1-4 | `RuleBasedTableContentGenerator` 구현 | `infrastructure/chunking/table_flattening/rule_based_generator.py` | 30m | 1-3 |
| 1-5 | TDD: `TableFlatteningPreprocessor` 테스트 작성 | `tests/infrastructure/chunking/table_flattening/test_preprocessor.py` | 45m | 1-1 |
| 1-6 | `TableFlatteningPreprocessor` 구현 (표 감지 + 교체) | `infrastructure/chunking/table_flattening/preprocessor.py` | 1h | 1-5 |

**Phase 1 산출물**: 독립적으로 동작하는 표 전처리 모듈 + 테스트

### Phase 2: ParentChildStrategy 통합 (2~3h)

> 목표: 전처리 모듈을 parent_child 전략에 연결

| # | Task | 파일 | 예상 시간 | 선행 |
|---|------|------|-----------|------|
| 2-1 | TDD: `ParentChildStrategy` 표 분리 테스트 작성 | `tests/infrastructure/chunking/test_parent_child_strategy.py` | 45m | Phase 1 |
| 2-2 | `ParentChildStrategy` 확장 (표 전처리 통합) | `infrastructure/chunking/strategies/parent_child_strategy.py` | 1h | 2-1 |
| 2-3 | `ChunkingFactory` 설정 확장 (`table_flattening` 옵션) | `infrastructure/chunking/chunking_factory.py` | 30m | 2-2 |
| 2-4 | 통합 테스트: 파싱 → 청킹 → 부모/자식 검증 | `tests/integration/test_table_retrieval.py` | 45m | 2-3 |

**Phase 2 산출물**: parent_child 전략에서 표 포함 문서 업로드 시 자동으로 의미 문장 변환

---

## 6. 인터페이스 확장성 설계

### 6.1 현재 구현 (규칙 기반)

```python
generator = RuleBasedTableContentGenerator()
preprocessor = TableFlatteningPreprocessor(generator)
```

### 6.2 향후 LLM 교체 시

```python
class LLMTableContentGenerator(TableContentGenerator):
    def __init__(self, llm: ChatOpenAI) -> None:
        self._llm = llm

    def generate(self, table_markdown: str, section_title: str) -> TableConversionResult:
        prompt = f"다음 표를 자연어 문장으로 변환하세요:\n{table_markdown}"
        response = self._llm.invoke(prompt)
        return TableConversionResult(
            original_markdown=table_markdown,
            search_optimized_text=response.content,
            metadata={"generation_method": "llm"},
        )

# 교체: 한 줄만 변경
generator = LLMTableContentGenerator(llm=ChatOpenAI(model="gpt-4o-mini"))
preprocessor = TableFlatteningPreprocessor(generator)
```

### 6.3 향후 하이브리드 교체 시

```python
class HybridTableContentGenerator(TableContentGenerator):
    def __init__(self, rule_gen, llm_gen, complexity_threshold: int = 5) -> None:
        self._rule = rule_gen
        self._llm = llm_gen
        self._threshold = complexity_threshold

    def generate(self, table_markdown: str, section_title: str) -> TableConversionResult:
        # 단순 표 → 규칙 기반 (빠름, 무료)
        # 복잡 표 (병합 셀, 5컬럼 초과 등) → LLM fallback
        if self._is_complex(table_markdown):
            return self._llm.generate(table_markdown, section_title)
        return self._rule.generate(table_markdown, section_title)
```

---

## 7. Testing Strategy

### 7.1 단위 테스트

| 모듈 | 주요 테스트 |
|------|------------|
| `RuleBasedTableContentGenerator` | 표 파싱 정확성, 의미 문장 생성, 빈 표 처리, 헤더-데이터 불일치, 숫자 데이터 감지 |
| `TableFlatteningPreprocessor` | 표 감지 (단일/복수), 표 없는 텍스트 통과, 표 전후 텍스트 보존, 인덱스 교체 정확성 |
| `ParentChildStrategy` (표 통합) | 부모=원본 보존 확인, 자식=의미 문장 확인, `table_flattened` 메타데이터, 기존 동작 회귀 |

### 7.2 핵심 테스트 케이스

```python
def test_parent_preserves_original_table():
    """부모 chunk에 원본 markdown 표가 그대로 보존되는지 확인."""

def test_child_has_semantic_sentences():
    """자식 chunk에 의미 문장이 포함되고, markdown 표가 없는지 확인."""

def test_no_table_document_unchanged():
    """표 없는 문서는 기존과 동일하게 동작하는지 확인."""

def test_multiple_tables_all_flattened():
    """텍스트에 표가 2개 이상일 때 모두 변환되는지 확인."""

def test_table_surrounding_text_preserved():
    """표 전후의 일반 텍스트가 손실 없이 보존되는지 확인."""

def test_section_title_included_in_sentences():
    """의미 문장에 섹션 제목이 접두어로 포함되는지 확인."""

def test_generator_interface_swappable():
    """TableContentGenerator를 mock으로 교체해도 동작하는지 확인."""
```

### 7.3 통합 테스트 (실제 금융 문서)

```python
def test_financial_rate_table_search_recall():
    """금리 기준표 → 의미 문장 저장 → '3등급 금리' 검색 → 해당 행 자식 chunk 반환."""

def test_parent_child_linkage_after_flattening():
    """표 flatten 후에도 parent_id ↔ children_ids 관계가 정상인지 확인."""
```

---

## 8. Success Criteria

### 8.1 Definition of Done

- [ ] `TableContentGenerator` 인터페이스 정의 (domain)
- [ ] `RuleBasedTableContentGenerator` 구현 + 테스트 통과
- [ ] `TableFlatteningPreprocessor` 구현 + 테스트 통과
- [ ] `ParentChildStrategy` 확장 + 기존 테스트 회귀 없음
- [ ] `ChunkingFactory`에서 `table_flattening=True` 옵션으로 활성화 가능
- [ ] 부모 chunk에 원본 markdown 표 보존 확인
- [ ] 자식 chunk에 의미 문장 변환 확인
- [ ] `table_flattened` 메타데이터 Qdrant 저장 확인

### 8.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상
- [ ] 린트 에러 없음
- [ ] LOG-001 규칙 준수
- [ ] 기존 parent_child 테스트 전체 통과 (회귀 없음)

---

## 9. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 표 감지 정규식이 비표준 markdown에서 실패 | 표가 변환 안 됨 | Medium | 실패 시 원본 그대로 통과 (graceful fallback) |
| 의미 문장이 임베딩에서 원본보다 낫지 않을 수 있음 | 검색 품질 미개선 | Low | RAGAS 평가로 비교 검증 (후속 과제) |
| 부모/자식 텍스트 길이 차이로 토큰 분할 매핑 어긋남 | 부모-자식 관계 불일치 | Medium | 부모는 원본 전체로 1 chunk, 자식만 분할하는 전략 고려 |
| 기존 parent_child 테스트 깨짐 | 회귀 | Low | `table_preprocessor=None` 기본값으로 기존 동작 유지 |
| 대량 표 문서에서 의미 문장 토큰 폭증 | 자식 chunk 과다 생성 | Low | 표당 최대 행 수 제한 옵션 |

---

## 10. Dependencies

### 10.1 신규 패키지

없음. 기존 의존성만 사용.

### 10.2 기존 인터페이스 영향

| 인터페이스 | 변경 | 영향 |
|-----------|------|------|
| `ChunkingStrategy` | 변경 없음 | 기존 전략 호환 |
| `ParentChildStrategy.__init__` | 선택적 파라미터 추가 | 하위 호환 |
| `ChunkingFactory.create_strategy()` | `table_flattening` 옵션 추가 | 기존 호출 영향 없음 |
| `PDFParserInterface` | 변경 없음 | 파서 독립 |

---

## 11. Implementation Order Summary

```
Phase 1 (3~4h): 독립 모듈
├── TableContentGenerator 인터페이스 (domain)
├── TableConversionResult, PreprocessResult VO (domain)
├── TDD: RuleBasedTableContentGenerator 테스트 → 구현
├── TDD: TableFlatteningPreprocessor 테스트 → 구현
└── 단위 테스트 전체 통과

Phase 2 (2~3h): 파이프라인 통합
├── TDD: ParentChildStrategy 표 분리 테스트 → 확장
├── ChunkingFactory table_flattening 옵션
├── 통합 테스트
└── 전체 테스트 통과 (기존 회귀 없음)
```

**총 예상 시간: 5~7h**

---

## 12. Architecture Considerations

### 12.1 Project Level

| Level | Selected |
|-------|:--------:|
| **Enterprise** (Thin DDD) | **Yes** |

### 12.2 Clean Architecture 적용

```
┌─────────────────────────────────────────────────────┐
│ domain/chunking/                                    │
│   - interfaces.py         (변경 없음)                │
│   - table_content_generator.py  ← 신규 인터페이스    │
│   - value_objects.py      (변경 없음)                │
├─────────────────────────────────────────────────────┤
│ infrastructure/chunking/                            │
│   - table_flattening/     ← 신규 패키지             │
│     - preprocessor.py                                │
│     - rule_based_generator.py                        │
│   - strategies/                                      │
│     - parent_child_strategy.py  ← 수정 (통합)        │
│   - chunking_factory.py  ← 수정 (옵션 추가)          │
├─────────────────────────────────────────────────────┤
│ application/ingest/                                 │
│   - ingest_use_case.py    (변경 없음, DI로 주입)     │
├─────────────────────────────────────────────────────┤
│ api/                                                │
│   - main.py               (변경 없음 또는 DI 설정)   │
└─────────────────────────────────────────────────────┘
```

### 12.3 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 인터페이스 위치 | domain vs infrastructure | domain | 구현체 교체 가능성 (규칙→LLM) |
| 전처리 위치 | 파서 내부 vs 청킹 내부 | 청킹 내부 | 파서는 추출만, 청킹이 검색 최적화 책임 |
| 기존 TableHandler 관계 | 상속 vs 재활용 vs 독립 | 로직 재활용 | TableHandler는 DocumentElement 의존, 여기는 순수 markdown 텍스트 |
| 활성화 방식 | 항상 활성 vs 옵션 | 옵션 (기본 True) | 기존 동작 보호, 점진적 활성화 |

---

## 13. Future Extensions

| Extension | Trigger |
|-----------|---------|
| `LLMTableContentGenerator` 구현 | 규칙 기반 품질 한계 도달 시 |
| `HybridTableContentGenerator` 구현 | 복잡 표 처리 필요 시 |
| 리스트/정의 목록 flattering | 표 외 구조화 데이터 recall 이슈 시 |
| RAGAS 평가: 표 flatten 전후 비교 | 효과 정량 측정 필요 시 |
| section_aware 전략 통합 | parent_child 외 전략에서도 필요 시 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-14 | Initial draft | 배상규 |
