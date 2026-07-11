import { useMemo, useState } from 'react'
import {
  useApi,
  type Cell,
  type DatasetInfo,
  type RawFeed,
  type RawFileEntry,
  type RawMarket,
  type RawPreview,
  type RowsPage,
  type SchemaCol,
} from '../api'
import EChart from '../charts/EChart'
import { scatterOption } from '../charts/options'
import { Card, EmptyState, PageHeader, Select, Spinner } from '../ui'

const PAGE_SIZE = 50

function fmtBytes(n: number) {
  if (n > 1e9) return `${(n / 1e9).toFixed(1)} GB`
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`
  return `${(n / 1e3).toFixed(1)} KB`
}

function fmtCell(v: Cell) {
  if (v === null) return '∅'
  if (typeof v === 'number' && !Number.isInteger(v)) return v.toPrecision(6)
  return String(v)
}

function RowsTable({ columns, rows }: { columns: string[]; rows: Cell[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-zinc-800 text-zinc-500">
            {columns.map((c) => (
              <th key={c} className="whitespace-nowrap px-2 py-2 font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-zinc-900 text-zinc-300">
              {r.map((v, j) => (
                <td key={j} className="whitespace-nowrap px-2 py-1.5 tabular-nums">
                  {fmtCell(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RawMarketView({ feed, market }: { feed: string; market: string }) {
  const files = useApi<RawFileEntry[]>(
    `/api/raw/files?feed=${feed}&market=${encodeURIComponent(market)}`,
  )
  const [partition, setPartition] = useState<string | null>(null)
  const sorted = useMemo(
    () => (files.data ?? []).slice().sort((a, b) => b.partition.localeCompare(a.partition)),
    [files.data],
  )
  const active = sorted.some((f) => f.partition === partition) ? partition! : sorted[0]?.partition
  const preview = useApi<RawPreview>(
    active
      ? `/api/raw/preview?feed=${feed}&partition=${encodeURIComponent(active)}&market=${encodeURIComponent(market)}&limit=100`
      : null,
  )
  if (files.loading && !files.data) return <Spinner />
  if (files.error) return <EmptyState error={files.error} />
  if (!sorted.length) return <EmptyState note="No files for this market." />
  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-medium text-zinc-300">
          {market} · {sorted.length} files
        </div>
        <Select
          label="partition"
          value={active ?? ''}
          options={sorted.map((f) => f.partition)}
          onChange={setPartition}
        />
      </div>
      {preview.loading && !preview.data && <Spinner />}
      {preview.error && <EmptyState error={preview.error} />}
      {preview.data && (
        <>
          <div className="mb-2 text-xs text-zinc-500">
            {preview.data.day} · era {preview.data.era} · {preview.data.total.toLocaleString()}{' '}
            rows · {fmtBytes(preview.data.size_bytes)} gzip · showing first{' '}
            {preview.data.rows.length}
          </div>
          <RowsTable
            columns={preview.data.columns.map((c) => c.name)}
            rows={preview.data.rows}
          />
        </>
      )}
    </Card>
  )
}

function RawFeedView({ feed }: { feed: string }) {
  const markets = useApi<RawMarket[]>(`/api/raw/markets?feed=${feed}`)
  const [market, setMarket] = useState<string | null>(null)
  const active =
    markets.data?.some((m) => m.market === market) && market
      ? market
      : markets.data?.length === 1
        ? markets.data[0].market
        : null
  if (markets.loading && !markets.data) return <Spinner />
  if (markets.error) return <EmptyState error={markets.error} />
  return (
    <div className="space-y-6">
      <Card>
        <div className="mb-3 text-sm font-medium text-zinc-300">
          T-{feed} — {markets.data!.length} market{markets.data!.length === 1 ? '' : 's'}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-zinc-800 text-zinc-500">
                {['market', 'files', 'size', 'coverage', 'eras'].map((h) => (
                  <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {markets.data!.map((m) => (
                <tr
                  key={m.market}
                  onClick={() => setMarket(m.market)}
                  className={`cursor-pointer border-b border-zinc-900 ${
                    active === m.market
                      ? 'bg-zinc-800/60 text-zinc-100'
                      : 'text-zinc-300 hover:bg-zinc-900'
                  }`}
                >
                  <td className="px-2 py-1.5 font-medium">{m.market}</td>
                  <td className="px-2 py-1.5 tabular-nums">{m.files}</td>
                  <td className="px-2 py-1.5 tabular-nums">{fmtBytes(m.size_bytes)}</td>
                  <td className="px-2 py-1.5 tabular-nums">
                    {m.first_day} → {m.last_day}
                  </td>
                  <td className="px-2 py-1.5">{m.eras.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!active && (
          <div className="mt-3 text-xs text-zinc-600">
            Pick a market to preview its files. Trade markets can also be charted in the Chart
            Lab (raw_trades_* sources).
          </div>
        )}
      </Card>
      {active && <RawMarketView key={`${feed}:${active}`} feed={feed} market={active} />}
    </div>
  )
}

type Sel = { kind: 'dataset'; name: string } | { kind: 'feed'; feed: string } | null

export default function DataBrowser() {
  const [sel, setSel] = useState<Sel>(null)
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<{ col: string; desc: boolean } | null>(null)
  const [xCol, setXCol] = useState('')
  const [yCol, setYCol] = useState('')

  const datasets = useApi<DatasetInfo[]>('/api/datasets')
  const feeds = useApi<RawFeed[]>('/api/raw/feeds')

  const selected = sel?.kind === 'dataset' ? sel.name : null
  const schema = useApi<{ name: string; columns: SchemaCol[] }>(
    selected ? `/api/datasets/${selected}/schema` : null,
  )
  const rowsPath = selected
    ? `/api/datasets/${selected}/rows?page=${page}&page_size=${PAGE_SIZE}` +
      (sort ? `&sort=${sort.col}&order=${sort.desc ? 'desc' : 'asc'}` : '')
    : null
  const rows = useApi<RowsPage>(rowsPath)

  const numericCols = useMemo(
    () =>
      (schema.data?.columns ?? [])
        .filter((c) => c.dtype.startsWith('Float') || c.dtype.startsWith('Int') || c.dtype.startsWith('UInt'))
        .map((c) => c.name),
    [schema.data],
  )

  const plotPath =
    selected && xCol && yCol
      ? `/api/datasets/${selected}/rows?page_size=500&sort=${xCol}`
      : null
  const plotRows = useApi<RowsPage>(plotPath)
  const plotOption = useMemo(() => {
    if (!plotRows.data || !xCol || !yCol) return null
    const xi = plotRows.data.columns.indexOf(xCol)
    const yi = plotRows.data.columns.indexOf(yCol)
    const points = plotRows.data.rows
      .filter((r) => typeof r[xi] === 'number' && typeof r[yi] === 'number')
      .map((r, i) => ({ x: r[xi] as number, y: r[yi] as number, name: `row ${i}` }))
    return scatterOption({ points, xName: xCol, yName: yCol })
  }, [plotRows.data, xCol, yCol])

  const selectDataset = (name: string) => {
    setSel({ kind: 'dataset', name })
    setPage(1)
    setSort(null)
    setXCol('')
    setYCol('')
  }

  return (
    <div>
      <PageHeader
        title="Data Browser"
        sub="Research tables (data/reports/ + loose parquets) and the raw CoinAPI flat-file archive (data/T-*)."
      />
      <div className="flex gap-6">
        <Card className="max-h-[80vh] w-80 shrink-0 overflow-y-auto">
          <div className="px-3 pb-1 pt-2 text-xs font-medium uppercase tracking-wider text-zinc-600">
            Research tables
          </div>
          {datasets.loading && <Spinner />}
          {datasets.error && <EmptyState error={datasets.error} />}
          {datasets.data?.map((d) => (
            <button
              key={d.name}
              onClick={() => selectDataset(d.name)}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm ${
                selected === d.name
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:bg-zinc-900'
              }`}
            >
              <div className="truncate font-medium">{d.name}</div>
              <div className="text-xs text-zinc-600">
                {d.kind === 'parts' ? `${d.files} parts · ` : ''}
                {d.columns} cols · {fmtBytes(d.size_bytes)}
              </div>
            </button>
          ))}
          <div className="px-3 pb-1 pt-4 text-xs font-medium uppercase tracking-wider text-zinc-600">
            Raw CoinAPI archive
          </div>
          {feeds.loading && <Spinner />}
          {feeds.error && <EmptyState error={feeds.error} />}
          {feeds.data?.length === 0 && (
            <div className="px-3 py-2 text-xs text-zinc-600">No T-* feeds under data/.</div>
          )}
          {feeds.data?.map((f) => (
            <button
              key={f.feed}
              onClick={() => setSel({ kind: 'feed', feed: f.feed })}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm ${
                sel?.kind === 'feed' && sel.feed === f.feed
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:bg-zinc-900'
              }`}
            >
              <div className="truncate font-medium">T-{f.feed}</div>
              <div className="text-xs text-zinc-600">
                {f.partitions} partitions · {f.markets} markets · {fmtBytes(f.size_bytes)}
              </div>
            </button>
          ))}
        </Card>
        <div className="min-w-0 flex-1 space-y-6">
          {!sel && <EmptyState note="Select a table or raw feed on the left." />}
          {sel?.kind === 'feed' && <RawFeedView key={sel.feed} feed={sel.feed} />}
          {selected && rows.loading && !rows.data && <Spinner />}
          {selected && rows.error && <EmptyState error={rows.error} />}
          {selected && rows.data && (
            <>
              <Card>
                <div className="mb-3 flex items-center justify-between">
                  <div className="text-sm text-zinc-400">
                    {rows.data.total.toLocaleString()} rows
                  </div>
                  <div className="flex items-center gap-3 text-sm text-zinc-400">
                    <button
                      className="rounded-md border border-zinc-800 px-2 py-1 disabled:opacity-40"
                      disabled={page <= 1}
                      onClick={() => setPage(page - 1)}
                    >
                      ← Prev
                    </button>
                    <span>
                      page {rows.data.page} / {Math.max(1, Math.ceil(rows.data.total / PAGE_SIZE))}
                    </span>
                    <button
                      className="rounded-md border border-zinc-800 px-2 py-1 disabled:opacity-40"
                      disabled={page * PAGE_SIZE >= rows.data.total}
                      onClick={() => setPage(page + 1)}
                    >
                      Next →
                    </button>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-zinc-800 text-zinc-500">
                        {rows.data.columns.map((c) => (
                          <th
                            key={c}
                            className="cursor-pointer whitespace-nowrap px-2 py-2 font-medium hover:text-zinc-300"
                            onClick={() =>
                              setSort(
                                sort?.col === c
                                  ? { col: c, desc: !sort.desc }
                                  : { col: c, desc: false },
                              )
                            }
                          >
                            {c}
                            {sort?.col === c ? (sort.desc ? ' ↓' : ' ↑') : ''}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.data.rows.map((r, i) => (
                        <tr key={i} className="border-b border-zinc-900 text-zinc-300">
                          {r.map((v, j) => (
                            <td key={j} className="whitespace-nowrap px-2 py-1.5 tabular-nums">
                              {fmtCell(v)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
              {numericCols.length >= 2 && (
                <Card>
                  <div className="mb-3 flex items-center gap-4">
                    <span className="text-sm font-medium text-zinc-300">Quick plot</span>
                    <Select label="x" value={xCol} options={['', ...numericCols]} onChange={setXCol} />
                    <Select label="y" value={yCol} options={['', ...numericCols]} onChange={setYCol} />
                  </div>
                  {plotOption ? (
                    <EChart option={plotOption} height={360} />
                  ) : (
                    <div className="py-8 text-center text-sm text-zinc-600">
                      Pick x and y columns (first 500 rows plotted).
                    </div>
                  )}
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
