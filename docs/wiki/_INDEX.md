# 위키 트리 인덱스

> `/wiki update` 실행 시 wiki-curator가 이 파일을 함께 갱신한다.
> 표기: ✅ approved · 📝 draft · 🗑 deprecated
> **설명은 트리거 조건형**: "무엇에 관한 문서"가 아니라 "언제 읽어야 하는 문서"로 쓴다.

## backend/
- 📝 [백엔드 아키텍처 조감도](backend/architecture-overview.md) — **idt/ 작업 첫 진입 시, 또는 새 기능이 어느 레이어·어느 그래프에 붙는지 정할 때** — DI는 main.py 단일 집중, supervisor 그래프는 요청마다 DB 정의로 동적 컴파일, 문서는 저장소 3곳 분산, 성장 루프 4 플래그 기본 off, 실행 경로 5종(백그라운드 잡 포함)
- api/
  - 📝 [백엔드 라우터 지도](backend/api/router-map.md) — **새 API 라우터 추가하거나 기존 라우터의 책임·경유 서비스를 찾을 때**. tree 선언 순서·source 토글·도구 ID 이중 네임스페이스·skills/list=POST·wiki 인증 선행+싱글턴 같은 특이 계약 포함
- db/
  - 📝 [MySQL FK 참조 테이블 collation 규칙](backend/db/mysql-fk-collation.md) — **새 테이블 마이그레이션 SQL 작성 전 필수** — SQLAlchemy 생성 테이블 FK 참조 시 CHARSET/COLLATE 명시하면 errno 3780 + COMMENT 문자열의 최상위 콤마가 DDL 주석 검사 파서를 깬다
  - 📝 [미니 ERD — 에이전트 도메인](backend/db/erd-agent.md) — **agent_definition/tool/subscription/memory 테이블을 조회·수정·확장할 때**. tool_id 저장 표기·memory scope 가드 주의점 포함
  - 📝 [미니 ERD — 대화·평가 도메인](backend/db/erd-conversation-eval.md) — **대화·피드백 테이블 작업 전** — FK 0개 소프트 참조 구조, 세션 테이블 없음, 평가 취소=행 삭제라는 비직관 계약
  - 📝 [미니 ERD — 지식베이스 도메인](backend/db/erd-kb.md) — **KB 테이블·kb_id를 참조하는 코드 작업 전** — kb_id 소프트 참조 3곳·NULL 의미론·청킹 opt-in 상호배타(앱 레이어)
  - 📝 [미니 ERD — 위키 도메인](backend/db/erd-wiki.md) — **위키 테이블·환류·폴더 요약 기능 작업 전** — agent_id 예약석(HUMAN/CONVERSATION)·출처 불변식·len(refs)=지지 수·폴더 요약은 힌트일 뿐(진실은 wiki_list)
- patterns/
  - 📝 [사용자 평가 저장 — 취소는 행 삭제 토글](backend/patterns/feedback-toggle-row-delete.md) — **"있다/없다" 신호를 저장하는 기능 설계 시** — 상태 컬럼 대신 행 존재+upsert/delete, 0건 집계는 None
  - ✅ [무거운 외부 클라이언트는 앱 수명 싱글턴](backend/patterns/app-lifetime-client-singleton.md) — **임베딩·Qdrant·ES 클라이언트를 쓰는 DI/라우터 추가 시, 또는 특정 API가 초 단위로 느릴 때** — per-request 생성이면 요청당 ~6.5s+누수, 인증 파라미터는 use_case보다 앞에, 무토큰 4xx도 느리면 DI 병목
  - ✅ [Supervisor 그래프 계약 3종](backend/patterns/supervisor-graph-contracts.md) — **워커 래퍼·수퍼바이저 프롬프트·강제 라우팅 트리거를 수정하기 전 필수** — 워커 산출물=AIMessage(name) 1건(위반 시 고아 tool 400), 능력 목록 프레이밍은 과차단 유발, 재주입분은 강제 라우팅 제외
  - ✅ [빌트인 도구 — opt-out 채널 분리](backend/patterns/builtin-tools-optout-channel.md) — **표준 도구를 전 에이전트에 보급하거나 "LLM은 못 빼고 사용자만 뺄 수 있는" 요구를 만났을 때** — is_builtin(V054) SoT·upsert 보존 계약·exclude 필드 부재로 채팅 우회 구조 차단
  - ✅ [Stateless HITL 질문 왕복](backend/patterns/stateless-hitl-clarification.md) — **무상태 API에 "부족하면 되묻기" 다회 왕복을 넣을 때, 또는 compose/Fix 탭 질문 흐름 수정 전** — 세션 테이블 대신 질문 에코백+클라 신고값 서버 재clamp 2요소, Protocol이 application DTO를 물면 application 레이어 배치, v3 auto_agent_builder 루프와 혼동 금지
  - 📝 [탈착형 모듈 이음매](backend/patterns/detachable-module-seam.md) — **실험적/부가 기능을 기존 실행 경로에 끼울 때, 또는 "안 되면 뺄 수 있게" 요구를 받았을 때** — 팩토리가 None 반환=노드 미존재, 실패 시 입력 그대로 반환(부분 성공 금지), 킬스위치 기본 off, 경계는 AST import 테스트로 강제. ⚠️ 근거 전량 미커밋 + 두 사이클 모두 미활성 — 확립된 관행 아닌 제안
  - 📝 [MCP 런타임 도구 객체의 실제 형태](backend/patterns/mcp-runtime-tool-shape.md) — **MCP 도구의 이름·설명·서버명을 코드에서 읽거나 프롬프트/UI에 넣기 전 필수** — server_config.name은 `mcp_{uuid}`, tool.name은 UUID 40자 접두 합성명, 사람이 읽는 서버명은 런타임에 없음
  - 📝 [DB 큐 + 인프로세스 워커](backend/patterns/db-queue-inprocess-worker.md) — **비동기 작업·주기 실행을 추가할 때(브로커/cron 도입 검토 전)** — MySQL 큐 + lifespan 워커, FOR UPDATE SKIP LOCKED 선점, 기동 시 reconcile로 재시작 복구, 스케줄 틱 single-flight, V060 의존
  - ✅ [logger.warning의 exception kwarg](backend/patterns/structured-logger-warning-exception.md) — **예외 삼키고 폴백하는 경로에 warning 로그를 쓸 때** — `exception=e`로 스택 트레이스 기록 가능(`error=str(e)` 금지), 인터페이스에 없어도 구현(_log)이 받는다

## frontend/
- chat/
  - 📝 [채팅 메시지 단위 액션 부착](frontend/chat/streaming-message-action-id.md) — **채팅 메시지에 버튼·액션을 붙일 때** — 히스토리/스트리밍 id 양방향 해석 함수 + "id 없으면 미노출" 폴백 필수
- patterns/
  - 📝 [라우트 간 1회성 상태 핸드오프 G1~G5](frontend/patterns/cross-route-draft-handoff.md) — **다른 라우트로 폼 초안·의도를 넘길 때, 또는 "적용했는데 값이 비어 있다"를 만났을 때** — persist 금지·원자적 consume·getState()만(구독 금지)·의존 쿼리 settled 후 소비(로딩 중 변환은 조용히 실패)
  - ✅ [뮤테이션 버튼은 LoadingButton](frontend/patterns/loading-button-pending-guard.md) — **생성/수정/삭제 버튼을 만들거나 이중 제출 테스트를 쓸 때 필수** — isPending 필수 prop으로 타입 강제, disabled 버튼에 userEvent.click은 가드 검증이 아님(항상 통과), mutateAsync는 try/catch 세트
  - ✅ [2차 네비는 레이아웃 소유 탭](frontend/patterns/layout-owned-nav-tabs.md) — **네비게이션 계층 추가·관리자 메뉴 항목 추가 시** — 탭은 레이아웃이 경로 역산으로 소유(페이지 무수정), adminNav.ts 단일 소스, 개수 하드코딩 단언 금지(관계 기반), ENTRY_PATH=/admin/dashboard
- screens/
  - 📝 [화면↔API 지도 — 채팅·계정·설정](frontend/screens/chat-screens.md) — **ChatPage/Settings/Usage/Login 수정 전** 해당 화면의 API 절단면 확인용
  - 📝 [화면↔API 지도 — 에이전트](frontend/screens/agent-screens.md) — **스토어/빌더/워크스페이스/유틸리티 화면 수정 전** — 도구 ID 변환·update 화이트리스트·빌트인 해제 전용 상태·compose HITL 에코백·skills/list=POST 함정 포함
  - 📝 [화면↔API 지도 — 지식베이스·컬렉션](frontend/screens/kb-screens.md) — **KB·컬렉션 화면 수정 전** — KB vs 컬렉션 계층 구분 + 전체 교체·source 토글 계약
  - 📝 [화면↔API 지도 — 관리자](frontend/screens/admin-screens.md) — **/admin/* 화면 수정하거나 관리 메뉴를 추가하기 전** — 4그룹+2차탭 구조(URL 불변)·ENTRY_PATH=/admin/dashboard·PUT 전체 교체·메타 기준 적재량 주의
  - 📝 [화면↔API 지도 — 위키·지식 노출](frontend/screens/wiki-screens.md) — **위키/지식 화면 수정 전** — tree 선언 순서·can_manage 인가 계약

## conventions/
- 📝 ["데이터는 있고 노출 경로만 없다" 패턴](conventions/data-exists-exposure-missing.md) — **새 계산·집계 기능을 만들기 전** — 기존 산출물(버려지는 반환값·잘린 응답 스키마)에 이미 있는지 먼저 확인
- 📝 [계약 확장은 additive + 응답 타입 분리](conventions/additive-contract-extension.md) — **공용 스키마·API·WS 계약을 변경하거나 기존 UseCase에 협력자를 추가할 때** — 기존 소비자 무변경(신규 응답 타입·optional 필드·optional 마지막 인자+폴백)으로 회귀 0, 신규 상태값은 구형 소비자 안전 강하 동반, 독립 opt-in 선호
- 📝 [거짓 초록 품질 게이트 4종](conventions/false-green-quality-gates.md) — **Plan에서 DoD·품질 기준을 적을 때, Do를 닫기 전, MSW/픽스처를 작성하기 전** — 전역 기준은 단일 사이클에서 달성 불가(baseline 스냅샷 필수), `tsc --noEmit` ≠ `tsc -b`, 핸들러가 훅 select와 어긋나면 조용히 통과
- 📝 [PDCA gap 명시적 이월](conventions/explicit-gap-carryover.md) — **gap 분석 후 미달 항목 처리 방침 정할 때** — 억지로 메우지 않고 후속 소형 사이클로 회수

## ops/
- ✅ [마이그레이션 배포 의존성](ops/migration-deploy-deps.md) — **배포 전 필수** — V046~V060 × 기능 매핑(V054 미적용 시 tool_catalog 조회 SQL 에러, V060 미적용 시 워커 기동 즉시 실패), "마이그레이션 0" 기능의 선행 V 의존 포함
- ✅ [E2E 이월 체크리스트](ops/e2e-carryover-checklist.md) — **Qdrant/ES/실서버 기동 시** 일괄 소화할 수동 검증 목록 (KB·위키환류·메모리·에이전트 4개 절)
