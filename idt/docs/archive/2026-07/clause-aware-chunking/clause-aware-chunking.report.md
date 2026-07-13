# clause-aware-chunking 완료 리포트

> **Feature**: clause-aware-chunking (조·항 의미 경계 인식 청킹 파이프라인)
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Period**: 2026-07-07 (Plan → Report, 단일 세션)
> **Final Match Rate**: **99%**
> **Status**: ✅ Completed (백엔드) — 프론트/기본경로 교체는 후속 PDCA

---

## Executive Summary

### 1.1 개요

| 항목 | 내용 |
|------|------|
| Feature | clause-aware-chunking |
| 기간 | 2026-07-07 (Plan·Design·Do·Check·Report) |
| PDCA 흐름 | Plan ✅ → Design ✅ → Do ✅ → Check ✅ (99%) → Report ✅ |
| 아키텍처 | Thin DDD (Domain·Application·Infrastructure·Interfaces) |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| Match Rate | 99% (최초 98% → G1/G2 즉시 해소) |
| 신규 프로덕션 파일 | 12개 (1,170 LOC) |
| 수정(additive) 파일 | 8개 |
| 신규 테스트 | 94건 (887 LOC) — 전부 통과 |
| 관련 기존 스위트 회귀 | 0건 (223건 통과 유지) |
| High/Medium Gap | 0건 |
| DB 마이그레이션 | V041(신규 테이블+시드), V042(KB additive) |

### 1.3 Value Delivered

| Perspective | 전달된 가치 (실측) |
|-------------|---------------------|
| **Problem** | 업로드가 문서 구조 무관 `parent_child` 토큰 분할을 하드코딩(`unified_upload/use_case.py:89`)해 조·항 경계가 청크 중간에서 잘리던 문제 → `ClauseAwareStrategy`로 조 단위 의미 보존. 경계 보존·페이지 결합·overlap을 19개 단위 테스트로 검증. |
| **Solution** | 3단계 파이프라인(①조 경계 분할 → ②초과 시 토큰 분할 → ③overlap) 신규 전략 + 청킹 프로파일(정규식 규칙 DB 관리) + KB 단위 late-binding 설정. 기존 경로는 `chunking_config=None` 분기로 완전 불변(회귀 가드 테스트). |
| **Function/UX Effect** | 관리자: `/api/v1/admin/chunking/profiles` CRUD로 문서 유형별 경계 프로파일·기본값 관리(화면 없이 API). 사용자: KB 생성 시 청킹 설정 지정/기본값 위임, 해당 KB 업로드에 자동 적용. 에이전트 빌더: `GET /api/v1/chunking/profiles`로 프리필. |
| **Core Value** | 조=parent 매핑으로 **기존 하이브리드 검색 코드 무수정 호환** + 청킹 정책의 중앙 관리(관리자)/개별 오버라이드(KB) 분리. Match Rate 99%, 회귀 0건으로 안전하게 병행 도입. |

---

## 2. 구현 범위

### 2.1 신규 프로덕션 파일 (12개)

| 레이어 | 파일 | 역할 |
|--------|------|------|
| DB | `V041__create_chunking_profile.sql` | 프로파일 테이블 + 기본 프로파일 시드 |
| DB | `V042__alter_knowledge_base_add_chunking.sql` | KB additive 컬럼 4개 + FK |
| domain | `chunking_profile/entities.py` | `ChunkingProfile`, `BoundaryRule` |
| domain | `chunking_profile/interfaces.py` | Repository 인터페이스 |
| domain | `chunking_profile/policy.py` | 이름·규칙(정규식 컴파일)·사이즈·KB오버라이드 검증 |
| application | `chunking_profile/use_case.py` | 관리자 CRUD + default 유일성(단일 세션) + 사용자 목록 |
| application | `knowledge_base/chunking_resolver.py` | KB 설정 → 업로드 config 해석 + 폴백 |
| infra | `chunking_profile/repository.py` | MySQL 영속화 (JSON 규칙 직렬화) |
| infra | `persistence/models/chunking_profile.py` | SQLAlchemy 모델 |
| infra | `chunking/strategies/clause_aware_strategy.py` | ①→②→③ 청킹 전략 (핵심) |
| api | `admin_chunking_router.py` | 관리자 CRUD (require_role admin) |
| api | `chunking_profile_router.py` | 사용자 조회 |

### 2.2 수정 파일 (additive, 8개)

- `chunking/chunking_factory.py` — `CLAUSE_AWARE` 전략 등록
- `unified_upload/{schemas,use_case}.py` — `UploadChunkingConfig` + `_build_strategy` 분기
- `knowledge_base/{use_case,upload_use_case}.py` — 청킹 필드 검증/resolver 위임
- `domain/knowledge_base/entities.py`, `persistence/models/knowledge_base.py`, `knowledge_base/repository.py` — additive 컬럼
- `api/routes/knowledge_base_router.py` — 청킹 필드 + 업로드 응답 전략
- `api/main.py` — DI 배선 + 라우터 등록

---

## 3. 핵심 설계 결정 이행 (D1~D16)

전 16개 설계 결정 코드 반영 확인. 대표:
- **D8 페이지 결합**: 파서가 페이지당 Document를 산출하나 조는 페이지 경계를 넘으므로, 전략이 페이지를 결합하고 누적 offset으로 `page_start/page_end`를 산출 (동일 본문 조 중복도 정확 — G1 반영).
- **D9 계약 호환**: 산출 청크가 기존 `parent_child` 메타데이터(chunk_type/parent_id/children_ids/chunk_index/total_chunks)를 그대로 준수 → 검색 무수정.
- **D5/D11 late binding**: KB NULL 컬럼 = 업로드 시점 프로파일 값, 값 = 사용자 고정. 프로파일 삭제/부재 시 default→legacy 폴백으로 업로드 항상 성공.
- **D6 opt-in**: `use_clause_chunking` KB는 Query 청킹 파라미터 무시+warning (OpenAPI description 명시 — G2 반영).

---

## 4. Gap 처리 (Check 99%)

| # | Gap | 조치 |
|---|-----|------|
| G1 | `find()` 역탐색 → 중복 본문 조 페이지 오탐 가능 | 누적 offset 직접 전달 리팩터 + 회귀 테스트 → 해소 |
| G2 | 업로드 D6 규칙 OpenAPI 문서화 누락 | `@router.post(description=...)` 추가 → 해소 |
| G3 | 시드 정규식이 전각 괄호·공백 변형 미커버 | 설계가 Do 체크리스트로 명시 이연 (프로파일 UPDATE로 조정, 코드 무관) |

---

## 5. 검증 결과

- **테스트**: 신규 94건 전부 통과, 관련 기존 223건 회귀 0건.
- **verify-architecture**: 5/5 PASS (도메인→인프라/LangChain 참조 없음, 라우터 직접 인스턴스화 없음, 인프라 Policy 없음).
- **verify-tdd**: 핵심 모듈 전부 직접 테스트 보유 (repository는 `KnowledgeBaseRepository` 선례대로 간접 커버).
- **verify-logging**: 신규 파일 `print()` 없음, request_id 로깅 준수.

---

## 6. 후속 과제 (Plan §7 로드맵)

1. **운영 절차 (즉시)**: V041/V042 Flyway 적용 + 시드 패턴 실제 규정 PDF 검증 (G3).
2. **chunking-frontend**: 관리자 프로파일 화면 + KB/에이전트 빌더 청킹 UI (`/api-contract-sync`).
3. **chunking-default-migration**: 검증 후 기존 업로드 기본 전략을 clause_aware로 교체, 하드코딩 제거.
4. **document-rechunk**: 프로파일 변경 시 기존 문서 재청킹·재인덱싱.
5. **표 처리 최적화**: clause_aware에 table_flattening 결합 (D13 이연분).

---

## 7. 학습 노트

- 파서 산출 단위(페이지당 Document)를 먼저 확인한 것이 D8(페이지 결합) 설계로 이어져, "조가 페이지 경계를 넘어 잘리는" 잠재 결함을 구현 전 차단.
- 기존 `ParentChildStrategy`의 메타데이터 계약을 정확히 복제(조=parent)한 것이 검색 코드 무수정 호환의 핵심 — 신규 기능을 기존 파이프라인에 안전하게 병행 도입하는 패턴.
- additive optional 필드(`chunking_config=None`) + 회귀 가드 테스트 조합으로 "기존 프로세스 무수정" 요구를 검증 가능한 형태로 보장.
