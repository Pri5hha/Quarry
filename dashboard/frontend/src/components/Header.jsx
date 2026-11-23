const TABS = [
  { id: 'rankings', label: 'Rankings' },
  { id: 'backtest', label: 'Backtest' },
  { id: 'replay', label: 'Replay' },
  { id: 'portfolio', label: 'Optimal Portfolio' },
  { id: 'sensitivity', label: 'Sensitivity' },
  { id: 'robust', label: 'Robust Allocation' },
]

export default function Header({ activeTab, onTabChange }) {
  return (
    <header className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--surface-0)]/95 backdrop-blur">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 pt-5">
        <div className="flex items-center gap-3">
          <svg width="30" height="30" viewBox="0 0 100 100" className="shrink-0">
            <rect width="100" height="100" rx="18" fill="var(--surface-2)" />
            <path d="M28 68 L50 26 L72 68 Z" fill="none" stroke="var(--accent)" strokeWidth="6" strokeLinejoin="round" />
            <circle cx="50" cy="56" r="5" fill="var(--accent)" />
          </svg>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-[var(--text-primary)]">
              Quarry
            </h1>
            <p className="text-xs text-[var(--text-muted)] -mt-0.5">LBO target screening &amp; capital allocation</p>
          </div>
        </div>

        <nav className="mt-5 flex gap-1 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`whitespace-nowrap rounded-t-lg px-3.5 py-2.5 text-sm font-medium transition-colors border-b-2 ${
                activeTab === tab.id
                  ? 'border-[var(--accent)] text-[var(--accent-strong)]'
                  : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>
    </header>
  )
}
