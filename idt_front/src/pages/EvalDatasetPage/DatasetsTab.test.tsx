// eval-hub: 데이터셋 탭 — 목록·생성 3방식(수동/파일/문서 draft 검토)
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import DatasetsTab from './DatasetsTab';

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const emptyPage = { items: [], total: 0, limit: 20, offset: 0 };

const testset = {
  id: 'ts-1',
  name: '여신 QA셋',
  description: '여신 규정 QA',
  case_count: 2,
  created_at: '2026-08-01T00:00:00Z',
  user_id: '1',
};

const renderTab = () => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <DatasetsTab />
    </Wrapper>,
  );
};

describe('데이터셋 탭', () => {
  it('빈 상태 → 생성 유도 버튼', async () => {
    server.use(
      http.get('*/api/ragas/testsets', () => HttpResponse.json(emptyPage)),
    );
    renderTab();
    expect(
      await screen.findByText('사용 가능한 데이터셋이 없습니다.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('+ 시작하려면 첫 번째 데이터셋을 생성하세요.'),
    ).toBeInTheDocument();
  });

  it('목록 표시 + 클릭 시 QA 상세', async () => {
    server.use(
      http.get('*/api/ragas/testsets', () =>
        HttpResponse.json({ ...emptyPage, items: [testset], total: 1 }),
      ),
      http.get('*/api/ragas/testsets/ts-1', () =>
        HttpResponse.json({
          ...testset,
          cases: [
            { question: '한도 기준은?', ground_truth: '담보 가치 기준' },
            { question: '연체 이자율은?', ground_truth: null },
          ],
        }),
      ),
    );
    renderTab();
    await userEvent.click(await screen.findByText('여신 QA셋'));
    expect(await screen.findByText('한도 기준은?')).toBeInTheDocument();
    expect(screen.getByText('담보 가치 기준')).toBeInTheDocument();
  });

  it('수동 입력 생성 — POST 페이로드에 유효 QA만 포함', async () => {
    let payload: unknown = null;
    server.use(
      http.get('*/api/ragas/testsets', () => HttpResponse.json(emptyPage)),
      http.post('*/api/ragas/testsets', async ({ request }) => {
        payload = await request.json();
        return HttpResponse.json({ ...testset, id: 'ts-new' }, { status: 201 });
      }),
    );
    renderTab();
    await userEvent.click(await screen.findByText('+ 데이터셋 생성'));
    await userEvent.type(screen.getByLabelText('데이터셋 이름'), '수동셋');
    await userEvent.type(screen.getByLabelText('질문 1'), '질문입니다');
    await userEvent.type(screen.getByLabelText('정답 1'), '정답입니다');
    await userEvent.click(screen.getByRole('button', { name: '데이터셋 저장' }));

    await waitFor(() => expect(payload).not.toBeNull());
    expect(payload).toEqual({
      name: '수동셋',
      description: '',
      cases: [{ question: '질문입니다', ground_truth: '정답입니다' }],
    });
  });

  it('이름 없이 저장하면 인라인 에러', async () => {
    server.use(
      http.get('*/api/ragas/testsets', () => HttpResponse.json(emptyPage)),
    );
    renderTab();
    await userEvent.click(await screen.findByText('+ 데이터셋 생성'));
    await userEvent.click(screen.getByRole('button', { name: '데이터셋 저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '데이터셋 이름을 입력하세요.',
    );
  });

  it('파일 업로드 생성 — multipart 전송 후 목록 재조회', async () => {
    let uploadedName: string | null = null;
    let listCalls = 0;
    server.use(
      http.get('*/api/ragas/testsets', () => {
        listCalls += 1;
        return HttpResponse.json(emptyPage);
      }),
      http.post('*/api/ragas/testsets/upload', async ({ request }) => {
        const form = await request.formData();
        uploadedName = form.get('name') as string;
        return HttpResponse.json({ ...testset, id: 'ts-up' }, { status: 201 });
      }),
    );
    renderTab();
    await userEvent.click(await screen.findByText('+ 데이터셋 생성'));
    await userEvent.click(screen.getByRole('button', { name: '파일 업로드' }));
    await userEvent.type(screen.getByLabelText('데이터셋 이름'), '업로드셋');

    const csv = new File(['question,ground_truth\nq,a\n'], 'qa.csv', {
      type: 'text/csv',
    });
    await userEvent.upload(screen.getByLabelText('파일 선택'), csv);
    const before = listCalls;
    await userEvent.click(screen.getByRole('button', { name: '데이터셋 저장' }));

    await waitFor(() => expect(uploadedName).toBe('업로드셋'));
    await waitFor(() => expect(listCalls).toBeGreaterThan(before)); // invalidate 재조회
  });

  it('문서에서 생성 — draft를 편집기에 프리필 후 저장해야 서버 반영', async () => {
    let saved: unknown = null;
    server.use(
      http.get('*/api/ragas/testsets', () => HttpResponse.json(emptyPage)),
      http.post('*/api/ragas/testsets/generate', () =>
        HttpResponse.json({
          source_filename: 'policy.pdf',
          items: [{ question: '생성된 질문', ground_truth: '생성된 정답' }],
        }),
      ),
      http.post('*/api/ragas/testsets', async ({ request }) => {
        saved = await request.json();
        return HttpResponse.json({ ...testset, id: 'ts-gen' }, { status: 201 });
      }),
    );
    renderTab();
    await userEvent.click(await screen.findByText('+ 데이터셋 생성'));
    await userEvent.click(screen.getByRole('button', { name: '문서에서 생성' }));

    const file = new File(['pdf'], 'policy.pdf', { type: 'application/pdf' });
    await userEvent.upload(screen.getByLabelText('파일 선택'), file);
    await userEvent.click(screen.getByRole('button', { name: '초안 생성' }));

    // draft 프리필 확인 (아직 저장 안 됨)
    expect(await screen.findByDisplayValue('생성된 질문')).toBeInTheDocument();
    expect(saved).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: '데이터셋 저장' }));
    await waitFor(() => expect(saved).not.toBeNull());
    expect(saved).toMatchObject({
      name: 'policy',
      cases: [{ question: '생성된 질문', ground_truth: '생성된 정답' }],
    });
  });
});
