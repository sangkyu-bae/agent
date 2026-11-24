// Design Ref: firewall-admin-console §5.4 공통 (Plan FR-17) — 연결 상태와 DRY-RUN/LIVE 를 항상 보여 준다.
// 색만으로 전달하지 않도록 배지에 글자를 함께 쓴다.
import Badge from '@/components/ui/Badge';
import type { FirewallStatusResponse } from '@/types/firewall';

interface FirewallStatusBarProps {
  status: FirewallStatusResponse;
}

const FirewallStatusBar = ({ status }: FirewallStatusBarProps) => {
  const { fwctl } = status;

  let connection = <Badge tone="success" dot>연결됨</Badge>;
  if (!fwctl.configured) connection = <Badge tone="neutral">설정 필요</Badge>;
  else if (!fwctl.reachable) connection = <Badge tone="danger" dot>연결 안 됨</Badge>;

  return (
    <section
      aria-label="방화벽 상태"
      className="mb-5 rounded-lg border border-border bg-surface px-4 py-3"
    >
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-fg-muted">
        <span className="flex items-center gap-2">
          <span className="text-fg-subtle">fwctl</span>
          {connection}
        </span>
        {fwctl.reachable && fwctl.dry_run !== null && (
          <span className="flex items-center gap-2">
            <span className="text-fg-subtle">모드</span>
            {fwctl.dry_run ? (
              <Badge tone="warning">DRY-RUN</Badge>
            ) : (
              <Badge tone="danger">LIVE</Badge>
            )}
          </span>
        )}
        {fwctl.reachable && fwctl.max_ttl_seconds !== null && (
          <span>
            <span className="text-fg-subtle">TTL 상한</span> {fwctl.max_ttl_seconds}초
          </span>
        )}
        {fwctl.reachable && fwctl.ipset_exists !== null && (
          <span>
            <span className="text-fg-subtle">ipset</span>{' '}
            {fwctl.ipset_exists ? '정상' : '없음'}
          </span>
        )}
        {fwctl.reachable && fwctl.version && (
          <span>
            <span className="text-fg-subtle">버전</span> {fwctl.version}
          </span>
        )}
      </div>

      {!fwctl.configured && (
        <p className="mt-2 text-sm text-fg-muted">
          서버에 fwctl 주소와 토큰이 설정되지 않았습니다. 설정 이름:{' '}
          <code>FIREWALL_ADMIN_FWCTL_URL</code>, <code>FIREWALL_ADMIN_FWCTL_TOKEN</code>
        </p>
      )}
      {fwctl.configured && !fwctl.reachable && (
        <p className="mt-2 text-sm text-danger">
          fwctl에 연결할 수 없어 차단·해제를 할 수 없습니다. 방화벽 랩이 실행 중인지 확인하세요.
        </p>
      )}
      {fwctl.reachable && fwctl.dry_run === true && (
        <p className="mt-2 text-sm text-warning">
          차단 요청은 기록만 되고 실제로 적용되지 않습니다.
        </p>
      )}
      {fwctl.reachable && fwctl.ipset_exists === false && (
        <p className="mt-2 text-sm text-danger">
          차단 목록(ipset)을 찾을 수 없습니다. firewall과 fwctl 컨테이너를 함께 다시 시작하세요.
        </p>
      )}
    </section>
  );
};

export default FirewallStatusBar;
