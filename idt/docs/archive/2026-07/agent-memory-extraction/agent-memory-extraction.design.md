# agent-memory-extraction Design Document (메모리 Phase 2)

> **Plan**: `docs/01-plan/features/agent-memory-extraction.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **소스 기준**: master 워킹트리 실코드 (general_chat/use_case.py:368-403 · section_summary/launcher.py · wiki/wiki_distiller.py · memory/* Phase 1 전체 정독)

---

## 1. Overview

Phase 2 범위: General Chat 답변 완료 후 백그라운드 LLM 추출 → `pending` 적재 → `/settings` 승인/거부 게이트. **마이그레이션 0** (Phase 1 예약 컬럼 status/source_run_id/confidence 사용).

### 1.1 Plan 이월 결정 5건 — 확정

| # | 결정 대상 | 확정안 | 근거 |
|---|-----------|--------|------|
| ① | 추출 입력 범위 | **마지막 턴만** (question + answer, 합산 4000자 초과 시 절단) | 비용 상수화. 이전 문맥은 요약·히스토리로 이미 반영, 반복 노출 사실은 다음 턴에 재기회 |
| ② | 추출 LLM | **WikiDistiller 선례** — LLM 객체 주입(테스트 mock) + `from_openai` 팩토리, config `memory_extraction_model_name`(기본 gpt-4o-mini) | distill과 동일 구조 — 경량 모델 고정, LangSmith 추적 일관 |
| ③ | pending 노출 API | **GET /memories에 `status` 쿼리(기본 active)** — 응답 형태 `{items,total,max_count}` 유지, pending 조회 시 max_count=pending 상한 | additive·기존 프론트 무수정. 잘못된 status는 422 |
| ④ | 근거 표시 | Phase 2는 **created_at + "대화에서 자동 추출" 뱃지만**. run 딥링크는 Phase 3 이월 | 사용자용 run 조회 API 부재(관측성 조회는 message 기준·admin 성향) — source_run_id는 DB에 기록되므로 후속에서 additive |
| ⑤ | 훅 위치 | **stream() 내부, `_finish_observability`(:388) 직후·ANSWER_COMPLETED yield 직전** — sync `kickoff()` 호출(즉시 반환) | run_id 접근 가능(관측성 연결 FR-03) + fire-and-forget이라 yield 지연 0. **chart-edit 조기 리턴 경로(:307)는 추출 제외**(도구 변환 턴 — 저장 가치 낮음) |

### 1.2 실코드 검증으로 확정된 선례

| 선례 | 내용 | 설계 반영 |
|------|------|----------|
| launcher 가드 패턴 | `_tasks: set` 보관(GC 방지) + `add_done_callback(discard)` + `_run_guarded` try/except error 로그 (`launcher.py:44-113`) | MemoryExtractionService 동일 구조 — 잡 테이블은 미도입(best-effort 허용 손실, Plan 리스크 확정) |
| LLM content 정규화 | `_coerce_text` 블록 리스트 대응 (`wiki_distiller.py:23`) | extractor 응답 파싱에 동일 적용 |
| optional 의존성 | Phase 1 `memory_assembler=None` 기본 — 기존 테스트 무수정 통과 | `memory_extractor=None` 동일 패턴 (FR-09: off/미주입 시 Phase 1과 100% 동일) |
| 404 은닉·_find_owned | `crud_use_case.py:87-93` | approve/reject 재사용 |
| 상태 전이 게이트 | wiki review(draft→approved만 허용) | MemoryPolicy.validate_transition — **pending만** approve/reject 가능, 그 외 ValueError→422 |

---

## 2. Architecture

```
[General Chat stream()]
  ... _persist_messages → _finish_observability
  → if memory_extractor: extractor.kickoff(user_id, question, answer, run_id, request_id)   # sync, 즉시 반환
  → ANSWER_COMPLETED / CHAT_DONE (지연 0)

[MemoryExtractionService (앱 싱글톤, application/memory/extraction_service.py)]
  kickoff() → enabled=False면 no-op → asyncio.create_task(_run_guarded)
  _run_guarded():                                # 모든 예외 warning 격리
    session_factory() 짧은 세션:
      existing = repo.find_by_user(user_id, [ACTIVE, PENDING])
      pending_count 상한 검사 (초과 시 debug 스킵, FR-08)
    candidates = extractor.extract(question, answer, existing, request_id)   # LLM 1회
    후보 필터: content 정확 일치(strip) dedup · max_per_turn 절단 · validate_content
    session_factory() 짧은 세션:
      Memory(status=PENDING, source_run_id=run_id, confidence=후보값, tier=0, scope=USER) 저장

[승인 게이트]
  PATCH /memories/{id}/approve → crud.approve: _find_owned → validate_transition(PENDING)
                                  → validate_active_count(승인 시 active 상한 검사) → status=ACTIVE
  PATCH /memories/{id}/reject  → crud.reject:  _find_owned → validate_transition(PENDING) → status=REJECTED
  GET   /memories?status=pending → 승인 대기 목록

[프론트 /settings]
  "AI가 기억하는 내용"(active — 기존) 위에 "승인 대기 N건" 섹션 조건부 렌더
    후보 카드: 타입 뱃지 + content + "대화에서 자동 추출 · {날짜}" + [승인][거부]
```

## 3. Detailed Design

### 3-1. Domain (additive)

**`MemoryPolicy` 확장** (`domain/memory/policies.py`):

```python
# Phase 2 추출 상수
EXTRACT_INPUT_MAX = 4000      # 결정 ①: question+answer 합산 절단
CONFIDENCE_MIN = 0
CONFIDENCE_MAX = 100

@staticmethod
def validate_transition(memory: Memory) -> None:
    """PENDING이 아닌 상태의 승인/거부 시도 → ValueError (라우터 422)."""

@staticmethod
def clamp_confidence(value: int) -> int:
    """LLM 자체 평가값을 0~100으로 clamp."""

@staticmethod
def dedup_candidates(candidates, existing_contents: set[str]) -> list:
    """content.strip() 정확 일치 제거 + 후보 내 중복 제거 (FR-04)."""
```

**추출 인터페이스** (`application/memory/interfaces.py` — WikiDistillerInterface 위치 선례):

```python
@dataclass
class MemoryCandidate:
    mem_type: str      # MemoryType value — 불량 값은 저장 전 검증 탈락
    content: str
    confidence: int

class MemoryExtractorInterface(ABC):
    async def extract(self, question, answer, existing_contents: list[str],
                      request_id) -> list[MemoryCandidate]: ...
```

### 3-2. Infrastructure — `MemoryCandidateExtractor` (`infrastructure/memory/extractor.py`)

- WikiDistiller 동형: `__init__(llm, logger)` + `from_openai(model_name, api_key, logger)` (temperature=0)
- 프롬프트: JSON 배열 `[{"mem_type","content","confidence"}]` 강제, 규칙 —
  ① 사용자에 대한 **지속적 사실만**(일회성 질문 내용 금지) ② 기존 메모리 목록과 중복 금지
  ③ **개인 식별 정보(주민번호·전화·계좌·이메일) 금지** ④ 저장 가치 없으면 빈 배열 `[]`
- 응답 파싱: `_coerce_text` → `json.loads` — 실패·비배열이면 warning 후 `[]` (FR-05·격리)

### 3-3. Application

**`MemoryExtractionService`** (`application/memory/extraction_service.py`) — launcher 가드 패턴:

```python
class MemoryExtractionService:
    def __init__(self, session_factory, extractor, logger, *,
                 enabled: bool, max_per_turn: int, pending_cap: int): ...

    def kickoff(self, user_id, question, answer, run_id: str | None, request_id) -> None:
        if not self._enabled: return                      # FR-09
        task = asyncio.create_task(self._run_guarded(...))
        self._tasks.add(task); task.add_done_callback(self._tasks.discard)

    async def _run_guarded(self, ...):
        try:  ... §2 흐름 ...
              self._logger.info("memory candidates extracted", saved=n, ...)
        except Exception as e:
            self._logger.warning("memory extraction failed (chat unaffected)",
                                 request_id=request_id, exception=e)   # FR-01
```

**`MemoryCrudUseCase` 확장** — 별도 ReviewUseCase 없음 (wiki와 달리 승인자=소유자=동일 인가 모델 → `_find_owned` 재사용이 최소 표면):

```python
async def list_by_status(self, user_id, status: MemoryStatus, request_id) -> list[Memory]
async def approve(self, user_id, memory_id, request_id) -> Memory
    # _find_owned → validate_transition → count_active + validate_active_count → ACTIVE
async def reject(self, user_id, memory_id, request_id) -> Memory
@property pending_cap  # 목록 응답 max_count용
```

**Repository additive** (interface + 구현): `find_by_user_and_status(user_id, status, request_id)`, `count_by_user_and_status(...)`. 기존 `find_active_by_user`는 무수정(주입 경로 회귀 0 — FR-06).

**general_chat 통합**: `__init__(..., memory_extractor=None)` + `:388` 직후:

```python
if self._memory_extractor is not None:
    self._memory_extractor.kickoff(
        request.user_id, request.message, answer,
        str(run_id) if run_id is not None else None, request_id,
    )
```

### 3-4. Interfaces

**라우터** (`memory_router.py` additive):

```python
GET  ""?status=active|pending   # 기본 active, 그 외 422. pending 시 max_count=pending_cap
PATCH "/{memory_id}/approve" → MemoryResponse   # 404 은닉 / 비pending 422
PATCH "/{memory_id}/reject"  → MemoryResponse
```

**config** (`config.py`):

```python
memory_extraction_enabled: bool = False        # 기본 off 배포 (Plan §2)
memory_extraction_model_name: str = "gpt-4o-mini"
memory_extraction_max_per_turn: int = 3
memory_max_pending_per_user: int = 20
```

**DI** (`main.py`): `get_memory_extraction_service()` lazy singleton (assembler 선례) — extractor는 `MemoryCandidateExtractor.from_openai(settings.memory_extraction_model_name, settings.openai_api_key, logger)`. general_chat factory에 `memory_extractor=` 주입. **enabled 판정은 서비스 내부** — off여도 주입 자체는 항상(코드 경로 단일화).

### 3-5. Frontend

- 계약: `MEMORY_APPROVE/REJECT(id)` 상수, `memoryService.getMemories(status?)`·`approve`·`reject`, 훅 `usePendingMemories`(= useMemories('pending'))·`useApproveMemory`·`useRejectMemory`(성공 시 `memories.all` invalidate — active·pending 동시 갱신), `queryKeys.memories.list(status?)`
- `types/memory.ts`: `MemoryStatus` 타입 추가 불필요(응답 형태 불변) — status는 쿼리 파라미터만
- SettingsPage: active 섹션 위에 **조건부 "승인 대기 N건" 섹션**(0건이면 미렌더) — 카드: 타입 뱃지 + content + `대화에서 자동 추출 · {created_at 날짜}` + [승인]/[거부] 버튼. 승인 시 active 상한 422는 기존 errorDetail 표면화 재사용
- MSW: GET status 쿼리 분기 + approve/reject 핸들러 2종

### 3-6. 사용자 흐름

```
(admin이 .env로 추출 on) → 사용자 채팅 "우리 팀은 여신심사팀이야, 한도 규정 알려줘"
→ 답변 후 백그라운드 추출 → pending 1건 → /settings "승인 대기 1건" → [승인]
→ 다음 질문부터 [사용자 메모리] 블록에 반영 → 거부한 후보는 rejected로 재노출 없음
```

---

## 4. Test Plan (TDD — Red 먼저)

| 파일 | 케이스 |
|------|--------|
| `tests/domain/memory/test_policies.py` 확장 | validate_transition(pending 통과/active·rejected 거부) · clamp_confidence · dedup_candidates(기존 일치/후보 내 중복/공백 차이) |
| `tests/application/memory/test_extraction_service.py` 신규 | enabled=False no-op · 후보 저장 시 PENDING+source_run_id+confidence · pending 상한 스킵(debug) · dedup 탈락 · max_per_turn 절단 · 불량 mem_type 탈락 · LLM 예외 시 warning+저장 0(FR-01) · 세션 호출마다 개폐 |
| `tests/application/memory/test_crud_use_case.py` 확장 | approve(정상→ACTIVE·active 상한 422·비pending 422·타인 404) · reject(→REJECTED) · list_by_status |
| `tests/infrastructure/memory/test_extractor.py` 신규 | 정상 JSON 파싱 · 블록 리스트 content · 불량 JSON→[] · 빈 배열 |
| `tests/infrastructure/memory/test_memory_repository.py` 확장 | find/count_by_user_and_status |
| `tests/api/test_memory_router.py` 확장 | GET ?status=pending(max_count=pending_cap) · 불량 status 422 · approve/reject 200/404/422 |
| `tests/application/general_chat/test_memory_injection.py` 확장 | extractor 주입 시 kickoff 호출(인자: user_id/question/answer/run_id) · None이면 미호출(회귀) · chart-edit 경로 미호출 |
| `useMemories.test.ts` 확장 | pending 조회 · approve/reject 훅 + invalidate |
| `SettingsPage/index.test.tsx` 확장 | pending 섹션 렌더(N건)·0건 미렌더 · 승인/거부 요청 · 승인 상한 422 표면화 |

## 5. Implementation Order

1. MemoryPolicy 확장(transition/clamp/dedup) + MemoryCandidate·인터페이스 — 정책 테스트 먼저
2. Repository additive 2메서드
3. MemoryCandidateExtractor (JSON 파싱 테스트 먼저)
4. MemoryExtractionService (서비스 테스트 먼저)
5. CrudUseCase approve/reject/list_by_status + 라우터 additive + config 4키 + main.py DI
6. general_chat kickoff 통합 — 회귀 0 확인
7. 프론트 계약(상수→서비스→훅) + SettingsPage pending 섹션 (MSW 테스트 먼저)
8. verify 스킬 3종 → `/pdca analyze agent-memory-extraction`

## 6. Plan 리스크 해소 매핑

| Plan 리스크 | 설계 해소 |
|-------------|-----------|
| pending 폭주 | 프롬프트 저장 가치 기준 + max_per_turn(3) + pending_cap(20, FR-08) |
| PII 추출 | 프롬프트 금지 지침 §3-2 ③ + 승인 게이트 자체가 사람 확인 — pii_masking 엔진 연동은 Phase 3 |
| LLM 비용 | 기본 off + gpt-4o-mini 고정 + 마지막 턴 4000자 절단 |
| 태스크 유실 | best-effort 명시 — launcher 가드(_tasks 보관·done_callback)로 GC 유실만 방지, 잡 테이블 미도입 |
| 세션 충돌 | _run_guarded 내 session_factory per-call 2회(조회/저장 분리 짧은 세션) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-20 | Initial draft — 이월 결정 5건 확정(마지막 턴·distiller 선례 LLM·status 쿼리·뱃지만·stream 훅), launcher/distiller/Phase1 선례 반영 | 배상규 |
