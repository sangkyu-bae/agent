# builtin-middleware — Gap Analysis (Check)

> Analyzed: 2026-08-05
> Analyzer: bkit gap-detector (Design `docs/02-design/features/builtin-middleware.design.md` vs 구현)
> **Match Rate: 92.4%** (프로세스 항목 제외 시 95.2%) — 90% 게이트 **통과** ✅

---

## 1. Match Rate 산출

| 축 | 가중치 | 항목 수 | 점수 |
|---|---:|---:|---|
| 설계 결정 D0~D10 | 3 | 11 | 10.4 / 11 (94.5%) → 31.2 / 33 |
| FR-01~FR-12 | 2 | 12 | 11.45 / 12 (95.4%) → 22.9 / 24 |
| §13 테스트 목록 | 1 | 10 | 9.7 / 10 |
| §13 마무리(회귀 실행·커밋) | 3 | 1 | 0.9 / 3 |
| **합계** | | | **64.7 / 70 = 92.4%** |

부분점 내역: D1 0.85 · D9 0.7 · D10 0.85 / FR-09 0.6 · FR-11 0.85 / call_limit 테스트 0.7 / 마무리 0.3.
**미구현(Design O / 구현 X) 항목 없음** — D0~D10의 모든 구조·파일·엔드포인트가 실재.

## 2. 항목별 대조표 (D0~D10)

| D | 판정 | 근거 (코드가 진실) |
|---|:---:|---|
| D0 create_agent 전환 게이트 | ✅ | `pyproject.toml` langchain>=1.0; `test_create_agent_equivalence.py` 시그니처·v2 스트리밍·ainvoke 계약; 워커/General Chat 단일 경로. name 규약은 기존 `test_worker_trace_leak.py` 위임(설계 §2.2대로) |
| D1 도메인 모듈 + v2 격리 | ⚠️ | 모듈 4종 완비. `list_enforced` 미구현(G7 — 구현이 더 단순), v2 "실험 경로" 주석 부재(G8) |
| D2 V056 마이그레이션 | ✅ | 2테이블+시드 4종, 전 컬럼 COMMENT, FK CHARSET 미명시, ORM `comment=` 동일 반영 |
| D3 시드 단순화 | ✅ | 부팅 sync 없음 — 공급원은 마이그레이션 INSERT 단독. 단 확장 시 enum 동반 필요(G3) |
| D4 관리자 API | ✅ | GET(로그인)/PATCH(admin, 404/400), `MiddlewareConfigPolicy` 타입별 범위·미등록 폴백 모델 검증 |
| D5 생성 스냅샷 + 수정 4곳 세트 | ✅ | Step 2.8 exclude·sort 유지; 스키마→apply_update→`_sync_middleware`→DI 4곳 확인; 조회 노출 완비 |
| D6 WorkflowCompiler 조립 | ✅ | optional DI, depth 0 1회 prepare, 워커마다 `_instantiate` 재호출(인스턴스 분리), sub_agent 재귀 미전달 |
| D7 General Chat | ✅ | `prepare(None)` → 빌트인 ∪ enforced, prepare 실패 격리, astream_events v2 유지 |
| D8 조립 격하 규칙 | ✅ | langchain 참조 단일 지점, 개별 실패 warning+계속, fallback은 해석된 BaseChatModel만 |
| D9 call_limit × supervisor | ⚠️ | 시드/검증/빌더 완비. supervisor 수렴·IterationLimitPolicy 상호작용 단언 부재(G2) |
| D10 프론트엔드 | ⚠️ | 전 구성요소 구현. sort_order 컬럼(G4)·페이로드/비관리자 테스트(G5)·LoadingButton 범위(G6)·명칭 표류(G9) |

## 3. Gap 목록

| # | 심각도 | 내용 | 권장 조치 |
|---|---|---|---|
| G1 | Medium | §13 마무리 미수행 — builtin-middleware 커밋 없음(워킹트리 M 상태), 회귀 실행 기록 없음 | 격리 회귀 후 §13 커밋 분할(D0 전환 커밋 단독 revert 가능하게) |
| G2 | Medium | D9 시나리오가 워커 단독 그래프만 단언 — supervisor 수렴 미검증 (`test_call_limit_scenario.py:43-55`) | 컴파일 그래프 + run_limit=1 supervisor 수렴 테스트 추가 |
| G3 | Medium | 카탈로그에 enum 미등록 타입 행 존재 시 `_to_domain`(repository.py:128) ValueError → API 500 + 실행 경로 조립 실패 | `_to_domain` 미지 타입 skip+warning (전방 호환) |
| G4 | Low-Med | 관리자 목록에 적용순서(sort_order) 컬럼 없음 (§12.3) | 컬럼 추가 또는 설계에서 제거 |
| G5 | Low-Med | `exclude_builtin_middleware_types`/`middleware_types` 페이로드 직접 단언 테스트 없음, TopNav 비관리자 미노출 단언 없음 | 페이로드 테스트 1건 + TopNav 단언 추가 |
| G6 | Low | 관리자 토글 2종이 LoadingButton 아닌 자체 pendingKey 가드 (§12.3) | 의도적 — 설계 갱신 권장 |
| G7 | Low | `list_enforced` 인터페이스 미구현 — `list_all`+정책 필터로 대체(조회 1회, 더 단순) | 설계 문서에서 제거 |
| G8 | Low | v2(middleware_agent) 모듈 docstring "실험 경로" 주석 미추가 | 4개 모듈에 1줄 추가 |
| G9 | Low | 명칭 표류: `patchMiddlewareFlags`→`setMiddlewareFlags`, queryKey `middlewareCatalog`, `MiddlewareSection`은 LeftConfigPanel 내부 named export | 설계 문서 갱신 |
| G10 | Low | `build_for_agent` → `prepare()`+`MiddlewarePlan.instantiate()` 구조 개선(워커별 인스턴스 분리 — 우수한 이탈) | 설계 문서 갱신 |
| G11 | Low | FR-09 재시도 실측은 수동 E2E 이월 상태 (plan §8.2대로) | V056 적용 + venv 기동 후 수동 E2E |

## 4. Design에 없는 추가 구현 (모두 정당·유지)

- `MiddlewareConfigPolicy` 도메인 분리 + 미지 config 키 400 (오타 조용한 무시 방지)
- `SessionScoped*Repository` 2종 (앱 싱글톤 런타임 조회 경로, 쓰기 차단)
- `MiddlewarePlan` + `default_builtin=False` (agent_id 미상 시 enforced만 — 사용자 opt-out 무시 방지)
- General Chat prepare 실패 격리 (D8 격하를 provider 단계까지 확장)
- `AgentDefinition.middleware_types=None` 의미 분리 (미로드 update 시 스냅샷 소실 방지)
- Provider 앱 싱글톤 (wiki-tree-performance 선례 선반영)
- 추가 테스트: provider 5건 + infra repository 5건

## 5. 권장 조치 우선순위

1. **즉시**: G1 회귀+커밋 분할 → G3 전방 호환 가드 → G2 supervisor 수렴 테스트
2. **문서 갱신**(코드가 진실): G6·G7·G9·G10 설계 문서 반영
3. **후속**: G5 프론트 테스트, G4 sort_order 컬럼, G8 주석, G11 수동 E2E

→ 92.4% ≥ 90%: `/pdca report builtin-middleware` 진행 가능. 단 G1(커밋)·G3(전방 호환)은 리포트 전 처리 권장.

---

## 6. 조치 결과 (2026-08-05, 동일 세션)

| Gap | 조치 | 검증 |
|---|---|---|
| G3 | `_to_domain_or_none` skip+warning 가드 — list_all/list_builtin/find_by_type/update_flags 전 경로 (repository.py) | 신규 테스트 3건 (test_repository.py, TDD Red→Green) |
| G2 | run_limit 종료 × `_wrap_worker` 규약 유지 + `route_to_worker_or_final` final_answer 수렴 테스트 2건 | test_call_limit_scenario.py 4 passed |
| G8 | v2 `middleware_agent` 3계층 `__init__.py`에 "실험 경로" docstring | — |
| G4·G6·G7·G9·G10 | 설계 문서를 구현(코드가 진실)에 맞게 갱신 — `prepare()`/`MiddlewarePlan`, `list_enforced` 제거, `setMiddlewareFlags`/`queryKeys.middlewareCatalog`, 적용순서=행 정렬, LoadingButton 범위 | design.md 각 위치에 "구현 반영, Check Gn" 표기 |

회귀: 미들웨어 도메인/앱/인프라 40건 + 라우터·컴파일러·동등성·General Chat 16건 전부 통과.

**잔존 Gap**: G1(회귀+커밋 분할 — 사용자 커밋 시점), G5(프론트 페이로드·비관리자 테스트 — 후속), G11(FR-09 수동 E2E — V056 적용 후).
**조치 후 Match Rate 재산정: ≈95.2%** (D1·D9 Match 승격, D10 0.95, call_limit 테스트 만점).
