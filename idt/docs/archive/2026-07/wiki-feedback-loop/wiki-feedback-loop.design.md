# wiki-feedback-loop Design Document

> **Plan**: `docs/01-plan/features/wiki-feedback-loop.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-21
> **Status**: Draft
> **소스 기준**: master 실코드 (wiki/entity.py:16 CONVERSATION 예약석 · policies.py refs_key·validate_for_creation·PATH 규칙 · distill_use_case.py dedup 멱등 선례 · wiki_distiller.py from_openai 패턴 · eval/use_cases.py 트리거+Q/A 복원 · value_objects.py:45 SUPER_AGENT_ID="super" · WikiPage/index.tsx:20 agent_id 자유 입력 · types/wiki.ts:8 'conversation' 기존 정의 · main.py:3428 wiki DI)

---

## 1. Plan 이월 결정 6건 — 확정

| # | 결정 | 확정안 | 근거 (실측) |
|---|------|--------|------|
| ① | 위키 귀속 agent_id | **`message.agent_id` 그대로 저장** (general-chat → `"super"`) | WikiPage는 agent_id 자유 텍스트 입력(index.tsx:20,44) — admin이 "super" 입력으로 조회·승인 가능. 스킵하면 현재 유일한 트리거 경로(general-chat)에서 기능이 죽음. wiki 테이블 agent_id는 문자열 스코프 키(FK 없음) |
| ② | 정제 계약 | **신규 `FeedbackWikiDistillerInterface`** — `distill_feedback(question, answer, feedback_note, request_id) -> FeedbackWikiDraft \| None` (None=승격 가치 없음) | 기존 `WikiDistillerInterface`는 WikiSourceGroup(청크 그룹) 입력 — Q/A+이유를 어댑팅하면 topic_hint/texts 의미 왜곡. 판정+정제를 LLM 1회로 통합(비용 상한) |
| ③ | 트리거 배선 | **신규 `FeedbackWikiService`**(MemoryExtractionService 동형 launcher) + SubmitFeedbackUseCase에 두 번째 optional 의존성. **Q/A 복원 1회를 memory·wiki 팬아웃이 공유** | optional 의존성 무회귀 패턴 검증됨(eval-feedback-loop). 복원 조회 중복 방지 — `_kickoff_feedback_fanout`으로 트리거 지점 단일화(40줄 규칙 준수) |
| ④ | path 분류 | **고정 `"피드백"`** | 승인 큐에서 트리 노드로 묶여 가시성 확보. PATH 규칙(1 segment·30자 이하) 통과. distill의 collection_name path 선례와 동형(출처별 기본 분류) |
| ⑤ | confidence | **LLM 판정 점수 매핑** — 0~100 정수 응답 → /100 → `WikiPolicy.clamp_confidence`. 부재·파싱 실패 시 0.5 | entity 기본값 0.5와 정합, 승인 큐 정렬 신호로 활용 가능 |
| ⑥ | 프론트 배지 | **diff 0 — 변경 없음** | `WIKI_SOURCE_TYPES`에 'conversation' 기존 정의(types/wiki.ts:8), 렌더는 raw 문자열(`WikiArticleTable.tsx:126`, `WikiDetailPanel.tsx:97`) — 신규 값이 자연 표시됨 |

## 2. Architecture

```
[트리거] SubmitFeedbackUseCase.execute (comment 있는 down + 이전 상태와 다름 — eval-feedback-loop 가드 재사용)
  └─ _kickoff_feedback_fanout: Q/A 복원 1회(_find_question) 후
       ├─ memory:  extraction.kickoff_feedback(...)      (기존 — 무변경)
       └─ wiki:    wiki_feedback.kickoff_draft(...)      (신규, 독립 플래그)
                    │ sync 즉시 반환 (fire-and-forget)
[백그라운드] FeedbackWikiService (신규 — MemoryExtractionService 동형)
  1) dedup: repo.find_by_agent(agent_id) → refs_key("feedback:{message_id}") 기존 존재 시
     LLM 호출 전 스킵 (distill 멱등 선례, FR-04)
  2) LLM 판정+정제 1회: FeedbackWikiDistiller → None(가치 없음)이면 종료 (FR-02)
  3) WikiArticle(draft, CONVERSATION, refs=[feedback:{id}], path="피드백",
     confidence=판정 점수) 구성 → WikiPolicy.validate_for_creation 통과분만
  4) 짧은 세션 + session.begin() 명시 트랜잭션으로 repo.save (쓰기 세션 교훈)
  실패 전부 warning 격리 — 평가 저장·memory 환류에 무영향 (FR-06)

[설정] wiki_feedback_draft_enabled: bool = False   ← memory 환류와 독립 opt-in
[승인] 기존 흐름 그대로 — WikiPage(agent_id="super" 입력) → draft 목록 → 승인 → 검색 노출
[프론트] diff 0 · [DB] 마이그레이션 0 (source_type 문자열, enum 값 기존 정의)
```

## 3. Detailed Design

### 3-1. config (`src/config.py`)

```python
# wiki-feedback-loop: 이유 있는 👎 → 위키 draft 환류 — memory 환류와 독립 opt-in
wiki_feedback_draft_enabled: bool = False
```

LLM 모델은 기존 distiller와 동일하게 `settings.openai_llm_model` 재사용(신규 설정 0).

### 3-2. 계약 (`src/application/wiki/interfaces.py` · `schemas.py`)

```python
@dataclass
class FeedbackWikiDraft:
    title: str
    content: str
    confidence: float  # 0.0~1.0 (LLM 판정 점수 /100, clamp)

class FeedbackWikiDistillerInterface(ABC):
    @abstractmethod
    async def distill_feedback(
        self, question: str, answer: str, feedback_note: str, request_id: str,
    ) -> FeedbackWikiDraft | None:
        """팀 일반화 가치가 없으면 None(강제 생성 금지)."""
```

### 3-3. FeedbackWikiDistiller (`src/infrastructure/wiki/feedback_distiller.py` 신규)

- `WikiDistiller` 동형: LLM 주입 + `from_openai` 팩토리 + `_coerce_text` 정규화
- 프롬프트(요지): 사용자 질문/답변/불만 이유를 주고 — "**팀 전체에 유효한 일반 지식**(용어 정의·사실 교정·정책/규정)만 추출. 개인 선호·일회성 불만·추측이면 `{"worthy": false}`. worthy면 `{"worthy": true, "title": ..., "content": ..., "confidence": 0~100}` JSON만 출력. 이유에 없는 원인을 추측하지 말 것"
- 파싱 실패·비JSON·worthy=false → None + warning (memory extractor `_parse` 선례)
- title 200자 절단(`_TITLE_MAX` 선례), content는 정책 검증에 위임

### 3-4. FeedbackWikiService (`src/application/wiki/feedback_service.py` 신규)

MemoryExtractionService 동형 launcher:

```python
def __init__(self, session_factory, distiller, logger, *,
             enabled: bool, repo_builder: Callable | None = None): ...
@property
def enabled(self) -> bool: ...
def kickoff_draft(self, agent_id, message_id: int, question, answer,
                  feedback_note, request_id) -> None:   # off면 no-op, sync 반환
```

백그라운드 `_run_guarded` 순서: ① 짧은 세션으로 `find_by_agent(agent_id)` → `WikiPolicy.refs_key(["feedback:{message_id}"])` 기존 키 집합 대조, 존재 시 debug 로그 후 종료 ② `distill_feedback` (세션 밖 — DB 점유 없음) ③ None이면 종료 ④ WikiArticle 구성(`id=uuid4`, `status=DRAFT`, `source_type=CONVERSATION`, `path="피드백"`) + `validate_for_creation`/`validate_path` 위반 시 warning 스킵 ⑤ 짧은 세션 + `session.begin()`으로 `repo.save` ⑥ info 로그(`trigger="feedback"`, message_id, article_id). 예외 전부 warning 격리.

### 3-5. SubmitFeedbackUseCase 팬아웃 (`src/application/eval/use_cases.py`)

- `__init__`에 optional `wiki_feedback: FeedbackWikiService | None = None` 추가
- 기존 `_should_trigger_extraction` → **순수 조건 `_is_actionable_negative`**(rating·comment·전이 판정)로 개명, 서비스별 enabled 체크는 팬아웃에서:

```python
if self._is_actionable_negative(parsed, comment, existing):
    await self._kickoff_feedback_fanout(message, comment, request_id)

async def _kickoff_feedback_fanout(self, message, comment, request_id):
    memory_on = self._extraction is not None and self._extraction.feedback_enabled
    wiki_on = self._wiki_feedback is not None and self._wiki_feedback.enabled
    if not (memory_on or wiki_on):
        return  # 복원 조회 0회 — off 경로 기존 동일 (FR-05)
    question = await self._find_question(message)   # 1회 공유
    if question is None:
        warning 후 return                            # FR-02 선례
    if memory_on: self._extraction.kickoff_feedback(...)
    if wiki_on:   self._wiki_feedback.kickoff_draft(...)
```

- 기존 memory 단독 경로와 동작 동일(호출 순서·인자 불변) — eval-feedback-loop 테스트 무수정 통과가 회귀 기준

### 3-6. DI (`src/api/main.py`)

- `FeedbackWikiService` lazy 싱글톤(`get_feedback_wiki_service`) — 기존 `_make_distiller`와 동일하게 `FeedbackWikiDistiller.from_openai(settings.openai_llm_model, ...)`, `session_factory=get_session_factory()`, `enabled=settings.wiki_feedback_draft_enabled`, repo_builder는 기존 `_make_repo` 패턴(WikiArticleRepository) 재사용
- `_eval_submit_f`에 `wiki_feedback=get_feedback_wiki_service()` 주입 — "off여도 주입은 항상" 원칙 계승

## 4. 테스트 설계 (TDD 순서)

| # | 파일 | 케이스 |
|---|------|--------|
| T1 | `tests/infrastructure/wiki/test_feedback_distiller.py` (신규) | worthy JSON → FeedbackWikiDraft(제목·본문·confidence /100 clamp) / worthy=false → None / 불량 JSON → None+warning / 프롬프트에 질문·답변·이유 원문 포함 / title 200자 절단 |
| T2 | `tests/application/wiki/test_feedback_service.py` (신규) | enabled=False → no-op(세션 0회) / dedup: 동일 refs 존재 → distiller 미호출 / worthy 초안 → draft·CONVERSATION·refs·path="피드백" 저장 / distiller None → 저장 0건 / 불변식 위반(빈 content) → warning 스킵 / 예외 → warning 격리 / 세션 조회·저장 분리 |
| T3 | `tests/application/eval/test_use_cases.py` (확장) | wiki on+memory off → kickoff_draft만 호출(질문·답변·이유·agent_id 전달) / 둘 다 on → 복원(find_by_session) 1회 + 양쪽 호출 / 둘 다 off → 복원 조회 0회 / bare down → 미호출 / wiki 미주입 → 기존 동작 (기존 eval-feedback-loop 테스트 11건 무수정 통과) |
| T4 | 회귀 | wiki(distill·review·query)·eval·memory 스위트 무수정 통과 (`-p no:randomly`) |

## 5. 구현 순서

1. T1 → 3-2 계약 + 3-3 distiller — Red→Green
2. T2 → 3-4 서비스 — Red→Green
3. T3 → 3-5 팬아웃 리팩토링 — Red→Green (기존 11건 그린 유지 확인)
4. 3-1 config + 3-6 DI 배선
5. T4 회귀 일괄

## 6. 영향 범위 / 주의

- **신규 3**: feedback_distiller.py · feedback_service.py (+ 테스트 2) / **수정 4**: config.py · wiki/interfaces.py · wiki/schemas.py · eval/use_cases.py · api/main.py
- 마이그레이션 0 · 신규 라우트 0 · 프론트 diff 0 · API 계약 무변경
- 레이어: application(eval)→application(wiki) 참조는 UseCase→Service 허용(§eval-feedback-loop 선례) · infrastructure distiller는 application 인터페이스 구현(WikiDistiller 동형)
- 자동 승인 절대 금지 — `status=DRAFT` 하드코딩, 상태 전이는 기존 review_use_case만
- 쓰기 세션 `begin()` 필수(agent-memory-extraction 교훈) — repo.save가 flush만 하므로 명시 트랜잭션 없으면 조용히 미저장
- 팬아웃 개명(`_should_trigger_extraction`→`_is_actionable_negative`)은 내부 헬퍼 — 기존 테스트가 공개 동작만 검증하므로 무수정 통과 예상, 깨지면 리팩토링 회귀로 간주
