import { useEffect, type ReactNode } from 'react';

interface ModalProps {
  /** 생략(기본 true) 시 부모 조건부 렌더 방식 지원 */
  isOpen?: boolean;
  onClose: () => void;
  /** 헤더 타이틀. 생략 시 헤더 자체를 렌더하지 않음 (커스텀 헤더는 children으로) */
  title?: ReactNode;
  /** 타이틀 하단 보조 설명 */
  subtitle?: ReactNode;
  /** 콘텐츠 박스 최대 폭 (Tailwind max-w-*와 1:1, 'full'은 뷰포트 80%). 기본 'md' */
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl' | '4xl' | 'full';
  /** 하단 액션 영역. 본문 스크롤과 분리 렌더 */
  footer?: ReactNode;
  /** 배경 클릭으로 닫기. 기본 true */
  closeOnBackdrop?: boolean;
  /** ESC로 닫기. 기본 true */
  closeOnEsc?: boolean;
  /** true면 배경클릭/ESC/X 모두 차단 (업로드 진행 중 등) */
  disableClose?: boolean;
  /** 딤 스타일. 기본 'default'(bg-black/50), 'blur'(bg-black/40 + backdrop-blur-sm) */
  dim?: 'default' | 'blur';
  /** 스크롤 모드. 'body'=헤더/footer 고정+본문 스크롤, 'content'=박스 전체 스크롤, 'none'=스크롤 없음 */
  scroll?: 'body' | 'content' | 'none';
  /** 헤더 X 닫기 버튼 표시. 기본 true (title 있을 때만 렌더) */
  showCloseButton?: boolean;
  /** 콘텐츠 박스 추가 클래스 (고정폭 등 특수 레이아웃 보존용) */
  contentClassName?: string;
  children: ReactNode;
}

const SIZE_CLASSES = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '3xl': 'max-w-3xl',
  '4xl': 'max-w-4xl',
  full: 'max-w-[80vw]',
} as const;

/**
 * 공통 모달 오버레이 (tool-config-modal Design §2.1).
 * 프로젝트 전역의 `fixed inset-0 z-50` 중복 구현을 대체한다.
 * ESC는 document keydown으로 표준화, 접근성(role/aria-modal)을 일괄 부여한다.
 */
const Modal = ({
  isOpen = true,
  onClose,
  title,
  subtitle,
  size = 'md',
  footer,
  closeOnBackdrop = true,
  closeOnEsc = true,
  disableClose = false,
  dim = 'default',
  scroll = 'none',
  showCloseButton = true,
  contentClassName = '',
  children,
}: ModalProps) => {
  useEffect(() => {
    if (!isOpen || !closeOnEsc || disableClose) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, closeOnEsc, disableClose, onClose]);

  if (!isOpen) return null;

  const dimClass =
    dim === 'blur' ? 'bg-black/40 backdrop-blur-sm' : 'bg-black/50';
  const scrollContentClass =
    scroll === 'content' ? 'max-h-[85vh] overflow-y-auto' : scroll === 'body' ? 'flex max-h-[85vh] flex-col' : '';

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center px-4 ${dimClass}`}
      onClick={() => {
        if (closeOnBackdrop && !disableClose) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        className={`w-full ${SIZE_CLASSES[size]} rounded-2xl bg-white p-6 shadow-2xl ${scrollContentClass} ${contentClassName}`}
        onClick={(e) => e.stopPropagation()}
      >
        {title != null && (
          <div className="shrink-0">
            <div className="flex items-center justify-between">
              <h2 className="text-[16px] font-semibold text-zinc-900">{title}</h2>
              {showCloseButton && (
                <button
                  type="button"
                  onClick={onClose}
                  disabled={disableClose}
                  aria-label="닫기"
                  className="rounded-lg p-1 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
            {subtitle != null && (
              <p className="mt-1 text-[12.5px] text-zinc-400">{subtitle}</p>
            )}
          </div>
        )}

        {scroll === 'body' ? (
          <div className="mt-4 flex-1 overflow-y-auto">{children}</div>
        ) : (
          <div className={title != null ? 'mt-4' : ''}>{children}</div>
        )}

        {footer != null && (
          <div className="mt-5 flex shrink-0 justify-end gap-2">{footer}</div>
        )}
      </div>
    </div>
  );
};

export default Modal;
