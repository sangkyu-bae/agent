# kb-document-management Completion Report

> **Status**: Complete (브라우저 육안 확인 1건 이월)
>
> **Project**: sangplusbot — idt (백엔드) + idt_front (프론트)
> **Version**: 브랜치 `feature/kb-document-management` (기준 1baf6d1, 미커밋)
> **Author**: 배상규 + Claude
> **Completion Date**: 2026-11-03
> **PDCA Cycle**: Plan → Design → Do(module 1~4) → Check, Act 반복 0회

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| 기능 | KB 상세 화면 문서 단건 삭제 + 컬렉션 문서 삭제 API 인증 전환 |
| 시작일 | 2026-11-02 |
| 종료일 | 2026-11-03 |
| 작업 공간 | worktree `../wt/kb-document` |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 98.5%   (Act 반복 0회)          │
├─────────────────────────────────────────────┤
│  ✅ FR 완료:          13 / 13                 │
│  ✅ Success Criteria:  6 / 7                  │
│  ⚠️ 부분 충족(이월):   1 / 7 (SC-6 브라우저)  │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **문제** | KB 상세 화면에 문서 삭제가 없어 P2가 컬렉션 화면이나 DB로 우회해야 했다. 우회 경로인 컬렉션 삭제 API는 위조 헤더만으로 임의 문서를 지울 수 있었다. |
| **해결** | KB 문서 삭제 API와 행 삭제 버튼을 추가했다. 소유자·ADMIN·업로더만 삭제할 수 있고, 요약 잡 진행 중에는 409로 막으며, 저장소 삭제가 모두 성공해야 메타데이터를 지운다. 컬렉션 삭제 API 2개는 토큰 인증으로 바꿨다. |
| **기능·UX 효과** | 실저장소 실런에서 삭제 후 해당 문서의 Qdrant·ES·메타데이터·잡 행이 모두 0건이 되었고, 같은 컬렉션의 다른 KB 문서는 그대로였다. 삭제한 문서는 리트리버 테스트 결과에서 빠졌다. ES 장애 시 503을 돌려주고 문서를 목록에 남겨, 복구 후 같은 버튼으로 다시 지울 수 있다. |
| **핵심 가치** | S1 "업로드 → 저장 상태 확인" 뒤의 되돌리기 단계를 DB·Swagger 조작 없이 화면에서 끝낼 수 있다. 무인증 삭제 경로가 막혀 KB 권한 검사를 우회할 수 없다. |

---

## 1.4 Success Criteria Final Status

| # | 기준 | 상태 | 근거 |
|---|------|:----:|------|
| SC-1 | 실저장소 삭제 후 해당 문서 0건, 다른 KB 문서 유지 | ✅ | 실런: Qdrant 4·ES 4·메타 1 → 0·0·0, 잡 행 0. 다른 KB 문서 4·4·1 유지 |
| SC-2 | 권한 표별 기대 상태 코드 | ✅ | `tests/api/test_knowledge_base_document_delete.py` (실제 가드·정책·UseCase 조립) |
| SC-3 | ES 실패 시 메타 유지·5xx, 복구 후 재시도 성공 | ✅ | 실런: 503, Qdrant 0·ES 4·메타 1, 목록 유지 → 재시도 200, 전부 0 |
| SC-4 | 진행 중 잡 409, stale 잡 삭제 | ✅ | 실런: `processing` 잡 409·데이터 불변 → stale로 바꾼 뒤 200 |
| SC-5 | 무토큰 위조 헤더 거부, 토큰 삭제 정상 | ✅ | 실런: 위조 헤더 401·데이터 불변, 토큰 200 |
| SC-6 | 브라우저에서 업로드 → 삭제 → 상태 해제, DB 조작 0회 | ⚠️ | 페이지 테스트 5건으로 흐름 검증. 실제 브라우저 확인은 이월(포트 8000·5173 개발 서버 교체 필요) |
| SC-7 | 삭제 후 리트리버 테스트에서 제외 | ✅ | 실런: 삭제 전 검색 노출 → 삭제 후 미노출, 다른 문서는 노출 |

**Success Rate**: 6/7 충족 (86%), 1건 부분 충족

## 1.5 Decision Record Summary

| 출처 | 결정 | 준수 | 결과 |
|------|------|:----:|------|
| [Plan] | 삭제 권한: 소유자·ADMIN·업로더 | ✅ | 부서원이 남의 문서를 지우는 경우와 PUBLIC 열람자를 모두 403으로 막았다 |
| [Plan] | 요약 잡 진행 중 409, stale 제외 | ✅ | 러너를 고치지 않고 경합을 막았다. 실런으로 확인 |
| [Plan] | 저장소 실패 시 메타 유지·재시도 | ✅ | 부분 삭제 후에도 DB 조작 없이 복구됐다 |
| [Plan] | 컬렉션 DELETE 2개 인증 전환 포함 | ✅ | 테스트 Red 단계에서 무인증 삭제를 재현한 뒤 막았다 |
| [Design] | Option C: 신규 UseCase + `delete_verified()` | ✅ | 컬렉션 경로의 기존 메서드와 테스트를 바꾸지 않았다. 기존 테스트 파일은 추가만 있고 삭제 줄 0 |
| [Design] | 메타·잡 행·활동 로그 1트랜잭션 | ✅ | 배선 테스트로 같은 세션 사용을 고정했다 |
| [Design] | `delete_verified` 호출 지점 1곳 | ✅ | AST 계약 테스트로 고정했다 |

---

## 2. Related Documents

| 단계 | 문서 | 상태 |
|------|------|------|
| Plan | [kb-document-management.plan.md](../01-plan/features/kb-document-management.plan.md) | ✅ |
| Design | [kb-document-management.design.md](../02-design/features/kb-document-management.design.md) | ✅ v0.2 |
| Check | [kb-document-management.analysis.md](../03-analysis/kb-document-management.analysis.md) | ✅ 98.5% |
| Report | 이 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | 요구사항 | 상태 |
|----|----------|:----:|
| FR-01 | KB 문서 단건 삭제 API | ✅ |
| FR-02 | 삭제 권한 정책(소유자·ADMIN·업로더) | ✅ |
| FR-03 | 판정 순서 404→403→404→403→409→503 | ✅ |
| FR-04 | 저장소 실패 시 메타데이터 유지, 503, 멱등 재시도 | ✅ |
| FR-05 | 진행 중 요약 잡 409, stale 제외 | ✅ |
| FR-06 | 잡 행 삭제 | ✅ (요청 세션 저장소에 추가, Design §1.3 정정) |
| FR-07 | 활동 로그에 `kb_id` 기록 | ✅ |
| FR-08 | 문서 목록 `can_delete` | ✅ |
| FR-09 | 컬렉션 DELETE 2개 토큰 인증 | ✅ |
| FR-10 | 행 삭제 버튼 (`can_delete` 행만) | ✅ |
| FR-11 | 확인 다이얼로그, 대기 중 이중 제출 차단, 오류 표시 | ✅ |
| FR-12 | 성공 후 캐시 무효화, 드릴다운·검색 범위 해제 | ✅ |
| FR-13 | 프론트 계약 동기화 | ✅ |

### 3.2 Non-Functional Requirements

| 항목 | 목표 | 결과 | 상태 |
|------|------|------|:----:|
| 보안 | 삭제 경로 3개 토큰 인증, 헤더 위조 무효 | 실런 401 확인 | ✅ |
| 데이터 정합성 | 삭제 대상만 0건, 다른 문서 유지 | 실런 확인 | ✅ |
| 성능 | 요청마다 클라이언트 생성 안 함 | 팩토리에서 1회 생성 | ✅ |
| 아키텍처 | 레이어 규칙, 함수 40줄, if 2단 | 신규 함수 모두 충족. DI 팩토리 90줄은 기존 구조와 동일 | ✅ |
| 호환성 | 기존 동작 불변 | 백엔드 회귀 신규 실패 0, 프론트 신규 실패 0, tsc 신규 오류 0 | ✅ |
| 접근성 | 버튼 이름에 파일명, 키보드 조작 | `IconButton` `aria-label`, RTL `getByRole` 테스트 | ✅ |

### 3.3 Deliverables

| 산출물 | 위치 |
|--------|------|
| 백엔드 신규 UseCase | `idt/src/application/knowledge_base/delete_document_use_case.py` |
| 백엔드 수정 10개 | 정책·값 객체·가드·목록 UseCase·저장소 2·`DeleteDocumentUseCase`·라우터 2·`main.py` |
| 백엔드 테스트 | 신규 5개 파일, 기존 5개 파일에 추가 |
| 프론트 신규 컴포넌트 | `idt_front/src/components/knowledge-base/DeleteKbDocumentDialog.tsx` |
| 프론트 수정 7개 | 상수·타입·서비스·훅·표·페이지·MSW 핸들러 |
| 프론트 테스트 | 신규 1개 파일, 기존 5개 파일에 추가 |
| 문서 | Plan, Design v0.2, Analysis, 이 보고서 |

DB 마이그레이션은 없다.

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| 항목 | 이유 | 우선순위 |
|------|------|:--------:|
| SC-6 브라우저 육안 확인 | 포트 8000·5173 개발 서버가 다른 코드로 실행 중이고 CORS가 5173만 허용. 서버 교체 후 확인 | High |
| 실제 섹션·문서 요약이 있는 문서의 삭제 실런 | 실런 문서는 요약 프로파일 없이 올라갔다. 요약도 같은 `document_id` 필터로 지워지는 것은 코드로만 확인 | Medium |
| `doc_browse_router` GET 2개 인증 | 문서 목록·청크 원문이 무인증으로 조회된다 | High |
| `kb-vector-cleanup` | KB soft-delete 후 벡터가 남는다 | Medium |

### 4.2 Cancelled/On Hold Items

| 항목 | 이유 |
|------|------|
| 문서 일괄 삭제 | Plan에서 제외 결정 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 지표 | 목표 | 결과 |
|------|------|------|
| Match Rate | 90% | 98.5% (구조 100, 기능 97, 계약 100, 런타임 97.6) |
| Critical·Important 이슈 | 0 | 0 |
| 백엔드 회귀 | 신규 실패 0 | master 기준선 실패 60건 대비 신규 0, 통과 +61 |
| 프론트 회귀 | 신규 실패 0 | 상시 실패 9건(4개 파일)과 동일, 수정 파일 0 |
| 타입 검사 | 신규 오류 0 | `tsc -b` 210 → 210 |

### 5.2 Resolved Issues

| 문제 | 해결 | 결과 |
|------|------|------|
| 컬렉션 삭제 API가 `X-User-Role` 헤더를 신뢰 | `get_current_user`로 전환 | ✅ 실런 401 |
| 제안서의 "가드로 검증 후 위임"은 읽기 권한만 검사 | 가드 뒤에 삭제 권한 정책 추가 | ✅ PUBLIC 열람자 403 |
| 기존 삭제 UseCase가 ES 실패를 삼키고 메타를 지움 | KB 경로에 엄격 삭제 진입점 추가 | ✅ 실런 503·재시도 성공 |
| 진행 중 요약 잡이 삭제 후 고아 요약 생성 가능 | 409 차단, stale 제외 | ✅ 실런 확인 |
| 문서 목록에 업로더 정보가 없어 버튼 노출을 판단할 수 없음 | `KbDocumentSummary.user_id` additive | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- Plan 전에 제안서의 전제를 코드와 대조해 2건을 정정했다. 그대로 구현했다면 PUBLIC 열람자가 삭제할 수 있었다.
- 보안 구멍을 코드 읽기로 찾은 뒤 테스트 Red 단계와 실런으로 각각 재현해 수정 전후를 증명했다.
- 판정 순서 테스트를 mock UseCase가 아니라 실제 가드·정책·UseCase 조립으로 작성했다. 순서 오류를 거짓 초록으로 넘길 수 없다.
- master를 detached worktree에 받아 기준선을 따로 측정해, 회귀를 실패 목록 diff로 증명했다.
- worktree 사용으로 master 작업 트리의 다른 미커밋 작업과 섞이지 않았다.

### 6.2 What Needs Improvement (Problem)

- Design에서 잡 행 삭제 위치를 싱글턴 스토어로 적었다가, 트랜잭션이 갈리는 문제를 Design 작성 중에 발견해 정정했다. 세션 경계는 Plan 조사 단계에서 확인해야 했다.
- gap-detector가 30턴 제한에 걸려 보고서를 내지 못했다. 범위가 큰 정적 분석은 확인 항목을 줄이거나 파일 단위로 나눠 맡겨야 한다.
- 페이지 테스트의 서버 지연을 클릭 두 번보다 짧게 잡아, 대기 중 닫기 검증이 한 번 잘못 실패했다.

### 6.3 What to Try Next (Try)

- 부작용 기능의 Plan 조사 항목에 "트랜잭션 경계(요청 세션 vs 싱글턴 세션)"를 넣는다.
- 이중 제출·대기 상태 테스트는 서버 지연을 넉넉히 두고 버튼 비활성도 함께 단언한다.
- 개발 서버가 이미 떠 있는 환경에서는 module-4 시작 전에 브라우저 확인 방식을 먼저 정한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| 단계 | 개선 제안 |
|------|-----------|
| Plan | 제안서 근거를 그대로 옮기지 말고 재사용 대상의 권한·실패 처리를 먼저 읽는다 |
| Design | 새 저장 경로가 어느 세션을 쓰는지 표로 적는다 |
| Do | 기준선 측정은 수정 없는 detached worktree에서 병렬로 시작한다 |
| Check | 정적 분석 에이전트에는 확인 항목 목록과 출력 파일 경로를 함께 준다 |

### 7.2 Tools/Environment

| 영역 | 제안 |
|------|------|
| 로컬 실행 | worktree별 백엔드 포트를 쓰려면 CORS 허용 목록을 설정값으로 빼야 한다 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 변경 커밋과 PR (현재 미커밋)
- [ ] SC-6 브라우저 육안 확인
- [ ] 배포 시: 마이그레이션 없음. 컬렉션 삭제 API가 토큰 필수로 바뀌므로 헤더만 보내던 외부 호출자가 있으면 401이 난다

### 8.2 Next PDCA Cycle

| 항목 | 우선순위 |
|------|:--------:|
| `doc_browse_router` GET 인증 | High |
| `kb-vector-cleanup` | Medium |
| 요약 포인트가 있는 문서의 삭제 실런 | Medium |

---

## 9. Changelog

### kb-document-management (2026-11-03)

**Added:**
- `DELETE /api/v1/knowledge-bases/{kb_id}/documents/{document_id}`
- KB 문서 목록 응답 `can_delete`
- KB 상세 화면 행 삭제 버튼과 확인 다이얼로그

**Changed:**
- 컬렉션 문서 삭제 DELETE 2개: `X-User-Id`·`X-User-Role` 헤더 대신 Bearer 토큰으로 사용자와 역할 판정. ADMIN은 이제 실제 ADMIN 권한으로 판정된다

**Fixed:**
- 위조 헤더만으로 임의 문서를 삭제할 수 있던 문제

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-03 | 완료 보고서 작성 | 배상규 + Claude |
