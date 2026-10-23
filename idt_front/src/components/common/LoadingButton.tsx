// mutation-pending-guard: TanStack Query isPending과 직결되는 공통 대기 버튼.
// isPending을 필수로 받아 "가드 누락" 실수를 타입 레벨에서 차단한다.
// Design Ref: ui-redesign-chat §5.3 — ui/Button 호환 래퍼. 기존 사용처의 className을 그대로 쓰기 위해 unstyled로 위임한다.
import type { ButtonHTMLAttributes } from 'react';
import Button from '@/components/ui/Button';

interface LoadingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** mutation.isPending 직결 — true면 disable + 스피너 */
  isPending: boolean;
  /** 대기 중 대체 문구 (미지정 시 children 유지) */
  pendingText?: string;
}

const LoadingButton = ({ isPending, pendingText, ...rest }: LoadingButtonProps) => (
  <Button unstyled isPending={isPending} pendingText={pendingText} {...rest} />
);

export default LoadingButton;
