# Archive Index — 2026-11

| Feature | Phase | Match Rate | Archived At | Path |
|---------|-------|:----------:|-------------|------|
| tool-access-control | completed | 95.0% (Check 90.2% → Act-1) | 2026-11-04 | [tool-access-control/](tool-access-control/) |

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
