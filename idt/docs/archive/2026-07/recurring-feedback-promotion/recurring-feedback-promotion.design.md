# recurring-feedback-promotion Design Document

> **Plan**: `docs/01-plan/features/recurring-feedback-promotion.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-21
> **Status**: Draft
> **소스 기준**: master 실코드 (wiki/feedback_service.py `_distill_and_save` — find_by_agent 기수행·refs dedup · feedback_distiller.py worthy JSON 파싱 · schemas.py FeedbackWikiDraft · entity.py apply_edit(version+1 선례) · policies.py clamp_confidence · wiki_repository.py update()=load-then-mutate · WikiArticleTable.tsx:128 confidence 노출)

---

## 1. Plan 이월 결정 5건 — 확정

| # | 결정 | 확정안 | 근거 |
|---|------|--------|------|
| ① | 플래그 전략 | **신규 독립 opt-in `wiki_feedback_reinforce_enabled: bool = False`** — off면 기존 동작(항상 신규 draft) 바이트 동일, on이면 강화 | 사용자 확립 선호: 기존 동작 갈아끼우기 대신 신규 bool+분기+기준선 보존(교차검증). off/on 초안 생성 양상 비교로 오매칭률 실측 가능 |
| ② | match 반환 계약 | `FeedbackWikiDraft`에 **additive optional `match_id: str \| None = None`** + `distill_feedback`에 additive optional `candidates: list[tuple[str, str]] \| None = None`(id, title) | 기존 호출부·mock 무변경(additive 원칙). candidates=None이면 프롬프트 기존과 동일 |
| ③ | confidence 공식 | **`WikiPolicy.reinforce_confidence(current) = min(0.95, current + 0.1)`** — 상수 `REINFORCE_STEP=0.1`·`REINFORCE_CAP=0.95` | 단조 증가·승인 전 1.0 도달 금지. 정책 함수 1곳이라 로그 스케일 등으로 교체 용이. 지지 수는 len(refs)로 관측(공식 입력 아님 — 갱신 시점마다 +0.1 동치) |
| ④ | 후보 상한·정렬 | **updated_at desc 최근 20개** (서비스 상수 `_MATCH_CANDIDATES_MAX = 20`) — CONVERSATION + **DRAFT만** | 프롬프트 예산 상한. 이미 조회한 find_by_agent 결과에서 필터·정렬 — 추가 조회 0 |
| ⑤ | title 갱신 | **유지** (본문·제목 불변 — refs·confidence·version·updated_at만 변경) | 매칭 키 안정성 + 오매칭 시 피해 최소화. 본문 품질은 승인자 편집 몫 |

## 2. Architecture

```
[FeedbackWikiService._distill_and_save]  (wiki_feedback_draft_enabled on 전제)
  1) find_by_agent (기존 dedup 조회 재사용)
     ├─ refs dedup: feedback:{message_id} 기존재 → 종료 (기존 — FR-06 지지 수 인플레 방지)
     └─ reinforce on이면: 후보 = CONVERSATION+DRAFT, updated_at desc 상위 20 → (id, title)
  2) distill_feedback(..., candidates=후보 or None)   ← off면 None(프롬프트 기존 동일)
  3) draft.match_id 분기
     ├─ None            → 신규 draft 저장 (기존 동작 — FR-05)
     ├─ 후보 내 실재+DRAFT → 강화: article.add_support(ref, reinforce_confidence(cur), now)
     │                      → repo.update() (짧은 세션 + begin())  [FR-02]
     └─ 미실재·비DRAFT    → warning + 신규 draft 폴백 (오염 방지 — FR-04)

[설정] wiki_feedback_reinforce_enabled: bool = False (독립 opt-in — 결정 ①)
[프론트] diff 0 — confidence·version·refs 기존 노출이 우선순위 신호
[DB] 마이그레이션 0 — 지지 수 = len(source_refs)
```

## 3. Detailed Design

### 3-1. config (`src/config.py`)

```python
# recurring-feedback-promotion: 같은 주제 반복 👎 → 기존 draft 강화 — 독립 opt-in
wiki_feedback_reinforce_enabled: bool = False
```

### 3-2. 도메인 (`src/domain/wiki/entity.py` · `policies.py`)

```python
# entity — apply_edit 동형 (본문 불변, 지지 축적만)
def add_support(self, ref: str, confidence: float, now: datetime) -> None:
    """반복 피드백 지지 축적 — refs 추가·신뢰도 갱신·버전 증가 (제목·본문 불변)."""
    self.source_refs = [*self.source_refs, ref]
    self.confidence = confidence
    self.version += 1
    self.updated_at = now

# policy
REINFORCE_STEP = 0.1
REINFORCE_CAP = 0.95

@staticmethod
def reinforce_confidence(current: float) -> float:
    """지지 1회당 +STEP, CAP 클램프 — 승인 전 1.0 도달 금지."""
    return min(WikiPolicy.REINFORCE_CAP, current + WikiPolicy.REINFORCE_STEP)
```

### 3-3. 계약 확장 (`schemas.py` · `interfaces.py` · `feedback_distiller.py`)

- `FeedbackWikiDraft.match_id: str | None = None` (additive)
- `distill_feedback(..., candidates: list[tuple[str, str]] | None = None)` (additive)
- 프롬프트: candidates 있으면 HumanMessage에 블록 추가 —

```
[기존 초안 후보 — 같은 주제면 병합]
- {id}: {title}
...
신규 지식이 위 후보 중 하나와 **같은 주제**면 "match_id"에 그 id를 넣으세요.
확실하지 않으면 match_id는 null — 잘못된 병합보다 새 초안이 낫습니다.
```

- 출력 JSON에 `"match_id": "<id>" | null` (worthy=true일 때만 유효). 파싱: 후보 id 집합에 없는 match_id는 None으로 강등(환각 id 차단 1차 — 서비스에서 2차 검증)

### 3-4. FeedbackWikiService (`feedback_service.py`)

- 생성자 additive kwarg `reinforce_enabled: bool = False`
- `_distill_and_save` 확장 (기존 6단계 유지 + 분기):
  1. 기존 find_by_agent 결과에서 `_match_candidates(existing)` — CONVERSATION+DRAFT 필터, updated_at desc(없으면 후순위), 상위 20, `(id, title)` 목록. reinforce off·후보 0이면 None
  2. `distill_feedback(..., candidates=...)`
  3. `draft.match_id`가 있으면 `_reinforce(existing, draft.match_id, message_id, request_id)`:
     - 대상 검색(existing 내 id 일치) — 미실재 또는 status≠DRAFT면 warning 후 **None 반환 → 신규 draft 경로 계속**
     - 실재하면 `article.add_support(f"feedback:{message_id}", WikiPolicy.reinforce_confidence(article.confidence), utcnow())` → 짧은 세션+`begin()`으로 `repo.update(article)` → info 로그(`reinforced=True`, article_id, support=len(refs)) → 저장 경로 종료
  4. 강화 미성립 시 기존 신규 draft 저장 경로 그대로
- 함수 40줄 규칙: `_match_candidates`·`_reinforce` 헬퍼 분리

### 3-5. DI (`api/main.py`)

`get_feedback_wiki_service()` 생성부에 `reinforce_enabled=settings.wiki_feedback_reinforce_enabled` 추가 — 1줄.

## 4. 테스트 설계 (TDD 순서)

| # | 파일 | 케이스 |
|---|------|--------|
| T1 | `tests/domain/wiki/` (WikiPolicy·entity 테스트 확장) | reinforce_confidence 단조(+0.1)·CAP 클램프(0.95 초과 금지) / add_support: refs 추가·version+1·제목·본문 불변 |
| T2 | `tests/infrastructure/wiki/test_feedback_distiller.py` (확장) | candidates 전달 → 프롬프트에 id·title·병합 지시 포함 / match_id 파싱 / 후보에 없는 match_id → None 강등 / candidates=None → 프롬프트 기존과 동일(기존 8케이스 무수정 통과) |
| T3 | `tests/application/wiki/test_feedback_service.py` (확장) | reinforce on + match → 기존 draft 갱신(refs 2·confidence 상승·v2)·신규 draft 미생성·repo.update 호출 / match_id 미실재 → warning+신규 draft 폴백 / 비DRAFT 대상 → 폴백 / reinforce off → candidates=None 전달·기존 동작(기존 8케이스 무수정 통과) / 후보 상한 20·DRAFT만 필터 |
| T4 | 회귀 | wiki·eval·memory 스위트 무수정 통과 (`-p no:randomly`) |

## 5. 구현 순서

1. T1 → 3-2 도메인(policy+entity) — Red→Green
2. T2 → 3-3 계약+distiller — Red→Green
3. T3 → 3-4 서비스 — Red→Green
4. 3-1 config + 3-5 DI (1줄)
5. T4 회귀 일괄

## 6. 영향 범위 / 주의

- **수정 7**: config.py · domain/wiki/entity.py · domain/wiki/policies.py · application/wiki/schemas.py · application/wiki/interfaces.py · infrastructure/wiki/feedback_distiller.py · application/wiki/feedback_service.py · api/main.py(1줄) (+테스트 3 확장) — 신규 파일 0
- 마이그레이션 0 · 신규 라우트 0 · 프론트 diff 0 · API 계약 무변경
- **off 경로 회귀 기준**: `reinforce_enabled=False`면 candidates=None → distiller 프롬프트·서비스 동작 기존과 바이트 동일 — 기존 T1~T3 테스트 무수정 통과가 증거
- 환각 match_id 2중 방어: distiller(후보 집합 검증) + 서비스(실재·DRAFT 재검증 후 폴백)
- update 경쟁: fire-and-forget 저빈도 + 짧은 트랜잭션 — best-effort 허용(기존 환류 원칙, Plan 리스크 확정)
