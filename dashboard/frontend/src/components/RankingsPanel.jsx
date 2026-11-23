import { Fragment, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Card, Loading, ErrorState, fmtUsd, fmtNum, Badge } from './Primitives'
import ScoreBreakdown from './ScoreBreakdown'

export default function RankingsPanel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [sector, setSector] = useState('All')
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    api.rankings().then(setData).catch((e) => setError(e.message))
  }, [])

  const sectors = useMemo(() => {
    if (!data) return []
    return ['All', ...Array.from(new Set(data.companies.map((c) => c.sector))).sort()]
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return []
    return data.companies.filter((c) => {
      const matchesQuery =
        !query ||
        c.ticker.toLowerCase().includes(query.toLowerCase()) ||
        c.name.toLowerCase().includes(query.toLowerCase())
      const matchesSector = sector === 'All' || c.sector === sector
      return matchesQuery && matchesSector
    })
  }, [data, query, sector])

  if (error) return <ErrorState message={error} />
  if (!data) return <Loading label="Loading rankings..." />

  return (
    <Card
      title="LBO Attractiveness Rankings"
      subtitle={`${data.n_companies} companies scored across ${data.n_sectors} sectors. Click a row for its score breakdown.`}
    >
      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search ticker or name..."
          className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:border-[var(--accent)]"
        />
        <select
          value={sector}
          onChange={(e) => setSector(e.target.value)}
          className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
        >
          {sectors.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      <div className="overflow-x-auto -mx-1">
        <table className="w-full text-sm border-collapse min-w-[640px]">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-[var(--text-muted)] border-b border-[var(--border)]">
              <th className="px-3 py-2 font-medium">Rank</th>
              <th className="px-3 py-2 font-medium">Ticker</th>
              <th className="px-3 py-2 font-medium">Company</th>
              <th className="px-3 py-2 font-medium">Sector</th>
              <th className="px-3 py-2 font-medium text-right">Market Cap</th>
              <th className="px-3 py-2 font-medium text-right">Score</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 200).map((c) => (
              <Fragment key={c.ticker}>
                <tr
                  onClick={() => setExpanded(expanded === c.ticker ? null : c.ticker)}
                  className="cursor-pointer border-b border-[var(--border)] hover:bg-[var(--surface-2)] transition-colors"
                >
                  <td className="px-3 py-2.5 text-[var(--text-muted)] tabular-nums">{c.rank}</td>
                  <td className="px-3 py-2.5 font-medium text-[var(--text-primary)]">{c.ticker}</td>
                  <td className="px-3 py-2.5 text-[var(--text-secondary)] max-w-[240px] truncate">{c.name}</td>
                  <td className="px-3 py-2.5"><Badge>{c.sector}</Badge></td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-secondary)]">{fmtUsd(c.market_cap)}</td>
                  <td className="px-3 py-2.5 text-right">
                    <span className="inline-flex items-center gap-2">
                      <span className="tabular-nums font-semibold text-[var(--accent-strong)]">{fmtNum(c.lbo_score)}</span>
                      <span className="h-1.5 w-14 rounded-full bg-[var(--surface-2)] overflow-hidden hidden sm:block">
                        <span
                          className="block h-full rounded-full bg-[var(--accent)]"
                          style={{ width: `${Math.min(100, c.lbo_score)}%` }}
                        />
                      </span>
                    </span>
                  </td>
                </tr>
                {expanded === c.ticker && (
                  <tr className="border-b border-[var(--border)] bg-[var(--surface-2)]/40">
                    <td colSpan={6} className="px-4 py-4">
                      <ScoreBreakdown company={c} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center text-sm text-[var(--text-muted)] py-8">No companies match your filters.</div>
        )}
        {filtered.length > 200 && (
          <div className="text-center text-xs text-[var(--text-muted)] py-3">
            Showing first 200 of {filtered.length} matches — refine your search.
          </div>
        )}
      </div>
    </Card>
  )
}
