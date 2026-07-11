import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { rowsToObjects, useApi, type RowsPage } from '../api'
import EChart from '../charts/EChart'
import { dotWhisker, scatterOption, type CIItem } from '../charts/options'
import { EXPLAIN } from '../explain'
import { C } from '../theme'
import { Card, ChartTitle, EmptyState, PageHeader, Spinner } from '../ui'

const pct = (v: unknown) => `${(Number(v) * 100).toFixed(1)}%`

function CensusSection() {
  const rows = useApi<RowsPage>('/api/datasets/study3_sa_census/rows?page_size=500')
  const { scatter, top } = useMemo(() => {
    if (!rows.data) return { scatter: null, top: null }
    const objs = rowsToObjects(rows.data).filter((o) => o.mean_apr != null)
    const scatter = scatterOption({
      points: objs
        .filter((o) => o.shock_half_life_hours != null)
        .map((o) => ({
          x: Number(o.shock_half_life_hours),
          y: Number(o.mean_apr) * 100,
          name: String(o.market),
        })),
      xName: 'shock half-life (h)',
      yName: 'mean APR (%)',
    })
    const topItems = objs
      .sort((a, b) => Number(b.mean_apr) - Number(a.mean_apr))
      .slice(0, 15)
      .map(
        (o): CIItem => ({
          label: String(o.market),
          value: Number(o.mean_apr) * 100,
          lo: Number(o.mean_apr_ci_low) * 100,
          hi: Number(o.mean_apr_ci_high) * 100,
        }),
      )
    return { scatter, top: dotWhisker([{ name: 'mean APR', color: C.series[0], items: topItems }], 'mean APR (%)') }
  }, [rows.data])
  if (rows.loading) return <Spinner />
  if (rows.error) return <EmptyState error={rows.error} />
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <ChartTitle
          title="Funding census: size vs persistence (183 markets)"
          info={EXPLAIN.study3_census_scatter}
        />
        {scatter && <EChart option={scatter} height={380} />}
        <p className="mt-2 text-xs text-zinc-600">
          Half-life median 1.3h, max 9.9h — the 24h carry bar is structurally unreachable; 0/183
          markets are carry-relevant.
        </p>
      </Card>
      <Card>
        <ChartTitle title="Top mean APR with 95% CI" info={EXPLAIN.study3_census_top} />
        {top && <EChart option={top} height={380} />}
      </Card>
    </div>
  )
}

function ClockSection() {
  const rows = useApi<RowsPage>('/api/datasets/study3_sd_brackets/rows?page_size=500')
  const option = useMemo(() => {
    if (!rows.data) return null
    const objs = rowsToObjects(rows.data).filter((o) => o.group_type === 'all')
    if (!objs.length) return null
    const label = (o: Record<string, unknown>) => `${o.coverage_group} · ±${o.bracket_minutes}m`
    return dotWhisker(
      [
        {
          name: 'funding bracket',
          color: C.series[0],
          items: objs.map(
            (o): CIItem => ({
              label: label(o),
              value: Number(o.mean_return) * 1e4,
              lo: Number(o.ci_low) * 1e4,
              hi: Number(o.ci_high) * 1e4,
            }),
          ),
        },
        {
          name: 'baseline',
          color: C.baseline,
          items: objs.map(
            (o): CIItem => ({
              label: label(o),
              value: Number(o.baseline_mean_return) * 1e4,
              lo: Number(o.baseline_ci_low) * 1e4,
              hi: Number(o.baseline_ci_high) * 1e4,
            }),
          ),
        },
      ],
      'mean return (bps)',
    )
  }, [rows.data])
  if (rows.loading) return <Spinner />
  if (rows.error) return <EmptyState error={rows.error} />
  return (
    <Card>
      <ChartTitle
        title="Funding-clock brackets vs baseline (95% CI) — 12/12 do not separate"
        info={EXPLAIN.study3_clock}
      />
      {option ? <EChart option={option} height={420} /> : <EmptyState note="No 'all' group rows." />}
      <p className="mt-2 text-xs text-zinc-600">
        SKHX/SMSN use the full L4 window; the other eight markets are a 3.5-day recent-regime null
        only.
      </p>
    </Card>
  )
}

function SpreadsSection() {
  const rows = useApi<RowsPage>(
    '/api/datasets/study3_se_spreads/rows?page_size=100&sort=mean_abs_diff_apr&order=desc',
  )
  if (rows.loading) return <Spinner />
  if (rows.error) return <EmptyState error={rows.error} />
  const objs = rowsToObjects(rows.data!).slice(0, 12)
  return (
    <Card>
      <ChartTitle
        title="Cross-dex twin spreads — top funding differentials (0/57 pairs viable)"
        info={EXPLAIN.study3_spreads}
      />
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-zinc-800 text-zinc-500">
              {['pair', 'mean |Δ APR|', 'half-life (h)', '% time > maker BE', '% time > taker BE', 'basis p95 vs edge'].map((h) => (
                <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {objs.map((o) => (
              <tr key={String(o.pair_id)} className="border-b border-zinc-900 text-zinc-300">
                <td className="px-2 py-1.5 font-mono text-[11px]">{String(o.pair_id)}</td>
                <td className="px-2 py-1.5 font-mono text-[11px] tabular-nums">{pct(o.mean_abs_diff_apr)}</td>
                <td className="px-2 py-1.5 font-mono text-[11px] tabular-nums">{Number(o.persistence_half_life_hours).toFixed(2)}</td>
                <td className="px-2 py-1.5 font-mono text-[11px] tabular-nums">{pct(o.pct_time_gt_maker_breakeven)}</td>
                <td className="px-2 py-1.5 font-mono text-[11px] tabular-nums">{pct(o.pct_time_gt_taker_breakeven)}</td>
                <td className="px-2 py-1.5 font-mono text-[11px] tabular-nums text-rose-400">
                  {Number(o.basis_p95_abs_excursion) > Number(o.p95_diff_horizon_return) ? 'basis swamps edge' : 'edge survives'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-zinc-600">
        Basis is the scale-invariant log-ratio metric; all 57 pairs fail — basis p95 exceeds the
        persistence-horizon funding edge everywhere.
      </p>
    </Card>
  )
}

function HazardSection() {
  const rows = useApi<RowsPage>('/api/datasets/study3_sf_event_rates/rows?page_size=100')
  const option = useMemo(() => {
    if (!rows.data) return null
    const objs = rowsToObjects(rows.data)
      .filter((o) => o.analysis_cut === 'apr_bucket')
      .sort((a, b) => Number(a.bucket_order) - Number(b.bucket_order))
    if (!objs.length) return null
    return dotWhisker(
      [
        {
          name: 'event rate',
          color: C.series[0],
          items: objs.map(
            (o): CIItem => ({
              label: String(o.funding_bucket),
              value: Number(o.event_rate_per_market_hour),
              lo: Number(o.ci_low),
              hi: Number(o.ci_high),
            }),
          ),
        },
      ],
      'proxy events / market-hour',
    )
  }, [rows.data])
  if (rows.loading) return <Spinner />
  if (rows.error) return <EmptyState error={rows.error} />
  return (
    <Card>
      <ChartTitle
        title="Forced-flow event rate by funding bucket (95% CI)"
        info={EXPLAIN.study3_hazard}
      />
      {option ? <EChart option={option} height={320} /> : <EmptyState note="No apr_bucket rows." />}
      <p className="mt-2 text-xs text-zinc-600">
        Per-market rate-ratio CIs include 1 — funding does not time forced flow within a market.
      </p>
    </Card>
  )
}

export default function Study3() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Study 3 — HIP-3 funding deep dive"
        sub="Funding is large but efficiently priced: no carry, no clock edge, no spread arb."
      />
      <CensusSection />
      <Card>
        <div className="text-sm text-zinc-400">
          Carry backtest results (equity, drawdown, attribution) live in the{' '}
          <Link className="text-cyan-400 hover:underline" to="/backtests">
            Backtests viewer
          </Link>
          .
        </div>
      </Card>
      <ClockSection />
      <SpreadsSection />
      <HazardSection />
    </div>
  )
}
