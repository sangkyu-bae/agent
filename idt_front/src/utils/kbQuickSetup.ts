// agent-kb-quick-setup Design §3.1 — 이름·범위 매핑, 폼 부착, 진행 단계 파생 (순수 함수).
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import {
  KB_NAME_MAX_LENGTH,
  KB_QUICK_FALLBACK_NAME,
  KB_QUICK_NAME_SUFFIX,
  KB_QUICK_STEP_LABELS,
  type QuickKbResponse,
} from '@/types/kbQuickSetup';
import { PROGRESS_STEP_STATUS, type ProgressStep } from '@/types/progress';
import {
  DEFAULT_RAG_CONFIG,
  type CollectionScope,
  type RagToolConfig,
} from '@/types/ragToolConfig';
import { RAG_CATALOG_TOOL_ID } from '@/utils/agentDetailMapping';

export type AgentVisibility = 'private' | 'department' | 'public';

/** `{에이전트명} 지식` — 이름이 비면 `새 에이전트 지식`, 100자 절단 */
export const kbNameForAgent = (agentName: string): string => {
  const trimmed = agentName.trim();
  if (!trimmed) return KB_QUICK_FALLBACK_NAME;
  const room = KB_NAME_MAX_LENGTH - KB_QUICK_NAME_SUFFIX.length;
  return `${trimmed.slice(0, room).trimEnd()}${KB_QUICK_NAME_SUFFIX}`;
};

const VISIBILITY_TO_SCOPE: Record<AgentVisibility, CollectionScope> = {
  private: 'PERSONAL',
  department: 'DEPARTMENT',
  public: 'PUBLIC',
};

export const scopeForVisibility = (visibility: AgentVisibility): CollectionScope =>
  VISIBILITY_TO_SCOPE[visibility];

/**
 * FR-07: RAG 도구가 없으면 추가하고, 설정은 기존값(없으면 기본값) 위에 kb_id 만 덮는다.
 * KB 선택 시 컬렉션·필터는 KB 것으로 고정되므로 비운다 (RagConfigPanel.handleKbChange 와 동일).
 */
export const attachKbToForm = (
  form: AgentBuilderFormData,
  kbId: string,
): AgentBuilderFormData => {
  const base: RagToolConfig = form.toolConfigs[RAG_CATALOG_TOOL_ID] ?? { ...DEFAULT_RAG_CONFIG };
  const tools = form.tools.includes(RAG_CATALOG_TOOL_ID)
    ? form.tools
    : [...form.tools, RAG_CATALOG_TOOL_ID];
  return {
    ...form,
    tools,
    toolConfigs: {
      ...form.toolConfigs,
      [RAG_CATALOG_TOOL_ID]: {
        ...base,
        kb_id: kbId,
        collection_name: undefined,
        metadata_filter: {},
      },
    },
  };
};

/** [바꾸기] — 도구는 남기고 kb_id 만 푼다. 도구 제거는 기존 도구함 [제거] 경로. */
export const detachKbFromForm = (form: AgentBuilderFormData): AgentBuilderFormData => {
  const current = form.toolConfigs[RAG_CATALOG_TOOL_ID];
  if (!current) return form;
  return {
    ...form,
    toolConfigs: { ...form.toolConfigs, [RAG_CATALOG_TOOL_ID]: { ...current, kb_id: undefined } },
  };
};

export type QuickKbPhase = 'idle' | 'pending' | 'done' | 'error';

/**
 * 진행 카드 3단계. 요청 1개가 KB 생성+업로드를 모두 하므로 pending 동안은 1·2단계가
 * 함께 진행중이고, 응답 후 파일 결과로 2단계를, 성공 파일 유무로 3단계를 확정한다 (FR-08).
 */
export const quickKbProgressSteps = (
  phase: QuickKbPhase,
  result: QuickKbResponse | null,
  total: number,
): ProgressStep[] => {
  const { COMPLETED, IN_PROGRESS, PENDING, ERROR } = PROGRESS_STEP_STATUS;
  if (phase === 'pending') {
    return [
      { id: 'create', label: KB_QUICK_STEP_LABELS.create, status: IN_PROGRESS },
      { id: 'upload', label: KB_QUICK_STEP_LABELS.upload, status: IN_PROGRESS, badgeLabel: `0/${total}` },
      { id: 'attach', label: KB_QUICK_STEP_LABELS.attach, status: PENDING },
    ];
  }
  if (phase === 'error' || !result) {
    return [
      { id: 'create', label: KB_QUICK_STEP_LABELS.create, status: phase === 'error' ? ERROR : PENDING },
      { id: 'upload', label: KB_QUICK_STEP_LABELS.upload, status: PENDING },
      { id: 'attach', label: KB_QUICK_STEP_LABELS.attach, status: PENDING },
    ];
  }
  const anyUploaded = result.uploaded_count > 0;
  return [
    { id: 'create', label: KB_QUICK_STEP_LABELS.create, status: COMPLETED },
    {
      id: 'upload',
      label: KB_QUICK_STEP_LABELS.upload,
      status: anyUploaded ? COMPLETED : ERROR,
      badgeLabel: `${result.uploaded_count}/${result.documents.length}`,
    },
    { id: 'attach', label: KB_QUICK_STEP_LABELS.attach, status: anyUploaded ? COMPLETED : ERROR },
  ];
};
