# clause-aware-chunking Design Document

> **Plan**: `docs/01-plan/features/clause-aware-chunking.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-07
> **Status**: Draft

---

## 1. 설계 요약

조·항 의미 경계 우선 청킹 파이프라인을 additive-only로 추가한다. 4개 블록:

1. `chunking_profile` MySQL 테이블(경계 규칙 + 기본값) + domain/application/infrastructure 신규 모듈 + 기본 프로파일 시드
2. 관리자 CRUD `/api/v1/admin/chunking/profiles` + 사용자 조회 `/api/v1/chunking/profiles`
3. `knowledge_base` additive ALTER(옵트인 플래그 + 프로파일/토큰/overlap 오버라이드) + KB 생성/조회 API 확장
4. `ClauseAwareStrategy`(조=parent, 항·호=child, 기존 메타데이터 계약 준수) + 업로드 opt-in 경로(`UnifiedUploadRequest.chunking_config` additive)

### 코드 확인으로 확정된 사실 (2026-07-07)

| 확인 항목 | 결과 | 영향 |
|-----------|------|------|
| 파서 산출 단위 | `parse_bytes` → **페이지당 Document 1개** (`unified_upload/use_case.py:84-87`, total_pages=len) | 조가 페이지 경계를 넘을 수 있음 → 전략이 페이지를 결합 후 분할 (D8) |
| parent/child 메타데이터 계약 | `{chunk_type, chunk_id, parent_id, children_ids, chunk_index, total_chunks}` (`parent_child_strategy.py:57-110`). child의 chunk_index/total_chunks는 문서 전체 기준 재부여 | 신규 전략이 동일 계약 산출 → 검색 무수정 (D9) |
| `VALID_CHUNK_TYPES` | `{"parent","child","full","semantic"}` (`domain/chunking/value_objects.py:6`) | chunk_type은 `parent`/`child` 그대로 사용, 확장 불필요 |
| 토큰 분할+overlap | `BaseTokenChunker.split_by_tokens()`가 이미 구현 (`base_token_chunker.py:38-71`) | ②③단계 재사용, 신규 토큰 로직 없음 |
| 업로드 하드코딩 지점 | 전략 생성(89-94행), `chunk_strategy="parent_child"` 기록(146행), 응답 `chunking_config`(189-194행) — 3곳 | `chunking_config` optional 필드로 3곳 분기 (D10) |
| `UnifiedUploadRequest` | frozen dataclass, `extra_metadata` additive 선례 (`unified_upload/schemas.py:14`) | 동일 패턴으로 `chunking_config: UploadChunkingConfig | None = None` 추가 |
| KB 테이블/엔티티/라우터 | V040 + `CreateKnowledgeBaseBody`에 청킹 필드 없음. 업로드 Query로 child 값 수신 (`knowledge_base_router.py:211-212`) | additive ALTER(V042) + optional body 필드 (D5), Query 우선순위 규칙 (D6) |
| admin 라우터 선례 | `admin_collection_router.py` — `require_role("admin")` + 위임 패턴 | 동일 패턴으로 admin_chunking_router 작성 |
| 시드 마이그레이션 선례 | `V008__seed_internal_tools.sql` | 기본 프로파일을 V041에서 INSERT 시드 (D4) |
| ES 저장 | `_store_to_es`는 고정 필드 화이트리스트 (`use_case.py:262-280`) | 신규 메타(clause_title 등)는 Qdrant payload에만 전파 — 검색 격리와 무관하므로 ES 매핑 수정 **불필요** |

---

## 2. 설계 결정 (Decisions)

| ID | 결정 | 근거 |
|----|------|------|
| D1 | 경계 규칙은 `chunking_profile.boundary_rules` **JSON 컬럼**에 저장. 형식: `[{"pattern": str, "priority": int, "level": "parent"\|"child"}]` | 규칙은 프로파일 단위로만 읽고 씀(개별 규칙 쿼리 불필요) — 자식 테이블은 과도한 정규화(두꺼운 DDD 금지) |
| D2 | 프로파일이 **경계 규칙 + 기본값 세트**를 함께 보유: `parent_chunk_size`(조 상한), `chunk_size`(child), `chunk_overlap`. 전역 기본 = `is_default=1` 프로파일 | 문서 유형별로 적정 토큰이 다름 — "관리자 기본값"을 프로파일에 내장해 별도 설정 테이블 불필요 |
| D3 | `is_default` 유일성은 **UseCase가 단일 세션에서 보장**(기존 default 해제 + 신규 지정). DB 제약 없음. default 프로파일은 삭제 불가(422) | MySQL은 partial unique 미지원. 세션 규칙(UseCase 단일 세션) 내 원자성 확보 |
| D4 | 기본 프로파일 1건을 **V041 마이그레이션에서 시드**(id 고정 UUID, `is_default=1`, 국내 법령·규정 표준 패턴, 2000/500/50 — 기존 하드코딩 기본과 동일 값) | V008 시드 선례. 스타트업 시드는 다중 인스턴스 경합 리스크. 기존 기본값과 동일해 이행 시 동작 예측 가능 |
| D5 | KB additive 컬럼(V042): `use_clause_chunking`(bool, NOT NULL DEFAULT 0 — **opt-in 스위치**), `chunking_profile_id`(NULL=업로드 시점 default 프로파일), `chunk_size`/`chunk_overlap`(NULL=프로파일 값). **NULL = late binding, 값 = 사용자 오버라이드 고정** | Plan §4-1. 스위치와 프로파일 지정을 분리해 "기본 프로파일 따르는 opt-in"(profile_id NULL) 표현 가능 |
| D6 | `use_clause_chunking=true`인 KB 업로드에서 Query `child_chunk_size`/`child_chunk_overlap`은 **무시**(warning 로그). 422 거부하지 않음 | 기존 호출부(프론트) 무수정 원칙. 설정의 단일 출처는 KB 레코드 |
| D7 | KB 오버라이드 검증: `chunk_size` 100~4000, `chunk_overlap` 0~500(기존 Query 범위와 동일), **overlap 지정 시 size 지정 필수** + overlap < size | overlap만 지정하면 upload 시점 프로파일 size와 교차 검증이 필요해짐 — 생성 시점 완결 검증으로 단순화 |
| D8 | `ClauseAwareStrategy`는 문서의 **전체 페이지를 결합 후 분할**: 페이지 텍스트를 `\n\n`으로 join하며 offset→페이지 매핑을 기록, 각 parent에 `page_start`/`page_end` 주입(메타데이터 베이스는 첫 페이지) | 조가 페이지 경계를 넘는 것이 법령·규정 문서의 일반 형태 — 페이지 단위 분할은 조 무결성 훼손. 기존 전략들은 무수정이므로 회귀 없음 |
| D9 | 산출 계약: 기존 parent_child와 **완전 동일 필드**(chunk_type=parent/child, chunk_id, parent_id, children_ids, chunk_index, total_chunks — child index 문서 전체 재부여 포함) + 추가 필드 `clause_title`(조 번호·제목), `page_start`, `page_end`, `boundary`("clause"\|"token"\|"fallback") | FR-06. 추가 필드는 Qdrant payload로만 전파(ES 화이트리스트 미포함) — 검색 영향 없음 |
| D10 | `UnifiedUploadRequest`에 `chunking_config: UploadChunkingConfig | None = None` additive 추가. `UploadChunkingConfig = {strategy: str, params: dict, display: dict}`. None이면 기존 하드코딩 경로 그대로, 있으면 factory에 위임 + `display`를 metadata/응답에 기록 | extra_metadata 선례(D2, knowledge-base-scoping). unified_upload가 프로파일 도메인을 모르게 dict 기반 전달 — 레이어 결합 차단 |
| D11 | 프로파일 해석은 신규 `ChunkingSettingsResolver`(application/knowledge_base): KB → `use_clause_chunking` false면 None / true면 프로파일 로드(지정 or default) → KB 오버라이드 병합 → `UploadChunkingConfig` 반환. **참조 프로파일이 soft-deleted면 default 프로파일 폴백 + warning** | 업로드 실패 금지(FR-07 정신). 해석 로직을 UseCase에서 분리해 40줄 규칙 준수 |
| D12 | 규칙 검증(`ChunkingProfilePolicy`): `re.compile` 성공 필수, 패턴 1~200자, 규칙 1~50개, level ∈ {parent, child}, parent 규칙 최소 1개, priority는 int(정렬 키). 프로파일 이름 1~100자·소유 개념 없음(관리자 전역)·active 이름 중복 금지 | NFR-07(ReDoS 노출 최소화 — 길이/개수 상한 + 컴파일 검증). 매치 대상도 페이지 결합 텍스트로 유한 |
| D13 | 표 처리: `clause_aware`는 **이번 사이클에서 table_flattening 미적용**(조문 문서가 1차 대상). `has_table` 페이지가 섞여도 텍스트로 처리. 표 최적화는 후속 | 범위 통제. 기존 경로는 계속 table_flattening 적용되므로 표 중심 문서는 기존 경로 사용 가능 |
| D14 | 사용자 조회는 `GET /api/v1/chunking/profiles` 단일 엔드포인트(active만, `is_default` 포함) — 프리필은 프론트가 is_default 항목 사용. 별도 defaults 엔드포인트 없음 | 엔드포인트 최소화. 목록에 기본값이 모두 포함됨 |
| D15 | 프로파일 CRUD의 activity log 연동 없음 — StructuredLogger 로깅만 | knowledge-base-scoping D11 선례 (ActionType enum 확장 회피) |
| D16 | 짧은 항 병합: child 후보(항·호 세그먼트)를 **순서대로 chunk_size 이내 그리디 병합** — 여러 짧은 항이 한 child에 담기되 경계에서만 이어붙임. chunk_size 초과 세그먼트만 `split_by_tokens`(overlap 적용) | 항 단위가 한 문장인 경우가 흔함 — 과분할은 검색 노이즈. ①경계 우선 ②초과 시에만 토큰 분할 ③overlap 요구와 정확히 일치 |

---

## 3. 파일 구조 (신규/수정)

```
idt/
├── db/migration/
│   ├── V041__create_chunking_profile.sql                     [신규] (+기본 프로파일 시드)
│   └── V042__alter_knowledge_base_add_chunking.sql           [신규]
├── src/
│   ├── domain/chunking_profile/
│   │   ├── __init__.py                                       [신규]
│   │   ├── entities.py        # ChunkingProfile, BoundaryRule [신규]
│   │   ├── interfaces.py      # ChunkingProfileRepositoryInterface [신규]
│   │   └── policy.py          # ChunkingProfilePolicy         [신규]
│   ├── application/chunking_profile/
│   │   ├── __init__.py                                       [신규]
│   │   └── use_case.py        # ChunkingProfileUseCase (관리자 CRUD + 사용자 목록) [신규]
│   ├── application/knowledge_base/
│   │   ├── chunking_resolver.py # ChunkingSettingsResolver   [신규]
│   │   ├── use_case.py        # create에 청킹 설정 검증·저장  [수정: additive]
│   │   └── upload_use_case.py # resolver 경유 chunking_config 위임 [수정: additive]
│   ├── application/unified_upload/
│   │   ├── schemas.py         # UploadChunkingConfig + 필드   [수정: additive]
│   │   └── use_case.py        # 전략 선택/기록 3곳 분기       [수정: additive]
│   ├── domain/knowledge_base/entities.py                     [수정: additive 필드 4개]
│   ├── infrastructure/
│   │   ├── persistence/models/chunking_profile.py            [신규]
│   │   ├── persistence/models/knowledge_base.py              [수정: additive 컬럼 4개]
│   │   ├── chunking_profile/repository.py                    [신규]
│   │   ├── knowledge_base/repository.py                      [수정: 매핑 additive]
│   │   └── chunking/
│   │       ├── chunking_factory.py    # CLAUSE_AWARE 등록     [수정: additive]
│   │       └── strategies/clause_aware_strategy.py           [신규]
│   ├── api/routes/
│   │   ├── admin_chunking_router.py   # /api/v1/admin/chunking [신규]
│   │   ├── chunking_profile_router.py # /api/v1/chunking       [신규]
│   │   └── knowledge_base_router.py   # body/응답 청킹 필드    [수정: additive]
│   └── api/main.py            # 라우터 등록 + DI 배선          [수정: 추가만]
└── tests/
    ├── domain/chunking_profile/test_policy.py                [신규]
    ├── application/chunking_profile/test_use_case.py         [신규]
    ├── application/knowledge_base/test_chunking_resolver.py  [신규]
    ├── application/knowledge_base/test_upload_chunking.py    [신규]
    ├── application/unified_upload/test_chunking_config.py    [신규] (회귀 가드 포함)
    ├── infrastructure/chunking/test_clause_aware_strategy.py [신규]
    └── api/
        ├── test_admin_chunking_router.py                     [신규]
        ├── test_chunking_profile_router.py                   [신규]
        └── test_knowledge_base_router.py                     [수정: 케이스 추가]
```

---

## 4. DB 스키마

### 4.1 `V041__create_chunking_profile.sql`

```sql
-- clause-aware-chunking Design §4.1:
-- 청킹 프로파일 — 조·항 경계 규칙(JSON) + 문서 유형별 기본 토큰/overlap.
-- 전역 기본 = is_default=1 (유일성은 UseCase 단일 세션이 보장, D3).
-- soft delete(status): KB가 참조 중일 수 있어 레코드 보존 (D11 폴백).
-- ⚠️ FK 콜레이션 주의(errno 3780): CHARSET/COLLATE 명시 금지 (V037 선례).
CREATE TABLE chunking_profile (
    id                VARCHAR(36)  NOT NULL PRIMARY KEY,
    name              VARCHAR(100) NOT NULL,
    description       VARCHAR(500) NULL,
    boundary_rules    JSON         NOT NULL COMMENT '[{"pattern","priority","level":"parent|child"}]',
    parent_chunk_size INT          NOT NULL DEFAULT 2000 COMMENT '조(parent) 토큰 상한',
    chunk_size        INT          NOT NULL DEFAULT 500  COMMENT 'child 토큰 상한',
    chunk_overlap     INT          NOT NULL DEFAULT 50   COMMENT '토큰 분할 시 overlap',
    is_default        TINYINT(1)   NOT NULL DEFAULT 0,
    status            VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT 'active | deleted',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_chunking_profile_status (status),
    INDEX idx_chunking_profile_default (is_default, status)
) ENGINE=InnoDB;

-- 기본 프로파일 시드 (D4) — 기존 하드코딩 기본값(2000/500/50)과 동일, 이행 시 동작 예측 가능
INSERT INTO chunking_profile
    (id, name, description, boundary_rules, parent_chunk_size, chunk_size, chunk_overlap, is_default)
VALUES (
    'a0000000-0000-4000-8000-000000000001',
    '법령·규정 기본',
    '제N조/제N조의N을 조(parent) 경계로, 항(①…) 및 호(1., 가.)를 child 경계로 분할',
    JSON_ARRAY(
        JSON_OBJECT('pattern', '^제\\s*[0-9]+\\s*조(의\\s*[0-9]+)?\\s*(\\(|\\uFF08)', 'priority', 1, 'level', 'parent'),
        JSON_OBJECT('pattern', '^제\\s*[0-9]+\\s*조(의\\s*[0-9]+)?\\b',               'priority', 2, 'level', 'parent'),
        JSON_OBJECT('pattern', '^\\s*[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]',                     'priority', 1, 'level', 'child'),
        JSON_OBJECT('pattern', '^\\s*[0-9]+\\.\\s',                                   'priority', 2, 'level', 'child'),
        JSON_OBJECT('pattern', '^\\s*[가나다라마바사아자차카타파하]\\.\\s',            'priority', 3, 'level', 'child')
    ),
    2000, 500, 50, 1
);
```

> 시드 패턴은 Do 단계에서 실제 문서 샘플로 검증 후 미세 조정 가능(테이블 데이터이므로 코드 무수정).

### 4.2 `V042__alter_knowledge_base_add_chunking.sql`

```sql
-- clause-aware-chunking Design §4.2 (additive):
-- use_clause_chunking = opt-in 스위치 (D5). NULL 컬럼 = 업로드 시점 late binding:
--   chunking_profile_id NULL → default 프로파일 / chunk_size·overlap NULL → 프로파일 값.
ALTER TABLE knowledge_base
    ADD COLUMN use_clause_chunking TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN chunking_profile_id VARCHAR(36) NULL,
    ADD COLUMN chunk_size INT NULL,
    ADD COLUMN chunk_overlap INT NULL,
    ADD CONSTRAINT fk_kb_chunking_profile FOREIGN KEY (chunking_profile_id)
        REFERENCES chunking_profile(id);
```

---

## 5. Domain Layer

### 5.1 `domain/chunking_profile/entities.py`

```python
@dataclass(frozen=True)
class BoundaryRule:
    pattern: str
    priority: int
    level: str                       # "parent" | "child"

@dataclass
class ChunkingProfile:
    name: str
    boundary_rules: list[BoundaryRule]
    parent_chunk_size: int = 2000
    chunk_size: int = 500
    chunk_overlap: int = 50
    description: str | None = None
    is_default: bool = False
    id: str | None = None            # UUID v4
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def parent_patterns(self) -> list[str]:   # priority 오름차순 정렬
    def child_patterns(self) -> list[str]:
```

### 5.2 `domain/chunking_profile/policy.py` — `ChunkingProfilePolicy` (D12)

| 메서드 | 규칙 |
|--------|------|
| `validate_name(name)` | strip 후 1~100자, 제어문자 금지 (KB 정책과 동형) |
| `validate_rules(rules)` | 1~50개 / pattern 1~200자 / `re.compile` 성공 / level ∈ {parent, child} / **parent 규칙 ≥ 1개** |
| `validate_sizes(parent_chunk_size, chunk_size, chunk_overlap)` | parent 100~8000, child 100~4000, overlap 0~500, overlap < chunk_size, chunk_size ≤ parent_chunk_size |
| `validate_kb_override(chunk_size, chunk_overlap)` | 둘 다 optional. **overlap 지정 시 size 필수** + overlap < size + 위 범위 (D7) |
| `can_delete(profile)` | `is_default`면 거부(ValueError) — "default profile cannot be deleted" |

정책은 `re` 표준 라이브러리만 사용(외부 의존 없음 — domain 규칙 준수).

### 5.3 `domain/chunking_profile/interfaces.py`

```python
class ChunkingProfileRepositoryInterface(ABC):
    async def save(self, profile: ChunkingProfile, request_id: str) -> ChunkingProfile: ...
    async def find_by_id(self, profile_id: str, request_id: str) -> ChunkingProfile | None: ...  # status 무관 조회(폴백 판정용)
    async def find_all_active(self, request_id: str) -> list[ChunkingProfile]: ...
    async def find_default(self, request_id: str) -> ChunkingProfile | None: ...                 # is_default=1 AND active
    async def exists_active_name(self, name: str, exclude_id: str | None, request_id: str) -> bool: ...
    async def update(self, profile: ChunkingProfile, request_id: str) -> ChunkingProfile: ...
    async def clear_default(self, request_id: str) -> None: ...                                  # 전체 is_default=0
    async def soft_delete(self, profile_id: str, request_id: str) -> None: ...
```

### 5.4 `domain/knowledge_base/entities.py` — additive 필드 4개

```python
    # clause-aware-chunking (D5): opt-in + late-binding 오버라이드
    use_clause_chunking: bool = False
    chunking_profile_id: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
```

기본값이 있는 필드 추가이므로 기존 생성부 무영향(additive).

---

## 6. ClauseAwareStrategy (infrastructure/chunking)

### 6.1 생성 파라미터 (factory 경유, DB 무접근)

```python
ChunkingStrategyFactory.create_strategy(
    "clause_aware",
    parent_patterns=[...],   # 문자열 목록 (priority 정렬 완료 상태로 전달)
    child_patterns=[...],
    parent_chunk_size=2000,
    chunk_size=500,
    chunk_overlap=50,
)
```

factory가 `re.compile(p, re.MULTILINE)`로 컴파일해 전략에 주입. 기본 상수는 factory 클래스 상수(`DEFAULT_CLAUSE_*`)로 정의(하드코딩 금지 규칙 준수).

### 6.2 알고리즘 (①→②→③)

```
chunk(documents):
    1. 페이지 결합 (D8): full_text = "\n\n".join(page contents),
       각 페이지의 [start_offset, end_offset) → page 번호 매핑 테이블 기록.
       base_metadata = documents[0].metadata (chunk 관련 키 제외)
    2. ① parent 분할: parent_patterns를 순서대로 시도 — 첫 번째로 매치가 존재하는
       패턴의 매치 시작점들로 full_text를 분할.
       - 첫 매치 이전 텍스트(전문·목차)는 선행 세그먼트로 유지 (clause_title="(전문)")
       - 매치 전무 → fallback: 전체 텍스트 1세그먼트 (boundary="fallback")
       각 세그먼트의 clause_title = 매치 라인(최대 100자), page_start/page_end = offset→페이지 매핑
    3. parent 상한 처리: 세그먼트가 parent_chunk_size 초과 시
       BaseTokenChunker(parent_config, overlap=0)로 분할 — 분할된 parent들은
       동일 clause_title 공유 (기존 parent_child의 'parents don't overlap' 선례)
    4. ② child 분할: 각 parent 텍스트를 child_patterns(전체 순차 적용)의 매치 시작점으로
       세그먼트화 → 세그먼트들을 순서대로 chunk_size 이내 그리디 병합 (D16)
       → 병합 후에도 chunk_size 초과 세그먼트만 ③ split_by_tokens(child_config)로
         토큰 분할 + chunk_overlap 적용 (boundary="token", 그 외 "clause")
       child가 하나도 안 나오면 parent 전문을 child 1개로 (parent_child와 동일하게
       parent/child 쌍 항상 존재 — 검색 계약 유지)
    5. 메타데이터 부여 (D9): parent/child 계약 필드 + clause_title/page_start/page_end/boundary.
       마지막에 전체 child의 chunk_index/total_chunks 재부여 (parent_child 104-108행과 동일)
    get_strategy_name() → "clause_aware" / get_chunk_size() → child chunk_size
```

구현은 단계별 private 메서드로 분리(함수 40줄 제한): `_join_pages`, `_split_parents`, `_split_children`, `_greedy_merge`, `_locate_pages`.

### 6.3 factory 등록 (additive)

`StrategyType.CLAUSE_AWARE = "clause_aware"` + `_create_clause_aware_strategy(**kwargs)` 추가. 기존 전략 코드 무수정.

---

## 7. Application Layer

### 7.1 `ChunkingProfileUseCase` (application/chunking_profile/use_case.py)

의존성: `profile_repo`, `policy`, `logger`. 예외 규약은 collection_router와 동일(ValueError/PermissionError 매핑).

| 메서드 | 흐름 |
|--------|------|
| `create(req, request_id)` | validate_name → validate_rules → validate_sizes → active 이름 중복 검사 → save(id=uuid4). `is_default=True` 요청이면 `clear_default` 후 저장(단일 세션, D3) |
| `list_active(request_id)` | `find_all_active` — 사용자 조회 API와 관리자 목록이 공유 |
| `get(profile_id, request_id)` | find_by_id → 없거나 deleted면 ValueError("not found") |
| `update(profile_id, req, request_id)` | 존재 확인 → 동일 검증 → 이름 중복(exclude self) → update. is_default=True면 clear_default 선행 |
| `set_default(profile_id, request_id)` | 존재·active 확인 → clear_default → is_default=1 update |
| `delete(profile_id, request_id)` | 존재 확인 → `policy.can_delete`(default 거부) → soft_delete. **KB 참조는 차단하지 않음** — 업로드 시 default 폴백 (D11) |

### 7.2 `ChunkingSettingsResolver` (application/knowledge_base/chunking_resolver.py, D11)

```
resolve(kb, request_id) -> UploadChunkingConfig | None:
    if not kb.use_clause_chunking: return None
    profile = (find_by_id(kb.chunking_profile_id) if kb.chunking_profile_id else None)
    if profile is None or profile.status != "active":
        if kb.chunking_profile_id:
            logger.warning("chunking profile missing/deleted, falling back to default", ...)
        profile = await profile_repo.find_default(request_id)
    if profile is None:
        logger.warning("no default chunking profile, using legacy path", ...)
        return None                          # 업로드는 항상 성공 (FR-07)
    chunk_size = kb.chunk_size or profile.chunk_size
    chunk_overlap = kb.chunk_overlap if kb.chunk_overlap is not None else profile.chunk_overlap
    return UploadChunkingConfig(
        strategy="clause_aware",
        params={parent_patterns, child_patterns, parent_chunk_size: profile.parent_chunk_size,
                chunk_size, chunk_overlap},
        display={strategy: "clause_aware", profile_id: profile.id, profile_name: profile.name,
                 parent_chunk_size, chunk_size, chunk_overlap},
    )
```

주의: `chunk_overlap=0` 오버라이드가 유효하도록 `is not None` 판정(or 금지).

### 7.3 `KnowledgeBaseUseCase.create` additive 수정

- 요청에 청킹 필드(`use_clause_chunking`, `chunking_profile_id`, `chunk_size`, `chunk_overlap`) 수용
- `use_clause_chunking=True`일 때: `ChunkingProfilePolicy.validate_kb_override(size, overlap)` + `chunking_profile_id` 지정 시 존재·active 검증(profile_repo 의존성 추가)
- `use_clause_chunking=False`인데 청킹 필드가 오면 ValueError(422) — 무의미한 설정 저장 방지

### 7.4 `KnowledgeBaseUploadUseCase` additive 수정

```python
# __init__에 resolver 추가
chunking_config = await self._chunking_resolver.resolve(kb, request_id)
if chunking_config is not None and (child_chunk_size != 500 or child_chunk_overlap != 50):
    self._logger.warning("query chunk params ignored (KB clause chunking active)", ...)  # D6
unified_req = UnifiedUploadRequest(..., chunking_config=chunking_config)
```

### 7.5 `UnifiedUploadUseCase` additive 수정 (3곳, D10)

```python
# schemas.py
@dataclass(frozen=True)
class UploadChunkingConfig:
    strategy: str
    params: dict            # ChunkingStrategyFactory kwargs
    display: dict           # document_metadata/응답 기록용

# UnifiedUploadRequest 마지막 필드
chunking_config: UploadChunkingConfig | None = None

# use_case.py execute() — 전략 생성부(89-94행) 분기
if request.chunking_config is not None:
    strategy = ChunkingStrategyFactory.create_strategy(
        request.chunking_config.strategy, **request.chunking_config.params)
    strategy_name = request.chunking_config.strategy
    chunking_config_dict = request.chunking_config.display
else:
    strategy = <기존 그대로>; strategy_name = "parent_child"
    chunking_config_dict = <기존 dict 그대로>

# 146행: chunk_strategy=strategy_name / 189-194행: chunking_config=chunking_config_dict
```

`chunking_config=None`(기본값)이면 세 값 모두 기존과 동일 — 회귀 없음.

---

## 8. API 명세

### 8.1 `/api/v1/admin/chunking/profiles` (신규, tags=["Admin"], 전부 `require_role("admin")`)

| Method | Path | Request | Response | 에러 |
|--------|------|---------|----------|------|
| POST | `/` | `{name, description?, boundary_rules: [{pattern, priority, level}], parent_chunk_size?, chunk_size?, chunk_overlap?, is_default?}` | 201 `ProfileResponse` | 409 이름 중복 / 422 검증 실패 |
| GET | `/` | - | `{profiles: [ProfileResponse], total}` (active만) | - |
| GET | `/{id}` | - | `ProfileResponse` | 404 |
| PUT | `/{id}` | POST와 동일 body | `ProfileResponse` | 404 / 409 / 422 |
| PUT | `/{id}/default` | - | `{profile_id, message}` | 404 / 422(deleted) |
| DELETE | `/{id}` | - | `{profile_id, message}` | 404 / 422(default 삭제 불가) |

`ProfileResponse`: `{profile_id, name, description, boundary_rules, parent_chunk_size, chunk_size, chunk_overlap, is_default, created_at, updated_at}`

일반 사용자 호출 시 403 (`require_role` 가드 — admin_collection_router 선례).

### 8.2 `GET /api/v1/chunking/profiles` (신규, tags=["Chunking"], `get_current_user`, D14)

active 프로파일 목록 + `is_default` — KB 생성 폼/에이전트 빌더 프리필용. 응답 스키마는 8.1 `ProfileResponse` 재사용.

### 8.3 `/api/v1/knowledge-bases` (additive 수정)

- `CreateKnowledgeBaseBody`에 optional 추가: `use_clause_chunking: bool = False`, `chunking_profile_id: str | None`, `chunk_size: int | None`, `chunk_overlap: int | None`
- `KbInfoResponse`/`KbCreateResponse`에 동일 필드 노출 (프론트 `/api-contract-sync`는 후속 PDCA에서 일괄)
- `POST /{kb_id}/documents`: 시그니처 무변경. `use_clause_chunking` KB면 Query 파라미터 무시(D6) — docstring/OpenAPI description에 명시. `KbUploadResponse`에 `chunking_strategy: str` 추가(적용 전략 확인용, FR-10)

---

## 9. DI 배선 (main.py — 추가만)

기존 `create_knowledge_base_factories` 패턴을 따른다.

```
def create_chunking_profile_factories():
    def profile_use_case_factory(session = Depends(get_session)):
        repo = ChunkingProfileRepository(session, app_logger)
        return ChunkingProfileUseCase(repo, ChunkingProfilePolicy(), app_logger)
    return profile_use_case_factory

# 기존 kb factory 수정(추가만):
#  - kb_use_case_factory: ChunkingProfileRepository 추가 주입 (§7.3 검증용)
#  - kb_upload_factory: ChunkingSettingsResolver(profile_repo, app_logger) 추가 주입
# 세션 규칙: 동일 요청의 모든 repository는 같은 Depends(get_session) 세션 사용
```

라우터 등록: `admin_chunking_router`, `chunking_profile_router` include + DI override 2건 추가.

---

## 10. 테스트 설계 (TDD — Red 먼저)

| 파일 | 케이스 |
|------|--------|
| `test_policy.py` | 규칙: 잘못된 정규식/201자 패턴/51개/level 오타/parent 규칙 0개 거부, 정상 통과. 사이즈: overlap ≥ size, child > parent, 범위 초과 거부. KB 오버라이드: overlap만 지정 거부(D7), 정상 조합 통과. can_delete: default 거부 |
| `test_use_case.py` (profile) | create: 정상(UUID 발급)/이름 중복 409 경로/is_default=True 시 clear_default 호출. update: not found/이름 중복(self 제외). set_default: clear→set 순서 검증. delete: default 422 경로, soft_delete 호출. list_active |
| `test_clause_aware_strategy.py` | **경계 보존**: "제1조…제2조…" 텍스트 → 조별 parent, 조 시작이 청크 중간에 없음. **페이지 결합**: 조가 2페이지에 걸침 → parent 1개 + page_start/page_end 정확. **전문 처리**: 첫 조 이전 텍스트 → 선행 parent. **② 초과 시에만 분할**: 작은 조 → 토큰 분할 없음(boundary="clause"), 큰 항 → split_by_tokens + ③ overlap 검증(인접 child 접미/접두 중첩). **그리디 병합**(D16): 짧은 항 여러 개 → 한 child. **fallback**: 매치 전무 → 전체 1 parent + child들, 업로드 성공. **계약**(D9): parent_child와 동일 필드 존재, child index 전체 재부여, parent/child 쌍 항상 존재 |
| `test_chunking_resolver.py` | use_clause=False → None. 프로파일 지정 → 해당 프로파일. 미지정 → default. deleted 참조 → default 폴백 + warning. default도 없음 → None(legacy). 오버라이드 병합: size만/overlap=0(`is not None` 판정) |
| `test_upload_chunking.py` (KB upload) | resolver 결과가 UnifiedUploadRequest.chunking_config로 전달. Query 파라미터 무시 + warning(D6) |
| `test_chunking_config.py` (unified) | chunking_config 지정 시: factory에 strategy/params 전달, metadata `chunk_strategy`·응답 `chunking_config`=display. **미지정 시 기존 동작 완전 불변**(전략명 parent_child, 기존 dict — 회귀 가드) |
| `test_admin_chunking_router.py` | 일반 사용자 403 / 관리자 CRUD 상태코드(201/409/404/422) / default 지정·삭제 거부 |
| `test_chunking_profile_router.py` | 인증 사용자 목록 조회, is_default 포함 |
| `test_knowledge_base_router.py` (추가) | 청킹 필드 포함 KB 생성 201 + 응답 노출 / use_clause=False + 청킹 필드 → 422 / overlap만 지정 422 |
| KB use_case 기존 테스트 | additive 필드 기본값으로 기존 케이스 무수정 통과 확인 |

기존 테스트 스위트: 신규 회귀 0건 (사전 실패분 [[preexisting-api-test-failures-auth-di]] 오인 금지).

---

## 11. 구현 순서 (Do Phase)

1. `V041`/`V042` 마이그레이션 + SQLAlchemy 모델 2건(chunking_profile 신규, knowledge_base additive)
2. domain: `chunking_profile` entities → policy(테스트 먼저) → interfaces + KB entity additive 필드
3. infrastructure: `ChunkingProfileRepository`(테스트 먼저) + KB repository 매핑 additive
4. `ClauseAwareStrategy`(테스트 먼저 — 경계/페이지/overlap/계약/fallback) + factory 등록
5. application: `ChunkingProfileUseCase` → `ChunkingSettingsResolver` → `UnifiedUploadUseCase` additive(`test_chunking_config.py` 먼저) → KB create/upload additive
6. api: admin_chunking_router → chunking_profile_router → knowledge_base_router additive
7. main.py DI 배선 + 라우터 등록
8. `/verify-architecture`, `/verify-tdd`, `/verify-logging` 실행
9. 시드 프로파일 패턴을 실제 규정 PDF 샘플로 수동 검증(Do 체크리스트)

---

## 12. 리스크 재확인 (Plan §5 대비 갱신)

| Plan 리스크 | Design 확정 결과 |
|-------------|------------------|
| 관리자 정규식 오류·ReDoS | 컴파일 검증 + 패턴 200자/50개 상한 (D12). 매치는 `re.MULTILINE` finditer — 대상 텍스트 유한 |
| 조 하나가 parent 상한 초과 | 토큰 분할로 복수 parent, clause_title 공유 (§6.2-3) |
| 경계 패턴 없는 문서 | 전략 내 fallback(전체 1 parent) + resolver의 default 부재 시 legacy 폴백 — 업로드 실패 경로 없음 |
| 프로파일 수정/삭제와 기존 청크 불일치 | soft delete + 업로드 시 default 폴백(D11), 적용 내역을 chunk_strategy/응답에 기록(FR-10) |
| parent/child 계약 불일치 | 계약 필드 동일성 테스트 + child index 재부여 로직 동일 구현 (§10) |
| 표 포함 문서 | clause_aware는 table_flattening 미적용(D13) — 표 중심 문서는 기존 경로 사용, 후속 최적화 |
| **신규 발견**: 조가 페이지 경계를 넘음 | 페이지 결합 + offset→페이지 매핑으로 해소 (D8), page_start/page_end 메타 제공 |
