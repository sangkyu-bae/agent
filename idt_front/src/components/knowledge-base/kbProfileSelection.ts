/**
 * 청킹 프로파일 선택 판단 (kb-profile-selector Design §3)
 *
 * 폴백 순서와 크기 우선순위는 백엔드 chunking_resolver.py와 동일하다.
 * 모달·카드·저장 로직이 이 결과만 사용해 표시와 저장 값을 일치시킨다.
 */
import type { ChunkingProfile } from '@/types/chunkingProfile';

export interface KbProfileSelection {
  isListReady: boolean;
  effectiveId: string | null;
  isStale: boolean;
  defaultProfile: ChunkingProfile | null;
  appliedProfile: ChunkingProfile | null;
  usesLegacyFallback: boolean;
}

export interface EffectiveProfileSizes {
  parentChunkSize: number;
  chunkSize: number;
  chunkOverlap: number;
}

/** profiles는 조회 성공 시에만 넘긴다. undefined면 삭제로 판단하지 않는다 (FR-09) */
export const resolveProfileSelection = (
  selectedId: string | null,
  profiles: ChunkingProfile[] | undefined,
): KbProfileSelection => {
  if (!profiles) {
    return {
      isListReady: false,
      effectiveId: selectedId,
      isStale: false,
      defaultProfile: null,
      appliedProfile: null,
      usesLegacyFallback: false,
    };
  }
  const selected =
    profiles.find((profile) => profile.profile_id === selectedId) ?? null;
  const defaultProfile = profiles.find((profile) => profile.is_default) ?? null;
  const appliedProfile = selected ?? defaultProfile;
  return {
    isListReady: true,
    effectiveId: selected?.profile_id ?? null,
    isStale: selectedId !== null && selected === null,
    defaultProfile,
    appliedProfile,
    usesLegacyFallback: appliedProfile === null,
  };
};

export const effectiveProfileSizes = (
  profile: ChunkingProfile,
  kbChunkSize: number | null | undefined,
  kbChunkOverlap: number | null | undefined,
): EffectiveProfileSizes => ({
  parentChunkSize: profile.parent_chunk_size,
  chunkSize: kbChunkSize || profile.chunk_size,
  chunkOverlap: kbChunkOverlap ?? profile.chunk_overlap,
});

export const clauseProfileSummary = (selection: KbProfileSelection): string => {
  if (!selection.isListReady) return '조항 단위 청킹 (프로파일 기반)';
  if (selection.usesLegacyFallback) {
    return '조항 단위 청킹 — 프로파일 없음, 기본 청킹으로 처리';
  }
  const name = selection.appliedProfile?.name;
  if (selection.isStale) {
    return `조항 단위 청킹 — 삭제된 프로파일, 기본 프로파일 (${name}) 적용`;
  }
  if (selection.effectiveId === null) {
    return `조항 단위 청킹 — 기본 프로파일 (${name})`;
  }
  return `조항 단위 청킹 — ${name}`;
};
