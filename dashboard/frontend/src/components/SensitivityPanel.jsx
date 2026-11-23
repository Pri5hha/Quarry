import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { api } from '../api'
import { Card, StatTile, Loading, ErrorState, fmtNum, fmtPct } from './Primitives'

function DualTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-xs shadow-lg">
      <div className="font-medium text-[var(--text-primary)]">{d.sector}</div>
      <div className="text-[var(--text-secondary)]">{d.n_candidates_in_sector} eligible candidates, cap {d.cap}</div>
      <div className="text-[var(--text-secondary)]">{d.binding ? 'Binding constraint' : 'Not binding'}</div>
      <div className="text-[var(--text-secondary)]">
        Shadow price: <span className="tabular-nums text-[var(--text-primary)]">{d.shadow_price ?? 0}</span>
      </div>
    </div>
  )
}

export default function SensitivityPanel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.sensitivity().then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <ErrorState message={error} />
  if (!data) return <Loading label="Loading sensitivity report..." />

  const lp = data.lp_relaxation_shadow_prices
  const div = data.diversification_cost
  const dualsData = [...lp.sector_diversification_duals].sort((a, b) => (b.shadow_price || 0) - (a.shadow_price || 0))

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="Shadow Prices & Duality"
        subtitle="Marginal value of relaxing the budget and diversification constraints, read from the LP relaxation of the allocation MILP."
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
          <StatTile
            label="Value per +$1M budget"
            value={fmtNum(lp.budget_shadow_price_per_1m, 3)}
            detail="score-points of extra portfolio value"
            accent
          />
          <StatTile label="Budget constraint" value={lp.budget_binding ? 'Binding' : 'Slack'} />
          <StatTile
            label="Diversification cost"
            value={fmtNum(div.forgone_value_from_diversification)}
            detail={`${fmtPct(div.forgone_value_pct)} of unconstrained value forgone`}
          />
        </div>

        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)] mb-3">
          Diversification shadow price by sector
        </h3>
        <ResponsiveContainer width="100%" height={Math.max(220, dualsData.length * 30)}>
          <BarChart data={dualsData} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
            <CartesianGrid horizontal={false} stroke="var(--gridline)" />
            <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--baseline)" />
            <YAxis type="category" dataKey="sector" width={130} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} stroke="var(--baseline)" />
            <Tooltip content={<DualTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
            <Bar dataKey="shadow_price" radius={[0, 4, 4, 0]} maxBarSize={16}>
              {dualsData.map((d) => (
                <Cell key={d.sector} fill={d.binding ? 'var(--accent)' : 'var(--text-muted)'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <div className="flex items-center gap-4 mt-3 text-xs text-[var(--text-muted)]">
          <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: 'var(--accent)' }} /> Binding cap</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: 'var(--text-muted)' }} /> Slack</span>
        </div>
      </Card>

      <Card title="With vs. without diversification">
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-4">
            <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
              With cap ({div.with_diversification.max_per_sector}/sector)
            </div>
            <div className="mt-1 text-xl font-semibold text-[var(--text-primary)] tabular-nums">{fmtNum(div.with_diversification.total_value)}</div>
            <div className="text-xs text-[var(--text-secondary)]">{div.with_diversification.n_selected} targets</div>
          </div>
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-4">
            <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Unconstrained by sector</div>
            <div className="mt-1 text-xl font-semibold text-[var(--accent-strong)] tabular-nums">{fmtNum(div.without_diversification.total_value)}</div>
            <div className="text-xs text-[var(--text-secondary)]">{div.without_diversification.n_selected} targets</div>
          </div>
        </div>
        <p className="mt-4 text-xs text-[var(--text-muted)] leading-relaxed">{data.methodology_note}</p>
      </Card>
    </div>
  )
}
