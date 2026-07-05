import { useEffect, useId, useMemo, useRef, useState } from 'react';

export interface DropdownOption<T extends string = string> {
  value: T;
  label: string;
  /** 우측 인라인 배지 텍스트 (예: 'API 키 미등록' → [API 키 미등록]) */
  badge?: string;
  disabled?: boolean;
}

export interface DropdownProps<T extends string = string> {
  value: T;
  onChange: (value: T) => void;
  options: DropdownOption<T>[];
  /** 'default': 일반 텍스트(필터/폼) · 'model': mono+bullet+badge (dropdown.png) */
  variant?: 'default' | 'model';
  /** 검색 입력 노출 여부 (기본: variant === 'model') */
  searchable?: boolean;
  placeholder?: string;
  disabled?: boolean;
  isLoading?: boolean;
  emptyText?: string;
  searchPlaceholder?: string;
  className?: string;
  id?: string;
  ariaLabel?: string;
  /** 네이티브 form 제출 연동 시 hidden input name */
  name?: string;
}

const CheckIcon = () => (
  <svg className="h-3.5 w-3.5 text-violet-600" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
  </svg>
);

const ChevronIcon = ({ open }: { open: boolean }) => (
  <svg
    className={`h-4 w-4 shrink-0 text-zinc-400 transition-transform ${open ? 'rotate-180' : ''}`}
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={2}
    stroke="currentColor"
  >
    <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
  </svg>
);

const SearchIcon = () => (
  <svg className="h-4 w-4 shrink-0 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
  </svg>
);

/**
 * 공통 헤드리스 드롭다운 (dropdown.png 디자인).
 * 네이티브 `<select value onChange>`를 대체. controlled 전용.
 */
const Dropdown = <T extends string = string,>({
  value,
  onChange,
  options,
  variant = 'default',
  searchable,
  placeholder = '선택하세요',
  disabled = false,
  isLoading = false,
  emptyText = '항목이 없습니다',
  searchPlaceholder = '검색...',
  className = '',
  id,
  ariaLabel,
  name,
}: DropdownProps<T>) => {
  const isModel = variant === 'model';
  const canSearch = searchable ?? isModel;

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [showScrollHint, setShowScrollHint] = useState(false);

  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  const filtered = useMemo(() => {
    if (!canSearch || !query.trim()) return options;
    const q = query.trim().toLowerCase();
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, query, canSearch]);

  const selected = options.find((o) => o.value === value);

  const firstEnabled = () => {
    const i = filtered.findIndex((o) => !o.disabled);
    return i >= 0 ? i : 0;
  };
  const lastEnabled = () => {
    for (let i = filtered.length - 1; i >= 0; i -= 1) if (!filtered[i].disabled) return i;
    return 0;
  };

  // 열릴 때 검색어 초기화 + active 위치를 현재 선택값으로
  useEffect(() => {
    if (!open) return;
    setQuery('');
    const idx = options.findIndex((o) => o.value === value);
    setActiveIndex(idx >= 0 ? idx : 0);
    if (canSearch) requestAnimationFrame(() => searchRef.current?.focus());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // 외부 클릭 닫기
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  // 스크롤 인디케이터(▾) 계산
  const updateScrollHint = () => {
    const el = listRef.current;
    if (!el) {
      setShowScrollHint(false);
      return;
    }
    const overflow = el.scrollHeight - el.clientHeight;
    setShowScrollHint(overflow > 4 && el.scrollTop < overflow - 4);
  };
  useEffect(() => {
    if (open) requestAnimationFrame(updateScrollHint);
    else setShowScrollHint(false);
  }, [open, filtered.length]);

  const commit = (opt: DropdownOption<T>) => {
    if (opt.disabled) return;
    onChange(opt.value);
    setOpen(false);
  };

  const moveActive = (dir: 1 | -1) => {
    if (!filtered.length) return;
    let i = activeIndex;
    for (let n = 0; n < filtered.length; n += 1) {
      i = (i + dir + filtered.length) % filtered.length;
      if (!filtered[i].disabled) break;
    }
    setActiveIndex(i);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled || isLoading) return;
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        moveActive(1);
        break;
      case 'ArrowUp':
        e.preventDefault();
        moveActive(-1);
        break;
      case 'Home':
        e.preventDefault();
        setActiveIndex(firstEnabled());
        break;
      case 'End':
        e.preventDefault();
        setActiveIndex(lastEnabled());
        break;
      case 'Enter':
        e.preventDefault();
        if (filtered[activeIndex]) commit(filtered[activeIndex]);
        break;
      case 'Escape':
        e.preventDefault();
        setOpen(false);
        break;
      case 'Tab':
        setOpen(false);
        break;
      default:
        break;
    }
  };

  if (isLoading) {
    return (
      <div className={`h-[42px] w-full animate-pulse rounded-xl border border-zinc-200 bg-zinc-100 ${className}`} />
    );
  }

  const triggerLabel = selected?.label ?? placeholder;
  const activeOptionId = open && filtered[activeIndex] ? `${listId}-opt-${activeIndex}` : undefined;

  return (
    <div ref={rootRef} className={`relative ${className}`} onKeyDown={handleKeyDown}>
      {name && <input type="hidden" name={name} value={value} />}

      <button
        type="button"
        id={id}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={activeOptionId}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className={`flex w-full items-center gap-1.5 rounded-xl border bg-white px-3.5 py-2.5 text-left outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100 disabled:cursor-not-allowed disabled:bg-zinc-50 disabled:text-zinc-400 ${
          open ? 'border-violet-400' : 'border-zinc-300'
        }`}
      >
        {isModel && <span className="text-zinc-300">•</span>}
        <span
          className={`flex-1 truncate ${isModel ? 'font-mono text-[13px]' : 'text-[13.5px]'} ${
            selected ? 'text-zinc-800' : 'text-zinc-400'
          }`}
        >
          {triggerLabel}
          {selected?.badge && <span className="ml-1.5 text-[11px] text-zinc-400">[{selected.badge}]</span>}
        </span>
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-50 mt-1 overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-xl">
          {canSearch && (
            <div className="sticky top-0 flex items-center gap-2 border-b border-zinc-100 bg-white px-3 py-2">
              <SearchIcon />
              <input
                ref={searchRef}
                type="text"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActiveIndex(0);
                }}
                placeholder={searchPlaceholder}
                aria-label="검색"
                aria-controls={listId}
                aria-activedescendant={activeOptionId}
                className="w-full bg-transparent text-[13px] text-zinc-800 outline-none placeholder:text-zinc-400"
              />
            </div>
          )}

          <ul
            ref={listRef}
            id={listId}
            role="listbox"
            onScroll={updateScrollHint}
            className="max-h-[280px] overflow-y-auto py-1"
          >
            {filtered.length === 0 ? (
              <li className="px-3 py-3 text-center text-[13px] text-zinc-400">{emptyText}</li>
            ) : (
              filtered.map((opt, i) => {
                const isSelected = opt.value === value;
                const isActive = i === activeIndex;
                return (
                  <li
                    key={opt.value}
                    id={`${listId}-opt-${i}`}
                    role="option"
                    aria-selected={isSelected}
                    aria-disabled={opt.disabled}
                    onMouseEnter={() => !opt.disabled && setActiveIndex(i)}
                    onClick={() => commit(opt)}
                    className={`flex items-center gap-1.5 px-3 py-2 ${
                      opt.disabled
                        ? 'cursor-not-allowed text-zinc-300'
                        : `cursor-pointer ${isActive ? 'bg-violet-50' : ''}`
                    }`}
                  >
                    <span className="flex w-4 shrink-0 justify-center">{isSelected && <CheckIcon />}</span>
                    {isModel && (
                      <span className={isSelected ? 'text-violet-500' : 'text-zinc-300'}>•</span>
                    )}
                    <span
                      className={`flex-1 truncate ${isModel ? 'font-mono text-[13px]' : 'text-[13.5px]'} ${
                        opt.disabled ? 'text-zinc-300' : 'text-zinc-700'
                      }`}
                    >
                      {opt.label}
                    </span>
                    {opt.badge && <span className="ml-auto shrink-0 text-[11px] text-zinc-400">[{opt.badge}]</span>}
                  </li>
                );
              })
            )}
          </ul>

          {showScrollHint && (
            <div className="pointer-events-none flex justify-center border-t border-zinc-100 py-0.5 text-zinc-300">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
              </svg>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Dropdown;
