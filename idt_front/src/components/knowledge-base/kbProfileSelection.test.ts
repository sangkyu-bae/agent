/**
 * 프로파일 선택 판단 테스트 (kb-profile-selector Design §3)
 */
import { describe, expect, it } from 'vitest';
import type { ChunkingProfile } from '@/types/chunkingProfile';
import {
  clauseProfileSummary,
  effectiveProfileSizes,
  resolveProfileSelection,
} from './kbProfileSelection';

const makeProfile = (
  profile_id: string,
  overrides: Partial<ChunkingProfile> = {},
): ChunkingProfile => ({
  profile_id,
  name: profile_id,
  description: null,
  boundary_rules: [],
  parent_chunk_size: 2000,
  chunk_size: 500,
  chunk_overlap: 50,
  is_default: false,
  summary_llm_model_id: null,
  created_at: null,
  updated_at: null,
  ...overrides,
});

const defaultProfile = makeProfile('default', { is_default: true });
const contract = makeProfile('contract');

describe('resolveProfileSelection', () => {
  it('U1: 목록이 없으면 판단하지 않고 지정 ID를 유지한다', () => {
    expect(resolveProfileSelection('contract', undefined)).toEqual({
      isListReady: false,
      effectiveId: 'contract',
      isStale: false,
      defaultProfile: null,
      appliedProfile: null,
      usesLegacyFallback: false,
    });
  });

  it('U2: 지정 ID가 목록에 있으면 그 프로파일을 적용한다', () => {
    const result = resolveProfileSelection('contract', [
      defaultProfile,
      contract,
    ]);
    expect(result).toMatchObject({
      isListReady: true,
      effectiveId: 'contract',
      isStale: false,
      appliedProfile: contract,
      usesLegacyFallback: false,
    });
  });

  it('U3: 미지정이면 기본 프로파일을 적용한다', () => {
    const result = resolveProfileSelection(null, [defaultProfile, contract]);
    expect(result).toMatchObject({
      effectiveId: null,
      isStale: false,
      defaultProfile,
      appliedProfile: defaultProfile,
      usesLegacyFallback: false,
    });
  });

  it('U4: 지정 ID가 목록에 없으면 삭제로 보고 기본 프로파일을 적용한다', () => {
    const result = resolveProfileSelection('deleted', [defaultProfile]);
    expect(result).toMatchObject({
      effectiveId: null,
      isStale: true,
      appliedProfile: defaultProfile,
      usesLegacyFallback: false,
    });
  });

  it('U5: 미지정이고 기본 프로파일이 없으면 기본 청킹으로 처리된다', () => {
    const result = resolveProfileSelection(null, [contract]);
    expect(result).toMatchObject({
      effectiveId: null,
      isStale: false,
      appliedProfile: null,
      usesLegacyFallback: true,
    });
  });

  it('U6: 삭제됐고 기본 프로파일도 없으면 기본 청킹으로 처리된다', () => {
    const result = resolveProfileSelection('deleted', []);
    expect(result).toMatchObject({
      effectiveId: null,
      isStale: true,
      appliedProfile: null,
      usesLegacyFallback: true,
    });
  });
});

describe('effectiveProfileSizes', () => {
  it('U7: 오버라이드가 없으면 프로파일 크기를 쓴다', () => {
    expect(effectiveProfileSizes(contract, null, null)).toEqual({
      parentChunkSize: 2000,
      chunkSize: 500,
      chunkOverlap: 50,
    });
  });

  it('U8: chunk_size 오버라이드가 있으면 KB 값을 쓴다', () => {
    expect(effectiveProfileSizes(contract, 700, null).chunkSize).toBe(700);
  });

  it('U9: chunk_overlap 오버라이드 0을 유지한다', () => {
    expect(effectiveProfileSizes(contract, null, 0).chunkOverlap).toBe(0);
  });
});

describe('clauseProfileSummary', () => {
  it('U10: 상태별 카드 문구를 만든다', () => {
    const named = makeProfile('contract', { name: '계약서' });
    const fallback = makeProfile('default', {
      name: '금융 조항',
      is_default: true,
    });

    expect(clauseProfileSummary(resolveProfileSelection('x', undefined))).toBe(
      '조항 단위 청킹 (프로파일 기반)',
    );
    expect(
      clauseProfileSummary(resolveProfileSelection('contract', [named])),
    ).toBe('조항 단위 청킹 — 계약서');
    expect(
      clauseProfileSummary(resolveProfileSelection(null, [fallback])),
    ).toBe('조항 단위 청킹 — 기본 프로파일 (금융 조항)');
    expect(
      clauseProfileSummary(resolveProfileSelection('deleted', [fallback])),
    ).toBe('조항 단위 청킹 — 삭제된 프로파일, 기본 프로파일 (금융 조항) 적용');
    expect(clauseProfileSummary(resolveProfileSelection(null, []))).toBe(
      '조항 단위 청킹 — 프로파일 없음, 기본 청킹으로 처리',
    );
  });
});
