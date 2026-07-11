import type { EChartsOption, SeriesOption } from 'echarts'
import { C, MONO } from '../theme'

export const base: EChartsOption = {
  backgroundColor: 'transparent',
  textStyle: { color: C.text, fontFamily: 'inherit' },
  tooltip: {
    trigger: 'axis',
    backgroundColor: C.panel,
    borderColor: C.border,
    textStyle: { color: C.text, fontSize: 12 },
  },
  grid: { left: 64, right: 24, top: 36, bottom: 44 },
}

export function axis() {
  return {
    axisLine: { lineStyle: { color: C.border } },
    axisTick: { lineStyle: { color: C.border } },
    axisLabel: { color: C.muted, fontFamily: MONO, fontSize: 11 },
    splitLine: { lineStyle: { color: C.grid } },
    nameTextStyle: { color: C.muted, fontFamily: MONO, fontSize: 11 },
  }
}

export function lineOption(cfg: {
  categories: string[]
  series: { name: string; data: (number | null)[] }[]
  yName: string
}): EChartsOption {
  return {
    ...base,
    legend: { textStyle: { color: C.muted }, top: 0 },
    xAxis: { type: 'category', data: cfg.categories, ...axis() },
    yAxis: { type: 'value', name: cfg.yName, ...axis() },
    series: cfg.series.map((s, i) => ({
      name: s.name,
      type: 'line' as const,
      data: s.data,
      smooth: false,
      symbolSize: 6,
      lineStyle: { width: 2 },
      itemStyle: { color: C.series[i % C.series.length] },
    })),
  }
}

export function scatterOption(cfg: {
  points: { x: number; y: number; name: string }[]
  xName: string
  yName: string
}): EChartsOption {
  return {
    ...base,
    tooltip: {
      ...base.tooltip,
      trigger: 'item',
      formatter: (p: unknown) => {
        const q = p as { data: { name: string; value: [number, number] } }
        return `${q.data.name}<br/>${cfg.xName}: ${q.data.value[0].toFixed(2)}<br/>${cfg.yName}: ${q.data.value[1].toFixed(2)}`
      },
    },
    xAxis: { type: 'value', name: cfg.xName, ...axis() },
    yAxis: { type: 'value', name: cfg.yName, ...axis() },
    series: [
      {
        type: 'scatter',
        symbolSize: 9,
        itemStyle: { color: C.series[0], opacity: 0.75 },
        data: cfg.points.map((p) => ({ name: p.name, value: [p.x, p.y] })),
      },
    ],
  }
}

export interface CIItem {
  label: string
  value: number
  lo: number
  hi: number
}

/** Horizontal dot-and-whisker chart for point estimates with confidence intervals. */
export function dotWhisker(
  groups: { name: string; color: string; items: CIItem[] }[],
  xLabel: string,
): EChartsOption {
  // Category order = first appearance across ALL groups; items are matched by
  // label (not array position), so groups may list categories in any order.
  const cats: string[] = []
  for (const g of groups)
    for (const it of g.items) if (!cats.includes(it.label)) cats.push(it.label)
  const offset = (gi: number) => (gi - (groups.length - 1) / 2) * 8
  const series: SeriesOption[] = groups.flatMap((g, gi) => [
    {
      name: g.name,
      type: 'custom' as const,
      silent: true,
      // The legend swatch is taken from the first series bearing the group name —
      // this one — so it must carry the group color too, not just the scatter.
      itemStyle: { color: g.color },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      renderItem: (_p: any, api: any) => {
        const y = api.coord([0, api.value(2)])[1] + offset(gi)
        const x0 = api.coord([api.value(0), 0])[0]
        const x1 = api.coord([api.value(1), 0])[0]
        const style = { stroke: g.color, lineWidth: 1.5 }
        return {
          type: 'group',
          children: [
            { type: 'line', shape: { x1: x0, y1: y, x2: x1, y2: y }, style },
            { type: 'line', shape: { x1: x0, y1: y - 4, x2: x0, y2: y + 4 }, style },
            { type: 'line', shape: { x1: x1, y1: y - 4, x2: x1, y2: y + 4 }, style },
          ],
        }
      },
      data: g.items.map((it) => [it.lo, it.hi, cats.indexOf(it.label)]),
      z: 1,
    },
    {
      name: g.name,
      type: 'scatter' as const,
      symbolSize: 8,
      itemStyle: { color: g.color },
      data: g.items.map((it) => ({
        name: it.label,
        value: [it.value, cats.indexOf(it.label)] as [number, number],
      })),
      z: 2,
    },
  ])
  return {
    ...base,
    tooltip: { ...base.tooltip, trigger: 'item' },
    legend: groups.length > 1 ? { textStyle: { color: C.muted }, top: 0 } : undefined,
    grid: { left: 170, right: 30, top: groups.length > 1 ? 32 : 12, bottom: 44 },
    xAxis: { type: 'value', name: xLabel, ...axis() },
    yAxis: { type: 'category', data: cats, inverse: true, ...axis() },
    series,
  }
}

export function monthlyHeatmap(monthly: { ym: string; ret: number }[]): EChartsOption {
  const years = [...new Set(monthly.map((m) => m.ym.slice(0, 4)))].sort()
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const data = monthly.map((m) => [
    Number(m.ym.slice(5, 7)) - 1,
    years.indexOf(m.ym.slice(0, 4)),
    Number((m.ret * 100).toFixed(2)),
  ])
  const maxAbs = Math.max(0.01, ...monthly.map((m) => Math.abs(m.ret * 100)))
  return {
    ...base,
    tooltip: { ...base.tooltip, trigger: 'item' },
    grid: { left: 64, right: 24, top: 12, bottom: 64 },
    xAxis: { type: 'category', data: months, ...axis(), splitLine: { show: false } },
    yAxis: { type: 'category', data: years, ...axis(), splitLine: { show: false } },
    visualMap: {
      min: -maxAbs,
      max: maxAbs,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      textStyle: { color: C.muted, fontFamily: MONO, fontSize: 11 },
      inRange: { color: [C.down, '#3f3f46', C.up] },
    },
    series: [
      {
        type: 'heatmap',
        data,
        label: {
          show: true,
          color: C.text,
          fontFamily: MONO,
          fontSize: 11,
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          formatter: (p: any) => `${(p.data as number[])[2]}%`,
        },
      },
    ],
  }
}
