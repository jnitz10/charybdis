import type { ReactNode } from 'react'
import { ApiError } from './api'

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
      <div className={`mt-1 text-lg font-semibold tabular-nums ${toneCls}`}>{value}</div>
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
            This view needs a parquet that is not present in data/reports/.
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
