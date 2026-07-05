# Design: Tool Config Modal (도구 옵션 설정 모달화 + 공통 Modal 컴포넌트)

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | tool-config-modal |
| Plan 참조 | `docs/01-plan/features/tool-config-modal.plan.md` |
| 작성일 | 2026-07-02 |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | 도구함에서 내부 문서 검색/문서추출기 선택 시 옵션 패널이 인라인으로 펼쳐져 좌측 패널 가독성 저하 + 모달 오버레이 21곳 중복 구현 |
| **Solution** | 공통 `Modal` 신설 → 두 도구 설정을 전용 모달로 이동, 도구 행에는 요약 배지 + 설정 버튼. 기존 21곳 전면 마이그레이션 |
| **Function UX Effect** | 도구 추가 → 설정 모달 자동 오픈 → 저장 → 행 배지로 상태 확인. 좌측 패널 상시 컴팩트 |
| **Core Value** | 빌더 화면 가독성 회복 + 모달 동작(ESC/배경클릭/aria) 전역 통일 |

---

## 1. 아키텍처 개요

### 1.1 현재 (문제 상태)

```
LeftConfigPanel
└─ CollapsibleSection "도구함"
   ├─ 도구 행 리스트 (이름 + 제거 버튼)
   ├─ ragConfig 존재 시 → RagConfigPanel 인라인 (≈ 500px+)   ❌
   └─ 문서추출기 선택 시 → DocumentExtractorConfigPanel 인라인 (≈ 700px+) ❌
```

### 1.2 변경 후 (목표)

```
LeftConfigPanel
└─ CollapsibleSection "도구함"
   └─ 도구 행 리스트
      ├─ 일반 도구:   [이름] [MCP칩?] ──────────── [제거]
      └─ 설정형 도구: [이름] [요약 배지] ─ [설정] [제거]
                        │
                        ├─ RAG 행 "설정" 클릭 ──▶ RagConfigModal (저장/취소)
                        └─ 추출기 행 "설정" 클릭 ▶ DocumentExtractorConfigModal (즉시반영/닫기)

ToolPickerModal에서 설정형 도구 추가 시:
  onToggle(추가) → picker 닫기 → 해당 설정 모달 자동 오픈
```

### 1.3 컴포넌트 의존 구조

```
components/common/Modal.tsx          ← 신규 (오버레이/헤더/ESC/배경클릭/footer)
        ▲
        ├─ agent-builder/RagConfigModal.tsx              ← 신규 (RagConfigPanel 래핑)
        ├─ agent-builder/DocumentExtractorConfigModal.tsx ← 신규 (Panel 래핑)
        ├─ agent-builder/{ToolPicker,ModelSettings,SkillPicker,SubAgentManager}Modal
        ├─ common/ConfirmDialog.tsx  (내부 구현만 교체, 외부 API 유지)
        └─ …전체 21곳 마이그레이션 (§4 카탈로그)
```

---

## 2. 상세 설계

### 2.1 공통 Modal — `src/components/common/Modal.tsx`

```tsx
import { useEffect, type ReactNode } from 'react';

export interface ModalProps {
  /** 생략(기본 true) 시 부모 조건부 렌더 방식 지원 (WikiDetailPanel 등 3곳) */
  isOpen?: boolean;
  onClose: () => void;
  /** 헤더 타이틀. 생략 시 헤더 자체를 렌더하지 않음 (커스텀 헤더는 children으로) */
  title?: ReactNode;
  /** 타이틀 하단 보조 설명 (SubAgentManager·UserRegister 등) */
  subtitle?: ReactNode;
  /** 콘텐츠 박스 최대 폭. 기본 'md' */
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  /** 하단 액션 영역. 콘텐츠 스크롤과 분리 렌더 */
  footer?: ReactNode;
  /** 배경 클릭으로 닫기. 기본 true (예외 3곳: ToolAdmin 2곳·UserRegister) */
  closeOnBackdrop?: boolean;
  /** ESC로 닫기. 기본 true — document keydown으로 표준화 */
  closeOnEsc?: boolean;
  /** true면 배경클릭/ESC/X 모두 차단 (업로드 진행 중 등) */
  disableClose?: boolean;
  /** 딤 스타일. 기본 'default'(bg-black/50), 'blur'(bg-black/40 + backdrop-blur-sm) */
  dim?: 'default' | 'blur';
  /** 스크롤 모드. 기본 'body'(헤더/footer 고정 + 본문 스크롤), 'content'(박스 전체 스크롤), 'none' */
  scroll?: 'body' | 'content' | 'none';
  /** 헤더 X 닫기 버튼. 기본 true (title 있을 때) */
  showCloseButton?: boolean;
  /** 콘텐츠 박스 추가 클래스 (고정폭 w-[360px] 등 특수 레이아웃 보존용) */
  contentClassName?: string;
  children: ReactNode;
}
```

**구현 스펙**

| 항목 | 스펙 |
|------|------|
| 조건부 렌더 | `if (!isOpen) return null` (기존 관례 유지) |
| 오버레이 | `fixed inset-0 z-50 flex items-center justify-center px-4` + dim 클래스 |
| size 매핑 | sm=`max-w-sm`, md=`max-w-md`, lg=`max-w-lg`, xl=`max-w-2xl`, 2xl=`max-w-4xl` (`max-w-3xl`는 contentClassName) |
| 콘텐츠 박스 | `flex max-h-[85vh] w-full flex-col rounded-2xl bg-white shadow-2xl` — scroll='body'면 헤더/footer 고정 + 본문 `overflow-y-auto`, 'content'면 박스 전체 `overflow-y-auto`, 'none'이면 스크롤 없음 |
| 배경 클릭 | 오버레이 `onClick` → `closeOnBackdrop && !disableClose && onClose()`. 콘텐츠는 `stopPropagation` |
| ESC | `useEffect`로 `document` keydown 등록 (isOpen && closeOnEsc && !disableClose일 때만) → 기존 4종 제각각 구현(window/document/onKeyDown/미구현)을 표준화. ESC가 없던 모달에 ESC가 생기는 것은 의도된 동작 개선 |
| 접근성 | `role="dialog"` `aria-modal="true"` `aria-label={typeof title === 'string' ? title : undefined}`, 닫기 버튼 `aria-label="닫기"` |
| 헤더 | title 존재 시: `text-[16px] font-semibold text-zinc-900` + 우측 X 버튼 (기존 스타일 그대로) |
| footer | 존재 시 `mt-5 flex justify-end gap-2` 래퍼로 렌더 |

> 포커스 트랩·포탈·애니메이션은 Out-of-Scope (Plan §2.4). 중첩 모달은 "닫고 열기"로 회피하므로 z-index 계층 불필요.

**테스트 (Modal.test.tsx)**

1. isOpen=false → 미렌더
2. title/children/footer 렌더
3. X 버튼·ESC·배경 클릭 → onClose (배경: closeOnBackdrop=false면 미호출)
4. 콘텐츠 클릭 → onClose 미호출
5. role="dialog" + aria-modal

### 2.2 RagConfigModal — `src/components/agent-builder/RagConfigModal.tsx`

```tsx
interface RagConfigModalProps {
  isOpen: boolean;
  config: RagToolConfig;            // form.toolConfigs[RAG_TOOL_ID]
  onApply: (config: RagToolConfig) => void;
  onClose: () => void;
}
```

- **로컬 드래프트 방식** (ModelSettingsModal과 동일): 열릴 때 `useEffect([isOpen])`로 `config`를 로컬 상태에 복사 → `RagConfigPanel`은 로컬 상태로 렌더 → **저장** 시 `onApply(local); onClose()` / **취소·X·ESC·배경 클릭** 시 폐기.
- `Modal size="lg"`(max-w-2xl), title="내부 문서 검색 설정", footer=취소/저장 버튼.
- `RagConfigPanel`은 **무변경 재사용** (config/onChange props 그대로) — 내부 `useCollections`/`useMetadataKeys` 훅도 그대로 동작.
- 저장 버튼 스타일: `bg-zinc-900 … hover:bg-zinc-800` (ModelSettingsModal 관례).

### 2.3 DocumentExtractorConfigModal — `src/components/agent-builder/DocumentExtractorConfigModal.tsx`

```tsx
interface DocumentExtractorConfigModalProps {
  isOpen: boolean;
  draft: DocumentExtractorDraft | null;   // form.documentExtractorDraft
  onChange: (draft: DocumentExtractorDraft | null) => void;  // 즉시 반영
  onClose: () => void;
}
```

- **즉시 반영 + 닫기** 방식: 업로드(extract)/재추천(refine)이 서버 뮤테이션이므로 취소 모델 불성립 (Plan §2.3). footer는 "닫기" 단독.
- `Modal size="lg"`, title="문서추출기 — 양식 등록", `closeOnBackdrop={false}` — 업로드/편집 중 배경 오클릭으로 닫히는 사고 방지 (드래프트는 보존되지만 UX 혼란 방지).
- `DocumentExtractorConfigPanel` 재사용하되 **R4 effect 2개를 패널에서 제거**하고 LeftConfigPanel로 이동 (§2.5):
  - 마운트 시 sessionStorage 복원 (`DocumentExtractorConfigPanel.tsx:52-60`)
  - draft 변경 시 sessionStorage 동기화 (`:63-65`)
  - 이동 근거: ① 모달을 열지 않아도 복원되어 배지가 정확해짐 ② 현재 구조는 도구 해제로 패널이 언마운트되면 `saveDraftToSession(null)`이 실행되지 않아 sessionStorage에 스테일 드래프트가 남는 잠재 버그가 있음 — 상위 이동으로 함께 해소.
- **유휴 5분 재추천(GA3) 타이머는 패널에 유지** → 모달 열림 중에만 동작 (Plan §2.3 확정: 허용된 동작 변경).

### 2.4 LeftConfigPanel 통합 — `src/components/agent-builder/LeftConfigPanel.tsx`

#### 상태 추가

```tsx
const [isRagConfigOpen, setRagConfigOpen] = useState(false);
const [isExtractorConfigOpen, setExtractorConfigOpen] = useState(false);
```

#### 자동 오픈: onToolToggle 래핑

```tsx
const CONFIGURABLE_TOOL_IDS: readonly string[] = [RAG_TOOL_ID, DOCUMENT_EXTRACTOR_TOOL_ID];

const handleToolToggle = (toolId: string) => {
  const isAdding = !form.tools.includes(toolId);
  onToolToggle(toolId);
  if (isAdding && CONFIGURABLE_TOOL_IDS.includes(toolId)) {
    setToolModalOpen(false);            // picker를 닫고 (중첩 회피)
    if (toolId === RAG_TOOL_ID) setRagConfigOpen(true);
    else setExtractorConfigOpen(true);
  }
};
```

- ToolPickerModal의 `onToggle`에 이 래퍼를 전달. VisualCanvas의 `onAddTool`은 picker만 열므로 무변경.
- 자동 오픈된 RAG 모달에서 취소해도 도구는 추가된 상태 유지 (기본값 `DEFAULT_RAG_CONFIG`로 동작 — `AgentBuilderPage.handleToolToggle:217`이 이미 기본값을 넣음).

#### 인라인 패널 제거 및 행 개선

`LeftConfigPanel.tsx:282-298`의 `RagConfigPanel`/`DocumentExtractorConfigPanel` 인라인 렌더를 삭제하고, `selectedTools.map` 행 렌더를 확장:

```tsx
{selectedTools.map((tool) => {
  const isConfigurable = CONFIGURABLE_TOOL_IDS.includes(tool.tool_id);
  return (
    <li key={tool.tool_id} className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5">
      <div className="flex items-center gap-2">
        <span className="text-[13px] font-medium text-zinc-700">{tool.name}</span>
        {tool.source === 'mcp' && <span className="…">MCP</span>}
        {isConfigurable && (
          <button type="button" onClick={() => openConfig(tool.tool_id)}
            aria-label={`${tool.name} 설정`}
            className="ml-auto rounded-lg px-2 py-1 text-[12px] font-medium text-violet-600 hover:bg-violet-50">
            설정
          </button>
        )}
        <button /* 제거 — isConfigurable이면 ml-auto 제거 */ … />
      </div>
      {isConfigurable && <ToolConfigBadge … />}  {/* 요약 배지 행 */}
    </li>
  );
})}
```

#### 요약 배지 사양 (Plan §2.2 구체화)

| 도구 | 조건 | 배지 텍스트 | 스타일 |
|------|------|------------|--------|
| RAG | `ragConfig` 존재 | `{컬렉션} · {모드} · top_k {n}` (+`위키` 칩) | `text-[11.5px] text-zinc-400` |
| 추출기 | `draft == null` | `⚠ 양식 미등록` | `text-amber-600 bg-amber-50` |
| 추출기 | `draft && !confirmed` | `작성 중 · 슬롯 {slots.length}` | `text-zinc-500 bg-zinc-100` |
| 추출기 | `draft.confirmed` | `✓ 양식 확정됨` | `text-emerald-700 bg-emerald-50` |

- 컬렉션 표시명: `useCollections()` 훅을 LeftConfigPanel에서 호출해 `collection_name → display_name` 매핑, 미선택(`undefined`)이면 `전체`. TanStack Query 캐시가 RagConfigPanel과 공유되므로 추가 네트워크 비용 없음.
- 모드 라벨: `hybrid=하이브리드, vector_only=벡터, bm25_only=BM25` — `RagConfigPanel.SEARCH_MODES`를 export하여 재사용.

### 2.5 sessionStorage R4 effect 이동

LeftConfigPanel에 추가 (패널에서는 두 effect 삭제):

```tsx
// R4 복원: 추출기 도구가 선택돼 있고 드래프트가 없으면 sessionStorage에서 복원
const restoredRef = useRef(false);
useEffect(() => {
  if (restoredRef.current) return;
  if (!form.tools.includes(DOCUMENT_EXTRACTOR_TOOL_ID) || form.documentExtractorDraft) return;
  restoredRef.current = true;
  const restored = loadDraftFromSession();
  if (restored) onChange({ ...form, documentExtractorDraft: restored });
}, [form.tools]);

// R4 동기화: 드래프트 변경 → sessionStorage (null 포함 → 도구 해제 시 정리 버그 해소)
useEffect(() => {
  saveDraftToSession(form.documentExtractorDraft ?? null);
}, [form.documentExtractorDraft]);
```

- 복원 알림("이전에 작업하던 양식 초안을 복원했습니다")은 배지가 `작성 중`으로 표시되므로 별도 토스트 없이 생략 가능. 모달 내 noticeMessage 로직은 패널에서 제거.

### 2.6 기존 모달 21곳 마이그레이션 카탈로그 (전수 조사 완료)

> 원칙: 각 모달의 **기존 동작을 그대로 보존**하는 Modal props 조합으로 교체한다.
> 예외적으로 ESC 닫기는 전 모달에 표준 제공(동작 개선), 접근성(`role="dialog"` `aria-modal`)도 Modal이 일괄 부여한다.

| # | 대상 | size | dim | closeOnBackdrop | scroll | 특이 처리 | 기존 테스트 |
|---|------|------|-----|-----------------|--------|-----------|------------|
| 1 | agent-builder/ToolPickerModal | lg | default | true | body | 즉시 토글 + footer "완료" | O |
| 2 | agent-builder/ModelSettingsModal | md | default | true | none | 열릴 때 로컬 초기화 유지 | O |
| 3 | agent-builder/SkillPickerModal | lg | default | true | body | 타이틀에 카운트 배지 (`title`에 ReactNode) | X |
| 4 | agent-builder/SubAgentManagerModal | `max-w-3xl` (contentClassName) | default | true | body | 2컬럼 각자 스크롤 → 본문 내부에서 처리 | O |
| 5 | common/ConfirmDialog | sm | default | true | none | **외부 API 유지** — variant/isPending/error 로직은 ConfirmDialog에 잔존, 내부만 Modal 사용. X버튼 없음 → `showCloseButton={false}` | X |
| 6 | collection/CreateCollectionModal | md | default | true | none | `<form onSubmit>` — form+버튼을 children에 유지, footer 미사용 (§폼 규칙) | O |
| 7 | collection/RenameCollectionModal | md | default | true | none | form 패턴, autoFocus 유지 | X |
| 8 | collection/UpdateScopeModal | md | default | true | none | form 패턴, 열릴 때 초기화 유지 | O |
| 9 | collection/UploadDocumentModal | lg | default | true | content | **`disableClose={isLoading}`** (업로드 중 배경/ESC/X 차단 — 기존 동작 보존) | X |
| 10 | collection/ChunkDetailModal | 2xl | blur | true | body | 부모 조건부 렌더 (isOpen 생략), 커스텀 헤더(배지) → title 생략 + children 헤더 | X |
| 11 | agent-store/PublishAgentModal | lg | default | true | none | 목록만 내부 스크롤 유지 | X |
| 12 | agent-store/AgentDetailModal | xl | default | true | content | absolute X버튼 → `showCloseButton={false}` + 자체 X 유지 (레이아웃 보존) | X |
| 13 | rag/ChunkViewer (ChunkMetaModal) | lg | `bg-black/40` → default로 통일 | true | none | 부모 조건부 렌더 | X |
| 14 | pages/WikiPage/WikiDetailPanel | xl | default | true | content | 부모 조건부 렌더, 편집모드별 footer 세트 교체 | O |
| 15 | pages/AdminDepartmentsPage (FormModal) | md | default | true | none | form 패턴, X버튼 없음 유지 | X |
| 16a | pages/ToolAdminPage DeleteConfirm | `w-[360px]` (contentClassName) | blur | **false** | none | X버튼 없음 | X |
| 16b | pages/ToolAdminPage ToolFormModal | xl | blur | **false** | body | `h-full max-h-[720px]` → contentClassName | X |
| 17 | admin/UserRegisterModal | lg | default | **false** | content | form noValidate, 기존 window ESC → Modal 표준 ESC로 대체 | O |
| 18 | pages/AdminSkillsPage (SkillFormModal) | lg | default | true | content | form 패턴 | O |
| 19a | pages/AdminMcpServersPage FormModal | lg | default | true | content | form + 연결테스트 버튼 유지 | O |
| 19b | pages/AdminMcpServersPage 행 테스트 결과 | md | default | true | none | 인라인 JSX → Modal 직접 사용 | O(페이지) |

**폼 모달 규칙**: `<form onSubmit>` 기반 모달은 submit 버튼이 form 내부에 있어야 하므로, **form과 액션 버튼 전체를 children에 유지**하고 Modal의 `footer` 슬롯은 사용하지 않는다 (구조 변경 최소화). footer 슬롯은 button-onClick 기반 모달만 사용.

**딤 통일 결정**: `bg-black/40`(blur 없음, #13·#1 ChunkViewer/WikiDetailPanel 계열)은 시각 차가 미미하므로 `default(bg-black/50)`로 통일한다. `backdrop-blur-sm` 3곳만 `dim="blur"` 유지.

**접근성 상향**: 기존에 aria가 없던 모달들도 Modal을 통해 `role="dialog"` `aria-modal="true"`를 일괄 획득한다 (기존 테스트에서 `getByRole('dialog')` 충돌 여부 각 파일 교체 시 확인).

---

## 3. 구현 순서 체크리스트 (TDD)

```
[ ] Step 1: Modal.test.tsx (Red) → Modal.tsx (Green)
[ ] Step 2: RagConfigModal.test.tsx (Red) → RagConfigModal.tsx (Green)
[ ] Step 3: DocumentExtractorConfigModal.test.tsx (Red) → 모달 구현 +
            DocumentExtractorConfigPanel에서 R4 effect 2개 제거 (기존 패널 테스트 수정)
[ ] Step 4: LeftConfigPanel — 인라인 제거, 행 배지/설정 버튼, 자동 오픈, R4 effect 수용
            (LeftConfigPanel 신규 테스트 + RagConfigPanel SEARCH_MODES export)
[ ] Step 5: agent-builder 4곳 마이그레이션 (ToolPicker → ModelSettings → SkillPicker → SubAgentManager)
[ ] Step 6: ConfirmDialog 내부 교체 (외부 API 유지 — 사용처 무변경)
[ ] Step 7: collection 5곳 → agent-store 2곳 → admin 5곳 → 기타 4곳 (파일 단위, 각각 테스트 그린 확인)
[ ] Step 8: 전체 검증 — npm run test:run -- --pool=threads / type-check / lint
```

---

## 4. 파일별 변경 요약

| 파일 | 유형 | 내용 |
|------|------|------|
| `src/components/common/Modal.tsx` (+test) | 신규 | 공통 모달 |
| `src/components/agent-builder/RagConfigModal.tsx` (+test) | 신규 | 로컬 드래프트 + 저장/취소 |
| `src/components/agent-builder/DocumentExtractorConfigModal.tsx` (+test) | 신규 | 즉시 반영 + 닫기 |
| `src/components/agent-builder/LeftConfigPanel.tsx` | 수정 | 인라인 제거, 배지/설정 버튼, 자동 오픈, R4 effect |
| `src/components/agent-builder/DocumentExtractorConfigPanel.tsx` | 수정 | R4 effect 2개 + notice 제거 |
| `src/components/agent-builder/RagConfigPanel.tsx` | 수정 | `SEARCH_MODES` export |
| §2.6 카탈로그 19파일 | 수정 | 공통 Modal로 오버레이 교체 |

---

## 5. 테스트 계획

| 대상 | 항목 |
|------|------|
| `Modal` | §2.1 테스트 5종 |
| `RagConfigModal` | 열림 시 config 반영 / 취소 → onApply 미호출 / 저장 → 변경값 1회 호출 |
| `DocumentExtractorConfigModal` | draft 렌더 / onChange 즉시 전달 / 닫기 버튼 |
| `LeftConfigPanel` | 인라인 패널 부재 / 배지 4상태 / 설정 버튼 → 모달 오픈 / RAG 추가 → 자동 오픈 + picker 닫힘 / sessionStorage 복원 → 배지 `작성 중` |
| 마이그레이션 회귀 | 기존 테스트 파일 그린 유지 (ToolPickerModal, ModelSettingsModal, SubAgentManagerModal, CreateCollectionModal 등 9파일) — 사전 실패 8건은 제외 |
| 테스트 부재 11파일 | ChunkViewer, ToolAdminPage, ConfirmDialog, PublishAgentModal, AgentDetailModal, SkillPickerModal, UploadDocumentModal, RenameCollectionModal, ChunkDetailModal, AdminDepartmentsPage 등 — 공통 Modal 단위 테스트가 오버레이 동작을 커버하므로 개별 스냅샷 테스트는 추가하지 않되, 교체 시 수동 스모크(열기/닫기/액션) 확인 |

---

## 6. 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| 21곳 마이그레이션 회귀 | 파일 단위 교체 + 즉시 테스트. 동작 차이(배경클릭/blur)는 props로 보존 |
| ESC 전역 리스너 중복 (모달 다중 마운트) | isOpen일 때만 리스너 등록 → 동시 열림은 "닫고 열기" 설계로 1개 이하 |
| RagConfigModal 자동 오픈 시 config 미준비 | 부모 `handleToolToggle`이 토글 시점에 `DEFAULT_RAG_CONFIG` 주입 → 다음 렌더에서 항상 존재. `config` 없으면 모달 미렌더 가드 |
| sessionStorage 이동에 따른 기존 패널 테스트 실패 | Step 3에서 패널 테스트를 함께 수정 (복원 테스트는 LeftConfigPanel 테스트로 이관) |
