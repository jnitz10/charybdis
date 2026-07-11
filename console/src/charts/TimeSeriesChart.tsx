import { useEffect, useRef } from 'react'
import { BaselineSeries, ColorType, createChart, type Time } from 'lightweight-charts'
import type { TimePoint } from '../api'
import { C } from '../theme'

export default function TimeSeriesChart({
  points,
  height = 280,
  percent = false,
}: {
  points: TimePoint[]
  height?: number
  percent?: boolean
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
      },
      grid: { vertLines: { color: C.border }, horzLines: { color: C.border } },
      timeScale: { timeVisible: true, borderColor: C.border },
      rightPriceScale: { borderColor: C.border },
    })
    const series = chart.addSeries(BaselineSeries, {
      baseValue: { type: 'price', price: 0 },
      topLineColor: C.up,
      topFillColor1: 'rgba(16, 185, 129, 0.25)',
      topFillColor2: 'rgba(16, 185, 129, 0.02)',
      bottomLineColor: C.down,
      bottomFillColor1: 'rgba(244, 63, 94, 0.02)',
      bottomFillColor2: 'rgba(244, 63, 94, 0.25)',
      priceLineVisible: false,
      priceFormat: percent
        ? { type: 'custom', formatter: (v: number) => `${(v * 100).toFixed(1)}%` }
        : { type: 'price', precision: 4, minMove: 0.0001 },
    })
    series.setData(points.map((p) => ({ time: p.t as Time, value: p.v })))
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [points, percent])
  return <div ref={ref} style={{ height }} />
}
