# 위키 트리 인덱스

> `/wiki update` 실행 시 wiki-curator가 이 파일을 함께 갱신한다.
> 표기: ✅ approved · 📝 draft · 🗑 deprecated
> **설명은 트리거 조건형**: "무엇에 관한 문서"가 아니라 "언제 읽어야 하는 문서"로 쓴다.

## backend/
- ✅ [백엔드 아키텍처 조감도](backend/architecture-overview.md) — **idt/ 작업 첫 진입 시, 또는 새 기능이 어느 레이어·어느 그래프에 붙는지 정할 때** — DI는 main.py 단일 집중, supervisor 그래프는 요청마다 DB 정의로 동적 컴파일, 문서는 저장소 3곳 분산, 성장 루프 4 플래그 기본 off
- api/
  - 📝 [백엔드 라우터 지도](backend/api/router-map.md) — **새 API 라우터 추가하거나 기존 라우터의 책임·경유 서비스를 찾을 때**. tree 선언 순서·source 토글·도구 ID 이중 네임스페이스 같은 특이 계약 포함
- db/
  - 📝 [MySQL FK 참조 테이블 collation 규칙](backend/db/mysql-fk-collation.md) — **새 테이블 마이그레이션 SQL 작성 전 필수** — SQLAlchemy 생성 테이블 FK 참조 시 CHARSET/COLLATE 명시하면 errno 3780
  - 📝 [미니 ERD — 에이전트 도메인](backend/db/erd-agent.md) — **agent_definition/tool/subscription/memory 테이블을 조회·수정·확장할 때**. tool_id 저장 표기·memory scope 가드 주의점 포함
  - 📝 [미니 ERD — 대화·평가 도메인](backend/db/erd-conversation-eval.md) — **대화·피드백 테이블 작업 전** — FK 0개 소프트 참조 구조, 세션 테이블 없음, 평가 취소=행 삭제라는 비직관 계약
  - 📝 [미니 ERD — 지식베이스 도메인](backend/db/erd-kb.md) — **KB 테이블·kb_id를 참조하는 코드 작업 전** — kb_id 소프트 참조 3곳·NULL 의미론·청킹 opt-in 상호배타(앱 레이어)
  - 📝 [미니 ERD — 위키 도메인](backend/db/erd-wiki.md) — **위키 테이블·환류 기능 작업 전** — agent_id 예약석(HUMAN/CONVERSATION)·출처 불변식·len(refs)=지지 수
- patterns/
  - 📝 [사용자 평가 저장 — 취소는 행 삭제 토글](backend/patterns/feedback-toggle-row-delete.md) — **"있다/없다" 신호를 저장하는 기능 설계 시** — 상태 컬럼 대신 행 존재+upsert/delete, 0건 집계는 None

## frontend/
- chat/
  - 📝 [채팅 메시지 단위 액션 부착](frontend/chat/streaming-message-action-id.md) — **채팅 메시지에 버튼·액션을 붙일 때** — 히스토리/스트리밍 id 양방향 해석 함수 + "id 없으면 미노출" 폴백 필수
- screens/
  - 📝 [화면↔API 지도 — 채팅·계정·설정](frontend/screens/chat-screens.md) — **ChatPage/Settings/Usage/Login 수정 전** 해당 화면의 API 절단면 확인용
  - 📝 [화면↔API 지도 — 에이전트](frontend/screens/agent-screens.md) — **스토어/빌더/워크스페이스 화면 수정 전** — 도구 ID 변환·update 화이트리스트 함정 포함
  - 📝 [화면↔API 지도 — 지식베이스·컬렉션](frontend/screens/kb-screens.md) — **KB·컬렉션 화면 수정 전** — KB vs 컬렉션 계층 구분 + 전체 교체·source 토글 계약
  - 📝 [화면↔API 지도 — 관리자](frontend/screens/admin-screens.md) — **/admin/* 화면 수정 전** — PUT 전체 교체·메타 기준 적재량 주의
  - 📝 [화면↔API 지도 — 위키·지식 노출](frontend/screens/wiki-screens.md) — **위키/지식 화면 수정 전** — tree 선언 순서·can_manage 인가 계약

## conventions/
- 📝 ["데이터는 있고 노출 경로만 없다" 패턴](conventions/data-exists-exposure-missing.md) — **새 계산·집계 기능을 만들기 전** — 기존 산출물(버려지는 반환값·잘린 응답 스키마)에 이미 있는지 먼저 확인
- 📝 [계약 확장은 additive + 응답 타입 분리](conventions/additive-contract-extension.md) — **공용 스키마·API·WS 계약을 변경할 때** — 기존 소비자 무변경(신규 응답 타입·optional 필드)으로 회귀 0, 독립 opt-in 선호
- 📝 [PDCA gap 명시적 이월](conventions/explicit-gap-carryover.md) — **gap 분석 후 미달 항목 처리 방침 정할 때** — 억지로 메우지 않고 후속 소형 사이클로 회수

## ops/
- ✅ [마이그레이션 배포 의존성](ops/migration-deploy-deps.md) — **배포 전 필수** — V046~V052 × 기능 매핑, "마이그레이션 0" 기능의 선행 V 의존 포함
- ✅ [E2E 이월 체크리스트](ops/e2e-carryover-checklist.md) — **Qdrant/ES/실서버 기동 시** 일괄 소화할 수동 검증 목록 (KB·위키환류·메모리·에이전트 4개 절)
