import { useMemo, useState } from 'react'
import {
  useApi,
  type Cell,
  type DatasetInfo,
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

export default function DataBrowser() {
  const [selected, setSelected] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<{ col: string; desc: boolean } | null>(null)
  const [xCol, setXCol] = useState('')
  const [yCol, setYCol] = useState('')

  const datasets = useApi<DatasetInfo[]>('/api/datasets')
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

  const select = (name: string) => {
    setSelected(name)
    setPage(1)
    setSort(null)
    setXCol('')
    setYCol('')
  }

  return (
    <div>
      <PageHeader title="Data Browser" sub="Every parquet in data/reports/ — schema, rows, quick plots." />
      <div className="flex gap-6">
        <Card className="max-h-[80vh] w-80 shrink-0 overflow-y-auto">
          {datasets.loading && <Spinner />}
          {datasets.error && <EmptyState error={datasets.error} />}
          {datasets.data?.map((d) => (
            <button
              key={d.name}
              onClick={() => select(d.name)}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm ${
                selected === d.name
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:bg-zinc-900'
              }`}
            >
              <div className="truncate font-medium">{d.name}</div>
              <div className="text-xs text-zinc-600">
                {d.columns} cols · {fmtBytes(d.size_bytes)}
              </div>
            </button>
          ))}
        </Card>
        <div className="min-w-0 flex-1 space-y-6">
          {!selected && <EmptyState note="Select a dataset on the left." />}
          {selected && rows.loading && <Spinner />}
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
