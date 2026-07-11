import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  LineSeries,
  type Time,
} from 'lightweight-charts'
import { C } from '../theme'

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
  height = 520,
}: {
  time: number[]
  open: number[]
  high: number[]
  low: number[]
  close: number[]
  overlays: OverlaySeries[]
  panes: Pane[]
  height?: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: C.muted,
        panes: { separatorColor: C.border },
      },
      grid: {
        vertLines: { color: C.border },
        horzLines: { color: C.border },
      },
      timeScale: { timeVisible: true, borderColor: C.border },
      rightPriceScale: { borderColor: C.border },
    })
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: C.up,
      downColor: C.down,
      borderVisible: false,
      wickUpColor: C.up,
      wickDownColor: C.down,
    })
    candle.setData(
      time.map((t, i) => ({
        time: t as Time,
        open: open[i],
        high: high[i],
        low: low[i],
        close: close[i],
      })),
    )
    const lineData = (values: (number | null)[]) =>
      time.map((t, i) =>
        values[i] == null ? { time: t as Time } : { time: t as Time, value: values[i] as number },
      )
    let ci = 0
    const nextColor = () => C.series[ci++ % C.series.length]
    for (const o of overlays) {
      chart
        .addSeries(LineSeries, {
          color: nextColor(),
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          title: o.name,
        })
        .setData(lineData(o.values))
    }
    panes.forEach((p, pi) => {
      for (const s of p.series) {
        chart
          .addSeries(
            LineSeries,
            {
              color: nextColor(),
              lineWidth: 2,
              priceLineVisible: false,
              lastValueVisible: false,
              title: s.name,
            },
            pi + 1,
          )
          .setData(lineData(s.values))
      }
    })
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [time, open, high, low, close, overlays, panes])
  return <div ref={ref} style={{ height }} />
}
