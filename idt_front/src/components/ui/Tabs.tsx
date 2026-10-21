// Design Ref: ui-redesign-chat §5.3 — 밑줄형 탭 1종. tablist/tab 역할과 좌우·Home·End 키 이동을 제공한다.
import { useRef, type KeyboardEvent } from 'react';
import { cn } from '@/utils/cn';
import type { TabItem } from '@/types/ui';

interface TabsProps {
  items: TabItem[];
  value: string;
  onChange: (key: string) => void;
  'aria-label': string;
  className?: string;
}

const Tabs = ({ items, value, onChange, 'aria-label': ariaLabel, className }: TabsProps) => {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const move = (from: number, delta: number) => {
    const enabled = items.map((it, i) => (it.disabled ? -1 : i)).filter((i) => i >= 0);
    if (enabled.length === 0) return;
    const pos = enabled.indexOf(from);
    const nextPos = (pos + delta + enabled.length) % enabled.length;
    const next = enabled[nextPos];
    refs.current[next]?.focus();
    onChange(items[next].key);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const enabled = items.map((it, i) => (it.disabled ? -1 : i)).filter((i) => i >= 0);
    switch (e.key) {
      case 'ArrowRight':
        e.preventDefault();
        move(index, 1);
        break;
      case 'ArrowLeft':
        e.preventDefault();
        move(index, -1);
        break;
      case 'Home':
        e.preventDefault();
        if (enabled.length) {
          refs.current[enabled[0]]?.focus();
          onChange(items[enabled[0]].key);
        }
        break;
      case 'End':
        e.preventDefault();
        if (enabled.length) {
          const last = enabled[enabled.length - 1];
          refs.current[last]?.focus();
          onChange(items[last].key);
        }
        break;
      default:
        break;
    }
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn('flex items-center gap-1 border-b border-border', className)}
    >
      {items.map((item, index) => {
        const selected = item.key === value;
        return (
          <button
            key={item.key}
            ref={(el) => {
              refs.current[index] = el;
            }}
            role="tab"
            type="button"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            disabled={item.disabled}
            onClick={() => onChange(item.key)}
            onKeyDown={(e) => handleKeyDown(e, index)}
            className={cn(
              '-mb-px inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3.5 py-3 text-sm font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50',
              selected
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-fg-muted hover:text-fg',
            )}
          >
            {item.label}
            {item.count != null && (
              <span
                className={cn(
                  'rounded-full px-1.5 text-xs',
                  selected ? 'bg-brand-50 text-brand-700' : 'bg-surface-sunken text-fg-subtle',
                )}
              >
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};

export default Tabs;
