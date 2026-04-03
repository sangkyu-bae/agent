# ES-001: Elasticsearch 공통 Repository 모듈

> Task ID: ES-001
> 의존성: LOG-001
> 상태: Plan
> Plan 문서: docs/01-plan/features/elasticsearch.plan.md

---

## 목적

멀티 에이전트 및 프로젝트 전반에서 공통으로 사용할 최소 Elasticsearch 기반 레이어.
문서 색인(index), 전문 검색(full-text search), ID 기반 CRUD를 제공하는 기본 인터페이스만 정의한다.
이후 필요 기능(BM25 하이브리드 검색, 집계(aggregation), 자동완성 등)은 이 위에 확장한다.

---

## 구현 대상

### Domain Layer
| 파일 | 설명 |
|------|------|
| `src/domain/elasticsearch/interfaces.py` | `ElasticsearchRepositoryInterface` (추상) |
| `src/domain/elasticsearch/schemas.py` | `ESDocument`, `ESSearchResult`, `ESSearchQuery` Value Object |

### Infrastructure Layer
| 파일 | 설명 |
|------|------|
| `src/infrastructure/elasticsearch/es_client.py` | ES 비동기 연결 어댑터 (elasticsearch-py AsyncElasticsearch) |
| `src/infrastructure/elasticsearch/es_repository.py` | 기본 CRUD + 검색 구현 |
| `src/infrastructure/config/elasticsearch_config.py` | `ElasticsearchConfig` (pydantic-settings) |

---

## 인터페이스

```python
# src/domain/elasticsearch/schemas.py
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class ESDocument:
    """Elasticsearch에 저장할 단일 문서."""
    id: str
    body: dict[str, Any]
    index: str

@dataclass
class ESSearchQuery:
    """Elasticsearch 검색 요청 파라미터."""
    index: str
    query: dict[str, Any]          # ES query DSL (match, bool, term 등)
    size: int = 10
    from_: int = 0
    source_fields: list[str] = field(default_factory=list)  # 빈 경우 전체 반환

@dataclass
class ESSearchResult:
    """Elasticsearch 검색 결과 단일 히트."""
    id: str
    score: float
    source: dict[str, Any]
    index: str


# src/domain/elasticsearch/interfaces.py
from abc import ABC, abstractmethod
from typing import Optional
from src.domain.elasticsearch.schemas import ESDocument, ESSearchQuery, ESSearchResult

class ElasticsearchRepositoryInterface(ABC):

    @abstractmethod
    async def index(self, document: ESDocument, request_id: str) -> str:
        """문서 색인 (신규 또는 덮어쓰기). 저장된 document ID 반환."""

    @abstractmethod
    async def bulk_index(self, documents: list[ESDocument], request_id: str) -> int:
        """문서 대량 색인. 성공한 건수 반환."""

    @abstractmethod
    async def get(self, index: str, doc_id: str, request_id: str) -> Optional[dict]:
        """ID로 문서 조회. 없으면 None 반환."""

    @abstractmethod
    async def delete(self, index: str, doc_id: str, request_id: str) -> bool:
        """ID로 문서 삭제. 삭제 성공 여부 반환."""

    @abstractmethod
    async def search(self, query: ESSearchQuery, request_id: str) -> list[ESSearchResult]:
        """Query DSL 기반 검색. 히트 목록 반환."""

    @abstractmethod
    async def exists(self, index: str, doc_id: str, request_id: str) -> bool:
        """문서 존재 여부 확인."""

    @abstractmethod
    async def delete_by_query(self, index: str, query: dict, request_id: str) -> int:
        """쿼리 조건으로 문서 일괄 삭제. 삭제된 건수 반환."""
```

---

## 환경 변수

```env
ES_HOST=localhost
ES_PORT=9200
ES_SCHEME=http
ES_USERNAME=
ES_PASSWORD=
ES_CA_CERTS=
ES_MAX_RETRIES=3
ES_RETRY_ON_TIMEOUT=true
ES_REQUEST_TIMEOUT=30
```

---

## 예상 폴더 구조

```
src/
├── domain/
│   └── elasticsearch/
│       ├── __init__.py
│       ├── interfaces.py          # ElasticsearchRepositoryInterface (ABC)
│       └── schemas.py             # ESDocument, ESSearchQuery, ESSearchResult
│
└── infrastructure/
    ├── elasticsearch/
    │   ├── __init__.py
    │   ├── es_client.py           # AsyncElasticsearch 연결 어댑터
    │   └── es_repository.py       # ElasticsearchRepositoryInterface 구현체
    └── config/
        └── elasticsearch_config.py  # pydantic-settings ElasticsearchConfig

tests/
├── domain/
│   └── elasticsearch/
│       └── test_schemas.py        # Value Object 단위 테스트 (mock 금지)
└── infrastructure/
    └── elasticsearch/
        ├── test_es_client.py      # 연결/해제 (Mock AsyncElasticsearch)
        └── test_es_repository.py  # CRUD + 검색 (Mock 기반)
```

---

## 구현 상세

### ElasticsearchClient (infrastructure)

```python
# src/infrastructure/elasticsearch/es_client.py
from elasticsearch import AsyncElasticsearch
from src.infrastructure.config.elasticsearch_config import ElasticsearchConfig

class ElasticsearchClient:
    """AsyncElasticsearch 연결 어댑터."""

    def __init__(self, es: AsyncElasticsearch) -> None:
        self._es = es

    @classmethod
    def from_config(cls, config: ElasticsearchConfig) -> "ElasticsearchClient":
        """설정으로부터 ElasticsearchClient 생성."""
        kwargs: dict = {
            "hosts": [{"host": config.ES_HOST, "port": config.ES_PORT, "scheme": config.ES_SCHEME}],
            "max_retries": config.ES_MAX_RETRIES,
            "retry_on_timeout": config.ES_RETRY_ON_TIMEOUT,
            "request_timeout": config.ES_REQUEST_TIMEOUT,
        }
        if config.ES_USERNAME and config.ES_PASSWORD:
            kwargs["http_auth"] = (config.ES_USERNAME, config.ES_PASSWORD)
        if config.ES_CA_CERTS:
            kwargs["ca_certs"] = config.ES_CA_CERTS
        return cls(es=AsyncElasticsearch(**kwargs))

    def get_client(self) -> AsyncElasticsearch:
        """AsyncElasticsearch 인스턴스 반환."""
        return self._es

    async def close(self) -> None:
        """연결 종료."""
        await self._es.close()
```

### ElasticsearchRepository (infrastructure)

```python
# src/infrastructure/elasticsearch/es_repository.py
class ElasticsearchRepository(ElasticsearchRepositoryInterface):
    """ElasticsearchRepositoryInterface의 elasticsearch-py 구현체."""

    def __init__(self, client: ElasticsearchClient, logger: LoggerInterface) -> None:
        self._client = client
        self._logger = logger

    async def index(self, document: ESDocument, request_id: str) -> str:
        self._logger.info("ES index start", request_id=request_id, index=document.index, doc_id=document.id)
        try:
            es = self._client.get_client()
            resp = await es.index(index=document.index, id=document.id, body=document.body)
            self._logger.info("ES index completed", request_id=request_id, doc_id=document.id)
            return resp["_id"]
        except Exception as e:
            self._logger.error("ES index failed", exception=e, request_id=request_id)
            raise

    # bulk_index, get, delete, search, exists, delete_by_query 동일 패턴 적용
```

---

## 테스트 파일

| 테스트 파일 | 대상 | mock 여부 |
|------------|------|-----------|
| `tests/domain/elasticsearch/test_schemas.py` | ESDocument/ESSearchQuery/ESSearchResult 생성, 필드 검증 | ❌ (domain, mock 금지) |
| `tests/infrastructure/elasticsearch/test_es_client.py` | from_config 생성, get_client, close | ✅ Mock AsyncElasticsearch |
| `tests/infrastructure/elasticsearch/test_es_repository.py` | index/bulk_index/get/delete/search/exists/delete_by_query | ✅ Mock AsyncElasticsearch |

### 테스트 케이스 목록

#### test_es_repository.py
- `test_index_returns_doc_id` — 정상 index 시 doc_id 반환
- `test_index_logs_start_and_completion` — 로그 INFO × 2 기록 확인
- `test_index_raises_and_logs_error_on_exception` — 예외 시 ERROR 로그 + 재raise
- `test_bulk_index_returns_success_count` — 성공 건수 반환
- `test_bulk_index_partial_failure_logs_warning` — 일부 실패 시 WARNING 로그
- `test_get_returns_source_when_found` — 문서 조회 성공
- `test_get_returns_none_when_not_found` — NotFoundError → None 반환
- `test_delete_returns_true_when_deleted` — 삭제 성공
- `test_delete_returns_false_when_not_found` — 없는 문서 삭제 → False
- `test_search_returns_hits` — 검색 결과 ESSearchResult 목록 반환
- `test_search_respects_size_and_from` — size/from_ 파라미터 전달 확인
- `test_exists_returns_true_when_document_exists` — 존재 확인
- `test_exists_returns_false_when_not_found` — 없는 경우 False
- `test_delete_by_query_returns_deleted_count` — 삭제 건수 반환

---

## LOG-001 로깅 체크리스트

- [ ] `LoggerInterface` 주입 받아 사용 (ElasticsearchRepository)
- [ ] 주요 처리 시작/완료 INFO 로그 (`request_id` 포함)
- [ ] 예외 발생 시 ERROR 로그 + `exception=e` (스택 트레이스)
- [ ] `ES_PASSWORD` / `ES_USERNAME` 로그 마스킹
- [ ] `bulk_index` 부분 실패 시 WARNING 로그 기록

---

## 확장 포인트 (이 모듈 위에 구축할 수 있는 것들)

| 확장 | 설명 |
|------|------|
| HybridSearchRepository | BM25 + Vector 하이브리드 검색 (kNN + 전문 검색 혼합) |
| AggregationRepository | 집계(aggregation) 기반 통계 쿼리 |
| AutocompleteRepository | completion suggester 기반 자동완성 |
| ESIndexManager | 인덱스 매핑 생성/삭제/재색인(reindex) 관리 |

---

## 완료 기준

- [ ] `ESDocument`, `ESSearchQuery`, `ESSearchResult` Value Object 정의
- [ ] `ElasticsearchRepositoryInterface` 추상 클래스 정의
- [ ] `ElasticsearchClient` 비동기 연결 어댑터 (from_config 팩토리 포함)
- [ ] `ElasticsearchRepository` 구현 (index/bulk_index/get/delete/search/exists/delete_by_query)
- [ ] `ElasticsearchConfig` pydantic-settings 정의
- [ ] `.env.example` 환경 변수 추가
- [ ] 전체 테스트 통과 (Red → Green 순서 준수)
- [ ] LOG-001 로깅 적용 (request_id 전파, ERROR 시 스택 트레이스)
- [ ] `pyproject.toml`에 `elasticsearch[async]>=8.0.0` 추가
