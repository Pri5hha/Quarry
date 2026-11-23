export function Card({ title, subtitle, children, className = '' }) {
  return (
    <section
      className={`rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6 ${className}`}
    >
      {(title || subtitle) && (
        <header className="mb-4">
          {title && <h2 className="text-sm font-semibold tracking-wide text-[var(--text-primary)] uppercase">{title}</h2>}
          {subtitle && <p className="mt-1 text-sm text-[var(--text-secondary)]">{subtitle}</p>}
        </header>
      )}
      {children}
    </section>
  )
}

export function StatTile({ label, value, detail, accent = false }) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3.5 min-w-0">
      <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
      <div
        className={`mt-1 text-2xl font-semibold tabular-nums ${accent ? 'text-[var(--accent-strong)]' : 'text-[var(--text-primary)]'}`}
      >
        {value}
      </div>
      {detail && <div className="mt-1 text-xs text-[var(--text-secondary)] leading-snug">{detail}</div>}
    </div>
  )
}

export function Loading({ label = 'Loading...' }) {
  return (
    <div className="flex items-center gap-2 text-sm text-[var(--text-muted)] py-8 justify-center">
      <span className="h-3 w-3 rounded-full border-2 border-[var(--accent)] border-t-transparent animate-spin" />
      {label}
    </div>
  )
}

export function ErrorState({ message }) {
  return (
    <div className="rounded-lg border border-[var(--status-critical)]/40 bg-[var(--status-critical)]/10 px-4 py-3 text-sm text-[var(--text-primary)]">
      <span className="font-medium text-[var(--status-critical)]">Couldn't load this panel. </span>
      {message}
    </div>
  )
}

export function Badge({ children, tone = 'neutral' }) {
  const tones = {
    neutral: 'bg-[var(--surface-2)] text-[var(--text-secondary)] border-[var(--border)]',
    accent: 'bg-[var(--accent-soft)] text-[var(--accent-strong)] border-[var(--accent)]/30',
    good: 'bg-[var(--status-good)]/15 text-[var(--status-good)] border-[var(--status-good)]/30',
  }
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function fmtUsd(value, { compact = true } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (compact) {
    const abs = Math.abs(value)
    if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`
    if (abs >= 1e6) return `$${(value / 1e6).toFixed(1)}M`
    if (abs >= 1e3) return `$${(value / 1e3).toFixed(1)}K`
  }
  return `$${value.toLocaleString()}`
}

export function fmtPct(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value.toFixed(digits)}%`
}

export function fmtNum(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}
