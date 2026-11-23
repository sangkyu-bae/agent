// document-revision §4.2 — 개정 관련 서비스 호출 계약.
// MSW 핸들러에서 request.formData() 를 읽지 않는다(멈춤 함정) → axios 호출 인자를 직접 검사한다.
import { afterEach, describe, expect, it, vi } from 'vitest';
import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import knowledgeBaseService from './knowledgeBaseService';

afterEach(() => vi.restoreAllMocks());

const formOf = (spy: ReturnType<typeof vi.spyOn>) =>
  spy.mock.calls[0][1] as FormData;

describe('knowledgeBaseService — document-revision', () => {
  it('uploadKbDocument 는 개정 입력을 Form 필드로 보낸다', async () => {
    const spy = vi
      .spyOn(authApiClient, 'post')
      .mockResolvedValue({ data: { document_id: 'new' } });
    const file = new File(['x'], '규정_v3.pdf');

    await knowledgeBaseService.uploadKbDocument('kb-1', file, {
      supersedesDocumentId: 'v2',
      versionLabel: '2026-11 개정',
      effectiveDate: '2026-12-01',
      revisionCheckId: 'chk',
    });

    expect(spy.mock.calls[0][0]).toBe(API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS('kb-1'));
    const form = formOf(spy);
    expect(form.get('file')).toBe(file);
    expect(form.get('supersedes_document_id')).toBe('v2');
    expect(form.get('version_label')).toBe('2026-11 개정');
    expect(form.get('effective_date')).toBe('2026-12-01');
    expect(form.get('revision_check_id')).toBe('chk');
  });

  it('uploadKbDocument 는 개정 입력이 없으면 file 만 보낸다 (quick setup 호환)', async () => {
    const spy = vi
      .spyOn(authApiClient, 'post')
      .mockResolvedValue({ data: {} });
    await knowledgeBaseService.uploadKbDocument('kb-1', new File(['x'], 'a.pdf'), {
      supersedesDocumentId: '',
      versionLabel: null,
    });
    const keys = [...formOf(spy).keys()];
    expect(keys).toEqual(['file']);
  });

  it('checkKbRevision 은 점검 엔드포인트에 파일을 보낸다', async () => {
    const spy = vi
      .spyOn(authApiClient, 'post')
      .mockResolvedValue({ data: { check_id: 'chk', verdict: 'new' } });
    const file = new File(['x'], 'a.pdf');
    const res = await knowledgeBaseService.checkKbRevision('kb-1', file);
    expect(spy.mock.calls[0][0]).toBe(
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_CHECK('kb-1'),
    );
    expect(formOf(spy).get('file')).toBe(file);
    expect(res.check_id).toBe('chk');
  });

  it('deleteKbDocument 는 restore_previous 를 쿼리로 넘긴다', async () => {
    const spy = vi
      .spyOn(authApiClient, 'delete')
      .mockResolvedValue({ data: {} });
    await knowledgeBaseService.deleteKbDocument('kb-1', 'd', {
      restorePrevious: false,
    });
    expect(spy.mock.calls[0][1]).toEqual({ params: { restore_previous: false } });
  });

  it('deleteKbDocument 는 옵션이 없으면 서버 기본값(true)을 따른다', async () => {
    const spy = vi
      .spyOn(authApiClient, 'delete')
      .mockResolvedValue({ data: {} });
    await knowledgeBaseService.deleteKbDocument('kb-1', 'd');
    expect(spy.mock.calls[0][1]).toEqual({ params: undefined });
  });

  it('개정 관리 API 경로·본문', async () => {
    const post = vi.spyOn(authApiClient, 'post').mockResolvedValue({ data: {} });
    const patch = vi.spyOn(authApiClient, 'patch').mockResolvedValue({ data: {} });
    const get = vi.spyOn(authApiClient, 'get').mockResolvedValue({ data: {} });

    await knowledgeBaseService.getDocumentVersions('kb-1', 'd');
    await knowledgeBaseService.rollbackRevision('kb-1', 'd', 'detach');
    await knowledgeBaseService.linkRevision('kb-1', 'n', 'o');
    await knowledgeBaseService.updateRevisionMeta('kb-1', 'd', {
      version_label: 'L',
      effective_date: null,
    });
    await knowledgeBaseService.retryRevisionSync('kb-1', 'd');
    await knowledgeBaseService.updateRevisionMode('kb-1', 'suggest');

    expect(get.mock.calls[0][0]).toBe(
      API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_VERSIONS('kb-1', 'd'),
    );
    expect(post.mock.calls[0]).toEqual([
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_ROLLBACK('kb-1', 'd'),
      { mode: 'detach' },
    ]);
    expect(post.mock.calls[1]).toEqual([
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_LINK('kb-1', 'n'),
      { supersedes_document_id: 'o' },
    ]);
    expect(patch.mock.calls[0]).toEqual([
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_META('kb-1', 'd'),
      { version_label: 'L', effective_date: null },
    ]);
    expect(post.mock.calls[2][0]).toBe(
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_SYNC('kb-1', 'd'),
    );
    expect(patch.mock.calls[1]).toEqual([
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_MODE('kb-1'),
      { revision_mode: 'suggest' },
    ]);
  });
});
