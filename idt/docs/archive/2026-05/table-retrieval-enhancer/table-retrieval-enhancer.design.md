# table-retrieval-enhancer Design Document

> **Summary**: Parent-Child 청킹에서 부모=원본 markdown 표 보존, 자식=의미 문장 변환 모듈 상세 설계
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-14
> **Status**: Draft
> **Planning Doc**: [table-retrieval-enhancer.plan.md](../../01-plan/features/table-retrieval-enhancer.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- markdown 텍스트에서 표 영역을 감지하고, 행 단위 의미 문장으로 변환하는 **독립 전처리 모듈** 구현
- `ParentChildStrategy`에 통합하여 **부모=원본, 자식=의미 문장**으로 분리 청킹
- `TableContentGenerator` 인터페이스 추상화로 규칙 기반 → LLM → 하이브리드 교체 가능
- 기존 코드 최소 변경, 하위 호환 보장

### 1.2 Design Principles

- **Open-Closed**: `ParentChildStrategy`에 선택적 전처리기를 주입. 기존 동작 보호
- **Strategy Pattern**: `TableContentGenerator` 인터페이스로 변환 로직 교체 가능
- **Single Responsibility**: 전처리기는 표 감지/교체만, 전략은 청킹만 담당
- **Dependency Inversion**: domain에 인터페이스, infrastructure에 구현체

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    Application Layer                              │
│  IngestDocumentUseCase                                           │
│    → ChunkingStrategyFactory.create_strategy("parent_child",     │
│         table_flattening=True)                                   │
└──────────────┬───────────────────────────────────────────────────┘
               │ ChunkingStrategy.chunk(documents)
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                Infrastructure Layer                               │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ ParentChildStrategy (수정)                                  │ │
│  │                                                             │ │
│  │  chunk(docs) ──► has_table? ──► YES ──► _chunk_with_table() │ │
│  │                      │                         │            │ │
│  │                      NO                        ▼            │ │
│  │                      │           TableFlatteningPreprocessor │ │
│  │                      ▼                         │            │ │
│  │              _chunk_default()        ┌─────────┴──────────┐ │ │
│  │              (기존 로직)              │ process(text, title)│ │ │
│  │                                     │  → parent_text      │ │ │
│  │                                     │  → child_text       │ │ │
│  │                                     └─────────┬──────────┘ │ │
│  │                                               │            │ │
│  │                                               ▼            │ │
│  │                                     TableContentGenerator   │ │
│  │                                     (인터페이스 호출)        │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ table_flattening/ (신규 패키지)                             │ │
│  │  ├── preprocessor.py       → TableFlatteningPreprocessor    │ │
│  │  └── rule_based_generator.py → RuleBasedTableContentGenerator│ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ ChunkingStrategyFactory (수정)                              │ │
│  │  _create_parent_child_strategy(table_flattening=True)       │ │
│  │    → preprocessor 주입                                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Domain Layer                                    │
│  chunking/                                                        │
│    interfaces.py              (변경 없음)                          │
│    value_objects.py            (변경 없음)                          │
│    table_content_generator.py  (신규: 인터페이스 + VO)              │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
[pymupdf4llm 파서 출력]
  Document(
    page_content="## 대출 금리\n\n일반 내용...\n\n| 등급 | 금리 | 한도 |\n|---|---|---|\n| A | 3.5% | 1억 |\n| B | 4.2% | 5천 |\n\n후속 내용...",
    metadata={has_table: true, section_title: "대출 금리", page: 3}
  )
     │
     ▼
[ParentChildStrategy.chunk()]
     │
     ├── metadata["has_table"] == True AND self._table_preprocessor is not None
     │
     ▼
[TableFlatteningPreprocessor.process(text, section_title)]
     │
     ├── 1. _detect_tables(text) → [TableSpan(start=28, end=95)]
     │
     ├── 2. generator.generate(table_md, "대출 금리")
     │      → TableConversionResult(
     │           original: "| 등급 | 금리 | ...",
     │           search_optimized: "대출 금리에서 등급은(는) A, 금리은(는) 3.5%, 한도은(는) 1억.\n대출 금리에서 등급은(는) B, ..."
     │           metadata: {columns: [...], row_count: 2}
     │        )
     │
     └── 3. PreprocessResult(
              parent_text = 원본 텍스트 (표 포함),
              child_text  = "## 대출 금리\n\n일반 내용...\n\n대출 금리에서 등급은(는) A, ...\n\n후속 내용...",
              table_count = 1,
              metadata = {columns: [...], row_count: 2}
           )
     │
     ▼
[ParentChildStrategy._chunk_with_table_flattening()]
     │
     ├── 부모: split_by_tokens(parent_text) → parent chunks (원본 markdown 보존)
     │     metadata += {chunk_type: "parent", table_count: 1, columns: [...]}
     │
     └── 자식: split_by_tokens(child_text) → child chunks (의미 문장 포함)
           metadata += {chunk_type: "child", table_flattened: true, parent_id: ...}
     │
     ▼
[Qdrant 저장]
  부모 payload: {content: "... | A | 3.5% | ...", chunk_type: "parent", ...}
  자식 payload: {content: "대출 금리에서 등급은(는) A, ...", chunk_type: "child", table_flattened: true, ...}
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `TableContentGenerator` | (없음 — 순수 인터페이스) | 변환 추상화 |
| `RuleBasedTableContentGenerator` | `TableContentGenerator` | 규칙 기반 변환 구현 |
| `TableFlatteningPreprocessor` | `TableContentGenerator` | 표 감지 + 변환 오케스트레이션 |
| `ParentChildStrategy` | `TableFlatteningPreprocessor` (선택적) | 청킹에 전처리 통합 |
| `ChunkingStrategyFactory` | `TableFlatteningPreprocessor`, `RuleBasedTableContentGenerator` | DI 조립 |

---

## 3. Data Model

### 3.1 Domain Value Objects (신규)

**파일**: `src/domain/chunking/table_content_generator.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TableConversionResult:
    """표 변환 결과 VO."""
    original_markdown: str
    search_optimized_text: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TableSpan:
    """텍스트 내 표 위치."""
    start: int
    end: int


@dataclass(frozen=True)
class PreprocessResult:
    """전처리 결과 VO."""
    parent_text: str
    child_text: str
    table_count: int
    metadata: dict = field(default_factory=dict)


class TableContentGenerator(ABC):
    """표 → 검색 최적화 텍스트 변환 인터페이스."""

    @abstractmethod
    def generate(
        self, table_markdown: str, section_title: str
    ) -> TableConversionResult:
        """markdown 표를 검색 최적화 텍스트로 변환.

        Args:
            table_markdown: pipe 형식의 markdown 표 문자열
            section_title: 표가 속한 섹션 제목 (의미 문장 접두어)

        Returns:
            TableConversionResult with original + search_optimized + metadata
        """
        pass
```

### 3.2 Chunk 메타데이터 확장

기존 `ChunkMetadata` VO는 수정하지 않는다. `merge_metadata()`를 통해 dict 수준에서 추가 필드를 병합한다.

| 필드 | 타입 | 적용 대상 | 설명 |
|------|------|----------|------|
| `table_flattened` | bool | child chunk | 표가 의미 문장으로 변환되었는지 |
| `table_count` | int | parent chunk | 원본에 포함된 표 개수 |
| `table_columns` | list[str] | parent chunk | 표 컬럼 이름 목록 |
| `table_row_count` | int | parent chunk | 표 데이터 행 수 |

---

## 4. API Specification

### 4.1 변경되는 API

없음. API 레이어 변경 없이 인프라 레이어 내부에서만 동작한다.

기존 Ingest API의 `chunking_strategy=parent_child` 사용 시 자동 적용.

### 4.2 ChunkingStrategyFactory 인터페이스 변경

```python
# 기존
ChunkingStrategyFactory.create_strategy("parent_child")

# 변경 후 (하위 호환)
ChunkingStrategyFactory.create_strategy(
    "parent_child",
    table_flattening=True,  # 신규 옵션, 기본값 True
)
```

---

## 5. Detailed Implementation Design

### 5.1 TableContentGenerator 인터페이스 (Domain)

**파일**: `src/domain/chunking/table_content_generator.py`

위 3.1절의 코드 그대로. VO 3개 + ABC 1개.

### 5.2 RuleBasedTableContentGenerator (Infrastructure)

**파일**: `src/infrastructure/chunking/table_flattening/rule_based_generator.py`

```python
"""규칙 기반 표 → 의미 문장 변환."""
import re

from src.domain.chunking.table_content_generator import (
    TableContentGenerator,
    TableConversionResult,
)


class RuleBasedTableContentGenerator(TableContentGenerator):
    """규칙 기반 표 → 의미 문장 변환 구현체.

    기존 TableHandler의 의미 문장 생성 로직을 markdown 문자열 입력으로 재구성.
    """

    def generate(
        self, table_markdown: str, section_title: str
    ) -> TableConversionResult:
        rows = self._parse_markdown_table(table_markdown)

        if not rows or len(rows) < 2:
            return TableConversionResult(
                original_markdown=table_markdown,
                search_optimized_text=table_markdown,
                metadata={"parse_failed": True},
            )

        headers = rows[0]
        data_rows = rows[1:]
        sentences = self._generate_sentences(headers, data_rows, section_title)

        return TableConversionResult(
            original_markdown=table_markdown,
            search_optimized_text="\n".join(sentences),
            metadata={
                "columns": headers,
                "row_count": len(data_rows),
                "has_numeric_data": self._has_numeric_data(data_rows),
            },
        )

    def _parse_markdown_table(self, md_text: str) -> list[list[str]]:
        """markdown 표 문자열을 2차원 리스트로 파싱."""
        rows: list[list[str]] = []
        for line in md_text.strip().split("\n"):
            line = line.strip()
            if not line.startswith("|"):
                continue
            if re.match(r"^\|[\s\-:|]+\|$", line):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells:
                rows.append(cells)
        return rows

    def _generate_sentences(
        self,
        headers: list[str],
        data_rows: list[list[str]],
        section_title: str,
    ) -> list[str]:
        """헤더 + 데이터 행을 자연어 의미 문장으로 변환."""
        prefix = f"{section_title}에서 " if section_title else ""
        sentences: list[str] = []

        for row in data_rows:
            if len(row) != len(headers):
                continue
            parts = [
                f"{h}은(는) {v}"
                for h, v in zip(headers, row)
                if v and v.strip()
            ]
            if parts:
                sentences.append(prefix + ", ".join(parts) + ".")

        return sentences

    def _has_numeric_data(self, data_rows: list[list[str]]) -> bool:
        """데이터 행에 숫자 데이터가 있는지 검사."""
        for row in data_rows:
            for cell in row:
                cleaned = (
                    cell.replace(",", "")
                    .replace("%", "")
                    .replace("원", "")
                    .replace("억", "")
                    .replace("만", "")
                    .strip()
                )
                try:
                    float(cleaned)
                    return True
                except ValueError:
                    continue
        return False
```

### 5.3 TableFlatteningPreprocessor (Infrastructure)

**파일**: `src/infrastructure/chunking/table_flattening/preprocessor.py`

```python
"""markdown 텍스트에서 표를 감지하고 검색 최적화 버전을 생성."""
import re
from typing import Optional

from src.domain.chunking.table_content_generator import (
    PreprocessResult,
    TableContentGenerator,
    TableSpan,
)


class TableFlatteningPreprocessor:
    """markdown 텍스트에서 표를 감지하여 부모/자식용 텍스트를 분리."""

    # markdown 표 라인 패턴: | ... | 로 시작/끝
    _TABLE_LINE_PATTERN = re.compile(r"^\s*\|.+\|\s*$")
    # 구분선 패턴: |---|---|
    _SEPARATOR_PATTERN = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")

    def __init__(self, generator: TableContentGenerator) -> None:
        self._generator = generator

    def process(
        self,
        text: str,
        section_title: str = "",
    ) -> PreprocessResult:
        """텍스트에서 표를 감지하여 원본/검색용 두 버전 생성.

        Args:
            text: markdown 포맷의 원본 텍스트
            section_title: 섹션 제목 (의미 문장 접두어)

        Returns:
            PreprocessResult with parent_text, child_text, table_count, metadata
        """
        tables = self._detect_tables(text)

        if not tables:
            return PreprocessResult(
                parent_text=text,
                child_text=text,
                table_count=0,
            )

        child_text = text
        all_metadata: list[dict] = []

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
            parent_text=text,
            child_text=child_text,
            table_count=len(tables),
            metadata=self._merge_table_metadata(all_metadata),
        )

    def _detect_tables(self, text: str) -> list[TableSpan]:
        """markdown 표 영역의 시작/끝 위치를 감지.

        연속된 | ... | 라인 중 구분선(|---|)을 포함하는 블록만 표로 인식.
        """
        lines = text.split("\n")
        tables: list[TableSpan] = []

        i = 0
        current_pos = 0
        table_start: Optional[int] = None
        has_separator = False

        for i, line in enumerate(lines):
            is_table_line = bool(self._TABLE_LINE_PATTERN.match(line))
            is_separator = bool(self._SEPARATOR_PATTERN.match(line))

            if is_table_line:
                if table_start is None:
                    table_start = current_pos
                if is_separator:
                    has_separator = True
            else:
                if table_start is not None and has_separator:
                    table_end = current_pos
                    tables.append(TableSpan(start=table_start, end=table_end))
                table_start = None
                has_separator = False

            current_pos += len(line) + 1  # +1 for \n

        # 텍스트 끝에서 표가 끝나는 경우
        if table_start is not None and has_separator:
            tables.append(TableSpan(start=table_start, end=len(text)))

        return tables

    def _merge_table_metadata(self, metadata_list: list[dict]) -> dict:
        """여러 표의 메타데이터를 병합."""
        if not metadata_list:
            return {}
        if len(metadata_list) == 1:
            return metadata_list[0]

        all_columns: list[list[str]] = []
        total_rows = 0
        has_numeric = False

        for meta in metadata_list:
            if "columns" in meta:
                all_columns.append(meta["columns"])
            total_rows += meta.get("row_count", 0)
            if meta.get("has_numeric_data"):
                has_numeric = True

        return {
            "table_columns": all_columns,
            "total_row_count": total_rows,
            "has_numeric_data": has_numeric,
            "multi_table": len(metadata_list) > 1,
        }
```

### 5.4 ParentChildStrategy 확장 (Infrastructure)

**파일**: `src/infrastructure/chunking/strategies/parent_child_strategy.py`

변경 범위: `__init__` 파라미터 추가, `_chunk_document` 분기 추가, `_chunk_with_table_flattening` 신규 메서드.

```python
"""Parent-child chunking strategy implementation."""
import uuid
from typing import List, Optional

from langchain_core.documents import Document

from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.chunking.value_objects import ChunkingConfig
from src.infrastructure.chunking.base_token_chunker import BaseTokenChunker
from src.infrastructure.chunking.table_flattening.preprocessor import (
    TableFlatteningPreprocessor,
)


class ParentChildStrategy(ChunkingStrategy):
    """Chunking strategy that creates parent-child hierarchical chunks."""

    def __init__(
        self,
        parent_config: ChunkingConfig,
        child_config: ChunkingConfig,
        table_preprocessor: Optional[TableFlatteningPreprocessor] = None,
    ):
        self._parent_config = parent_config
        self._child_config = child_config
        self._parent_chunker = BaseTokenChunker(parent_config)
        self._child_chunker = BaseTokenChunker(child_config)
        self._table_preprocessor = table_preprocessor

    def chunk(self, documents: List[Document]) -> List[Document]:
        """Split documents into parent-child hierarchical chunks."""
        if not documents:
            return []

        result = []
        for doc in documents:
            doc_chunks = self._chunk_document(doc)
            result.extend(doc_chunks)

        return result

    def _chunk_document(self, doc: Document) -> List[Document]:
        has_table = doc.metadata.get("has_table", False)

        if has_table and self._table_preprocessor:
            section_title = doc.metadata.get("section_title", "")
            preprocess = self._table_preprocessor.process(
                doc.page_content, section_title
            )
            if preprocess.table_count > 0:
                return self._chunk_with_table_flattening(doc, preprocess)

        return self._chunk_default(doc)

    def _chunk_default(self, doc: Document) -> List[Document]:
        """기존 parent-child 청킹 로직 (변경 없음)."""
        content = doc.page_content
        if not content:
            return []

        result = []
        parent_texts = self._parent_chunker.split_by_tokens(content)

        for parent_idx, parent_text in enumerate(parent_texts):
            parent_id = self._generate_chunk_id()
            child_texts = self._child_chunker.split_by_tokens(parent_text)
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
                    },
                )
                child_docs.append(
                    Document(page_content=child_text, metadata=child_metadata)
                )

            parent_metadata = self._parent_chunker.merge_metadata(
                doc.metadata,
                {
                    "chunk_type": "parent",
                    "chunk_id": parent_id,
                    "chunk_index": parent_idx,
                    "total_chunks": len(parent_texts),
                    "children_ids": children_ids,
                },
            )
            parent_doc = Document(
                page_content=parent_text, metadata=parent_metadata
            )

            result.append(parent_doc)
            result.extend(child_docs)

        children = [
            d for d in result if d.metadata.get("chunk_type") == "child"
        ]
        for i, child in enumerate(children):
            child.metadata["chunk_index"] = i
        for child in children:
            child.metadata["total_chunks"] = len(children)

        return result

    def _chunk_with_table_flattening(
        self, doc: Document, preprocess
    ) -> List[Document]:
        """부모=원본 markdown, 자식=의미 문장 버전으로 청킹."""
        result = []

        # 부모: 원본 텍스트로 분할
        parent_texts = self._parent_chunker.split_by_tokens(
            preprocess.parent_text
        )
        # 자식: 의미 문장 버전으로 분할
        child_texts = self._child_chunker.split_by_tokens(
            preprocess.child_text
        )

        # 부모가 1개인 경우: 모든 자식이 해당 부모에 연결
        # 부모가 N개인 경우: 자식들을 균등 배분
        if len(parent_texts) == 1:
            parent_id = self._generate_chunk_id()
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
                child_docs.append(
                    Document(
                        page_content=child_text, metadata=child_metadata
                    )
                )

            parent_metadata = self._parent_chunker.merge_metadata(
                doc.metadata,
                {
                    "chunk_type": "parent",
                    "chunk_id": parent_id,
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "children_ids": children_ids,
                    "table_count": preprocess.table_count,
                    **preprocess.metadata,
                },
            )
            result.append(
                Document(
                    page_content=parent_texts[0], metadata=parent_metadata
                )
            )
            result.extend(child_docs)
        else:
            # 부모가 여러 개인 경우: 각 부모에 대해 해당 부모 텍스트 범위의
            # 자식을 매핑. 자식 전체를 균등 배분.
            children_per_parent = max(
                1, len(child_texts) // len(parent_texts)
            )
            child_offset = 0

            for parent_idx, parent_text in enumerate(parent_texts):
                parent_id = self._generate_chunk_id()

                # 마지막 부모는 남은 자식 모두 수용
                if parent_idx == len(parent_texts) - 1:
                    assigned_children = child_texts[child_offset:]
                else:
                    assigned_children = child_texts[
                        child_offset : child_offset + children_per_parent
                    ]

                children_ids = []
                child_docs = []

                for local_idx, child_text in enumerate(assigned_children):
                    child_id = self._generate_chunk_id()
                    children_ids.append(child_id)
                    child_metadata = self._parent_chunker.merge_metadata(
                        doc.metadata,
                        {
                            "chunk_type": "child",
                            "chunk_id": child_id,
                            "chunk_index": child_offset + local_idx,
                            "total_chunks": len(child_texts),
                            "parent_id": parent_id,
                            "table_flattened": True,
                        },
                    )
                    child_docs.append(
                        Document(
                            page_content=child_text, metadata=child_metadata
                        )
                    )

                parent_metadata = self._parent_chunker.merge_metadata(
                    doc.metadata,
                    {
                        "chunk_type": "parent",
                        "chunk_id": parent_id,
                        "chunk_index": parent_idx,
                        "total_chunks": len(parent_texts),
                        "children_ids": children_ids,
                        "table_count": preprocess.table_count,
                        **preprocess.metadata,
                    },
                )
                result.append(
                    Document(
                        page_content=parent_text, metadata=parent_metadata
                    )
                )
                result.extend(child_docs)
                child_offset += len(assigned_children)

        return result

    def _generate_chunk_id(self) -> str:
        return str(uuid.uuid4())

    def get_strategy_name(self) -> str:
        return "parent_child"

    def get_chunk_size(self) -> int:
        return self._child_config.chunk_size
```

### 5.5 ChunkingStrategyFactory 확장

**파일**: `src/infrastructure/chunking/chunking_factory.py`

```python
# _create_parent_child_strategy 메서드 수정

@classmethod
def _create_parent_child_strategy(cls, **kwargs) -> ParentChildStrategy:
    parent_chunk_size = kwargs.get("parent_chunk_size", cls.DEFAULT_PARENT_SIZE)
    child_chunk_size = kwargs.get("child_chunk_size", cls.DEFAULT_CHILD_SIZE)
    child_chunk_overlap = kwargs.get("child_chunk_overlap", cls.DEFAULT_CHILD_OVERLAP)
    table_flattening = kwargs.get("table_flattening", True)

    parent_config = ChunkingConfig(chunk_size=parent_chunk_size, chunk_overlap=0)
    child_config = ChunkingConfig(
        chunk_size=child_chunk_size, chunk_overlap=child_chunk_overlap
    )

    table_preprocessor = None
    if table_flattening:
        from src.infrastructure.chunking.table_flattening.rule_based_generator import (
            RuleBasedTableContentGenerator,
        )
        from src.infrastructure.chunking.table_flattening.preprocessor import (
            TableFlatteningPreprocessor,
        )
        generator = RuleBasedTableContentGenerator()
        table_preprocessor = TableFlatteningPreprocessor(generator)

    return ParentChildStrategy(
        parent_config=parent_config,
        child_config=child_config,
        table_preprocessor=table_preprocessor,
    )
```

---

## 6. Error Handling

### 6.1 에러 시나리오

| 시나리오 | 처리 | 결과 |
|---------|------|------|
| 표 감지 실패 (비표준 markdown) | `_detect_tables()` → 빈 리스트 반환 | 원본 텍스트로 기존 청킹 실행 |
| 표 파싱 실패 (헤더 없음, 행 불일치) | `generate()` → `parse_failed: True`, 원본 반환 | 해당 표만 원본 유지 |
| `has_table` 메타데이터 없음 | `_chunk_document()` → `has_table=False` | 기존 로직 실행 |
| `table_preprocessor=None` | `_chunk_document()` → 기존 로직 | 기존 로직 실행 |
| 빈 텍스트 | `_chunk_default()` → 빈 리스트 | 빈 리스트 반환 |

### 6.2 Graceful Degradation 원칙

**모든 실패 경로에서 원본 텍스트가 손실되지 않는다.** 전처리 실패 시 기존 parent_child 로직으로 fallback.

---

## 7. Security Considerations

- [x] 외부 입력 없음 — 파서가 생성한 내부 데이터만 처리
- [x] 정규식 DoS 방지 — 단순 패턴만 사용, 역추적 없음
- [x] 메모리 안전 — 표 변환 결과가 원본보다 커질 수 있으나, 토큰 기반 청킹이 크기 제한
- [x] 원본 보존 — 부모 chunk에 항상 원본 보존, 데이터 손실 위험 없음

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | 파일 |
|------|--------|------|
| Unit Test | `RuleBasedTableContentGenerator` | `tests/infrastructure/chunking/table_flattening/test_rule_based_generator.py` |
| Unit Test | `TableFlatteningPreprocessor` | `tests/infrastructure/chunking/table_flattening/test_preprocessor.py` |
| Unit Test | `ParentChildStrategy` (표 통합) | `tests/infrastructure/chunking/test_parent_child_strategy.py` (기존 파일에 추가) |
| Unit Test | `ChunkingStrategyFactory` 확장 | `tests/infrastructure/chunking/test_chunking_factory.py` (기존 파일에 추가) |

### 8.2 Test Cases — RuleBasedTableContentGenerator

| Test Case | 설명 |
|-----------|------|
| `test_generate_simple_table` | 2행 2열 단순 표 → 2개 의미 문장 |
| `test_generate_with_section_title` | 섹션 제목 접두어 포함 확인 |
| `test_generate_without_section_title` | 섹션 제목 없을 때 접두어 생략 |
| `test_generate_numeric_data_detected` | 숫자/퍼센트/원 포함 시 `has_numeric_data=True` |
| `test_generate_empty_cells_skipped` | 빈 셀은 의미 문장에서 제외 |
| `test_generate_header_only_table` | 데이터 행 없으면 원본 반환 + `parse_failed` |
| `test_generate_mismatched_columns` | 헤더-데이터 컬럼 수 불일치 행 스킵 |
| `test_generate_preserves_original` | `original_markdown` 필드에 원본 보존 |
| `test_metadata_has_columns_and_row_count` | 메타데이터 필드 검증 |

### 8.3 Test Cases — TableFlatteningPreprocessor

| Test Case | 설명 |
|-----------|------|
| `test_no_table_passthrough` | 표 없는 텍스트 → `parent_text == child_text`, `table_count=0` |
| `test_single_table_detected` | 단일 표 감지 + 변환 |
| `test_multiple_tables_detected` | 복수 표 모두 감지 + 각각 변환 |
| `test_surrounding_text_preserved` | 표 전후 텍스트 보존 (parent & child 모두) |
| `test_parent_text_unchanged` | `parent_text`가 항상 원본과 동일 |
| `test_child_text_has_sentences` | `child_text`에 의미 문장 포함, markdown 표 없음 |
| `test_table_at_end_of_text` | 텍스트 끝에 위치한 표 감지 |
| `test_table_at_start_of_text` | 텍스트 시작에 위치한 표 감지 |
| `test_non_table_pipe_lines_ignored` | `|` 포함하지만 구분선 없는 텍스트는 표로 미감지 |
| `test_metadata_merged_for_multiple_tables` | 복수 표 메타데이터 병합 |

### 8.4 Test Cases — ParentChildStrategy (표 통합)

| Test Case | 설명 |
|-----------|------|
| `test_table_doc_parent_has_original_markdown` | 부모 chunk에 원본 markdown 표 보존 |
| `test_table_doc_child_has_semantic_sentences` | 자식 chunk에 의미 문장 포함, 표 미포함 |
| `test_table_doc_child_metadata_has_table_flattened` | 자식에 `table_flattened: True` |
| `test_table_doc_parent_metadata_has_table_count` | 부모에 `table_count` 메타데이터 |
| `test_no_table_doc_uses_default_logic` | `has_table=False` → 기존 로직 |
| `test_no_preprocessor_uses_default_logic` | `table_preprocessor=None` → 기존 로직 |
| `test_parent_child_relationship_intact` | 표 flatten 후에도 `parent_id ↔ children_ids` 정상 |
| `test_existing_tests_still_pass` | 기존 12개 테스트 전체 회귀 없음 |

### 8.5 Test Cases — ChunkingStrategyFactory

| Test Case | 설명 |
|-----------|------|
| `test_parent_child_with_table_flattening_true` | `table_flattening=True` → preprocessor 주입 확인 |
| `test_parent_child_with_table_flattening_false` | `table_flattening=False` → preprocessor=None |
| `test_parent_child_default_has_table_flattening` | 기본값이 `True`인지 확인 |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | `TableContentGenerator` (인터페이스), VO | `src/domain/chunking/table_content_generator.py` |
| **Infrastructure** | `RuleBasedTableContentGenerator`, `TableFlatteningPreprocessor` | `src/infrastructure/chunking/table_flattening/` |
| **Infrastructure** | `ParentChildStrategy` (수정) | `src/infrastructure/chunking/strategies/parent_child_strategy.py` |
| **Infrastructure** | `ChunkingStrategyFactory` (수정) | `src/infrastructure/chunking/chunking_factory.py` |
| **Application** | `IngestDocumentUseCase` (변경 없음) | `src/application/ingest/ingest_use_case.py` |
| **Interface** | API routes (변경 없음) | `src/api/routes/` |

### 9.2 Dependency Rules

```
ParentChildStrategy ──→ TableFlatteningPreprocessor ──→ TableContentGenerator (ABC)
                                                              ▲
                                                              │
                                                   RuleBasedTableContentGenerator

ChunkingStrategyFactory ──→ ParentChildStrategy
                       ──→ TableFlatteningPreprocessor (DI 조립)
                       ──→ RuleBasedTableContentGenerator (DI 조립)
```

- Domain 레이어 변경: `table_content_generator.py` 신규 (인터페이스 + VO만)
- Infrastructure → Domain 방향 의존만 존재: **준수**
- Domain 내부에 Infrastructure 참조 없음: **준수**

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location | 변경 유형 |
|-----------|-------|----------|----------|
| `TableContentGenerator` | Domain | `src/domain/chunking/table_content_generator.py` | **신규** |
| `TableConversionResult` | Domain | (동일 파일) | **신규** |
| `TableSpan` | Domain | (동일 파일) | **신규** |
| `PreprocessResult` | Domain | (동일 파일) | **신규** |
| `RuleBasedTableContentGenerator` | Infrastructure | `src/infrastructure/chunking/table_flattening/rule_based_generator.py` | **신규** |
| `TableFlatteningPreprocessor` | Infrastructure | `src/infrastructure/chunking/table_flattening/preprocessor.py` | **신규** |
| `ParentChildStrategy` | Infrastructure | `src/infrastructure/chunking/strategies/parent_child_strategy.py` | **수정** |
| `ChunkingStrategyFactory` | Infrastructure | `src/infrastructure/chunking/chunking_factory.py` | **수정** |
| `ChunkingStrategy` | Domain | `src/domain/chunking/interfaces.py` | 변경 없음 |
| `ChunkingConfig` | Domain | `src/domain/chunking/value_objects.py` | 변경 없음 |
| `IngestDocumentUseCase` | Application | `src/application/ingest/ingest_use_case.py` | 변경 없음 |

---

## 10. Coding Convention Reference

### 10.1 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 클래스 네이밍 | `TableFlatteningPreprocessor`, `RuleBasedTableContentGenerator` — 역할 명확 |
| 파일 네이밍 | `preprocessor.py`, `rule_based_generator.py` — snake_case |
| 패키지 구조 | `table_flattening/` 패키지로 독립 분리 |
| 타입 힌트 | 모든 메서드에 파라미터·반환 타입 명시 |
| 함수 길이 | 40줄 이내 (private 메서드로 분리) |
| VO | `@dataclass(frozen=True)` — 불변성 보장 |
| DI | 팩토리에서 조립, 전략에 주입 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/domain/chunking/
├── interfaces.py                     # 변경 없음
├── value_objects.py                  # 변경 없음
└── table_content_generator.py        # ★ 신규

src/infrastructure/chunking/
├── base_token_chunker.py             # 변경 없음
├── chunking_factory.py               # 수정
├── table_flattening/                 # ★ 신규 패키지
│   ├── __init__.py
│   ├── preprocessor.py
│   └── rule_based_generator.py
└── strategies/
    ├── parent_child_strategy.py      # 수정
    ├── full_token_strategy.py        # 변경 없음
    ├── semantic_strategy.py          # 변경 없음
    └── section_aware_strategy.py     # 변경 없음

tests/infrastructure/chunking/
├── table_flattening/                 # ★ 신규 패키지
│   ├── __init__.py
│   ├── test_rule_based_generator.py
│   └── test_preprocessor.py
├── test_parent_child_strategy.py     # 수정 (테스트 추가)
└── test_chunking_factory.py          # 수정 (테스트 추가)
```

### 11.2 Implementation Order

```
Phase 1: 독립 모듈 (3~4h)
─────────────────────────────
1. [ ] domain/chunking/table_content_generator.py
       → TableContentGenerator ABC + TableConversionResult + TableSpan + PreprocessResult VO

2. [ ] tests/infrastructure/chunking/table_flattening/test_rule_based_generator.py
       → TDD Red: 9개 테스트 케이스

3. [ ] infrastructure/chunking/table_flattening/rule_based_generator.py
       → TDD Green: RuleBasedTableContentGenerator 구현

4. [ ] tests/infrastructure/chunking/table_flattening/test_preprocessor.py
       → TDD Red: 10개 테스트 케이스

5. [ ] infrastructure/chunking/table_flattening/preprocessor.py
       → TDD Green: TableFlatteningPreprocessor 구현

Phase 2: 파이프라인 통합 (2~3h)
─────────────────────────────
6. [ ] tests/infrastructure/chunking/test_parent_child_strategy.py
       → TDD Red: 8개 테스트 케이스 추가 (기존 12개 유지)

7. [ ] infrastructure/chunking/strategies/parent_child_strategy.py
       → TDD Green: _chunk_with_table_flattening 추가, _chunk_default 리팩토링

8. [ ] infrastructure/chunking/chunking_factory.py
       → table_flattening 옵션 추가 + DI 조립

9. [ ] tests/infrastructure/chunking/test_chunking_factory.py
       → 팩토리 테스트 3개 추가

10. [ ] 전체 테스트 실행 → 회귀 없음 확인
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-14 | Initial draft | 배상규 |
