import { useEffect, useState } from 'react'
import { api } from '../api'
import { Loading } from './Primitives'

export default function KeyFindingsBanner() {
  const [findings, setFindings] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.keyFindings().then((d) => setFindings(d.findings)).catch((e) => setError(e.message))
  }, [])

  if (error) return null
  if (!findings) return <Loading label="Loading key findings..." />

  return (
    <div className="rounded-xl border border-[var(--accent)]/25 bg-gradient-to-r from-[var(--accent-soft)] to-transparent p-5 sm:p-6">
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--accent-strong)] mb-3">
        Key findings
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {findings.map((f) => (
          <div key={f.label} className="min-w-0">
            <div className="text-xs text-[var(--text-muted)] uppercase tracking-wide">{f.label}</div>
            <div className="mt-0.5 text-xl font-semibold text-[var(--text-primary)] tabular-nums">{f.value}</div>
            <div className="mt-1 text-xs text-[var(--text-secondary)] leading-snug">{f.detail}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
