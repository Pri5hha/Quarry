import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, Tooltip, ReferenceLine, LabelList, ResponsiveContainer } from 'recharts'
import { Loading } from './Primitives'

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-xs shadow-lg">
      <div className="font-medium text-[var(--text-primary)]">{d.label}</div>
      <div className="text-[var(--text-secondary)] mt-0.5">
        Value: <span className="tabular-nums text-[var(--text-primary)]">{d.value_pct ?? '—'}</span> percentile
      </div>
      <div className="text-[var(--text-secondary)]">
        Contribution: <span className={`tabular-nums font-medium ${d.shap_value >= 0 ? 'text-[var(--status-good)]' : 'text-[var(--status-critical)]'}`}>
          {d.shap_value >= 0 ? '+' : ''}{d.shap_value.toFixed(2)}
        </span>
      </div>
    </div>
  )
}

function ValueLabel(props) {
  const { x, y, width, height, value } = props
  const positive = value >= 0
  // Positive labels sit just right of their own bar's tip (open space, so the
  // bar's actual length stays visible). Negative labels anchor at the fixed
  // zero line instead of their own (variable, sometimes very long) tip, so
  // they never drift left into the row-label column.
  const labelX = positive ? x + width + 6 : (x + width) - 6
  return (
    <text
      x={labelX}
      y={y + height / 2}
      dy={4}
      fontSize={11}
      textAnchor={positive ? 'start' : 'end'}
      fill="var(--text-primary)"
      className="tabular-nums font-medium"
    >
      {positive ? '+' : ''}{value.toFixed(1)}
    </text>
  )
}

export default function ShapBreakdown({ explanation, loading }) {
  if (loading) return <Loading label="Computing SHAP breakdown..." />
  if (!explanation) {
    return <div className="text-sm text-[var(--text-muted)] py-8 text-center">No explanation available.</div>
  }

  const data = explanation.contributions.map((c) => ({ ...c }))

  return (
    <div>
      <div className="flex items-baseline justify-between mb-3">
        <div className="text-xs text-[var(--text-muted)]">
          Base (average company): <span className="tabular-nums text-[var(--text-secondary)]">{explanation.base_value}</span>
        </div>
        <div className="text-xs text-[var(--text-muted)]">
          Predicted score: <span className="tabular-nums font-semibold text-[var(--accent-strong)]">{explanation.predicted_score}</span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={190}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 44, bottom: 4, left: 44 }} barCategoryGap={12}>
          <CartesianGrid horizontal={false} stroke="var(--gridline)" />
          <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--baseline)" />
          <YAxis type="category" dataKey="label" width={140} tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} stroke="var(--baseline)" />
          <ReferenceLine x={0} stroke="var(--baseline)" />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
          <Bar dataKey="shap_value" radius={3} maxBarSize={18}>
            {data.map((d) => (
              <Cell key={d.ratio} fill={d.shap_value >= 0 ? 'var(--status-good)' : 'var(--status-critical)'} />
            ))}
            <LabelList dataKey="shap_value" content={ValueLabel} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 mt-1 text-xs text-[var(--text-muted)]">
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: 'var(--status-good)' }} /> Pushed score up</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: 'var(--status-critical)' }} /> Pushed score down</span>
      </div>
    </div>
  )
}
