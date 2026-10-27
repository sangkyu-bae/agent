# Archive Index — 2026-10

| Feature | Phase | Match Rate | Archived At | Path |
|---------|-------|:----------:|-------------|------|
| prompt-guard | completed | 99.8% | 2026-10-13 | [prompt-guard/](prompt-guard/) |
| judgment-backend | completed | 99.3% | 2026-10-16 | [judgment-backend/](judgment-backend/) |
| agent-opener | completed | 100% (Check 96.1% → Act-1) | 2026-10-27 | [agent-opener/](agent-opener/) |

> `idt/docs/archive/2026-10/` 에는 백엔드 전용 사이클(hwp-parser)이 별도로 있다.

---

## 이월 항목 (Carry-over)

> 아카이브 시점에 미완이었던 항목. 후속 사이클 진입 전 확인할 것.

| Feature | 이월 항목 | 성격 | 진입 조건 |
|---------|----------|------|-----------|
| **prompt-guard** | **`idt/.env.example` 에 `PROMPT_GUARD_*` 5키 미반영** — bkit 쓰기 정책이 `.env*` 를 차단해 세션에서 추가 불가. 키·주석 블록은 Report §4.1 / Design §4.3 | 수기 1분 | **배포 전 필수** |
| **prompt-guard** | **에이전트 실행 경로 turn_index 중복(기존 결함)** — `_save_user_message` 는 별도 세션 즉시 commit, `_save_assistant_message` 는 요청 세션 스냅샷으로 `find_by_session` 해 user 행을 못 봐 같은 turn 저장. 2026-09-30 이후 11세션 기존 재현(Design §8.6 발견 2). 가드는 Act G-1 로 tie 를 흡수했지만 근본 수정은 범위 밖 | 기존 결함, 소형 사이클 | 독립 사이클 — assistant 저장도 session_factory 경로로 |
| prompt-guard | mode 오타 → 가드 전체 비활성 + warning 1회 (G-10) | 설계(탈착형 이음매) 유지, config 주석에 주의 명기 | 운영 중 사고 시 `block` 폴백 검토 |
| prompt-guard | 커버리지 수치 미측정(SC-9) | 96건이 공개 메서드 전부 호출 | `pytest --cov` 1회 |
| prompt-guard | 판정 지연 1.3~2.7초 vs timeout 3초 — 여유 적음 | 운영 관측 필요 | `judge_error=timeout` 비율·REVIEW 비율 로그 1~2주 후 조정 |
| prompt-guard | 간접 인젹션(RAG·도구 결과), 출력 검사, 에이전트별 토글, 관리자 화면, 멀티턴 분할 공격, 인코딩 우회 | Plan Out of Scope | 후속 Plan — `InputSource` 확장으로 같은 Port 재사용 |
| prompt-guard | **코드 미커밋** — src·tests·docs 전부 워킹트리. `main.py`·`config.py` 에 무관한 excel_preview 변경이 섞여 있어 분리 커밋 필요 | 작업 관리 | 커밋 시 prompt_guard 파일만 선택 |
| **judgment-backend** | **실호출 미검증** — Jev 키·AnyJev 서버 미확보로 `-m llm` 스모크 2종은 작성만(skip). 양성 대조군 벤치(웹검색 필요 N + 불필요 M)로 임계값·백엔드별 캘리브레이션을 본 뒤 `JUDGMENT_BACKEND` on | 환경 확보 후 0.5일 | **운영 활성화 전 필수** — 기본값 off 라 배포는 안전 |
| judgment-backend | 테스트 보강 5건 — G4 폴백 자체 예외 시뮬레이션, G7 `typesafe_base_url=None` 시 SDK 기본 URL 명시, G8 실패 케이스 Choice parametrize, G10 스모크 `/health` 선조건, G11 `aclose` 실패 warning | 각 0.2~0.5h | 다음 judgment 소비 지점 사이클에 묶어 처리 |
| judgment-backend | 두 번째 소비 지점(RAG 관련성 `relevance_adapter` / prompt_guard judge)·Score 프리미티브·관리자 UI | Plan Out of Scope | 벤치 결과 양호 시 후속 Plan |
| **agent-opener** | **코드·테스트·문서 전부 미커밋** — 백엔드 8 수정·11 신규, 프론트 13 수정·7 신규. `main.py` diff 는 오프너 전용임을 확인 | 작업 관리 | 커밋 시 이 사이클 파일만 선택 |
| **agent-opener** | **V080 마이그레이션 배포 선행 필수** — 미적용 시 `/agents/my`·상세·생성·수정·포크가 `agent_opener` 테이블 부재로 500. `/wiki update` 시 `ops/migration-deploy-deps.md` 에 추가 | 배포 의존 | **배포 전 필수** |
| agent-opener | 실 DI 왕복·리포지토리 실 DB 테스트 없음(G2·G5) — 로컬 전용 스모크 13항목(`smoke_openers.py`, 스크래치)로 2회 검증. 앱 기동 지연 시 JWT 만료 → 토큰은 기동 후 발급 | 로컬 전용 | E2E 이월 체크리스트에 "오프너 스모크" 추가 |
| agent-opener | 라우터 `ValueError` 문자열 매퍼(`_attach_skill_http_error`, PATCH 분기)가 메시지에 "최대/이미/찾을 수 없" 이 있으면 409/404 — 정책 메시지에 사용자 입력 금지로 우회(Check G1). 근본은 예외 타입 기반 매핑 | 기존 구조, 소형 사이클 | 다음 agent_builder 라우터 수정 때 |
| agent-opener | Pydantic 422(배열 `detail`)는 `authClient` 가 "알 수 없는 오류" 로 표시(G6) — 프론트 가드로 사실상 미발생 | 기존 인터셉터 | 인터셉터 개선 시 |
| agent-opener | `/agents/my` 구독 건별 `find_by_id` N+1(기존), 스트리밍 중 supervisor JSON 원문 노출(기존, E2E 중 관찰) | 기존 결함 | 별도 사이클 |
| agent-opener | 빌더 테스트 탭 빈 상태·스토어 상세 모달 노출, 정렬 UI, AutoForkService 복사 | Plan Out of Scope | 필요 시 후속 Plan |
