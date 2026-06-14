import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import MarkdownRenderer from './MarkdownRenderer';

// chat-markdown-rendering Design §6 — 10케이스
describe('MarkdownRenderer', () => {
  it('1. 헤딩(###)을 h3로 렌더한다', () => {
    render(<MarkdownRenderer content={'### 분석 결과'} />);
    expect(screen.getByRole('heading', { level: 3, name: '분석 결과' })).toBeInTheDocument();
  });

  it('2. 굵게/기울임을 strong/em으로 렌더한다', () => {
    const { container } = render(<MarkdownRenderer content={'**굵게** 그리고 *기울임*'} />);
    expect(container.querySelector('strong')).toHaveTextContent('굵게');
    expect(container.querySelector('em')).toHaveTextContent('기울임');
  });

  it('3. 비순서/순서 목록을 ul/ol로 렌더한다', () => {
    const { container } = render(
      <MarkdownRenderer content={'- 항목1\n- 항목2\n\n1. 첫째\n2. 둘째'} />,
    );
    expect(container.querySelector('ul')).not.toBeNull();
    expect(container.querySelector('ol')).not.toBeNull();
    expect(screen.getByText('항목1')).toBeInTheDocument();
    expect(screen.getByText('둘째')).toBeInTheDocument();
  });

  it('4. GFM 표를 table로 렌더하고 overflow 래퍼로 감싼다', () => {
    const md = '| 항목 | 값 |\n|------|-----|\n| 매출 | 100 |';
    const { container } = render(<MarkdownRenderer content={md} />);
    const table = container.querySelector('table');
    expect(table).not.toBeNull();
    expect(table?.parentElement?.className).toContain('overflow-x-auto');
    expect(screen.getByText('매출')).toBeInTheDocument();
  });

  it('5. 펜스 코드블록을 pre > code로 렌더한다', () => {
    const md = '```python\nprint("hello")\n```';
    const { container } = render(<MarkdownRenderer content={md} />);
    expect(container.querySelector('pre > code')).toHaveTextContent('print("hello")');
  });

  it('6. 인라인 코드를 pre 외부 code로 렌더한다', () => {
    const { container } = render(<MarkdownRenderer content={'변수 `top_k` 를 설정'} />);
    const code = container.querySelector('code');
    expect(code).toHaveTextContent('top_k');
    expect(code?.closest('pre')).toBeNull();
  });

  it('7. 링크에 target=_blank rel=noopener noreferrer를 적용한다', () => {
    render(<MarkdownRenderer content={'[문서](https://example.com)'} />);
    const link = screen.getByRole('link', { name: '문서' });
    expect(link).toHaveAttribute('href', 'https://example.com');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('8. raw HTML을 실행하지 않고 텍스트로 이스케이프한다 (XSS)', () => {
    const { container } = render(
      <MarkdownRenderer content={'<script>alert(1)</script> 안전한 텍스트'} />,
    );
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).toContain('안전한 텍스트');
  });

  it('9. 단일 개행을 줄바꿈(br)으로 보존한다 (remark-breaks)', () => {
    const { container } = render(<MarkdownRenderer content={'첫째 줄\n둘째 줄'} />);
    expect(container.querySelector('br')).not.toBeNull();
  });

  it('10. 닫히지 않은 코드펜스 입력에도 크래시 없이 렌더한다 (스트리밍 안정성)', () => {
    const md = '결과는 다음과 같습니다:\n```sql\nSELECT *';
    expect(() => render(<MarkdownRenderer content={md} />)).not.toThrow();
  });
});
