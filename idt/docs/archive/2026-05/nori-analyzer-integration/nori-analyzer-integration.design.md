# nori-analyzer-integration Design Document

> **Summary**: ES Nori 한국어 분석기 도입으로 content 필드 BM25 검색 품질 근본 개선
>
> **Project**: sangplusbot (idt/)
> **Author**: 배상규
> **Date**: 2026-05-08
> **Status**: Draft
> **Planning Doc**: [nori-analyzer-integration.plan.md](../../01-plan/features/nori-analyzer-integration.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. `content` 필드에 Nori analyzer를 적용하여 인덱싱/검색 양방향 한국어 형태소 분석 활성화
2. `ensure_index_exists` 인터페이스를 settings를 지원하도록 확장
3. Nori 플러그인 미설치 환경에서도 Standard Analyzer로 graceful fallback
4. 기존 데이터 zero-downtime 마이그레이션 (Alias 전환 방식)

### 1.2 Design Principles

- 기존 인터페이스 시그니처 변경 최소화 (Optional 파라미터 추가)
- Kiwi morph_keywords 필드 유지 (태그/필터 용도로 계속 사용)
- content 필드 중심 검색으로 전환하되, morph_text는 보조 필드로 유지

---

## 2. Architecture

### 2.1 변경 영향 범위

```
┌─ domain/ ──────────────────────────────────────────────┐
│  elasticsearch/interfaces.py   ← ensure_index_exists   │
│                                   settings 파라미터 추가│
└────────────────────────────────────────────────────────┘
         │
┌─ infrastructure/ ──────────────────────────────────────┐
│  elasticsearch/es_index_mappings.py  ← settings 추가   │
│  elasticsearch/es_repository.py      ← settings 전달   │
└────────────────────────────────────────────────────────┘
         │
┌─ application/ ─────────────────────────────────────────┐
│  hybrid_search/use_case.py  ← 필드 부스트 조정         │
└────────────────────────────────────────────────────────┘
         │
┌─ interfaces/ (api) ───────────────────────────────────┐
│  main.py  ← _ensure_es_index()에 settings 전달        │
└────────────────────────────────────────────────────────┘
```

### 2.2 변경하지 않는 것

| 모듈 | 이유 |
|------|------|
| `es_client.py` | 커넥션 설정만 담당, 인덱스 매핑 무관 |
| `kiwi_morph_analyzer.py` | morph_keywords 추출용으로 계속 사용 |
| `unified_upload/use_case.py` | morph_text 생성 로직 유지 (Kiwi 키워드 보조 역할) |
| `collection_search/use_case.py` | HybridSearchUseCase를 통해 간접 호출, 변경 불필요 |
| RRF 정책 (`policies.py`) | 순위 기반 병합이라 BM25 점수 변동과 무관 |
| Parent-Child 청킹 전략 | 청킹은 ES 분석기와 무관 |

---

## 3. 상세 설계

### 3.1 ES 인덱스 Settings 정의

**파일**: `src/infrastructure/elasticsearch/es_index_mappings.py`

```python
"""Elasticsearch index mapping and settings definitions."""

DOCUMENTS_INDEX_SETTINGS: dict = {
    "analysis": {
        "tokenizer": {
            "nori_user_dict_tokenizer": {
                "type": "nori_tokenizer",
                "decompound_mode": "mixed",
            }
        },
        "filter": {
            "nori_posfilter": {
                "type": "nori_part_of_speech",
                "stoptags": [
                    "E", "IC", "J", "MAG", "MAJ",
                    "MM", "SP", "SSC", "SSO", "SC",
                    "SE", "XPN", "XSA", "XSN", "XSV",
                    "UNA", "NA", "VSV",
                ],
            }
        },
        "analyzer": {
            "nori_analyzer": {
                "type": "custom",
                "tokenizer": "nori_user_dict_tokenizer",
                "filter": ["nori_posfilter", "nori_readingform", "lowercase"],
            }
        },
    }
}

DOCUMENTS_INDEX_MAPPINGS: dict = {
    "properties": {
        "content": {"type": "text", "analyzer": "nori_analyzer"},
        "morph_text": {"type": "text"},
        "morph_keywords": {"type": "keyword"},
        "chunk_id": {"type": "keyword"},
        "chunk_type": {"type": "keyword"},
        "chunk_index": {"type": "integer"},
        "total_chunks": {"type": "integer"},
        "document_id": {"type": "keyword"},
        "user_id": {"type": "keyword"},
        "collection_name": {"type": "keyword"},
        "parent_id": {"type": "keyword"},
    }
}
```

**설계 결정**:

| 결정 | 선택 | 이유 |
|------|------|------|
| `content` analyzer | `nori_analyzer` | 주 검색 필드, 인덱싱+검색 양방향 한국어 분석 |
| `morph_text` analyzer | Standard (유지) | Kiwi가 이미 전처리한 키워드 텍스트, nori 이중 분석 불필요 |
| `decompound_mode` | `mixed` | 복합어 분해 + 원형 모두 인덱싱 (recall 최대화) |
| `nori_readingform` | 적용 | 한자 → 한글 읽기 변환 (금융 문서 대비) |
| stoptags | 조사/어미/접사 제거 | 내용어(명사/동사/형용사) 중심 인덱싱 |

**Nori POS Filter stoptags 설명**:

| 태그 | 의미 | 제거 이유 |
|------|------|----------|
| E | 어미 | 문법적 기능어 |
| J | 조사 | "을/를/이/가" 등 검색 노이즈 |
| IC | 감탄사 | 검색 무관 |
| MAG/MAJ | 부사 | 검색 정확도 저하 요인 |
| SP/SS*/SC/SE | 구두점/기호 | 검색 무관 |
| XPN/XSA/XSN/XSV | 접두사/접미사 | 단독 의미 없음 |

### 3.2 인터페이스 변경

**파일**: `src/domain/elasticsearch/interfaces.py`

```python
# 변경 전
@abstractmethod
async def ensure_index_exists(
    self, index: str, mappings: dict[str, Any]
) -> bool:

# 변경 후
@abstractmethod
async def ensure_index_exists(
    self, index: str, mappings: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
) -> bool:
```

Optional 파라미터 추가이므로 기존 호출부는 변경 없이 동작한다.

### 3.3 Repository 구현 변경

**파일**: `src/infrastructure/elasticsearch/es_repository.py`

```python
# 변경 전
async def ensure_index_exists(
    self, index: str, mappings: dict[str, Any]
) -> bool:
    ...
    await es.indices.create(index=index, mappings=mappings)
    ...

# 변경 후
async def ensure_index_exists(
    self, index: str, mappings: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
) -> bool:
    ...
    kwargs: dict[str, Any] = {"index": index, "mappings": mappings}
    if settings:
        kwargs["settings"] = settings
    await es.indices.create(**kwargs)
    ...
```

### 3.4 앱 시작 시 인덱스 초기화 변경

**파일**: `src/api/main.py` (`_ensure_es_index` 함수)

```python
# 변경 전
from src.infrastructure.elasticsearch.es_index_mappings import DOCUMENTS_INDEX_MAPPINGS
created = await es_repo.ensure_index_exists(
    settings.es_index, DOCUMENTS_INDEX_MAPPINGS
)

# 변경 후
from src.infrastructure.elasticsearch.es_index_mappings import (
    DOCUMENTS_INDEX_MAPPINGS,
    DOCUMENTS_INDEX_SETTINGS,
)

try:
    created = await es_repo.ensure_index_exists(
        settings.es_index, DOCUMENTS_INDEX_MAPPINGS,
        settings=DOCUMENTS_INDEX_SETTINGS,
    )
except Exception as e:
    # Nori 플러그인 미설치 시 settings 없이 재시도 (Standard Analyzer fallback)
    get_app_logger().warning(
        "ES index creation with nori failed, falling back to standard analyzer",
        exception=e,
    )
    created = await es_repo.ensure_index_exists(
        settings.es_index, DOCUMENTS_INDEX_MAPPINGS
    )
```

### 3.5 BM25 검색 쿼리 변경

**파일**: `src/application/hybrid_search/use_case.py` (`_fetch_bm25` 메서드)

```python
# 변경 전
multi_match_clause: dict = {
    "multi_match": {
        "query": request.query,
        "fields": ["content", "morph_text^1.5"],
        "type": "most_fields",
    }
}

# 변경 후
multi_match_clause: dict = {
    "multi_match": {
        "query": request.query,
        "fields": ["content^1.5", "morph_text"],
        "type": "most_fields",
    }
}
```

**변경 근거**: Nori 도입 후 `content` 필드가 형태소 분석되므로 주 검색 필드 역할. `morph_text`는 Kiwi 키워드 보조.

### 3.6 마이그레이션 스크립트

**파일**: `scripts/migrate_es_nori.py` (신규)

```
실행 순서:
1. documents_v2 인덱스 생성 (nori settings + mappings)
2. ES Reindex API로 documents → documents_v2 데이터 복사
3. Alias 전환: documents (alias) → documents_v2 (실제 인덱스)
4. 이전 인덱스 삭제 (수동 확인 후)
```

```python
async def migrate():
    """Zero-downtime ES 인덱스 마이그레이션."""
    es = AsyncElasticsearch(...)
    
    new_index = f"{INDEX_NAME}_v2"
    
    # 1. 새 인덱스 생성
    await es.indices.create(
        index=new_index,
        settings=DOCUMENTS_INDEX_SETTINGS,
        mappings=DOCUMENTS_INDEX_MAPPINGS,
    )
    
    # 2. Reindex (기존 → 신규)
    await es.reindex(
        source={"index": INDEX_NAME},
        dest={"index": new_index},
        wait_for_completion=True,
    )
    
    # 3. Alias 전환 (atomic)
    await es.indices.update_aliases(actions=[
        {"remove": {"index": INDEX_NAME, "alias": INDEX_NAME}},
        {"add": {"index": new_index, "alias": INDEX_NAME}},
    ])
    
    # 4. 이전 인덱스 삭제는 수동으로
```

**주의**: Reindex 시 `content` 필드의 텍스트는 그대로 복사되고, 새 인덱스의 nori_analyzer가 인덱싱 시점에 자동으로 토큰화를 재수행한다.

---

## 4. 파일별 변경 명세

| # | 파일 | 변경 유형 | 변경 내용 |
|---|------|----------|----------|
| 1 | `src/infrastructure/elasticsearch/es_index_mappings.py` | 수정 | `DOCUMENTS_INDEX_SETTINGS` dict 추가, `content` 필드에 `analyzer: nori_analyzer` 추가 |
| 2 | `src/domain/elasticsearch/interfaces.py` | 수정 | `ensure_index_exists`에 `settings: Optional[dict] = None` 파라미터 추가 |
| 3 | `src/infrastructure/elasticsearch/es_repository.py` | 수정 | `ensure_index_exists` 구현에 settings 전달 로직 추가 |
| 4 | `src/api/main.py` | 수정 | `_ensure_es_index()`에서 settings 전달 + fallback 로직 |
| 5 | `src/application/hybrid_search/use_case.py` | 수정 | `_fetch_bm25` 필드 부스트 `content^1.5`, `morph_text` 로 변경 |
| 6 | `scripts/migrate_es_nori.py` | 신규 | Reindex + Alias 전환 마이그레이션 스크립트 |

---

## 5. 에러 처리

### 5.1 Nori 플러그인 미설치 Fallback

```
앱 시작 → _ensure_es_index() 
  → settings(nori) 포함하여 인덱스 생성 시도
    → 성공: nori_analyzer 활성
    → 실패: settings 없이 재시도 (Standard Analyzer)
      → 성공: 기존 방식으로 동작 (morph_text 의존)
      → 실패: warning 로깅, 앱은 정상 시작 (기존 동작 유지)
```

### 5.2 마이그레이션 실패 대응

| 시나리오 | 대응 |
|----------|------|
| Reindex 중 네트워크 오류 | 새 인덱스 삭제 후 재시도 |
| Alias 전환 실패 | 수동으로 alias 지정 |
| 새 인덱스 문서 수 불일치 | count 비교 검증 후 재실행 |

---

## 6. 테스트 계획

### 6.1 단위 테스트

| 테스트 파일 | 검증 항목 | 우선순위 |
|------------|----------|---------|
| `tests/infrastructure/elasticsearch/test_es_index_mappings.py` | SETTINGS dict에 nori analyzer 정의 존재, MAPPINGS의 content 필드에 analyzer 지정 | High |
| `tests/infrastructure/elasticsearch/test_es_repository.py` | `ensure_index_exists(settings=...)` 호출 시 `es.indices.create`에 settings 전달 검증 | High |
| `tests/application/hybrid_search/test_hybrid_search_use_case.py` | multi_match fields가 `["content^1.5", "morph_text"]`인지 검증 | High |

### 6.2 통합 테스트

| 테스트 파일 | 검증 항목 | 우선순위 |
|------------|----------|---------|
| `tests/integration/test_nori_analyzer.py` | 실제 ES에 nori 인덱스 생성 → "대출심사기준" 인덱싱 → "대출 심사" 검색 시 매칭 확인 | Medium |

### 6.3 핵심 테스트 시나리오

```python
# 1. 매핑 구조 검증
def test_documents_index_settings_has_nori_analyzer():
    assert "analysis" in DOCUMENTS_INDEX_SETTINGS
    analyzer = DOCUMENTS_INDEX_SETTINGS["analysis"]["analyzer"]["nori_analyzer"]
    assert analyzer["tokenizer"] == "nori_user_dict_tokenizer"

def test_documents_index_mappings_content_uses_nori():
    content = DOCUMENTS_INDEX_MAPPINGS["properties"]["content"]
    assert content["analyzer"] == "nori_analyzer"

# 2. Repository settings 전달 검증
async def test_ensure_index_exists_passes_settings(mock_es):
    await repo.ensure_index_exists("idx", mappings, settings=nori_settings)
    mock_es.indices.create.assert_called_once_with(
        index="idx", mappings=mappings, settings=nori_settings
    )

# 3. 검색 쿼리 부스트 검증
async def test_bm25_query_boosts_content_field():
    # execute 호출 후 es_repo.search에 전달된 쿼리 확인
    query = captured_es_query.query
    fields = query["multi_match"]["fields"]
    assert fields == ["content^1.5", "morph_text"]
```

---

## 7. 구현 순서

```
1. [es_index_mappings.py]    SETTINGS + MAPPINGS 변경       ← 테스트 먼저
2. [interfaces.py]           ensure_index_exists 시그니처    ← 테스트 먼저
3. [es_repository.py]        settings 전달 구현             ← 테스트 먼저
4. [main.py]                 _ensure_es_index fallback      
5. [use_case.py]             필드 부스트 변경               ← 테스트 먼저
6. [migrate_es_nori.py]      마이그레이션 스크립트 작성      
7. 통합 테스트                                              
8. 기존 데이터 마이그레이션 실행                             
```

---

## 8. Nori 토큰화 예시 (검증 기준)

```
입력: "대출심사기준을 확인하세요"

Standard Analyzer (현재):
  → ["대출심사기준을", "확인하세요"]

Nori Analyzer (mixed + posfilter):
  → ["대출", "심사", "기준", "확인"]
  (조사 "을", 어미 "하세요" 제거됨)

검색 쿼리: "대출 심사"
  Standard: "대출" + "심사" → "대출심사기준을"과 불일치
  Nori:     "대출" + "심사" → "대출", "심사" 각각 매칭 ✅
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-08 | Initial draft | 배상규 |
