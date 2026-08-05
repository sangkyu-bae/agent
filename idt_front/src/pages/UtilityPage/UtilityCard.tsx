export type BadgeTone = 'sky' | 'violet' | 'amber' | 'emerald' | 'zinc';

export interface UtilityBadge {
  label: string;
  tone: BadgeTone;
}

interface UtilityCardProps {
  title: string;
  description: string;
  badges: UtilityBadge[];
  /** 보조 정보 (필요 환경변수, MCP 서버명 등) */
  meta?: string;
  /** 비활성 항목(비활성 모델 등)은 흐리게 표시 */
  dimmed?: boolean;
}

const TONE_STYLE: Record<BadgeTone, string> = {
  sky: 'bg-sky-50 text-sky-600',
  violet: 'bg-violet-50 text-violet-600',
  amber: 'bg-amber-50 text-amber-600',
  emerald: 'bg-emerald-50 text-emerald-600',
  zinc: 'bg-zinc-100 text-zinc-500',
};

const UtilityCard = ({ title, description, badges, meta, dimmed = false }: UtilityCardProps) => (
  <article
    aria-label={title}
    className={`group relative flex flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg ${
      dimmed ? 'opacity-55' : ''
    }`}
  >
    <div className="flex-1">
      <h3 className="text-[14px] font-semibold text-zinc-900">{title}</h3>
      <p className="mt-1.5 text-[12.5px] leading-[1.6] text-zinc-500">{description}</p>
    </div>

    <div className="mt-3.5 flex flex-wrap items-center gap-1.5">
      {badges.map((badge) => (
        <span
          key={badge.label}
          className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${TONE_STYLE[badge.tone]}`}
        >
          {badge.label}
        </span>
      ))}
    </div>

    {meta && <p className="mt-2 text-[11px] text-zinc-400">{meta}</p>}
  </article>
);

export default UtilityCard;
