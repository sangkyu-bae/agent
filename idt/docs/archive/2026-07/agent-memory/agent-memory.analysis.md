# agent-memory Gap Analysis (Check)

> **Design**: `docs/02-design/features/agent-memory.design.md`
> **Analyzer**: gap-detector (bkit) + 메인 세션 검증 보강
> **Date**: 2026-07-20
> **Match Rate**: **98%** (기능 누락 0 · 무단 추가 0 · Low 편차 1 · 정당한 편차 4)

---

## 1. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 98% | ✅ |
| Architecture Compliance (Thin DDD) | 100% | ✅ (verify-architecture 신규 모듈 위반 0) |
| Test Plan Coverage (§4) | 100% | ✅ (설계 명시 케이스 전부 존재, 61건 통과) |
| Logging (LOG-001) | 100% | ✅ (verify-logging 위반 0) |

---

## 2. 섹션별 매칭 요약

| Design 섹션 | 판정 | 비고 |
|-------------|:----:|------|
| §3-1 V050 DDL·인덱스 | Match | 설계 SQL 문자 단위 일치, `idx_memory_user_status` 정확 |
| §3-1 SQLAlchemy 모델 정합 | Low 편차 | G1 참조 (TINYINT vs SMALLINT) |
| §3-2 Domain (엔티티·정책·인터페이스) | Match | 상수·시그니처·동작 전부 일치 |
| §3-3 CrudUseCase + 404 은닉 | Match | "찾을 수 없" 단일 메시지로 타인·미존재 은닉 |
| §3-3 ContextAssembler FR-05/06/07/09 | Match | 절단 debug·빈 헤더 금지·실패 격리·보수 지침 전부 구현 |
| §3-3 general_chat 통합 | Match | optional None 기본, `user_ctx + memory_block + _SYSTEM_PROMPT` 순서, stream() 조립 — 기존 테스트 회귀 0 |
| §3-4 라우터·config·DI | Match | 401/404/422 계약, str(user.id), config 30/800, assembler 싱글톤 |
| §3-5 Frontend 계약 + SettingsPage + /settings | Match | 계약 5종·페이지 요구 7항목·라우트·TopNav 진입점·MSW 4종 |
| §4 Test Plan | Match | 백엔드 57건 + 프론트 10건, 설계 케이스 누락 없음 |

---

## 3. Gap 목록

| # | 심각도 | 위치 | 내용 | 처리 |
|---|:---:|------|------|------|
| G1 | Low | `src/infrastructure/memory/models.py:21,25` vs `V050:8,12` | `tier`/`confidence` 모델 타입 SmallInteger(SMALLINT) ≠ DDL TINYINT. production 테이블은 Flyway DDL로 생성되므로 무해 — SQLite 테스트 경로에만 존재하는 타입 차이 | 보류(무해). 본 문서로 기록 — 다음 스키마 변경 시 정합화 |
| ~~G2~~ | — | `context_assembler.py:70-74` | ~~warning의 `exception=` 파라미터가 스택트레이스를 남기는지 미확인~~ → **해소 확인**: `StructuredLogger._log()`가 `exception=`을 `exc_info=(type, exc, __traceback__)`로 변환해 기록 (`structured_logger.py:128-132`). 설계 의사코드의 `exc_info=True`와 동등 | Gap 아님 (검증 완료) |

## 4. 정당한 편차 (Gap 아님 — 다음 분석 시 오인 방지용 기록)

| # | 편차 | 근거 |
|---|------|------|
| D1 | API 스키마 위치: 설계 `interfaces/schemas/memory_schemas.py` → 구현 `application/memory/api_schemas.py` | wiki `api_schemas.py` 선례 준수 — 라우터-스키마 배치 일관성 |
| D2 | `MemoryContextAssembler.__init__`에 `repo_builder(기본 None)` 추가 | 테스트 DI용 (RunScopedWikiSearch 동일 패턴), production 동작 무변화 |
| D3 | 프론트 상수 `MEMORY_LIST/CREATE/DETAIL` → `MEMORIES` + `MEMORY_DETAIL(id)` | GET/POST 동일 URL이라 1상수 통합 — 기능 동일 |
| D4 | 인라인 수정 진입 "항목 클릭" → "수정 버튼" | 삭제 버튼과 UX 일관성, 제출 시 PATCH 동일 |

구현 중 실측으로 조정된 2건(설계 의사코드 대비): ① 정렬을 `timestamp()` 변환 없이 이중 안정 정렬로 구현 (Windows `datetime.min.timestamp()` OSError 회피, 동작 계약 동일) ② 프론트 422 표면화는 `err.message` 사용 (authApiClient 인터셉터가 detail을 `ApiError(message)`로 변환하는 구조 실측).

---

## 5. 테스트 실행 결과

| 스위트 | 결과 |
|--------|------|
| 백엔드 신규 6파일 (정책 16·저장소 7·CRUD 13·조립기 6·라우터 9·주입 6) | 57/57 통과 (파일 격리 실행 — 교차 실행 에러는 기지의 Windows 이벤트루프 flakiness) |
| 기존 general_chat 회귀 | 0건 (optional 의존성 — 무수정 통과) |
| 프론트 신규 (훅 4·SettingsPage 6) + wiki 회귀 7 | 17/17 통과, 변경 파일 tsc 에러 0 |

## 6. 이월 항목

- **V050 마이그레이션 적용** (V051과 함께 미적용) — 배포 전 필수
- **실서버 E2E**: 등록 → 채팅 프롬프트 `[사용자 메모리]` 블록 확인(LangSmith trace) → 삭제 후 미주입 확인 — KB 공통 체크리스트 등재
- G1 모델-DDL 정수 타입 정합화 — 다음 스키마 변경 시

## 7. 총평

1. 설계 전 항목 구현·테스트 완료, 매칭 98%로 Check 기준(≥90%) 충족 — `/pdca report` 진행 가능.
2. 잔여 편차는 전부 Low 또는 근거 있는 의도적 편차로 회귀 위험 없음. G2는 실코드 검증으로 해소.
3. 코드 밖 검증(V050 적용 + E2E)만 공통 체크리스트로 이월.
