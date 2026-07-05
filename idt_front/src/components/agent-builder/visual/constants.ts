/**
 * Agent Builder 비주얼 캔버스 상수.
 * agent-builder-visual-canvas Design §2.1.
 */

export type VisualNodeKind =
  | 'agent'
  | 'skill'
  | 'tool'
  | 'subagent'
  | 'middleware'
  | 'model';

/** 리소스 노드 종류 (에이전트 허브 제외). */
export type ResourceKind = Exclude<VisualNodeKind, 'agent'>;

/** 노드 ID (각 종류 단일 인스턴스). */
export const NODE_ID: Record<VisualNodeKind, string> = {
  agent: 'agent',
  skill: 'skill',
  tool: 'tool',
  subagent: 'subagent',
  middleware: 'middleware',
  model: 'model',
};

/** 엣지 색상 (스크린샷 기준). */
export const EDGE_COLOR: Record<ResourceKind, string> = {
  skill: '#f59e0b', // amber  — 스킬
  tool: '#3b82f6', // blue   — 도구
  subagent: '#8b5cf6', // violet — 서브에이전트
  middleware: '#a855f7', // purple — 미들웨어
  model: '#f59e0b', // amber  — 모델
};

/** 기본 레이아웃 좌표 (허브=에이전트, 스크린샷 배치 근사). */
export const DEFAULT_LAYOUT: Record<VisualNodeKind, { x: number; y: number }> = {
  skill: { x: 40, y: 20 },
  tool: { x: 440, y: 20 },
  agent: { x: 40, y: 220 },
  subagent: { x: 440, y: 360 },
  model: { x: 40, y: 560 },
  middleware: { x: 440, y: 600 },
};

/** 빈 상태 텍스트 (스크린샷 일치). */
export const EMPTY_TEXT = {
  skill: '스킬이 설정되지 않았습니다',
  tool: '도구가 설정되지 않았습니다',
  subagent: 'No sub-agents',
  middleware: '미들웨어 없음',
  instructions: 'No instructions set',
} as const;

/** 리소스 노드 헤더 메타 (제목/아이콘/액션 라벨). */
export const RESOURCE_META: Record<
  ResourceKind,
  { title: string; icon: string; actionLabel: string }
> = {
  skill: { title: '스킬', icon: '📖', actionLabel: '+ 스킬 추가' },
  tool: { title: '도구', icon: '🔧', actionLabel: '+ 도구 추가' },
  subagent: { title: '서브 에이전트', icon: '👥', actionLabel: '⚙' },
  middleware: { title: '미들웨어', icon: '🧩', actionLabel: '+ 미들웨어 추가' },
  model: { title: '모델', icon: '⚙', actionLabel: '' },
};
