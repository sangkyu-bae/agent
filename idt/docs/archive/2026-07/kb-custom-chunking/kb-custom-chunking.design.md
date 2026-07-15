# kb-custom-chunking Design Document

> **Summary**: KB 단위 커스텀 청킹(전략·사이즈·오버랩·경계 정규식) 설정 — 독립 opt-in 필드 + resolver 분기 + 설정 수정 API 신설
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Author**: 배상규
> **Date**: 2026-07-14
> **Status**: Draft
> **Planning Doc**: [kb-custom-chunking.plan.md](../../01-plan/features/kb-custom-chunking.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. 사용자가 KB 생성/수정 시 청킹 전략 5종과 파라미터, 경계 정규식을 직접 지정
2. 기존 경로(legacy parent_child, 조항 clause_aware) **바이트 단위 무변경** — 독립 opt-in 분기만 추가
3. 신규 청킹 엔진 없이 기존 `ChunkingStrategyFactory` kwargs 통로만 개방
4. 검증은 domain, 해석은 application resolver, 전략 생성은 infrastructure factory — 기존 레이어 배치 관례 유지

### 1.2 Design Principles

- **독립 opt-in**: `use_custom_chunking` + `custom_chunking_config`(JSON) 신설. 기존 조항 필드 4개(`use_clause_chunking`/`chunking_profile_id`/`chunk_size`/`chunk_overlap`)의 의미 불변
- **재사용 우선**: 경계 패턴 검증은 `ChunkingProfilePolicy`의 상한/컴파일 검증 재사용, 경계 패턴 실행은 `clause_aware` 전략 기계 재사용
- **폴백 안전**: 해석 실패 시 legacy 경로 폴백 + warning — 업로드는 항상 성공 (clause 경로 FR-07 관례)

---

## 2. Design Decisions (D1–D12)

| # | 결정 | 근거 |
|---|------|------|
| D1 | KB에 `use_custom_chunking` TINYINT(1) + `custom_chunking_config` JSON 컬럼 신설 | 사용자 결정(독립 opt-in). 전략별 파라미터 가변성(경계 규칙 리스트) 때문에 개별 컬럼 대신 JSON 1개 |
| D2 | config JSON에 `version: 1` 키 포함 | 스키마 드리프트 대비 (Plan Risk) |
| D3 | 사용자 노출 전략명: `parent_child` \| `full_token` \| `semantic` \| `section_aware` \| `boundary_pattern`. `boundary_pattern`은 factory 호출 시 `clause_aware`로 매핑 | "조항"이라는 도메인 용어와 분리된 일반 명칭 제공, 신규 전략 구현 없음 |
| D4 | `use_clause_chunking`과 `use_custom_chunking` 동시 true 금지 — create/update 모두 422 | 두 해석 경로 충돌 방지 (Plan FR-05) |
| D5 | 검증 policy는 `domain/knowledge_base/custom_chunking.py`에 신설, 수치 상한은 `ChunkingProfilePolicy` 상수 재사용 | 전략별 필수/허용 파라미터가 달라 프로파일 policy와 별개 로직 필요. domain→domain import는 허용 |
| D6 | resolver 분기 순서: custom → clause → None(legacy). custom config 파싱/검증 실패 시 **legacy 폴백 + warning** | D4로 동시 활성 불가라 순서 무해. 업로드 항상 성공 원칙 |
| D7 | 청킹 설정 수정은 신규 `PATCH /api/v1/knowledge-bases/{kb_id}/chunking` 전용 엔드포인트 | 현재 KB update 경로 자체가 없음(create/list/get/delete뿐). 이름/scope 수정과 분리해 이번 범위를 청킹으로 한정 |
| D8 | repo에 `update_chunking()` 신설 — 청킹 6개 컬럼 화이트리스트만 UPDATE | 컬럼 화이트리스트 관례(스키마→use_case→repo→DI 4곳 세트 누락 주의) |
| D9 | 수정 권한: owner 또는 ADMIN — `KnowledgeBasePolicy.can_manage_settings()` 신설(can_delete와 동일 규칙) | 부서 쓰기 권한자는 업로드는 가능하되 KB 구조 설정 변경은 소유자 책임 |
| D10 | 설정 변경은 신규 업로드부터 적용, 재인덱싱 없음. 문서별 실제 사용 설정은 기존 `chunking_config` display 기록으로 추적 | 사용자 결정. `UnifiedUploadResult.chunking_config` 이미 존재 |
| D11 | boundary_rules는 parent 레벨 ≥ 1 필수, child 선택, 전체 ≤ 50개, 패턴 ≤ 200자 | `ChunkingProfilePolicy` 기존 상한 그대로 재사용 (ReDoS 완화 포함) |
| D12 | `semantic` 전략은 overlap 미지원(factory가 overlap=0 고정) — config에 overlap 지정 시 422 | factory 실제 동작과 UI 계약 일치. 무시(silent drop)보다 명시 거부 |

---

## 3. Architecture

### 3.1 Data Flow (업로드 시)

```
KB 업로드 요청
  └─ KnowledgeBaseUploadUseCase
       └─ ChunkingSettingsResolver.resolve(kb)
            ├─ kb.use_custom_chunking=True
            │    ├─ CustomChunkingConfig.parse(kb.custom_chunking_config)  ← 신규
            │    │    ├─ 성공 → UploadChunkingConfig(strategy, params, display)
            │    │    └─ 실패 → warning 로그 → None (legacy 폴백)      [D6]
            ├─ kb.use_clause_chunking=True → (기존 프로파일 경로, 무변경)
            └─ 둘 다 False → None
       └─ UnifiedUploadUseCase._build_strategy()
            ├─ chunking_config 있음 → ChunkingStrategyFactory.create_strategy(...)  (기존)
            └─ None → parent_child 하드코딩 (기존, 무변경)
```

### 3.2 전략별 factory 파라미터 매핑

| config.strategy | factory strategy | 전달 params | 필수 | 금지 |
|-----------------|------------------|-------------|------|------|
| `full_token` | `full_token` | `chunk_size`, `chunk_overlap` | chunk_size | parent_chunk_size, min_chunk_size, boundary_rules |
| `parent_child` | `parent_child` | `parent_chunk_size`, `child_chunk_size`(=chunk_size), `child_chunk_overlap`(=chunk_overlap) | chunk_size | min_chunk_size, boundary_rules |
| `semantic` | `semantic` | `chunk_size`, `min_chunk_size` | chunk_size | chunk_overlap(>0), parent_chunk_size, boundary_rules [D12] |
| `section_aware` | `section_aware` | `chunk_size`, `chunk_overlap`, `min_chunk_size` | chunk_size | parent_chunk_size, boundary_rules |
| `boundary_pattern` | `clause_aware` | `parent_patterns`, `child_patterns`, `parent_chunk_size`, `chunk_size`, `chunk_overlap` | chunk_size, boundary_rules(parent≥1) | min_chunk_size |

미지정 optional 값은 factory 기본값 사용(예: parent_chunk_size 2000, min_chunk_size 전략별 기본).

### 3.3 Dependencies (신규/변경 컴포넌트)

| Component | Depends On | 변경 유형 |
|-----------|-----------|----------|
| `domain/knowledge_base/custom_chunking.py` | `chunking_profile.entities.BoundaryRule`, `ChunkingProfilePolicy`(상수/검증 재사용) | **신규** |
| `domain/knowledge_base/entities.py` | — | 필드 2개 추가 |
| `domain/knowledge_base/policy.py` | — | `can_manage_settings()` 추가 [D9] |
| `application/knowledge_base/chunking_resolver.py` | custom_chunking | custom 분기 추가 [D6] |
| `application/knowledge_base/use_case.py` | custom_chunking policy | create 검증 확장 + `update_chunking()` 신설 [D7] |
| `infrastructure/persistence/models/knowledge_base.py` | — | 컬럼 2개 추가 |
| `infrastructure/knowledge_base/repository.py` | — | save/_to_domain 매핑 + `update_chunking()` [D8] |
| `api/routes/knowledge_base_router.py` | — | 스키마 확장 + PATCH 엔드포인트 + DI |
| `db/migration/V048__alter_knowledge_base_add_custom_chunking.sql` | — | **신규** |

---

## 4. Data Model

### 4.1 CustomChunkingConfig (domain, pydantic)

```python
# src/domain/knowledge_base/custom_chunking.py
STRATEGY_FULL_TOKEN = "full_token"
STRATEGY_PARENT_CHILD = "parent_child"
STRATEGY_SEMANTIC = "semantic"
STRATEGY_SECTION_AWARE = "section_aware"
STRATEGY_BOUNDARY_PATTERN = "boundary_pattern"

class CustomBoundaryRule(BaseModel):
    pattern: str          # 정규식, ≤200자, re.compile 검증
    priority: int         # 낮을수록 우선
    level: Literal["parent", "child"]

class CustomChunkingConfig(BaseModel):
    version: Literal[1] = 1
    strategy: Literal["full_token", "parent_child", "semantic",
                      "section_aware", "boundary_pattern"]
    chunk_size: int                        # 100~4000 (필수)
    chunk_overlap: int = 0                 # 0~500, < chunk_size
    parent_chunk_size: int | None = None   # 100~8000 (parent 계열만)
    min_chunk_size: int | None = None      # 50~2000, < chunk_size (semantic/section_aware만)
    boundary_rules: list[CustomBoundaryRule] = []  # boundary_pattern 전용
```

### 4.2 검증 규칙 (CustomChunkingPolicy)

| 규칙 | 내용 | 에러 |
|------|------|------|
| V-01 | 수치 범위: `ChunkingProfilePolicy` 상수 재사용 (CHILD 100~4000, OVERLAP 0~500, PARENT 100~8000) + `min_chunk_size` 50~2000 | 422, 필드명+허용범위 |
| V-02 | `chunk_overlap < chunk_size`, `chunk_size ≤ parent_chunk_size`(지정 시), `min_chunk_size < chunk_size` | 422 |
| V-03 | 전략별 금지 파라미터 지정 시 거부 (§3.2 금지 열, semantic+overlap>0 포함 [D12]) | 422, `"'semantic' does not support chunk_overlap"` 형식 |
| V-04 | `boundary_pattern`: rules 1~50개, parent 레벨 ≥1, 패턴 비어있지 않고 ≤200자, `re.compile` 성공 | 422, **실패한 패턴 원문 + re.error 메시지 포함** |
| V-05 | `boundary_pattern` 외 전략에서 boundary_rules 지정 시 거부 | 422 |
| V-06 | `use_custom_chunking=True`인데 config None → 거부 / `False`인데 config 지정 → 거부 | 422 |
| V-07 | `use_clause_chunking`과 `use_custom_chunking` 동시 True 거부 [D4] | 422 |

### 4.3 Database Schema (V048)

```sql
-- kb-custom-chunking Design D1 (additive):
-- use_custom_chunking = 독립 opt-in 스위치. 조항 청킹(use_clause_chunking)과 상호배타(앱 검증).
-- custom_chunking_config = 전략/파라미터/경계규칙 JSON (version 키 포함, Design §4.1).
-- FK 없음 — 콜레이션 이슈 해당 없음.
ALTER TABLE knowledge_base
    ADD COLUMN use_custom_chunking TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN custom_chunking_config JSON NULL;
```

SQLAlchemy: `use_custom_chunking: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)` (기존 use_clause_chunking과 동일 스타일), `custom_chunking_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)`.

도메인 엔티티(`KnowledgeBase`)에는 `use_custom_chunking: bool = False`, `custom_chunking_config: dict | None = None`로 보관(파싱은 resolver/policy에서 수행 — 엔티티는 저장 형식 그대로).

---

## 5. API Specification

### 5.1 Endpoint 변경 요약

| Method | Path | 변경 | Auth |
|--------|------|------|------|
| POST | `/api/v1/knowledge-bases` | Body에 `use_custom_chunking`, `custom_chunking_config` 추가 | 기존 |
| GET | `/api/v1/knowledge-bases` / `/{kb_id}` | 응답에 두 필드 추가 | 기존 |
| **PATCH** | **`/api/v1/knowledge-bases/{kb_id}/chunking`** | **신설** — 청킹 설정만 수정 [D7] | owner/ADMIN [D9] |

### 5.2 PATCH /api/v1/knowledge-bases/{kb_id}/chunking

**Request** (전체 교체 시맨틱 — 부분 병합 아님, 프론트가 현재값 프리필 후 전송):
```json
{
  "use_clause_chunking": false,
  "chunking_profile_id": null,
  "chunk_size": null,
  "chunk_overlap": null,
  "use_custom_chunking": true,
  "custom_chunking_config": {
    "version": 1,
    "strategy": "boundary_pattern",
    "chunk_size": 600,
    "chunk_overlap": 80,
    "parent_chunk_size": 3000,
    "boundary_rules": [
      {"pattern": "^제\\d+장", "priority": 1, "level": "parent"},
      {"pattern": "^\\d+\\.\\s", "priority": 1, "level": "child"}
    ]
  }
}
```

**Response (200)**: `KbInfoResponse` (변경 후 전체 KB 정보)

**검증**: create와 동일한 `_validate_chunking`(조항 계열) + `CustomChunkingPolicy`(커스텀 계열) + V-07 상호배타. 기존 조항 검증 로직은 create/update가 공유.

**Error**:
- `403` 권한 없음 (owner/ADMIN 아님)
- `404` KB 없음
- `422` 검증 실패 — detail에 실패 규칙 명시 (V-01~V-07)

### 5.3 청킹 설정 해석 결과 기록 (display)

resolver가 custom 경로에서 생성하는 `UploadChunkingConfig.display`:
```json
{
  "strategy": "boundary_pattern", "custom": true,
  "chunk_size": 600, "chunk_overlap": 80, "parent_chunk_size": 3000,
  "boundary_rule_count": 2
}
```
(`params`에는 §3.2 매핑 결과를 담아 factory에 위임. display의 `strategy`는 사용자 노출명 유지, factory 호출은 `clause_aware`)

---

## 6. UI/UX Design (idt_front)

### 6.1 KB 생성 모달 — 고급 옵션 확장

```
┌─ 고급 옵션 ──────────────────────────────────┐
│ ○ 기본 청킹 (parent_child 2000/500/50)        │  ← radio 3택 (기존 토글 2개를
│ ○ 조항 기반 청킹 (프로파일 사용)               │     radio로 통합 표현 — 상호배타
│ ● 커스텀 청킹                                 │     UX, API 값으로 변환)
│   ┌─────────────────────────────────────┐   │
│   │ 전략   [boundary_pattern ▼] (툴팁)   │   │
│   │ 청크 크기   [600 ]  오버랩 [80 ]      │   │
│   │ 부모 청크 크기 [3000]  (parent 계열만) │   │
│   │ 최소 청크 크기 [   ]  (semantic 등만)  │   │
│   │ ── 경계 규칙 (boundary_pattern만) ──  │   │
│   │ [parent] [^제\d+장     ] [우선순위 1] ✕│   │
│   │ [child ] [^\d+\.\s     ] [우선순위 1] ✕│   │
│   │ [+ 규칙 추가]                         │   │
│   └─────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
```

- radio 선택에 따라 `use_clause_chunking`/`use_custom_chunking` 값 결정 (동시 true 원천 차단)
- 전략 변경 시 해당 전략에서 금지된 필드는 숨김+값 초기화 (§3.2 금지 열과 일치)
- 정규식 입력은 blur 시 `new RegExp()` try-catch로 1차 클라이언트 검증(참고용), 최종 검증은 서버(Python `re`)
- 전략별 설명 툴팁: 비용/특성 안내 (semantic = 문장 임베딩 유사도 기반 등)

### 6.2 KB 상세 페이지 — 청킹 설정 카드

- 현재 설정 요약 표시 (전략/파라미터/규칙 수)
- [설정 변경] 버튼 → §6.1과 동일한 폼의 수정 모달 (현재값 프리필) → PATCH 호출
- 저장 시 안내 문구 고정 노출: **"변경된 설정은 이후 업로드하는 문서부터 적용되며, 기존 문서는 다시 청킹되지 않습니다."** [D10]

### 6.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `ChunkingModeSelector` (신규) | `components/knowledge-base/` | radio 3택 + 하위 폼 스위칭 |
| `CustomChunkingFields` (신규) | `components/knowledge-base/` | 전략 select + 파라미터 입력 + 경계 규칙 편집 리스트, 로컬 검증 |
| `CreateKnowledgeBaseModal` (수정) | 〃 | 고급 옵션을 ChunkingModeSelector로 교체, 요청 조립 |
| `KbChunkingSettingsCard` (신규) | 〃 | 상세 페이지 설정 요약 + 수정 모달 |
| `KnowledgeBaseDetailPage` (수정) | `pages/` | 설정 카드 배치 |

### 6.4 프론트 계약 파일 (api-contract-sync)

| 파일 | 변경 |
|------|------|
| `types/knowledgeBase.ts` | `ChunkingStrategy`, `CustomBoundaryRule`, `CustomChunkingConfig`, `UpdateKbChunkingRequest` 추가, `CreateKnowledgeBaseRequest`에 두 필드 추가, `KbInfoResponse` 대응 타입 확장 |
| `services/knowledgeBaseService.ts` | `updateKbChunking(kbId, body)` 추가 |
| `hooks/useKnowledgeBases.ts` | `useUpdateKbChunking` mutation + `queryKeys` invalidate |
| `constants/api.ts` | `KB_CHUNKING: (kbId) => \`/api/v1/knowledge-bases/${kbId}/chunking\`` |

---

## 7. Error Handling

| Code | 상황 | 처리 |
|------|------|------|
| 422 | V-01~V-07 검증 실패 (create/PATCH) | detail에 실패 필드·규칙·(정규식이면) 패턴 원문 포함. 프론트는 해당 입력 필드에 인라인 표시 |
| 403 | PATCH 권한 없음 | "지식베이스 소유자만 설정을 변경할 수 있습니다" |
| 404 | KB 없음/삭제됨 | 기존 관례 |
| (업로드 시) | 저장된 config 파싱 실패 (스키마 드리프트 등) | 업로드 실패 대신 legacy 폴백 + `logger.warning("Custom chunking config invalid, falling back to legacy path", kb_id=...)` [D6] |

로깅: LOG-001 준수 — resolver 폴백/설정 변경 시 request_id, kb_id 포함 warning/info. print() 금지.

---

## 8. Test Plan (TDD — 테스트 선행)

### 8.1 백엔드 (pytest)

| 파일 | 케이스 |
|------|--------|
| `tests/domain/knowledge_base/test_custom_chunking_policy.py` (신규) | V-01~V-07 각 규칙의 성공/실패, 전략별 금지 파라미터 매트릭스, 잘못된 정규식 에러 메시지에 패턴 포함 |
| `tests/application/knowledge_base/test_chunking_resolver.py` (확장) | custom 경로 → UploadChunkingConfig 매핑(전략 5종), boundary_pattern→clause_aware 매핑, config 손상 시 legacy 폴백+warning, 기존 clause 경로 회귀 무변경 |
| `tests/application/knowledge_base/test_use_case.py` (확장) | create: 커스텀 검증 호출·상호배타 거부, `update_chunking`: 권한(owner/ADMIN/타인), 전체 교체 시맨틱, 검증 실패 |
| `tests/api/test_knowledge_base_router.py` (확장) | POST 두 필드 왕복, PATCH 200/403/404/422, 응답 스키마 |
| `tests/infrastructure/knowledge_base/test_repository.py` (확장) | save/조회 JSON 왕복, `update_chunking` 화이트리스트 컬럼만 변경 |

주의: Windows 이벤트 루프 teardown 산발 실패 — 신규 테스트는 격리 실행으로도 검증. 기존 사전 실패(tests/api 28건 등)와 신규 회귀 구분.

### 8.2 프론트엔드 (Vitest + RTL + MSW, `--pool=threads`)

| 파일 | 케이스 |
|------|--------|
| `CustomChunkingFields.test.tsx` (신규) | 전략 전환 시 필드 표시/숨김, 규칙 추가/삭제, 잘못된 정규식 인라인 에러, 값 범위 검증 |
| `CreateKnowledgeBaseModal.test.tsx` (확장) | radio 상호배타(커스텀 선택 시 조항 필드 미전송), 요청 body 조립 |
| `KbChunkingSettingsCard.test.tsx` (신규) | 현재값 프리필, PATCH 호출, "기존 문서 미적용" 안내 노출 |

MSW per-file listen 3종 훅 필수. 폼 검증 테스트는 noValidate 유의(jsdom constraint validation).

### 8.3 수동 검증 (E2E)

- [ ] 커스텀 KB(boundary_pattern) 생성 → 문서 업로드 → kb-content-browser로 청크 경계·크기 확인
- [ ] 양쪽 OFF KB 업로드 결과가 기존과 동일 (회귀)
- [ ] 설정 변경 후 기존 문서 청크 불변, 신규 업로드만 새 설정

---

## 9. Clean Architecture — Layer Assignment

| Component | Layer | 규칙 준수 |
|-----------|-------|----------|
| `CustomChunkingConfig` + `CustomChunkingPolicy` | domain | 표준 `re`/pydantic만 사용, 외부 의존 없음 |
| `ChunkingSettingsResolver` 확장 | application | 흐름 제어만, 규칙은 policy 위임 |
| repository `update_chunking` | infrastructure | commit/rollback 없음 (세션 규칙), flush만 |
| router PATCH + 스키마 | interfaces | 비즈니스 로직 없음, use_case 위임 |

`/verify-architecture`, `/verify-tdd`, `/verify-logging` 구현 후 실행.

---

## 10. Implementation Order

1. [ ] **V048 마이그레이션** + persistence model 컬럼 2개
2. [ ] **domain**: `custom_chunking.py` (config + policy) — 테스트 먼저
3. [ ] **infrastructure**: repository save/_to_domain 매핑 + `update_chunking()` — 테스트 먼저
4. [ ] **application**: use_case create 검증 확장 + `update_chunking()` 신설 + policy `can_manage_settings()` — 테스트 먼저
5. [ ] **application**: resolver custom 분기 — 테스트 먼저
6. [ ] **interfaces**: router 스키마 확장 + PATCH 엔드포인트 + DI 배선
7. [ ] **frontend 계약**: types/constants/service/hooks (api-contract-sync)
8. [ ] **frontend UI**: CustomChunkingFields → ChunkingModeSelector → 모달/카드 통합 — 테스트 먼저
9. [ ] 백엔드 전체 테스트 + 프론트 테스트 + 수동 E2E 체크리스트

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-14 | 최초 작성 — D1~D12 결정, V-01~V-07 검증 규칙, PATCH 신설 설계 | 배상규 |
