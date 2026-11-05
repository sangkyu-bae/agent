# agent-kb-quick-setup Gap Analysis (Check)

> **Date**: 2026-11-05
> **Plan**: [agent-kb-quick-setup.plan.md](../01-plan/features/agent-kb-quick-setup.plan.md)
> **Design**: [agent-kb-quick-setup.design.md](../02-design/features/agent-kb-quick-setup.design.md)
> **코드**: worktree `../wt/kb-quick-setup` (브랜치 `feature/agent-kb-quick-setup`, 미커밋)
> **방법**: gap-detector 정적 분석(3축) + 런타임 검증(L1 API, L2 UI, L3 E2E — 워크트리 백엔드 :8010 + 프론트 :5176, 실 DB·Qdrant·LLM)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | KB를 에이전트에 붙이는 데 4개 화면·약 15개 결정이 필요하고, 벡터 크기·거리 함수 같은 용어가 비개발자를 막는다. |
| **WHO** | P2 부서 담당자(비개발자)와 IT 운영자(반개발자). 관리자(P3)는 기본 임베딩 모델을 1회 설정한다. |
| **RISK** | KB마다 컬렉션 1개 전략으로 Qdrant 컬렉션 수가 KB 수만큼 늘어난다. 자동 생성 KB가 에이전트 저장 취소 후 고아로 남는다. 부분 업로드 실패를 성공으로 위장할 가능성. |
| **SUCCESS** | 신규 사용자가 스튜디오·위저드 각각에서 파일 업로드만으로 RAG 에이전트를 만들고 테스트 채팅에서 문서 근거 답변을 받는다. 기존 KB·컬렉션·RAG 설정 경로 회귀 0건. |
| **SCOPE** | M1 기본 임베딩 모델 설정·컬렉션 자동 배정 → M2 KB 원스톱 생성 API → M3 스튜디오 도구함 "지식 문서" 블록·RAG 패널 고급 접기 → M4 위저드 문서 단계 |

---

## 1. Match Rate

| 축 | 비율 | 근거 |
|---|:-:|---|
| Structural | 98.5% | Design §11.1 파일 34개 중 33개 존재·1개 이름 부분 일치(`useUpdateAdminKbDefaults`). 신규 파일 전부 §9.4 레이어 배치와 일치 |
| Functional | 95% | §5.4 Page UI Checklist 21.5/23 + Plan FR 역추적 14.5/15 |
| Contract | 92% | API 6/6 3-way 일치, §6.1 오류 코드 5/6(`COLLECTION_NAME_CONFLICT` 코드 미구현, 409 문자열 detail) |
| Runtime | 97% | L1 18/18, L2·L3 SC-1~SC-6 전부 통과. R1(연결 후 건너뛰기 시 kb_id 전송)은 미확인 |
| **Overall** | **95.5%** → Act-1 후 **98.9%** | 0.15·S + 0.25·F + 0.25·C + 0.35·R. Act-1: G1·G2 코드 수정(Functional 100), G3~G6 Design 갱신(Structural 100·Contract 100) |

(정적만의 참고값: 94.5%, gap-detector v2.1.1 6축 가중 91.3%)

---

## 2. 전략 정합(Strategic Alignment)

- **WHY 충족**: 스튜디오·위저드 모두에서 사용자가 정하는 것은 "파일"과 (서버 기본값인) 공개 범위뿐이다. 컬렉션·벡터·거리 함수·청킹·검색 모드 용어는 간단 모드 화면에 나오지 않는다(런타임 DOM 검사 0건).
- **Plan 결정 준수**: KB마다 컬렉션 1개(`kb-{id8}`) ✅, 관리자 전역 설정은 기본 임베딩 모델 1개 ✅, KB 이름 `{에이전트명} 지식`·범위 PERSONAL ✅, 설계안 C(서버 `/quick` + 기존 UseCase 조합, 파이프라인 optional `kb_id`) ✅.
- **의도된 편차(gap 아님)**: 스튜디오 생성 폼에 visibility 필드가 없어 블록은 `visibility="private"` 고정. PromptStep [이전]은 tools 단계로(FR-09 유지). MSW 핸들러는 multipart를 파싱하지 않음.

---

## 3. Plan Success Criteria

| SC | 판정 | 근거 |
|---|:-:|---|
| SC-1 스튜디오 PDF 드롭 → 저장 → 테스트 채팅 근거 답변 | ✅ Met | 실런: 블록 업로드 → "연결됨: [CHECK] 퀵셋업봇 지식" → 저장 → 에이전트 워커 `internal_document_search` `tool_config.kb_id`=KB id, 컬렉션 `kb-0b838911` points 2 → 테스트 채팅 답변 "주중 오전 9시~오후 6시, 4821"(문서 내용) |
| SC-2 위저드 업로드 → 생성 → 상세에 RAG+KB | ✅ Met | 실런: 도구 확정 → 문서 단계 업로드 → 계속 → 프롬프트 → 스튜디오 프리필(연결됨 배지) → 저장 → 워커 `internal_document_search` kb_id=`2ccb6a8a…`, KB `문서 Q&A 지식` PERSONAL `kb-2ccb6a8a` |
| SC-3 미설정 문구 노출 | ✅ Met | 설정 NULL 상태에서 블록 `role=alert` "관리자가 기본 임베딩 모델을 설정해야 합니다", 파일 입력 disabled, 기존 KB 선택은 가능 |
| SC-4 2개 중 1개 실패 시 파일명 표시 + 도구 연결 | ✅ Met | 위저드에서 정상 PDF + 깨진 PDF: "broken.pdf: Failed to open stream", 진행 카드 1/2, 도구 연결 완료. 백엔드 스모크(module-2)와 동일 |
| SC-5 `/knowledge-bases`에 `{이름} 지식`·범위 일치 | ✅ Met | KB 목록 API: `('[CHECK] 퀵셋업봇 지식','PERSONAL','kb-0b838911')`, 에이전트 visibility private와 일치 |
| SC-6 금지 용어 7종 없음 | ✅ Met | 블록 DOM 텍스트 검사 결과 `forbidden: []` + 컴포넌트 테스트 |
| SC-7 회귀 FAILED diff 비어 있음 | ✅ Met | 백엔드 53건 = master 상시 실패 목록(module-1·2·3·4 전 시점 동일). 프론트 9건 = 상시 실패 9건(AgentBuilderPage 추가 실패는 부하 시 플레이크, 단독 실행 통과) |

**7/7 Met.**

---

## 4. 런타임 검증 기록

### L1 API (인프로세스 스모크 + :8010 curl)

| # | 요청 | 결과 |
|---|---|---|
| 1-6 | admin GET/PUT kb-defaults, 사용자 GET | 200/200/200, configured 전이, warnings=[] |
| 7 | POST /knowledge-bases `collection_name` 생략 | 201 `kb-{id8}`, 활동 로그 CREATE `embedding_model=text-embedding-3-small`, Qdrant 1536·Cosine |
| 8 | 미설정 + 생략 | 422 `KB_DEFAULTS_NOT_CONFIGURED` (라우터 테스트) |
| 10-13 | /quick 정상 2개 / 정상+깨짐 / 0·11개·.exe / 같은 이름 2회 | 201 uploaded 26청크 / 201 1+1 failed "Failed to open stream" / 422 / ` (2)` 접미 |
| 16-18 | agents/pipeline kb_id 지정·미지정·권한 없음 | 라우터·UseCase 테스트 + 위저드 실런(CREATE가 RAG 워커 주입) |

### L2 UI (워크트리 :5176, 관리자 토큰)

- 관리자 `/admin/kb-defaults`: 사이드 nav "문서·품질 > 지식베이스 기본값", 미설정 경고, 모델 드롭다운(차원 표기), 저장 → "저장되었습니다", 경고 사라짐.
- 스튜디오 create 도구함: 블록·드롭 영역·기존 KB 드롭다운·안내 문구 → 업로드 후 ProgressCard 3단계(1/1) → 연결 배지 + 개인 배지 + [바꾸기] → 도구함에 "내부 문서 검색" 행 + "[CHECK] 퀵셋업봇 지식 · 하이브리드 · top_k 5" 요약 배지.
- RAG 설정 모달: KB 드롭다운·범위 안내·"고급 설정" 버튼만 보이고 검색 모드 라디오 등은 접힘.
- 위저드: 도구 확정 → "참고할 문서가 있나요?" 카드(서버 호출 없음) → 업로드 → "연결됨: 문서 Q&A 지식" → [계속] → 프롬프트 → [스튜디오로 보내기] → 폼 프리필.

### L3 E2E
SC-1, SC-2 전체 여정 완주(위 표). 테스트 자원(에이전트 2, KB 2, 컬렉션 2)은 삭제했고 기본 설정은 NULL로 되돌렸다.

---

## 5. Gap 목록

| ID | 심각도 | 확신도 | 위치 | 내용 | 수정 제안 |
|---|---|:-:|---|---|---|
| G1 | Important | 90% | `idt_front/src/components/agent-builder/KnowledgeDocsBlock.tsx` 재시도 | 전부 실패 후 [다시 시도]가 `/quick`을 다시 불러 새 KB·컬렉션(` (2)`)을 만든다. 빈 KB가 재시도마다 누적된다 | 재시도는 `result.kb_id`로 기존 KB 업로드 API를 파일별 호출하거나, 안내 문구로 빈 KB 잔존을 알린다 |
| G2 | Important | 85% | 같은 파일 하단 안내 | "저장하지 않아도 지식베이스는 남습니다"가 연결 전에만 보이고 위저드에서는 안 보인다. Plan 완화책은 "생성 직후" 표시 | 조건을 `result || attachedKbId`로, 위저드에도 표시 |
| G3 | Minor | 90% | `knowledge_base_router.py` /quick 409, `collection_assigner.py` | §6.1 `COLLECTION_NAME_CONFLICT` 코드 미구현(409 문자열), kb_id 재생성 1회 없음 | Design §6.1·§4.2를 실제 동작으로 갱신 (uuid 충돌은 실질 불가) |
| G4 | Minor | 95% | Design §4.1 | 경로 `/api/v1/agent-pipeline` 표기 오류(실제 `/api/v1/agents/pipeline`) | Design 수정 |
| G5 | Minor | 90% | Design §10.4 | `isKbLoading` settled 가드 불필요(블록이 자체 조회, `attachKbToForm` 순수) | Design 수정 |
| G6 | Minor | 85% | Design §5.3 | 훅 이름 `useAdminKbDefaults`/`useUpdateAdminKbDefaults`, 진행 단계 파생은 `utils/kbQuickSetup.ts` | Design 수정 |
| G7 | Minor | 80% | `application/knowledge_base/use_case.py` create | 함수 약 77줄(40줄 규칙) | save+rollback을 private 메서드로 분리 |
| G8 | Minor | 80% | `quick_create_use_case.py` | 이름 중복 판정이 예외 문자열 매칭 | 전용 예외 도입 |

### 요검토(확신도 80% 미만)

| ID | 내용 | 비고 |
|---|---|---|
| R1 | KB 연결 뒤 [건너뛰기]를 눌러도 kb_id·RAG가 PROMPT 요청에 실린다 | 건너뛰기 시 kbId 해제 또는 버튼 비활성 |
| R2 | [이전]에서 RAG 해제해도 kbId가 남아 핸드오프에서 RAG가 다시 붙는다 | RAG 토글 해제 시 kbId 해제 |
| R3 | /quick 파일 루프가 세션 1개 공유 — DB 오류성 실패 뒤 후속 파일·commit 영향 | `begin_nested` 검토 |
| R4 | 파일 오류 원문(영문)이 그대로 노출 | 사용자 메시지 매핑 |
| R5 | 관리자 드롭다운이 비활성 모델도 노출(저장은 409로 차단) | `is_active` 필터 |
| R6 | `CollapsibleSection defaultOpen`은 마운트 시점만 평가 | 모달이 매번 마운트되어 실질 영향 낮음 |
| R7 | `/quick` 성공 시 collections 캐시 미무효화, 실패 시 KB 캐시 미무효화 | `onSettled`로 둘 다 무효화 |

---

## 6. Decision Record 검증

| 결정 | 준수 | 근거 |
|---|:-:|---|
| KB마다 컬렉션 1개 `kb-{id8}` | ✅ | `KbQuickSetupPolicy.collection_name_for`, 실런 `kb-0b838911`·`kb-2ccb6a8a` |
| 관리자 설정은 기본 임베딩 모델만(단일 행 V084) | ✅ | `kb_default_setting` 1행, 관리자 화면 항목 1개 |
| KB 이름·범위는 에이전트를 따라감 | ✅ | `{에이전트명} 지식`, PERSONAL(생성 폼 visibility 없음 → private) |
| 설계안 C: 서버 `/quick` + 기존 UseCase 조합, 파이프라인 단계 수 불변 | ✅ | `QuickCreateKnowledgeBaseUseCase`, steps 5개 유지, optional `kb_id` |
| 흡수 지점 1곳 | ✅ | AST 계약 테스트(`_upload_one`만 `except Exception`) |

---

## 7. 결론

Overall 95.5%(≥90%). Critical 0, Important 2(G1·G2, 프론트 블록 1파일 범위), Minor 6(대부분 Design 문서 갱신). 요검토 7건은 후속 소형 사이클로 이월 가능.

---

## 8. Act-1 (2026-11-05, 사용자 결정: Important 2건만 수정)

| ID | 처리 | 근거 |
|---|---|---|
| G1 | ✅ 수정 | `useRetryKbUpload` + `kbQuickSetupService.retryUploadToKb`: 전부 실패 후 [다시 시도]는 기존 `result.kb_id`에 파일만 재업로드. 테스트: `/quick` 1회·업로드 API 1회 단언 |
| G2 | ✅ 수정 | 고아 안내 조건 `mode==='studio' || result || attachedKbId` — 생성 직후·위저드·연결 상태 모두 표시. 테스트 2건 |
| G3 | 📝 문서 | Design §6.1: 컬렉션 충돌은 문자열 409, 전용 code·재생성 없음으로 확정 |
| G4 | 📝 문서 | Design §4.1/§4.2 경로 `/api/v1/agents/pipeline` |
| G5 | 📝 문서 | Design §10.4 settled 가드 요구 삭제 |
| G6 | 📝 문서 | Design §2.3/§5.3 훅 이름·진행 단계 파생 위치 |
| G7·G8 | ⏭ 이월 | 코드 품질(함수 길이·예외 문자열 매칭) — 후속 소형 사이클 |
| R1~R7 | ⏭ 이월 | 요검토 항목. R7은 `useQuickKnowledgeBase` `onSettled` 무효화로 일부 반영 |

재실행: 블록·LeftConfigPanel·DocumentsStep·위저드 통합 60 테스트 통과, eslint·tsc 신규 파일 0 errors.
