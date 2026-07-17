import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { chunkingProfileService } from './chunkingProfileService';
import type {
  ChunkingProfile,
  ChunkingProfileRequest,
} from '@/types/chunkingProfile';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const profile: ChunkingProfile = {
  profile_id: 'prof-1',
  name: '금융 조항 기본',
  description: '조 단위 분할',
  boundary_rules: [
    { pattern: '^제\\s*\\d+\\s*장', priority: 1, level: 'parent' },
    { pattern: '^제\\s*\\d+\\s*조', priority: 1, level: 'child' },
  ],
  parent_chunk_size: 2000,
  chunk_size: 500,
  chunk_overlap: 50,
  is_default: true,
  summary_llm_model_id: 'uuid-1',
  created_at: '2026-07-01T00:00:00',
  updated_at: '2026-07-10T00:00:00',
};

const request: ChunkingProfileRequest = {
  name: profile.name,
  description: profile.description,
  boundary_rules: profile.boundary_rules,
  parent_chunk_size: 2000,
  chunk_size: 500,
  chunk_overlap: 50,
  is_default: true,
  summary_llm_model_id: 'uuid-1',
};

describe('chunkingProfileService', () => {
  it('S1: list — GET /admin/chunking/profiles 응답의 profiles를 반환한다', async () => {
    server.use(
      http.get('*/api/v1/admin/chunking/profiles', () =>
        HttpResponse.json({ profiles: [profile], total: 1 }),
      ),
    );
    const result = await chunkingProfileService.getChunkingProfiles();
    expect(result.total).toBe(1);
    expect(result.profiles[0].profile_id).toBe('prof-1');
  });

  it('S2: create — POST 바디에 전체 필드(summary_llm_model_id 포함)를 전송한다', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/admin/chunking/profiles', async ({ request: req }) => {
        captured = (await req.json()) as Record<string, unknown>;
        return HttpResponse.json(profile, { status: 201 });
      }),
    );
    await chunkingProfileService.createChunkingProfile({
      ...request,
      summary_llm_model_id: null,
    });
    expect(captured).toMatchObject({
      name: '금융 조항 기본',
      parent_chunk_size: 2000,
      chunk_size: 500,
      chunk_overlap: 50,
      is_default: true,
      summary_llm_model_id: null,
    });
    expect(
      (captured as unknown as Record<string, unknown>).boundary_rules,
    ).toHaveLength(2);
  });

  it('S3: update — PUT 전체 교체 바디에 모든 필드를 포함한다 (D2 회귀 가드)', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.put('*/api/v1/admin/chunking/profiles/:id', async ({ params, request: req }) => {
        captured = (await req.json()) as Record<string, unknown>;
        expect(params.id).toBe('prof-1');
        return HttpResponse.json(profile);
      }),
    );
    await chunkingProfileService.updateChunkingProfile('prof-1', request);
    const keys = Object.keys(captured as unknown as Record<string, unknown>);
    expect(keys).toEqual(
      expect.arrayContaining([
        'name',
        'description',
        'boundary_rules',
        'parent_chunk_size',
        'chunk_size',
        'chunk_overlap',
        'is_default',
        'summary_llm_model_id',
      ]),
    );
  });

  it('S4: setDefault — PUT /profiles/{id}/default를 호출한다', async () => {
    let calledId: string | null = null;
    server.use(
      http.put('*/api/v1/admin/chunking/profiles/:id/default', ({ params }) => {
        calledId = params.id as string;
        return HttpResponse.json({
          profile_id: params.id,
          message: 'Default profile updated',
        });
      }),
    );
    await chunkingProfileService.setDefaultChunkingProfile('prof-2');
    expect(calledId).toBe('prof-2');
  });

  it('S5: remove — DELETE /profiles/{id}를 호출한다', async () => {
    let calledId: string | null = null;
    server.use(
      http.delete('*/api/v1/admin/chunking/profiles/:id', ({ params }) => {
        calledId = params.id as string;
        return HttpResponse.json({
          profile_id: params.id,
          message: 'Chunking profile deleted',
        });
      }),
    );
    await chunkingProfileService.deleteChunkingProfile('prof-1');
    expect(calledId).toBe('prof-1');
  });
});
