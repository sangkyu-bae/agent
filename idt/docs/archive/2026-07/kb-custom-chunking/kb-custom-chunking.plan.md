# kb-custom-chunking Planning Document

> **Summary**: KB(지식베이스) 단위로 사용자가 청킹 전략·사이즈·오버랩·경계 패턴(정규식)을 직접 설정할 수 있는 커스텀 청킹 기능
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Author**: 배상규
> **Date**: 2026-07-14
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 청킹 파이프라인에 5개 전략이 이미 구현돼 있음에도 사용자는 "조항 청킹 ON/OFF" 토글 하나만 제어 가능하다. 조항 미사용 KB는 `parent_child`(parent 2000 / child 500 / overlap 50)가 하드코딩되어, 문서 특성(FAQ·매뉴얼·표 중심 등)에 맞는 청킹 조정이 불가능하다. |
| **Solution** | KB에 **독립 opt-in 필드**(`use_custom_chunking` + `custom_chunking_config` JSON)를 신설한다. 사용자는 KB 생성/수정 화면 고급 옵션에서 전략(5종), chunk_size/overlap/parent_size, 그리고 경계 패턴(정규식)까지 지정한다. 기존 조항 청킹 경로·legacy 경로는 손대지 않고 resolver에서 분기만 추가한다. |
| **Function/UX Effect** | KB 생성/수정 모달에서 전략 드롭다운 + 사이즈/오버랩 입력 + (경계 전략 선택 시) 정규식 패턴 편집 UI 제공. 설정 변경은 신규 업로드부터 적용되며 기존 문서는 불변. |
| **Core Value** | 문서 유형별 검색 품질 최적화를 관리자 개입 없이 사용자가 직접 수행 — RAG 플랫폼의 셀프서비스 수준을 한 단계 올린다. |

---

## 1. Overview

### 1.1 Purpose

KB별로 청킹 방식(자르는 기준·크기·오버랩)을 사용자가 직접 커스터마이징할 수 있게 한다.
현재는 조항(clause) 청킹 opt-in만 가능하고, 그 외에는 모든 KB가 동일한 하드코딩 값으로 청킹된다.

### 1.2 Background (현재 구조 분석)

| 항목 | 현재 상태 | 근거 코드 |
|------|-----------|----------|
| 전략 구현 | 5종 존재: `full_token`, `parent_child`, `semantic`, `section_aware`, `clause_aware` | `src/infrastructure/chunking/chunking_factory.py` |
| 사용자 선택권 | `use_clause_chunking` bool 토글 하나뿐 | `CreateKnowledgeBaseModal.tsx:32` |
| 비조항(legacy) 경로 | `parent_child` 고정, parent 2000 하드코딩, child size/overlap은 업로드 쿼리 파라미터(기본 500/50)이나 프론트 미노출 | `unified_upload/use_case.py:202-214` |
| KB의 `chunk_size`/`chunk_overlap` | **조항 청킹 전용 오버라이드** — 조항 OFF면 무시됨 | `chunking_resolver.py:29-30` |
| 경계 패턴 | ChunkingProfile(관리자 CRUD)의 `boundary_rules`로만 존재, 조항 경로 전용 | `domain/chunking_profile/entities.py` |
| 청킹 프리뷰 | `/api/v1/preview/ingest` 존재하나 KB 설정 기반 아님 | `preview_router.py` |

### 1.3 Related Documents

- 선행 기능: `clause-aware-chunking` (아카이브) — 프로파일/resolver/전략 구조의 원형
- 규칙: `docs/rules/rag-retrieval.md`, `docs/rules/testing.md`, `docs/rules/db-session.md`
- 사용자 결정 사항 (2026-07-14 질의응답):
  1. 커스텀 범위: **경계 패턴(정규식)까지** 포함
  2. 설정 단위: **KB 단위** (업로드별 오버라이드 없음)
  3. 기존 문서: **신규 업로드부터 적용** (재인덱싱 제외)
  4. 필드 설계: **독립 opt-in 필드 신설** (기존 조항 필드 의미 변경 금지)

---

## 2. Scope

### 2.1 In Scope

**백엔드 (idt/)**
- [ ] KB 엔티티/테이블에 독립 opt-in 필드 신설: `use_custom_chunking`(bool, default false) + `custom_chunking_config`(JSON, nullable) — Flyway 마이그레이션 포함
- [ ] `custom_chunking_config` 스키마 정의: `strategy`, `chunk_size`, `chunk_overlap`, `parent_chunk_size`, `min_chunk_size`, `boundary_rules[{pattern, priority, level}]`
- [ ] KB 생성/수정 API 확장 + 서버측 검증(전략별 필수 파라미터, 값 범위, 정규식 컴파일 검증, 조항 토글과 상호배타)
- [ ] `ChunkingSettingsResolver` 확장: custom 켜진 KB → `UploadChunkingConfig` 생성 (경계 패턴 전략은 기존 `clause_aware` 전략 기계 재사용)
- [ ] 검증 불가/손상된 설정 시 legacy 경로 폴백 + warning 로그 (업로드는 항상 성공 — 기존 FR-07 패턴 준용)
- [ ] KB 상세 조회 응답에 커스텀 청킹 설정 노출

**프론트엔드 (idt_front/)**
- [ ] KB 생성 모달 고급 옵션 확장: 커스텀 청킹 토글 → 전략 선택 + 파라미터 입력 + (경계 전략 시) 정규식 규칙 편집 리스트
- [ ] KB 상세 페이지에서 청킹 설정 조회/수정 UI (기존 문서 불변 안내 문구 포함)
- [ ] 타입/서비스/훅/API 상수 동기화 (`api-contract-sync` 체크리스트 준수)
- [ ] 조항 토글과 커스텀 토글 상호배타 UX (하나 켜면 다른 쪽 비활성)

**공통**
- [ ] TDD: 백엔드 pytest / 프론트 Vitest+RTL+MSW 테스트 선행 작성

### 2.2 Out of Scope

- 기존 업로드 문서의 **재인덱싱/재청킹** (설정 변경은 신규 업로드부터만 적용) → 후속 `kb-rechunk-reindex`
- 업로드 시점 문서별 오버라이드 UI (KB 단위로 통일)
- 커스텀 설정 기반 **청킹 프리뷰**(업로드 전 미리보기) → 후속 후보 (`/api/v1/preview` 재사용 가능)
- ChunkingProfile(관리자 프로파일) 시스템 변경 — 조항 경로는 현행 유지
- 임베딩 모델/검색 파라미터 커스터마이징 (청킹 한정)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | KB에 `use_custom_chunking`(bool)·`custom_chunking_config`(JSON) 독립 필드 신설, 기본값 OFF — 기존 KB/조항 경로 동작 무변경 | High | Pending |
| FR-02 | 전략 선택: `parent_child` / `full_token` / `semantic` / `section_aware` / `boundary_pattern`(내부적으로 clause_aware 재사용) 5종 | High | Pending |
| FR-03 | 파라미터 지정: `chunk_size`(100–4000), `chunk_overlap`(0–500, chunk_size 미만), `parent_chunk_size`(500–8000, parent 계열만), `min_chunk_size`(semantic/section_aware) | High | Pending |
| FR-04 | 경계 패턴: parent/child 레벨별 정규식 + priority 목록을 사용자가 정의. 저장 시 `re.compile` 검증, 실패 시 400 + 어떤 패턴이 왜 실패했는지 응답 | High | Pending |
| FR-05 | `use_clause_chunking`과 `use_custom_chunking` 동시 활성 금지 — 생성/수정 API에서 422 거부, 프론트도 상호배타 UX | High | Pending |
| FR-06 | 업로드 시 resolver가 custom 설정을 `UploadChunkingConfig`로 해석, `display`에 전략/파라미터 기록(문서별 청킹 이력 추적 유지) | High | Pending |
| FR-07 | 설정이 손상/해석 불가면 legacy 경로 폴백 + warning 로그 — 업로드 실패 금지 | High | Pending |
| FR-08 | 설정 변경은 신규 업로드부터 적용, 기존 문서 불변 — 수정 UI에 "기존 문서에는 적용되지 않음" 안내 표시 | Medium | Pending |
| FR-09 | KB 생성/수정/상세 프론트 UI: 전략 드롭다운, 파라미터 입력(범위 검증), 경계 규칙 편집(추가/삭제/우선순위) | High | Pending |
| FR-10 | 프론트-백엔드 타입 계약 동기화 (`types/knowledgeBase.ts`, `services`, `hooks`, `constants/api.ts`) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 안전성 | 사용자 정규식 ReDoS 방지: 패턴 길이 상한(예: 200자) + 규칙 개수 상한(예: 레벨당 10개) + 컴파일 검증. (Python `re`는 타임아웃 미지원 → 상한으로 완화) | 단위 테스트 + 코드 리뷰 |
| 하위 호환 | 기존 KB(양쪽 토글 OFF) 및 조항 KB의 청킹 결과 바이트 단위 동일 | 기존 테스트 회귀 통과 |
| 아키텍처 | Thin DDD 레이어 준수 — 검증 규칙은 domain policy, 해석은 application resolver, 전략 생성은 infrastructure factory | `/verify-architecture` |
| 테스트 | TDD 선행, 신규 모듈 테스트 파일 존재 | `/verify-tdd` |
| 코드 규약 | 함수 40줄 이하, if 중첩 2단계 이하, config 하드코딩 금지 | 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-10 구현 및 테스트 통과
- [ ] Flyway 마이그레이션 파일 생성 (`db/migration/V0xx__alter_knowledge_base_custom_chunking.sql`)
- [ ] 커스텀 KB에 문서 업로드 → 지정한 전략/파라미터로 청킹됨을 chunk 브라우저(kb-content-browser)로 확인
- [ ] 양쪽 토글 OFF KB 업로드 → 기존과 동일한 legacy 청킹 (회귀 없음)
- [ ] Gap 분석(`/pdca analyze kb-custom-chunking`) ≥ 90%

### 4.2 Quality Criteria

- [ ] 백엔드 pytest 신규 테스트 전부 통과 (기존 사전 실패 케이스와 구분 — memory: preexisting failures 참고)
- [ ] 프론트 Vitest 신규 테스트 통과 (`--pool=threads`, MSW per-file listen 준수)
- [ ] 빌드/린트 무오류

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 잘못된 정규식으로 이상 청킹(0개 매치 → 거대 청크 등) | Medium | High | 저장 시 컴파일 검증 + 매치 실패 시 토큰 분할 폴백은 기존 clause_aware 동작 재사용. 후속으로 프리뷰 기능 권장 |
| ReDoS성 패턴(중첩 수량자) | High | Low | 패턴 길이·개수 상한, 문서화. 필요 시 후속에서 `regex` 모듈 타임아웃 도입 검토 |
| 한 KB 안에 서로 다른 청킹 문서 혼재 → 검색 품질 편차 | Medium | Medium | 사용자 결정대로 신규 업로드부터 적용. 문서별 `chunking_config` display 기록으로 추적 가능, UI 안내 문구 |
| 조항/커스텀 토글 충돌 | Medium | Medium | FR-05 상호배타 검증(백+프론트 이중) |
| `semantic` 전략의 비용/속도 특성 미고지 | Low | Medium | UI에 전략별 설명 툴팁 제공 |
| JSON config 필드의 스키마 드리프트 | Medium | Low | domain에 pydantic 스키마 고정 + 버전 키(`version: 1`) 포함 |

---

## 6. Architecture Considerations

### 6.1 Project Level

기존 프로젝트 구조 유지 — **Enterprise**(Thin DDD: domain → application → infrastructure → interfaces). 신규 레벨 결정 없음.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 필드 설계 | 기존 필드 의미 확장 vs 독립 opt-in 신설 | **독립 opt-in** (`use_custom_chunking` + JSON config) | 사용자 결정. 기존 조항 경로가 교차검증 기준선으로 보존됨 (메모리: 독립 opt-in 선호) |
| 경계 패턴 저장 위치 | ChunkingProfile 재사용 vs KB 인라인 JSON | **KB 인라인 JSON** | 프로파일은 관리자 공유 자원, 커스텀은 KB 소유 설정 — 소유권/권한 모델이 다름. 프로파일 시스템 무변경 |
| 경계 패턴 실행 | 신규 전략 구현 vs clause_aware 재사용 | **clause_aware 기계 재사용** | factory가 이미 `parent_patterns`/`child_patterns` kwargs 지원 — 신규 코드 최소화 |
| 설정 해석 지점 | 업로드 use_case vs resolver | **`ChunkingSettingsResolver` 확장** | 조항 경로와 동일한 해석 지점 — 분기 한 곳으로 수렴 |
| config 저장 형식 | 개별 컬럼 vs JSON 컬럼 | **JSON 컬럼 1개** | 전략별 파라미터 가변성(경계 규칙 리스트 포함) 수용, 스키마 변경 최소화 |

### 6.3 예상 변경 지점 (설계 단계에서 상세화)

```
idt/ (백엔드)
├── domain/knowledge_base/entities.py           # 필드 2개 추가
├── domain/knowledge_base/custom_chunking.py    # (신규) config 스키마 + 검증 policy
├── application/knowledge_base/chunking_resolver.py  # custom 분기 추가
├── application/knowledge_base/use_case.py      # 생성/수정 시 검증 호출
├── infrastructure/persistence/models/knowledge_base.py  # 컬럼 추가
├── infrastructure/knowledge_base/repository.py # 매핑 + update 화이트리스트 (메모리: repo update() 4곳 세트 주의)
├── api/routes/knowledge_base_router.py         # 요청/응답 스키마 확장
└── db/migration/V0xx__...sql                   # ALTER TABLE

idt_front/ (프론트엔드)
├── types/knowledgeBase.ts                      # 타입 확장
├── components/knowledge-base/CreateKnowledgeBaseModal.tsx  # 고급 옵션 확장
├── components/knowledge-base/CustomChunkingFields.tsx      # (신규) 전략/파라미터/규칙 편집
├── pages/KnowledgeBaseDetailPage/index.tsx     # 설정 조회/수정
├── services/knowledgeBaseService.ts, hooks/useKnowledgeBases.ts
└── constants/api.ts
```

---

## 7. Convention Prerequisites

- [x] `CLAUDE.md` 코딩 컨벤션 존재 (루트 + idt + idt_front)
- [x] 레이어 규칙: domain은 LangChain/DB 접근 금지 — config 검증은 순수 python/pydantic으로 domain에 배치
- [x] DB 세션 규칙: `docs/rules/db-session.md` (Repository 내 commit 금지 등)
- [x] 로깅: LOG-001, print() 금지
- [x] 테스트: 백엔드 pytest 격리 실행(Windows 이벤트 루프 이슈), 프론트 `--pool=threads` + MSW per-file listen
- 신규 환경변수: **없음**

---

## 8. Next Steps

1. [ ] `/pdca design kb-custom-chunking` — config 스키마·검증 규칙·UI 상세 설계
2. [ ] 설계 리뷰 (특히 FR-04 정규식 검증 정책, JSON 스키마 확정)
3. [ ] TDD 구현 시작

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-14 | 최초 작성 (사용자 질의응답 4건 반영) | 배상규 |
