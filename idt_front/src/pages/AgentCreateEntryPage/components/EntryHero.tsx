// Design Ref: agent-create-entry §5.1 — 시안(docs/img/create_agent.png) 상단 히어로.
const EntryHero = () => (
  <div className="flex flex-col items-center text-center">
    <div
      className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl shadow-lg"
      style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
    >
      <svg
        className="h-7 w-7 text-white"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={1.5}
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z"
        />
      </svg>
    </div>

    <h1 className="text-[26px] font-bold tracking-tight text-violet-700">
      생성하려는 에이전트에 대해 알려주세요
    </h1>
    <p className="mt-3 text-[15px] leading-relaxed text-zinc-500">
      원하는 에이전트가 무엇을 하길 원하는지 설명해 주시면, 단계별로 안내해 드리겠습니다
    </p>
  </div>
);

export default EntryHero;
