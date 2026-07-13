# knowledge-base-scoping Gap Analysis Report

> **Analyzed**: 2026-07-07
> **Phase**: Check (PDCA) — Design vs Implementation 갭 분석
> **Design**: `docs/02-design/features/knowledge-base-scoping.design.md`
> **Plan**: `docs/01-plan/features/knowledge-base-scoping.plan.md`
> **Scope**: 물리 컬렉션(관리자)/논리 지식베이스(사용자, kb_id payload 필터) 분리 신규 경로 (additive-only)

---

## 1. 분석 개요

| 항목 | 값 |
|------|-----|
| 검증 대상 | knowledge-base-scoping 백엔드 신규 경로 |
| 설계 결정 | D1~D12 |
| 검증 축 | §3 파일구조, §4 DDL, §5 domain, §6 application(additive 2곳 + ES 매핑), §7 API 명세, §8 DI 배선, §9 테스트 |
| 알려진 의도적 편차 | 3건 (감점 제외 — §5 참조) |
| 이연 항목(정상 미구현) | D10/D11/D12 |

---

## 2. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match (D1~D12 + §3~§8) | 99% | ✅ |
| Architecture Compliance (Thin DDD, 세션 규칙) | 100% | ✅ |
| Test Coverage (§9 대조) | 100% | ✅ |
| **Overall** | **98%** | ✅ |

**결론**: 설계와 구현이 사실상 완전 일치. High/Medium 갭 없음. 발견된 편차는 모두 Low(외형/문서 표기) 수준이거나 명시된 의도적 편차이다. 추가 수정 없이 Report 단계 진행 가능.

---

## 3. 설계 결정 대조표 (D1~D12)

| ID | 결정 | 구현 위치 | 결과 |
|----|------|-----------|:----:|
| D1 | payload 필터키 `kb_id`=KB PK(VARCHAR(36) UUID), `kb_name` 동봉 | `V040:8`(PK+comment), `upload_use_case.py:63` | ✅ |
| D2 | `UnifiedUploadRequest.extra_metadata: dict[str,str]` optional(frozen, default_factory), 고정키 우선 | `schemas.py:14`(frozen), `use_case.py:102-103`(setdefault) | ✅ |
| D3 | ES 매핑 kb_id/kb_name keyword + `_store_to_es` body 병합(고정키 우선) | `es_index_mappings.py:45-46`, `use_case.py:278-279` | ✅ |
| D4 | soft delete(status active/deleted), DB (owner,name) 유니크 없음, active 중복은 UseCase 차단 | `V040:15,21-23`(유니크 無), `repository.py:93-100`, `use_case.py:46-51` | ✅ |
| D5 | 이름 유니코드 허용/1~100자/제어문자 금지, 소유자 내 active 중복 금지 | `policy.py:18-29`, `use_case.py:46` | ✅ |
| D6 | 물리 컬렉션 배정 `CollectionAssignerInterface` 추상화, `UserSelectedCollectionAssigner` 구현 | `interfaces.py:42-53`, `collection_assigner.py` | ✅ |
| D7 | `KnowledgeBasePolicy` domain 신규, `CollectionScope` import 재사용, collection_permissions 불연동 | `policy.py:9,15`(독립 클래스) | ✅ |
| D8 | 업로드 쓰기: PERSONAL/DEPARTMENT 동형, **PUBLIC=소유자+ADMIN만** | `policy.py:46-57` | ✅ |
| D9 | 신규 업로드 `get_current_user` 필수, user_id 토큰 추출(Query user_id 답습 금지) | `knowledge_base_router.py:213`, `upload_use_case.py:59` | ✅ |
| D10 | Qdrant kb_id payload index 이연 | 미구현(정상) | ✅ 이연 |
| D11 | KB CRUD activity_log 이연, StructuredLogger만 | `use_case.py:67,102`(logger.info만), activity_log 미연동 | ✅ 이연 |
| D12 | KB 상세 문서수/포인트수 집계 이연(레코드 필드만) | `get()` 레코드 반환, `KbInfoResponse` 집계 필드 없음 | ✅ 이연 |

---

## 4. 구조·명세 대조표 (§3~§9)

| 검증 축 | 설계 | 구현 | 결과 |
|---------|------|------|:----:|
| §3 파일 구조 | 신규 13 + 수정 3 파일 | 전부 존재(도메인/앱/인프라 `__init__.py` 포함), 수정 3곳 additive | ✅ |
| §4 DDL V040 | 컬럼/ENUM/FK(콜레이션 명시 금지)/인덱스 3종 | `V040` 설계문과 1:1 일치, SQLAlchemy 모델 `CollectionPermissionModel` 패턴 준수 | ✅ |
| §5.1 entities | `KnowledgeBase` dataclass 필드 | `entities.py` 필드/기본값 완전 일치 | ✅ |
| §5.2 policy | validate_name/can_read/write/delete/validate_scope | `policy.py` 5개 메서드 모두 구현 | ✅ |
| §5.3 interfaces | Repo IF 5메서드 + AssignerIF | 구현 + `find_all_active` 추가(의도적) | ✅ |
| §6.1 UseCase | create/list/get/delete 흐름 | `use_case.py` 흐름 일치 (list의 ADMIN 전체 분기 포함) | ✅ |
| §6.2 Assigner | 미존재→ValueError, 권한→check_read_access | `collection_assigner.py` 일치 | ✅ |
| §6.3 Upload | KB 조회→can_write→collection_name 자동→extra_metadata 위임 | `upload_use_case.py` 일치 | ✅ |
| §6.4 additive 2곳 | chunk.metadata + _store_to_es body setdefault | `use_case.py:102-103, 278-279` | ✅ |
| §6.5 ES 매핑 | kb_id/kb_name keyword | `es_index_mappings.py:45-46` | ✅ |
| §7.1 KB API | POST201/GET/GET{id}/DELETE/POST documents + 상태코드 매핑 | `knowledge_base_router.py` 5 엔드포인트 + `_raise_http` 매핑 | ✅ |
| §7.2 admin API | require_role('admin'), 기존 UseCase 재사용, scope 기본 PUBLIC | `admin_collection_router.py` 위임+PUBLIC 서브클래스 | ✅ |
| §8 DI 배선 | `create_knowledge_base_factories`, 동일 세션 규칙, admin은 기존 factory 공유 | `main.py:2525-2583`(unified=factory(session)), `:3392-3396` override, `:3568-3569` 등록 | ✅ |
| §9 테스트 | 7개 파일 케이스 목록 | 7개 전부 존재, 설계 케이스 전량 커버 | ✅ |

### 4-1. 테스트 케이스 커버리지 상세

| 파일 | 설계 요구 케이스 | 구현 | 결과 |
|------|------------------|------|:----:|
| `test_policy.py` | 이름 검증(빈/101/제어문자/한글), read/write/delete 매트릭스(PUBLIC 쓰기=소유자), validate_scope | 8+6+7+3+5 케이스 | ✅ |
| `test_use_case.py` | create 정상/중복409/이름검증/dept, list PERSONAL·ADMIN, get 404/403, delete 소유자·타인·ADMIN·soft_delete 검증 | 전량 | ✅ |
| `test_collection_assigner.py` | 미존재/빈값/권한없음/정상 | 5 케이스 | ✅ |
| `test_upload_use_case.py` | KB없음/쓰기권한없음/위임 인자검증(collection_name·extra_metadata)/청크옵션 | 4 케이스 | ✅ |
| `test_extra_metadata.py` | Qdrant·ES 전파, 미지정 회귀가드, 고정키 우선 | 4 케이스 | ✅ |
| `test_knowledge_base_router.py` | CRUD 201/409/404/403/422, 업로드 200+kb_id | 전량 | ✅ |
| `test_admin_collection_router.py` | 일반 403, ADMIN 201, 기본 PUBLIC, 중복 409 | 4 케이스 | ✅ |

---

## 5. 알려진 의도적 편차 (감점 제외 — 확인 완료)

| 항목 | 설계 근거 | 구현 위치 | 확인 |
|------|-----------|-----------|:----:|
| create의 "not found" ValueError → 404 아닌 422 | §7.1 "create는 404 없음" | `knowledge_base_router.py:143-150` | ✅ 명세대로 |
| `find_all_active` 인터페이스 추가 | §6.1 "ADMIN이면 전체 active" 구현 필요 | `interfaces.py:20-22`, `use_case.py:77-78` | ✅ 요구 구현 |
| D10/D11/D12 미구현 | 이연 결정 | 해당 없음 | ✅ 정상 |

---

## 6. Gap 목록 (실제 발견 — 모두 Low)

### 🔵 Low (외형/문서 표기 — 기능 영향 없음)

| # | 심각도 | 항목 | Design 근거 | 구현 | 설명 |
|---|:------:|------|-------------|------|------|
| G1 | Low | 제어문자 정규식 범위 초과 | §5.2 `\x00-\x1f` 금지 | `policy.py:12` `[\x00-\x1f\x7f]` | 구현이 DEL(`\x7f`)까지 추가 거부. 설계보다 **더 엄격**(개선 방향) — 결함 아님. 문서 동기화 시 §5.2에 `\x7f` 명시 권장 |
| G2 | Low | `create()` 시그니처 형태 | §6.1 의사코드 `create(req, user, request_id)` | `use_case.py:33-42` 명시적 kwargs(name/collection_name/scope/…) | req 객체 대신 개별 인자. 기능 동일, 라우터가 body 필드를 그대로 전달 — 실질 갭 아님 |
| G3 | Low | POST 경로 표기 | §7.1 표 Path `/` | `knowledge_base_router.py:117` `@router.post("")` | prefix+"" → canonical `/api/v1/knowledge-bases`(trailing slash 없음). 테스트도 동일 경로로 통과. 라우팅 정상 |
| G4 | Low | 업로드 응답에 `chunking_config` 미포함 | §7.1 "기존 UnifiedUploadResponse 필드 + …" | `KbUploadResponse`(`:74-85`) | document_id/pages/chunk_count/qdrant/es/status는 반환하나 chunking_config는 생략. 핵심 필드 충족, 부가정보 누락 — 필요 시 추가 |

> High/Medium 갭: **0건**. 위 4건은 모두 코드 수정 없이 수용 가능하거나 문서 동기화 대상.

---

## 7. 아키텍처·컨벤션 준수

| 항목 | 근거 규칙 | 확인 |
|------|-----------|:----:|
| Thin DDD 레이어 분리 | domain은 LangChain/DB 무참조 | `domain/knowledge_base/*` 순수(auth·collection.permission_schemas만 import) ✅ |
| 정책 domain 배치 | NFR-02 | `KnowledgeBasePolicy` domain ✅ |
| DB 세션 단일화 | `docs/rules/db-session.md`, NFR-06 | `kb_upload_factory`가 `unified_upload_factory(session)`로 동일 세션 조립(`main.py:2574`) ✅ |
| Repository commit/rollback 금지 | 금지 규칙 | `repository.py` flush만, commit 없음 ✅ |
| FK 콜레이션 명시 금지(errno 3780) | V037 선례 | `V040` CHARSET/COLLATE 미지정, `ENGINE=InnoDB`만 ✅ |
| additive-only 회귀 0 | NFR-01 | extra_metadata 기본 빈 dict, `test_extra_metadata.py` 회귀 가드 존재 ✅ |
| 로깅(print 금지, request_id) | LOG-001, NFR-05 | 전 UseCase `logger.info(..., request_id=...)` ✅ |

---

## 8. 권고 (Recommended Actions)

### 즉시 조치
- 없음 (기능/구조 갭 없음).

### 문서 동기화 (선택)
1. Design §5.2 제어문자 범위를 `\x00-\x1f\x7f`로 갱신 (G1 — 구현이 더 엄격).
2. Design §6.1 `create` 시그니처를 실제 kwargs 형태로 갱신 (G2).
3. (선택) `KbUploadResponse`에 `chunking_config` 필드 추가 여부 결정 (G4).

### 운영 체크리스트 (Design §6.5 운영 노트 — 코드 갭 아님)
- 기존 ES 인덱스에 `PUT /{index}/_mapping {"properties":{"kb_id":{"type":"keyword"},"kb_name":{"type":"keyword"}}}` 1회 실행 필요. 신규 인덱스는 `DOCUMENTS_INDEX_MAPPINGS` 자동 반영.

### 다음 단계
- Match Rate 98% (≥90%) → **Report 단계 진행 권장**: `/pdca report knowledge-base-scoping`
- 후속 로드맵(Plan §7): kb-rag-filter(payload index+검색 필터), kb-vector-cleanup(delete-by-filter).

---

## Related Documents
- Plan: [knowledge-base-scoping.plan.md](../01-plan/features/knowledge-base-scoping.plan.md)
- Design: [knowledge-base-scoping.design.md](../02-design/features/knowledge-base-scoping.design.md)
