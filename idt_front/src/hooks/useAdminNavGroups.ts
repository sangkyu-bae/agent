import { useMemo } from 'react';
import { selectAdminNavGroups, type AdminNavGroup } from '@/constants/adminNav';
import { useFirewallStatus } from '@/hooks/useFirewall';
import { useAuthStore } from '@/store/authStore';

/**
 * 화면에 노출할 관리자 메뉴 그룹.
 * firewall-admin-console §10.4 (Plan FR-16): "보안 운영" 그룹은 백엔드 모듈이 켜져 있을 때만 보인다.
 * 설정 출처를 백엔드 한 곳으로 두기 위해 프론트 환경변수가 아니라 status 응답으로 판정한다.
 * 관리자가 아니면 status 를 묻지 않는다. 메뉴는 모든 화면에 있으므로 주기 갱신은 하지 않는다
 * (방화벽 페이지가 열려 있을 때만 페이지가 30초마다 갱신한다 — Check G5).
 */
export const useAdminNavGroups = (): AdminNavGroup[] => {
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin');
  const { data } = useFirewallStatus({ enabled: isAdmin, poll: false });
  const firewallEnabled = data?.enabled === true;
  return useMemo(() => selectAdminNavGroups({ firewallEnabled }), [firewallEnabled]);
};
