import { useMemo, useState } from 'react'
import {
  useApi,
  type CandlePayload,
  type CandleSource,
  type IndicatorMeta,
} from '../api'
import CandleChart, { type OverlaySeries, type Pane } from '../charts/CandleChart'
import { EXPLAIN } from '../explain'
import { Card, EmptyState, InfoPopover, PageHeader, Select, Spinner } from '../ui'

function defaultSpec(m: IndicatorMeta): string {
  const params = Object.values(m.params)
  return params.length ? `${m.name}:${params.join(':')}` : m.name
}

export default function ChartLab() {
  const sources = useApi<CandleSource[]>('/api/candles/sources')
  const registry = useApi<IndicatorMeta[]>('/api/indicators')

  const [sourceId, setSourceId] = useState('')
  const [market, setMarket] = useState('')
  const [specs, setSpecs] = useState<string[]>([])
  const [draft, setDraft] = useState('')

  const source = sources.data?.find((s) => s.id === sourceId) ?? sources.data?.[0]
  const activeMarket = source?.markets.includes(market) ? market : source?.markets[0]

  const candlesPath =
    source && activeMarket
      ? `/api/candles?source=${source.id}&market=${encodeURIComponent(activeMarket)}` +
        (specs.length ? `&ind=${encodeURIComponent(specs.join(','))}` : '')
      : null
  const candles = useApi<CandlePayload>(candlesPath)

  const { overlays, panes } = useMemo(() => {
    const overlays: OverlaySeries[] = []
    const panes: Pane[] = []
    for (const ind of candles.data?.indicators ?? []) {
      const series = Object.entries(ind.series).map(([name, values]) => ({ name, values }))
      if (ind.display === 'overlay') overlays.push(...series)
      else panes.push({ name: ind.id, series })
    }
    return { overlays, panes }
  }, [candles.data])

  const addDraft = () => {
    const s = draft.trim()
    if (s && !specs.includes(s)) setSpecs([...specs, s])
    setDraft('')
  }

  if (sources.loading || registry.loading) return <Spinner />
  if (sources.error) return <EmptyState error={sources.error} />
  if (!sources.data?.length)
    return <EmptyState note="No candle sources present (study3_candles_1h/1d parquet missing)." />

  return (
    <div>
      <PageHeader title="Chart Lab" sub="Candles + indicators over any harvested market." />
      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-4">
          <InfoPopover title="Sources, indicators, symbols">{EXPLAIN.chartlab}</InfoPopover>
          <Select
            label="source"
            value={source!.id}
            options={sources.data.map((s) => s.id)}
            onChange={(v) => setSourceId(v)}
          />
          <Select
            label="market"
            value={activeMarket ?? ''}
            options={source!.markets}
            onChange={setMarket}
          />
          <div className="flex items-center gap-2">
            <Select label="add indicator" value="" options={['', ...(registry.data ?? []).map(defaultSpec)]} onChange={(v) => v && setSpecs((p) => (p.includes(v) ? p : [...p, v]))} />
            <input
              className="w-36 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200 outline-none focus:border-cyan-500"
              placeholder="custom: ema:50"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addDraft()}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {specs.map((s) => (
              <span
                key={s}
                className="flex items-center gap-1 rounded-full border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs text-zinc-300"
              >
                {s}
                <button
                  className="text-zinc-500 hover:text-rose-400"
                  onClick={() => setSpecs(specs.filter((x) => x !== s))}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>
      </Card>
      {candles.loading && !candles.data && <Spinner />}
      {candles.error && <EmptyState error={candles.error} />}
      {candles.data && (
        <Card>
          <div className="mb-2 text-sm text-zinc-400">
            {candles.data.market} · {candles.data.interval} · {candles.data.time.length} bars
          </div>
          {candles.data.warnings?.length > 0 && (
            <div className="mb-2 text-xs text-amber-500">
              {candles.data.warnings.join(' · ')}
            </div>
          )}
          <CandleChart
            time={candles.data.time}
            open={candles.data.open}
            high={candles.data.high}
            low={candles.data.low}
            close={candles.data.close}
            overlays={overlays}
            panes={panes}
            resetKey={`${candles.data.source}:${candles.data.market}`}
            height={560}
          />
        </Card>
      )}
    </div>
  )
}
