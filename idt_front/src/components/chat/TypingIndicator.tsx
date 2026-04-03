const TypingIndicator = () => {
  return (
    <div className="flex items-start gap-4">
      <div
        className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-md"
        style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
      >
        <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z" />
        </svg>
      </div>
      <div className="flex items-center gap-1.5 rounded-2xl border border-zinc-100 bg-zinc-50 px-4 py-3.5">
        <span className="h-2 w-2 rounded-full bg-zinc-400 animate-bounce [animation-delay:-0.3s]" />
        <span className="h-2 w-2 rounded-full bg-zinc-400 animate-bounce [animation-delay:-0.15s]" />
        <span className="h-2 w-2 rounded-full bg-zinc-400 animate-bounce" />
      </div>
    </div>
  );
};

export default TypingIndicator;
