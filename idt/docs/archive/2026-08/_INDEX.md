# Archive Index — 2026-08

> 이 디렉토리는 PDCA 사이클이 완료된 피처 문서를 보관합니다.

| 피처 | 완료일 | Match Rate | 테스트 | 경로 |
|------|--------|-----------|--------|------|
| builtin-tools | 2026-08-01 | 100%(Check 1차 93% → Partial 5건 즉시 보강, 이터레이션 0) | 백엔드 신규 17케이스(sync 시드/왕복 보존 · repo 보존 계약 SQL 검사 · SetBuiltin · 라우터 403/404 · 주입 10케이스) 51 pass · 프론트 신규 3파일+보강(ToolPickerModal 빌트인 4 · AgentBuilderPage 3(초안 적용 불변식 포함) · AdminToolsPage 3) · 회귀 백 506 + 프론트 130 무회귀 · **백 신규 2+수정 12 / 프론트 신규 2+수정 12 / 마이그레이션 1(V054)** — **에이전트 생성 시 자동 주입되는 빌트인 도구 + 관리자 등록/해제**. 런타임 SoT `tool_catalog.is_builtin`(관리자 `PATCH /tool-catalog/builtin`, `/admin/tools` 화면) + `ToolMeta.builtin_default`(프레시 DB sync INSERT 시드) 이원화, upsert UPDATE 분기의 is_builtin 미변경 성질을 SQL SET 절 검사로 **계약 테스트화**(재부팅 보존). 주입은 `CreateAgentUseCase` Step 2.7(정책 검증 후 → MAX_TOOLS 상한 제외, 정규화 dedup, 비활성 MCP 제외+경고 격하, flow_hint 미포함). ★ **opt-out 채널 구조 분리 패턴** — "채팅(Fix)은 못 빼고 사용자는 뺄 수 있다"를 백엔드 `exclude_builtin_tool_ids` 필드 + 프론트 `excludedBuiltinTools` 전용 상태(ToolPickerModal에서만 토글, 초안 적용 경로는 접근 불가 + 초안의 빌트인 혼입 필터)로 구조적으로 보장(프롬프트 방어 아님). 초기 빌트인 wiki_read+wiki_list, 스냅샷 방식(기존 에이전트 소급 없음). 이월: **V054 배포 필수**, 수동 E2E 3종(관리자 토글/채팅 생성 포함/폼 해제), 커밋·PR, 후속 후보(기존 에이전트 백필·config 필요 도구 빌트인화) | [→](./builtin-tools/) |
