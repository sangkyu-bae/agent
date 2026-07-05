# Plan: Tool Config Modal (도구 옵션 설정 모달화 + 공통 Modal 컴포넌트)

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | tool-config-modal |
| 작성일 | 2026-07-02 |
| 예상 소요 | 6~8시간 (공통 Modal 신설 2h + 설정 모달 2개 2h + 전체 마이그레이션 21곳 3~4h) |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | 에이전트 빌더 도구함에서 "내부 문서 검색"·"문서추출기"를 선택하면 옵션 패널(RagConfigPanel, DocumentExtractorConfigPanel)이 좌측 패널에 인라인으로 펼쳐져 폼이 수직으로 매우 길어지고 가독성이 크게 떨어짐. 또한 프로젝트 전체에 모달 오버레이 패턴이 21곳 중복 구현되어 있음 |
| **Solution** | 공통 `Modal` 컴포넌트(`components/common/Modal.tsx`)를 신설하고, 두 도구의 옵션 설정을 각각 전용 모달(RagConfigModal, DocumentExtractorConfigModal)로 이동. 도구함 행에는 설정 요약 배지 + 설정 버튼만 표시. 기존 21곳 모달을 공통 컴포넌트로 전면 마이그레이션 |
| **Function UX Effect** | 도구 추가 시 설정 모달 자동 오픈 → 옵션 입력 → 저장 후 도구함 행에서 요약 배지("컬렉션명 · 하이브리드 · top_k 5", "✓ 양식 확정됨")로 상태 확인. 좌측 패널이 항상 컴팩트하게 유지됨 |
| **Core Value** | 에이전트 빌더 핵심 화면의 가독성 회복 + 모달 UI의 프로젝트 전역 일관성(접근성·ESC·배경클릭 동작 통일) 및 유지보수 비용 감소 |

---

## 1. 현재 상황 분석

### 1.1 인라인 옵션 패널 문제

`LeftConfigPanel`의 "도구함" `CollapsibleSection` 내부에서, 특정 도구가 선택되면 설정 UI가 인라인으로 렌더링된다:

| 도구 | tool_id | 인라인 패널 | 렌더 위치 |
|------|---------|------------|-----------|
| 내부 문서 검색 | `internal:internal_document_search` | `RagConfigPanel` (컬렉션 선택, 메타데이터 필터 최대 10개, 검색 모드, top_k 슬라이더, 위키 우선 토글, 도구 이름/설명) | `LeftConfigPanel.tsx:282-286` |
| 문서추출기 | `DOCUMENT_EXTRACTOR_TOOL_ID` | `DocumentExtractorConfigPanel` (파일 업로드, 미리보기 iframe, 슬롯 목록/수동추가/재요청/확정) | `LeftConfigPanel.tsx:288-298` |

두 도구를 모두 선택하면 도구함 섹션 하나가 화면 몇 페이지 분량으로 늘어나 지침/모델/스킬 등 다른 섹션의 가독성을 해친다.

### 1.2 모달 오버레이 패턴 중복 (21곳 / 19파일)

`fixed inset-0 z-50 ... bg-black/50(40)` 오버레이 + 헤더 + 닫기 버튼 구조가 공통 컴포넌트 없이 반복 구현되어 있다:

| 분류 | 파일 |
|------|------|
| agent-builder (4) | `ModelSettingsModal`, `ToolPickerModal`, `SkillPickerModal`, `SubAgentManagerModal` |
| collection (5) | `UploadDocumentModal`, `CreateCollectionModal`, `RenameCollectionModal`, `UpdateScopeModal`, `ChunkDetailModal` |
| agent-store (2) | `PublishAgentModal`, `AgentDetailModal` |
| admin/common (5) | `ConfirmDialog`, `UserRegisterModal`, `AdminDepartmentsPage`(인라인), `AdminSkillsPage`(인라인), `AdminMcpServersPage`(인라인 2곳) |
| 기타 (3파일 4곳) | `ChunkViewer`, `WikiDetailPanel`, `ToolAdminPage`(인라인 2곳) |

배경 클릭 닫기 여부, `backdrop-blur` 적용 여부, dim 농도(`/40` vs `/50`), ESC 처리(대부분 없음), aria 속성 등이 파일마다 제각각이다.

### 1.3 사용자 결정 사항 (Q&A 결과)

| 항목 | 결정 |
|------|------|
| 공통화 범위 | **프로젝트 전체 21곳 마이그레이션** (사용자 확정) |
| 도구 행 상태 표시 | **설정 요약 배지 표시** (사용자 확정) |
| 모달 트리거 | 도구 추가 시 자동 오픈 + 행의 "설정" 버튼 (추천안 적용) |
| 저장 방식 | RAG: 저장/취소 (로컬 드래프트) · 문서추출기: 즉시 반영 + 닫기 (§2.3 참고) (추천안 적용) |

---

## 2. 구현 범위

### 2.1 In-Scope

| # | 항목 | 설명 |
|---|------|------|
| 1 | 공통 `Modal` 컴포넌트 신설 | `src/components/common/Modal.tsx` — 오버레이/센터링, 타이틀+닫기 버튼 헤더, ESC 닫기, 배경 클릭 닫기(옵션), 사이즈 변형(md/lg/xl), footer 슬롯, `role="dialog"` + `aria-modal` |
| 2 | `RagConfigModal` 신설 | 기존 `RagConfigPanel` 본문을 모달로 래핑. 모달 로컬 상태로 편집 → **저장** 시에만 `onRagConfigChange` 반영, **취소** 시 폐기 (ModelSettingsModal과 동일 UX) |
| 3 | `DocumentExtractorConfigModal` 신설 | 기존 `DocumentExtractorConfigPanel` 본문을 모달로 래핑. 업로드/재추천은 서버 뮤테이션이므로 즉시 반영 + **닫기** 버튼만 제공 |
| 4 | 도구함 행 개선 | 설정형 도구(RAG·문서추출기) 행에 "설정" 버튼 + 설정 요약 배지 표시 (§2.2) |
| 5 | 자동 오픈 플로우 | ToolPickerModal에서 설정형 도구를 **추가**하면 picker를 닫고 해당 설정 모달을 즉시 오픈 |
| 6 | 인라인 패널 제거 | `LeftConfigPanel.tsx:282-298`의 인라인 렌더링 삭제 |
| 7 | sessionStorage 복원 위치 이동 | 문서추출기 드래프트 복원(R4)을 패널 마운트 시점 → `LeftConfigPanel`(또는 페이지) 레벨로 이동 — 모달을 열지 않아도 배지가 정확히 표시되도록 |
| 8 | 전체 모달 마이그레이션 | §1.2의 21곳을 공통 `Modal` 기반으로 교체 (`ConfirmDialog`는 내부에서 `Modal`을 사용하도록 리팩토링, 외부 API 유지) |
| 9 | 테스트 | Modal 단위 테스트 + 신규 모달 2종 테스트 + LeftConfigPanel 동작 테스트 + 마이그레이션 대상 기존 테스트 그린 유지 (TDD) |

### 2.2 설정 요약 배지 사양

| 도구 | 상태 | 배지 표시 |
|------|------|-----------|
| 내부 문서 검색 | 설정됨 | `{컬렉션 display_name 또는 '전체'} · {검색모드 라벨} · top_k {n}` (+ 위키 우선 시 `위키` 칩) |
| 문서추출기 | 드래프트 없음 | `⚠ 양식 미등록` (amber) |
| 문서추출기 | 작성 중 (미확정) | `작성 중 · 슬롯 {n}` (zinc) |
| 문서추출기 | 확정됨 | `✓ 양식 확정됨` (emerald) |

### 2.3 문서추출기 모달의 특수성 (설계 시 유의)

- 업로드(extract)·재추천(refine)은 **서버 뮤테이션**이라 로컬 드래프트/취소 모델이 성립하지 않음 → 즉시 반영 + 닫기.
- 드래프트는 폼 상태 + sessionStorage(R4)에 이미 보존되므로 모달을 닫아도 작업 유실 없음.
- **유휴 5분 자동 재추천(GA3) 타이머**는 현재 패널 마운트 중에만 동작 → 모달화 이후 "모달이 열려 있는 동안만" 동작하는 것으로 범위 축소. Design 단계에서 확정 (허용 가능한 동작 변경으로 판단).

### 2.4 Out-of-Scope

- 백엔드 API 변경 없음 (프론트 전용 리팩토링)
- VisualCanvas(비주얼 탭)의 노드 → 설정 모달 연결 (후속 과제, 단 리소스 노드에서 열 수 있게 하는 것은 Design에서 재검토)
- RagConfigPanel / DocumentExtractorConfigPanel의 내부 필드·검증 로직 변경 (본문 UI는 그대로 재사용)
- 모달 애니메이션/포커스 트랩 고도화 (기본 ESC + 배경 클릭 + autoFocus 수준까지만)

---

## 3. 구현 순서 (TDD)

### Step 1: 공통 Modal 컴포넌트 (Red → Green)

`src/components/common/Modal.tsx` + `Modal.test.tsx`

```tsx
interface ModalProps {
  isOpen: boolean;
  title: string;
  onClose: () => void;
  size?: 'md' | 'lg' | 'xl';          // max-w-md / max-w-2xl / max-w-4xl
  footer?: ReactNode;                  // 하단 액션 영역 슬롯
  closeOnBackdrop?: boolean;           // 기본 true
  children: ReactNode;
}
```

- 테스트: isOpen=false 시 미렌더 / 타이틀·닫기 버튼 / ESC keydown → onClose / 배경 클릭 → onClose (closeOnBackdrop=false면 무시) / 콘텐츠 클릭은 전파 차단 / role="dialog" aria-modal.

### Step 2: RagConfigModal (Red → Green)

`src/components/agent-builder/RagConfigModal.tsx` — Modal(size="lg") 내부에 기존 RagConfigPanel 렌더. 열릴 때 `config`를 로컬 상태로 복사, 저장 시 `onApply(local)`, 취소/닫기 시 폐기.

- 테스트: 열림 시 현재 config 반영 / 값 변경 후 취소 → onApply 미호출 / 저장 → 변경값으로 onApply 1회.

### Step 3: DocumentExtractorConfigModal (Red → Green)

`src/components/agent-builder/DocumentExtractorConfigModal.tsx` — Modal(size="lg") 내부에 기존 DocumentExtractorConfigPanel 렌더, footer 없이 "닫기"만. sessionStorage 복원 effect는 패널에서 제거하고 LeftConfigPanel 레벨로 이동.

### Step 4: LeftConfigPanel 통합 (Red → Green)

- 인라인 패널 제거, 설정형 도구 행에 배지(§2.2) + "설정" 버튼.
- `handleToolToggle` 래핑: 설정형 도구 추가 시 picker 닫고 설정 모달 오픈.
- 테스트: 배지 표시 / 설정 버튼 → 모달 오픈 / RAG 도구 추가 → RagConfigModal 자동 오픈 / 인라인 패널 부재 확인. 기존 `RagConfigPanel.test.tsx`, `DocumentExtractorConfigPanel.test.tsx`는 패널 단위로 그린 유지.

### Step 5: 전체 마이그레이션 (21곳, 파일 단위 커밋)

우선순위: agent-builder 4곳 → common(ConfirmDialog) → collection 5곳 → agent-store 2곳 → admin 5곳 → 기타 4곳.
각 파일 교체 후 해당 테스트 실행(그린 확인) 후 다음 파일 진행. 배경 클릭 닫기 없던 모달은 `closeOnBackdrop=false`로 기존 동작 보존.

### Step 6: 전체 검증

`npm run test:run -- --pool=threads` + `npm run type-check` + `npm run lint`. 사전 실패 8건(기존 이슈)은 회귀로 오인하지 않음.

---

## 4. 영향 파일 목록

### 신규

| 파일 | 내용 |
|------|------|
| `src/components/common/Modal.tsx` (+test) | 공통 모달 |
| `src/components/agent-builder/RagConfigModal.tsx` (+test) | RAG 옵션 모달 |
| `src/components/agent-builder/DocumentExtractorConfigModal.tsx` (+test) | 문서추출기 모달 |

### 수정

| 파일 | 변경 |
|------|------|
| `src/components/agent-builder/LeftConfigPanel.tsx` | 인라인 패널 제거, 배지/설정 버튼, 자동 오픈, 드래프트 복원 이동 |
| `src/components/agent-builder/DocumentExtractorConfigPanel.tsx` | sessionStorage 복원 effect 제거 (상위 이동) |
| §1.2의 19개 파일 | 공통 Modal로 오버레이 교체 |

---

## 5. 리스크

| 리스크 | 대응 |
|--------|------|
| 21곳 일괄 마이그레이션 회귀 | 파일 단위 교체 + 즉시 테스트, 기존 동작(배경 클릭 여부 등) 옵션으로 보존 |
| 문서추출기 유휴 재추천 동작 변경 | §2.3 명시, Design 단계에서 확정 |
| 모달 중첩(picker → 설정 모달) z-index | picker를 닫고 열기(중첩 회피)로 설계 |
| 배지 표시용 컬렉션 이름 조회 | `useCollections` 훅 재사용 (LeftConfigPanel에서 display_name 매핑) |

---

## 6. 완료 기준 (Acceptance Criteria)

1. 도구함에서 내부 문서 검색/문서추출기를 선택해도 좌측 패널에 인라인 옵션 UI가 나타나지 않는다.
2. 설정형 도구 추가 시 설정 모달이 자동으로 열리고, 이후 행의 "설정" 버튼으로 재진입할 수 있다.
3. 도구 행에 §2.2 요약 배지가 정확히 표시된다 (새로고침 후 sessionStorage 드래프트 복원 포함).
4. RAG 모달에서 취소 시 폼 값이 변하지 않고, 저장 시에만 반영된다.
5. 프로젝트 내 `fixed inset-0 z-50` 오버레이 직접 구현이 0곳이 된다 (공통 Modal 내부 1곳 제외).
6. 기존 테스트 스위트 그린 (사전 실패 8건 제외) + 신규 테스트 통과.
