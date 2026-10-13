import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ExcelPreviewGrid from './ExcelPreviewGrid';

// excel-preview Design §8.3 #11~12 — 렌더 구조·XSS
describe('ExcelPreviewGrid', () => {
  it('columns를 thead th로, rows를 tbody td로 렌더한다', () => {
    const { container } = render(
      <ExcelPreviewGrid
        columns={['지점', '매출']}
        rows={[
          ['서울', '1200'],
          ['부산', '900'],
        ]}
      />,
    );
    expect(container.querySelectorAll('thead th')).toHaveLength(2);
    expect(container.querySelectorAll('tbody tr')).toHaveLength(2);
    expect(container.querySelectorAll('tbody tr')[0].querySelectorAll('td')).toHaveLength(2);
    expect(screen.getByText('지점')).toBeInTheDocument();
    expect(screen.getByText('900')).toBeInTheDocument();
  });

  it('<script> 문자열 셀을 텍스트로만 렌더한다 (XSS, NFR)', () => {
    const payload = '<script>alert(1)</script>';
    const { container } = render(
      <ExcelPreviewGrid columns={['비고']} rows={[[payload]]} />,
    );
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText(payload)).toBeInTheDocument();
  });

  it('table 시맨틱을 사용한다 (접근성 NFR)', () => {
    render(<ExcelPreviewGrid columns={['a']} rows={[['1']]} />);
    expect(screen.getByRole('table')).toBeInTheDocument();
  });
});
