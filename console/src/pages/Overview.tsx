import { Link } from 'react-router-dom'
import { useApi, type Findings } from '../api'
import { Card, EmptyState, PageHeader, Spinner } from '../ui'

export default function Overview() {
  const findings = useApi<Findings>('/api/findings')
  if (findings.loading) return <Spinner />
  if (findings.error) return <EmptyState error={findings.error} />
  return (
    <div>
      <PageHeader
        title="The story so far"
        sub="Headline conclusions per study — curated, with links to the interactive detail views."
      />
      <div className="grid gap-6 xl:grid-cols-3">
        {findings.data!.studies.map((s) => (
          <Card key={s.id} className="flex flex-col">
            <div className="mb-1 font-mono text-xs tracking-wider text-zinc-500">{s.date}</div>
            <h2 className="text-base font-semibold text-zinc-100">{s.title}</h2>
            <div className="mt-2.5 w-fit border-l-2 border-zinc-600 bg-zinc-800/40 py-1 pl-2.5 pr-3 font-mono text-[11px] leading-relaxed text-zinc-200">
              {s.verdict}
            </div>
            <p className="mt-3 text-sm leading-relaxed text-zinc-400">{s.summary}</p>
            <dl className="mt-4 space-y-2">
              {s.numbers.map((n) => (
                <div key={n.label} className="flex items-baseline justify-between gap-3 border-b border-zinc-900 pb-1.5">
                  <dt className="text-xs text-zinc-500">{n.label}</dt>
                  <dd className="text-right font-mono text-xs font-medium tabular-nums text-zinc-200">
                    {n.value}
                  </dd>
                </div>
              ))}
            </dl>
            <div className="mt-auto flex items-center justify-between pt-4">
              <Link to={s.page} className="text-sm font-medium text-cyan-400 hover:underline">
                Explore →
              </Link>
              <span className="font-mono text-[10px] text-zinc-600">{s.report}</span>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
