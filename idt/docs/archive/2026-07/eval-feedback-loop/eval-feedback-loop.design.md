# eval-feedback-loop Design Document

> **Plan**: `docs/01-plan/features/eval-feedback-loop.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-21
> **Status**: Draft (rev1 — 2026-07-21 사용자 결정: bare 👎 추측 추출 제거, **이유(comment) 있는 👎만 트리거** + 프론트 이유 수집 UI 추가)
> **소스 기준**: master 실코드 (eval/use_cases.py:41 SubmitFeedbackUseCase · memory/extraction_service.py:39 kickoff · memory/interfaces.py:21 extract · infrastructure/memory/extractor.py:69 · general_chat/use_case.py:747 _persist_messages turn 페어링 · api/main.py:4058 eval DI · config.py:177 · idt_front useMessageFeedback.ts:18 — submit이 이미 comment? 수용)

---

## 1. Plan 이월 결정 5건 — 확정

| # | 결정 | 확정안 | 근거 (실측) |
|---|------|--------|------|
| ① | Q/A 복원 경로 | **기존 `find_by_session` 재사용** — assistant 메시지 `find_by_id` → 같은 세션 목록에서 `turn_index-1`·role=USER 매칭. 신규 repo 메서드 0 | `_persist_messages`가 user=N+1, assistant=N+2로 저장(use_case.py:765,771) — 직전 turn이 항상 질문. 페어 불일치(role≠USER 등)면 skip+warning (FR-02) |
| ② | 부정 맥락 전달 | **`extract()`에 additive optional `feedback_note: str \| None = None`** — HumanMessage에 `[사용자 평가 신호]` 블록 추가, 시스템 프롬프트 무변경 | 기존 호출부(위치 인자) 무변경으로 회귀 0. 별도 메서드는 파싱·절단 로직 중복, 접두 방식은 절단(EXTRACT_INPUT_MAX)에 잘릴 위험 |
| ③ | pending cap 상호작용 | **동일 cap 적용** (우회 없음) | cap은 승인 적체 방어 장치 — 우회 시 취지 훼손. skip은 기존 debug 로그로 관찰 가능, 승인 처리로 자연 해소 |
| ④ | 후보 provenance | **표시 없음** — `source_run_id=None`, info 로그에 message_id 기록 | run_id 해석은 `find_runs_by_user_message`(user 메시지 키) 추가 조회+repo DI 증가 대비 가치 낮음. 마이그레이션 0 유지 |
| ⑤ | 트리거 위치·조건 | **SubmitFeedbackUseCase 내부** — optional 의존성(`extraction=None`) 주입. 트리거는 **comment 있는 down 저장**(신규 down·rating 전이·comment 변경)일 때만 — bare 👎는 통계만, 동일 comment 재제출은 재트리거 금지 | 라우터 비즈니스 로직 금지 규칙 + optional 의존성 무회귀 패턴(agent-memory 선례). **rev1**: 이유 없는 👎로 LLM이 원인을 추측하는 것은 할루시네이션 소스 — 사용자가 말한 이유가 있을 때만 추출 |
| ⑥ | 이유 수집 UI (rev1 신규) | **MessageFeedback.tsx 확장** — 👎 활성 시 이유 칩(부정확함·질문과 무관·근거 부족·형식 불만) + 자유 코멘트 입력 노출, 제출은 기존 `submit.mutate({rating:'down', comment})` upsert 재사용 | `useSubmitFeedback`이 이미 `comment?` 파라미터 보유(훅·서비스·API 무변경). 서버 취소 규칙(같은 rating + comment None → 삭제)과 충돌 없음 |

## 2. Architecture

```
[프론트] MessageFeedback.tsx (확장 — rev1)
  👎 클릭 → submit({rating:'down'}) 즉시(통계) → 이유 패널 노출
  칩 클릭/코멘트 제출 → submit({rating:'down', comment}) upsert
  (훅·서비스·타입·API 무변경 — comment? 이미 존재)

[트리거] SubmitFeedbackUseCase.execute
  (rating=down + comment 존재 + 이전 상태와 다름 → 저장 성공 시만)
  ├─ extraction 미주입 or feedback_enabled=False → 기존 경로 그대로 (조회 0회 추가)
  └─ on: Q/A 복원(find_by_id 재사용 + find_by_session 1회) → kickoff_feedback()
                                                              │ sync 즉시 반환
[백그라운드] MemoryExtractionService (기존 싱글톤 재사용)
  kickoff_feedback(user_id, question, answer, feedback_note, request_id)
    → _run_guarded(..., feedback_note)  ← 실패 warning 격리(평가 저장 무관)
    → pending cap 검사(동일) → extract(feedback_note=...) → dedup·validate
    → PENDING 저장 (active 직행 금지 — 기존 흐름 합류)

[설정] eval_feedback_extraction_enabled: bool = False   ← 독립 opt-in
  (memory_extraction_enabled 매 턴 추출과 별개 — 둘 다 off 기본)

[DB] 마이그레이션 0 (comment VARCHAR(500)·기존 memory 테이블 재사용)
```

## 3. Detailed Design

### 3-1. config (`src/config.py`)

```python
# eval-feedback-loop: 부정 평가 트리거 추출 — 매 턴 추출과 독립 opt-in
eval_feedback_extraction_enabled: bool = False
```

### 3-2. 추출 계약 확장 (`src/application/memory/interfaces.py`)

```python
async def extract(
    self, question: str, answer: str, existing_contents: list[str],
    request_id: str, feedback_note: str | None = None,   # ← additive, 기본 None
) -> list[MemoryCandidate]: ...
```

`MemoryCandidateExtractor.extract`: `feedback_note`가 있으면 HumanMessage 끝에 블록 추가 —

```
[사용자 평가 신호]
사용자가 이 답변에 '싫어요'를 누르고 이유를 남겼습니다: "{comment}"
이 이유가 드러내는 사용자 선호(preference)·용어 교정(domain_term)을 우선 추출하세요.
이유에 없는 원인을 추측하지 마세요.
```

(rev1: comment가 트리거 전제조건이므로 이유는 항상 존재 — 추측 금지 지시 포함)

시스템 프롬프트·파싱·절단(EXTRACT_INPUT_MAX)은 무변경. 블록은 절단 **후** 부착(신호 유실 방지).

### 3-3. MemoryExtractionService (`src/application/memory/extraction_service.py`)

- 생성자 additive kwarg: `feedback_enabled: bool = False` + 읽기 프로퍼티 `feedback_enabled`
- 신규 `kickoff_feedback(user_id, question, answer, feedback_note, request_id)` — `feedback_enabled=False`면 no-op, on이면 기존 `_run_guarded`에 `feedback_note` 전달 (fire-and-forget·`_tasks` 보관 동일)
- `_run_guarded/_extract_and_store`에 optional `feedback_note=None` 스레딩 — 기존 `kickoff`는 None 전달(무변경 동작). 피드백 경로는 `_spawn`→`_run_guarded` 직행이므로 `run()` 래퍼(테스트·매 턴 전용)는 확장하지 않음
- 저장 성공 info 로그에 `trigger="feedback"`·message_id 포함 (provenance 결정 ④)

### 3-4. SubmitFeedbackUseCase (`src/application/eval/use_cases.py`)

```python
def __init__(self, feedback_repo, message_repo, logger,
             extraction: MemoryExtractionService | None = None):  # ← optional
```

`execute` down 저장(upsert 성공) 직후:

```python
# rev1 결정 ⑤: comment 있는 down + 이전 상태와 다를 때만 (bare 👎·동일 재제출 제외)
should_trigger = (
    parsed == Rating.DOWN
    and comment is not None and comment.strip()
    and (existing is None
         or existing.rating != Rating.DOWN
         or existing.comment != comment)
)
if should_trigger and self._extraction is not None and self._extraction.feedback_enabled:
    await self._kickoff_feedback_extraction(message, comment, request_id)
```

`_kickoff_feedback_extraction`: `_resolve_agent_id`에서 이미 조회한 assistant `message` 재사용(재조회 금지) → `find_by_session(message.user_id, message.session_id)`에서 `turn_index == assistant.turn_index - 1`·role=USER 매칭 → 실패 시 warning 후 return(평가 저장 유지, FR-02) → 성공 시 `kickoff_feedback(message.user_id.value, question, answer, note, request_id)`. `note`는 코멘트 포함 문자열. **메모리 소유자는 대화 소유자(`message.user_id`)** — 평가자와 동일인 전제(본인 대화만 평가).

주의: `_resolve_agent_id`가 반환을 agent_id 문자열에서 **message 엔티티로 확장**(내부 헬퍼라 시그니처 조정 가능) — 호출부 1곳 동반 수정.

### 3-5. DI (`src/api/main.py`)

- `get_memory_extraction_service()` 생성부에 `feedback_enabled=settings.eval_feedback_extraction_enabled` 추가 (2185행 부근)
- `_eval_submit_f`에 `extraction=get_memory_extraction_service()` 주입 (4058행 부근) — "off여도 주입은 항상(코드 경로 단일화)" 기존 주석 원칙 계승

### 3-6. 프론트 — 이유 수집 UI (`idt_front/src/components/chat/MessageFeedback.tsx`, rev1)

- 👎 클릭: 기존대로 `submit.mutate({rating: 'down'})` 즉시 제출(통계 반영) — 무변경
- `current === 'down'`이면 이유 패널 렌더:
  - 칩 4종(단일 선택 즉시 제출): `부정확함` · `질문과 무관` · `근거 부족` · `형식/톤 불만` → `submit.mutate({rating: 'down', comment: 칩라벨})`
  - 자유 코멘트 input + 보내기 버튼 → `submit.mutate({rating: 'down', comment: text})` (공백만이면 미전송)
  - 이미 이유 제출됨(`data?.comment`): 패널 대신 "이유: {comment}" 표시 + 수정 버튼(패널 재오픈)
- 취소 토글 보존: 👎 재클릭(comment 미포함) → 서버가 행 삭제(이유 포함) → 패널 닫힘
- 서비스·타입·상수 무변경 — `useSubmitFeedback`의 `comment?`·`MyFeedback.comment` 기존 필드 사용
- 훅 1건 결함 수정 포함(Do 중 발견): `useSubmitFeedback`의 전역 싱글톤 queryClient 참조를 `useQueryClient()`로 전환 — Provider 클라이언트와 불일치 시 캐시 갱신 유실 결함 해소, 공개 API 무변경
- 접근성: 패널 `role="group"` + `aria-label="싫어요 이유"`, 칩은 `aria-pressed`

## 4. 테스트 설계 (TDD 순서)

| # | 파일 | 케이스 |
|---|------|--------|
| T1 | `tests/application/eval/test_use_cases.py` (확장) | down+comment 신규 → kickoff_feedback 호출(질문·답변·이유 전달) / 기존 down에 comment 추가 → 호출 / up→down+comment → 호출 / **bare down → 미호출** / 동일 comment 재제출 → 미호출 / down 재클릭(취소) → 미호출 / up 저장 → 미호출 / extraction 미주입·off → 미호출(기존 경로 동일) / 직전 user 메시지 부재 → warning + 평가 저장은 성공 |
| T2 | `tests/application/memory/test_extraction_service.py` (확장) | kickoff_feedback off → no-op / on → extract에 feedback_note 전달·PENDING 저장 / cap 도달 → skip(동일 정책) |
| T3 | `tests/infrastructure/memory/test_extractor.py` (확장) | feedback_note 있으면 HumanMessage에 평가 블록(이유 원문 포함)·없으면 기존 프롬프트 바이트 동일 |
| T4 | 회귀 | 기존 eval 30건·memory·general_chat 스위트 무수정 통과 (`-p no:randomly` 격리 실행) |
| T5 | `MessageFeedback.test.tsx` (확장) | 👎 클릭 → 이유 패널 노출 / 칩 클릭 → comment 포함 제출 / 자유 코멘트 제출 / comment 존재 시 "이유:" 표시 / 👎 재클릭 취소 → 패널 닫힘 / 기존 3케이스 무수정 통과 (MSW per-file 훅·`--pool=threads`) |

## 5. 구현 순서

1. T3 → 3-2 extractor(계약+프롬프트) — Red→Green
2. T2 → 3-3 서비스(kickoff_feedback·스레딩) — Red→Green
3. T1 → 3-4 UseCase(comment 가드·Q/A 복원) — Red→Green
4. 3-1 config + 3-5 DI 배선 + 백엔드 회귀 T4
5. T5 → 3-6 프론트 이유 수집 UI — Red→Green + 프론트 회귀

## 6. 영향 범위 / 주의

- **백엔드 수정 6**: config.py · memory/interfaces.py · memory/extractor.py · memory/extraction_service.py · eval/use_cases.py · api/main.py (+테스트 3 확장)
- **프론트 수정 2**: MessageFeedback.tsx (+test 확장) · useMessageFeedback.ts(useQueryClient 결함 수정) — 서비스·타입·API 상수 무변경
- 마이그레이션 0 · 신규 라우트 0 · API 계약 무변경(comment 필드 기존 존재 — api-contract-sync 불필요)
- `extract()` 시그니처는 additive 기본값 — 기존 mock(위치 인자) 호출 무변경
- 레이어 준수: application(eval)→application(memory) 참조는 UseCase→Service 허용 범위(기존 general_chat→MemoryExtractionService 선례와 동형)
- 서버 취소 규칙 주의: 👎 재클릭 취소는 이유(comment)도 함께 삭제(행 삭제) — 의도된 동작(평가 철회 = 이유 철회)
