# Gap Analysis: self-hosted-qwen-endpoint

> Phase: Check
> 분석일: 2026-06-28
> Design: `docs/02-design/features/self-hosted-qwen-endpoint.design.md`
> Plan: `docs/01-plan/features/self-hosted-qwen-endpoint.plan.md`
> Match Rate: **100%** (29/29) — gap-detector
> 판정: 코드를 진실로 간주, 읽기 전용 대조

---

## 1. 설계서 §2 (변경 상세) 대조

| # | 설계 항목 | 파일:위치 | 판정 |
|---|-----------|-----------|:----:|
| 2-1 | `LlmModel.base_url: str \| None = None` + docstring | entity.py:47, docstring:30 | ✅ |
| 2-2 | ORM `base_url` 컬럼 `String(500)` | models.py:46 | ✅ |
| 2-3a | `_to_orm`에 `base_url=model.base_url` | repository.py:165 | ✅ |
| 2-3b | `_to_domain`에 `base_url=row.base_url` | repository.py:184 | ✅ |
| 2-3c | `update()`에 `row.base_url = model.base_url` | repository.py:122 | ✅ |
| 2-4a | `_create_openai` base_url 전달 + `allow_empty` | llm_factory.py:34-46 | ✅ |
| 2-4b | `_create_ollama` base_url 전달 | llm_factory.py:58-65 | ✅ |
| 2-4c | `_resolve_api_key(allow_empty)` + `"EMPTY"` 더미키 | llm_factory.py:67-79 | ✅ |
| 2-5a | `CreateLlmModelRequest.base_url` Field(max_length=500) | schemas.py:23 | ✅ |
| 2-5b | `UpdateLlmModelRequest.base_url` | schemas.py:32 | ✅ |
| 2-5c | `LlmModelResponse.base_url` additive | schemas.py:55 | ✅ |
| 2-5d | `from_domain`에 `base_url=model.base_url` | schemas.py:71 | ✅ |
| 2-6a | Create UseCase `base_url` 전달 | create_..._use_case.py:60 | ✅ (강화) |
| 2-6b | Update UseCase 부분 갱신 | update_..._use_case.py:45-47 | ✅ (강화) |
| 2-7 | `V035__alter_llm_model_add_base_url.sql` | db/migration/V035 | ✅ |
| 2-8 | `.env.example` `QWEN_API_KEY` | .env.example:79-82 | ✅ |

> 강화 사항(갭 아님): Create/Update UseCase가 `request.base_url or None`로 빈 문자열을 None 정규화 — 설계 §2-6 주석 및 리스크 R3에서 "선택"으로 언급한 처리를 실제 채택.

## 2. 설계서 §5 (TDD 케이스) 대조

12개 케이스(T1~T12) 전부 구현됨. 추가 보너스 테스트 3건(빈문자열 정규화 R3, repository None 기본값 등). 파일 배치는 설계 허용 범위 내(repository는 기존 파일 보강).

## 3. 프론트엔드 동기화

| 항목 | 위치 | 판정 |
|------|------|:----:|
| `LlmModel.base_url?: string \| null` | idt_front/src/types/llmModel.ts:11 | ✅ |

> Plan상 프론트는 Out of Scope(후속)였으나 타입 동기화는 additive로 선반영. 등록 폼 UI는 후속 과제.

## 4. Match Rate

| 카테고리 | 충족/전체 | 비율 |
|----------|:--------:|:----:|
| §2 변경 상세 | 16/16 | 100% |
| §5 TDD 케이스 | 12/12 | 100% |
| 프론트 동기화 | 1/1 | 100% |
| **전체** | **29/29** | **100%** |

| 평가축 | 점수 |
|--------|:----:|
| Design Match | 100% ✅ |
| Architecture(DDD) 준수 | 100% ✅ |
| Convention(additive/NULL ALTER/env) 준수 | 100% ✅ |

## 5. 갭 목록

- 미구현(Design O / Impl X): **없음**
- 불일치(회귀 위험): **없음**

## 6. 검증 결과 (격리 실행)

```
신규 base_url 테스트   20 passed
회귀(factory+llm_model) 40 passed
router(pricing)         4 passed
tsc --noEmit            오류 0
```

## 7. 권장 조치

- **즉시**: 없음 → `/pdca report` 진행 가능.
- **후속(Plan 명시)**: ① 프론트 모델 등록 폼 `base_url` 입력 UI ② 폐쇄망 내부 실연결 검증(R4 — streaming usage_metadata 포함).
