# Plan: nori-analyzer-integration

> Feature: Elasticsearch Nori 한국어 분석기 도입 및 BM25 검색 품질 개선
> Created: 2026-05-08
> Status: Plan

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | ES Standard Analyzer가 한국어 어절을 분리하지 못해 검색 쿼리 측 형태소 분석이 누락되고, BM25 점수가 `morph_text` 단일 필드에 의존 |
| **Solution** | ES Nori 분석기를 인덱스 매핑에 적용하여 인덱싱/검색 양방향 한국어 토큰화 활성화 |
| **Function/UX Effect** | 복합어·조사 포함 검색에서 매칭 정확도 향상, "대출심사기준" ↔ "대출 심사" 양방향 검색 가능 |
| **Core Value** | 한국어 BM25 검색 품질의 근본적 개선으로 하이브리드 검색 전체 recall/precision 향상 |

---

## 1. 목적 (Why)

### 1.1 현재 문제

현재 ES는 Standard Analyzer만 사용하여 한국어를 어절(공백) 단위로만 분리한다.

```
"대출심사기준을 확인하세요"
  Standard Analyzer → ["대출심사기준을", "확인하세요"]
```

이를 보완하기 위해 Kiwi 형태소 분석기로 사전 처리한 `morph_text` 필드를 별도 저장하고 있지만, 두 가지 구조적 한계가 있다:

1. **검색 쿼리 측 분석 부재**: 사용자 검색어는 여전히 Standard Analyzer로 분석됨 → "대출심사"를 붙여 쓰면 한 토큰으로 처리
2. **BM25 통계 왜곡**: `morph_text`는 키워드만 나열한 필드라 문서 길이(doc_length)와 빈도(TF) 통계가 원본 텍스트와 괴리

### 1.2 기대 효과

Nori 분석기 도입으로:
- `content` 필드 자체에서 한국어 형태소 분석이 인덱싱/검색 양쪽에 적용
- BM25 TF-IDF 통계가 정상적으로 계산
- 동의어 사전, 사용자 사전으로 도메인 용어 커스터마이징 가능

### 1.3 관련 문서

- 현재 ES 전략 문서: `docs/architecture/elasticsearch-strategy.md`
- ES 인덱스 매핑: `src/infrastructure/elasticsearch/es_index_mappings.py`
- 하이브리드 검색 UseCase: `src/application/hybrid_search/use_case.py`

---

## 2. 기능 범위 (Scope)

### In Scope

- [ ] ES 인덱스 settings에 Nori analyzer 정의 (nori_tokenizer + nori_part_of_speech filter)
- [ ] `content` 필드 매핑을 `text` → `text (analyzer: nori_analyzer)` 로 변경
- [ ] `morph_text` 필드에도 nori analyzer 적용 (또는 필드 제거 검토)
- [ ] 인덱스 재생성 스크립트/마이그레이션 작성
- [ ] 기존 문서 재인덱싱 유틸리티 작성
- [ ] BM25 검색 쿼리 최적화 (필드 부스트 비율 재조정)
- [ ] nori 사용자 사전 설정 (금융/여신 도메인 용어)

### Out of Scope

- Qdrant 벡터 검색 로직 변경 (영향 없음)
- RRF 병합 알고리즘 변경 (가중치 튜닝은 별도 이슈)
- Parent-Child 청킹 전략 변경
- Kiwi 형태소 분석기 자체 제거 (morph_keywords는 유지, 태그/필터 용도)

---

## 3. 기술 의존성

| 모듈 | 파일 | 변경 필요 |
|------|------|----------|
| ES 인덱스 매핑 | `src/infrastructure/elasticsearch/es_index_mappings.py` | 매핑 + settings 추가 |
| ES 클라이언트 | `src/infrastructure/elasticsearch/es_client.py` | 변경 없음 |
| ES Repository | `src/infrastructure/elasticsearch/es_repository.py` | `ensure_index_exists`에 settings 전달 |
| 업로드 UseCase | `src/application/unified_upload/use_case.py` | morph_text 생성 로직 검토 |
| 하이브리드 검색 | `src/application/hybrid_search/use_case.py` | multi_match 필드/부스트 조정 |
| 앱 초기화 | `src/api/main.py` | 인덱스 생성 시 settings 포함 |
| Kiwi 형태소 분석기 | `src/infrastructure/morph/kiwi_morph_analyzer.py` | 변경 없음 (유지) |

### 외부 의존성

| 항목 | 요구사항 |
|------|---------|
| ES Nori 플러그인 | `elasticsearch-plugin install analysis-nori` 필요 |
| ES 버전 | 7.x 이상 (nori 플러그인 지원) |

---

## 4. 설계 개요

### 4.1 Nori Analyzer 인덱스 설정

```python
# es_index_mappings.py 에 추가할 settings
DOCUMENTS_INDEX_SETTINGS = {
    "analysis": {
        "tokenizer": {
            "nori_user_dict_tokenizer": {
                "type": "nori_tokenizer",
                "decompound_mode": "mixed",    # 복합어 분해 + 원형 유지
                # "user_dictionary": "userdict_ko.txt"  # 사용자 사전 (선택)
            }
        },
        "filter": {
            "nori_posfilter": {
                "type": "nori_part_of_speech",
                "stoptags": [
                    "E", "IC", "J", "MAG", "MAJ",
                    "MM", "SP", "SSC", "SSO", "SC",
                    "SE", "XPN", "XSA", "XSN", "XSV",
                    "UNA", "NA", "VSV"
                ]
            }
        },
        "analyzer": {
            "nori_analyzer": {
                "type": "custom",
                "tokenizer": "nori_user_dict_tokenizer",
                "filter": ["nori_posfilter", "nori_readingform", "lowercase"]
            }
        }
    }
}
```

### 4.2 매핑 변경

| 필드 | 현재 | 변경 후 |
|------|------|---------|
| `content` | `{"type": "text"}` | `{"type": "text", "analyzer": "nori_analyzer"}` |
| `morph_text` | `{"type": "text"}` | `{"type": "text", "analyzer": "nori_analyzer"}` 또는 필드 유지+Standard |
| 나머지 필드 | 동일 | 동일 |

### 4.3 검색 쿼리 변경

```python
# 변경 전
"fields": ["content", "morph_text^1.5"]

# 변경 후 (nori가 content를 제대로 분석하므로 content 가중치 상향)
"fields": ["content^1.5", "morph_text"]
```

Nori 도입 후 `content` 필드가 주 검색 필드가 되고, `morph_text`는 보조 역할로 전환된다.

### 4.4 마이그레이션 전략

기존 인덱스의 analyzer는 변경할 수 없으므로:

1. 새 인덱스 `documents_v2` 생성 (nori settings 포함)
2. 기존 `documents` → `documents_v2` Reindex API로 데이터 이전
3. 별칭(alias) `documents` → `documents_v2` 전환
4. 이전 인덱스 삭제

---

## 5. TDD 계획

| 테스트 파일 | 검증 항목 |
|------------|----------|
| `tests/infrastructure/elasticsearch/test_es_index_mappings.py` | nori settings/mappings 구조 검증 |
| `tests/infrastructure/elasticsearch/test_es_repository.py` | ensure_index_exists에 settings 전달 검증 |
| `tests/application/hybrid_search/test_hybrid_search_use_case.py` | 변경된 multi_match 쿼리 구조 검증 |
| `tests/integration/test_nori_analyzer.py` | (통합) 실제 ES에서 nori 토큰화 동작 검증 |

---

## 6. CLAUDE.md 규칙 체크

- [x] domain에 외부 의존성 없음 (ES 설정은 infrastructure에 위치)
- [x] application은 도메인 규칙 조합만 수행
- [x] infrastructure 어댑터에서 ES 매핑/설정 관리
- [x] 기존 인터페이스(ElasticsearchRepositoryInterface) 변경 불필요
- [x] TDD 순서: 테스트 → 구현

---

## 7. 리스크 및 대응

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Nori 플러그인 미설치 시 인덱스 생성 실패 | High | Medium | 앱 시작 시 플러그인 존재 여부 체크, 미설치 시 Standard Analyzer fallback |
| 재인덱싱 중 서비스 중단 | Medium | Low | Alias 전환 방식으로 zero-downtime 마이그레이션 |
| morph_text 필드 역할 변경으로 검색 품질 일시 변동 | Medium | Medium | A/B 검색 비교 테스트 후 부스트 비율 최종 결정 |
| 사용자 사전 미반영 도메인 용어 분절 오류 | Low | Medium | 금융 용어 사전을 초기 seed로 제공 |

---

## 8. 구현 순서

1. [ ] ES Nori 플러그인 설치 확인 및 환경 준비
2. [ ] `es_index_mappings.py`에 settings + 매핑 변경
3. [ ] `es_repository.py`의 `ensure_index_exists`에 settings 파라미터 추가
4. [ ] `main.py` 인덱스 초기화 코드에 settings 전달
5. [ ] `hybrid_search/use_case.py` 검색 쿼리 필드 부스트 조정
6. [ ] 재인덱싱 스크립트 작성 (Reindex API + Alias 전환)
7. [ ] 단위 테스트 작성 및 통과
8. [ ] 통합 테스트 (실제 ES에서 한국어 토큰화 검증)
9. [ ] 기존 데이터 마이그레이션 실행

---

## 9. 완료 기준

- [ ] `content` 필드에 nori_analyzer 적용된 인덱스 정상 생성
- [ ] "대출심사기준" 검색 시 "대출", "심사", "기준" 각각 매칭 확인
- [ ] 기존 문서 재인덱싱 완료 (데이터 손실 없음)
- [ ] 하이브리드 검색 API 정상 동작 (BM25 + 벡터 RRF)
- [ ] 테스트 커버리지 유지
- [ ] LOG-001 로깅 적용

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-08 | Initial draft | 배상규 |
