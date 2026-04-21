# CLAUDE.md - AI Assistant Guide

> Last Updated: 2026-04-20
> Purpose: Define strict rules for AI-assisted development  
> Scope: FastAPI + LangGraph/LangChain 기반 RAG & Agent 시스템

---

## 1. Project Overview

- Language: **Python 3.11+**
- Framework: **FastAPI**
- Agent Framework: **LangGraph / LangChain**
- Architecture: **Thin DDD** (Domain → Application → Infrastructure)
- RDB: **MySQL** / Vector DB: **Qdrant**
- TDD 필수: 테스트 먼저 작성 → 실패 확인 → 구현 → 통과 확인

---

## 2. Layer Responsibilities (요약)

| Layer | 역할 | 금지 |
|-------|------|------|
| **domain/** | Entity, VO, Policy, 규칙 정의, LoggerInterface | 외부 API·DB·LangChain 사용 |
| **application/** | UseCase, Workflow, LangGraph graph, 흐름 제어 | 비즈니스 규칙 직접 구현 |
| **infrastructure/** | MySQL, Qdrant, OpenAI, Adapter, StructuredLogger | 비즈니스 규칙 포함 |
| **interfaces/** | FastAPI router, request/response schema, Middleware 적용 | 비즈니스 로직 작성 |

---

## 3. Coding Conventions

- 클래스/모듈은 단일 책임
- 함수 길이 40줄 초과 금지
- if 중첩 2단계 초과 금지
- 명시적 타입 사용 (pydantic / typing)
- config 값 하드코딩 금지

---

## 4. AI Behavior Rules

**자율 수행 가능**: 리팩토링, 네이밍 개선, 테스트 추가, 성능/가독성 개선

**절대 금지**: 아키텍처 변경, 레이어 이동, DB 스키마 임의 변경, 대화 메모리 정책 변경, Parent/Child 문서 구조 변경

---

## 5. Output Format (AI Response Contract)

1. 요약 (What changed / Answer)
2. 설계 설명 (Why / Policy Mapping)
3. 코드 (필요한 범위만)
4. 주의사항 / 영향 범위

---

## 6. Forbidden Actions (절대 금지)

- domain → infrastructure 참조
- controller/router에 비즈니스 로직 작성
- 대화 기록을 vector db에 저장
- 요약 규칙 무시
- spec에 없는 기능 구현
- 과도한 추상화 (두꺼운 DDD)
- print() 사용 (logger 사용 필수)
- 스택 트레이스 없는 에러 처리
- Repository 내부에서 commit()/rollback() 호출
- 팩토리/서비스에서 get_session_factory()()로 세션 직접 생성
- 한 UseCase 안에서 repository 별 서로 다른 세션 사용

---

## 7. 세부 규칙 (필요 시 참조)

| 규칙 | 파일 | 참조 시점 |
|------|------|----------|
| DB 세션 & 트랜잭션 | `docs/rules/db-session.md` | DB/Repository 작업 시 |
| 로깅 & 에러 추적 | `docs/rules/logging.md` | 새 모듈 개발, 에러 처리 시 |
| 대화 메모리 정책 | `docs/rules/conversation-memory.md` | 대화 기능 개발 시 |
| RAG & 문서 규칙 | `docs/rules/rag-retrieval.md` | RAG/검색 관련 작업 시 |
| 테스트 & 작업 절차 | `docs/rules/testing.md` | 기능 추가, 버그 수정 시 |
| Task 파일 목록 | `docs/task-registry.md` | Task 조회, 새 task 추가 시 |
| Skills 목록 | `docs/skills.md` | 검증/개발 스킬 확인 시 |
