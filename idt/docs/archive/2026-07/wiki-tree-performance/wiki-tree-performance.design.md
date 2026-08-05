# Wiki Tree Performance Design Document

> **Summary**: wiki DI 병목 수정의 구현 설계 — `main.py`에 **앱 전역 lazy 싱글턴 `get_wiki_vector_stack()`**(임베딩+Qdrant 클라이언트+벡터스토어 1회 생성)을 신설하고(D1, `get_wiki_folder_summary_service` lazy-global 선례 패턴), `create_wiki_factories._make_repo`·`_article_repo_builder` 두 지점이 이를 공유. `wiki_router` 전 엔드포인트의 의존성 선언 순서를 **인증 → use_case**로 교정(D2). agent-run 경로(2365행)·distill의 ES/증류기 빌더는 무변경(D3)
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-29
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/wiki-tree-performance.plan.md`

---

## 1. Design Overview

수정 대상은 `src/api/main.py`(DI 조립)와 `src/api/routes/wiki_router.py`(의존성 순서) 2개 파일.
domain/application/infrastructure 레이어는 무변경.

```
[현행 — 요청마다]                          [설계 — 앱 수명 1회]
wiki 요청                                  create_app()
  └ query_factory(session)                   └ create_wiki_factories()
      └ _make_repo(session)                      └ get_wiki_vector_stack()  ← D1: 최초 1회만 생성
          ├ OpenAIEmbedding()   ~2.8s*               ├ OpenAIEmbedding()
          ├ AsyncQdrantClient() ~3.3s*               ├ AsyncQdrantClient()
          └ QdrantVectorStore()                      └ QdrantVectorStore()
                                           wiki 요청
                                             └ query_factory(session)
                                                 └ _make_repo(session)      ← 세션 바인딩만 (~0s)
* 시스템 Py3.13 실측. .venv에서도 ~0.2s/요청 낭비
```

**공유 대상 생성 지점 정리 (실측 기반)**:

| 지점 | 현행 | 설계 |
|------|------|------|
| `create_agent_builder_factories` `main.py:2365-2374` | 앱 조립 시 1회 (올바름) | **무변경** (Plan Out of Scope — 통합은 후속 후보) |
| `get_wiki_folder_summary_service._article_repo_builder` `main.py:3477-3490` | **빌더 호출마다** 생성 | `get_wiki_vector_stack()` 공유 |
| `create_wiki_factories._make_repo` `main.py:3514-3530` | **요청마다** 생성 ← 주 병목 | `get_wiki_vector_stack()` 공유 |
| `create_wiki_factories._make_source_provider`·`_make_distiller` (distill 전용) | 요청마다 생성 | **무변경** (D3 — admin 전용·저빈도) |

---

## 2. D1 — `get_wiki_vector_stack()` 앱 전역 lazy 싱글턴

### 2.1 결정

Plan §6.2에서 유보한 두 가지를 다음과 같이 확정한다.

**생성 시점**: 모듈 레벨 **lazy 전역 + `create_wiki_factories()` 본문에서 즉시 1회 호출**.

| 대안 | 기각/채택 근거 |
|------|---------------|
| 모듈 import 시점 eager 생성 | 기각 — import 부작용(테스트가 `main` import만 해도 외부 클라이언트 생성), 테스트 격리 불가 |
| 첫 요청 시 lazy (호출 지연) | 기각 — 최초 요청 1건이 콜드 비용(~수 초)을 뒤집어씀. 기동 시점에 지불하는 것이 예측 가능 |
| **lazy 전역 + create_wiki_factories에서 즉시 호출 (채택)** | `create_app()` 경유 시 기동 시점 1회 생성(콜드 비용은 startup으로), 테스트는 전역 리셋+패치로 격리. `get_wiki_folder_summary_service`(3453-3506행) 기존 lazy-global 선례와 동형 |

**인스턴스 출처**: `create_agent_builder_factories`의 기존 `_wiki_embedding`/`_wiki_qdrant`(2366행)를
**공유하지 않고** wiki API용 스택을 별도 1회 생성한다.

| 대안 | 기각/채택 근거 |
|------|---------------|
| 2365행 클로저 인스턴스 공유 | 기각 — agent-run 조립 함수의 내부 변수를 외부로 노출하는 구조 변경 필요. Plan Out of Scope("agent-run 경로 무변경") 위반. 프로세스당 인스턴스 2개는 무해 |
| **wiki API용 별도 싱글턴 (채택)** | 변경 반경이 wiki 조립부에 한정. 요청당 N개 → 프로세스당 2개로 목적(FR-01/05) 달성. 완전 통합은 후속 후보로 기록 |

### 2.2 코드 변경 (`main.py`)

```python
# get_wiki_folder_summary_service 인근(모듈 레벨)에 추가:
_wiki_vector_stack: tuple | None = None


def get_wiki_vector_stack():
    """wiki-tree-performance D1: wiki API용 임베딩·Qdrant·벡터스토어 앱 전역 lazy 싱글턴.

    per-request 생성 시 요청마다 수 초의 클라이언트 초기화 비용 + 미해제 누수 발생
    (plan §1.2 실측). 클라이언트는 무상태(설정+커넥션 풀)이므로 동시 요청 공유 안전
    — create_agent_builder_factories(2365행)가 동일 방식으로 이미 공유 운용 중.
    """
    global _wiki_vector_stack
    if _wiki_vector_stack is None:
        collection = getattr(settings, "wiki_collection_name", "wiki_knowledge")
        embedding = OpenAIEmbedding(model_name=settings.openai_embedding_model)
        qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host, port=settings.qdrant_port
        )
        vector_store = QdrantVectorStore(
            client=qdrant_client, embedding=embedding, collection_name=collection
        )
        _wiki_vector_stack = (embedding, vector_store, collection)
    return _wiki_vector_stack
```

```python
# create_wiki_factories() — _make_repo 교체:
def create_wiki_factories():
    app_logger = get_app_logger()
    embedding, vector_store, wiki_collection = get_wiki_vector_stack()  # 기동 시 1회

    def _make_repo(session: AsyncSession):
        return WikiArticleRepository(
            session=session, logger=app_logger, embedding=embedding,
            vector_store=vector_store, collection_name=wiki_collection,
        )
    # distill/query/review/human_write 팩토리 본문은 무변경 (_make_repo 시그니처 동일)
```

```python
# get_wiki_folder_summary_service() — _article_repo_builder 교체:
def _article_repo_builder(session: AsyncSession):
    embedding, vector_store, wiki_collection = get_wiki_vector_stack()
    return WikiArticleRepository(
        session=session, logger=app_logger, embedding=embedding,
        vector_store=vector_store, collection_name=wiki_collection,
    )
```

- `_make_repo`의 **시그니처·반환 타입 불변** → 4개 팩토리 본문·유스케이스·레포 코드 무변경.
- 클라이언트 명시 close는 추가하지 않는다 — 앱 수명 공유 자원(프로세스 종료 시 해제),
  2367행 선례와 동일 운용. per-request 누수는 생성 자체가 없어지므로 소멸.
- 이벤트 루프 바인딩: `AsyncQdrantClient`는 생성 시 루프에 바인딩되지 않음(httpx lazy) —
  2367행이 동일 조건(모듈 import 시점 `app = create_app()`)에서 이미 검증된 운용.

---

## 3. D2 — `wiki_router` 의존성 선언 순서 교정

### 3.1 결정

FastAPI는 파라미터 선언 순서대로 의존성을 해석하므로, **10개 전 엔드포인트**
(distill·create·tree·list·get·approve·reject·deprecate·restore·edit)에서
인증 의존성(`_user`/`user`/`_admin`)을 use_case 앞으로 이동한다
(agents 라우터 `agent_builder_router.py:154-155`와 동일 관례).

```python
# 예: GET /tree (전 엔드포인트 동일 패턴)
@router.get("/tree", response_model=WikiTreeResponse)
async def wiki_tree(
    agent_id: str,
    _user: User = Depends(get_current_user),   # ← 인증 먼저
    use_case=Depends(get_query_use_case),      # ← 인증 통과 후에만 해석
):
```

- 미인증 요청은 use_case DI(세션 개설 포함)를 실행하지 않고 즉시 거부된다 (FR-03).
  D1 이후에도 세션 개설·레포 조립을 건너뛰므로 여전히 유효한 교정.
- `dependency_overrides` 키는 함수 객체이므로 **기존 테스트 override 방식 영향 없음**.
- 거부 상태코드는 현행 유지(변경 없음) — 테스트 단언은 4xx(401/403)로 둔다.

---

## 4. D3 — 무변경 결정 (검토 후 기각)

| 후보 | 기각 근거 |
|------|----------|
| distill_factory의 `_make_source_provider`(ES)·`_make_distiller`(LLM) 싱글턴화 | admin 전용·저빈도 경로로 병목 아님(실측 대상 아님). 변경 반경 최소화 — 후속 후보로만 기록 |
| `/tree` 전용 경량 레포(벡터 의존 제거) 분리 | D1로 요청당 생성비가 0이 되면 벡터 의존은 미사용 필드일 뿐 비용이 없음. YAGNI (Plan §2.2 재평가 조건 충족) |
| `create_agent_builder_factories`와 스택 완전 통합 | §2.1 — Plan Out of Scope. 후속 후보 |
| qdrant-client `check_compatibility=False` 설정 | 버전 정렬(서버 1.11 ↔ 클라이언트 1.16/1.17)과 함께 후속 항목 — 싱글턴화로 요청 경로에서는 이미 제거됨 |
| Qdrant/OpenAI 클라이언트 앱 shutdown 훅 close | 앱 수명 자원은 프로세스 종료로 충분(선례 동일). 훅 추가는 이득 대비 반경 증가 |

---

## 5. Test Design

### 5.1 신규 테스트 ① `tests/api/test_wiki_di_singleton.py` (FR-01/05)

`src.api.main`의 심볼을 monkeypatch로 계수 페이크 교체 후 생성 횟수를 단언한다.

| ID | 시나리오 | 단언 |
|----|----------|------|
| TC-01 | `create_wiki_factories()` 후 `query_factory(session=MagicMock())` 3회 호출 | `OpenAIEmbedding`·`AsyncQdrantClient`·`QdrantVectorStore` 생성 횟수 **각 1회** (FR-01) |
| TC-02 | `create_wiki_factories()` 2회 호출 + 각 팩토리 혼합 호출 | 생성 횟수 여전히 각 1회 — 전역 싱글턴이 조립 함수 재호출에도 유지 (FR-05) |
| TC-03 | `get_wiki_folder_summary_service()`의 `_article_repo_builder(MagicMock())` 2회 호출 | 신규 생성 0회 — `get_wiki_vector_stack()` 공유 확인 |

- **패치 지점**: `src.api.main.OpenAIEmbedding` / `src.api.main.AsyncQdrantClient` /
  `src.api.main.QdrantVectorStore` (main.py가 모듈 상단 import로 참조하므로 main 네임스페이스 패치).
- **전역 리셋**: autouse fixture로 `src.api.main._wiki_vector_stack = None`(전/후) —
  `_wiki_folder_summary_service` 전역도 TC-03 전 `None` 리셋.
- TC-03은 `FolderSummaryDistiller.from_openai`·`WikiFolderSummaryService`도 MagicMock 패치
  (LLM 클라이언트 실생성 방지).
- **Red 확인**: 현행 코드에서 TC-01은 생성 횟수 3회로 실패해야 정상.

### 5.2 신규 테스트 ② `tests/api/test_wiki_router.py` 확장 (FR-03)

기존 파일의 minimal-app 조립 패턴(라우터 단독 mount + `dependency_overrides`)을 재사용한다.

| ID | 시나리오 | 단언 |
|----|----------|------|
| TC-04 | `get_query_use_case` override를 "호출되면 플래그 기록" 스텁으로 설정, **Authorization 없이** GET /tree | 응답 4xx(401/403) + **스텁 미호출** (인증이 먼저 해석됨) |
| TC-05 | 동일 조건 GET /(목록)·GET /{id} | 동일 단언 |
| TC-06 | 정상 토큰(기존 `get_current_user` override) + GET /tree | 200 + 기존 응답 계약 불변 (순서 교정의 기능 무회귀) |

### 5.3 회귀 스위트 + 실측 프로토콜

```
pytest tests/api/test_wiki_router.py tests/api/test_wiki_di_singleton.py (격리 실행)
pytest tests/application/wiki/ tests/infrastructure/wiki/ (격리 실행 — Windows 이벤트 루프 관례)
+ verify-architecture, verify-tdd
```

**성능 실측 (FR-02) — 개선 전 수치는 plan §8.2에 확보됨**:

```bash
# .venv로 기동 (필수 — 시스템 Python 기동이 증폭 원인의 절반)
.venv\Scripts\activate && uvicorn src.api.main:app --reload --port 8000

# 무토큰 401 경로 (개선 전 6~7s → 목표 < 100ms)
curl -s -o /dev/null -w "%{time_total}s\n" "http://localhost:8000/api/v1/wiki/tree?agent_id=..."
# 정상 토큰 경로 3회 반복 (개선 전 대비표 작성, 목표 p50 < 500ms)
```

---

## 6. Implementation Order

```
1. TC-01~03 작성 → Red 확인 (현행: 요청마다 생성 → 횟수 3회로 실패)
   → get_wiki_vector_stack() 신설 + _make_repo/_article_repo_builder 교체 (D1) → Green
2. TC-04~06 작성 → Red 확인 (현행: 스텁이 인증 전에 호출됨)
   → wiki_router 10개 엔드포인트 파라미터 순서 교정 (D2) → Green
3. wiki 관련 기존 테스트 격리 실행 무회귀 (5.3)
4. .venv 기동 → FR-02 실측 비교표 작성 (plan §8.2 수치 대비)
```

---

## 7. 주의사항 / 영향 범위

- **API 계약·DB·프론트 무변경** — 응답 스키마·상태코드·엔드포인트 경로 전부 동일.
  (파라미터 순서 변경은 FastAPI 시그니처 내부 문제로 OpenAPI 스키마에 영향 없음 —
  쿼리 파라미터 `agent_id` 등은 계속 첫 번째 선언 유지)
- 공유 임베딩·Qdrant 클라이언트는 wiki **쓰기 경로**(`save`/`update`의 `_index_vector`)에서도
  사용된다 — 무상태 클라이언트 공유이므로 동작 동일, 5.3 회귀 스위트가 커버.
- 기동 시점 콜드 비용(~수 초, 인터프리터에 따라)이 startup으로 이동한다 —
  요청 지연보다 예측 가능하며, agent_builder 조립(2366행)이 이미 동일 비용을 기동 시 지불 중.
- **운영 전제**: 로컬/배포 모두 프로젝트 venv 인터프리터로 기동할 것 (시스템 Python 기동 시
  생성자 비용이 회당 ~6s로 증폭되는 환경임을 plan §1.2에서 실측 — D1 이후에는 기동 1회 비용).
- 후속 기록(본 건 범위 외): ① qdrant-client ↔ 서버 1.11.0 버전 정렬(+`check_compatibility`)
  ② agent_builder 스택과의 완전 통합 ③ distill 경로 ES/증류기 빌더 싱글턴화.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-29 | Initial draft — 생성 시점(lazy 전역+조립 시 즉시 호출)·인스턴스 출처(별도 싱글턴)·순서 교정 범위(전 엔드포인트) 확정 | 배상규 |
| 0.2 | 2026-07-29 | Gap 분석 G1 정정 — 엔드포인트 수 9개 → 10개 (distill 포함, 구현은 처음부터 10개 전부 교정) | 배상규 |
