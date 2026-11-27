---
title: Graph RAG 장애 동작과 로컬 운영 함정 — 장애별 업로드·추출·검색·관리자 반응
status: approved
source_type: conversation
source_refs:
  - idt/src/api/graph_rag_di.py (_build_store: GRAPH_BACKEND·URI·드라이버 실패 → None, start_graph_rag)
  - idt/src/api/graph_rag_runtime_store.py (GraphBackendUnavailableError)
  - idt/src/infrastructure/graph_rag/settings_reader.py (읽기 실패 = 닫힌 기본값)
  - idt/src/application/graph_rag/retrieval/source.py (skip_reason 변환)
  - idt/src/application/rag_agent/tools.py (도구 하드 상한 6초)
  - idt/src/application/graph_rag/extraction/use_case.py, launcher.py
  - idt/src/application/graph_rag/admin/health_use_case.py, jobs_use_case.py
  - idt/src/application/knowledge_base/upload_use_case.py, idt/src/application/doc_browse/delete_document_use_case.py (훅 예외 삼킴)
  - idt/pyproject.toml ([project.optional-dependencies] graph = neo4j>=5.20, pytest 마커 neo4j 기본 제외)
  - idt/src/config.py (graph_backend 기본 off)
  - 커밋 eb91f95 (Neo4j 접속 불가 상태에서 use_graph 에이전트 대화 200 확인)
confidence: 0.8
version: 1
created: 2026-11-21
updated: 2026-11-27
verified_at: 49b0970
reviewer: 배상규
---

# Graph RAG 장애 동작과 로컬 운영 함정

## 문제

그래프 모듈은 "답변·업로드·삭제 경로를 깨지 않는다"가 원칙이라 장애가 대부분 조용히 흡수된다.
화면에 오류가 안 보이니 "고장인가, 설정인가, 의도된 흡수인가"를 장애 종류별로 구분할 기준이 필요하다.

## 검증된 사실

### 1. 공통 원칙 (세 겹)

1. 코어 호출 지점(업로드·삭제)이 훅 예외를 로그만 남기고 삼킨다.
2. 그래프 소스는 예외 대신 `skip_reason`을 돌려준다.
3. RAG 도구가 보조 태스크를 6초 하드 상한으로 한 번 더 감싼다.

### 2. 장애별 동작

| 장애 | 업로드 | 추출 잡 | 대화 검색 | 관리자 화면 |
|------|--------|---------|-----------|-------------|
| `GRAPH_BACKEND=off`(기본)·URI/비밀번호 누락·**neo4j 드라이버 미설치** | 정상(조건 맞으면 잡은 생성) | 첫 Neo4j 호출에서 예외 → failed | `backend_unavailable`, 기존 결과만 | health 연결 안 됨, 수동 추출 503, 엔티티·검색·정합성 503 |
| 주소는 있으나 접속 불가(Aura 정지 등) | 정상 | 드라이버 재시도 동안 pending → 이후 failed. 프로세스가 먼저 죽으면 고아 pending | 대개 `timeout`, 또는 `backend_unavailable` — 대화는 200 | health에 오류 문자열, 수동 추출은 store 객체가 있어 202 접수 후 잡 failed |
| 기동 시 벡터 차원 불일치 | 정상 | store 없음 → failed | `backend_unavailable` | 모듈 비활성 |
| 기동 시 스키마 생성 일시 실패 | 정상 | 회복되면 정상 | 회복되면 정상 | 경고 로그만 |
| 추출 LLM 실패(청크) | — | failed_chunks+1 후 계속, 전부면 failed | — | 잡 카운터 |
| 추출 모델 미설정 | 자동 추출 건너뜀 | 사전 조건 failed | — | 수동 추출 422 |
| 이름 임베딩 실패 | — | 정확·별칭 후보만으로 판정, 새 엔티티에 임베딩 없음 | 질문 벡터 없이 정확·별칭 연결만 | — |
| Jev 실패 | — | 그 언급만 LLM 대체, 잡 안 연속 5회면 남은 구간 Jev 생략 | 질문 주제를 LLM으로, 라우터 연속 5회 후 재기동 전까지 Jev 안 씀 | — |
| 판정 LLM 실패 | — | 새 엔티티 + 검토 대기 | 질문 주제 `llm_error` → 범위 없이 | 검토 큐에 쌓임 |
| 주제 제안·판정 실패 | — | 경고, 기존 주제로 계속 | 그 문서 청크에 topic_ids 없음 → 범위 검색에서 빠짐 | — |
| ES 장애 | 업로드 자체 실패 가능 | 청크 조회 예외 → failed | 근거 조회 예외 → `error` | 엔티티 상세·정합성 오류 |
| MySQL 설정 읽기 실패 | 자동 추출 건너뜀(닫힌 기본값) | 사전 조건 `stage_off` | `stage_off` | 설정 API 오류 |
| 프로세스 재기동 | — | 진행 중 잡 끊김 → 다음 기동 때 failed(`interrupted`). 그 전까지 같은 문서 수동 실행 409 BUSY | — | 관리자가 resume |

### 3. 로컬 운영 함정 (실측 확인)

- **neo4j 드라이버는 optional extra `graph`** 다(`pyproject.toml`). 메인 venv에 없으면 `_build_store`가 드라이버 생성 실패로 None → 관리자 화면 "연결 안 됨". 설치는 `uv pip install neo4j`. **`uv sync`는 쓰지 않는다** — 명시하지 않은 extra·dev 패키지를 지운다.
- **dev 서버 `--reload`는 의존성 설치·스키마(마이그레이션) 변경을 반영하지 못한다** → 서버를 재시작해야 한다. 드라이버 설치 후에도 재시작 전까지 "연결 안 됨"이 유지된다.
- 추출을 띄운 프로세스(dev 서버 재로드 포함)가 죽으면 pending 잡이 남아 같은 문서 추출이 `GRAPH_JOB_BUSY`로 막힌다 → 재기동 정리 후 resume([[extraction-pipeline]] §9).
- Neo4j가 필요한 테스트는 pytest 마커 `neo4j`로 기본 제외된다(`-m neo4j`로 명시 실행). 기본 회귀가 초록이어도 Neo4j 실연결 경로는 검증되지 않은 것이다.
- `retrieval_timeout_ms` 기본 800이면 끔/켬 비교가 무의미해진다([[retrieval-path]] §8).

## 다음에 적용하는 법

1. 관리자 health가 "연결 안 됨"이면 순서대로: `GRAPH_BACKEND=neo4j` → `NEO4J_URI`/`NEO4J_PASSWORD` → venv에 neo4j 설치 → 서버 재시작(--reload 아님) → 기동 로그의 `graph store disabled`/차원 불일치 경고.
2. 그래프가 꺼진 것처럼 보이면 장애보다 먼저 설정 읽기 실패(닫힌 기본값)·stage·3중 게이트를 의심한다 — 이 모듈의 실패는 대부분 "기능 꺼짐"으로 보인다.
3. 새 실패 지점을 추가할 때 위 세 겹 원칙을 유지한다: 코어로 예외를 올리지 않고, 소스는 skip_reason, 잡은 청크 단위 실패 카운트.
4. 배포 전 [[e2e-carryover-checklist]]에 Neo4j 실연결(`-m neo4j`)과 health 확인을 포함한다.

## 관련 문서

- [[overview]] · [[extension-hooks-boundary]] · [[execution-gates-and-rollout]] · [[degradation-vs-failure-boundary]] · [[migration-deploy-deps]]
