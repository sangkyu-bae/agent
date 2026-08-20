# 위키 트리 인덱스

> `/wiki update` 실행 시 wiki-curator가 이 파일을 함께 갱신한다.
> 표기: ✅ approved · 📝 draft · 🗑 deprecated
> **설명은 트리거 조건형**: "무엇에 관한 문서"가 아니라 "언제 읽어야 하는 문서"로 쓴다.

## backend/
- ✅ [백엔드 아키텍처 조감도](backend/architecture-overview.md) — **idt/ 작업 첫 진입 시, 또는 새 기능이 어느 레이어·어느 그래프에 붙는지 정할 때** — DI는 main.py 단일 집중, supervisor 그래프는 요청마다 DB 정의로 동적 컴파일, 문서는 저장소 3곳 분산, 성장 루프 4 플래그 기본 off, 실행 경로 5종(백그라운드 잡 포함)
- api/
  - ✅ [백엔드 라우터 지도](backend/api/router-map.md) — **새 API 라우터 추가하거나 기존 라우터의 책임·경유 서비스를 찾을 때**. 라우트 등록 테스트는 `app.routes` 순회 금지(`_IncludedRouter` 로 깨짐)·pipeline 라우터는 DI 섹션 조건부 include+와일드카드보다 선등록 필수·intent 라우터는 독립 모듈(hot path 미배선)·tree 선언 순서·source 토글·도구 ID 이중 네임스페이스·skills/list=POST·wiki 인증 선행+싱글턴
- db/
  - ✅ [MySQL FK 참조 테이블 collation 규칙](backend/db/mysql-fk-collation.md) — **새 테이블 마이그레이션 SQL 작성 전 필수, 또는 DDL COMMENT 검사가 이상한 컬럼명으로 위반을 낼 때** — CHARSET/COLLATE 명시 시 errno 3780 + COMMENT 안의 콤마가 검사기 파서(`_split_top_level`, 따옴표 미추적)를 깨 허위 위반 발생(파서 고치지 말고 콤마를 뺄 것)
  - 📝 [미니 ERD — 에이전트 도메인](backend/db/erd-agent.md) — **agent_definition/tool/subscription/memory 테이블을 조회·수정·확장할 때**. tool_id 저장 표기·memory scope 가드 주의점 포함
  - 📝 [미니 ERD — 대화·평가 도메인](backend/db/erd-conversation-eval.md) — **대화·피드백 테이블 작업 전** — FK 0개 소프트 참조 구조, 세션 테이블 없음, 평가 취소=행 삭제라는 비직관 계약
  - 📝 [미니 ERD — 지식베이스 도메인](backend/db/erd-kb.md) — **KB 테이블·kb_id를 참조하는 코드 작업 전** — kb_id 소프트 참조 3곳·NULL 의미론·청킹 opt-in 상호배타(앱 레이어)
  - 📝 [미니 ERD — 위키 도메인](backend/db/erd-wiki.md) — **위키 테이블·환류·폴더 요약 기능 작업 전** — agent_id 예약석(HUMAN/CONVERSATION)·출처 불변식·len(refs)=지지 수·폴더 요약은 힌트일 뿐(진실은 wiki_list)
- patterns/
  - 📝 [사용자 평가 저장 — 취소는 행 삭제 토글](backend/patterns/feedback-toggle-row-delete.md) — **"있다/없다" 신호를 저장하는 기능 설계 시** — 상태 컬럼 대신 행 존재+upsert/delete, 0건 집계는 None
  - ✅ [무거운 외부 클라이언트는 앱 수명 싱글턴](backend/patterns/app-lifetime-client-singleton.md) — **임베딩·Qdrant·ES 클라이언트를 쓰는 DI/라우터 추가 시, 또는 특정 API가 초 단위로 느릴 때** — per-request 생성이면 요청당 ~6.5s+누수, 인증 파라미터는 use_case보다 앞에, 무토큰 4xx도 느리면 DI 병목
  - ✅ [Supervisor 그래프 계약 3종](backend/patterns/supervisor-graph-contracts.md) — **워커 래퍼·수퍼바이저 프롬프트·강제 라우팅 트리거를 수정하기 전 필수** — 워커 산출물=AIMessage(name) 1건(위반 시 고아 tool 400), 능력 목록 프레이밍은 과차단 유발, 재주입분은 강제 라우팅 제외
  - ✅ [빌트인 도구 — opt-out 채널 분리](backend/patterns/builtin-tools-optout-channel.md) — **표준 도구를 전 에이전트에 보급하거나 "LLM은 못 빼고 사용자만 뺄 수 있는" 요구를 만났을 때** — is_builtin(V054) SoT·upsert 보존 계약·exclude 필드 부재로 채팅 우회 구조 차단
  - ✅ [Stateless HITL 질문 왕복](backend/patterns/stateless-hitl-clarification.md) — **무상태 API에 "부족하면 되묻기" 다회 왕복을 넣을 때, 또는 compose/Fix 탭·에이전트 파이프라인 질문 흐름 수정 전** — 세션 테이블 대신 질문 에코백+클라 신고값 서버 재clamp 2요소, 두 번째 적용(pipeline: 왕복 후 4단계 실행까지, 세션 0), Protocol이 application DTO를 물면 application 레이어 배치, v3 auto_agent_builder 루프와 혼동 금지
  - 📝 [탈착형 모듈 이음매](backend/patterns/detachable-module-seam.md) — **실험적/부가 기능을 기존 실행 경로에 끼울 때, 또는 "안 되면 뺄 수 있게" 요구를 받았을 때** — 팩토리가 None 반환=노드 미존재, 실패 시 입력 그대로 반환(부분 성공 금지), 킬스위치 기본 off, 경계는 AST import 테스트로 강제. ⚠️ 근거 전량 미커밋 + 두 사이클 모두 미활성 — 확립된 관행 아닌 제안(단, v4: 두 번째 소비자 등장 시 선언 목록 확장 프로세스는 실작동 확인 — duck typing 규칙은 "떼어도 동작해야 하는" 소비자에게만). **§3(LLM 스키마 겸용+3층 방어)은 폐기 → [LLM 출력 신뢰 경계](backend/patterns/llm-output-trust-boundary.md)로 대체**
  - 📝 [MCP 런타임 도구 객체의 실제 형태](backend/patterns/mcp-runtime-tool-shape.md) — **MCP 도구의 이름·설명·서버명을 코드에서 읽거나 프롬프트/UI에 넣기 전 필수** — server_config.name은 `mcp_{uuid}`, tool.name은 UUID 40자 접두 합성명, 사람이 읽는 서버명은 런타임에 없음
  - 📝 [DB 큐 + 인프로세스 워커](backend/patterns/db-queue-inprocess-worker.md) — **비동기 작업·주기 실행을 추가할 때(브로커/cron 도입 검토 전)** — MySQL 큐 + lifespan 워커, FOR UPDATE SKIP LOCKED 선점, 기동 시 reconcile로 재시작 복구, 스케줄 틱 single-flight, V060 의존
  - ✅ [LLM 출력 신뢰 경계](backend/patterns/llm-output-trust-boundary.md) — **`with_structured_output` 스키마를 정의할 때, 또는 LLM 결과를 DB에 저장하는 기능을 만들 때 필수** — 계산 필드(degraded/dropped/elapsed)와 표기 이름을 스키마에 두면 LLM이 오염시킨다(방어 코드는 필드 수만큼 늘다 실패). Draft/Result 분리 + 필드 집합 동등 비교 테스트, 프롬프트 금지 문구는 2차 방어선일 뿐
  - ✅ [OpenAI strict structured outputs — 자유 키 dict 금지](backend/patterns/structured-output-strict-schema.md) — **`with_structured_output` 스키마에 dict 필드를 넣기 전, 그리고 fake로만 테스트한 LLM 모듈을 완료 처리하기 전 필수** — `dict[str,X]` 하나가 strict 모드 전체를 무효화(매 호출 400)해 3개월 은폐된 실사례, 재귀 탐색 테스트로 정적 차단, function_calling 우회는 되묻기를 죽여 기각, 미배선 모듈은 실 LLM 1회가 DoD
  - ✅ [되묻기는 선언된 슬롯 축의 함수](backend/patterns/declared-slot-elicitation.md) — **LLM에게 "부족하면 되묻기"를 시키는 기능을 설계할 때, 또는 슬롯 채우기 프롬프트가 과충전/미발동으로 이상할 때** — 질문=required 축 미충족의 함수(SlotSpec 데이터 선언), complete/missing은 Policy 계산(LLM 필드 금지), 프롬프트는 "비우는 게 기본"으로 반전해도 과충전 부분 잔존(사용자 확인 UI 필요), 축 의미는 소비자 모듈에(AGENT_BUILD_SLOTS — 미배선 죽은 코드 경고)
  - ✅ [소스 계약은 AST 테스트로](backend/patterns/ast-source-contract-tests.md) — **"…하지 않는다"류 설계 계약을 테스트로 못박을 때, Protocol 포트를 쓰는 UseCase를 짤 때, 라우터 등록 테스트를 쓸 때** — 문자열 grep은 독스트링에 오탐, Protocol은 미선언 메서드 호출을 아무도 안 잡음(구현 교체 시 AttributeError), 라우트는 정적 검증 불가→TestClient 실요청
  - ✅ [degraded vs 예외 전파 경계](backend/patterns/degradation-vs-failure-boundary.md) — **graceful degradation·폴백을 설계할 때, "이 실패를 200으로 줄까 5xx로 줄까" 망설일 때** — 기준은 "쓸 수 있는 결과가 존재하는가"(LLM 실패=degraded, 저장 실패=전파), 흡수는 어댑터 한 곳(포트 계약+AST로 고정), 배제한 입력은 스냅샷에서도 제외, 다단계 적용례(파이프라인: 단계별 degraded + bind만 흡수 — agent_id가 이미 존재)
  - ✅ [SSE heartbeat — wait_for 전제 조건](backend/patterns/sse-heartbeat-async-generator.md) — **SSE/스트림에 heartbeat·타임아웃을 붙이기 전 필수, 또는 heartbeat 추가 후 스트림이 중간에 죽을 때** — `wait_for(__anext__)`는 큐 기반 스트림 전용(직접 LLM await 제너레이터에 쓰면 취소가 내부로 주입돼 파이프라인 중단), 직접 await 형은 task 유지+`asyncio.wait(timeout)`, heartbeat 테스트는 이벤트 무손실 단언 세트
  - ✅ [동기+SSE 이중 노출 — 공유 제너레이터+고정 steps](backend/patterns/sync-sse-dual-exposure.md) — **같은 작업을 동기·스트리밍 두 엔드포인트로 낼 때, 또는 화면 단계 진행 바용 다단계 상태 계약을 설계할 때** — UseCase는 async generator 하나(이벤트…+최종 결과), 두 라우터는 소비 방식만 상이(의미 동일이 구조로 강제+직렬화 동일성 테스트), steps는 항상 고정 5개(미도달 skipped, finalize_steps), wire 문자열=StrEnum value(변경=프론트 계약 파괴), 스트림 개시 후 실패는 SSE 레이어가 이벤트로 합성
  - ✅ [logger.warning의 exception kwarg](backend/patterns/structured-logger-warning-exception.md) — **예외 삼키고 폴백하는 경로에 warning 로그를 쓸 때** — `exception=e`로 스택 트레이스 기록 가능(`error=str(e)` 금지), 인터페이스에 없어도 구현(_log)이 받는다

## frontend/
- chat/
  - 📝 [채팅 메시지 단위 액션 부착](frontend/chat/streaming-message-action-id.md) — **채팅 메시지에 버튼·액션을 붙일 때** — 히스토리/스트리밍 id 양방향 해석 함수 + "id 없으면 미노출" 폴백 필수
- patterns/
  - ✅ [공통 카드 컴포넌트 — ProgressCard·question-card 재사용 우선](frontend/patterns/common-card-components.md) — **다단계 진행 표시나 질문/선택지/직접입력 UI를 새로 만들기 전 필수** — 이미 `common/`에 있다(신규 구현=중복). ProgressCard는 `ProgressStep[]` stateless 단일 소스, question-card는 순차 제출 위저드+스테일 카드 2중 가드(F10, 사용처 가드 누락 금지), 구 ClarifyQuestionCard는 삭제됨, 어댑터 추출은 3번째 사용처부터
  - ✅ [TSX 파일 작성 함정 2종](frontend/patterns/tsx-authoring-pitfalls.md) — **새 `.tsx` 컴포넌트 파일을 만들 때, 또는 파일이 갑자기 바이너리로 인식되거나 react-refresh 린트에 걸릴 때** — 컴포넌트 파일의 런타임 export는 types//constants/로 분리(위반 시 Do 단계 재작업 실증), 유니코드 제어 문자는 리터럴 금지·이스케이프 표기(위반 시 git/grep이 파일을 바이너리 취급)
  - 📝 [라우트 간 1회성 상태 핸드오프 G1~G5](frontend/patterns/cross-route-draft-handoff.md) — **다른 라우트로 폼 초안·의도를 넘길 때, 또는 "적용했는데 값이 비어 있다"를 만났을 때** — persist 금지·원자적 consume·getState()만(구독 금지)·의존 쿼리 settled 후 소비(로딩 중 변환은 조용히 실패)
  - ✅ [뮤테이션 버튼은 LoadingButton](frontend/patterns/loading-button-pending-guard.md) — **생성/수정/삭제 버튼을 만들거나 이중 제출 테스트를 쓸 때 필수** — isPending 필수 prop으로 타입 강제, disabled 버튼에 userEvent.click은 가드 검증이 아님(항상 통과), mutateAsync는 try/catch 세트
  - ✅ [2차 네비는 레이아웃 소유 탭](frontend/patterns/layout-owned-nav-tabs.md) — **네비게이션 계층 추가·관리자 메뉴 항목 추가 시** — 탭은 레이아웃이 경로 역산으로 소유(페이지 무수정), adminNav.ts 단일 소스, 개수 하드코딩 단언 금지(관계 기반), ENTRY_PATH=/admin/dashboard
- screens/
  - 📝 [화면↔API 지도 — 채팅·계정·설정](frontend/screens/chat-screens.md) — **ChatPage/Settings/Usage/Login 수정 전** 해당 화면의 API 절단면 확인용
  - 📝 [화면↔API 지도 — 에이전트](frontend/screens/agent-screens.md) — **스토어/빌더/워크스페이스/유틸리티 화면 수정 전** — 도구 ID 변환·update 화이트리스트·빌트인 해제 전용 상태·compose HITL 에코백(질문 카드는 common/question-card로 교체, 구 ClarifyQuestionCard 삭제)·skills/list=POST 함정 포함
  - 📝 [화면↔API 지도 — 지식베이스·컬렉션](frontend/screens/kb-screens.md) — **KB·컬렉션 화면 수정 전** — KB vs 컬렉션 계층 구분 + 전체 교체·source 토글 계약
  - 📝 [화면↔API 지도 — 관리자](frontend/screens/admin-screens.md) — **/admin/* 화면 수정하거나 관리 메뉴를 추가하기 전** — 4그룹+2차탭 구조(URL 불변)·ENTRY_PATH=/admin/dashboard·PUT 전체 교체·메타 기준 적재량 주의
  - 📝 [화면↔API 지도 — 위키·지식 노출](frontend/screens/wiki-screens.md) — **위키/지식 화면 수정 전** — tree 선언 순서·can_manage 인가 계약

## conventions/
- 📝 ["데이터는 있고 노출 경로만 없다" 패턴](conventions/data-exists-exposure-missing.md) — **새 계산·집계 기능을 만들기 전** — 기존 산출물(버려지는 반환값·잘린 응답 스키마)에 이미 있는지 먼저 확인
- 📝 [계약 확장은 additive + 응답 타입 분리](conventions/additive-contract-extension.md) — **공용 스키마·API·WS 계약을 변경하거나 기존 UseCase에 협력자를 추가할 때** — 기존 소비자 무변경(신규 응답 타입·optional 필드·optional 마지막 인자+폴백)으로 회귀 0, 신규 상태값은 구형 소비자 안전 강하 동반, 독립 opt-in 선호
- ✅ [거짓 초록 품질 게이트 4종](conventions/false-green-quality-gates.md) — **Plan에서 DoD·품질 기준을 적을 때, Do를 닫기 전, "회귀 0건"을 증명해야 할 때, MSW/픽스처를 작성하기 전** — 회귀는 pass/fail 개수가 아니라 정렬된 `FAILED` 목록 diff로 증명(baseline 58건 상시 존재), 전역 기준은 단일 사이클에서 달성 불가, `tsc --noEmit` ≠ `tsc -b`, 핸들러가 훅 select와 어긋나면 조용히 통과
- 📝 [PDCA gap 명시적 이월](conventions/explicit-gap-carryover.md) — **gap 분석 후 미달 항목 처리 방침 정할 때** — 억지로 메우지 않고 후속 소형 사이클로 회수
- ✅ [운영 config는 소비 지점 기준 단일 출처](conventions/config-single-source-at-consumption.md) — **새 config 키를 추가하기 전, 특히 기존 모듈의 상한·타임아웃을 "오버라이드 가능하게" 복제하고 싶을 때 필수** — 소비 지점이 안 읽는 config는 dead config(값을 바꿔도 동작 불변, G-02/G-03 실사례), 기존 config의 VO 변환 메서드 주입으로 재사용하고 새 키에는 소비 지점 파일:라인을 docstring에 명기
- ✅ [중간 산출물도 검증 대상](conventions/intermediate-artifact-verification.md) — **Design 작성·검수 시(FR 역추적 표), 그리고 gap-detector 등 에이전트가 "기본 동작·기본값" 류 판정을 냈을 때** — Plan FR이 Design에서 유실되면 구현·테스트가 성실하게 함께 누락(G-04), 판정은 확신도 85%여도 실측 반증 가능(G-06: 403 주장→실측 401) — 수정 전 재현 테스트부터

## ops/
- ✅ [마이그레이션 배포 의존성](ops/migration-deploy-deps.md) — **배포 전 필수** — V046~V062 × 기능 매핑(V054 미적용 시 tool_catalog 조회 SQL 에러, V060 미적용 시 워커 기동 즉시 실패, V061/V062는 prompt-composer·pipeline 선행), "마이그레이션 0" 기능의 선행 V 의존 포함
- ✅ [E2E 이월 체크리스트](ops/e2e-carryover-checklist.md) — **Qdrant/ES/실서버 기동 시** 일괄 소화할 수동 검증 목록 (KB·위키환류·메모리·에이전트 4개 절)
