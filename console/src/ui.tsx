import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ApiError } from './api'

/** Click-a-`?` explainer. Invisible until clicked; closes on Esc or outside click. */
export function InfoPopover({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <span className="relative inline-flex" ref={ref}>
      <button
        aria-label={`About: ${title}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex h-4 w-4 items-center justify-center rounded-full border text-[10px] leading-none transition-colors ${
          open
            ? 'border-cyan-500 text-cyan-300'
            : 'border-zinc-700 text-zinc-500 hover:border-zinc-500 hover:text-zinc-300'
        }`}
      >
        ?
      </button>
      {open && (
        <div className="absolute left-0 top-6 z-30 w-[26rem] max-w-[80vw] cursor-auto rounded-lg border border-zinc-700 bg-zinc-900 p-4 text-left shadow-xl shadow-black/50">
          <div className="mb-2 text-sm font-medium text-zinc-200">{title}</div>
          <div className="space-y-2 text-xs font-normal leading-relaxed text-zinc-400">
            {children}
          </div>
        </div>
      )}
    </span>
  )
}

/** Chart header row: title + optional `?` explainer on the left, controls on the right. */
export function ChartTitle({
  title,
  info,
  right,
}: {
  title: string
  info?: ReactNode
  right?: ReactNode
}) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-sm font-medium text-zinc-300">
        {title}
        {info && <InfoPopover title={title}>{info}</InfoPopover>}
      </div>
      {right}
    </div>
  )
}

export function PageHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-xl font-semibold tracking-tight text-zinc-100">{title}</h1>
      {sub && <p className="mt-1 text-sm text-zinc-500">{sub}</p>}
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 ${className}`}>
      {children}
    </div>
  )
}

export function StatCard({
  label,
  value,
  sub,
  tone = 'flat',
}: {
  label: string
  value: string
  sub?: string
  tone?: 'up' | 'down' | 'flat'
}) {
  const toneCls =
    tone === 'up' ? 'text-emerald-400' : tone === 'down' ? 'text-rose-400' : 'text-zinc-100'
  return (
    <Card>
      <div className="text-xs uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`mt-1 font-mono text-lg font-semibold tabular-nums ${toneCls}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500">{sub}</div>}
    </Card>
  )
}

export function EmptyState({ error, note }: { error?: ApiError; note?: string }) {
  const msg =
    error?.status === 404
      ? error.message
      : (error?.message ?? note ?? 'No data available')
  return (
    <Card className="flex min-h-32 items-center justify-center">
      <div className="text-center">
        <div className="text-sm text-zinc-400">{msg}</div>
        {error?.status === 404 && (
          <div className="mt-1 text-xs text-zinc-600">
            This view needs a dataset that is not present on disk.
          </div>
        )}
      </div>
    </Card>
  )
}

export function Spinner() {
  return (
    <div className="flex min-h-32 items-center justify-center">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-700 border-t-cyan-400" />
    </div>
  )
}

export function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-zinc-400">
      {label}
      <select
        className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200 outline-none focus:border-cyan-500"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  )
}
