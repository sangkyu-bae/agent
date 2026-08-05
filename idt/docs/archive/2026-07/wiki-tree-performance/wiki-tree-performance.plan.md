# Wiki Tree Performance Planning Document

> **Summary**: `/api/v1/wiki/tree`(및 wiki 전 엔드포인트)가 매 요청 5~7초 걸리는 병목 수정 — 원인은 쿼리가 아니라 **per-request DI에서 `OpenAIEmbedding` + `AsyncQdrantClient`를 요청마다 새로 생성**하는 것(실측 확정). 앱 수명 싱글턴 재사용으로 전환하고, 인증 전에 무거운 DI가 실행되는 의존성 선언 순서도 교정한다
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-29
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `/api/v1/wiki/tree` 호출이 매번 5~7초. 실측 결과 SQL·인덱스 문제가 아니라(쿼리 3~45ms), wiki 계열 DI 팩토리(`main.py create_wiki_factories._make_repo`)가 **요청마다** `OpenAIEmbeddings`(~2.8s)+`AsyncQdrantClient`(~3.3s, 버전체크 HTTP 포함)를 새로 생성하는 것이 원인. MySQL만 쓰는 /tree도 벡터 클라이언트 생성비를 전액 지불하고, 생성된 클라이언트는 닫히지 않고 누수됨 |
| **Solution** | ① 임베딩·Qdrant 클라이언트·벡터스토어를 앱 수명 싱글턴으로 1회 생성해 4개 wiki 팩토리가 공유(동일 파일 `main.py:2366-2374`의 기존 선례 패턴) ② wiki_router 의존성 선언 순서 교정(인증 먼저 → 미인증 401이 DI 비용 없이 즉시 반환) ③ 회귀 테스트 + 응답시간 실측 |
| **Function/UX Effect** | 지식 트리(워크스페이스/지식 페이지) 로딩 6~7초 → 수백 ms 이내. wiki 목록·단건·리뷰 등 wiki API 전체가 동일하게 개선. 요청당 소켓/클라이언트 누수 중단 |
| **Core Value** | "무거운 외부 클라이언트는 앱 수명 1회 생성, 세션만 요청 스코프" 원칙을 wiki DI에 복원 — agent-run 경로(`_wiki_repo_builder`)는 이미 준수하며, 이탈자(create_wiki_factories)만 정렬하는 최소 수정 |

---

## 1. Overview

### 1.1 Purpose

`/api/v1/wiki/tree`를 포함한 wiki API 전체의 요청당 5~7초 지연을 제거한다.
병목은 엔드포인트 로직이 아니라 per-request DI의 무거운 클라이언트 생성이므로,
클라이언트를 앱 수명 싱글턴으로 승격하고 요청 스코프에는 DB 세션만 남긴다.

### 1.2 Background — 원인 실측 확정 (2026-07-29, 로컬 기동 서버 대상)

**증상 격리 (curl 실측)**:

| 요청 | 시간 | 의미 |
|------|------|------|
| `GET /health` | 8~40ms | 서버·이벤트 루프 정상 |
| `POST /auth/login` (DB 조회+해시검증) | 27~180ms | MySQL 세션·풀 정상 |
| `GET /api/v1/agents` (무토큰 401) | 20ms | 인증이 먼저 해석되는 라우트는 빠름 |
| `GET /api/v1/wiki/tree` (무토큰 **401**) | **6.3~7.4s** | 핸들러·DB 실행 전인데 이미 느림 |
| `GET /api/v1/wiki`, `/api/v1/wiki/{id}` (무토큰 401) | 5.8~7.0s | wiki 팩토리 공유 라우트 전부 동일 |

무토큰 401에서도 6~7초 = 병목은 인증보다 **먼저 해석되는 `Depends(get_query_use_case)`**
(FastAPI는 파라미터 선언 순서대로 의존성을 해석하며, `wiki_router.py:116-119`는
use_case가 `_user`보다 앞임). 느린 요청 중 `/health`는 정상(이벤트 루프 비블로킹) —
sync 팩토리는 threadpool에서 실행되므로 서버 전체는 멀쩡하고 해당 요청만 느리다.

**병목 구간 분해 (생성자 단독 실측)**:

`create_wiki_factories._make_repo`(`main.py:3514-3530`)는 **요청마다**
`OpenAIEmbedding` → `AsyncQdrantClient` → `QdrantVectorStore`를 새로 생성한다.

| 생성자 | 현 서버 인터프리터(시스템 Python 3.13) | 프로젝트 .venv |
|--------|------------------------------------|---------------|
| `OpenAIEmbeddings()` | **~2.8s 매회** | 최초 2.7s, 이후 ~0.12s |
| `AsyncQdrantClient()` | **~3.3s 매회** | 최초 0.3s, 이후 ~0.10s |
| 합계 (요청당) | **~6.1s** ← 관측된 6~7s와 일치 | ~0.2s |
| (참고) tree SELECT 자체 | — | 3~45ms (인덱스 `idx_wiki_agent_path` 존재) |

**원인은 2중**:

1. **코드 결함(근본)** — wiki 4개 팩토리(query/distill/review/human_write)가 요청마다
   무거운 클라이언트를 생성. MySQL만 쓰는 `/tree`·목록·단건 조회도 전액 지불.
   생성된 `AsyncQdrantClient`(httpx AsyncClient 내장)와 OpenAI sync/async 클라이언트는
   **닫히지 않고 요청마다 누수**. `review_factory` 경유의 `_article_repo_builder`
   (`main.py:3477-3490`)도 동일 패턴.
2. **환경 증폭기** — 현재 로컬 서버가 `.venv`가 아닌 **시스템 Python 3.13**
   (`Python313\python.exe -m uvicorn src.api.main:app`, 패키지 별도 설치본)으로 기동돼
   생성자 비용이 회당 ~6.1초로 증폭. `.venv`에서는 ~0.2초라 그동안 티가 덜 났을 뿐,
   per-request 생성 자체가 낭비인 점은 동일하다.

**부수 관찰**: qdrant-client(venv 1.17.1 / 시스템 1.16.2)와 Qdrant 서버(1.11.0)의
버전 비호환 경고가 **클라이언트 생성마다** 출력되고, 생성마다 서버 버전체크 HTTP 왕복이
발생한다(싱글턴화 시 1회로 축소; 버전 정렬은 후속 항목).

### 1.3 Related Documents / 선례

- **준수 선례(같은 파일)**: `main.py:2365-2383` — `_wiki_embedding`·`_wiki_qdrant`를
  모듈 수명 1회 생성 후 `_wiki_repo_builder(session)`이 세션만 바인딩 (agent-run 경로)
- DB 세션 규칙: `docs/rules/db-session.md` (요청 1건 = 세션 1개 — 세션은 현행 유지)
- wiki API 신설 이력: wiki-user-facing (tree 라우트 선언 순서 계약),
  wiki-folder-summaries (review_factory 팬아웃 배선)

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. wiki DI 싱글턴화**: `create_wiki_factories` 내 임베딩·Qdrant 클라이언트·
      벡터스토어를 앱 수명 1회 생성으로 승격, 4개 팩토리는 세션만 요청 스코프로 바인딩.
      `_article_repo_builder`(`main.py:3477`)도 동일 정렬 (2365행 선례 패턴과 통일 —
      기존 `_wiki_embedding`/`_wiki_qdrant` 인스턴스 공유 여부는 Design에서 확정)
- [ ] **S2. 의존성 순서 교정**: `wiki_router.py`의 GET /tree·목록·단건 등에서
      `_user: User = Depends(get_current_user)`를 use_case보다 **앞에** 선언 —
      미인증 요청이 DI 비용 없이 401 (agents 라우터와 동일 관례)
- [ ] **S3. 회귀 테스트**: ① 팩토리가 요청 반복 시 임베딩/Qdrant 클라이언트를 재생성하지
      않음(생성 횟수 단언) ② wiki 조회/작성/리뷰 기존 테스트 무회귀
- [ ] **S4. E2E 실측**: 로컬 기동 후 `/api/v1/wiki/tree` 응답시간 측정 —
      p50 < 500ms (.venv 기동 기준)
- [ ] **S5. 기동 가이드 명기**: 로컬 서버는 `.venv`로 기동해야 함을 확인·안내
      (`idt/CLAUDE.md 4-3`의 uvicorn 명령이 venv 활성화를 전제함을 재확인 — 문서 수정이
      필요하면 보고만, SoT 규칙 준수)

### 2.2 Out of Scope

- tree SQL·인덱스 최적화 (실측 3~45ms — 병목 아님), 응답 캐싱
- qdrant-client ↔ Qdrant 서버 버전 정렬 / `check_compatibility` 설정 변경
  (후속 항목으로 기록 — 싱글턴화만으로 요청 경로에서는 제거됨)
- `/tree` 전용 경량 레포(벡터 의존 없는 read-only 레포 분리) — 싱글턴화로 충분하면
  YAGNI, Design에서 재평가
- agent-run 경로(`_wiki_repo_builder`)·타 도메인 DI 구조 변경
- 프론트엔드, API 계약, DB 마이그레이션 (전부 무변경)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | wiki 4개 use case 팩토리가 임베딩·Qdrant 클라이언트·벡터스토어를 프로세스 수명 동안 1회만 생성하고 공유한다 (요청당 신규 생성 0) | High | Pending |
| FR-02 | `/api/v1/wiki/tree` 응답시간 p50 < 500ms (.venv 로컬, 데이터 현행 규모) — 개선 전 6~7s 대비 실측 비교 | High | Pending |
| FR-03 | 미인증 요청은 use case DI 실행 없이 401을 즉시 반환한다 (wiki_router 의존성 선언 순서: 인증 → use_case) | Medium | Pending |
| FR-04 | wiki CRUD·리뷰·트리·검색 경로의 기능 동작 불변 (기존 테스트 무회귀) | High | Pending |
| FR-05 | 요청 반복 시 Qdrant/OpenAI 클라이언트 인스턴스가 누적 생성되지 않는다 (누수 중단 — 생성 횟수 단언으로 검증) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 성능 | tree/목록/단건 p50 < 500ms, 401 경로 < 100ms | curl `time_total` 반복 실측 (개선 전 수치와 비교표) |
| 동시성 안전 | 공유 `AsyncQdrantClient`·임베딩 클라이언트가 동시 요청에서 안전 (2365행 선례가 이미 공유 중 — Design에서 근거 명시) | 코드 근거 + 병행 요청 실측 |
| 회귀 안전 | 기존 pytest 무회귀 (사전 실패분 제외, Windows 격리 실행 관례) | pytest 격리 실행 |
| 아키텍처 | DI 조립(main.py)·router 계층 내 수정, 레이어 이동 없음 | verify-architecture 스킬 |
| TDD | 테스트 선행 (생성 횟수 단언 Red 확인 후 구현) | verify-tdd 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 개선 전/후 실측 비교표 확보: tree 6~7s → < 500ms (동일 조건)
- [ ] 팩토리 반복 호출 시 클라이언트 생성 횟수 1회 단언 테스트 통과 (Red 선행 확인)
- [ ] 무토큰 401 실측 < 100ms (S2)
- [ ] 기존 wiki 관련 테스트 전체 무회귀

### 4.2 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, config 하드코딩 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 공유 `AsyncQdrantClient`의 이벤트 루프 바인딩 — 테스트가 루프를 재생성하는 환경(Windows pytest flakiness 이력)에서 앱 수명 클라이언트가 stale 루프를 참조할 가능성 | Medium | Medium | 선례(`main.py:2367`)가 동일 방식으로 이미 운용 중임을 근거로 삼되, 생성 시점을 `create_app()` 내부(모듈 import 시점 아님)로 확정 — Design에서 결정. 테스트는 앱 팩토리 단위로 생성 |
| 싱글턴 임베딩 클라이언트 공유가 wiki 쓰기 경로(색인 `_index_vector`) 동작에 영향 | Low | Low | 클라이언트는 무상태(설정+커넥션 풀). 쓰기 경로 기존 테스트로 회귀 확인 |
| 의존성 순서 변경(S2)이 기존 테스트의 override 방식과 충돌 | Low | Low | 파라미터 순서만 변경, override 키(함수 객체)는 불변. wiki API 테스트로 확인 |
| `.venv` 기동으로 바꿔도 남는 ~0.2s/요청(venv에서의 생성비)이 재발 오인 유발 | Low | Medium | S1이 근본 해결이므로 환경 무관 0에 수렴 — 성능 단언은 S1 이후 수치로 |
| qdrant 버전 비호환(1.16/1.17 ↔ 서버 1.11)이 언젠가 실제 API 불일치로 표면화 | Medium | Low | 본 건에서는 관측만 기록, 버전 정렬을 후속 항목으로 명시 (Out of Scope) |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation | 기존 프로젝트 구조 (Thin DDD) | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 병목 해소 방식 | per-request 생성 유지+캐싱 / 앱 수명 싱글턴 / tree 전용 경량 레포 분리 | 앱 수명 싱글턴 (S1) | 같은 파일 2365행에 동일 패턴 선례 존재 — 최소 수정으로 전 wiki 엔드포인트 일괄 해결. 경량 레포 분리는 싱글턴화 후에도 필요성이 남으면 후속(YAGNI) |
| 싱글턴 인스턴스 출처 | 2365행 기존 `_wiki_embedding`/`_wiki_qdrant` 공유 / create_wiki_factories 자체 1회 생성 | Design에서 확정 | 공유 시 인스턴스 수 최소화 vs 조립 함수 간 결합 증가 — 생성 시점(create_app 내부)과 함께 결정 |
| 인증·DI 순서 | 현행 유지 / 인증 먼저 | 인증 먼저 (S2) | 미인증 요청이 무거운 DI를 트리거하는 것은 비용·방어 양면에서 불리. agents 라우터가 이미 인증 먼저 관례 |

### 6.3 변경 대상 파일 (예상)

```
idt/src/
├── api/main.py                       # S1: create_wiki_factories·_article_repo_builder 싱글턴화
├── api/routes/wiki_router.py         # S2: 의존성 선언 순서 (인증 → use_case)
└── tests/
    └── api/ 또는 tests/application/wiki/
        └── (신규) wiki DI 생성 횟수·순서 회귀 테스트   # S3: FR-01/03/05
```

> 도메인·application 레이어 로직은 무변경 — 수정은 DI 조립부와 라우터 시그니처에 한정.

---

## 7. Convention Prerequisites

- [x] 검증 스킬 존재: verify-architecture, verify-tdd
- [x] 백엔드 테스트 격리 실행 관례 (Windows 이벤트 루프 flakiness — 메모리 기록)
- 환경변수·마이그레이션·API 계약 변경 **없음** (프론트 동기화 불필요)
- 로컬 서버 기동은 `.venv` 인터프리터 사용 (S5 — 시스템 Python 기동이 이번 증폭의 절반)

---

## 8. Implementation Guide

### 8.1 구현 순서

```
1. FR-01/05  생성 횟수 단언 테스트 먼저 (Red) → create_wiki_factories 싱글턴화 (Green)
             → _article_repo_builder 동일 정렬
2. FR-03     무토큰 401 경로 테스트 → wiki_router 의존성 순서 교정
3. FR-04     기존 wiki 테스트 격리 실행 무회귀 확인
4. FR-02     .venv로 서버 기동 → 개선 전/후 실측 비교표 작성 (tree·목록·401 경로)
```

### 8.2 검증 자료 (본 계획 수립 시 실측 로그)

- 무토큰 401 실측: tree 7.37s/6.35s/7.13s, 목록 7.01s/5.83s, 단건 6.13s
  ↔ /health 8~40ms, login 27~180ms, agents 401 20ms
- 생성자 단독 실측: 시스템 Py3.13 — `OpenAIEmbeddings()` 2.7~2.9s·`AsyncQdrantClient()`
  3.2~3.6s 매회 / .venv — 각 ~0.12s·~0.10s (warm)
- 재현 스크립트: threadpool 경유 요청 재현 벤치 (세션+begin·생성자·SELECT 구간 분해,
  warm 요청 합계 ~0.25s → 서버 관측치와의 차이로 인터프리터 문제 특정)
- 실행 중 서버 확인: `Python313\python.exe -m uvicorn src.api.main:app` (venv 아님)

---

## 9. Next Steps

1. [ ] Write design document (`/pdca design wiki-tree-performance`) —
       싱글턴 생성 시점(create_app 내부 vs 모듈 수명)·2365행 인스턴스 공유 여부 확정
2. [ ] 구현 (TDD)
3. [ ] Gap 분석 (`/pdca analyze wiki-tree-performance`)
4. [ ] (후속 기록) qdrant-client ↔ 서버 1.11.0 버전 정렬

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-29 | Initial draft — curl 구간 격리 + 생성자 단독 실측 + 재현 벤치로 원인 확정 | 배상규 |
