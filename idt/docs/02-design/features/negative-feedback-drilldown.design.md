# negative-feedback-drilldown Design Document

> **Summary**: 관리자 전용 드릴다운 UseCase·엔드포인트를 추가하고, 대시보드의 👎 항목에서 질문·답변·근거·런 링크를 모달로 표시한다.
>
> **Project**: sangplusbot — idt (백엔드) + idt_front (프론트)
> **Version**: 기준 커밋 1baf6d1 (master)
> **Author**: 배상규 + Claude
> **Date**: 2026-11-02
> **Status**: Draft
> **Planning Doc**: [negative-feedback-drilldown.plan.md](../../01-plan/features/negative-feedback-drilldown.plan.md) (v0.2)

---

## Context Anchor

> Plan에서 복사했다. Design → Do 인계 시 맥락을 유지한다.

| Key | Value |
|-----|-------|
| **WHY** | 👎 데이터는 쌓이지만 관리자가 질문·답변·실행 근거를 열어 볼 화면이 없어 원인을 판단할 수 없다. |
| **WHO** | P3 관리자(부서·시스템) — 👎 원인을 확인하고 위키 draft 승인 여부를 판단하는 사람. P2 에이전트 소유자는 관리자 권한이 있을 때만 해당한다. |
| **RISK** | 대화 원문을 관리자 화면에 처음 표시한다(런 상세 API는 이미 반환 중). 👎가 있는 답변으로만 조회를 제한하고 조회 기록을 남긴다. 평가 id(assistant)와 런 연결 id(user)가 달라 질문 복원을 빠뜨리면 200 빈 결과로 조용히 실패한다. |
| **SUCCESS** | 로컬 실데이터 👎 2건 모두 질문·답변·런 링크가 표시된다. 👎가 없는 메시지는 404, 비관리자는 403이다. 응답에 사용자 id가 없다. 기존 pytest/Vitest 회귀 0. |
| **SCOPE** | 신규 조회 UseCase·엔드포인트 1개, 프론트 타입·서비스·훅·모달, 패널 항목 버튼화, 테스트. 필터·페이지네이션, 전용 화면, 스키마 변경, `retrievals` 동작 변경은 제외한다. |

---

## 1. Overview

### 1.1 Design Goals

- 질문 복원 규칙과 런·근거 조회 규칙을 복제하지 않고 기존 구현을 재사용한다.
- 드릴다운 조회가 `recent-negative` 목록 성능과 기존 계약에 영향을 주지 않는다.
- 관리자가 조회할 수 있는 대화를 👎가 달린 답변으로 코드에서 제한한다.
- "근거 없음", "런 없음", "질문 복원 실패"를 서로 다른 상태로 표시한다.

### 1.2 Design Principles

- 신규 UseCase는 조회 순서만 제어한다. 규칙은 `EvalPolicy`, 런·근거 조회는 `GetMessageRetrievalsUseCase`가 맡는다.
- 응답 스키마는 허용 필드만 선언해 사용자 식별자가 구조적으로 빠지게 한다.
- 기존 공개 API는 변경하지 않는다(`additive-contract-extension`).

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| 기준 | A: 최소 변경 | B: 분리 우선 | C: 실용 균형 |
|------|:-:|:-:|:-:|
| **방식** | `AgentEvalStatsUseCase`에 메서드 추가, `_group_by_query` 직접 import | 조회 포트·어댑터 신설, 질문 복원 서비스 추출 | 신규 `GetNegativeDrilldownUseCase`가 `GetMessageRetrievalsUseCase`에 위임 |
| **신규 파일(운영 코드)** | 1 | 6 | 3 |
| **수정 파일(운영 코드)** | 12 | 11 | 10 |
| **복잡도** | 낮음 | 높음 | 중간 |
| **유지보수성** | 중간 | 높음 | 높음 |
| **작업량** | 작음 | 큼 | 작음~중간 |
| **위험** | 집계와 상세 조회 혼재, 근거 DTO 복제 필요 | 소비자 1곳에 추상화 과다 | 메시지 조회 1회 중복(무시 가능) |

**선택**: C (사용자 결정). 런·근거 규칙을 복제하지 않고, 응답 스키마를 `interfaces/schemas/`에 두어 기존 DTO를 재사용한다.

### 2.1 Component Diagram

```
AgentSatisfactionPanel ── 선택 ──▶ NegativeDrilldownModal
                                     │ useNegativeDrilldown
                                     ▼
                          messageFeedbackService
                                     │ GET /admin/eval/negative/{id}/drilldown
                                     ▼
eval_router (require_role admin) ──▶ GetNegativeDrilldownUseCase
                                     ├─ MessageFeedbackRepository.has_negative
                                     ├─ ConversationMessageRepository (답변·세션 조회)
                                     ├─ EvalPolicy.find_question (재사용)
                                     └─ GetMessageRetrievalsUseCase (재사용, 질문 id로 호출)
```

### 2.2 Data Flow

```
message_id(assistant)
  → has_negative = False → 404
  → find_by_id = None 또는 role != assistant → 404
  → find_by_session + EvalPolicy.find_question
      → None → 200 {question: null, runs: []}
      → question → retrievals.execute(question.id, admin_id, is_admin=True)
  → 조회 로그 → 200
```

### 2.3 Dependencies

| 구성 요소 | 의존 대상 | 목적 |
|----------|----------|------|
| `GetNegativeDrilldownUseCase` | `MessageFeedbackRepositoryInterface` | 👎 존재 확인 |
| 〃 | `ConversationMessageRepository` | 답변·세션 메시지 조회 |
| 〃 | `EvalPolicy` | 질문 복원 |
| 〃 | `GetMessageRetrievalsUseCase` | 런·근거 그룹 조회 |
| `NegativeDrilldownResponse` | `MessageRetrievalsResponse` | 런·근거 변환 재사용 |
| `NegativeDrilldownModal` | 공통 `Modal`, `MarkdownRenderer`, `Button` | 표시 |

---

## 3. Data Model

스키마 변경은 없다. 마이그레이션 0.

### 3.1 Application DTO

```python
@dataclass(frozen=True)
class NegativeDrilldownDto:
    message_id: int
    agent_id: str
    question: str | None          # 복원 실패 시 None
    answer: str
    runs: list[MessageRunRetrievals] = field(default_factory=list)
```

`MessageRunRetrievals`는 `get_message_retrievals_use_case.py`의 기존 DTO다.

### 3.2 Entity Relationships

```
message_feedback.message_id ┄soft┄▶ conversation_message(assistant)
                                        │ EvalPolicy.find_question (turn-1, 같은 turn 폴백)
                                        ▼
                                    conversation_message(user)
                                        ▲
ai_run.user_message_id ─────────────────┘   ai_run 1 ─ N ai_retrieval_source
```

### 3.3 저장소 포트 추가

```python
@abstractmethod
async def has_negative(self, message_id: int, request_id: str) -> bool:
    """해당 메시지에 down 평가가 1건 이상 있으면 True."""
```

구현은 `select(id).where(message_id, rating=down).limit(1)`이다. 인덱스 `uq_feedback_msg_user(message_id, user_id)`의 선두 컬럼을 탄다. 테스트 코드에 이 포트를 상속한 구현체는 없어(grep 확인) 추상 메서드 추가의 파급이 없다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 설명 | 인증 |
|--------|------|------|------|
| GET | `/api/v1/admin/eval/negative/{message_id}/drilldown` | 👎 답변의 질문·답변·런·근거 조회 | admin |

### 4.2 Detailed Specification

**Path**: `message_id` — 평가된 assistant 메시지 id (int)

**Response 200**

```json
{
  "message_id": 284,
  "agent_id": "2fc01e00-090a-419a-9978-269b7574b20b",
  "question": "질문 원문",
  "answer": "답변 원문",
  "runs": [
    {
      "run_id": "5a7d6c11-ecc1-4b05-8fea-66b4123e4f1f",
      "agent_id": "2fc01e00-090a-419a-9978-269b7574b20b",
      "langsmith_run_url": null,
      "groups": [
        {
          "search_query": "재작성 쿼리",
          "query_source": "...",
          "search_mode": "...",
          "sources": [{ "id": "...", "collection_name": "...", "rank_index": 1, "score": 0.8, "content_preview": "...", "created_at": "..." }]
        }
      ]
    }
  ]
}
```

- `runs[]`는 `MessageRunRetrievalsDto`를 그대로 쓴다.
- 질문 복원 실패: `question: null`, `runs: []`, `answer`는 유지.
- 런 없음: `runs: []`. 런은 있으나 근거 없음: `groups: []`.
- `user_id`, `session_id`는 없다.

**Error Responses**

| 코드 | 조건 |
|------|------|
| 401 | 미인증 |
| 403 | 비관리자 |
| 404 | down 평가 없음 / 원본 메시지 없음 / assistant 메시지가 아님 |
| 422 | `message_id`가 정수가 아님 |

404 세 조건은 같은 메시지 `메시지를 찾을 수 없습니다.`를 반환한다. 기존 `_raise_feedback_error`를 재사용한다.

### 4.3 라우터

```python
@router.get(
    "/admin/eval/negative/{message_id}/drilldown",
    response_model=NegativeDrilldownResponse,
)
async def negative_drilldown(
    message_id: int,
    # 인증을 먼저 둬 미인증·비관리자 요청은 세션을 열기 전에 거부한다
    admin: User = Depends(require_role("admin")),
    use_case=Depends(get_negative_drilldown_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        dto = await use_case.execute(message_id, str(admin.id), request_id)
    except ValueError as e:
        _raise_feedback_error(e)
    return NegativeDrilldownResponse.from_dto(dto)
```

### 4.4 응답 스키마 (`src/interfaces/schemas/eval_drilldown_response.py`)

```python
class NegativeDrilldownResponse(BaseModel):
    message_id: int
    agent_id: str
    question: str | None = None
    answer: str
    runs: list[MessageRunRetrievalsDto] = []

    @classmethod
    def from_dto(cls, dto) -> "NegativeDrilldownResponse":
        converted = MessageRetrievalsResponse.from_dto(
            MessageRetrievalsDto(message_id=dto.message_id, runs=dto.runs)
        )
        return cls(message_id=dto.message_id, agent_id=dto.agent_id,
                   question=dto.question, answer=dto.answer, runs=converted.runs)
```

변환 로직을 복제하지 않기 위해 기존 `MessageRetrievalsResponse.from_dto`를 통과시킨다. `application/eval/api_schemas.py`에 두지 않는 이유는 application이 interfaces를 import하면 레이어 규칙을 어기기 때문이다.

### 4.5 UseCase (`src/application/eval/drilldown_use_case.py`)

```python
class GetNegativeDrilldownUseCase:
    def __init__(self, feedback_repo, message_repo, retrievals, logger) -> None: ...

    async def execute(self, message_id: int, admin_id: str, request_id: str) -> NegativeDrilldownDto:
        answer = await self._resolve_answer(message_id, request_id)
        question = await self._find_question(answer)
        runs = await self._find_runs(question, admin_id)
        self._logger.info(
            "negative drilldown viewed", request_id=request_id, admin_id=admin_id,
            message_id=message_id, question_restored=question is not None,
            run_count=len(runs),
        )
        return NegativeDrilldownDto(...)
```

- `_resolve_answer`: `has_negative` False, 메시지 None, role이 ASSISTANT가 아니면 `ValueError("메시지를 찾을 수 없습니다.")`.
- `_find_question`: `find_by_session(answer.user_id, answer.session_id)` + `EvalPolicy.find_question`. `SubmitFeedbackUseCase._find_question`과 같은 2줄이다. 규칙은 Policy 한 곳에 있으므로 호출 2줄을 공유하려고 기존 UseCase를 수정하지 않는다.
- `_find_runs`: question이 None이면 `[]`. 아니면 `retrievals.execute(message_id=question.id.value, requesting_user_id=admin_id, is_admin=True)`의 `.runs`.
- 로그에는 질문·답변 본문을 넣지 않는다.

### 4.6 DI (`main.py`, Eval Gate DI 구역)

```python
def _eval_drilldown_f(session: AsyncSession = Depends(get_session)):
    logger = get_app_logger()
    message_repo = SQLAlchemyConversationMessageRepository(session)
    return GetNegativeDrilldownUseCase(
        feedback_repo=MessageFeedbackRepository(session, logger),
        message_repo=message_repo,
        retrievals=GetMessageRetrievalsUseCase(
            agent_run_repo=SqlAlchemyAgentRunRepository(session),
            message_repo=message_repo,
            logger=logger,
        ),
        logger=logger,
    )
```

모든 저장소가 같은 요청 세션을 쓴다(`db-session` 규칙).

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌ 답변 드릴다운 ─────────────────────────────── X ┐
│ {agent_id 전체} · 2026-10-20 14:03               │
├─────────────────────────────────────────────────┤
│ 👎 이유     (코멘트 없음)                         │
│ 질문        사용자 질문 원문                      │
│ 답변        MarkdownRenderer 렌더링               │
│ 실행 근거                                        │
│  ┌ 실행 5a7d6c11…  [런 상세] [LangSmith]        ┐ │
│  │ 재작성 쿼리: ...  (hybrid)                   │ │
│  │  1. collection · 0.82 · 미리보기 2줄          │ │
│  │ 또는 "이 실행은 문서 검색을 사용하지 않았습니다"│ │
│  └──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

공통 `Modal`을 `size="3xl"`, `scroll="body"`로 쓴다.

### 5.2 User Flow

```
대시보드 → 최근 부정 피드백 항목 클릭 → 모달 조회 → 질문·답변·근거 확인
  → [런 상세] /admin/agent-runs/{run_id} 이동 또는 ESC·X·배경 클릭으로 닫기
```

### 5.3 Component List

| 컴포넌트 | 위치 | 책임 |
|----------|------|------|
| `AgentSatisfactionPanel` (수정) | `pages/AdminDashboardPage/components/` | 항목 버튼화, 선택 상태, 조건부 모달 렌더 |
| `NegativeDrilldownModal` (신규) | 같은 위치 | 조회, 로딩·오류·본문 상태, 런·근거 표시 |

- 모달 props: `item: RecentNegativeItem`, `onClose: () => void`. 이유·시각은 목록 값을 쓴다.
- 패널은 `selected: RecentNegativeItem | null` 상태를 가진다. 모달은 선택 시에만 마운트하므로 조회도 그때 일어난다.
- 패널 항목 `key`는 같은 메시지 👎 중복에 대비해 `${message_id}-${created_at}`로 바꾼다.
- 런 상세 링크는 react-router `Link`다. 공통 테스트 래퍼에 Router가 없으므로 모달 테스트는 `MemoryRouter`로 감싼다.

### 5.4 Page UI Checklist

#### AgentSatisfactionPanel

- [ ] 버튼: 부정 피드백 항목 전체가 `<button type="button">`이며 `aria-label`은 `{agent_id} {이유 또는 "코멘트 없음"} 상세 보기`다. 코멘트 없는 항목끼리 이름이 같아지지 않게 에이전트를 포함한다
- [ ] 텍스트: 빈 문자열 이유도 "(코멘트 없음)"으로 표시한다(모달과 같은 규칙)
- [ ] 텍스트: 기존 에이전트 id와 이유(또는 "(코멘트 없음)") 표시 유지
- [ ] 동작: 클릭 시 모달 표시, 닫으면 패널 유지

#### NegativeDrilldownModal

- [ ] 헤더: 제목 "답변 드릴다운", 부제에 에이전트 id와 평가 시각
- [ ] 텍스트: 👎 이유 또는 "코멘트 없음"
- [ ] 텍스트: 질문 원문, 복원 실패 시 "질문을 찾지 못했습니다"
- [ ] 본문: 답변 `MarkdownRenderer` 렌더링
- [ ] 런 카드: 런 id 앞 8자, "런 상세" 링크(`/admin/agent-runs/{run_id}`)
- [ ] 링크: `langsmith_run_url`이 있을 때만 "LangSmith" 새 탭(`rel="noopener noreferrer"`)
- [ ] 근거 그룹: `search_query`, `search_mode`, 문서별 순위·컬렉션·점수·미리보기
- [ ] 빈 상태: 런은 있으나 근거 0건 → "이 실행은 문서 검색을 사용하지 않았습니다"
- [ ] 빈 상태: 질문은 복원됐으나 런 0건 → "연결된 실행 기록이 없습니다"
- [ ] 로딩: "불러오는 중…"
- [ ] 오류 404: "원본 대화를 찾을 수 없습니다"
- [ ] 오류 기타: "불러오지 못했습니다" + "다시 시도" 버튼(`refetch`)

---

## 6. Error Handling

### 6.1 Error Code Definition

| 코드 | 원인 | 처리 |
|------|------|------|
| 401 | 토큰 만료·없음 | 기존 인터셉터가 갱신 또는 로그인 이동 |
| 403 | 비관리자 | 관리자 화면 라우트 가드로 도달하지 않음. 도달 시 기타 오류 표시 |
| 404 | §4.2 세 조건 | 모달에 안내, 대시보드 유지 |
| 500 | 서버 오류 | 기타 오류 표시, 스택 트레이스는 기존 예외 처리 로그 |

### 6.2 프론트 오류 판정

`authApiClient` 오류는 `ApiError(message, status, code)`다. `error instanceof ApiError && error.status === 404`로 판정한다. 훅은 `retry: false`로 둔다. 404를 재시도하면 안내가 늦어지기 때문이다.

---

## 7. Security Considerations

- [ ] 인가: `require_role("admin")`. 401·403 라우터 테스트
- [ ] 조회 범위: down 평가가 있는 assistant 메시지만
- [ ] 식별자 제외: 응답에 `user_id`, `session_id` 없음. 재귀 키 검사 테스트
- [ ] 조회 기록: `admin_id`, `message_id`를 INFO 로그로 기록. 본문 미포함 테스트
- [ ] XSS: `MarkdownRenderer`는 `react-markdown` 기반으로 raw HTML을 렌더링하지 않는다. `rehype-raw`를 추가하지 않는다
- [ ] 외부 링크: `langsmith_run_url`은 서버 저장값, `rel="noopener noreferrer"`

**알려진 한계 (이번 범위 밖)**

- 런 상세 화면은 `run.user_id`를 표시하고, `GET /agents/runs/{id}`는 step의 `input_summary`(질문)와 `output_summary`(답변)를 관리자에게 반환한다. 실데이터 2건에서 확인했다. 드릴다운의 평가자 비노출은 이 응답 안에서만 성립한다.
- 평가자 본인과 세션 소유자를 구분할 수 없는 기존 구조는 그대로다.

---

## 8. Test Plan

> Do에서 구현과 테스트를 함께 작성한다(Red → Green).

### 8.1 Test Scope

| 유형 | 대상 | 도구 | 단계 |
|------|------|------|------|
| 단위 | UseCase 분기, 저장소 `has_negative` | pytest | Do |
| API | 라우터 상태 코드·응답 형태 | TestClient | Do |
| 컴포넌트 | 패널·모달 상태별 표시 | Vitest + RTL + MSW | Do |
| 실런 | 실앱 조립·실 DB·브라우저 | TestClient 인프로세스, Chrome | Do |

### 8.2 L1: API Test Scenarios

| # | 대상 | 시나리오 | 기대 상태 | 기대 응답 |
|---|------|---------|:-------:|----------|
| 1 | drilldown | 관리자 + 👎 메시지 | 200 | question, answer, runs 포함 |
| 2 | drilldown | 비관리자 | 403 | — |
| 3 | drilldown | 미인증 | 401 | — |
| 4 | drilldown | UseCase가 not found ValueError | 404 | detail 메시지 |
| 5 | drilldown | 응답 전체 재귀 탐색 | 200 | `user_id`, `session_id` 키 없음 |
| 6 | drilldown | 문자열 id | 422 | — |

### 8.3 UseCase·저장소 시나리오

| # | 시나리오 | 기대 |
|---|---------|------|
| 1 | down 없음(👍만, 평가 없음) | ValueError, 메시지 조회 호출 안 함 |
| 2 | 메시지 삭제 | ValueError |
| 3 | user 메시지에 달린 down | ValueError |
| 4 | turn-1 질문 정상 | `retrievals.execute`가 **질문 id**로 호출 (assistant id 아님) |
| 5 | 같은 turn 과거 행 | 같은 turn 질문으로 호출 |
| 6 | 모호·미복원 | question None, runs [], `retrievals` 미호출, 답변 유지 |
| 7 | 호출 인자 | `is_admin=True`, `requesting_user_id=admin_id` |
| 8 | 로그 | `admin_id`, `message_id` 포함, 본문 문자열 미포함 |
| 9 | `has_negative` | down 있음 True, up만 False, 없음 False |

### 8.4 L2: UI Action Test Scenarios

| # | 대상 | 동작 | 기대 결과 |
|---|------|------|----------|
| 1 | 패널 | 항목 표시 | 버튼 role, 기존 텍스트 유지 |
| 2 | 패널 | 항목 클릭 | dialog 표시, 드릴다운 API 호출 1회 |
| 3 | 패널 | 키보드 Enter | dialog 표시 |
| 4 | 패널 | 항목 미클릭 | 드릴다운 API 호출 0회 |
| 5 | 모달 | 정상 응답 | 질문, 답변, 이유, 런 링크 href 일치 |
| 6 | 모달 | `groups=[]` | 검색 미사용 문구 |
| 7 | 모달 | `runs=[]` + 질문 있음 | 실행 기록 없음 문구 |
| 8 | 모달 | `question=null` | 질문 미복원 문구, 답변 표시 |
| 9 | 모달 | `langsmith_run_url` null·값 | 링크 없음·있음 |
| 10 | 모달 | 404 | 원본 없음 문구, 재시도 버튼 없음 |
| 11 | 모달 | 500 후 다시 시도 | 재조회 후 본문 표시 |

### 8.5 L3: 실런 시나리오

| # | 시나리오 | 성공 기준 |
|---|---------|----------|
| 1 | TestClient 인프로세스, 메시지 284·267 | 질문·답변·런 1건, `groups=[]` |
| 2 | TestClient, 👍 메시지와 평가 없는 메시지 | 404 |
| 3 | TestClient, 비관리자 토큰 | 403 |
| 4 | 브라우저: 대시보드 → 항목 → 모달 → 런 상세 | 콘솔 오류 0, 런 상세 진입 |
| 5 | 근거 있는 런에 임시 👎 삽입 → 표시 확인 → 삭제 | 그룹·문서 표시, 임시 행 잔존 0 |

### 8.6 Seed Data Requirements

| 데이터 | 최소 건수 | 비고 |
|--------|:-------:|------|
| 👎 + 런 연결 메시지 | 2 | 로컬 284, 267 |
| 근거 있는 런과 연결된 assistant 메시지 | 1 | 임시 👎 행 1건을 넣고 검증 후 삭제. 실행 전 대상 메시지를 보고한다 |

---

## 9. Clean Architecture

### 9.1 Layer Assignment

| 구성 요소 | 레이어 | 위치 |
|----------|--------|------|
| `has_negative` 포트 | Domain | `src/domain/eval/interfaces.py` |
| `EvalPolicy.find_question` (재사용) | Domain | `src/domain/eval/policies.py` |
| `GetNegativeDrilldownUseCase`, DTO | Application | `src/application/eval/drilldown_use_case.py` |
| `has_negative` 구현 | Infrastructure | `src/infrastructure/eval/repository.py` |
| `NegativeDrilldownResponse` | Interfaces | `src/interfaces/schemas/eval_drilldown_response.py` |
| 라우트, DI 플레이스홀더 | API | `src/api/routes/eval_router.py` |
| DI 조립 | API | `src/api/main.py` |
| 프론트 타입 | Front | `src/types/messageFeedback.ts` |
| 서비스·훅 | Front | `src/services/messageFeedbackService.ts`, `src/hooks/useMessageFeedback.ts` |
| 모달·패널 | Front | `src/pages/AdminDashboardPage/components/` |

### 9.2 Dependency Rules

`application/eval`은 같은 레이어의 `application/agent_run` UseCase·DTO를 import한다. 기존 `eval/use_cases.py`가 `application/memory`, `application/wiki`를 참조하는 것과 같은 방향이며 domain·infrastructure 규칙을 어기지 않는다. 신규 UseCase는 infrastructure를 import하지 않는다.

---

## 10. Coding Convention Reference

| 항목 | 적용 규칙 |
|------|----------|
| 백엔드 함수 길이 | 40줄 이하, if 중첩 2단계 이하 — `execute`를 `_resolve_answer`·`_find_question`·`_find_runs`로 분할 |
| 로깅 | `LoggerInterface`, `request_id` 포함, `print` 금지 |
| 세션 | 저장소 commit 금지, 한 요청 한 세션 |
| 프론트 타입 | 백엔드 필드명 snake_case 유지(기존 `messageFeedback.ts` 관례) |
| 쿼리 키 | `queryKeys.eval.negativeDrilldown(messageId)` — 직접 배열 금지 |
| 엔드포인트 상수 | `ADMIN_EVAL_NEGATIVE_DRILLDOWN: (messageId: number) => ...` |
| 상태 | 서버 상태는 TanStack Query, 선택 항목은 `useState` |
| 스타일 | 신규 모달은 토큰·`components/ui` 사용, `zinc-400` 금지, 컴포넌트 파일 런타임 상수 export 금지 |
| 근거 타입 | `RetrievalDto`는 `types/agentRunAdmin.ts`에서 재사용 |
| 코드 주석 | `Design Ref: §…`, `Plan SC: …` 추적 주석 |

### 프론트 추가 타입

```ts
export interface QueryRetrievalGroup {
  search_query: string | null;
  query_source: string | null;
  search_mode: string | null;
  sources: RetrievalDto[];
}

export interface MessageRunRetrievals {
  run_id: string;
  agent_id: string;
  langsmith_run_url: string | null;
  groups: QueryRetrievalGroup[];
}

export interface NegativeDrilldown {
  message_id: number;
  agent_id: string;
  question: string | null;
  answer: string;
  runs: MessageRunRetrievals[];
}
```

### 프론트 훅

```ts
export const useNegativeDrilldown = (messageId: number) =>
  useQuery({
    queryKey: queryKeys.eval.negativeDrilldown(messageId),
    queryFn: () => messageFeedbackService.getNegativeDrilldown(messageId),
    retry: false,
  });
```

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/src/
├── domain/eval/interfaces.py                    (수정) has_negative
├── infrastructure/eval/repository.py            (수정) has_negative
├── application/eval/drilldown_use_case.py       (신규)
├── interfaces/schemas/eval_drilldown_response.py (신규)
├── api/routes/eval_router.py                    (수정)
└── api/main.py                                  (수정)

idt/tests/
├── application/eval/test_drilldown_use_case.py  (신규)
├── infrastructure/eval/test_repository.py       (수정)
└── api/test_eval_router.py                      (수정)

idt_front/src/
├── types/messageFeedback.ts                     (수정)
├── constants/api.ts                             (수정)
├── lib/queryKeys.ts                             (수정)
├── services/messageFeedbackService.ts           (수정)
├── hooks/useMessageFeedback.ts                  (수정)
└── pages/AdminDashboardPage/components/
    ├── AgentSatisfactionPanel.tsx               (수정)
    ├── AgentSatisfactionPanel.test.tsx          (수정)
    ├── NegativeDrilldownModal.tsx               (신규)
    └── NegativeDrilldownModal.test.tsx          (신규)
```

### 11.2 Implementation Order

1. [ ] 저장소 `has_negative` 테스트 → 구현
2. [ ] UseCase 테스트 → 구현
3. [ ] 라우터 테스트 → 스키마·라우트 구현 → `main.py` DI
4. [ ] TestClient 실앱 실런(§8.5 #1~3)
5. [ ] 프론트 타입·상수·쿼리 키·서비스·훅
6. [ ] 모달 테스트 → 구현
7. [ ] 패널 테스트 → 구현
8. [ ] 브라우저 실런(§8.5 #4), 임시 👎 검증(§8.5 #5)
9. [ ] 회귀 diff, verify 스킬, SOT·위키 어긋남 보고

### 11.3 Session Guide

#### Module Map

| 모듈 | Scope Key | 설명 | 예상 턴 |
|------|-----------|------|:------:|
| 백엔드 조회 | `module-1` | 저장소, UseCase, 스키마, 라우트, DI, 실앱 실런 | 10-15 |
| 프론트 화면 | `module-2` | 타입, 서비스, 훅, 모달, 패널, 테스트 | 10-15 |
| 통합 검증 | `module-3` | 브라우저 실런, 임시 👎 검증, 회귀 diff | 5-8 |

#### Recommended Session Plan

| 세션 | 단계 | 범위 |
|------|------|------|
| 세션 1 | Do | `--scope module-1,module-2,module-3` — 규모가 작아 단일 세션 권장 |
| 세션 2 | Check + Report | 전체 |

### 11.4 FR 역추적

| FR | 설계 위치 | 테스트 |
|----|----------|--------|
| FR-01 | §4.3 | §8.2 #2·3 |
| FR-02 | §4.5 `_resolve_answer` | §8.3 #1·3 |
| FR-03 | §4.5 `_find_question` | §8.3 #4·5 |
| FR-04 | §4.5 `_find_runs` | §8.3 #4·7 |
| FR-05 | §4.2, §4.4 | §8.2 #1 |
| FR-06 | §4.4 | §8.2 #5 |
| FR-07 | §2.2 | §8.3 #6 |
| FR-08 | §4.5 | §8.3 #2 |
| FR-09 | §4.5 | §8.3 #8 |
| FR-10 | §5.3 | §8.4 #1~4 |
| FR-11 | §5.4 | §8.4 #5 |
| FR-12 | §5.4 | §8.4 #5·9 |
| FR-13 | §5.4 | §8.4 #6~8 |
| FR-14 | §6.2 | §8.4 #10·11 |
| FR-15 | §10 프론트 타입 | `tsc -b` |

### 11.5 Do에서 확인할 사항

- `MarkdownRenderer`의 엑셀 미리보기 버튼은 `ChatPage`에만 마운트된 모달을 연다. 관리자 화면에서는 눌러도 열리지 않을 수 있다. 문서 추출 파일 링크도 다른 사용자 파일이면 권한 오류가 날 수 있다. 검수 용도에 지장이 없으면 그대로 두고, 동작을 Report에 기록한다.
- 백엔드 `RetrievalDto`에는 프론트 타입에 없는 점수 필드(`bm25_score` 등)가 있다. 표시하지 않으므로 타입은 확장하지 않는다.
- `rank_index`는 백엔드가 `enumerate(start=1)`로 저장하는 1부터 시작하는 값이다. 그대로 표시한다.

---

## Version History

| 버전 | 날짜 | 변경 | 작성자 |
|------|------|------|--------|
| 0.1 | 2026-11-02 | 초안 — 설계안 C 선택, `MarkdownRenderer` 재사용 결정, 런 상세 API의 원문 반환 측정 반영 | 배상규 + Claude |
| 0.2 | 2026-11-02 | Do 실런 반영 — `rank_index` 예시를 실제 값(1부터)으로 정정 | 배상규 + Claude |
| 0.3 | 2026-11-03 | Check 반영 — 패널 버튼 접근성 이름(I-1)·빈 코멘트 표시(M-3), Depends 순서(M-2), 부제 예시(M-6), 의존 목록 `Badge` 제거(M-7) | 배상규 + Claude |
