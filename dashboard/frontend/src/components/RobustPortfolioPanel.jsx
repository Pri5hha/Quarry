import { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, StatTile, Loading, ErrorState, Badge, fmtUsd, fmtNum, fmtPct } from './Primitives'

export default function RobustPortfolioPanel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.robustPortfolio().then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <ErrorState message={error} />
  if (!data) return <Loading label="Loading robust portfolio..." />

  const cmp = data.comparison_vs_deterministic

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="Chance-Constrained Allocation"
        subtitle={`Each company's value is treated as score + noise calibrated to its historical revenue volatility. The portfolio is required to clear a minimum value target in at least ${fmtPct(data.parameters.target_probability * 100)} of ${data.parameters.n_scenarios} simulated scenarios (at a $${(data.parameters.budget_usd / 1e9).toFixed(0)}B budget).`}
      >
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <StatTile
            label="Target probability"
            value={fmtPct(data.parameters.target_probability * 100)}
            accent
            detail={`empirically ${fmtPct(data.empirical_probability_above_target * 100)}`}
          />
          <StatTile label="Min value target" value={fmtNum(data.min_portfolio_value_target)} />
          <StatTile label="Expected value" value={fmtNum(data.expected_portfolio_value)} detail={`vs. ${fmtNum(data.deterministic_baseline_value)} deterministic`} />
          <StatTile label="Value given up" value={fmtNum(cmp.expected_value_given_up)} detail="score-points, for safety" />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-4">
            <div className="text-xs uppercase tracking-wide text-[var(--text-muted)] mb-2">Dropped by robust solution</div>
            {cmp.dropped_by_robust_solution.length === 0 ? (
              <div className="text-sm text-[var(--text-muted)]">None</div>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {cmp.dropped_by_robust_solution.map((t) => <Badge key={t} tone="neutral">{t}</Badge>)}
              </div>
            )}
          </div>
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-4">
            <div className="text-xs uppercase tracking-wide text-[var(--text-muted)] mb-2">Added by robust solution</div>
            {cmp.added_by_robust_solution.length === 0 ? (
              <div className="text-sm text-[var(--text-muted)]">None</div>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {cmp.added_by_robust_solution.map((t) => <Badge key={t} tone="good">{t}</Badge>)}
              </div>
            )}
          </div>
        </div>
      </Card>

      <Card title="Robust portfolio holdings">
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse min-w-[560px]">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-[var(--text-muted)] border-b border-[var(--border)]">
                <th className="px-3 py-2 font-medium">Ticker</th>
                <th className="px-3 py-2 font-medium">Company</th>
                <th className="px-3 py-2 font-medium">Sector</th>
                <th className="px-3 py-2 font-medium text-right">Score</th>
                <th className="px-3 py-2 font-medium text-right">Uncertainty (σ)</th>
                <th className="px-3 py-2 font-medium text-right">Acquisition Cost</th>
              </tr>
            </thead>
            <tbody>
              {data.selected_companies.map((c) => (
                <tr key={c.ticker} className="border-b border-[var(--border)]">
                  <td className="px-3 py-2.5 font-medium text-[var(--text-primary)]">{c.ticker}</td>
                  <td className="px-3 py-2.5 text-[var(--text-secondary)] max-w-[220px] truncate">{c.name}</td>
                  <td className="px-3 py-2.5"><Badge>{c.sector}</Badge></td>
                  <td className="px-3 py-2.5 text-right tabular-nums font-semibold text-[var(--accent-strong)]">{fmtNum(c.lbo_score)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-secondary)]">± {fmtNum(c.sigma)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-secondary)]">{fmtUsd(c.acquisition_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-xs text-[var(--text-muted)] leading-relaxed">{data.methodology_note}</p>
      </Card>
    </div>
  )
}
