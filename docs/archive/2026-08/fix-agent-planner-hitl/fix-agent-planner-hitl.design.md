# fix-agent-planner-hitl Design Document

> **Summary**: compose 파이프라인을 Planner→Composer 2단계로 재구성 — Planner가 빌드 계획(BuildPlan)과 구조화 질문을 산출하고, UseCase가 질문/진행을 분기하며, 확정 계획을 Composer 프롬프트에 주입한다. 서버 무저장(stateless) HITL, DB 변경 0, 요청/응답 additive 확장.
>
> **Plan**: `docs/01-plan/features/fix-agent-planner-hitl.plan.md`
> **Author**: 배상규
> **Date**: 2026-08-06
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | Fix 탭 compose는 LLM 1회 추측으로 초안을 만들어, 모호한 요청에서 시행착오가 반복된다. |
| **Solution** | `AgentPlanner` 모듈 신설(Protocol 뒤 DI 교체 가능) + `ComposeAgentUseCase` 분기 오케스트레이션 + `AgentComposer`에 계획 블록 주입. 질문은 선택지+자유입력 구조화 카드로 왕복하고, 상태는 요청 페이로드(`clarification_answers`/`clarification_round`)로만 운반한다. |
| **Function/UX Effect** | 모호 요청 → 질문 카드(부분 답변 허용, 최대 3문항×2라운드) → 계획 요약이 붙은 초안 카드. create/edit 동일 동작, Planner 장애 시 기존 단발 compose 폴백. |
| **Core Value** | 한 번의 왕복으로 의도에 맞는 초안 + 모듈 경계(Planner/Composer/Policy) 명확화로 LangGraph HITL 등 후속 교체 용이. |

---

## 1. 아키텍처 개요

```
POST /api/v1/agents/compose  (엔드포인트·인증 불변)
  └─ ComposeAgentUseCase.execute()
       ├─ ① llm_model 해석·후보 수집·history clamp        (기존 그대로)
       ├─ ② AgentPlanner.plan()  ──실패──▶ plan=None (폴백, 경고 로그)
       │      └─ BuildPlan + clarifying_questions + confidence
       ├─ ③ PlannerPolicy.should_ask(confidence, questions, round)
       │      ├─ True  ▶ status="needs_clarification" 응답 반환 (여기서 종료)
       │      └─ False ▶ ④로 진행 (라운드 소진 시 best-effort 강제 진행)
       ├─ ④ AgentComposer.compose(..., plan=BuildPlan)    ([빌드 계획] 블록 부착)
       └─ ⑤ 서버 보정(drop/매핑/clamp) → 초안 응답 + plan_summary  (기존 보정 불변)
```

**레이어 배치** (Thin DDD):

| 레이어 | 신규/변경 | 내용 |
|--------|-----------|------|
| domain/agent_composer | `schemas.py` 확장, `policies.py` 확장 | BuildPlan·ClarifyingQuestion·ClarificationAnswer VO, PlannerPolicy |
| application/agent_composer | `planner.py` 신규, `interfaces.py` 신규, `composer.py`·`compose_agent_use_case.py`·`schemas.py` 수정 | AgentPlanner(LLM), PlannerInterface(Protocol), 오케스트레이션, DTO |
| api | `main.py` DI만 수정 | AgentPlanner 생성·주입. 라우터 변경 없음 |
| infrastructure | 변경 없음 | tracer는 기존 `make_composer_tracer` 재사용 |

- `PlannerInterface`는 **application 레이어 Protocol**로 둔다 — 파라미터가 application DTO(`ComposeCurrentConfig`)를 포함하므로 domain에 두면 역참조 위반. UC는 Protocol 타입에만 의존하고 main.py DI가 구현을 바인딩한다(교체 지점, FR-09).
- DB·마이그레이션·세션 저장 없음. `auto_agent_builder` 경로 무변경.

---

## 2. 백엔드 설계

### 2.1 도메인 VO — `domain/agent_composer/schemas.py` (추가)

```python
@dataclass(frozen=True)
class ToolDirectionHint:
    """계획의 역량→도구 방향 힌트 (D5: 확정 아님, Composer가 최종 결정)."""
    capability: str
    suggested_tool_ids: list[str]   # 후보 tool_id, 빈 배열 허용
    note: str = ""

@dataclass(frozen=True)
class ClarifyingQuestion:
    """HITL 구조화 질문. id는 서버가 부여(q1, q2…)."""
    id: str
    question: str
    options: list[str]              # 빈 배열이면 자유 입력 전용
    allow_free_text: bool = True

@dataclass(frozen=True)
class ClarificationAnswer:
    """사용자 답변. answer==""는 무응답(D-부분답변 허용)."""
    question_id: str
    question: str                   # stateless 재구성용 에코백 (D8)
    answer: str = ""

@dataclass(frozen=True)
class BuildPlan:
    """Planner 산출 빌드 계획 — Composer 프롬프트 주입 단위."""
    requirement_summary: str        # 요구 재정리 (한국어 1~2문장)
    tool_hints: list[ToolDirectionHint]
    plan_summary: str               # 사용자 노출용 계획 요약 (1~3문장)
    confidence: float               # 0.0~1.0
```

### 2.2 PlannerPolicy — `domain/agent_composer/policies.py` (추가)

```python
class PlannerPolicy:
    CONFIDENCE_THRESHOLD: float = 0.8
    MAX_CLARIFICATION_ROUNDS: int = 2      # 질문 라운드 상한 (FR-04)
    MAX_QUESTIONS_PER_ROUND: int = 3

    @classmethod
    def clamp_round(cls, round_: int) -> int:
        """클라이언트 신고 라운드를 0..MAX 범위로 clamp (음수·과대값 방어)."""

    @classmethod
    def should_ask(cls, confidence: float, question_count: int, round_: int) -> bool:
        """질문 있음 AND confidence < 임계값 AND round < MAX → 질문 반환."""

    @classmethod
    def clamp_questions(cls, questions: list) -> list:
        """상위 MAX_QUESTIONS_PER_ROUND개만 유지."""
```

- 상수는 기존 `AutoAgentBuilderPolicy` 선례를 따르되 **agent_composer 도메인에 독립** 정의(경로 간 결합 금지). 임계값·상한을 settings로 옮길 필요가 생기면 UC 생성자 주입으로 확장(현 단계는 상수, config 하드코딩 아님 — 도메인 정책 상수는 허용 선례).

### 2.3 AgentPlanner — `application/agent_composer/planner.py` (신규)

```python
class _QuestionOutput(BaseModel):
    question: str
    options: list[str] = Field(default_factory=list, description="선택지 2~4개, 없으면 빈 배열")
    allow_free_text: bool = True

class _PlanOutput(BaseModel):
    requirement_summary: str
    tool_hints: list[_ToolHintOutput]      # capability, suggested_tool_ids, note
    plan_summary: str                      # 한국어 1~3문장, 사용자에게 그대로 노출
    confidence: float                      # 0.0~1.0
    clarifying_questions: list[_QuestionOutput] = []

class AgentPlanner:  # implements PlannerInterface
    def __init__(self, llm: ChatOpenAI, logger, max_candidates: int = 100): ...
    async def plan(
        self, user_request, candidates, request_id,
        current_config=None, history=None, answers=None,   # answers: list[ClarificationAnswer]
        round_=0,                          # G1: HITL 라운드 — trace metadata 기록용
    ) -> PlanResult:                       # (BuildPlan, questions: list[ClarifyingQuestion])
```

**프롬프트 구성** (시스템):

1. 역할: "에이전트 빌드 플래너 — 요구를 분석해 계획을 세우고, **초안 품질을 실질적으로 바꿀 정보만** 질문한다"
2. `[후보 도구]` 블록 — Composer와 동일 포맷. 기존 `AgentComposer._build_candidates_block`을 **모듈 함수 `build_candidates_block()`으로 추출**해 양쪽에서 재사용 (`composer.py`에 두고 import)
3. `[현재 에이전트 설정]` 블록 — edit 시(current_config 존재) Composer의 증분 수정 규칙과 동일 취지: "기존 구성 유지 전제로 변경분만 계획"
4. `[질문 규칙]`: 최대 3개, 각 질문에 선택지 2~4개 제시(가능하면), confidence ≥ 0.8이면 질문 금지, **무응답("")된 이전 질문은 다시 묻지 말고 합리적 기본값으로 가정**
5. 유저 메시지: history(clamp된 것) + `[이전 질문과 답변]` 블록(answers 존재 시: `Q: {question} / A: {answer or "무응답"}`) + user_request

**후처리** (Act-1 정정): Planner는 `_PlanOutput`→`BuildPlan` 매핑 시 임시 id(`q{i+1}`)를 부여하고 `PlannerPolicy.clamp_questions`를 적용해 **질문 상한을 Planner 계약으로 보장**한다(교체 구현체 대비). 최종 API 노출 id(`q{round}-{i}`)는 UseCase의 `_maybe_clarification`이 확정한다(UC의 clamp 재적용은 무해한 이중 방어). tool_hints의 tool_id는 검증하지 않는다(힌트일 뿐, 최종 검증은 기존 Composer 보정이 수행 — D5).

**관측**: `make_composer_tracer(tags=["agent-composer","planner"])`, run_name `plan:{name or 요청 프리뷰 30자}`, metadata에 round·request_id (round는 UC가 clamp한 값을 `plan(round_=...)`로 전달). 로그에 confidence·question_count·round.

### 2.4 PlannerInterface — `application/agent_composer/interfaces.py` (신규)

```python
class PlannerInterface(Protocol):
    async def plan(self, user_request, candidates, request_id,
                   current_config=None, history=None, answers=None) -> PlanResult: ...
```

`PlanResult`는 `NamedTuple(plan: BuildPlan, questions: list[ClarifyingQuestion])`. 후속 LangGraph 구현체도 이 Protocol만 만족하면 DI 교체로 대체 가능.

### 2.5 DTO 확장 — `application/agent_composer/schemas.py` (additive only)

```python
class ClarificationAnswerDto(BaseModel):
    question_id: str = Field(..., max_length=50)
    question: str = Field(..., min_length=1, max_length=500)   # 에코백 (D8)
    answer: str = Field("", max_length=1000)                   # ""=무응답

class ClarifyingQuestionDto(BaseModel):
    id: str
    question: str
    options: list[str] = Field(default_factory=list)
    allow_free_text: bool = True

class ComposeAgentRequest(BaseModel):
    # ... 기존 필드 불변 ...
    clarification_answers: list[ClarificationAnswerDto] | None = Field(None, max_length=6)
    clarification_round: int = Field(0, ge=0, le=10)   # 서버가 PlannerPolicy로 재clamp

class ComposeAgentDraftResponse(BaseModel):
    status: Literal["draft", "needs_clarification"] = "draft"
    questions: list[ClarifyingQuestionDto] = Field(default_factory=list)
    plan_summary: str = ""
    # ... 기존 필드 전부 불변 ...
```

**needs_clarification 응답 규약** (D7 — 하위호환 폴백 표현, Act-1 정정):
`status="needs_clarification"`, `questions=[...]`, `plan_summary=지금까지의 이해 요약`, `coverage="none"`, 초안 필드는 빈 값(단, `name_suggestion`은 요청 `name` 에코 — 폼 프리필 일관성), `notes="추가 정보가 필요합니다."` — status를 모르는 구형 소비자는 기존 coverage=none 흐름으로 안전 강하한다.

### 2.6 ComposeAgentUseCase 오케스트레이션 (수정)

```python
# Act-1 정정: planner는 마지막 optional 인자 — 미주입 시 기존 단발 compose와
# 동일 동작(기존 테스트 무수정 통과를 회귀 기준선으로 유지, G4)
def __init__(self, composer, tool_catalog_repo, ..., planner: PlannerInterface | None = None):

async def execute(self, request, request_id):
    llm_model_id = ...; candidates, fallback_note = ...; history = ...   # 기존
    round_ = PlannerPolicy.clamp_round(request.clarification_round)
    answers = [ClarificationAnswer(...) for a in request.clarification_answers or []]

    plan_result = await self._try_plan(request, candidates, history, answers, request_id)
    if plan_result and PlannerPolicy.should_ask(
        plan_result.plan.confidence, len(plan_result.questions), round_
    ):
        return self._to_clarification_response(request, plan_result, llm_model_id)

    output = await self._composer.compose(
        ..., plan=plan_result.plan if plan_result else None,   # 기존 인자 유지
    )
    draft = self._assemble_draft(...)                          # 기존 보정 불변
    return self._to_response(request, draft, llm_model_id,
                             plan_summary=plan_result.plan.plan_summary if plan_result else "")
```

- `_try_plan`: Planner 예외 시 `logger.warning("AgentPlanner failed — fallback to direct compose", exception=...)` 후 `None` 반환 (FR-08). ValueError로 전파하지 않는다 — 사용자 관점 기능 저하 없음.
- 함수 40줄 제한: 분기·응답 조립은 `_try_plan` / `_to_clarification_response` 프라이빗 메서드로 분리.

### 2.7 AgentComposer 계획 주입 (수정)

- `compose(..., plan: BuildPlan | None = None)` 파라미터 추가 (기본 None → 기존 동작 완전 동일).
- plan 존재 시 시스템 프롬프트에 부착:

```
[빌드 계획]
- 요구 요약: {requirement_summary}
- 역량→도구 방향: {capability}: {suggested_tool_ids} ({note}) …
- 계획: {plan_summary}

[계획 준수 규칙]
- 위 계획을 따르되, 후보 목록에 없는 도구는 여전히 사용 금지.
- 계획과 사용자의 명시적 최신 요청이 충돌하면 사용자 요청이 우선.
```

- `_build_candidates_block`을 모듈 함수로 추출(§2.3)하되 시그니처·출력 포맷 불변 — 기존 composer 테스트 무수정 통과가 기준.

### 2.8 DI 배선 — `api/main.py` `create_agent_composer_factories()` (수정)

```python
llm = ChatOpenAI(model=settings.openai_llm_model, ...)      # 기존 인스턴스
composer = AgentComposer(llm=llm, ...)
planner = AgentPlanner(llm=llm, logger=app_logger,          # D6: 동일 모델 재사용
                       max_candidates=settings.composer_max_candidates)
# compose_factory 내부: ComposeAgentUseCase(composer=composer, planner=planner, ...)
```

라우터·엔드포인트·인증 변경 없음.

### 2.9 백엔드 테스트 (TDD, 선행 작성)

| 파일 | 검증 |
|------|------|
| `tests/domain/agent_composer/test_planner_policy.py` | should_ask 행렬(임계값 경계·질문 0개·라운드 소진), clamp_round 음수/과대, clamp_questions |
| `tests/application/agent_composer/test_agent_planner.py` | 프롬프트 조립(후보 블록·current_config 블록·이전 Q/A "무응답" 표기), _PlanOutput→BuildPlan 매핑, 질문 id 부여, tracer config |
| `tests/application/agent_composer/test_compose_use_case_planner.py` | ① 저신뢰→needs_clarification 응답(coverage none·빈 초안), ② 답변 동봉 재호출→plan 주입 compose, ③ 라운드 소진→질문 있어도 강제 진행, ④ Planner 예외→폴백 compose(plan=None), ⑤ `clarification_*` 미전송 기존 요청 → planner 경유하되 계약 동일 |
| 기존 `test_compose_agent_use_case*` 등 | **무수정 통과** (하위호환 기준선) |

Mock 규약: Planner/Composer는 AsyncMock, LLM 실호출 없음. Windows 이벤트 루프 teardown 산발 실패 이력 → 격리 실행으로 검증.

---

## 3. 프론트엔드 설계

### 3.1 타입 동기화 — `types/agentComposer.ts` (추가)

```typescript
export type ComposeStatus = 'draft' | 'needs_clarification';
export interface ClarifyingQuestion { id: string; question: string; options: string[]; allow_free_text: boolean; }
export interface ClarificationAnswer { question_id: string; question: string; answer: string; }
// ComposeAgentRequest += clarification_answers?: ClarificationAnswer[] | null; clarification_round?: number;
// ComposeAgentDraftResponse += status: ComposeStatus; questions: ClarifyingQuestion[]; plan_summary: string;
// FixChatMessage += questions?: ClarifyingQuestion[]; answered?: boolean;
```

서비스(`agentComposerService`)·훅(`useComposeAgent`)은 시그니처 무변경(같은 엔드포인트).

### 3.2 ClarifyQuestionCard — `components/agent-builder/fix/ClarifyQuestionCard.tsx` (신규)

- props: `{ questions, planSummary, answered, onSubmit(answers: ClarificationAnswer[]) }`
- 질문별: 선택지 버튼(단일 선택 토글) + `allow_free_text`면 자유 입력란. 선택지 클릭 후 자유 입력 시 자유 입력 우선.
- **부분 답변 허용**: 제출 버튼은 항상 활성, 미답변 질문은 `answer: ""`로 제출 (확정 결정)
- 제출 후 `answered=true` → 카드 비활성 + "답변 완료" 배지 (재제출 방지, mutation-pending-guard 선례처럼 isPending 중 disabled)
- 카드 상단에 planSummary("지금까지 이해한 내용") 표시

### 3.3 FixAgentPanel 흐름 확장 (수정)

```
onSuccess(res):
  if res.status === 'needs_clarification':
    push assistant message { questions: res.questions, planSummary }
    save pendingClarify = { userRequest: 직전 전송 문장, round: 다음 라운드 번호 }
  else: 기존 초안 카드 push
handleAnswerSubmit(answers):
  composeMutation.mutate({
    user_request: pendingClarify.userRequest,      // 원 요청 그대로 재전송 (stateless)
    current_config: 현재 폼 스냅샷(최신),           // 기존 로직 재사용
    history: buildHistory(),
    clarification_answers: answers,
    clarification_round: pendingClarify.round,
  })
  질문 메시지 answered=true 마킹 + 답변 요약을 history용 user 턴 텍스트로 추가
    (예: "①여신심사 / 무응답 / 최신 문서만" — 500자 clamp 인지)
```

- `새 대화` 시 pendingClarify 초기화. 에러 응답 시 기존 에러 메시지 흐름 재사용.
- round는 패널이 관리(응답에 라운드 없음): 최초 0 전송 → needs_clarification 수신 시 다음 제출 round=1 → 재수신 시 2. 서버가 상한 clamp하므로 어긋나도 안전.

### 3.4 ComposeDraftCard — plan_summary 섹션 (수정)

- 헤더(이름+coverage 배지) 바로 아래, `plan_summary`가 비어있지 않으면 **"빌드 계획" 별도 섹션** 렌더 (확정 결정): 좌측 보더 강조의 정적 블록, 1~3문장. 기존 notes·도구 칩·프롬프트 접기 구조 불변.

### 3.5 프론트 테스트 (Vitest + MSW + RTL)

| 파일 | 검증 |
|------|------|
| `ClarifyQuestionCard.test.tsx` | 선택지 토글·자유 입력, 부분 답변 제출 페이로드(미답변 `""`), answered 비활성 |
| `FixAgentPanel.test.tsx` (확장) | needs_clarification → 질문 카드 렌더, 답변 제출 시 2차 요청 페이로드(원 요청 재전송·answers·round), draft 응답 시 plan_summary 섹션, 기존 시나리오 회귀 |
| MSW | (Act-1 정정) 공용 handlers.ts 확장 대신 **테스트 파일 내 `server.use` 로컬 오버라이드**로 status 분기 variant 구성 — 테스트 격리성 우선 (파일별 server.listen 3종 훅 규약 유지) |

프리플라이트: `npm test -- --pool=threads` (Windows forks 타임아웃 선례).

---

## 4. 구현 순서

1. [BE] `test_planner_policy.py` → PlannerPolicy (Red→Green)
2. [BE] `test_agent_planner.py` → AgentPlanner + PlannerInterface + build_candidates_block 추출
3. [BE] `test_compose_use_case_planner.py` → UseCase 오케스트레이션 + DTO 확장
4. [BE] Composer plan 주입 + main.py DI + 기존 테스트 전체 회귀
5. [FE] 타입 동기화 (/api-contract-sync)
6. [FE] ClarifyQuestionCard (테스트 먼저)
7. [FE] FixAgentPanel 흐름 + ComposeDraftCard plan_summary + MSW variant
8. 회귀: 백엔드 pytest 격리 실행, 프론트 `--pool=threads`, 기존 테스트 무수정 통과 확인

---

## 5. 설계 결정 기록

| # | 결정 | 근거 |
|---|------|------|
| D1 | stateless HITL — 상태는 요청 페이로드로 왕복 | Plan 확정. 서버 세션·DB 0, compose 무저장 원칙 유지 |
| D2 | Planner→Composer 2단계, Protocol 뒤 DI | Plan 확정. LangGraph interrupt 구현체로 교체 가능한 경계 |
| D3 | 구조화 질문 카드 + **부분 답변 허용** (미답변="") | 사용자 확정. 모르는 질문 강요 금지, Planner가 기본값 가정 |
| D4 | create+edit 모두, current_config 유무로 계획 분기 | Plan 확정 |
| D5 | BuildPlan은 **방향 힌트만** — 도구 최종 결정·검증은 Composer+기존 서버 보정 | 사용자 확정. 계획-조합 책임 분리, 오판 복구 경로 유지 |
| D6 | Planner LLM은 Composer와 **동일 ChatOpenAI 인스턴스 재사용** | 사용자 확정. 설정 변경 0, 추후 settings 분리 여지 |
| D7 | needs_clarification 시 coverage="none"+빈 초안으로 표현 | status 모르는 구형 소비자의 안전 강하 (additive 계약) |
| D8 | 질문 텍스트를 답변 DTO에 **에코백** | 세션이 없으므로 서버가 Q/A 맥락을 요청만으로 재구성 |
| D9 | PlannerInterface를 application 레이어에 배치 | 파라미터가 application DTO 포함 — domain에 두면 역참조 위반 |
| D10 | Planner 실패 시 plan=None 폴백, 예외 전파 금지 | Fix 탭 가용성 우선 (FR-08) |

---

## Next Step

`/pdca do fix-agent-planner-hitl` — 구현 순서 §4를 따라 TDD로 진행.
