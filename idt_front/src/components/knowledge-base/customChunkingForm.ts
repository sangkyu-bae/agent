/**
 * 커스텀 청킹 폼 상태·검증·변환 유틸 (kb-custom-chunking Design §6.1)
 *
 * 검증 규칙은 백엔드 V-01~V-05와 동일 범위(클라이언트 1차 검증) —
 * 정규식은 JS RegExp 기준이라 최종 판정은 서버(Python re)가 한다.
 */
import type {
  ChunkingStrategy,
  CustomChunkingConfig,
} from '@/types/knowledgeBase';

export interface CustomBoundaryRuleForm {
  pattern: string;
  priority: string;
  level: 'parent' | 'child';
}

export interface CustomChunkingFormState {
  strategy: ChunkingStrategy;
  chunkSize: string;
  chunkOverlap: string;
  /** '' = 미지정(서버 기본값 사용) */
  parentChunkSize: string;
  /** '' = 미지정(서버 기본값 사용) */
  minChunkSize: string;
  rules: CustomBoundaryRuleForm[];
}

export const STRATEGY_OPTIONS: {
  value: ChunkingStrategy;
  label: string;
  description: string;
}[] = [
  {
    value: 'parent_child',
    label: 'Parent-Child',
    description: '큰 부모 청크 + 작은 자식 청크 2계층 (기본 방식과 동일 구조)',
  },
  {
    value: 'full_token',
    label: '고정 토큰',
    description: '문서를 일정 토큰 크기로 순차 분할',
  },
  {
    value: 'semantic',
    label: '시맨틱',
    description: '문장 의미 유사도 기반 분할 — 오버랩 미지원, 처리 비용 높음',
  },
  {
    value: 'section_aware',
    label: '섹션 인식',
    description: '마크다운 헤딩 등 섹션 경계를 우선해 분할',
  },
  {
    value: 'boundary_pattern',
    label: '경계 패턴 (정규식)',
    description: '사용자 정의 정규식 경계로 분할 (조항 청킹과 동일 엔진)',
  },
];

// 전략별 지원 필드 (백엔드 §3.2 금지 열과 일치)
export const supportsOverlap = (s: ChunkingStrategy) => s !== 'semantic';
export const supportsParentSize = (s: ChunkingStrategy) =>
  s === 'parent_child' || s === 'boundary_pattern';
export const supportsMinSize = (s: ChunkingStrategy) =>
  s === 'semantic' || s === 'section_aware';
export const supportsBoundaryRules = (s: ChunkingStrategy) =>
  s === 'boundary_pattern';

export const defaultCustomChunkingForm = (): CustomChunkingFormState => ({
  strategy: 'parent_child',
  chunkSize: '500',
  chunkOverlap: '50',
  parentChunkSize: '',
  minChunkSize: '',
  rules: [],
});

/** 전략 전환 시 미지원 필드 초기화 (Design §6.1) */
export const resetForStrategy = (
  form: CustomChunkingFormState,
  strategy: ChunkingStrategy,
): CustomChunkingFormState => ({
  ...form,
  strategy,
  chunkOverlap: supportsOverlap(strategy) ? form.chunkOverlap : '0',
  parentChunkSize: supportsParentSize(strategy) ? form.parentChunkSize : '',
  minChunkSize: supportsMinSize(strategy) ? form.minChunkSize : '',
  rules: supportsBoundaryRules(strategy) ? form.rules : [],
});

export const isValidRegex = (pattern: string): boolean => {
  try {
    new RegExp(pattern);
    return true;
  } catch {
    return false;
  }
};

const intOrNaN = (v: string): number => (v.trim() === '' ? NaN : Number(v));

/** 첫 번째 위반 메시지 반환, 유효하면 null */
export function validateCustomChunkingForm(
  form: CustomChunkingFormState,
): string | null {
  const size = intOrNaN(form.chunkSize);
  if (!Number.isInteger(size) || size < 100 || size > 4000) {
    return '청크 크기는 100~4000 사이여야 합니다';
  }
  const overlap = supportsOverlap(form.strategy)
    ? intOrNaN(form.chunkOverlap || '0')
    : 0;
  if (!Number.isInteger(overlap) || overlap < 0 || overlap > 500) {
    return '오버랩은 0~500 사이여야 합니다';
  }
  if (overlap >= size) return '오버랩은 청크 크기보다 작아야 합니다';
  return (
    validateOptionalSizes(form, size) ?? validateBoundaryRules(form)
  );
}

function validateOptionalSizes(
  form: CustomChunkingFormState,
  size: number,
): string | null {
  if (supportsParentSize(form.strategy) && form.parentChunkSize !== '') {
    const parent = intOrNaN(form.parentChunkSize);
    if (!Number.isInteger(parent) || parent < 100 || parent > 8000) {
      return '부모 청크 크기는 100~8000 사이여야 합니다';
    }
    if (size > parent) return '청크 크기는 부모 청크 크기 이하여야 합니다';
  }
  if (supportsMinSize(form.strategy) && form.minChunkSize !== '') {
    const min = intOrNaN(form.minChunkSize);
    if (!Number.isInteger(min) || min < 50 || min > 2000) {
      return '최소 청크 크기는 50~2000 사이여야 합니다';
    }
    if (min >= size) return '최소 청크 크기는 청크 크기보다 작아야 합니다';
  }
  return null;
}

function validateBoundaryRules(
  form: CustomChunkingFormState,
): string | null {
  if (!supportsBoundaryRules(form.strategy)) return null;
  if (form.rules.length === 0) return '경계 규칙을 1개 이상 추가해주세요';
  if (form.rules.length > 50) return '경계 규칙은 최대 50개입니다';
  if (!form.rules.some((r) => r.level === 'parent')) {
    return "'parent' 레벨 규칙이 1개 이상 필요합니다";
  }
  for (const rule of form.rules) {
    if (!rule.pattern.trim()) return '비어있는 정규식 패턴이 있습니다';
    if (rule.pattern.length > 200) {
      return '정규식 패턴은 200자 이내여야 합니다';
    }
    if (!isValidRegex(rule.pattern)) {
      return `잘못된 정규식: ${rule.pattern}`;
    }
  }
  return null;
}

/** 폼 → API config. 미지정 optional은 생략(서버 기본값) */
export function buildCustomChunkingConfig(
  form: CustomChunkingFormState,
): CustomChunkingConfig {
  const config: CustomChunkingConfig = {
    version: 1,
    strategy: form.strategy,
    chunk_size: Number(form.chunkSize),
    chunk_overlap: supportsOverlap(form.strategy)
      ? Number(form.chunkOverlap || '0')
      : 0,
  };
  if (supportsParentSize(form.strategy) && form.parentChunkSize !== '') {
    config.parent_chunk_size = Number(form.parentChunkSize);
  }
  if (supportsMinSize(form.strategy) && form.minChunkSize !== '') {
    config.min_chunk_size = Number(form.minChunkSize);
  }
  if (supportsBoundaryRules(form.strategy)) {
    config.boundary_rules = form.rules.map((r) => ({
      pattern: r.pattern,
      priority: Number(r.priority || '1'),
      level: r.level,
    }));
  }
  return config;
}

/** 저장된 config → 폼 프리필 (설정 수정 모달용) */
export function formFromConfig(
  config: CustomChunkingConfig | null | undefined,
): CustomChunkingFormState {
  if (!config) return defaultCustomChunkingForm();
  return {
    strategy: config.strategy,
    chunkSize: String(config.chunk_size),
    chunkOverlap: String(config.chunk_overlap ?? 0),
    parentChunkSize:
      config.parent_chunk_size != null
        ? String(config.parent_chunk_size)
        : '',
    minChunkSize:
      config.min_chunk_size != null ? String(config.min_chunk_size) : '',
    rules: (config.boundary_rules ?? []).map((r) => ({
      pattern: r.pattern,
      priority: String(r.priority),
      level: r.level,
    })),
  };
}
