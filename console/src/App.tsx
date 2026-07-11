import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { useApi, type DatasetInfo, type RawFeed } from './api'
import Overview from './pages/Overview'
import Study12 from './pages/Study12'
import Study3 from './pages/Study3'
import ChartLab from './pages/ChartLab'
import Backtests from './pages/Backtests'
import DataBrowser from './pages/DataBrowser'

const NAV = [
  { to: '/', label: 'Overview' },
  { to: '/studies-1-2', label: 'Studies 1–2' },
  { to: '/study-3', label: 'Study 3' },
  { to: '/chart-lab', label: 'Chart Lab' },
  { to: '/backtests', label: 'Backtests' },
  { to: '/data', label: 'Data Browser' },
]

function fmtSize(n: number) {
  return n > 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${(n / 1e6).toFixed(0)} MB`
}

/** What the instrument is loaded with — reports + raw archive on disk. */
function DataStatus() {
  const datasets = useApi<DatasetInfo[]>('/api/datasets')
  const feeds = useApi<RawFeed[]>('/api/raw/feeds')
  if (!datasets.data && !feeds.data) return null
  const tableB = (datasets.data ?? []).reduce((a, d) => a + d.size_bytes, 0)
  const rawB = (feeds.data ?? []).reduce((a, f) => a + f.size_bytes, 0)
  return (
    <div className="mt-auto border-t border-zinc-900 px-2 pt-3 font-mono text-[10px] leading-relaxed text-zinc-600">
      {datasets.data && (
        <div>
          {datasets.data.length} tables · {fmtSize(tableB)}
        </div>
      )}
      {feeds.data && feeds.data.length > 0 && (
        <div>
          {feeds.data.length} raw feeds · {fmtSize(rawB)}
        </div>
      )}
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-full">
        <aside className="flex w-52 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 p-4">
          <div className="mb-6 px-2">
            <span className="font-mono text-sm font-bold tracking-[0.25em] text-cyan-400">
              CHARYBDIS
            </span>
            <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-600">
              research console
            </div>
          </div>
          <nav className="flex flex-col gap-0.5">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === '/'}
                className={({ isActive }) =>
                  `relative rounded-md py-2 pl-4 pr-3 text-sm transition-colors ${
                    isActive
                      ? 'bg-zinc-900 font-medium text-zinc-100 before:absolute before:bottom-2 before:left-0 before:top-2 before:w-0.5 before:rounded-full before:bg-cyan-400'
                      : 'text-zinc-400 hover:bg-zinc-900/60 hover:text-zinc-200'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <DataStatus />
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto p-8">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/studies-1-2" element={<Study12 />} />
            <Route path="/study-3" element={<Study3 />} />
            <Route path="/chart-lab" element={<ChartLab />} />
            <Route path="/backtests" element={<Backtests />} />
            <Route path="/data" element={<DataBrowser />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
