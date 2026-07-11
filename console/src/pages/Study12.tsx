import { useMemo, useState } from 'react'
import { rowsToObjects, useApi, type RowsPage, type Study1Markout } from '../api'
import EChart from '../charts/EChart'
import { dotWhisker, lineOption, type CIItem } from '../charts/options'
import { C } from '../theme'
import { Card, EmptyState, PageHeader, Select, Spinner } from '../ui'

function Study1Section() {
  const markout = useApi<Study1Markout>('/api/study1/markout')
  const [market, setMarket] = useState('')
  if (markout.loading) return <Spinner />
  if (markout.error) return <EmptyState error={markout.error} />
  const d = markout.data!
  const active = d.markets.includes(market) ? market : d.markets[0]
  const series = d.segments.map((seg) => ({
    name: seg,
    data: d.horizons.map(
      (h) =>
        d.cells.find((c) => c.market === active && c.segment === seg && c.horizon === h)
          ?.mean_bps ?? null,
    ),
  }))
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-medium text-zinc-300">
          Net maker markout by horizon and session
        </div>
        <Select label="market" value={active} options={d.markets} onChange={setMarket} />
      </div>
      <EChart option={lineOption({ categories: d.horizons, series, yName: 'net markout (bps)' })} height={360} />
      <p className="mt-2 text-xs text-zinc-600">
        Stale quotes excluded. L2 fill simulation is an optimistic upper bound (no cancel/priority
        visibility). Verdict: off-hours is not better than RTH — CIs overlap in 8/8 markets.
      </p>
    </Card>
  )
}

function Study2Section() {
  const rows = useApi<RowsPage>(
    '/api/datasets/forced_flow_vs_baseline_markout_proxy/rows?page_size=500',
  )
  const [horizon, setHorizon] = useState('30s')
  const { horizons, option } = useMemo(() => {
    if (!rows.data) return { horizons: [] as string[], option: null }
    const objs = rowsToObjects(rows.data)
    const horizons = [...new Set(objs.map((o) => String(o.horizon)))]
    const groups = ['forced-flow', 'baseline'].map((wt, i) => ({
      name: wt,
      color: i === 0 ? C.series[0] : C.baseline,
      items: objs
        .filter((o) => o.horizon === horizon && String(o.window_type).includes(wt === 'forced-flow' ? 'forced' : 'baseline'))
        .map(
          (o): CIItem => ({
            label: String(o.market),
            value: Number(o.point_estimate_bps),
            lo: Number(o.ci_low_bps),
            hi: Number(o.ci_high_bps),
          }),
        ),
    }))
    const valid = groups.every((g) => g.items.length > 0)
    return {
      horizons,
      option: valid ? dotWhisker(groups, 'net markout (bps)') : null,
    }
  }, [rows.data, horizon])
  if (rows.loading) return <Spinner />
  if (rows.error) return <EmptyState error={rows.error} />
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-medium text-zinc-300">
          Forced-flow proxy vs matched baseline (95% CI)
        </div>
        <Select label="horizon" value={horizon} options={horizons} onChange={setHorizon} />
      </div>
      {option ? <EChart option={option} height={300} /> : <EmptyState note="No rows for this horizon." />}
      <p className="mt-2 text-xs text-zinc-600">
        All events are heuristic proxy tags (0 confirmed liquidations in HLSYSTEMEVENTS). Post
        2026-06-18 quote poisoning drops 39.5% of windows; the comparison is confounded and
        conservative.
      </p>
    </Card>
  )
}

export default function Study12() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Studies 1–2 — Markout"
        sub="Off-hours maker markout (Study 1) and forced-flow proxy vs baseline (Study 2)."
      />
      <Study1Section />
      <Study2Section />
    </div>
  )
}
