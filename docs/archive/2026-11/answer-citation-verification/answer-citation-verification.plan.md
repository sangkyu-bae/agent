# answer-citation-verification Planning Document

> **Summary**: 답변 모델이 문장마다 근거 청크 번호를 달고, 근거 판정기가 그 인용을 검증해 "어느 문서 몇 쪽의 어느 문장을 보고 썼는지"만 보여 준다
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-20
> **Status**: Draft
> **Related**: `docs/archive/2026-11/source-passage-viewer` (원문 뷰어, PR #124), `docs/wiki/backend/patterns/grounding-rewrite-loop.md` (근거 판정 루프), `idt/docs/archive/2026-10/judgment-backend` (Jev 판정 포트, PR #77)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 근거 칩은 검색된 청크 전체를 보여 준다. 사용자는 그중 무엇이 답변의 어느 문장을 뒷받침하는지 알 수 없고, 원문 뷰어도 청크 전체에 음영을 칠해 "어느 구절"인지 좁혀 주지 못한다. BM25로 찾은 청크에는 쪽 번호도 없다. |
| **Solution** | 검색 결과에 실행 단위 번호를 붙여 답변 모델이 문장 끝에 `[n]`을 달게 한다. 답변마다 이미 도는 근거 판정기(GroundedGenerator)의 같은 호출에서 인용 쌍을 검증하고 근거 문장을 뽑는다. 검증된 인용을 DB에 저장해 칩·원문 뷰어·재진입에서 같은 결과를 보여 준다. 선행으로 ES 청크 쪽 번호와 청킹 한글 깨짐을 고친다. |
| **Function/UX Effect** | 답변 문장 끝에 `[1]` 표시가 붙고, 칩에는 `1 파일명 · 3쪽 · "근거 문장…" [원문 보기]`만 남는다. 쓰지 않은 구절은 접힌 목록으로 내려가고, 검증된 인용이 없으면 "근거 확인 안 됨"을 표시한다. 원문 뷰어는 근거 문장만 진하게 칠한다. |
| **Core Value** | 금융·정책 답변의 문장 단위 출처를 검증된 상태로 제시한다. 지어낸 인용이 화면에 나가지 않고, 근거가 없을 때는 없다고 말한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 칩이 "검색한 것"만 보여 주고 "답변에 쓴 것"을 보여 주지 않아 신뢰 근거가 되지 못한다 |
| **WHO** | 채팅에서 RAG 답변을 받는 사용자, 답변 근거를 점검하는 에이전트 소유자(P2), 판정 모델을 고르는 관리자 |
| **RISK** | 판정 프롬프트 확장이 기존 근거 판정 품질(gpt-4o 벤치 결과)을 떨어뜨린다. 모델이 인용 표시를 빠뜨리면 "근거 확인 안 됨"이 남발된다 |
| **SUCCESS** | 스위치 off면 기존과 동일. on이면 인용 정확도 90% 이상, 지어낸 인용 제거 100%, 추가 LLM 호출 0회, 신규 업로드 문서의 인용 100%에 쪽 번호, 재진입 시 같은 인용 |
| **SCOPE** | 백엔드: 청킹 U+FFFD 수정, ES page 메타, 검색 결과 번호 부여, 판정기 확장, 인용 저장(V093), 판정 모델 관리자 설정(V094). 프론트: `[n]` 렌더, 칩 정리, 문장 단위 음영, 관리자 판정 모델 화면. 웹 검색·MCP 결과 인용과 기존 문서 재청킹은 제외 |

---

## 1. Overview

### 1.1 Purpose

답변 근거를 "검색된 청크 묶음"에서 "답변 문장 ↔ 문서·쪽·근거 문장" 쌍으로 좁히고, 그 쌍을 검증된 것만 보여 준다.

### 1.2 Background — 현재 코드 기준 사실

| 항목 | 현재 상태 | 근거 |
|------|----------|------|
| 검색 결과 텍스트 | 청크마다 `[출처: 파일명]\n본문`만 넘긴다. 같은 파일의 청크는 이름표가 같아서 답변 모델이 청크를 구별해 인용할 수 없다 | `idt/src/application/rag_agent/tools.py:540` `_format_results` |
| 최종 답변 프롬프트 | 검색 결과를 `[수집된 검색 결과]` 블록으로 원문 그대로 싣는다(LLM 요약 없음) | `idt/src/application/agent_builder/workflow_compiler.py:1813` |
| 근거 판정 | `GroundedGenerator`가 답변마다 판정→재작성→문장 제거 루프를 돈다. 기본 on, 판정 모델 `gpt-4o`. 판정 결과는 "근거 없는 주장" 목록뿐이고 "어느 구절이 뒷받침하는가"는 내지 않는다 | `workflow_compiler.py:1930` `_generate_final_answer`, `idt/src/domain/hallucination/grounding.py` `GroundingVerdict` |
| 판정 모델 지정 | `.env`의 `GROUNDING_JUDGE_MODEL` 이름으로 등록 모델을 찾는다. 관리자 화면에서 바꿀 수 없다 | `idt/src/config.py:169`, `idt/src/api/main.py:917` |
| 관리자 설정 패턴 | 기능별 단일 행 설정 테이블 + 관리자 API + 관리자 화면 (`multimodal_setting`, `kb_default_setting`, `graph_rag_setting`) | `idt/db/migration/V065·V084·V086`, `idt_front/src/pages/AdminMultimodalPage` |
| 스트리밍 | 판정 루프 때문에 최종 답변은 이미 완성본으로 한 번에 전송된다 | 위키 grounding-rewrite-loop §4 |
| 칩 구성 | 검색 기록(`ai_retrieval_source`) 전체로 만든다. 원문 뷰어는 그 청크 전부에 음영을 칠한다 | `idt/src/application/agent_run/run_sources.py`, `source_policy.py` |
| ES 쪽 번호 | KB 업로드의 ES 본문에 `page`를 넣지 않는다. Qdrant 청크에는 있다 | `idt/src/application/unified_upload/use_case.py:309` |
| 청킹 한글 깨짐 | 토큰 단위로 자르고 다시 디코딩해, 한글 한 글자가 토큰 경계에 걸리면 U+FFFD가 생긴다 | `idt/src/infrastructure/chunking/base_token_chunker.py:38` `split_by_tokens` |
| Jev 판정 포트 | 머지됨(PR #77), 기본 off, 검색 여부 판정 한 곳에만 연결. 실호출 스모크 미실행 | `idt/src/domain/judgment/`, `config.py:403` |

### 1.3 사용자 확정 사항 (2026-11-20)

| 질문 | 결정 |
|------|------|
| 인용 결정 방식 | 답변 모델이 `[n]`으로 인용하고, 검증기가 인용된 쌍만 검증한다 |
| 검증 엔진 | 기존 근거 판정기를 확장한다(추가 호출 없음). 판정 모델은 gpt-4o 고정을 풀어 **관리자가 화면에서 고르게** 한다 |
| 화면 | 본문 `[n]` + 칩에는 인용된 구절만(파일·쪽·근거 문장). 쓰지 않은 구절은 접힌 목록 |
| 검증된 인용 0건 | "근거 확인 안 됨" 표시 + 검색된 구절은 접힌 목록 |
| 함께 할 선행 작업 | ES 청크 쪽 번호, 청크 안 문장 단위 음영, 청킹 U+FFFD 수정 (세 가지 모두) |
| 재진입 | 검증된 인용을 DB에 저장해 기록에서 다시 열어도 같게 보인다 |
| 인용 대상 | 내부 문서 검색 결과만. 웹 검색·MCP 도구 결과는 지금처럼 둔다 |
| 켜고 끄기 | env 킬스위치 기본 off(탈착형). 관리자 화면은 판정 모델 선택만 |

### 1.4 계획 단계에서 정한 기본값 (Design에서 재확인)

| 항목 | 기본값 | 이유 |
|------|--------|------|
| 적용 실행 경로 | Agent Builder supervisor 그래프의 `final_answer` 노드 | 판정 루프가 붙어 있는 유일한 답변 경로. 다른 경로(일반 RAG 채팅 등)는 인용 데이터를 만들지 않으므로 칩을 **지금처럼** 보여 준다("근거 확인 안 됨"으로 오해시키지 않는다) |
| 근거 판정 off + 인용 on | 판정기를 인용 검증 전용으로 1회 호출한다(재작성·문장 제거는 하지 않음) | 인용 기능이 근거 판정 플래그에 묶이지 않게 |
| 번호 범위 | 실행(run) 단위로 1부터 증가. 같은 청크가 여러 검색에서 다시 나오면 같은 번호 | 한 답변 안에서 검색을 여러 번 해도 번호가 겹치지 않게 |
| 판정기 실패 | fail-open — 답변은 그대로 내보내고 인용은 "검증 안 됨"(0건 처리)으로 저장 | 기존 판정 루프 원칙과 같음 |
| 기존 문서 | 다시 청킹하지 않는다. U+FFFD 수정·ES page는 새 업로드부터 적용 | 지난 사이클 결정과 같음 |

---

## 2. Scope

### 2.1 In Scope

- [ ] **선행 1 — 청킹 U+FFFD 수정**: 토큰 경계가 한글 글자 중간에 걸려도 깨진 문자가 생기지 않게 분할 (새 업로드부터)
- [ ] **선행 2 — ES 청크 쪽 번호**: KB 업로드 ES 본문에 `page` 저장, 검색 결과 metadata로 전달 (새 업로드부터)
- [ ] **인용 번호 부여**: 내부 문서 검색 결과 텍스트에 실행 단위 번호 라벨(`[출처 3: 파일명 · 5쪽]`), 번호↔chunk_id 대응 기록. 스위치 on일 때만
- [ ] **답변 인용 지시**: 최종 답변 프롬프트에 "근거 문장 끝에 `[n]`" 지시 추가. 스위치 on일 때만
- [ ] **판정기 확장**: 같은 판정 호출에서 인용 쌍별 뒷받침 여부 + 청크 안 근거 문장(원문 그대로) 반환. 결정적 검증(인용 번호 존재·근거 문장이 청크에 실제로 있음)
- [ ] **인용 정리 정책**: 검증 탈락 인용의 `[n]` 표시 제거, 번호 재정렬, 0건 판정
- [ ] **인용 저장 (V093)**: 실행별 인용(번호·chunk_id·document_id·쪽·근거 문장·검증 결과) 저장, 재진입 조회
- [ ] **칩 계약 확장**: 답변 완료 이벤트·재진입 DTO에 `citations`(검증된 인용)와 미사용 구절 구분, 0건 표시 상태
- [ ] **판정 모델 관리자 설정 (V094)**: 단일 행 설정 테이블 + 관리자 API + 관리자 화면. 비면 `.env` 값으로 폴백. 기존 근거 판정과 인용 검증이 같은 모델 사용
- [ ] **프론트 — 본문 `[n]`**: 답변 마크다운의 인용 표시를 작은 번호로 렌더, 누르면 해당 인용 칩·원문 뷰어로 이동
- [ ] **프론트 — 칩 정리**: 인용된 구절만 파일·쪽·근거 문장으로, 미사용 구절은 접힌 목록, 0건이면 "근거 확인 안 됨"
- [ ] **프론트 — 문장 단위 음영**: 원문 뷰어(텍스트·PDF·docx)에서 근거 문장을 진하게, 청크 나머지는 옅게
- [ ] 킬스위치 `ANSWER_CITATION_ENABLED`(기본 false) + AST 경계 테스트 (탈착형)

### 2.2 Out of Scope

- 웹 검색·MCP·기타 도구 결과의 인용
- 기존 업로드 문서의 재청킹·ES 재색인 (U+FFFD·page는 새 업로드부터)
- Jev 판정 포트로의 교체 (포트 분리 여지는 Design에서 판단하되 이번 구현은 LLM 판정)
- 에이전트별 인용 on/off
- 관리자 화면의 인용 기능 on/off (env 스위치만)
- action 초안(draft) 경로의 인용 — 초안은 기존 판정 루프 그대로
- supervisor 그래프 밖의 답변 경로(일반 RAG 채팅, 딥서치 등)의 인용 생성
- 모바일 폭 전용 레이아웃

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 토큰 분할 시 한글 등 멀티바이트 글자를 경계에서 자르지 않는다. 결과 청크에 U+FFFD가 원문에 없던 위치로 생기지 않는다 | High | Pending |
| FR-02 | KB 업로드 ES 본문에 청크 `page`를 저장하고, BM25 검색 결과 metadata에 `page`가 실린다 | High | Pending |
| FR-03 | 스위치 on일 때 내부 문서 검색 결과 각 청크에 실행 단위 번호 라벨을 붙이고 번호↔chunk_id(+document_id·page)를 실행 컨텍스트에 기록한다. 같은 chunk_id는 같은 번호 | High | Pending |
| FR-04 | 스위치 on이고 번호가 붙은 검색 결과가 있으면 최종 답변 프롬프트에 `[n]` 인용 지시를 넣는다 | High | Pending |
| FR-05 | 근거 판정 호출이 인용 쌍마다 `supported` 여부와 청크 원문 안의 근거 문장(그대로 인용)을 함께 반환한다. 근거 판정 off여도 인용 on이면 검증 전용 1회 호출 | High | Pending |
| FR-06 | 결정적 검증: 존재하지 않는 번호, 청크에 글자 그대로 없는 근거 문장은 탈락시킨다 | High | Pending |
| FR-07 | 탈락 인용의 `[n]` 표시는 답변 본문에서 지우고, 남은 인용을 1부터 다시 번호 매긴다. 재작성·문장 제거 후의 최종 본문 기준으로 정리한다 | High | Pending |
| FR-08 | 검증된 인용을 실행별로 저장(V093)하고 재진입 API가 같은 인용을 돌려준다 | High | Pending |
| FR-09 | 답변 완료 이벤트·재진입 DTO의 근거 칩에 검증된 인용 목록(번호·파일·쪽·근거 문장·chunk_id)과 미사용 구절 구분, 상태(`verified`/`none`/`not_applicable`)를 싣는다 | High | Pending |
| FR-10 | 판정 모델 설정(V094): 관리자 API로 등록 모델 중 하나를 고른다. 비거나 고른 모델이 비활성·삭제되면 `.env` `GROUNDING_JUDGE_MODEL`로 폴백한다. 변경은 캐시 TTL 안에 반영 | High | Pending |
| FR-11 | 관리자 화면에서 판정 모델을 고르고 현재 적용 모델(폴백 여부 포함)을 확인한다 | Medium | Pending |
| FR-12 | 답변 본문의 `[n]`을 작은 번호로 렌더하고, 누르면 해당 인용의 원문 뷰어를 연다 | High | Pending |
| FR-13 | 칩: 인용된 구절만 `번호 · 파일명 · 쪽 · "근거 문장"`으로 표시, 미사용 구절은 "검색했지만 답변에 쓰지 않은 구절 N건" 접힘, `none`이면 "근거 확인 안 됨" 배지, `not_applicable`이면 기존 칩 그대로 | High | Pending |
| FR-14 | 원문 뷰어는 근거 문장을 진하게, 같은 청크의 나머지는 옅게 칠한다. 근거 문장 매칭 실패 시 청크 전체 음영으로 내려간다 | High | Pending |
| FR-15 | 스위치 off면 검색 결과 텍스트·답변 프롬프트·판정 호출·이벤트 payload·화면이 기존과 동일하다 | High | Pending |
| FR-16 | 판정기 실패·타임아웃은 답변을 막지 않는다(fail-open). 인용 상태는 `none`으로 저장하고 경고 로그를 남긴다(원문·주장 값은 로그에 싣지 않음) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 비용 | 근거 판정 on 상태에서 인용 on이 추가하는 LLM 호출 0회 | `ai_run.llm_call_count` 스위치 on/off 비교 |
| 지연 | 판정 출력이 길어져 늘어나는 답변 완료 시간 p50 +1.5초 이하 | 골든셋 10문항 on/off 비교 |
| 품질 | 기존 근거 판정 벤치(정상 7 + 날조 3) 결과가 확장 전과 같다 | 미니 벤치 재실행 |
| 보안 | 인용 조회는 기존 실행 조회 권한과 같은 검사. 근거 문장 노출은 원문 뷰어 KB 권한 검사를 따른다 | 권한 테스트 |
| 탈착성 | 스위치 off·조립 실패 시 기존 동작. 인용 모듈 import는 DI·라우터·선언된 이음매만 | AST 경계 테스트 |
| 로깅 | 판정 실패는 스택 포함 경고, 주장·근거 원문은 로그 제외 | LOG-001 검증 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-16 구현, 백엔드 pytest·프론트 vitest 신규 테스트 통과, 기존 실패 목록 외 회귀 0
- [ ] 마이그레이션 V093·V094 DDL에 테이블·전 컬럼 COMMENT (`test_migration_ddl_comments.py` 통과)
- [ ] 라이브 확인: 가계부채 PDF를 새로 올려 질문 → `[n]`·칩·쪽·문장 음영·재진입까지 화면 확인
- [ ] 관리자 화면에서 판정 모델 변경 → 다음 실행에 반영 확인

### 4.2 Success Criteria (측정 가능)

| SC | 기준 |
|----|------|
| SC-1 | 스위치 off에서 기존 테스트 전부 통과, 이벤트 payload에 인용 필드 없음(또는 null) |
| SC-2 | 골든셋(가계부채 PDF 10문항) 수기 라벨 대비 인용 정확도(표시된 인용 중 실제 뒷받침) 90% 이상 |
| SC-3 | 양성 대조군: 일부러 틀린 번호를 단 답변 5건에서 잘못된 인용 100% 탈락 |
| SC-4 | 신규 업로드 문서의 인용 100%에 쪽 번호 표시(Qdrant·ES 히트 모두, PDF 기준) |
| SC-5 | 근거 문장 음영 매칭 성공률 90% 이상(신규 업로드 PDF) |
| SC-6 | 근거 판정 on일 때 추가 LLM 호출 0회, 답변 완료 p50 증가 1.5초 이하 |
| SC-7 | 재진입 시 실시간 화면과 같은 인용 표시 |
| SC-8 | 검증 0건이면 "근거 확인 안 됨", supervisor 밖 경로는 기존 칩 그대로 |
| SC-9 | 한글 픽스처 청킹 결과 U+FFFD 0건(원문에 없는 경우) |
| SC-10 | 기존 근거 판정 미니 벤치(정상 7·날조 3) 결과 변화 없음 |

### 4.3 Quality Criteria

- [ ] 새 모듈 테스트 커버리지 80% 이상
- [ ] ruff·eslint 신규 오류 0 (main.py는 전체 format 금지 — Edit로만)
- [ ] 프론트 빌드 성공

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 판정 프롬프트 확장이 근거 없는 주장 탐지 품질을 떨어뜨림 | High | Medium | Design 단계에서 확장 프롬프트로 기존 벤치(정상 7·날조 3) + 인용 양성 대조군을 먼저 돌린다. 품질이 떨어지면 같은 포트 뒤에 인용 검증 전용 호출로 분리하는 대안을 Design에 둔다(비용 증가 감수) |
| 관리자가 고른 모델이 판정에 약함(위키: 4o-mini는 정상 7/7 오판) | High | Medium | 관리자 화면에 "판정 품질은 모델에 따라 크게 달라진다" 안내와 벤치 결과 링크. 모델 선택은 막지 않는다 |
| 답변 모델이 `[n]`을 빠뜨림(모델별 편차) | Medium | Medium | 모델별(gpt-4o-mini·Claude) 골든셋으로 인용 누락률 측정. 누락 시 "근거 확인 안 됨"이 정직한 결과라 기능상 안전하지만, 누락률이 높으면 프롬프트 보강 |
| 검색 결과 번호 라벨이 다른 소비자에 영향(analysis 노드, 판정 코퍼스, ReAct 경로) | Medium | High | 라벨은 스위치 on일 때만. 판정 코퍼스는 번호를 그대로 쓰는 쪽이 유리. 영향 경로는 §6에 나열하고 테스트로 고정 |
| 같은 chunk_id가 여러 검색에서 다른 번호를 받음 | Medium | Medium | 실행 컨텍스트에 chunk_id→번호 사전 유지(FR-03) |
| 재작성·문장 제거 후 본문의 `[n]`과 판정 결과가 어긋남 | Medium | Medium | 인용 정리는 판정 루프 종료 후 최종 본문 기준으로 한 번 더 수행(FR-07) |
| U+FFFD 수정이 청크 경계·토큰 수를 바꿔 검색 품질이 달라짐 | Medium | Low | 새 업로드부터만 적용, 청크 크기 상한(토큰) 유지 테스트 |
| ES 인덱스 매핑이 `page` 필드를 받지 않음(strict 매핑) | Medium | Low | Design에서 매핑 확인. 필요하면 매핑 추가(재색인 없이 새 필드) |
| 마이그레이션 2건(V093·V094) 운영 적용 순서 | Low | Low | 두 테이블 모두 신규 생성(기존 테이블 변경 없음). 스위치 off면 비어 있어도 동작 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `BaseTokenChunker.split_by_tokens` | 청킹 | 멀티바이트 경계 보정 |
| KB 업로드 ES 본문 | 색인 스키마 | `page` 필드 추가 |
| `InternalDocumentSearchTool._format_results` 출력 텍스트 | 프롬프트 계약 | 스위치 on일 때 번호 라벨 |
| 최종 답변 프롬프트 | 프롬프트 | 스위치 on일 때 인용 지시 |
| `GroundingJudgePort` / `GroundingVerdict` | 도메인 포트·VO | 인용 검증 결과 필드 추가(기본 빈 값) |
| 판정 프롬프트·어댑터 | infrastructure | 인용 쌍 입력·출력 스키마 |
| `RunSourceItem` / `SourceItemDto` / 프론트 `types/chat.ts` | API 계약 | `citations`·상태 필드 추가(선택 필드) |
| 판정 LLM 공급자(`get_grounding_judge_llm_provider`) | DI | DB 설정 우선, env 폴백 |
| `ai_answer_citation`(V093) | DB 신규 | 실행별 검증된 인용 |
| `grounding_judge_setting`(V094, 이름은 Design에서 확정) | DB 신규 | 판정 모델 단일 행 설정 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `split_by_tokens` | READ | full_token·parent_child 등 토큰 기반 청킹 전략 전부 | 새 업로드 청크 경계 변화 — 테스트 필요 |
| ES 본문 | WRITE | `unified_upload/use_case.py:309`, `chunk_and_index/use_case.py:77`, `morph_index/use_case.py:134` | KB 업로드 경로 우선, 나머지 두 경로는 Design에서 범위 결정 |
| ES 본문 | READ | `hybrid_search/use_case.py`, KB 청크 조회 | 필드 추가는 하위호환 |
| 검색 결과 텍스트 | READ | `final_answer_node`, analysis 노드, `_answer_grounding_sources`, ReAct 워커, 일반 RAG 채팅 | 스위치 off면 영향 없음, on이면 라벨 형식 변화 — 경로별 테스트 |
| `GroundedGenerator.run` | CALL | final_answer(답변), `action_pipeline.py:180`(초안) | 초안 경로는 인용 미요청 — 기존 결과 동일해야 함 |
| `GroundingJudgePort.judge` | IMPLEMENT | 판정 LLM 어댑터, 테스트 더블 | 반환 VO 필드 추가는 기본값으로 하위호환 |
| 칩 payload | READ | `SourceCitation.tsx`, `SourceViewerMount`, 재진입 화면 | 선택 필드 — 없으면 기존 렌더 |
| 판정 LLM 공급자 | READ | 근거 판정(답변·초안), 인용 검증 | 관리자 설정이 두 용도에 같이 적용됨 — 화면 문구에 명시 |
| 답변 본문 `[n]` | READ | `MarkdownRenderer.tsx`, 메시지 저장·복사·피드백 | 저장 본문에 `[n]`이 남음 — 스위치를 꺼도 과거 메시지는 숫자 표시로 렌더 |

### 6.3 Verification

- [ ] 위 소비자 경로별 스위치 on/off 테스트
- [ ] 초안(action) 경로 판정 결과가 확장 전과 같음
- [ ] 판정 미니 벤치 재실행

---

## 7. Architecture Considerations

### 7.1 Project Level

Enterprise 성격의 기존 모노레포(Thin DDD 백엔드 + React SPA). 새 프레임워크 도입 없음.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 인용 결정 | 모델 인용만 / 사후 판정만 / 모델 인용+검증 | 모델 인용+검증 | 사용자 결정. 판정 쌍을 인용된 것으로 한정해 비용 억제 |
| 검증 엔진 | 기존 판정기 확장 / 별도 LLM 호출 / Jev | 기존 판정기 확장 | 사용자 결정. 추가 호출 0회. 품질 저하 시 분리 대안(§5) |
| 판정 모델 지정 | env 고정 / 관리자 설정 | 관리자 설정 + env 폴백 | 사용자 요구("유연하게 관리자가 선택"). 기존 단일 행 설정 패턴 재사용 |
| 탈착 방식 | env 스위치 / 관리자 on·off / 에이전트별 | env 스위치 기본 off | 사용자 결정. 지난 원문 뷰어와 같은 탈착형 이음매 |
| 인용 영속화 | 실시간만 / 신규 테이블 | 신규 테이블(V093) | 재진입·감사·통계 |
| 번호 체계 | 청크 해시 라벨 / 실행 단위 순번 | 실행 단위 순번 | 모델이 짧은 숫자를 안정적으로 인용 |

### 7.3 레이어 배치 (초안 — Design에서 확정)

```
domain/answer_citation/      인용 VO·정리 정책(번호 재정렬·탈락 제거·0건 판정)·저장 포트
domain/hallucination/        GroundingVerdict 에 인용 검증 결과 필드 추가
application/answer_citation/ 번호 레지스트리(실행 컨텍스트)·인용 정리·저장 유스케이스
infrastructure/answer_citation/ 인용 저장 리포지토리(V093)
infrastructure/hallucination/ 판정 프롬프트·파서 확장
infrastructure/grounding_setting/ 판정 모델 설정 리포지토리(V094)
api/answer_citation_di.py    조립(스위치 off → None)
api/routes/admin_grounding_router.py  판정 모델 관리자 API
```

---

## 8. Convention Prerequisites

- 백엔드: `idt/CLAUDE.md` (함수 40줄·if 2단계·print 금지·Repository commit 금지·DDL COMMENT), `docs/rules/rag-retrieval.md`, `docs/rules/logging.md`, `docs/rules/db-session.md`
- 프론트: 컴포넌트 파일 런타임 상수 export 금지(`as const`는 `src/types/*.ts`), ApiError 인터셉터 경로
- 위키: 탈착형 모듈 이음매, 근거 판정 재작성 루프(판정기 새 기능은 양성 대조군 벤치 필수), LLM 출력 신뢰 경계
- `src/api/main.py`는 `ruff format` 전체 실행 금지 — Edit로만 수정

---

## 9. Next Steps

1. [ ] `/pdca design answer-citation-verification` — 아키텍처 3안, 판정 프롬프트 확장 미니 벤치 계획, 테이블 DDL, 이벤트 계약
2. [ ] Design 승인 후 전용 worktree(`wt/answer-citation`) 생성, 마이그레이션 번호 V093·V094 선점 확인
3. [ ] 모듈 순서: 선행(U+FFFD → ES page) → 번호 부여·프롬프트 → 판정 확장·벤치 → 저장·계약 → 관리자 설정 → 프론트

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-20 | 최초 작성 — 사용자 질의 2회(8항목) 반영 | 배상규 |
