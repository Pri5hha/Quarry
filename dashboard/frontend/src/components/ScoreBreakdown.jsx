import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, Tooltip, ResponsiveContainer } from 'recharts'

const COMPONENTS = [
  { key: 'fcf_conversion', label: 'FCF Conversion', color: 'var(--cat-1)' },
  { key: 'leverage_headroom', label: 'Leverage Headroom', color: 'var(--cat-2)' },
  { key: 'ebitda_margin', label: 'EBITDA Margin', color: 'var(--cat-3)' },
  { key: 'ebitda_growth_stability', label: 'EBITDA Stability', color: 'var(--cat-4)' },
  { key: 'revenue_volatility', label: 'Revenue Predictability', color: 'var(--cat-5)' },
]

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-xs shadow-lg">
      <div className="font-medium text-[var(--text-primary)]">{d.label}</div>
      <div className="text-[var(--text-secondary)] mt-0.5">
        Sector percentile: <span className="tabular-nums text-[var(--text-primary)]">{d.pct?.toFixed(0)}</span>
      </div>
      <div className="text-[var(--text-secondary)]">
        Weight in score: <span className="tabular-nums text-[var(--text-primary)]">{(d.weight * 100).toFixed(0)}%</span>
      </div>
    </div>
  )
}

export default function ScoreBreakdown({ company }) {
  const data = COMPONENTS.map((c) => ({
    label: c.label,
    pct: company[`${c.key}_pct`] ?? 0,
    weight: company[`${c.key}_weight`] ?? 0,
    color: c.color,
  }))

  return (
    <div className="pt-1">
      <div className="text-xs text-[var(--text-muted)] mb-2">
        Sector-relative percentile per screening factor (0-100, higher = more attractive), weighted into the composite score.
      </div>
      <ResponsiveContainer width="100%" height={170}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }} barCategoryGap={10}>
          <CartesianGrid horizontal={false} stroke="var(--gridline)" />
          <XAxis
            type="number"
            domain={[0, 100]}
            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
            stroke="var(--baseline)"
          />
          <YAxis
            type="category"
            dataKey="label"
            width={150}
            tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
            stroke="var(--baseline)"
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
          <Bar dataKey="pct" radius={[0, 4, 4, 0]} maxBarSize={18}>
            {data.map((d) => (
              <Cell key={d.label} fill={d.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
