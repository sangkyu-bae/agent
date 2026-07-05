# Completion Report: self-hosted-qwen-endpoint

> Feature: 폐쇄망 자체 호스팅 LLM(Qwen) 연결 지원 (LLM-MODEL-REG-002)
> Author: 배상규
> Date: 2026-06-28
> Phase: Completed
> Match Rate: **100%** (29/29)

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| **Feature** | 폐쇄망 GPU vLLM(OpenAI 호환) Qwen 연결 지원 |
| **기간** | 2026-06-28 (Plan → Design → Do → Check → Report, 단일 세션) |
| **PDCA** | Plan ✅ / Design ✅ / Do ✅ / Check 100% ✅ / Report ✅ |
| **변경 규모** | 소스 8파일 (+43/-8), 마이그레이션 1, 테스트 4파일(신규 3+보강 1), 프론트 타입 2 |
| **테스트** | 신규 20 + 회귀 40 + router 4 = **64 passed**, tsc 오류 0 |

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 폐쇄망 GPU의 vLLM Qwen이 있어도 `LLMFactory`가 `base_url`을 전달하지 못해 항상 api.openai.com으로만 호출 → 사내 엔드포인트 연결 불가 |
| **Solution** | `provider="openai"` 재사용 + 모델별 `base_url` 컬럼 1개 additive 추가, `ChatOpenAI(base_url=...)` 전달 + 인증 없는 vLLM용 `"EMPTY"` 더미키 허용 |
| **Function/UX Effect** | 외부 API 의존 없이 폐쇄망 내부 GPU Qwen으로 Agent/RAG/채팅 구동 — 데이터 외부 유출 없는 온프레미스 추론 |
| **Core Value** | 보안 폐쇄망 LLM 자체 호스팅 지원 확보. 기존 OpenAI/Anthropic/Ollama 동작 영향 0 (완전 additive) |

---

## 1. 구현 요약

### 1-1. 핵심 변경
- **신규 provider 없이** vLLM(OpenAI 호환)을 `provider="openai"`로 흡수
- 엔드포인트는 환경변수가 아닌 **DB `llm_model.base_url`** 에 모델별 저장 (멀티 모델/서버 대응)
- vLLM 인증 미사용 케이스 대응: `base_url` 있으면 빈 키여도 `"EMPTY"`로 통과

### 1-2. 변경 파일

| 레이어 | 파일 | 변경 |
|--------|------|------|
| Domain | `domain/llm_model/entity.py` | `base_url: str \| None = None` |
| **Infra** | **`infrastructure/llm/llm_factory.py`** | **ChatOpenAI/ChatOllama base_url 전달 + allow_empty + EMPTY** |
| Infra | `infrastructure/llm_model/models.py` | `base_url VARCHAR(500)` 컬럼 |
| Infra | `infrastructure/llm_model/llm_model_repository.py` | _to_orm/_to_domain/update 매핑 |
| App | `application/llm_model/schemas.py` | Create/Update/Response + from_domain |
| App | `create_/update_llm_model_use_case.py` | base_url 왕복 + 빈문자열→None 정규화 |
| DB | `db/migration/V035__alter_llm_model_add_base_url.sql` | ALTER ADD COLUMN |
| Config | `.env.example` | `QWEN_API_KEY=EMPTY` |
| Front | `idt_front/src/types/llmModel.ts` | `base_url?: string \| null` |
| Front | `idt_front/src/__tests__/mocks/handlers.ts` | mock 응답 base_url 반영 |

---

## 2. 검증 결과

```
신규 base_url 테스트 (domain/infra/app)   20 passed
회귀(factory + llm_model 전체)            40 passed
router(pricing)                           4 passed
tsc --noEmit (frontend)                   오류 0
모듈 임포트 무결성                        OK (8개)
```

- 테스트는 Windows 이벤트 루프 flakiness 회피 위해 **격리 실행** (backend-test-eventloop-flakiness 메모리 준수)
- DDD 레이어 규칙 / 컨벤션(additive, NULL ALTER, env 참조) 100% 준수

---

## 3. 학습 / 의사결정 기록

| 결정 | 채택안 | 이유 |
|------|--------|------|
| provider 추가 vs 재사용 | openai 재사용 | vLLM OpenAI 호환 → 분기/어댑터 0 |
| 엔드포인트 저장 | DB 컬럼 | 멀티 모델/서버, 레지스트리 일관성 |
| 인증 없는 vLLM | base_url 시 EMPTY 더미키 | 인증 미사용 케이스 수용 |
| 빈 문자열 base_url | None 정규화 | self-host 해제 의미 명확화 (R3) |

---

## 4. 운영 가이드 (폐쇄망 연결)

1. `idt/.env`: `QWEN_API_KEY=실제토큰` (인증 없으면 `EMPTY`)
2. Flyway: `V035` 마이그레이션 적용
3. 모델 등록 `POST /api/v1/llm-models`:
   ```json
   { "provider": "openai", "model_name": "<vLLM served-model-name>",
     "display_name": "사내 Qwen", "base_url": "http://<폐쇄망IP>:8000/v1",
     "api_key_env": "QWEN_API_KEY", "is_default": true }
   ```
4. 기본 모델 지정 → 채팅/Agent 자동 호출

⚠️ `model_name`은 vLLM `--served-model-name`과 **정확히 일치** 필요 (불일치 시 404).

---

## 5. 후속 과제 (Plan Out of Scope)

| # | 항목 | 상태 |
|---|------|------|
| 1 | 프론트 모델 등록 폼 `base_url` 입력 UI | 미착수 (타입만 선반영) |
| 2 | 폐쇄망 내부 실연결 검증 (실추론 + streaming usage_metadata, R1/R4) | 폐쇄망 내부 별도 확인 필요 |
| 3 | 임베딩 모델 self-host | 별도 과제 (본 작업 비목표) |

---

## 6. PDCA 산출물

- Plan: `docs/01-plan/features/self-hosted-qwen-endpoint.plan.md`
- Design: `docs/02-design/features/self-hosted-qwen-endpoint.design.md`
- Analysis: `docs/03-analysis/self-hosted-qwen-endpoint.analysis.md`
- Report: `docs/04-report/self-hosted-qwen-endpoint.report.md` (본 문서)
