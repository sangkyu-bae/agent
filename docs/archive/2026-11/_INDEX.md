# Archive Index — 2026-11

| Feature | Phase | Match Rate | Archived At | Path |
|---------|-------|:----------:|-------------|------|
| tool-access-control | completed | 95.0% (Check 90.2% → Act-1) | 2026-11-04 | [tool-access-control/](tool-access-control/) |
| sidebar-agent-list | completed | 99.8% (Check 99.0% → Act-1) | 2026-11-04 | [sidebar-agent-list/](sidebar-agent-list/) |
| agent-kb-quick-setup | completed | 98.9% (Check 95.5% → Act-1) | 2026-11-05 | [agent-kb-quick-setup/](agent-kb-quick-setup/) |
| agent-edit-entry | completed | 100% (Check 90% → Act-1) | 2026-11-05 | [agent-edit-entry/](agent-edit-entry/) |
| agent-run-tool-trace | completed | 97.5% (Check, Minor 4건 수정) | 2026-11-05 | [agent-run-tool-trace/](agent-run-tool-trace/) |
| pii-masking-integration | completed | 95.8% (Check 89.4% → Act-1) | 2026-11-06 | [pii-masking-integration/](pii-masking-integration/) |
| wizard-template-request | completed | 95% (Check 92% → Act-1) | 2026-11-06 | [wizard-template-request/](wizard-template-request/) |
| extractor-template-preview | completed | 98.6% (Check, Minor 5건 즉시 반영) | 2026-11-09 | [extractor-template-preview/](extractor-template-preview/) |
| document-file-preview | completed | 96.5% (Check 95.3% → Act-1) | 2026-11-19 | [document-file-preview/](document-file-preview/) |
| claude-agent-e2e-fixes | completed | 97% (Check 96% → Act-1) | 2026-11-19 | [claude-agent-e2e-fixes/](claude-agent-e2e-fixes/) |
| source-passage-viewer | completed | 97.2% (Check 94.8% → Act-1) | 2026-11-20 | [source-passage-viewer/](source-passage-viewer/) |
| answer-citation-verification | completed | 93.6% (Check 90.6% → Act-1) | 2026-11-23 | [answer-citation-verification/](answer-citation-verification/) |
| document-revision | completed | 96.1% (Check 90.3% → Act-1) | 2026-11-23 | [document-revision/](document-revision/) |
| firewall-admin-console | completed | 97.8% (Check, Minor 4건 수정) | 2026-11-24 | [firewall-admin-console/](firewall-admin-console/) |
| firewall-agent | completed | 96% (Check 92% → Act-1) | 2026-11-25 | [firewall-agent/](firewall-agent/) |
| stock-analysis-agents | completed | 94.6% (Check 94.6% → Act-2, SC 8/8) | 2026-11-26 | [stock-analysis-agents/](stock-analysis-agents/) |

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
| agent-run-tool-trace | 375·768 폭 화면 확인 (데스크톱 폭에서만 확인) | 확인 | 다음 채팅 화면 작업 시 |
| agent-run-tool-trace | 하단 "추론 진행" 패널의 UUID 런타임 도구 이름 — `ToolCatalogLookup` 재사용 | 기존 동작 | 소형 사이클 후보 |
| agent-run-tool-trace | 스트리밍 중 supervisor 라우팅 JSON 토큰 노출, 종료 판단 2줄 연속 기록 | 기존 동작 | 소형 사이클 후보 |
| agent-run-tool-trace | 프론트 커버리지 미측정 (`@vitest/coverage-v8` 미설치), 헤더 N은 상한 안 도구만 셈(G-02) | 측정·소형 | 요청 시 |
| **pii-masking-integration** | **배포는 shadow(기본)로 — `PII masking summary`·`MCP PII inspected` 로그로 오탐 확인 후 `PII_MASKING_MODE=on`. on 전환 시 `LANGSMITH_TRACING` 끄기(상태 원본 기록)** | 운영 절차 | **on 전환 전 필수** |
| pii-masking-integration | 실제 PII를 반환하는 MCP로 on 실런 1회 (고객 문의 MCP는 서버에서 사전 마스킹) | 검증 | on 전환 전 |
| pii-masking-integration | 외부 도구 인자 마스킹(Tavily·Perplexity·외부 MCP), 임베딩 API 쿼리, 이미지, 이름·주소(NER) | 잔여 위험 | shadow 집계 후 별도 Plan |
| pii-masking-integration | action 초안 생성기가 사용자가 준 본문 대신 다른 문장을 만듦 (shadow에서도 재현, 마스킹 무관) | 기존 결함 | 소형 사이클 후보 |
| pii-masking-integration | Minor G-5·G-7·G-8, `test_no_pii_in_logs`·호출 단위 성능 벤치 미작성 | 테스트·정리 | 해당 파일 수정 시 |
| pii-masking-integration | 부분 테스트 묶음 실행 시 `test_pii_masking_di`가 `main` import로 LangSmith 키를 다시 올려 일반 채팅 테스트가 순서 오염으로 깨짐 (전체 스위트에선 미재현) | 테스트 격리 | 소형 사이클 후보 |
| **wizard-template-request** | **프론트 전체 vitest 회귀 FAILED diff 미실행** — 시스템 메모리 부족으로 두 번 중단. master에서 `vitest --no-file-parallelism` 1회 | 회귀 증명 | **다음 프론트 작업 전** |
| wizard-template-request | 수동 E2E L3-01~03 (위저드→양식 첨부→스튜디오 저장→상세 `template_id`, 건너뛰기→`?edit` 안내, 추출기 미추천 화면 동일) — MCP 변환 도구 등록 로컬 필요 | 확인 | MCP 도구 등록 후 |
| wizard-template-request | `SourceFileArchiver.promote`가 `source_file_id` 소유자를 검증하지 않음 (스튜디오 경로도 동일) | 기존 결함 | 소형 사이클 후보 |
| wizard-template-request | Minor G4~G8: 스튜디오 패널 공유 에러 유틸, 카드 에러 detail 보조 표시·[다시 올리기], aria-live 상시 마운트, `document_template_attached` 프론트 소비 | 화면 소형 | 해당 파일 수정 시 |
| wizard-template-request | 위저드 직접 생성 버튼(스튜디오 진입 0회) — 무저장 계약 변경, 문서생성기 예시 문서→섹션 추출 | 스코프 후보 | 별도 Plan |
| **extractor-template-preview** | **확정 토큰화가 `<style>` 텍스트를 매칭** — 로컬 "여신심의서" 양식의 `{{deliberation_date_month}}`가 `@page { size: 8.5in 11in }`에 들어감. 채움 시 페이지 크기 손상 가능, 기존 저장 양식 점검 필요 | 기존 결함 | **다음 추출기 사이클 1순위** |
| extractor-template-preview | 반복 예시값 원문 잔존 — `tokenizeHtml`은 첫 출현만 토큰화, 포크 사용자가 skeleton 본문에서 원본 값을 볼 수 있음 (Design §7) | 보안 소형 | 소형 사이클 후보 |
| extractor-template-preview | 실데이터 미확인 3건: 타 사용자 403, 포크 사용자 화면(예시값 숨김·"포크로 받은 양식"), 교체 후 업로드·확정·저장 E2E (단위 테스트로만 확인) | 확인 | 포크·두 번째 계정 준비 시 |
| extractor-template-preview | DOCX 미리보기가 좁은 화면에서 축소되지 않음 (pt 페이지 폭 없음, 기존 업로드 패널과 동일) | 화면 소형 | 해당 파일 수정 시 |
| extractor-template-preview | 스토어 상세·채팅 화면 양식 미리보기 (Plan 범위 밖) | 스코프 후보 | 요청 시 |
| **document-file-preview** | **PDF 미리보기 실브라우저 확인** (Chrome·Edge, 가능하면 iOS Safari) — 헤드리스 Chromium엔 내장 PDF 뷰어가 없어 단위 테스트로만 확인 | 확인 | **운영 노출 전** |
| document-file-preview | 외부 이미지가 링크된 docx에서 외부 리소스 미로딩 확인, 실백엔드 에이전트 실행 → 채팅 버튼 → 모달 흐름, 1MB 이상 docx 렌더 시간 | 확인 | 다음 채팅 화면 작업 시 |
| document-file-preview | docx-preview가 단일 줄 간격을 100%로 그려 표 칸 글자가 Word보다 빽빽함 — 렌더 결과에 CSS 보정 | 화면 소형 | 요청 시 |
| document-file-preview | 배포·CSP: CSP 헤더를 넣을 때 `frame-src blob:` 허용 필요 (지금은 CSP 없음) | 배포 의존 | CSP 도입 시 |
| document-file-preview | 실행 내역·워크스페이스 등 채팅 외 화면 미리보기 진입점, 형식이 늘면 엑셀까지 공통 셸(Design Option B)로 통합 | 스코프 후보 | 요청 시 |
| **claude-agent-e2e-fixes** | **분석 워커가 첨부 원문(600행, 입력 약 5.8만 토큰)을 프롬프트에 그대로 받아, 항상 추론하는 모델(Opus 5.5)은 출력 16000을 추론에 다 써 빈 답이 된다** — 원문 대신 요약·통계 입력 또는 effort 조절 | 결함 후속 | 다음 엑셀 분석 작업 시 |
| claude-agent-e2e-fixes | 엑셀 생성이 끝난 뒤 실패했던 분석 워커를 다시 호출하는 비연속 재호출(분석 → 엑셀 → 분석) — 연속 상한으로는 막히지 않음 | 라우팅 | 수퍼바이저 작업 시 |
| claude-agent-e2e-fixes | 수퍼바이저 결정 실패 종료 경로에서 반복 상태(repeat_worker_*) 미리셋 — 런이 끝나 실영향 없음 | 경미 | 수퍼바이저 리팩터 시 |
| claude-agent-e2e-fixes | 운영 배포 시 V092 적용 + Opus 5.5 등 항상 추론하는 모델의 "최대 출력 토큰" 설정, 구형 Anthropic 기본 출력이 16000으로 바뀐 영향 확인 | 배포 의존 | 운영 배포 시 |
| **source-passage-viewer** | **임베딩(Qdrant) 검색 경로의 칩 → 원문 패널 라이브 확인** — 로컬 OpenAI 크레딧 소진으로 Claude + BM25(ES) 경로만 확인 | 확인 | **운영 반영 전** |
| source-passage-viewer | 운영 반영: `SOURCE_VIEWER_ENABLED=true`, `DOCUMENT_ORIGINAL_STORAGE_DIR` 볼륨 경로 지정·백업 대상 포함 (기본 off) | 배포 의존 | 운영 배포 시 |
| source-passage-viewer | 토큰 단위 child 청킹이 한글을 바이트 중간에서 잘라 청크에 U+FFFD 생성 — 뷰어 매칭은 정규화로 흡수(Design §12 M19), 청킹 자체는 미수정 | 결함 후속 | 청킹 작업 시 |
| source-passage-viewer | 원본 뷰어 매칭 범위를 구절 쪽 ±1 로 좁히기(M24), 컬렉션 전체 삭제 시 원본 고아 정리(M26), 모바일 폭 화면 확인 | 경미 | 요청 시 |
| **answer-citation-verification** | **PDF 원본 모드에서 근거 문장 음영 확인** — worktree의 node_modules junction 에서 pdf.js `?url` 워커가 비어 텍스트로 폴백, 텍스트·docx 모드만 확인 | 확인 | **운영 반영 전** |
| answer-citation-verification | 운영 반영: Flyway V093·V094 순서 확인, `ANSWER_CITATION_ENABLED` 기본 off 로 시작, 판정 모델은 LLM 모델 관리 페이지에서 선택(비면 env) | 배포 의존 | 운영 배포 시 |
| answer-citation-verification | SC-2 골든셋 10문항 인용 정확도, SC-5 음영 매칭률, SC-6 스위치 on/off 호출 수·지연 실측 | 실측 | 다음 인용 작업 시 |
| answer-citation-verification | 라우팅 검색 인용에 쪽 번호 없음(G-4), 관리자 카드 폴백 경고(G-5), GET effective 계산(G-6), supervisor 밖 경로 라벨(G-8), 설정 조회 실패 캐시(G-9), judge_model 미기록(G-3) | 경미 | 요청 시 |
| answer-citation-verification | 기존 동작(무관): supervisor 라우팅 JSON 이 채팅에 잠깐 스트리밍됨, KB 삭제 API 가 Qdrant 컬렉션을 남김 | 기존 결함 | 해당 영역 작업 시 |
| **document-revision** | **운영 반영: Flyway V095~V097 적용** — V095 는 `document_metadata` 컬럼 추가라 업로드·목록 쿼리가 새 컬럼을 참조. ES 기존 인덱스의 `revision_status` 매핑은 첫 전환 때 `put_mapping` 으로 멱등 추가 | 배포 의존 | **배포 전 필수** |
| document-revision | SC-5 근거 칩·원문 뷰어 버전 라벨 화면 확인 (백엔드 라벨 생성·칩 중복 제거 단위 테스트만 통과) | 확인 | 다음 인용 작업 시 |
| document-revision | 본문 유사도 개선 — 새 문서 앞부분 토막과 기존 청크 전체를 비교해 거의 같은 문서도 0.65~0.70. 임계값 `revision_content_min` 0.5 는 합성 픽스처 실측값 | 개선 | 판정 로그 실측 후 |
| document-revision | 계보 전체 삭제(FR-19 일부), `revision_mode=auto` 실동작(현재 422) | 범위 밖 | 요청 시 |
| document-revision | 기존 동작(무관): KB 삭제는 상태값만 `deleted` 로 바꿔 `document_metadata` 행·벡터가 남음 | 기존 결함 | 해당 영역 작업 시 |
| firewall-admin-console | 켤 때: `FIREWALL_ADMIN_*` 설정 5개 + Grafana Viewer 서비스 계정 토큰. 기본 off 라 설정 없이 배포해도 기존 동작 불변. 절차 `docs/firewall-admin-setup.md` | 운영 설정 | 기능을 켤 때 |
| firewall-admin-console | 실장비 연결 — TLS, 호출자별 토큰, 대역 차단, 차단 영속화, 감사 장기 보관, 조직 승인 (`docs/firewall-admin-setup.md` §7) | 범위 밖 | 별도 사이클 |
| firewall-admin-console | ~~fireware Phase 4 — 방화벽 에이전트 프롬프트(`detection-policy.md`), mcp-grafana 등록, 스케줄 실행~~ → firewall-agent 로 완료(2026-11-25, mcp-grafana 대신 고정 조회 도구) | 후속 기능 | 완료 |
| firewall-admin-console | `RejectReasonDialog` 를 `components/` 로 이동 — 방화벽 승인 탭이 작업함 페이지 파일을 import (G7) | 구조 소형 | 해당 파일 수정 시 |
| firewall-admin-console | 기존 동작(무관): 승인 API 가 에이전트 재개까지 동기 대기해 30초를 넘기면 작업함 화면이 오류를 표시(실제로는 처리됨). 방화벽 승인 탭만 "처리됐을 수 있음" 안내로 대응 | 기존 결함 | 승인 영역 작업 시 |
| firewall-admin-console | 기존 동작(무관): 승인 필요 MCP 도구에 도구 카탈로그 category `action` 을 지정하면 워커에서 빠져 에이전트가 호출하지 못함 → 미분류로 둘 것 | 기존 결함 | 도구 카테고리 작업 시 |
| **firewall-agent** | **운영 반영: Flyway V098(`agent_schedule.skip_when_busy`, `agent_schedule_run.skip_reason`)·V099(`agent_alert_receiver`, `agent_alert_receipt`) 적용.** 새 설정 4개(`FIREWALL_ADMIN_AGENT_ID`, `ALERT_HOOK_*` 2개, `AGENT_BUSY_RUN_STALE_SECONDS`)는 기본값이 있어 비워도 기존 동작 불변 | 배포 의존 | **배포 전 필수** |
| **firewall-agent** | **10분 스케줄을 켜기 전 토큰 비용 확인** — 탐지가 없는 빈 회차도 LLM 6회·20~33k 토큰(Sonnet 4.6), 하루 최대 144회. 조회 결과가 비면 짧게 끝나는 실행 경로가 후보 | 비용 | **스케줄 켜기 전** |
| firewall-agent | SC-2 보안 에이전트의 **스케줄 회차 성공 실행** 실측 — 실측 중 회차는 승인 대기로 건너뜀만 나왔고, 재확인 때 Windows 애플리케이션 제어가 `_kiwipiepy` DLL 을 막아 백엔드 기동 불가 | 확인 | 로컬 백엔드 기동 가능할 때 |
| firewall-agent | agent_mcp `mcp-firewall-server`(조회 도구 2종 포함) 미커밋 — 디렉터리 전체가 미추적이고 미커밋 `common` 로깅(`install_tool_call_logging`)에 의존해 단독 커밋 불가 | 저장소 정리 | agent_mcp 미커밋 작업 정리 시 |
| firewall-agent | Sonnet 보고가 "IP 마다 한 줄"(FR-22) 대신 표로 길다 — 판단은 정답. fireware `docs/security-agent-prompt.md` 보고 형식 강화 | 개선 | 요청 시 |
| firewall-agent | 수신 이력에 작업 링크(G4), 웹훅 본문 크기를 읽기 전에 검사(G9), 자동 점검 두 항목 동시 변경 시 대상 존재 선확인(G11) | 경미 | 해당 영역 작업 시 |
| stock-analysis-agents | ~~Minor G3~G9~~ → 모두 해결(G6·G8 fix/market-analysis-guards, G3·G4·G5·G7·G9 fix/market-analysis-minors) | 해결 | — |
| stock-analysis-agents | ~~거래량 순위 ETF 위주~~ → KIS `get_rankings(stocks_only=true)`(대상 제외 10자리 전부 켬, 실측 거래량 30위 = 주식 30)로 해결. 이 변경은 agent_mcp 쪽이라 미커밋 — 배포 시 KIS 서버를 idt 보다 먼저 올린다 | 배포 순서 | 배포 시 |
| stock-analysis-agents | agent_mcp 변경(KIS `get_index_history`·`group`, mcp-dart-server, mcp-perplexity-server, `get_rankings` stocks_only) 미커밋 | 저장소 정리 | agent_mcp 정리 시 |
| stock-analysis-agents | 배포: 운영 DB V100·V101, MCP 서버 3종 등록·키, `MARKET_ANALYSIS_ENABLED` | 배포 | 운영 반영 시 |
