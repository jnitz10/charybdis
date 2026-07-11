import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
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

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-full">
        <aside className="flex w-52 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 p-4">
          <div className="mb-6 px-2">
            <span className="text-sm font-bold tracking-[0.2em] text-cyan-400">CHARYBDIS</span>
            <div className="text-[10px] uppercase tracking-wider text-zinc-600">
              research console
            </div>
          </div>
          <nav className="flex flex-col gap-1">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === '/'}
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-sm ${
                    isActive
                      ? 'bg-zinc-800/80 font-medium text-zinc-100'
                      : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto p-8">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/studies-1-2" element={<Study12 />} />
            <Route path="/study-3" element={<Study3 />} />
            <Route path="/chart-lab" element={<ChartLab />} />
            <Route path="/backtests" element={<Backtests />} />
            <Route path="/data" element={<DataBrowser />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
