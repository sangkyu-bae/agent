// chunking-profile-admin-ui: 관리자 청킹 프로파일 타입
// 계약 원본: idt/src/api/routes/admin_chunking_router.py

export type BoundaryRuleLevel = 'parent' | 'child';

export interface BoundaryRule {
  pattern: string;
  priority: number;
  level: BoundaryRuleLevel;
}

export interface ChunkingProfile {
  profile_id: string;
  name: string;
  description: string | null;
  boundary_rules: BoundaryRule[];
  parent_chunk_size: number;
  chunk_size: number;
  chunk_overlap: number;
  is_default: boolean;
  // 섹션 요약 LLM (card-section-summary D2) — null이면 요약 비활성
  summary_llm_model_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** 생성(POST)/수정(PUT) 공용 바디 — PUT은 전체 교체이므로 모든 필드 필수 전송 */
export interface ChunkingProfileRequest {
  name: string;
  description: string | null;
  boundary_rules: BoundaryRule[];
  parent_chunk_size: number;
  chunk_size: number;
  chunk_overlap: number;
  is_default: boolean;
  summary_llm_model_id: string | null;
}

export interface ChunkingProfileListResponse {
  profiles: ChunkingProfile[];
  total: number;
}

export interface ChunkingProfileMessageResponse {
  profile_id: string;
  message: string;
}
