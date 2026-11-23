import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { api } from '../api'
import { Card, StatTile, Loading, ErrorState, Badge, fmtUsd, fmtNum, fmtPct } from './Primitives'

function SectorTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-xs shadow-lg">
      <div className="font-medium text-[var(--text-primary)]">{d.sector}</div>
      <div className="text-[var(--text-secondary)]">{d.n_targets} targets · {fmtUsd(d.total_cost)} deployed</div>
      <div className="text-[var(--text-secondary)]">Avg score: {fmtNum(d.avg_score)}</div>
    </div>
  )
}

export default function OptimalPortfolioPanel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.optimalPortfolio().then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <ErrorState message={error} />
  if (!data) return <Loading label="Loading optimal portfolio..." />

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="Optimal Acquisition Portfolio"
        subtitle={`MILP-selected subset maximizing total LBO attractiveness under a $${(data.parameters.budget_usd / 1e9).toFixed(0)}B budget and a max-${data.parameters.max_per_sector}-per-sector diversification constraint.`}
      >
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <StatTile label="Targets selected" value={data.n_targets_selected} accent />
          <StatTile label="Budget used" value={fmtUsd(data.budget_used_usd)} detail={`of $${(data.parameters.budget_usd / 1e9).toFixed(0)}B`} />
          <StatTile label="Budget utilization" value={fmtPct(data.budget_utilization_pct)} />
          <StatTile label="Portfolio value" value={fmtNum(data.total_portfolio_value)} detail="sum of LBO scores" />
        </div>

        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)] mb-3">Sector diversification</h3>
        <ResponsiveContainer width="100%" height={Math.max(200, data.sector_breakdown.length * 34)}>
          <BarChart data={data.sector_breakdown} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
            <CartesianGrid horizontal={false} stroke="var(--gridline)" />
            <XAxis type="number" allowDecimals={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--baseline)" />
            <YAxis type="category" dataKey="sector" width={130} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} stroke="var(--baseline)" />
            <Tooltip content={<SectorTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
            <Bar dataKey="n_targets" fill="var(--accent)" radius={[0, 4, 4, 0]} maxBarSize={18} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <Card title="Selected companies">
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse min-w-[560px]">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-[var(--text-muted)] border-b border-[var(--border)]">
                <th className="px-3 py-2 font-medium">Ticker</th>
                <th className="px-3 py-2 font-medium">Company</th>
                <th className="px-3 py-2 font-medium">Sector</th>
                <th className="px-3 py-2 font-medium text-right">Score</th>
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
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-secondary)]">{fmtUsd(c.acquisition_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
