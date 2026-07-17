import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  beforeAll,
  afterEach,
  afterAll,
  describe,
  it,
  expect,
  vi,
} from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import KbUploadDocumentModal from './KbUploadDocumentModal';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderModal = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <KbUploadDocumentModal
        isOpen
        onClose={vi.fn()}
        kbId="kb-1"
        kbName="여신 규정집"
      />
    </QueryClientProvider>,
  );
};

describe('KbUploadDocumentModal', () => {
  it('파일 입력이 PDF와 엑셀 확장자를 허용한다 (kb-excel-upload D10)', () => {
    renderModal();
    const input = screen.getByLabelText('업로드할 문서 파일');
    expect(input).toHaveAttribute('accept', '.pdf,.xlsx,.xls');
  });

  it('지원 형식 안내 문구를 표시한다', () => {
    renderModal();
    expect(screen.getByText(/지원 형식: PDF, 엑셀/)).toBeInTheDocument();
  });

  it('업로드 실패(422) 시 서버 detail 메시지를 표시한다', async () => {
    server.use(
      http.post('*/api/v1/knowledge-bases/kb-1/documents', () =>
        HttpResponse.json(
          {
            detail:
              "Sheet '대량' in '한도표.xlsx' has 30000 rows, exceeds limit 20000. Split the file and retry",
          },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderModal();
    const input = screen.getByLabelText('업로드할 문서 파일');
    await user.upload(
      input,
      new File(['x'], '한도표.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }),
    );
    await user.click(screen.getByRole('button', { name: '업로드' }));
    await waitFor(() => {
      expect(screen.getByText(/exceeds limit 20000/)).toBeInTheDocument();
    });
  });
});
