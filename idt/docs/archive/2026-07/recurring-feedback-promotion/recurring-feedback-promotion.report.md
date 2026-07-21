# recurring-feedback-promotion Completion Report

> **Feature**: recurring-feedback-promotion — 반복 👎 이유 빈도 집계로 위키 초안 승격 우선순위화
> **Author**: 배상규
> **기간**: 2026-07-21 (1일, 환류 3부작 후속)
> **Match Rate**: **98%** (gap-detector 97.6% → 경미 gap 1건 Check 내 해소)

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | recurring-feedback-promotion |
| 기간 | 2026-07-21 (Plan→Design→Do→Check→Report) |
| Match Rate | 98% (iterate 0회) |
| 변경 규모 | 기존 12파일 확장 +348/−16 · **신규 파일 0 · 마이그레이션 0 · 프론트 diff 0 · DI 1줄** |
| 테스트 | 신규 16케이스(도메인 5·distiller 5·서비스 6) / 회귀 wiki+eval+memory 301 pass |

### 1.3 Value Delivered (4관점)

| 관점 | 실제 결과 |
|------|-----------|
| **Problem** | 같은 주제의 👎 이유가 다른 메시지에서 반복되면 별개 draft가 남발 — 반복성(강한 신호)이 승인 큐에서 분산되어 안 보이고, 관리자는 같은 내용을 중복 검토 |
| **Solution** | LLM 판정에 기존 draft 후보(id, title) 전달 — 같은 주제면 신규 대신 **강화**: refs 지지 축적(지지 수 = len(refs)), confidence +0.1/지지(cap 0.95), version+1, 제목·본문 불변. `wiki_feedback_reinforce_enabled` 기본 off 독립 opt-in, 오매칭 2중 방어(후보 집합 검증 + 실재·DRAFT 재검증 → 신규 draft 폴백) |
| **Function UX Effect** | 반복 지지된 초안이 **높은 신뢰도·버전·다수 출처**로 승인 큐에서 우선 검토 대상화 — 기존 노출 필드 재사용, 신규 화면 0 |
| **Core Value** | 환류에 **빈도 차원** 완성 — 여러 사용자·턴에서 반복 확인된 지식이 스스로 상위로 떠오름. draft 남발 억제 + 관리자 검토 비용 절감 |

---

## 2. 산출물

| 단계 | 문서 |
|------|------|
| Plan | `docs/01-plan/features/recurring-feedback-promotion.plan.md` — FR-01~07 |
| Design | `docs/02-design/features/recurring-feedback-promotion.design.md` — 결정 ①~⑤ |
| Check | `docs/03-analysis/recurring-feedback-promotion.analysis.md` — 97.6% → 해소 후 잔여 0 |

## 3. 구현 요약

- **도메인**: `WikiPolicy.reinforce_confidence`(+0.1, cap 0.95 — 승인 전 1.0 도달 금지) + `WikiArticle.add_support`(refs 추가·version+1·제목/본문/상태 불변)
- **distiller**: additive `candidates` 파라미터 — `[기존 초안 후보 — 같은 주제면 병합]` 블록 + "잘못된 병합보다 새 초안이 낫습니다", `_parse_match_id`가 후보 id 집합 밖 환각 id를 None 강등
- **service**: `_match_candidates`(CONVERSATION+DRAFT·updated_at desc·상한 20 — 기존 dedup 조회 재사용, 추가 조회 0) + `_reinforce`(2차 검증 실패 시 warning+신규 draft 폴백, `session.begin()` + repo.update, `reinforced=True` 관측 로그)
- **off 경로 기준선**: reinforce off면 candidates=None → 프롬프트·동작 기존과 바이트 동일 (기존 테스트 무수정 통과)

## 4. FR 이행 — 7/7 ✅

FR-01 후보 전달(추가 조회 0) / FR-02 match 시 강화·신규 미생성 / FR-03 confidence 단조+클램프 / FR-04 미실재·비DRAFT 폴백 / FR-05 off·no-match 기존 동일 / FR-06 dedup 선행(지지 수 인플레 방지) / FR-07 회귀 301 pass

## 5. 학습 포인트

1. **지지 수를 스키마 없이**: `len(source_refs)`가 곧 빈도 — 기존 필드의 의미 확장으로 마이그레이션 0. "예약석 채우기"에 이어 "기존 필드 재해석" 패턴.
2. **오매칭은 2중 방어 + 폴백**: LLM 판정 오류를 막을 수 없다면 (a) 입력 후보 집합으로 1차 차단 (b) 저장 직전 재검증 (c) 실패 시 안전한 기본 동작(신규 draft) — 판정 오류가 최악의 경우에도 "기존 동작"으로 수렴.
3. **독립 opt-in의 배당**: off/on 토글 쌍으로 오매칭률·강화 효과를 A/B 실측할 기준선이 공짜로 생김 (rag-routed-integration 선례 재확인).

## 6. 이월 항목

- E2E 수동 검증: 3플래그(`EVAL_FEEDBACK_EXTRACTION`·`WIKI_FEEDBACK_DRAFT`·`WIKI_FEEDBACK_REINFORCE`) on + MySQL/Qdrant 기동 — 같은 주제 👎 2회 → 강화 실측
- 오매칭률 실측 후 REINFORCE_STEP/CAP 튜닝 (정책 상수 1곳)
- websearch 환류(WEBSEARCH 예약석) · agent 경로 평가 연동 · memory 반복 집계(선택)
- 배포: 신규 마이그레이션 없음, 활성화는 `WIKI_FEEDBACK_REINFORCE_ENABLED=true`
