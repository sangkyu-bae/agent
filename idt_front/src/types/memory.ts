// agent-memory: 사용자 메모리 타입.
// Mirror to backend src/application/memory/api_schemas.py.

export type MemoryType = 'profile' | 'preference' | 'domain_term' | 'episode';

/** 타입별 한국어 라벨 — 백엔드 주입 블록 라벨과 동일 체계 */
export const MEMORY_TYPE_LABELS: Record<MemoryType, string> = {
  profile: '프로필',
  domain_term: '용어',
  preference: '선호',
  episode: '참고',
};

/** content 최대 길이 — 백엔드 MemoryPolicy.CONTENT_MAX와 동기 */
export const MEMORY_CONTENT_MAX = 500;

export interface Memory {
  id: number;
  mem_type: MemoryType;
  content: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface MemoryListResponse {
  items: Memory[];
  total: number;
  max_count: number;
}

export interface CreateMemoryRequest {
  mem_type: MemoryType;
  content: string;
}

export interface UpdateMemoryRequest {
  mem_type?: MemoryType;
  content?: string;
}
