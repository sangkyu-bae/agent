export const WORKFLOW_STEP_TYPE = {
  input: 'input',
  search: 'search',
  code: 'code',
  llm: 'llm',
  condition: 'condition',
  output: 'output',
  api: 'api',
} as const;

export type WorkflowStepType = (typeof WORKFLOW_STEP_TYPE)[keyof typeof WORKFLOW_STEP_TYPE];

export const WORKFLOW_CATEGORY = {
  search: 'search',
  analysis: 'analysis',
  automation: 'automation',
  custom: 'custom',
} as const;

export type WorkflowCategory = (typeof WORKFLOW_CATEGORY)[keyof typeof WORKFLOW_CATEGORY];

export const WORKFLOW_CATEGORY_LABEL: Record<WorkflowCategory, string> = {
  search: '검색',
  analysis: '분석',
  automation: '자동화',
  custom: '커스텀',
};

export interface WorkflowStep {
  type: WorkflowStepType;
  label: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  category: WorkflowCategory;
  steps: WorkflowStep[];
  estimatedTime: string;
  active: boolean;
  runCount?: number;
}

// ─── Flow Canvas Types ────────────────────────────────────────────────────────

export interface FlowNode {
  id: string;
  type: WorkflowStepType;
  label: string;
  x: number;
  y: number;
}

export interface FlowEdge {
  id: string;
  fromId: string;
  toId: string;
}
