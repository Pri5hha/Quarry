import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts'
import { api } from '../api'
import { Card, StatTile, Loading, ErrorState, Badge, fmtPct, fmtNum } from './Primitives'

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-xs shadow-lg">
      <div className="font-medium text-[var(--text-primary)]">{d.ticker} — {d.name}</div>
      <div className="text-[var(--text-secondary)] mt-0.5">Sector: {d.sector}</div>
      <div className="text-[var(--text-secondary)]">Deal announced: {d.deal_announce_date}</div>
      <div className="text-[var(--text-secondary)]">
        Pre-deal percentile: <span className="tabular-nums text-[var(--text-primary)]">{d.percentile.toFixed(1)}</span>
      </div>
    </div>
  )
}

export default function BacktestPanel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.backtest().then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <ErrorState message={error} />
  if (!data) return <Loading label="Loading backtest results..." />

  const { summary, targets } = data
  const chartData = [...targets].sort((a, b) => a.percentile - b.percentile)

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="Backtest: real LBO targets, scored before their deals"
        subtitle="For each real take-private, financials from before the deal was announced are pulled from SEC EDGAR and run through the scoring model."
      >
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <StatTile label="Top-20% hit rate" value={fmtPct(summary.hit_rate_top20_pct)} accent
            detail={`${targets.filter((t) => t.in_top_20_pct).length} of ${summary.n_targets_scored} targets`} />
          <StatTile label="Median percentile" value={fmtNum(summary.median_percentile)} />
          <StatTile label="Mean percentile" value={fmtNum(summary.mean_percentile)} />
          <StatTile label="Targets scored" value={summary.n_targets_scored} detail={`of ${summary.n_historical_targets_curated} curated`} />
        </div>

        <ResponsiveContainer width="100%" height={Math.max(320, chartData.length * 26)}>
          <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
            <CartesianGrid horizontal={false} stroke="var(--gridline)" />
            <XAxis type="number" domain={[0, 100]} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--baseline)" />
            <YAxis type="category" dataKey="ticker" width={56} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} stroke="var(--baseline)" />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
            <ReferenceLine x={80} stroke="var(--accent)" strokeDasharray="4 3" label={{ value: 'Top 20%', position: 'insideTopRight', fill: 'var(--accent-strong)', fontSize: 11 }} />
            <Bar dataKey="percentile" radius={[0, 4, 4, 0]} maxBarSize={16}>
              {chartData.map((d) => (
                <Cell key={d.ticker} fill={d.in_top_20_pct ? 'var(--status-good)' : 'var(--text-muted)'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <div className="flex items-center gap-4 mt-3 text-xs text-[var(--text-muted)]">
          <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: 'var(--status-good)' }} /> Scored in top 20%</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: 'var(--text-muted)' }} /> Below top 20%</span>
        </div>
      </Card>

      <Card title="By sector" subtitle="Classic PE screening criteria predict some sectors' take-privates far better than others.">
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse min-w-[480px]">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-[var(--text-muted)] border-b border-[var(--border)]">
                <th className="px-3 py-2 font-medium">Sector</th>
                <th className="px-3 py-2 font-medium text-right">Targets</th>
                <th className="px-3 py-2 font-medium text-right">Median Percentile</th>
                <th className="px-3 py-2 font-medium text-right">Top-20% Hit Rate</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(summary.sector_breakdown).map(([sec, s]) => (
                <tr key={sec} className="border-b border-[var(--border)]">
                  <td className="px-3 py-2.5"><Badge>{sec}</Badge></td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-secondary)]">{s.n_targets}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-primary)]">{fmtNum(s.median_percentile)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-primary)]">{fmtPct(s.hit_rate_top20_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-xs text-[var(--text-muted)] leading-relaxed">{summary.methodology_note}</p>
      </Card>
    </div>
  )
}
