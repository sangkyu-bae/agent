# Plan: RAGAS Evaluation Module

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | RAGAS 기반 RAG/Agent 평가측정 모듈 |
| 작성일 | 2026-05-13 |
| 예상 기간 | 5~7일 |
| 우선순위 | High |

### Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | RAG 파이프라인·Agent 응답의 품질을 정량적으로 측정할 수단이 없어, 개선 방향을 객관적으로 판단할 수 없다 |
| **Solution** | RAGAS 프레임워크 기반 평가 모듈을 독립적으로 구성하여, 배치 평가 + 실시간 모니터링을 모두 지원한다 |
| **Function UX Effect** | 테스트셋 기반 일괄 평가 → 점수 리포트 조회 / 실시간 질의 시 백그라운드 평가 점수 기록 |
| **Core Value** | RAG·Agent 품질의 정량적 측정·추적으로 데이터 기반 개선 사이클 확립 |

---

## 1. 배경 및 목적

### 1.1 현황
- `hallucination` 모듈이 존재하나, 단순 이진(hallucinated/not) 판정만 수행
- 검색 품질(Context Precision/Recall), 답변 관련성(Answer Relevancy) 등 정량 지표 부재
- Agent Builder로 생성한 커스텀 에이전트의 응답 품질을 측정할 방법 없음

### 1.2 목적
- RAGAS 프레임워크 기반의 **독립적인** 평가 모듈 구축
- 배치 평가(테스트셋 기반) + 실시간 모니터링(API 호출 시 백그라운드 기록) 지원
- 향후 다른 기능(대시보드, 자동 최적화 등)과 통합할 수 있는 확장 가능한 구조

---

## 2. 평가 대상 및 지표

### 2.1 RAG 파이프라인 평가

| 지표 | 설명 | 측정 대상 |
|------|------|----------|
| **Faithfulness** | 답변이 검색된 문서에 근거하는 정도 | RAGAgentUseCase 응답 |
| **Answer Relevancy** | 답변이 질문과 관련있는 정도 | RAGAgentUseCase 응답 |
| **Context Precision** | 검색된 문서 중 실제 관련 문서 비율 | HybridSearchUseCase 결과 |
| **Context Recall** | 필요한 정보가 검색 결과에 포함된 비율 | HybridSearchUseCase 결과 |

### 2.2 Retrieval 품질 평가

| 지표 | 설명 | 측정 대상 |
|------|------|----------|
| **Hit Rate** | 정답 문서가 top-k 안에 포함되는 비율 | HybridSearchUseCase |
| **MRR (Mean Reciprocal Rank)** | 정답 문서의 평균 역순위 | HybridSearchUseCase |
| **NDCG** | 순위를 고려한 검색 품질 점수 | HybridSearchUseCase |

### 2.3 Agent 응답 평가

| 지표 | 설명 | 측정 대상 |
|------|------|----------|
| **Answer Correctness** | 정답 대비 응답의 정확도 | RunAgentUseCase |
| **Answer Similarity** | 정답과의 의미적 유사도 | RunAgentUseCase |
| **Tool Usage Accuracy** | 적절한 도구를 사용했는지 여부 | RunAgentUseCase (워커 호출 이력) |

---

## 3. 아키텍처 설계 방향

### 3.1 독립 모듈 구조 (Thin DDD 준수)

```
src/
├── domain/ragas/
│   ├── entities.py          # EvaluationRun, EvaluationResult
│   ├── value_objects.py     # MetricScore, TestCase, EvalConfig
│   ├── interfaces.py        # EvaluationRepositoryInterface
│   └── policies.py          # 평가 실행 조건, 점수 임계값 정책
│
├── application/ragas/
│   ├── batch_eval_use_case.py      # 테스트셋 기반 일괄 평가
│   ├── realtime_eval_use_case.py   # 실시간 백그라운드 평가
│   ├── eval_result_use_case.py     # 평가 결과 조회/통계
│   └── schemas.py                  # 요청/응답 DTO
│
├── infrastructure/ragas/
│   ├── ragas_adapter.py     # RAGAS 라이브러리 호출 어댑터
│   ├── metric_calculator.py # 커스텀 지표 계산 (Hit Rate, MRR 등)
│   ├── models.py            # SQLAlchemy 모델
│   └── repository.py        # MySQL 저장/조회 구현
│
└── api/routes/
    └── ragas_router.py      # REST API 엔드포인트
```

### 3.2 핵심 설계 원칙

1. **독립성**: 기존 RAG/Agent 모듈에 대한 의존은 인터페이스를 통해서만
2. **비동기 평가**: 실시간 모드에서 사용자 응답 지연 없이 백그라운드 처리
3. **확장성**: 새 평가 지표 추가 시 MetricCalculator 하나만 구현
4. **기존 hallucination 모듈**: 당장 변경하지 않되, 향후 ragas 모듈의 Faithfulness 지표로 대체 가능하도록 설계

---

## 4. DB 스키마 (초안)

### 4.1 evaluation_runs (평가 실행 이력)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | VARCHAR(36) PK | UUID |
| eval_type | ENUM('batch', 'realtime') | 평가 유형 |
| target_type | ENUM('rag', 'agent', 'retrieval') | 평가 대상 |
| target_id | VARCHAR(36) NULL | agent_id (Agent 평가 시) |
| status | ENUM('running', 'completed', 'failed') | 실행 상태 |
| total_cases | INT | 총 테스트 케이스 수 |
| config | JSON | 평가 설정 (metrics, top_k 등) |
| created_at | DATETIME | 생성일시 |
| completed_at | DATETIME NULL | 완료일시 |

### 4.2 evaluation_results (개별 평가 결과)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | VARCHAR(36) PK | UUID |
| run_id | VARCHAR(36) FK | evaluation_runs.id |
| question | TEXT | 질문 |
| ground_truth | TEXT NULL | 정답 (배치 평가용) |
| answer | TEXT | LLM 생성 답변 |
| contexts | JSON | 검색된 문서 리스트 |
| faithfulness | FLOAT NULL | Faithfulness 점수 |
| answer_relevancy | FLOAT NULL | Answer Relevancy 점수 |
| context_precision | FLOAT NULL | Context Precision 점수 |
| context_recall | FLOAT NULL | Context Recall 점수 |
| answer_correctness | FLOAT NULL | Answer Correctness 점수 |
| custom_metrics | JSON NULL | 추가 커스텀 지표 |
| created_at | DATETIME | 생성일시 |

### 4.3 evaluation_summaries (실행별 요약 통계)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | VARCHAR(36) PK | UUID |
| run_id | VARCHAR(36) FK UNIQUE | evaluation_runs.id |
| avg_faithfulness | FLOAT NULL | 평균 Faithfulness |
| avg_answer_relevancy | FLOAT NULL | 평균 Answer Relevancy |
| avg_context_precision | FLOAT NULL | 평균 Context Precision |
| avg_context_recall | FLOAT NULL | 평균 Context Recall |
| avg_answer_correctness | FLOAT NULL | 평균 Answer Correctness |
| custom_summary | JSON NULL | 커스텀 지표 요약 |
| created_at | DATETIME | 생성일시 |

---

## 5. API 엔드포인트

### 5.1 배치 평가

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/ragas/batch` | 테스트셋으로 일괄 평가 실행 |
| GET | `/api/ragas/runs` | 평가 실행 이력 목록 조회 |
| GET | `/api/ragas/runs/{run_id}` | 평가 실행 상세 + 요약 통계 |
| GET | `/api/ragas/runs/{run_id}/results` | 개별 케이스별 결과 조회 |
| DELETE | `/api/ragas/runs/{run_id}` | 평가 실행 삭제 |

### 5.2 실시간 평가

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/ragas/realtime/evaluate` | 단건 실시간 평가 요청 |
| GET | `/api/ragas/realtime/recent` | 최근 실시간 평가 결과 조회 |

### 5.3 테스트셋 관리

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/ragas/testsets` | 테스트셋 업로드 (JSON/CSV) |
| GET | `/api/ragas/testsets` | 테스트셋 목록 조회 |
| GET | `/api/ragas/testsets/{id}` | 테스트셋 상세 조회 |
| DELETE | `/api/ragas/testsets/{id}` | 테스트셋 삭제 |

---

## 6. 실행 방식 상세

### 6.1 배치 평가 플로우

```
사용자가 테스트셋 업로드 (질문-정답 쌍)
  → POST /api/ragas/batch 호출
  → EvaluationRun 생성 (status=running)
  → 각 테스트 케이스에 대해:
      1. HybridSearchUseCase로 검색 실행
      2. RAGAgentUseCase 또는 RunAgentUseCase로 답변 생성
      3. RAGAS 어댑터로 평가 지표 계산
      4. EvaluationResult DB 저장
  → EvaluationSummary 계산 및 저장
  → EvaluationRun status=completed
```

### 6.2 실시간 평가 플로우

```
사용자 질의 → RAG/Agent 응답 반환 (동기)
  → 백그라운드 태스크로 평가 실행 (비동기)
      1. 질문, 답변, 검색된 문서를 평가 큐에 전달
      2. RAGAS 어댑터로 Faithfulness, Answer Relevancy 계산
      3. EvaluationResult DB 저장 (eval_type=realtime)
```

---

## 7. 기술 의존성

| 의존성 | 용도 | 버전 |
|--------|------|------|
| `ragas` | RAGAS 평가 프레임워크 | 최신 안정 버전 |
| `datasets` | RAGAS 데이터셋 포맷 | ragas 의존성 |
| `langchain-core` | RAGAS ↔ LangChain 통합 | 기존 사용 중 |

---

## 8. 구현 순서 (Phase)

### Phase 1: Domain + Infrastructure 기반 (1~2일)
- [ ] domain/ragas 엔티티, VO, 인터페이스, 정책 정의
- [ ] infrastructure/ragas SQLAlchemy 모델 + Repository 구현
- [ ] DB 마이그레이션 파일 생성

### Phase 2: RAGAS 어댑터 + 배치 평가 (2~3일)
- [ ] infrastructure/ragas/ragas_adapter.py (RAGAS 라이브러리 래핑)
- [ ] infrastructure/ragas/metric_calculator.py (커스텀 지표)
- [ ] application/ragas/batch_eval_use_case.py
- [ ] application/ragas/eval_result_use_case.py (조회/통계)
- [ ] api/routes/ragas_router.py (배치 평가 API)

### Phase 3: 실시간 평가 + 테스트셋 관리 (1~2일)
- [ ] application/ragas/realtime_eval_use_case.py
- [ ] 테스트셋 업로드/관리 API
- [ ] 백그라운드 태스크 연동 (FastAPI BackgroundTasks)

### Phase 4: 통합 준비 (향후)
- [ ] 기존 hallucination 모듈과의 통합 검토
- [ ] 프론트엔드 대시보드 연동
- [ ] Agent Builder 품질 게이트 연동 (SupervisorConfig.quality_gate_enabled)

---

## 9. 통합 포인트 (향후 계획)

| 통합 대상 | 연동 방식 | 시기 |
|-----------|----------|------|
| Hallucination 모듈 | Faithfulness 점수로 대체 가능 | Phase 4 |
| Agent Builder | quality_gate_enabled에 평가 점수 임계값 적용 | Phase 4 |
| 프론트엔드 대시보드 | 평가 결과 시각화 (차트, 트렌드) | Phase 4 |
| 자동 최적화 | 낮은 점수 → top_k, rrf_k 등 파라미터 자동 조정 | Phase 4+ |

---

## 10. 테스트 전략

- **TDD 원칙 준수**: 테스트 먼저 작성 → 실패 확인 → 구현 → 통과
- Domain 레이어: 정책/VO 단위 테스트
- Application 레이어: UseCase 단위 테스트 (RAGAS 어댑터 mock)
- Infrastructure 레이어: Repository 통합 테스트 (test DB)
- API 레이어: 엔드포인트 E2E 테스트

---

## 11. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| RAGAS LLM 호출 비용 | 배치 평가 시 OpenAI 비용 증가 | 평가 대상 지표 선택 가능, 샘플링 비율 설정 |
| 실시간 평가 지연 | 백그라운드 처리로 영향 최소화 | BackgroundTasks 활용, 실패 시 무시 정책 |
| RAGAS 버전 호환성 | API 변경 시 어댑터 수정 필요 | 인프라 레이어에 격리, 인터페이스 통한 추상화 |
| 테스트셋 품질 | 정답(ground_truth) 품질이 평가 신뢰도 결정 | 테스트셋 검증 정책, 가이드 문서 제공 |
