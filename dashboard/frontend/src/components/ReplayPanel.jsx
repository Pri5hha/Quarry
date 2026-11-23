import { useEffect, useMemo, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, Dot, ResponsiveContainer } from 'recharts'
import { api } from '../api'
import { Card, StatTile, Loading, ErrorState, Badge, fmtNum } from './Primitives'
import ShapBreakdown from './ShapBreakdown'

const PREFERRED_DEFAULTS = ['RCM', 'SYNH', 'UNVR', 'CDK', 'FOCS']

function ScrubDot(props) {
  const { cx, cy, index, isLast } = props
  if (!isLast) return <Dot cx={cx} cy={cy} r={3} fill="var(--accent)" strokeWidth={0} />
  return (
    <Dot cx={cx} cy={cy} r={5.5} fill="var(--accent-strong)" stroke="var(--surface-1)" strokeWidth={2} />
  )
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-xs shadow-lg">
      <div className="font-medium text-[var(--text-primary)]">{d.date}</div>
      <div className="text-[var(--text-secondary)]">Score: <span className="tabular-nums text-[var(--text-primary)]">{d.score}</span></div>
      <div className="text-[var(--text-secondary)]">Percentile: <span className="tabular-nums text-[var(--text-primary)]">{d.rank_percentile.toFixed(1)}</span></div>
    </div>
  )
}

export default function ReplayPanel() {
  const [targets, setTargets] = useState(null);
  const [error, setError] = useState(null);

  const [ticker, setTicker] = useState(null);
  const [timeline, setTimeline] = useState(null); // null = not loaded, [] not used; use 'unavailable' sentinel
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineUnavailable, setTimelineUnavailable] = useState(false);

  const [shapByDate, setShapByDate] = useState({});
  const [shapLoading, setShapLoading] = useState(false);

  const [scrubberIndex, setScrubberIndex] = useState(0);

  useEffect(() => {
    api.backtest()
      .then((d) => {
        setTargets(d.targets);
        const preferred = PREFERRED_DEFAULTS.find((t) => d.targets.some((x) => x.ticker === t));
        setTicker(preferred || d.targets[0]?.ticker || null);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setTimeline(null);
    setTimelineUnavailable(false);
    setShapByDate({});
    setTimelineLoading(true);

    api.backtestTimeline(ticker).then(async (entry) => {
      if (cancelled) return;
      if (!entry) {
        setTimelineUnavailable(true);
        setTimelineLoading(false);
        return;
      }
      setTimeline(entry);
      setScrubberIndex(entry.points.length - 1);
      setTimelineLoading(false);

      setShapLoading(true);
      const results = await Promise.all(
        entry.points.map((p) => api.explainAtDate(ticker, p.date).then((r) => [p.date, r]))
      );
      if (cancelled) return;
      setShapByDate(Object.fromEntries(results));
      setShapLoading(false);
    }).catch((e) => {
      if (!cancelled) { setError(e.message); setTimelineLoading(false); }
    });

    return () => { cancelled = true; };
  }, [ticker]);

  const chartData = useMemo(() => {
    if (!timeline) return [];
    return timeline.points.slice(0, scrubberIndex + 1).map((p) => ({
      ...p,
      x: -p.months_before_deal,
    }));
  }, [timeline, scrubberIndex]);

  const xDomain = useMemo(() => {
    if (!timeline) return [-36, 0];
    const maxBack = Math.max(...timeline.points.map((p) => p.months_before_deal));
    return [-maxBack, 0];
  }, [timeline]);

  const currentPoint = timeline?.points[scrubberIndex];
  const currentExplanation = currentPoint ? shapByDate[currentPoint.date] : null;
  const topPct = currentPoint ? Math.max(1, Math.round(100 - currentPoint.rank_percentile)) : null;

  if (error) return <ErrorState message={error} />
  if (!targets) return <Loading label="Loading historical targets..." />

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="Backtest Replay Timeline"
        subtitle="Watch a real LBO target's Quarry score evolve quarter by quarter in the 3 years before its actual buyout -- proving the model would have flagged it before the deal, not just after."
      >
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-5">
          <select
            value={ticker || ''}
            onChange={(e) => setTicker(e.target.value)}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
          >
            {targets.map((t) => (
              <option key={t.ticker} value={t.ticker}>{t.ticker} — {t.name}</option>
            ))}
          </select>
          {timeline && (
            <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
              <Badge tone="accent">{timeline.sector}</Badge>
              <span>Acquired by {timeline.acquirer}</span>
              <span className="text-[var(--text-muted)]">· deal announced {timeline.deal_announce_date}</span>
            </div>
          )}
        </div>

        {timelineLoading && <Loading label="Building score replay..." />}

        {timelineUnavailable && (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-4 py-6 text-sm text-[var(--text-muted)] text-center">
            No quarterly replay available for this company (insufficient SEC quarterly filing history under
            the tags this demo looks for). Try another target from the dropdown.
          </div>
        )}

        {timeline && currentPoint && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5">
              <StatTile label="As of" value={currentPoint.date} />
              <StatTile label="Score" value={fmtNum(currentPoint.score)} accent />
              <StatTile
                label="Rank"
                value={`Top ${topPct}%`}
                detail={`percentile ${currentPoint.rank_percentile.toFixed(1)} of ${currentPoint.universe_size} companies`}
              />
            </div>

            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke="var(--gridline)" />
                <XAxis
                  type="number" dataKey="x" domain={xDomain}
                  tickFormatter={(v) => (v === 0 ? 'Deal' : `${v}mo`)}
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--baseline)"
                />
                <YAxis domain={[0, 100]} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--baseline)" />
                <Tooltip content={<ChartTooltip />} />
                <ReferenceLine
                  x={0} stroke="var(--accent)" strokeDasharray="4 3"
                  label={{ value: 'Deal announced', position: 'insideTopRight', fill: 'var(--accent-strong)', fontSize: 11 }}
                />
                <Line
                  type="monotone" dataKey="score" stroke="var(--accent)" strokeWidth={2}
                  dot={(props) => <ScrubDot key={props.index} {...props} isLast={props.index === chartData.length - 1} />}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>

            <div className="mt-3">
              <input
                type="range" min={0} max={timeline.points.length - 1} value={scrubberIndex}
                onChange={(e) => setScrubberIndex(Number(e.target.value))}
                className="w-full accent-[var(--accent)]"
              />
              <div className="flex justify-between text-[10px] text-[var(--text-muted)] mt-1">
                <span>{timeline.points[0].date} (36mo before)</span>
                <span>{timeline.points[timeline.points.length - 1].date} (closest to deal)</span>
              </div>
            </div>
          </>
        )}
      </Card>

      {timeline && currentPoint && (
        <Card
          title="Why did the score move?"
        >
          <ShapBreakdown explanation={currentExplanation} loading={shapLoading && !currentExplanation} />
        </Card>
      )}
    </div>
  )
}
