---
title: 근거 판정 재작성 루프 — 주장 단위 판정·fail-open·판정 모델 벤치
status: approved
source_type: conversation
source_refs:
  - idt/docs/04-report/draft-grounding-check.report.md (§1.3, §1.5 D-04/D-06/D-11~D-13, §6)
  - 커밋 72b3632 (승인 게이트 런 종료 + 초안·답변 근거 판정 재작성 루프)
  - idt/src/application/hallucination/grounded_generation.py (GroundedGenerator — 초안·답변 공통 루프)
  - idt/src/domain/hallucination/grounding.py (GroundingVerdict.excluding_found_in, _found_literally)
  - idt/src/domain/hallucination/grounding_edit.py (GroundingEditPolicy.strip_sentences)
  - idt/src/infrastructure/hallucination/prompts.py (<sources>/<generation> 태그 경계, 품질 비판정)
  - idt/src/config.py (grounding_check_enabled=True, grounding_judge_model="gpt-4o", retries 2/1)
confidence: 0.8
version: 1
created: 2026-10-06
updated: 2026-10-06
reviewer: 배상규
verified_at: ae12fc4
---

# 근거 판정 재작성 루프

## 문제

문의 63116의 초안·채팅 답변이 근거 어디에도 없는 "대표번호 1877-9900"을 반복 생성했다.
기존 `HallucinationEvaluator` 는 참/거짓만 돌려줘 **무엇을 고칠지** 몰랐고 에이전트 빌더 경로에
연결돼 있지 않았다. 고정 규칙(전화번호 차단 등)은 "어떤 질문에서는 나와도 되는 값"을 판단하지 못해
기각됐다(Plan v0.1→v0.2, 사용자 결정 — 규칙은 판정기 **힌트**로만 남김).

## 검증된 사실

### 1. 루프 구조 — action 초안과 final_answer가 같은 `GroundedGenerator` 를 쓴다

```
생성 → 주장 단위 판정(원문 구간·이유·high/low) → high만 사유 넣어 재작성
     → 상한(초안 2 / 답변 1) 초과 시 판정기가 인용한 구간이 든 문장 제거
```
- 초안이 비면 빈 문자열(호출측이 작성 실패 처리), **답변이 비면 원문 유지**.
- 근거 없음·설정 off·판정기 미주입이면 판정 0회.
- **fail-open**: 판정기 예외는 원문 유지 — 답변·초안을 막지 않는다. 부작용 경로의 최종 방어선은
  [승인 게이트](approval-gate-run-contract.md)다. (크레딧 소진 429 중에도 런은 성공함을 실측)
- 로그에 주장·값 원문을 싣지 않는다.

### 2. 판정 모델 품질이 결과를 좌우한다 — 유틸리티 모델 가정은 틀렸다

| 모델 | 정상 문장(7) | 날조(3) |
|------|------|------|
| gpt-4o-mini | 7/7 오판(조회 결과에 있는 제목·금액까지 "근거 없음" → 정상 문장 삭제) | — |
| gpt-4.1-mini | 오판 0 | **대표번호 누락** — 0 오판이 사실은 미검출 |
| gpt-4o | 오판 최소 | 3/3 검출 |

- 그래서 `grounding_judge_model="gpt-4o"` 전용 분리(판정당 비용 약 15배). 등록 모델에서 못 찾으면
  기본 모델로 폴백, 빈 문자열이면 관리자 유틸리티 모델.
- **양성 대조군(날조 샘플)을 넣지 않은 벤치는 "관대함"을 "정확함"으로 착각한다.**

### 3. 판정 오판을 줄인 결정적 장치

- **원문 그대로 근거에 있는 지적은 결정적 제외**(`excluding_found_in` / `_found_literally`, D-13) —
  원문 인용형 오판 제거, 과삭제 위험 0.
- **프롬프트 태그 경계**(`<sources>…</sources>`, `<generation>`): 근거 코퍼스에 섞인 `[현재 날짜]`
  같은 대괄호 헤더 때문에 판정기가 근거 섹션을 비어 있다고 읽던 문제를 해소(D-12).
- **품질 비판정**: "정보가 부족/모호하다"는 주장이 아니다 — 판정 범위를 "근거로 확인되는가"로 한정.
- 문장 제거는 글 단위 문장 경계·공백 흡수(D-14) — 조각("가능 여부는")·지시어 잔존 방지.

### 4. 스트리밍과의 상충

루프 중간 토큰을 채팅에 흘리면 판정 JSON·중간 재작성본이 노출된다 → 루프 토큰 보류 +
완료 이벤트로 최종본 전송(D-04, `_map_chat_stream` 태그 필터). 대가로 **final_answer 실시간
타이핑 효과가 사라졌다** — 의도된 트레이드오프이므로 "스트리밍이 끊겼다"를 버그로 고치지 말 것.

### 5. 기본 활성 — 비용 주의

`grounding_check_enabled` 기본 **True**(성장 루프 플래그들과 반대). 근거(sources)가 있는 모든
에이전트 런에서 gpt-4o 판정이 최소 1회 돈다. 비용·지연 이상 시 이 플래그와 retries부터 확인.

## 다음에 적용하는 법

1. 새 LLM 판정기·검증기를 만들 때는 Design 단계에서 **양성 대조군 포함 미니 벤치**(정상 N + 날조 M)를
   돌려 모델을 고른다. 이후 골든셋을 오프라인 회귀로 고정(보고서 Try — 아직 미구현).
2. 생성 결과를 고치는 기능은 "판정 → 사유 피드백 재작성 → 상한 초과 시 제거" 루프를 재사용한다
   (`GroundedGenerator.run`). 별도 구현 금지.
3. 근거 코퍼스를 프롬프트에 넣을 때는 대괄호 헤더가 섹션 경계를 무너뜨리지 않도록 XML 태그로 감싼다.
4. 판정 실패를 런 실패로 만들지 않는다([degraded vs 예외 전파](degradation-vs-failure-boundary.md) — 쓸 수 있는 결과=원문이 있다).

## 미해결 (이월)

- SC-3 Partial: gpt-4o도 값 없는 채널 안내("영업점 방문")를 high로 잡아 초안이 보수적. 위키 대표번호 시나리오·판정기 장애 주입 L3는 크레딧 소진으로 미수행.
