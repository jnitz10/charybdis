import { useState } from 'react'
import { useApi, type BacktestDetail, type BacktestEntry } from '../api'
import EChart from '../charts/EChart'
import { monthlyHeatmap } from '../charts/options'
import TimeSeriesChart from '../charts/TimeSeriesChart'
import { EXPLAIN } from '../explain'
import { Card, ChartTitle, EmptyState, PageHeader, Spinner, StatCard } from '../ui'

const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${(v * 100).toFixed(1)}%`

export default function Backtests() {
  const list = useApi<BacktestEntry[]>('/api/backtests')
  const [selected, setSelected] = useState<string | null>(null)
  const activeId = selected ?? list.data?.[0]?.id ?? null
  const detail = useApi<BacktestDetail>(activeId ? `/api/backtests/${activeId}` : null)

  if (list.loading) return <Spinner />
  if (list.error) return <EmptyState error={list.error} />
  if (!list.data?.length)
    return <EmptyState note="No backtests registered (study3_sc_backtest parquet missing)." />

  const d = detail.data
  const summary = d?.summary as Record<string, number> | null | undefined

  return (
    <div>
      <PageHeader title="Backtests" sub="Generic performance viewer — register a parquet, get the full readout." />
      <div className="mb-4 flex flex-wrap gap-2">
        {list.data.map((b) => (
          <button
            key={b.id}
            onClick={() => setSelected(b.id)}
            className={`rounded-full border px-3 py-1.5 text-sm ${
              b.id === activeId
                ? 'border-cyan-500 bg-cyan-500/10 text-cyan-300'
                : 'border-zinc-800 text-zinc-400 hover:border-zinc-600'
            }`}
          >
            {b.strategy}
          </button>
        ))}
      </div>
      {detail.loading && <Spinner />}
      {detail.error && <EmptyState error={detail.error} />}
      {d && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Total return"
              value={pct(d.stats.total_return)}
              tone={d.stats.total_return >= 0 ? 'up' : 'down'}
              sub={
                summary
                  ? `report CI [${pct(summary.return_ci_low)}, ${pct(summary.return_ci_high)}]`
                  : undefined
              }
            />
            <StatCard
              label="Sharpe"
              value={d.stats.sharpe?.toFixed(2) ?? '—'}
              sub={summary ? `report: ${summary.sharpe?.toFixed(2)}` : undefined}
            />
            <StatCard label="Max drawdown" value={pct(d.stats.max_drawdown)} tone="down" />
            <StatCard
              label="Periods"
              value={String(d.stats.periods)}
              sub={`${new Date(d.stats.start * 1000).toISOString().slice(0, 10)} → ${new Date(d.stats.end * 1000).toISOString().slice(0, 10)}`}
            />
          </div>
          {summary && (
            <div className="grid grid-cols-3 gap-4">
              <StatCard label="Funding PnL" value={pct(summary.funding_pnl)} tone={summary.funding_pnl >= 0 ? 'up' : 'down'} />
              <StatCard label="Price PnL" value={pct(summary.price_pnl)} tone={summary.price_pnl >= 0 ? 'up' : 'down'} />
              <StatCard label="Cost PnL" value={pct(summary.cost_pnl)} tone="down" />
            </div>
          )}
          <Card>
            <ChartTitle title="Equity (cumulative net return)" info={EXPLAIN.backtests_equity} />
            <TimeSeriesChart points={d.equity} percent height={300} />
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <ChartTitle title="Drawdown" info={EXPLAIN.backtests_drawdown} />
              <TimeSeriesChart points={d.drawdown} percent height={240} />
            </Card>
            <Card>
              <ChartTitle title="Rolling Sharpe (30 periods)" info={EXPLAIN.backtests_sharpe} />
              {d.rolling_sharpe.length ? (
                <TimeSeriesChart points={d.rolling_sharpe} height={240} />
              ) : (
                <div className="py-10 text-center text-sm text-zinc-600">
                  Not enough periods for a 30-period window.
                </div>
              )}
            </Card>
          </div>
          <Card>
            <ChartTitle title="Monthly returns" info={EXPLAIN.backtests_monthly} />
            <EChart option={monthlyHeatmap(d.monthly)} height={80 + 40 * new Set(d.monthly.map((m) => m.ym.slice(0, 4))).size} />
          </Card>
        </div>
      )}
    </div>
  )
}
