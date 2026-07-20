import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import HealthBadges from './HealthBadges';
import type { HealthComponent } from '@/types/adminDashboard';

const okComponent: HealthComponent = {
  name: 'mysql',
  status: 'ok',
  latency_ms: 7,
  error: null,
};

const failComponent: HealthComponent = {
  name: 'elasticsearch',
  status: 'fail',
  latency_ms: null,
  error: 'connection refused',
};

describe('HealthBadges', () => {
  it('ok 컴포넌트는 라벨과 응답시간 표시', () => {
    render(<HealthBadges components={[okComponent]} />);
    expect(screen.getByText('MySQL')).toBeInTheDocument();
    expect(screen.getByText('7ms')).toBeInTheDocument();
  });

  it('fail 컴포넌트는 에러 문자열 표시', () => {
    render(<HealthBadges components={[failComponent]} />);
    expect(screen.getByText('Elasticsearch')).toBeInTheDocument();
    expect(screen.getByText('connection refused')).toBeInTheDocument();
  });

  it('로딩 중에는 배지 미표시', () => {
    render(<HealthBadges components={undefined} loading />);
    expect(screen.queryByText('MySQL')).not.toBeInTheDocument();
  });
});
