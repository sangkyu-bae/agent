# Archive Index — 2026-11

| Feature | Phase | Match Rate | Archived At | Path |
|---------|-------|:----------:|-------------|------|
| tool-access-control | completed | 95.0% (Check 90.2% → Act-1) | 2026-11-04 | [tool-access-control/](tool-access-control/) |
| sidebar-agent-list | completed | 99.8% (Check 99.0% → Act-1) | 2026-11-04 | [sidebar-agent-list/](sidebar-agent-list/) |
| agent-kb-quick-setup | completed | 98.9% (Check 95.5% → Act-1) | 2026-11-05 | [agent-kb-quick-setup/](agent-kb-quick-setup/) |
| agent-edit-entry | completed | 100% (Check 90% → Act-1) | 2026-11-05 | [agent-edit-entry/](agent-edit-entry/) |

> 백엔드·프론트 전용 사이클은 `idt/docs/archive/2026-11/`, `idt_front/docs/archive/2026-11/` 에 있다.

---

## 이월 항목 (Carry-over)

> 아카이브 시점에 미완이었던 항목. 후속 사이클 진입 전 확인할 것.

| Feature | 이월 항목 | 성격 | 진입 조건 |
|---------|----------|------|-----------|
| **tool-access-control** | **배포 전 모든 MCP 서버 카탈로그 동기화** — 동기화 안 된 서버의 도구는 V083 시드에서 빠져 배포 직후 일반 사용자가 잃음 (G-08) | 배포 절차 | **배포 전 필수** |
| **tool-access-control** | **V082 → V083 순서 적용** — V082 는 `tool_catalog`·`users`·`departments` FK 참조. `/wiki update` 시 `ops/migration-deploy-deps.md` 에 추가 | 배포 의존 | **배포 전 필수** |
| **tool-access-control** | 배포 직후에는 시드로 전부 열려 있음 → 관리자가 기본 세트에서 민감 도구를 빼고 부서·사용자로 좁힘 | 운영 | 배포 직후 |
| tool-access-control | 승인 재개 답변 제외 안내(G-07), 빌더 테스트 패널(TestChatView) 안내, 채팅 안내 히스토리 저장 | 화면·스키마 소형 | 후속 소형 사이클 |
| tool-access-control | 경로별 전용 테스트(웹훅·잡·스케줄·RAGAS), 시드 동치 테스트(R13), FK CASCADE 통합 테스트, 커버리지 측정 | 테스트 보강 | 다음 접근 통제 사이클에 묶어 처리 |
| tool-access-control | `USE_WEB_SEARCH` 권한 코드 정의만 있고 확인 코드 없음 | 기존 결함 | 별도 정리 |
| tool-access-control | CORS 허용 출처가 5173 하드코딩 — worktree 병행 브라우저 확인 시 스크래치 런처 필요 | 개발 환경 | 소형 사이클 후보 |
| sidebar-agent-list | 사용자 정의 폴더(폴더 생성) — 백엔드 필요 | 기능 확장 | 요청 시 |
| sidebar-agent-list | 에이전트 관리·필터·숨김 (참고 사이트의 관리 아이콘) | 기능 확장 | 요청 시 |
| sidebar-agent-list | 하위 컴포넌트 props interface 위치(G5) | 스타일 | 해당 파일 수정 시 |
| **agent-kb-quick-setup** | **V084 적용 + 관리자가 `/admin/kb-defaults`에서 기본 임베딩 모델 1회 설정** — 미설정이면 사용자 경로가 422 안내에서 멈춤 | 배포 절차 | **배포 직후 필수** |
| agent-kb-quick-setup | 위저드 [건너뛰기] 시 kb_id 전송 여부(R1), [이전]에서 RAG 해제 후 kbId 잔존(R2), 파일 오류 원문 → 사용자 메시지 매핑(R4) | 제품 판단·화면 소형 | 후속 소형 사이클 |
| agent-kb-quick-setup | `/quick` 파일 루프 세션 공유 시 DB 오류 전파(R3), 관리자 드롭다운 비활성 모델 필터(R5) | 요검토 | 해당 파일 수정 시 |
| agent-kb-quick-setup | `KnowledgeBaseUseCase.create` 40줄 규칙 초과(G7), 이름 중복 판정의 예외 문자열 매칭(G8) | 코드 정리 | 해당 파일 수정 시 |
| agent-kb-quick-setup | 컬렉션 수 상한·정리 정책(KB 1개 = 컬렉션 1개), 에이전트 공개 범위 변경·삭제 시 KB 범위 동기화·정리, 생성 폼 공개 범위 필드 | 설계 필요 | 별도 Plan |
| agent-edit-entry | `cn`이 클래스를 병합하지 않아 컴포넌트 기본 display 클래스가 className의 `hidden`을 이김 — 다른 사용처 점검 | 기존 결함 | 소형 사이클 후보 |
| agent-edit-entry | 내 에이전트 목록 응답에 `can_edit` 추가 — 지금 채팅 헤더는 `source_type`으로 추정 | API 보강 | 편집 권한 정책 변경 시 |
| agent-edit-entry | 구독 에이전트에서 수정 아이콘 미노출 화면 확인 (단위 테스트로만 확인) | 확인 | 구독 데이터가 있을 때 |
| agent-edit-entry | 저장 후 브라우저 뒤로가기 시 편집 화면 재진입 (`navigate` push) — `replace` 검토 | UX 소형 | 요청 시 |
| agent-edit-entry | 사이드바 항목 hover 수정 아이콘 | 기능 확장 | 요청 시 |
