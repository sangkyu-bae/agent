# clause-aware-chunking Planning Document

> **Summary**: 벡터DB 적재 시 문서를 ① 조·항 등 의미 경계로 먼저 분할하고 ② 초과 조각만 토큰 기준 분할 ③ 인접 조항 잘림 방지 overlap을 적용하는 신규 청킹 파이프라인을 도입한다. 경계 규칙(정규식 프로파일)과 토큰/overlap 기본값은 관리자가 DB로 관리하고, 지식베이스(KB) 단위로 사용자가 오버라이드할 수 있다. 기존 업로드 프로세스는 무수정 유지(additive-only), 신규 경로는 opt-in으로 병행 후 추후 교체한다.
>
> **Project**: sangplusbot (idt 백엔드 전용)
> **Author**: 배상규
> **Date**: 2026-07-07
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 업로드는 문서 구조와 무관하게 `parent_child` 토큰 분할을 하드코딩으로 적용한다(`unified_upload/use_case.py:89-94`). 금융/정책 문서의 조·항 경계가 청크 중간에서 잘려 검색 품질이 저하되고, 청킹 파라미터(토큰 크기·overlap)도 코드/쿼리 파라미터에 흩어져 있어 관리자가 통제할 수 없다. |
| **Solution** | 조·항 의미 경계 우선 분할 → 초과 시에만 토큰 분할 → overlap 적용의 3단계 `clause_aware` 청킹 전략을 신규 추가한다. 경계 규칙은 "청킹 프로파일"(정규식 패턴 + 우선순위 + 기본 토큰/overlap)로 DB에서 관리자가 CRUD하고, KB 생성 시 프로파일·토큰·overlap을 스냅샷/오버라이드하여 업로드 시 자동 적용한다. 에이전트 빌더는 KB 선택/생성 시 관리자 기본값을 프리필받는다. |
| **Function/UX Effect** | 관리자는 문서 유형별(법령/규정/일반) 경계 프로파일과 기본값을 화면 없이도 API로 등록·수정한다. 사용자는 KB 생성 시 기본값이 채워진 청킹 설정을 그대로 쓰거나 변경하고, 이후 그 KB의 모든 업로드에 일관 적용된다. |
| **Core Value** | 조항 단위 의미 보존 청킹으로 RAG 검색 정확도 향상 + 청킹 정책의 중앙 관리(관리자) / 유연한 개별 설정(KB·에이전트) 분리. 기존 parent_child 검색 경로와 100% 호환되는 구조(조=parent)로 검색 코드 무수정. |

---

## 1. Overview

### 1.1 Purpose

문서 구조(조·항·호 등 의미 경계)를 인식하는 청킹 파이프라인을 신규 도입하고, 그 설정을 계층화한다.

- **관리자**: 경계 규칙 프로파일(정규식 목록) + 기본 토큰 크기/overlap을 DB에서 관리
- **사용자**: KB 생성 시 기본값 프리필 → 필요 시 변경(오버라이드) → 해당 KB 업로드에 자동 적용
- **에이전트**: 에이전트 생성 시 내부 문서 사용을 선택하면 KB의 청킹 설정을 따름(프리필은 프론트 후속)

이번 사이클은 **백엔드 신규 경로만** 추가한다. 기존 엔드포인트/유스케이스/전략은 수정하지 않고(additive-only), 신규 구조 검증 후 별도 PDCA로 기본 경로를 교체한다.

### 1.2 Background — 현재 구조 (2026-07-07 코드 확인)

**청킹이 업로드 유스케이스에 하드코딩**
- `UnifiedUploadUseCase.execute()`가 `ChunkingStrategyFactory.create_strategy("parent_child", parent_chunk_size=2000, ...)`를 고정 호출 (`src/application/unified_upload/use_case.py:89-94`). child 크기/overlap만 요청 파라미터(기본 500/50).
- KB 업로드(`knowledge_base/upload_use_case.py:43-44`)와 KB 라우터(`knowledge_base_router.py:211-212`)도 Query 파라미터로 child 값만 넘기고 동일 경로에 위임.

**청킹 전략 인프라는 이미 확장 가능**
- `ChunkingStrategyFactory` (`src/infrastructure/chunking/chunking_factory.py`)에 `full_token`/`parent_child`/`semantic`/`section_aware` 4개 전략 등록 — **신규 전략 타입 추가는 additive**.
- `BaseTokenChunker.split_by_tokens()`가 tiktoken 기반 토큰 분할 + overlap을 이미 지원 (`base_token_chunker.py:38-71`) — ②③ 단계의 빌딩블록 재사용 가능.
- 기존 `section_aware` 전략은 **파서가 넣어준 `section_title` 메타데이터** 기반이라, 관리자 정의 정규식으로 본문을 직접 분할하는 이번 요구와 다름(참고 구현으로만 활용).

**parent/child 메타데이터 계약 확인**
- `ParentChildStrategy`가 산출하는 계약: parent는 `{chunk_type: "parent", chunk_id, children_ids, chunk_index, total_chunks}`, child는 `{chunk_type: "child", chunk_id, parent_id, chunk_index, total_chunks}` (`parent_child_strategy.py:57-110`). 신규 전략이 이 계약을 그대로 산출하면 **기존 검색(child 검색 → parent 컨텍스트 확장) 무수정 호환**.

**설정 관리 인프라 부재**
- 관리자 설정 테이블 없음(마이그레이션 V001~V040 확인). 경계 규칙·기본값을 담을 신규 테이블 필요.
- `knowledge_base` 테이블(V040, 직전 사이클)에 청킹 관련 컬럼 없음 → additive ALTER 필요.
- 에이전트의 `RagToolConfig`(agent_tool config JSON)는 검색 설정(top_k, search_mode 등)만 보유 — 청킹은 업로드 시점 관심사이므로 여기에 두지 않는다(§1.3 결정).

### 1.3 사용자 결정 사항 (2026-07-07 확인)

| 질문 | 결정 |
|------|------|
| 경계 규칙 관리 단위 | **규칙 프로파일 방식** — 관리자가 '법령', '규정' 등 프로파일을 여러 개 등록, 각 프로파일에 정규식 패턴+우선순위 목록. 기본 프로파일 1개 지정 |
| 청킹 설정 저장·적용 위치 | **KB에 저장 + 에이전트 생성 시 프리필** — 데이터(청크)와 설정의 수명을 일치시켜 에이전트 간 충돌 방지. 에이전트별 오버라이드는 도입하지 않음 |
| 산출 청크 구조 | **조=parent, 분할 조각=child** — 기존 parent_child 검색 경로와 완전 호환, 검색 코드 무수정 |
| 이번 범위 | **백엔드 전체** — 신규 전략 + 관리자 CRUD API + KB 설정 연동 + 업로드 opt-in 경로. 프론트(관리자 화면, 에이전트 빌더 UI)는 후속 PDCA |
| 기존 코드 | 기존 프로세스 무수정 유지, 신규 opt-in 병행 후 추후 교체 |

---

## 2. Scope

### 2.1 In Scope (백엔드 idt/)

**A. 청킹 프로파일 도메인 + 영속화**
- [ ] `domain/chunking_profile/`(가칭): 엔티티(`ChunkingProfile` — 이름, 설명, 경계 규칙 목록, 기본 chunk_size/overlap, is_default, status), `ChunkingProfileRepositoryInterface`, 정책(`ChunkingProfilePolicy` — 규칙 정규식 컴파일 검증, 패턴 길이/개수 상한, chunk_size·overlap 범위 검증(overlap < size), 기본 프로파일 유일성)
- [ ] 경계 규칙 구조: `{pattern, priority, level}` — level로 parent 경계(조)와 child 경계(항·호)를 구분. 규칙 저장 형태(JSON 컬럼 vs 자식 테이블)는 Design에서 확정 (추천: JSON 컬럼 — 규칙은 프로파일 단위로만 읽고 쓰므로 과도한 정규화 회피)
- [ ] Flyway 마이그레이션 `V041__create_chunking_profile.sql` — FK 콜레이션 관례(CHARSET/COLLATE 명시 금지, V037 선례) 준수
- [ ] 시드: 기본 프로파일 1건(제N조/제N항/N. 등 국내 법령·규정 표준 패턴, is_default=true) — 시드 방식(마이그레이션 vs 스타트업)은 Design에서 확정

**B. 관리자 API — 신규 라우터 `/api/v1/admin/chunking`**
- [ ] `POST /profiles`, `GET /profiles`, `GET /profiles/{id}`, `PUT /profiles/{id}`, `DELETE /profiles/{id}`(soft delete, KB가 참조 중인 프로파일 삭제 정책은 Design에서 확정) — 전부 `Depends(require_role('admin'))`
- [ ] `PUT /profiles/{id}/default` — 기본 프로파일 지정(기존 default 해제와 원자적으로)
- [ ] 사용자 조회용: `GET /api/v1/chunking/profiles` (일반 인증) — KB 생성 폼/에이전트 빌더 프리필용 목록 + 유효 기본값 조회

**C. KB 청킹 설정 연동**
- [ ] `V042__alter_knowledge_base_add_chunking.sql`(additive): `chunking_profile_id`(nullable FK), `chunk_size`(nullable), `chunk_overlap`(nullable), `use_clause_chunking`(bool, default false 등 opt-in 플래그 — 컬럼 구성은 Design에서 확정)
- [ ] 의미: **NULL = 업로드 시점의 관리자 기본값을 따름 / 값 존재 = 사용자 오버라이드 고정** ("사용자 변경 시 그 기준을 따라간다" 요구 충족)
- [ ] `POST /api/v1/knowledge-bases` 요청에 optional 청킹 설정 필드 추가(additive — 미지정 시 기존 동작), `GET` 응답에 청킹 설정 노출

**D. `clause_aware` 청킹 전략 + 업로드 opt-in 경로**
- [ ] `StrategyType.CLAUSE_AWARE` + `ClauseAwareStrategy`(infrastructure/chunking/strategies/): ① parent 경계 규칙(조)으로 분할 → 조 전체=parent ② 조 내부를 child 경계(항·호)로 분할, 초과 조각만 `BaseTokenChunker`로 토큰 분할 ③ 토큰 분할 시 overlap 적용. 산출 메타데이터는 기존 parent_child 계약(chunk_type/parent_id/children_ids/chunk_index/total_chunks) 준수
- [ ] 경계 규칙 미매치 문서 fallback: 문서 전체를 기존 parent_child 방식으로 분할(전략 내부에서 처리 — 업로드 실패 금지)
- [ ] 전략은 DB 무접근 — 규칙은 생성 시점에 주입(UseCase가 프로파일 조회 → factory에 전달)
- [ ] `UnifiedUploadRequest`에 optional `chunking_config`(전략+파라미터) 필드 추가(additive, `extra_metadata` 선례) — 미지정 시 기존 parent_child 하드코딩 경로 그대로
- [ ] `KnowledgeBaseUploadUseCase`: KB에 청킹 설정이 있으면 프로파일 해석(오버라이드/기본값 병합) 후 `chunking_config`로 위임, 없으면 기존 동작. `document_metadata.chunk_strategy` 및 응답 `chunking_config`에 실제 사용 전략 기록

**E. 테스트 (TDD — 구현 전 작성)**
- [ ] 전략 단위 테스트: 조·항 분할 정확성(경계 보존), 초과 조각만 토큰 분할, overlap 적용, parent/child 계약 일치, 규칙 미매치 fallback
- [ ] 프로파일 정책 테스트: 잘못된 정규식 거부, 범위 검증, default 유일성
- [ ] use case/router 테스트: 관리자 가드 403, KB 설정 저장·해석(NULL=기본값/값=오버라이드), 업로드 위임 파라미터 검증
- [ ] 회귀 가드: `chunking_config` 미지정 시 기존 동작 불변

### 2.2 Out of Scope (후속 PDCA)

| 항목 | 사유/비고 |
|------|-----------|
| 기존 업로드 경로의 기본 전략 교체("갈아끼기") | 신규 구조 검증 후 진행 — 기존 parent_child 하드코딩 유지 |
| 기존 문서 재청킹/백필 | 프로파일·설정 변경은 신규 업로드부터 적용, 재인덱싱은 별도 사이클 |
| 프론트엔드(관리자 프로파일 화면, KB/에이전트 빌더 청킹 설정 UI) | 백엔드 검증 후 `/api-contract-sync`와 함께 |
| 에이전트 단위 청킹 오버라이드 | KB 단위로 충분 — 충돌 모델이 필요해지면 재검토 |
| 경계 규칙 자동 감지(문서 유형 분류) | 프로파일 수동 선택으로 시작 |
| unified upload(비-KB) 라우터에 clause_aware 노출 | KB 경로 우선 — 필요 시 저비용 추가 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| FR-01 | 관리자는 청킹 프로파일(이름, 경계 규칙[패턴+우선순위+level], 기본 chunk_size/overlap)을 CRUD할 수 있다. 일반 사용자는 관리 API에서 403 | High |
| FR-02 | 관리자는 기본 프로파일을 정확히 1개 지정할 수 있다 | High |
| FR-03 | 일반 사용자는 활성 프로파일 목록과 유효 기본값을 조회할 수 있다(KB 생성/에이전트 빌더 프리필용) | High |
| FR-04 | KB 생성 시 청킹 설정(프로파일, chunk_size, chunk_overlap)을 선택적으로 지정할 수 있고, 미지정 항목은 업로드 시점의 관리자 기본값을 따른다 | High |
| FR-05 | 청킹 설정이 있는 KB로 업로드하면 `clause_aware` 전략이 적용된다: 조 경계 분할(parent) → 항·호/초과 시 토큰 분할(child) → overlap | High |
| FR-06 | `clause_aware` 산출 청크는 기존 parent_child 메타데이터 계약을 준수하여 기존 하이브리드 검색이 무수정 동작한다 | High |
| FR-07 | 경계 규칙에 매치되지 않는 문서도 업로드가 실패하지 않고 fallback 분할된다 | High |
| FR-08 | 청킹 설정이 없는 KB·기존 업로드 경로는 기존 parent_child 동작을 그대로 유지한다 | High |
| FR-09 | 잘못된 정규식/범위 초과 설정(overlap ≥ size 등)은 저장 시점에 422로 거부된다 | Medium |
| FR-10 | 업로드 결과(응답·document_metadata)에 실제 적용된 전략/파라미터가 기록된다 | Medium |

### 3.2 Non-Functional Requirements

| ID | 요구사항 |
|----|----------|
| NFR-01 | 기존 엔드포인트·유스케이스·전략·테스트에 회귀 없음 (additive-only; optional 필드 추가만 허용) |
| NFR-02 | Thin DDD 준수 — 전략/도메인은 DB 무접근, 규칙은 주입. 정책은 domain에 |
| NFR-03 | TDD — 테스트 선작성 (pytest) |
| NFR-04 | 함수 40줄 이하, if 중첩 2단계 이하, config 하드코딩 금지(전략 기본값은 factory 상수/프로파일에서) |
| NFR-05 | 로깅 규칙(LOG-001) 준수 — 적용 전략·프로파일을 request_id와 함께 로깅 |
| NFR-06 | DB 세션 규칙 준수 — repository 내 commit/rollback 금지, UseCase 단일 세션 |
| NFR-07 | 관리자 입력 정규식의 안전성 — 컴파일 검증 + 패턴 길이/개수 상한(ReDoS 노출 최소화, 상세 기준 Design) |

---

## 4. 핵심 설계 방향 (Plan 레벨 결정, 상세는 Design)

1. **설정 계층 = 관리자 기본(프로파일) → KB 오버라이드**: 프로파일이 경계 규칙과 "그 문서 유형에 맞는" 기본 chunk_size/overlap을 함께 보유. 전역 기본 = is_default 프로파일. KB의 NULL 컬럼은 업로드 시점에 프로파일 값으로 해석(late binding) — 관리자가 기본값을 바꾸면 미오버라이드 KB에 자동 반영.
2. **조=parent / 항·호=child 계층 매핑**: 경계 규칙의 `level`(parent/child)로 2단 분할. parent(조)도 상한 필요 — 조 하나가 parent 상한 초과 시 처리(분할 vs 그대로)는 Design에서 확정.
3. **전략의 순수성**: `ClauseAwareStrategy`는 컴파일된 규칙+파라미터만 받는 순수 로직. 프로파일 조회·병합은 application 레이어(`KnowledgeBaseUploadUseCase` 또는 전용 resolver)가 담당.
4. **opt-in 스위치는 KB 레코드**: 요청 파라미터가 아닌 KB 설정 존재 여부로 신규 경로 진입 — 업로드 호출부(프론트) 변경 없이 KB만 설정하면 적용.
5. **기존 Query 파라미터(child_chunk_size/overlap)와의 우선순위**: KB 청킹 설정이 있으면 KB 설정이 우선(Query 무시 or 거부) — 정확한 규칙은 Design에서 확정.

---

## 5. Risks & Mitigations

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 관리자 정규식 오류·악성 패턴(ReDoS) | 업로드 지연/행 | 저장 시 컴파일 검증 + 길이/개수 상한 + 매치 대상 텍스트를 페이지 단위로 제한(파서 산출 구조 활용) |
| 조 하나가 parent 상한(예: 2000토큰) 대폭 초과 | parent 컨텍스트 품질 저하 or 저장 실패 | parent 상한 초과 시 분할 정책을 Design에서 확정(overlap 분할 추천), 테스트 케이스 포함 |
| 경계 패턴이 전혀 없는 문서(표 중심, 스캔본 등) | 청킹 실패 | 전략 내 fallback(기존 parent_child 동작)으로 업로드 항상 성공 |
| 프로파일 수정 시 기존 적재 청크와 신규 청크의 규칙 불일치 | 동일 KB 내 청킹 이질성 | 허용하되 문서화 + `document_metadata.chunk_strategy`/응답에 기록. 재청킹은 후속 |
| KB가 참조하는 프로파일 삭제 | 업로드 시 해석 실패 | soft delete + 참조 중 삭제 정책(차단 vs 기본 프로파일 폴백)을 Design에서 확정 |
| parent/child 계약 미묘한 불일치(children_ids, chunk_index 재부여 등) | 검색 컨텍스트 확장 오동작 | 기존 `ParentChildStrategy` 산출물과 계약 필드 동일성 테스트로 가드 |
| 테이블 포함 문서 처리(기존 table_flattening 전처리) | 신규 전략에서 표 손실 | 표 처리 범위(재사용 vs 이연)를 Design에서 확정 |

---

## 6. Acceptance Criteria

- [ ] 일반 사용자로 `/api/v1/admin/chunking/profiles` 호출 시 403, 관리자는 정상 CRUD
- [ ] 잘못된 정규식/overlap ≥ chunk_size 프로파일 저장 시 422
- [ ] 청킹 설정을 지정해 KB 생성 → 해당 KB 업로드 시 Qdrant/ES에 조 단위 parent + 조각 child가 기존 메타데이터 계약대로 저장됨
- [ ] 조·항 경계가 청크 중간에서 잘리지 않음(경계 보존 단위 테스트) + 초과 조각만 토큰 분할 + overlap 적용 확인
- [ ] 청킹 설정 없는 KB·기존 업로드 경로는 기존과 동일 동작(회귀 가드 테스트)
- [ ] 규칙 미매치 문서 업로드 성공(fallback)
- [ ] 기존 테스트 스위트 신규 회귀 0건 (사전 실패분 제외)
- [ ] `/verify-architecture`, `/verify-tdd`, `/verify-logging` 통과

---

## 7. 후속 로드맵 (참고)

1. **chunking-frontend**: 관리자 프로파일 관리 화면 + KB 생성/에이전트 빌더 청킹 설정 프리필 UI (`/api-contract-sync`)
2. **chunking-default-migration**: 검증 후 기존 업로드 경로의 기본 전략을 clause_aware로 교체, 하드코딩 제거
3. **document-rechunk**: 프로파일/설정 변경 시 기존 문서 재청킹·재인덱싱 파이프라인
4. **unified-upload-clause-optin**: 비-KB 업로드 라우터에도 청킹 설정 노출(필요 시)
