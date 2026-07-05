# Self-Hosted Qwen Endpoint Planning Document

> **Summary**: 폐쇄망 GPU에 vLLM(OpenAI 호환)으로 서빙되는 Qwen 모델을 LLM 모델 레지스트리에 등록·선택·호출할 수 있도록, 모델별 커스텀 엔드포인트(`base_url`)를 지원한다.
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-06-28
> **Status**: Draft
> **Code**: LLM-MODEL-REG-002 (LLM-MODEL-REG-001 확장)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 폐쇄망 GPU에 Qwen이 vLLM으로 떠 있으나, 현재 `LLMFactory`가 `ChatOpenAI`에 `base_url`을 전달하지 못해 항상 `api.openai.com`으로만 호출된다. 사내 IP 엔드포인트를 지정할 경로가 도메인/DB/API 어디에도 없다 |
| **Solution** | `provider="openai"`를 그대로 재사용하고, 모델별 `base_url` 필드 하나만 additive로 추가한다. vLLM이 OpenAI 호환(`/v1`)이므로 `ChatOpenAI(base_url=...)`만 넘기면 동작한다 |
| **Function/UX Effect** | 외부 API 의존 없이 폐쇄망 내부 GPU의 Qwen으로 Agent/RAG/일반 채팅을 구동. 데이터 외부 유출 없는 온프레미스 추론 가능 |
| **Core Value** | 보안 폐쇄망 환경에서의 LLM 자체 호스팅 지원 확보. 기존 OpenAI/Anthropic/Ollama 동작에 영향 0 (완전 additive) |

---

## 1. Overview

### 1.1 Purpose

폐쇄망 GPU 서버에 vLLM으로 서빙 중인 Qwen 모델을 기존 LLM 모델 레지스트리를 통해 등록하고, Agent Builder 및 채팅 흐름에서 선택·호출할 수 있게 한다. 핵심은 모델별 호출 엔드포인트(`base_url`)를 저장하고 `LLMFactory`가 이를 사용하도록 하는 것이다.

### 1.2 Background

- **서빙 방식 확정**: 폐쇄망 Qwen은 **vLLM(OpenAI 호환 `/v1`)** 으로 서빙됨 (사용자 확인 완료)
- **레지스트리 완비**: LLM 모델 레지스트리(CRUD + 가격 + API + DB)는 이미 구현되어 있음 (LLM-MODEL-REG-001)
- **단일 결손 지점**: `LLMFactory._create_openai`가 `ChatOpenAI`에 `base_url`을 전달하지 않으며(`src/infrastructure/llm/llm_factory.py:35`), 엔티티/ORM/스키마에 `base_url` 필드 자체가 없음
- **부분 선례**: 별도 `OllamaClient`는 이미 `base_url`을 받지만(`src/infrastructure/llm/ollama/ollama_client.py:43-49`), 레지스트리/팩토리 경로와 분리되어 메인 흐름에서 미사용

### 1.3 Related Documents

- 설계서(예정): `docs/02-design/features/self-hosted-qwen-endpoint.design.md`
- LLM 팩토리: `src/infrastructure/llm/llm_factory.py`
- LLM 모델 엔티티: `src/domain/llm_model/entity.py`
- LLM 모델 ORM: `src/infrastructure/llm_model/models.py`
- 모델 레지스트리 API: `src/api/routes/llm_model_router.py`
- 기존 가격 컬럼 마이그레이션 선례: `db/migration/V022__*`, `V032__alter_mcp_server_registry_add_secrets.sql`

---

## 2. Scope

### 2.1 In Scope

- [ ] `LlmModel` 엔티티에 `base_url: str | None` 필드 추가
- [ ] `llm_model` 테이블에 `base_url VARCHAR(500) NULL` 컬럼 추가 (마이그레이션)
- [ ] Repository 엔티티↔ORM `base_url` 왕복 매핑
- [ ] `LLMFactory._create_openai` / `_create_ollama`가 `base_url`을 LangChain 클라이언트에 전달
- [ ] vLLM 더미키 대응: `base_url`이 있으면 빈 api_key여도 통과(EMPTY 대체)
- [ ] Create/Update/Response 스키마에 `base_url` additive 추가
- [ ] `.env.example`에 `QWEN_API_KEY` 예시 추가

### 2.2 Out of Scope

- 프론트엔드 모델 등록 폼 `base_url` 입력 UI (후속, `/api-contract-sync`로 처리)
- TGI 등 비-OpenAI 프로토콜 어댑터 추가
- 임베딩 모델 self-host (별도 과제)
- 폐쇄망 네트워크/방화벽/vLLM 서버 구성 자체
- `provider="anthropic"`에 대한 base_url 지원 (해당 없음)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `LlmModel` 엔티티가 `base_url`(옵셔널)을 보관 | High | Pending |
| FR-02 | `LLMFactory`가 `base_url`이 있으면 `ChatOpenAI(base_url=...)`로 전달, 없으면 기본 엔드포인트 | High | Pending |
| FR-03 | `base_url`이 설정된 경우 빈 api_key여도 호출 통과 (vLLM 더미키 EMPTY) | High | Pending |
| FR-04 | Create/Update UseCase가 `base_url`을 DB와 왕복 저장 | High | Pending |
| FR-05 | `LlmModelResponse`가 `base_url`을 additive로 노출 | Medium | Pending |
| FR-06 | `_create_ollama`도 `base_url`을 `ChatOllama`에 전달 (보너스) | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Compatibility | base_url=None이면 기존 OpenAI/Anthropic/Ollama 동작 100% 동일 | 단위 테스트 |
| Migration Safety | NULL 허용 ALTER, 무중단, 기존 행 영향 0 | 마이그레이션 리뷰 |
| Security | base_url 평문 저장(비밀 아님), api_key는 기존 env 참조 방식 유지 | 코드 리뷰 |
| Observability | streaming 시 usage_metadata 유지 (vLLM 반환 여부 확인 필요) | 연결 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 폐쇄망 Qwen을 레지스트리에 등록 → 기본 모델 지정 → 채팅/Agent 호출 성공
- [ ] base_url 관련 단위 테스트 전부 통과 (entity/factory/usecase/repository/schema)
- [ ] 기존 LLM 모델 테스트 회귀 없음
- [ ] 마이그레이션 V035 적용 성공

### 4.2 Quality Criteria

- [ ] mypy/ruff 에러 없음
- [ ] DDD 레이어 규칙 준수 (domain에 외부 의존성 없음)
- [ ] TDD 사이클 준수 (Red → Green → Refactor)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| vLLM이 streaming에서 usage_metadata 미반환 | Medium | Medium | 토큰 사용량은 best-effort 처리, 없으면 0 기록 (기존 Ollama 패턴 참고) |
| vLLM `served-model-name`과 등록 `model_name` 불일치 | High | Medium | 등록 가이드에 명시, 연결 테스트로 사전 검증 |
| vLLM 인증 토큰 유무 불명확 | Low | Medium | base_url 존재 시 빈 키 허용(EMPTY), 실제 키 있으면 env로 주입 |
| 폐쇄망 네트워크 미연결로 통합 검증 불가 | Medium | Low | 단위 테스트로 base_url 전달 검증, 실연결은 폐쇄망 내부에서 별도 확인 |

---

## 6. Architecture Considerations

### 6.1 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 신규 provider vs 기존 재사용 | `provider="vllm"` 신규 / `openai` 재사용 | **openai 재사용** | vLLM이 OpenAI 호환 → 분기/어댑터 추가 불필요, 변경 최소 |
| 엔드포인트 저장 위치 | 환경변수 / DB 컬럼 | **DB 컬럼(base_url)** | 멀티 모델·멀티 서버 대응, 레지스트리 일관성 |
| api_key 부재 처리 | 필수 유지 / base_url시 EMPTY 허용 | **EMPTY 허용** | vLLM은 인증 미사용 케이스 존재 |
| 변경 방식 | breaking / additive | **additive only** | 기존 동작 무영향 보장 |

### 6.2 변경 레이어 배치

```
src/
├── domain/llm_model/
│   └── entity.py              # + base_url: str | None
├── infrastructure/llm_model/
│   ├── models.py              # + base_url 컬럼 (VARCHAR 500 NULL)
│   └── llm_model_repository.py # + base_url 왕복 매핑
├── infrastructure/llm/
│   └── llm_factory.py         # ChatOpenAI/ChatOllama에 base_url 전달, 빈 키 허용
├── application/llm_model/
│   ├── schemas.py             # Create/Update/Response + base_url
│   └── create_/update_..._use_case.py
└── db/migration/
    └── V035__alter_llm_model_add_base_url.sql
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] DDD 레이어 규칙 (domain → application → infrastructure)
- [x] Pydantic 스키마 기반 요청/응답
- [x] Flyway 마이그레이션 네이밍 (`V0NN__verb_table.sql`)
- [x] env 참조 방식 api_key (`api_key_env` 필드)
- [x] TDD 필수

### 7.2 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `QWEN_API_KEY` | 폐쇄망 vLLM 인증키 (미사용 시 `EMPTY`) | Server | ☑ |

엔드포인트 주소는 환경변수가 아니라 **DB `base_url`에 모델별 저장**.

---

## 8. Open Questions (구현 전 확인)

1. vLLM에 인증 토큰이 걸려 있는가? (있으면 `QWEN_API_KEY`에 실제 키, 없으면 `EMPTY`)
2. 등록할 `model_name`이 vLLM `--served-model-name`과 정확히 일치하는가?
3. 임베딩도 폐쇄망으로 가야 하는가? (현재 비목표 — LLM만)

---

## 9. Next Steps

1. [ ] Write design document (`self-hosted-qwen-endpoint.design.md`)
2. [ ] TDD 구현 (entity → factory → usecase → repository → schema → migration)
3. [ ] 프론트엔드 base_url 입력 UI (`/api-contract-sync`)
4. [ ] 폐쇄망 내부 실연결 검증

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-28 | Initial draft | 배상규 |
