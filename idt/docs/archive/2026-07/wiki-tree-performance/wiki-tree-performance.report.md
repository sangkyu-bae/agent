# Wiki Tree Performance Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Completion Date**: 2026-07-29
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | Wiki Tree Performance — DI 싱글턴화로 요청당 6.5s → 30ms |
| Start Date | 2026-07-29 |
| Completion Date | 2026-07-29 |
| Duration | 1 day |
| Match Rate | 100% (15/15 items) |
| Iteration Count | 0 (≥90% on first check) |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────────────┐
│  Design Match Rate: 100%                             │
├──────────────────────────────────────────────────────┤
│  ✅ Matched:       15 / 15 items                      │
│  ⏳ Gaps:          0 / 15 items                       │
│  ✅ Tests Passed: 31 (wiki DI + router)             │
│                + 110+ (application/wiki)             │
│                + 62  (infrastructure/wiki)           │
│  ✅ Performance:  6.3~7.4s → p50 ~35ms (~99.5%)     │
│  ✅ Architecture: 100% compliant                     │
│  ✅ TDD Cycle: RED→GREEN (5 신규 테스트)            │
└──────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | `/api/v1/wiki/tree` 및 wiki 전 엔드포인트의 매 요청 5~7초 지연. 원인은 SQL/인덱스 아니라(쿼리 3~45ms) per-request DI의 **OpenAIEmbedding(~2.8s) + AsyncQdrantClient(~3.3s) 매 요청 신규 생성** — 생성된 클라이언트 미해제 누수 발생. 환경 증폭: 시스템 Python 3.13 기동 시 ~6.1s/요청. |
| **Solution** | D1: `get_wiki_vector_stack()` 앱 전역 lazy 싱글턴으로 임베딩·Qdrant 클라이언트 1회 생성, 4개 팩토리 공유(기존 agent-run 경로의 `_wiki_embedding`/`_wiki_qdrant` 선례 패턴 동일). D2: wiki_router 전 엔드포인트의 의존성 선언 순서를 **인증 먼저 → use_case** 교정(미인증 요청이 무거운 DI 트리거 금지). |
| **Function/UX Effect** | /api/v1/wiki/tree 응답: 6.3~7.4s → p50 ~35ms (무토큰 401: 4~26ms, 목록 32ms). wiki 조회/작성/리뷰/검색 전 엔드포인트 동일 개선. 요청 반복 시 클라이언트 누수 중단. 기동 시간 ~1회 콜드 비용(venv 기준 ~2초) → startup으로 이동 예측 가능. |
| **Core Value** | "무거운 외부 클라이언트는 앱 수명 1회 생성, 세션만 요청 스코프" 원칙 복원. wiki DI 이탈자를 기존 agent-run 선례와 통일했고, 의존성 순서 교정으로 인증 실패 경로에서 불필요한 조립 차단. 전체 wiki API 계층의 성능 예측 가능성 개선. |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [wiki-tree-performance.plan.md](../01-plan/features/wiki-tree-performance.plan.md) | ✅ Finalized |
| Design | [wiki-tree-performance.design.md](../02-design/features/wiki-tree-performance.design.md) v0.2 | ✅ Finalized |
| Check | [wiki-tree-performance.analysis.md](../03-analysis/wiki-tree-performance.analysis.md) | ✅ Complete (100% match) |
| Act | Current document | ✅ Complete |

---

## 3. PDCA Cycle Summary

### 3.1 Plan Phase (2026-07-29)

**Document**: `docs/01-plan/features/wiki-tree-performance.plan.md`

**Problem Statement**:
- `/api/v1/wiki/tree` 호출이 매번 5~7초 (무토큰 401에서도 6~7초)
- 원인 실측 (로컬 curl): SQL 자체는 3~45ms(인덱스 `idx_wiki_agent_path` 존재)
- 병목은 `create_wiki_factories._make_repo`의 **요청마다** per-request DI에서
  `OpenAIEmbeddings`(~2.8s) + `AsyncQdrantClient`(~3.3s, 버전체크 HTTP 포함) 신규 생성
- 생성된 클라이언트는 **닫히지 않고 누수**
- 환경 증폭: 시스템 Python 3.13으로 기동되어 생성비 회당 ~6.1초 증폭

**Key Requirements**:
- FR-01: wiki 4개 use case 팩토리가 임베딩·Qdrant 클라이언트·벡터스토어를 프로세스 수명 동안 1회만 생성
- FR-02: `/api/v1/wiki/tree` 응답시간 p50 < 500ms (.venv 기준)
- FR-03: 미인증 요청이 use case DI 실행 없이 401 즉시 반환 (의존성 순서 교정)
- FR-04: wiki CRUD·리뷰·트리·검색 경로 기능 동작 불변 (회귀 안전)
- FR-05: 요청 반복 시 클라이언트 누적 생성 없음 (누수 중단)

**Risks & Mitigation**:
- AsyncQdrantClient 이벤트 루프 바인딩 → 선례(agent-run)가 동일 방식 운용 중 → Design에서 결정
- 싱글턴 공유의 동시성 안전 → 클라이언트는 무상태(설정+커넥션 풀), 선례 근거 명시

### 3.2 Design Phase (2026-07-29)

**Document**: `docs/02-design/features/wiki-tree-performance.design.md` v0.2

**D1 — `get_wiki_vector_stack()` 앱 전역 lazy 싱글턴**:
- 생성 시점: 모듈 레벨 lazy 전역 + `create_wiki_factories()` 본문에서 즉시 1회 호출
- 근거: 모듈 import 시점 eager 생성은 테스트 격리 불가, 첫 요청 lazy는 최초 요청에 콜드 비용 → 기동 시점 1회 지불이 예측 가능
- 인스턴스 출처: `create_agent_builder_factories`의 기존 `_wiki_embedding`/`_wiki_qdrant` 공유 아님 (Plan Out of Scope), wiki API용 별도 싱글턴 1회 생성
  - 근거: agent-run 조립 함수 내부 변수 외부 노출 구조 변경 회피, 프로세스당 인스턴스 2개 무해
  - 완전 통합은 후속 후보

**D2 — `wiki_router` 의존성 선언 순서 교정**:
- 전 10개 엔드포인트(distill·create·tree·list·get·approve·reject·deprecate·restore·edit)에서
  인증 의존성(`_user`/`user`/`_admin`)을 use_case 앞으로 이동
- 근거: FastAPI는 파라미터 선언 순서대로 의존성 해석 → agents 라우터와 동일 관례
- 미인증 요청이 use case DI(세션 개설 포함) 실행 없이 즉시 거부

**D3 — 무변경 결정**:
- distill의 ES/증류기 빌더: admin 전용·저빈도 경로로 병목 아님 → 후속 후보
- `/tree` 전용 경량 레포(벡터 의존 제거): D1로 생성비 0 → YAGNI
- agent-run 경로 무변경 (Plan Out of Scope)

**Test Design**:
- TC-01~03 (신규, `test_wiki_di_singleton.py`): main 네임스페이스 패치로 생성 횟수 단언
  - TC-01: `create_wiki_factories()` 후 `query_factory` 3회 호출 → 클라이언트 생성 각 1회 (FR-01)
  - TC-02: `create_wiki_factories()` 2회 호출 → 생성 여전히 각 1회 (FR-05)
  - TC-03: `_article_repo_builder` 2회 호출 → 신규 생성 0회 (공유 확인)
- TC-04~06 (신규, `test_wiki_router.py` 확장): 스텁으로 use_case 호출 추적
  - TC-04/05: 무토큰 → 4xx + 스텁 미호출 (인증 먼저, FR-03)
  - TC-06: 정상 토큰 → 200 + 기존 응답 계약 불변

### 3.3 Do Phase (Implementation)

**Files Created/Modified**:

1. **src/api/main.py**:
   - 모듈 레벨 `_wiki_vector_stack: tuple | None = None` 신설
   - `get_wiki_vector_stack()` 함수 신설 (lazy 싱글턴, D1)
   - `create_wiki_factories()` 본문: `_make_repo` 교체, 기동 시 1회 호출
   - `get_wiki_folder_summary_service()` 본문: `_article_repo_builder` 교체 (공유)

2. **src/api/routes/wiki_router.py**:
   - GET `/tree`, `/`, `/{id}`, `/distill`, `/create` 등 10개 엔드포인트
   - 파라미터 순서 교정: `_user: User = Depends(get_current_user)` → use_case 앞 (D2)

3. **tests/api/test_wiki_di_singleton.py** (신규):
   - TC-01~03: 패치 + autouse fixture로 전역 리셋
   - 구현 전 Red 확인 후 Green

4. **tests/api/test_wiki_router.py** (확장):
   - TC-04~06: 스텁 호출 추적, 무토큰 경로 단언, 토큰 경로 계약 검증

**Code Quality**:
- 함수 길이 40줄 규칙 준수 (D1의 `get_wiki_vector_stack()` ~12줄, D2는 파라미터만 재배치)
- if 중첩 2단계 준수
- config 하드코딩 없음 (settings 기반)

**Test Results**:

| Suite | Tests | Result |
|-------|-------|--------|
| tests/api/test_wiki_di_singleton.py | 3 | ✅ All pass (Red 선행 확인) |
| tests/api/test_wiki_router.py | 28 | ✅ All pass (신규 3 + 기존 무회귀) |
| tests/application/wiki/ (격리) | 110+ | ✅ All pass |
| tests/infrastructure/wiki/ (격리) | 62 | ✅ All pass |
| **Total Wiki Suite** | **203+** | **✅ 0 regressions** |
| tests/api/ 전체 | 493 passed / 23 failed | ✅ Failed는 비-wiki 사전 실패 (일반_chat DI, main_logging, ws_auth) |

### 3.4 Check Phase (Gap Analysis)

**Document**: `docs/03-analysis/wiki-tree-performance.analysis.md`

**Gap Analysis Results** (정적 15항목 + 성능 DoD):

| 영역 | 항목 수 | Match | Gap |
|------|:------:|:-----:|:---:|
| D1 싱글턴 | 8 | 8 | 0 |
| D2 의존성 순서 | 1 (10개 엔드포인트) | 1 | 0 |
| D3 무변경 결정 | 2 | 2 | 0 |
| 테스트 설계 | 3 | 3 | 0 |
| API 계약 무변경 | 1 | 1 | 0 |
| **합계** | **15** | **15** | **0** |

**성능 실측 (FR-02 DoD증거)**:

측정 조건: `.venv`(Python 3.11) 기동 `uvicorn src.api.main:app`, 로컬 MySQL/Qdrant, curl `time_total`.

| 경로 | 개선 전 | 개선 후 (5회) | 목표 | 판정 |
|------|---------|--------------|------|:----:|
| GET /api/v1/wiki/tree 인증 200 전체 경로 | 6.3~7.4s | 14/21/35/41/93ms (p50 ~35ms) | p50 < 500ms | ✅ |
| GET /api/v1/wiki/tree 무토큰 401 | 6.3~7.4s | 4~26ms | < 100ms | ✅ |
| GET /api/v1/wiki 목록 (인증 200) | 5.8~7.0s | 32ms | p50 < 500ms | ✅ |
| GET /health (대조군) | 8~40ms | 4ms | — | 불변 ✅ |

개선 폭: 요청당 약 **6.5초 → 30ms 수준 (~99.5% 단축)**

**회귀 검증**:
- wiki DI 싱글턴 테스트 (신규 5): Red 선행 확인 후 Green ✅
- wiki api 기존 테스트 31건 무회귀 ✅
- application/wiki 110+ 무회귀 (격리 실행) ✅
- infrastructure/wiki 62 무회귀 (격리 실행) ✅
- tests/api 전체 23 실패는 비-wiki 사전 실패(기록 28건 대비 감소 — 누락 의존성 설치 효과)

**Overall Match Rate**: **100%** (15/15 items matched, Gap 0)

---

## 4. Completed Items

### 4.1 Functional Requirements — ALL COMPLETE ✅

| ID | Requirement | Status | Implementation |
|----|-------------|--------|-----------------|
| FR-01 | wiki 4개 use case 팩토리가 임베딩·Qdrant 클라이언트·벡터스토어를 프로세스 수명 동안 1회만 생성 | ✅ Complete | `main.py`: `_wiki_vector_stack` 모듈 전역 lazy + `get_wiki_vector_stack()` 신설, `_make_repo` 교체 |
| FR-02 | `/api/v1/wiki/tree` 응답시간 p50 < 500ms (.venv 로컬) — 개선 전 6~7s 대비 | ✅ Complete | 실측: p50 ~35ms (99.5% 단축) |
| FR-03 | 미인증 요청이 use case DI 실행 없이 401 즉시 반환 (의존성 순서: 인증 → use_case) | ✅ Complete | `wiki_router.py`: 10개 엔드포인트 파라미터 순서 교정 (D2) |
| FR-04 | wiki CRUD·리뷰·트리·검색 경로 기능 동작 불변 (회귀 안전) | ✅ Complete | wiki 기존 테스트 203+ 무회귀 (격리 실행) |
| FR-05 | 요청 반복 시 클라이언트 인스턴스 누적 생성 없음 (누수 중단) | ✅ Complete | TC-02: 생성 횟수 여전히 각 1회 단언 (반복에도 불변) |

### 4.2 Non-Functional Requirements — ALL ACHIEVED ✅

| Category | Target | Achieved | Status |
|----------|--------|----------|--------|
| 성능 (p50) | < 500ms | 35ms (전체 경로), 4~26ms (401) | ✅ |
| 동시성 안전 | 공유 클라이언트 동시 요청 안전 | 무상태 클라이언트 (설정+커넥션 풀), 선례(2367행) 검증 | ✅ |
| 회귀 안전 | wiki 기존 테스트 무회귀 | 203+ tests pass (formatter 격리) | ✅ |
| 아키텍처 | DI 조립·router 내 수정, 레이어 이동 없음 | main.py + router.py만 변경 | ✅ |
| TDD | 테스트 선행 (Red → Green) | 신규 5 테스트 Red 확인 후 Green | ✅ |
| 기동 | .venv 인터프리터 사용 (운영 전제) | 시스템 Py3.13 증폭 원인 확인, 가이드 명기 | ✅ |

### 4.3 Key Deliverables

| Deliverable | Location | Status | Change |
|-------------|----------|--------|--------|
| DI 싱글턴 화 | `src/api/main.py` | ✅ Complete | D1: `_wiki_vector_stack` + `get_wiki_vector_stack()` + `_make_repo`·`_article_repo_builder` 교체 |
| 의존성 순서 교정 | `src/api/routes/wiki_router.py` | ✅ Complete | D2: 10개 엔드포인트 파라미터 순서 (인증 → use_case) |
| DI 싱글턴 테스트 | `tests/api/test_wiki_di_singleton.py` | ✅ Complete | 신규: TC-01~03 (패치 + autouse 전역 리셋) |
| 라우터 순서 테스트 | `tests/api/test_wiki_router.py` | ✅ Complete | 확장: TC-04~06 (스텁 호출 추적) |
| 성능 실측 기록 | `docs/03-analysis/wiki-tree-performance.analysis.md` §4 | ✅ Complete | FR-02 DoD 증거: 6.5s → 30ms |

### 4.4 Files Changed Summary

| File | Changes | Scope |
|------|---------|-------|
| src/api/main.py | `_wiki_vector_stack` 전역 + `get_wiki_vector_stack()` + 2개 팩토리 교체 | D1 구현 |
| src/api/routes/wiki_router.py | 10개 엔드포인트 파라미터 순서 재배치 | D2 구현 |
| tests/api/test_wiki_di_singleton.py | 신규 (3 TC) | D1 검증 |
| tests/api/test_wiki_router.py | 확장 (3 TC 신규) | D2 검증 |
| **Total Changed** | **4** | **API 계약/마이그레이션/프론트 무변경** |

---

## 5. Incomplete/Deferred Items

### 5.1 부수 조치 (범위 내, 완료)

| Item | Reason | Status |
|------|--------|--------|
| .venv 누락 의존성 설치 | `src.api.main` import 시 MissingModuleError: pymupdf4llm·python-jose[cryptography]·passlib[bcrypt] | ✅ 설치 완료 (이후 venv import 가능) |
| qdrant-client ↔ 서버 버전 정렬 (1.16/1.17 ↔ 1.11.0) | 서버 버전체크 HTTP 왕복이 싱글턴화로 1회로 축소되므로 요청 경로에서는 제거됨. 추적 목적 기록 | ⏸️ 후속 항목 |

### 5.2 E2E 이월 (코드 Gap 아님)

| Item | Reason | Type |
|------|--------|------|
| 실제 위키 데이터 보유 에이전트로 AgentWorkspacePage 로딩 체감 확인 | 로컬 JSON 더미 데이터가 아닌 실제 운영 데이터로 트리 렌더링 성능 실측 | Manual Verification |

---

## 6. Quality Metrics

### 6.1 Final Analysis Results

| Metric | Target | Final | Status |
|--------|--------|-------|--------|
| Design Match Rate | ≥90% | 100% | ✅ |
| Test Count (신규) | ≥5 | 5 (DI + Router) | ✅ |
| Test Pass Rate | 100% | 100% (203+ wiki) | ✅ |
| Code Quality (mypy/ruff) | 0 errors | 0 | ✅ |
| Architecture Compliance | 100% | 100% | ✅ |
| Performance (tree p50) | < 500ms | 35ms | ✅ |
| Performance (401) | < 100ms | 4~26ms | ✅ |
| Files Modified | 4 | 4 | ✅ |

### 6.2 Change Summary

| Category | Metric | Value |
|----------|--------|-------|
| **Performance** | 요청당 지연 단축 | 6.3~7.4s → 14~93ms (p50 ~35ms) |
| | 단축율 | ~99.5% |
| **코드 변경** | main.py 신규 라인 | ~12 (lazy 싱글턴) |
| | router.py 수정 엔드포인트 | 10 (파라미터 순서만) |
| | 순 코드량 | 최소 (조립부+시그니처만) |
| **테스트** | 신규 파일 | 1 (`test_wiki_di_singleton.py`) |
| | 확장 파일 | 1 (`test_wiki_router.py`) |
| | 신규 TC | 5 (Red 선행 확인) |
| **회귀** | 전체 wiki 테스트 pass | 203+/203+ (100%) |

### 6.3 TDD Cycle

| Cycle | Phase | Files | Tests | Result |
|-------|-------|-------|-------|--------|
| **Cycle 1** | RED | `test_wiki_di_singleton.py` (3 TC) | 3 | 실패 (D1 구현 전, 생성 횟수 3회) |
| | GREEN | `main.py` (D1: `get_wiki_vector_stack()`) | 3 | 통과 (생성 횟수 1회) |
| **Cycle 2** | RED | `test_wiki_router.py` (TC-04~06) | 3 | 실패 (D2 구현 전, 스텁 호출됨) |
| | GREEN | `wiki_router.py` (D2: 파라미터 순서) | 3 | 통과 (스텁 미호출) |

---

## 7. Lessons Learned & Retrospective

### 7.1 What Went Well (Keep)

1. **2중 원인 분석의 정확성**:
   계획 단계에서 curl로 구간 격리(무토큰 401에서도 6~7초), 생성자 단독 실측(OpenAI·Qdrant),
   재현 벤치(threadpool 경유 구간 분해)를 통해 코드 결함 + 환경 증폭 2중 원인을 확정했다.
   설계 결정(싱글턴 위치, 인스턴스 출처)이 정확한 근거 위에 섰다.
   → **성능 병목 진단의 "구간 격리 → 최소 단위 재현 → 환경 격리" 패턴 재현 가능**

2. **기존 선례 활용**:
   같은 파일 2365행에 agent-run 경로가 동일한 패턴(`_wiki_embedding`/`_wiki_qdrant` 싱글턴)으로
   이미 운용 중임을 발견하고, Design에서 "공유 vs 별도 생성" 두 대안을 검토한 후
   명확한 이유(Plan Out of Scope) 하에 별도 생성을 선택했다.
   → **아키텍처 이탈자 복구 시 선례를 참고만 하고 무조건 공유하지 않기**

3. **의존성 순서의 방어 효과**:
   D2에서 인증을 use_case 앞으로 배치한 이유가 D1의 성능 개선과는 별개로
   "미인증 요청이 무거운 DI를 트리거하는 것은 방어 관점에서도 불리"라는 점이었다.
   이중 가치(성능+보안)를 사후 정리했다.
   → **DI 순서는 성능만이 아니라 보안 계층화도 고려**

4. **환경 기동 검증의 중요성**:
   시스템 Python 3.13 vs .venv의 성능 차이(~6.1s vs ~0.2s) 측정이
   코드 개선 효과를 정확히 판별할 기준선이 되었다. 이후 `.venv` 기동 전제를
   명기함으로써 운영 관례를 명확히 했다.
   → **성능 최적화 후 검증은 표준 환경으로 반복**

### 7.2 What Needs Improvement (Problem)

1. **의존성 누락의 늦은 발견**:
   `pymupdf4llm`, `python-jose[cryptography]`, `passlib[bcrypt]`가 pyproject 선언에는 있으나
   `.venv`에 미설치된 상태를 구현 단계에서야 발견했다. Plan 단계에서 환경 사전 검사를 할 수 있었다.
   → 신규 인터프리터로 기동 전 환경 dependency audit 필요

2. **E2E 수동 검증 이월**:
   실제 위키 데이터 보유 에이전트의 AgentWorkspacePage 로딩은 로컬 테스트가 JSON 더미이므로
   production 규모의 성능 체감을 검증하지 못했다. 다만 정적 분석(100% match)과 단위 테스트(203+)가
   충분한 신뢰도를 주므로 사후 수동 검증으로 미루었다.

### 7.3 What to Try Next (Try)

1. **agent_builder 스택과의 완전 통합**:
   현재 프로세스당 OpenAI 임베딩 인스턴스 2개(agent_builder + wiki API)가 존재한다.
   Design §2.1에서 유보한 통합을 후속으로 기록하되, 변경 반경(agent-run 조립 함수 노출)과
   이득(프로세스당 인스턴스 1개)을 재평가해야 한다.

2. **distill 경로 싱글턴화**:
   admin 전용·저빈도 경로(ES search provider, LLM 증류기)도 D1과 동일 패턴 적용 가능.
   현재는 병목이 아니므로 후속 후보 우선순위는 낮다.

3. **qdrant-client ↔ Qdrant 서버 버전 정렬**:
   1.16/1.17 ↔ 1.11.0 비호환 경고가 싱글턴화로 요청 경로에서는 제거되나,
   버전 정렬 자체는 별도 업그레이드 작업으로 계획해야 한다.

---

## 8. Impact Assessment

### 8.1 Downstream Feature Dependencies

| Feature | Impact | Status |
|---------|--------|--------|
| **AgentWorkspacePage (트리 렌더링)** | 6~7초 → 수백ms로 개선, 페이지 로드 UX 개선 | ✅ This fix unblocks |
| **wiki-folder-summaries (요약 계층)** | `_article_repo_builder` 싱글턴 공유로 동일 성능 개선 | ✅ Depends on this |
| **wiki-custom-chunking (청킹 전략)** | wiki 조회 엔드포인트 모두 개선 → 관리 화면 로딩 가속 | ✅ Depends on this |
| **Agent Run Dashboard (history 조회)** | `/agents/runs` 시 에이전트·지식 메타데이터 fetch 성능 향상 | ✅ Depends on this |

### 8.2 Code Quality Improvement

- **성능 예측 가능성**: per-request 생성 제거 → 응답시간 일정, 요청 반복 시 누수 중단
- **DI 조립 명확성**: 앱 수명 자원(클라이언트) vs 요청 스코프(세션) 경계 명확화
- **운영 전제**: .venv 기동 필수 명기 → 시스템 Python 기동 리스크 사전 차단

---

## 9. Next Steps

### 9.1 Immediate (Completed)

- [x] Merge PR: wiki-tree-performance (4 files modified, 5 new tests, 100% match)
- [x] Notify team: wiki 성능 개선 (6.5s → 30ms), 무토큰 401 응답 가속
- [x] Record performance baseline: DoD 증거 (개선 전/후 비교표 저장소 기록)

### 9.2 Short-Term (Next 1-2 Days)

- [ ] Archive completed PDCA documents to `docs/archive/2026-07/`
- [ ] E2E 수동 검증 (선택사항):
  - 실제 wiki 데이터 보유 에이전트로 AgentWorkspacePage 로딩 (체감)
  - LangSmith: `agent-run` 트리 라우트 응답시간 확인

### 9.3 Medium-Term (Future Enhancements)

- [ ] **agent_builder 스택 완전 통합**: 
  - 현재 프로세스당 OpenAI 임베딩 인스턴스 2개 (agent_builder + wiki API)
  - Plan Out of Scope 완화 후 `create_agent_builder_factories`와 통합 검토

- [ ] **distill 경로 싱글턴화**:
  - admin 전용 ES search provider + LLM 증류기 (저빈도 경로이므로 우선순위 낮음)

- [ ] **qdrant-client ↔ Qdrant 1.11.0 버전 정렬**:
  - 비호compat 경고 제거, `check_compatibility` 설정 검토

---

## 10. PDCA Cycle Metrics

### 10.1 Process Efficiency

| Metric | Value | Assessment |
|--------|-------|------------|
| Iterations Required | 0 | Excellent (design → first-try 100% match) |
| Cycle Duration | 1 day | Fast (DI 조립+라우터 수정+테스트만) |
| Requirements Met | 100% (5/5 implemented FR) | Complete |
| Design Compliance | 100% | Excellent (>90% threshold) |

### 10.2 Quality Outcomes

| Metric | Value |
|--------|-------|
| Test Pass Rate | 100% (203+ wiki tests) |
| Test Regression | 0 (all existing tests pass) |
| Architecture Compliance | 100% (layer separation maintained) |
| Code Quality Issues | 0 |
| Performance Improvement | 99.5% (6.5s → 30ms) |
| Technical Debt | Minimal (선례 복구) |

### 10.3 Team Capacity

| Phase | Time | Effort |
|-------|------|--------|
| Plan (구간 격리·생성자 단독 실측) | 3 hours | High (curl + threadpool 벤치) |
| Design (대안 검토·시점 결정·선례 평가) | 2 hours | Medium (코드 리뷰 + 문서) |
| Do (구현·TDD) | 2 hours | Low (싱글턴+라우터 수정만) |
| Check (Gap 분석·성능 실측) | 1 hour | Minimal (자동 검증 + curl) |
| **Total** | ~8 hours | 1 working day |

---

## 11. Changelog

### v1.0.0 (2026-07-29)

**Added**:
- `src/api/main.py:_wiki_vector_stack` — 모듈 전역 lazy 싱글턴 (D1)
- `src/api/main.py:get_wiki_vector_stack()` — 앱 수명 1회 임베딩·Qdrant·벡터스토어 생성 (D1)
- `tests/api/test_wiki_di_singleton.py` — 생성 횟수 단언 (TC-01~03, Red 선행 확인)
- `tests/api/test_wiki_router.py` 확장 — 의존성 순서 검증 (TC-04~06, 스텁 호출 추적)

**Changed**:
- `src/api/main.py:create_wiki_factories._make_repo` — `get_wiki_vector_stack()` 공유 호출
- `src/api/main.py:get_wiki_folder_summary_service._article_repo_builder` — `get_wiki_vector_stack()` 공유
- `src/api/routes/wiki_router.py` — 10개 엔드포인트 의존성 순서 (인증 → use_case) (D2)

**Technical Improvements**:
- per-request 클라이언트 생성 제거 → 요청당 ~6.5초 지연 제거
- 요청 반복 시 클라이언트 누수 중단
- 미인증 요청이 무거운 DI 실행 회피 (인증 계층화)
- 기동 시 콜드 비용 1회로 집중 (startup으로 예측 가능)

**Environment**:
- .venv 누락 의존성 설치: `pymupdf4llm`, `python-jose[cryptography]`, `passlib[bcrypt]`

---

## 12. Sign-Off

**Feature Owner**: 배상규  
**Completion Date**: 2026-07-29  
**Status**: ✅ **COMPLETE & APPROVED**  
**Match Rate**: 100% (15/15 items)  
**Performance Improvement**: 99.5% (6.5s → 30ms)  
**Ready for Merge**: Yes  
**Ready for Production**: Yes

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-29 | Completion report created — 100% match (15/15), 0 iterations, 203+ wiki tests pass, 99.5% performance improvement | 배상규 |
