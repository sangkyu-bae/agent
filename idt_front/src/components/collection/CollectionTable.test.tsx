import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import CollectionTable from './CollectionTable';
import type { CollectionInfo } from '@/types/collection';

const renderWithRouter = (ui: React.ReactElement) =>
  render(<MemoryRouter>{ui}</MemoryRouter>);

const baseProps = {
  isLoading: false,
  isError: false,
  currentUserId: 10,
  currentUserRole: 'user',
  onRefresh: vi.fn(),
  onCreate: vi.fn(),
  onRename: vi.fn(),
  onDelete: vi.fn(),
  onUpdateScope: vi.fn(),
};

const mockCollections: CollectionInfo[] = [
  { name: 'my-docs', vectors_count: 100, points_count: 100, status: 'green', scope: 'PERSONAL', owner_id: 10 },
  { name: 'dept-docs', vectors_count: 50, points_count: 50, status: 'green', scope: 'DEPARTMENT', owner_id: 10 },
  { name: 'public-docs', vectors_count: 200, points_count: 200, status: 'green', scope: 'PUBLIC', owner_id: 99 },
];

describe('CollectionTable — Scope 배지', () => {
  it('PERSONAL scope는 "개인" 배지를 표시한다', () => {
    renderWithRouter(<CollectionTable {...baseProps} collections={[mockCollections[0]]} />);
    expect(screen.getByText('개인')).toBeInTheDocument();
  });

  it('DEPARTMENT scope는 "부서" 배지를 표시한다', () => {
    renderWithRouter(<CollectionTable {...baseProps} collections={[mockCollections[1]]} />);
    expect(screen.getByText('부서')).toBeInTheDocument();
  });

  it('PUBLIC scope는 "공개" 배지를 표시한다', () => {
    renderWithRouter(<CollectionTable {...baseProps} collections={[mockCollections[2]]} />);
    expect(screen.getByText('공개')).toBeInTheDocument();
  });

  it('scope 미설정(legacy) 컬렉션은 대시(—)를 표시한다', () => {
    const legacy: CollectionInfo = {
      name: 'legacy-col',
      vectors_count: 10,
      points_count: 10,
      status: 'green',
    };
    renderWithRouter(<CollectionTable {...baseProps} collections={[legacy]} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});

describe('CollectionTable — canManage 액션 버튼', () => {
  it('소유자(owner_id 일치)인 컬렉션에 이름변경/권한변경/삭제 버튼이 표시된다', () => {
    renderWithRouter(<CollectionTable {...baseProps} collections={[mockCollections[0]]} />);
    expect(screen.getByText('이름변경')).toBeInTheDocument();
    expect(screen.getByText('권한변경')).toBeInTheDocument();
    expect(screen.getByText('삭제')).toBeInTheDocument();
  });

  it('소유자가 아닌 컬렉션에 액션 버튼이 표시되지 않는다', () => {
    renderWithRouter(<CollectionTable {...baseProps} collections={[mockCollections[2]]} />);
    expect(screen.queryByText('이름변경')).not.toBeInTheDocument();
    expect(screen.queryByText('권한변경')).not.toBeInTheDocument();
    expect(screen.queryByText('삭제')).not.toBeInTheDocument();
  });

  it('admin 역할이면 소유자가 아니어도 액션 버튼이 표시된다', () => {
    renderWithRouter(
      <CollectionTable
        {...baseProps}
        currentUserRole="admin"
        collections={[mockCollections[2]]}
      />,
    );
    expect(screen.getByText('이름변경')).toBeInTheDocument();
    expect(screen.getByText('권한변경')).toBeInTheDocument();
    expect(screen.getByText('삭제')).toBeInTheDocument();
  });

  it('보호된 컬렉션(documents)은 "보호됨" 뱃지를 표시한다', () => {
    const protectedCol: CollectionInfo = {
      name: 'documents',
      vectors_count: 150,
      points_count: 150,
      status: 'green',
      scope: 'PUBLIC',
      owner_id: 10,
    };
    renderWithRouter(<CollectionTable {...baseProps} collections={[protectedCol]} />);
    expect(screen.getByText('보호됨')).toBeInTheDocument();
    expect(screen.queryByText('삭제')).not.toBeInTheDocument();
  });

  it('권한변경 버튼 클릭 시 onUpdateScope이 호출된다', async () => {
    const user = userEvent.setup();
    const onUpdateScope = vi.fn();
    renderWithRouter(
      <CollectionTable
        {...baseProps}
        onUpdateScope={onUpdateScope}
        collections={[mockCollections[0]]}
      />,
    );
    await user.click(screen.getByText('권한변경'));
    expect(onUpdateScope).toHaveBeenCalledWith('my-docs');
  });
});
