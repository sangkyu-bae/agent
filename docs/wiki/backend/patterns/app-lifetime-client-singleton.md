---
title: 무거운 외부 클라이언트는 앱 수명 싱글턴 — per-request DI 금지 + 인증 선행 선언
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/docs/archive/2026-07/wiki-tree-performance/wiki-tree-performance.report.md
  - idt/src/api/main.py (get_wiki_vector_stack, _wiki_vector_stack)
  - idt/src/api/routes/wiki_router.py (10개 엔드포인트 인증 선행 파라미터 순서)
  - idt/tests/api/test_wiki_di_singleton.py (생성 횟수 단언 TC-01~03)
confidence: 0.95
version: 1
created: 2026-08-03
updated: 2026-08-03
verified_at: 4f650d3c
---

## 문제

`/api/v1/wiki/tree` 등 wiki 전 엔드포인트가 매 요청 6.3~7.4초 걸렸다. SQL은 3~45ms로 무죄.
원인은 per-request DI(`create_wiki_factories._make_repo`)가 **요청마다**
`OpenAIEmbeddings`(~2.8s) + `AsyncQdrantClient`(~3.3s, 서버 버전체크 HTTP 왕복 포함)를
신규 생성한 것 — 게다가 생성된 클라이언트는 닫히지 않고 누수됐다.

## 검증된 사실

1. **수정 결과**: `get_wiki_vector_stack()` 모듈 전역 lazy 싱글턴(기동 시 1회 호출)으로
   교체 후 p50 ~35ms (~99.5% 단축, curl 실측). 세션은 여전히 요청 스코프다 —
   원칙: **앱 수명 자원 = 클라이언트, 요청 스코프 = 세션**.
2. **결정적 진단 단서**: 무토큰 401 요청도 6~7초였다. 인증 실패 경로까지 느리면 병목은
   핸들러/SQL이 아니라 **의존성 조립 자체**다. 진단 절차: 구간 격리(curl, 무토큰 대조) →
   최소 단위 재현(생성자 단독 실측) → 환경 격리(인터프리터 교차 측정).
3. **FastAPI는 파라미터 선언 순서대로 의존성을 해석한다** — 인증 의존성(`_user`/`_admin`)을
   use_case `Depends`보다 **앞에** 선언해야 미인증 요청이 무거운 DI(세션 개설 포함)를
   트리거하지 않는다. 성능 + 보안 계층화 이중 가치 (wiki_router 10개 엔드포인트에 적용됨).
4. **선례를 참고하되 무조건 공유하지 않는다**: 같은 main.py의 agent-run 경로에 동일 패턴
   (`_wiki_embedding`/`_wiki_qdrant`)이 이미 있었지만, 조립 함수 내부 변수를 외부 노출하는
   구조 변경을 피해 wiki API용 **별도** 싱글턴을 만들었다. 프로세스당 임베딩 인스턴스 2개는
   무해 — 완전 통합은 후속 후보로만 기록.
5. **환경 증폭**: 시스템 Python 3.13으로 기동하면 생성비가 회당 ~6.1s로 증폭된다.
   느린 API를 만나면 코드보다 먼저 실행 인터프리터(.venv 여부)를 확인할 것.

## 다음에 적용하는 법

- 새 라우터/팩토리에서 임베딩·Qdrant·ES 클라이언트를 요청 스코프 팩토리 내부에서 생성하지
  말 것. 위키 계열은 `get_wiki_vector_stack()` 재사용, 그 외는 동일한 lazy 전역 패턴 신설.
- 라우터 엔드포인트 시그니처는 항상 **인증 파라미터 → use_case 파라미터** 순서.
- 회귀 방지 테스트는 `test_wiki_di_singleton.py` 패턴: main 네임스페이스 패치로
  생성자 호출 횟수를 단언 (팩토리 N회 호출에도 생성 각 1회).
- distill 경로(ES/증류기 빌더)는 admin 전용·저빈도라 아직 per-request다 — 병목 되면 동일 패턴 적용.
