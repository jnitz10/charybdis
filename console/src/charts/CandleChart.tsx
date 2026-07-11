import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts'
import { C, MONO } from '../theme'

export interface OverlaySeries {
  name: string
  values: (number | null)[]
}
export interface Pane {
  name: string
  series: OverlaySeries[]
}

export default function CandleChart({
  time,
  open,
  high,
  low,
  close,
  overlays,
  panes,
  resetKey = '',
  height = 520,
}: {
  time: number[]
  open: number[]
  high: number[]
  low: number[]
  close: number[]
  overlays: OverlaySeries[]
  panes: Pane[]
  /** Zoom/pan survive data updates; the viewport refits only when this changes. */
  resetKey?: string
  height?: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const indicatorSeriesRef = useRef<ISeriesApi<'Line'>[]>([])
  const fittedKeyRef = useRef<string | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: C.muted,
        fontFamily: MONO,
        fontSize: 11,
        panes: { separatorColor: C.border },
      },
      grid: {
        vertLines: { color: C.grid },
        horzLines: { color: C.grid },
      },
      timeScale: { timeVisible: true, borderColor: C.border },
      rightPriceScale: { borderColor: C.border },
    })
    candleRef.current = chart.addSeries(CandlestickSeries, {
      upColor: C.up,
      downColor: C.down,
      borderVisible: false,
      wickUpColor: C.up,
      wickDownColor: C.down,
    })
    chartRef.current = chart
    return () => {
      chart.remove()
      chartRef.current = null
      candleRef.current = null
      indicatorSeriesRef.current = []
      fittedKeyRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    const candle = candleRef.current
    if (!chart || !candle) return
    const view = chart.timeScale().getVisibleLogicalRange()
    candle.setData(
      time.map((t, i) => ({
        time: t as Time,
        open: open[i],
        high: high[i],
        low: low[i],
        close: close[i],
      })),
    )
    for (const s of indicatorSeriesRef.current) chart.removeSeries(s)
    indicatorSeriesRef.current = []
    const lineData = (values: (number | null)[]) =>
      time.map((t, i) =>
        values[i] == null ? { time: t as Time } : { time: t as Time, value: values[i] as number },
      )
    let ci = 0
    const addLine = (name: string, values: (number | null)[], paneIndex?: number) => {
      const series = chart.addSeries(
        LineSeries,
        {
          color: C.series[ci++ % C.series.length],
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          title: name,
        },
        paneIndex,
      )
      series.setData(lineData(values))
      indicatorSeriesRef.current.push(series)
    }
    for (const o of overlays) addLine(o.name, o.values)
    panes.forEach((p, pi) => {
      for (const s of p.series) addLine(s.name, s.values, pi + 1)
    })
    if (fittedKeyRef.current !== resetKey) {
      chart.timeScale().fitContent()
      fittedKeyRef.current = resetKey
    } else if (view) {
      chart.timeScale().setVisibleLogicalRange(view)
    }
  }, [time, open, high, low, close, overlays, panes, resetKey])

  return <div ref={ref} style={{ height }} />
}
