import { useEffect, useState } from 'react'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) {
    let detail = r.statusText
    try {
      detail = (await r.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(r.status, detail)
  }
  return r.json() as Promise<T>
}

export function useApi<T>(path: string | null) {
  const [state, setState] = useState<{ data?: T; error?: ApiError; loading: boolean }>({
    loading: path !== null,
  })
  useEffect(() => {
    if (path === null) {
      setState({ loading: false })
      return
    }
    let live = true
    setState({ loading: true })
    apiGet<T>(path).then(
      (data) => live && setState({ data, loading: false }),
      (error: ApiError) => live && setState({ error, loading: false }),
    )
    return () => {
      live = false
    }
  }, [path])
  return state
}

export interface DatasetInfo {
  name: string
  columns: number
  size_bytes: number
  mtime: number
}
export interface SchemaCol {
  name: string
  dtype: string
}
export type Cell = string | number | boolean | null
export interface RowsPage {
  total: number
  page: number
  page_size: number
  columns: string[]
  rows: Cell[][]
}
export interface IndicatorMeta {
  name: string
  params: Record<string, number>
  display: 'overlay' | 'pane'
}
export interface CandleSource {
  id: string
  interval: string
  markets: string[]
}
export interface CandlePayload {
  source: string
  market: string
  interval: string
  time: number[]
  open: number[]
  high: number[]
  low: number[]
  close: number[]
  volume: number[]
  indicators: {
    id: string
    name: string
    display: 'overlay' | 'pane'
    series: Record<string, (number | null)[]>
  }[]
}
export interface BacktestEntry {
  id: string
  source: string
  strategy: string
  title: string
}
export interface TimePoint {
  t: number
  v: number
}
export interface BacktestDetail {
  id: string
  title: string
  stats: {
    total_return: number
    sharpe: number | null
    max_drawdown: number
    periods: number
    start: number
    end: number
  }
  equity: TimePoint[]
  drawdown: TimePoint[]
  rolling_sharpe: TimePoint[]
  monthly: { ym: string; ret: number }[]
  summary: Record<string, unknown> | null
}
export interface Findings {
  studies: {
    id: string
    title: string
    date: string
    verdict: string
    summary: string
    numbers: { label: string; value: string }[]
    page: string
    report: string
  }[]
}
export interface MarkoutCell {
  market: string
  segment: string
  horizon: string
  mean_bps: number | null
  n: number
}
export interface Study1Markout {
  horizons: string[]
  markets: string[]
  segments: string[]
  cells: MarkoutCell[]
}
