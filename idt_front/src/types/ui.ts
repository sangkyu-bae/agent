// Design Ref: ui-redesign-chat §3.1 — UI 키트 공유 상수·타입. 컴포넌트 파일에서 런타임 상수 export 금지 규칙에 따라 여기에 둔다.

export const BUTTON_VARIANT = {
  primary: 'primary',
  secondary: 'secondary',
  ghost: 'ghost',
  danger: 'danger',
} as const;
export type ButtonVariant = (typeof BUTTON_VARIANT)[keyof typeof BUTTON_VARIANT];

export const CONTROL_SIZE = {
  sm: 'sm',
  md: 'md',
} as const;
export type ControlSize = (typeof CONTROL_SIZE)[keyof typeof CONTROL_SIZE];

export const BADGE_TONE = {
  neutral: 'neutral',
  success: 'success',
  warning: 'warning',
  danger: 'danger',
  info: 'info',
  brand: 'brand',
} as const;
export type BadgeTone = (typeof BADGE_TONE)[keyof typeof BADGE_TONE];

export const ICON_BUTTON_TONE = {
  neutral: 'neutral',
  danger: 'danger',
} as const;
export type IconButtonTone = (typeof ICON_BUTTON_TONE)[keyof typeof ICON_BUTTON_TONE];

export interface TabItem {
  key: string;
  label: string;
  count?: number;
  disabled?: boolean;
}
