# Wiki Tree Performance Gap Analysis

> **Feature**: wiki-tree-performance
> **Date**: 2026-07-29
> **Analyzer**: gap-detector (정적 15항목) + 세션 실측 (성능·회귀)
> **Design Reference**: `docs/02-design/features/wiki-tree-performance.design.md`
> **Match Rate**: **100%** (정적 15/15 + 성능 DoD 실측 충족)

---

## 1. 판정 요약

| 영역 | 항목 수 | Match | Gap |
|------|:------:|:-----:|:---:|
| D1 싱글턴 (§2) | 8 | 8 | 0 |
| D2 의존성 순서 (§3) | 1 (10개 엔드포인트 일괄) | 1 | 0 |
| D3 무변경 결정 (§4) | 2 | 2 | 0 |
| 테스트 설계 (§5) | 3 | 3 | 0 |
| API 계약 무변경 (§7) | 1 | 1 | 0 |
| **합계** | **15** | **15** | **0** |

## 2. 항목별 판정 (gap-detector 정적 분석)

| # | Design 조항 | 구현 위치 | 판정 |
|---|---|---|---|
| 1 | §2.1 모듈 레벨 lazy 전역 `_wiki_vector_stack` | `main.py:3467-3488` | ✅ |
| 2 | §2.1 `create_wiki_factories()` 본문 즉시 1회 호출 | `main.py:3544` | ✅ |
| 3 | §2.1 모듈 import 시점 eager 생성 아님 (유일 호출지 create_app 내부) | `main.py:4186` | ✅ |
| 4 | §2.1 agent-run 경로 무변경 | `main.py:2366-2384` 원형 유지 | ✅ |
| 5 | §2.2 settings 기반 1회 생성·tuple 반환 (설계 스니펫 동일) | `main.py:3478-3488` | ✅ |
| 6 | §2.2 `_make_repo` 시그니처 불변 + 4개 팩토리 본문 무변경 | `main.py:3546-3590` | ✅ |
| 7 | §2.2 `_article_repo_builder` 싱글턴 공유 | `main.py:3514-3520` | ✅ |
| 8 | §2.2 명시 close 미추가 | grep 0건 | ✅ |
| 9 | §3 전 10개 엔드포인트 인증 → use_case 순서 | `wiki_router.py` 10/10 확인 | ✅ |
| 10 | §4 distill의 ES/증류기 빌더 per-request 유지 | `main.py:3555-3578` | ✅ |
| 11 | §4 `check_compatibility` 미변경 | 관련 설정 0건 | ✅ |
| 12 | §5.1 TC-01~03 (main 네임스페이스 패치 + autouse 전역 리셋) | `test_wiki_di_singleton.py` | ✅ |
| 13 | §5.2 TC-04/05 (스텁 미호출 + 4xx 단언) | `test_wiki_router.py:301-330` | ✅ |
| 14 | §5.2 TC-06 상당 (정상 토큰 tree 200 계약) | 기존 `TestTree` 커버 | ✅ |
| 15 | §7 API 계약 무변경 (response_model·경로·쿼리 파라미터 순서) | 전 데코레이터 원형 | ✅ |

## 3. Gap 및 처리

| ID | 내용 | 심각도 | 처리 |
|----|------|--------|------|
| G1 | Design이 엔드포인트 수를 "9개"로 과소 기술 (실제 10개, 구현은 10개 전부 교정) | Low | **해소** — Design v0.2로 정정 |
| G2 | FR-02 성능 실측 증거가 저장소에 미기록 | Medium | **해소** — 본 문서 §4에 실측표 기록 |

## 4. 성능 실측 (FR-02 DoD 증거, 2026-07-29)

측정 조건: `.venv`(Python 3.11) 기동 `uvicorn src.api.main:app`, 로컬 MySQL/Qdrant, curl `time_total`.
개선 전 수치는 Plan §8.2 (시스템 Py3.13 기동 구코드 서버 실측).

| 경로 | 개선 전 | 개선 후 (5회) | 목표 | 판정 |
|------|---------|--------------|------|:----:|
| GET /api/v1/wiki/tree 인증 200 전체 경로 | 6.3~7.4s | 14/21/35/41/93ms (p50 ~35ms) | p50 < 500ms | ✅ |
| GET /api/v1/wiki/tree 무토큰 401 | 6.3~7.4s | 4~26ms | < 100ms | ✅ |
| GET /api/v1/wiki 목록 (인증 200) | 5.8~7.0s | 32ms | p50 < 500ms | ✅ |
| GET /health (대조군) | 8~40ms | 4ms | — | 불변 |

개선 폭: 요청당 약 **6.5초 → 30ms 수준 (~99.5% 단축)**. 기동 시 1회 콜드 비용은 startup으로 이동(서버 기동 ~16s, venv 기준 — 기존 agent_builder 조립 비용과 동급).

## 5. 회귀 검증 (세션 실행 기록)

| 스위트 | 결과 |
|--------|------|
| tests/api/test_wiki_di_singleton.py + test_wiki_router.py | 31 passed (신규 5는 Red 선행 확인 후 Green) |
| tests/application/wiki/ (격리) | 110+ passed — 전체 실행 시 teardown 산발 에러는 사전 존재 Windows 이벤트 루프 flaky(격리 실행 전부 통과, 실패 테스트가 실행마다 다름) |
| tests/infrastructure/wiki/ (격리) | 62 passed |
| tests/api/ 전체 | 23 failed / 493 passed — 실패는 전부 비-wiki 사전 실패 계열(general_chat DI 플레이스홀더·main_logging 422≠500·ws auth context). 사전 실패 기록 28건 대비 감소(누락 의존성 설치 효과) |

## 6. 부수 조치 (범위 내 기록)

- `.venv`에 pyproject 선언 의존성 3종 누락 발견·설치: `pymupdf4llm`, `python-jose[cryptography]`, `passlib[bcrypt]` — 이후 `src.api.main`이 venv에서 import 가능 (테스트·기동 전제).
- 운영 전제 재확인: 서버는 반드시 `.venv`로 기동 (시스템 Py3.13 기동이 증폭 원인 절반 — Design §7).

## 7. 후속 항목 (범위 외, Design §7 기록 유지)

1. qdrant-client(1.16/1.17) ↔ Qdrant 서버(1.11.0) 버전 정렬 (+`check_compatibility` 검토)
2. agent_builder 위키 스택과 `get_wiki_vector_stack()` 완전 통합 (프로세스당 인스턴스 2→1)
3. distill 경로 ES/증류기 빌더 싱글턴화 (admin 전용·저빈도라 보류)

---

## 결론

Match Rate **100%** (≥ 90%) — Act(iterate) 불필요. 다음 단계: `/pdca report wiki-tree-performance`.
