import { useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, getKey, setKey, type Settings } from './api'
import Aurora from './components/Aurora'
import Tour from './components/Tour'
import Welcome from './components/Welcome'
import { flag, setFlag } from './storage'
import Toasts from './components/Toasts'
import { useLoad } from './hooks'
import Calls from './pages/Calls'
import Controls from './pages/Controls'
import Plan from './pages/Plan'
import Practice from './pages/Practice'
import CustomerDetail from './pages/CustomerDetail'
import Customers from './pages/Customers'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import { SettingsContext } from './settings-context'

export default function App() {
  const [authed, setAuthed] = useState(() => !!getKey())
  const navigate = useNavigate()
  const logout = () => { setKey(''); setAuthed(false); navigate('/') }

  return (
    <Toasts>
      <Aurora />
      {authed ? <Shell onLogout={logout} /> : <Login onLogin={() => setAuthed(true)} />}
    </Toasts>
  )
}

const TOUR = [
  { selector: '[data-tour="nav-dashboard"]', title: 'Your home base', text: 'The dashboard shows today at a glance: calls, outcomes, what is scheduled and how setup is going.' },
  { selector: '[data-tour="checklist"]', title: 'Getting started', text: 'This checklist ticks itself off as you set things up, so you always know the next step.' },
  { selector: '[data-tour="stats"]', title: "Today's numbers", text: 'Live counts of calls and outcomes. Hover the cards for a little tilt.' },
  { selector: '[data-tour="panels"]', title: 'Calls, customers and settings', text: 'Recent activity on the left, and a read-only summary of your rules and integrations on the right.' },
  { selector: '[data-tour="plan"]', title: "Today's plan", text: 'Who the next run would call, and a plain-English reason for everyone it would skip.' },
  { selector: '[data-tour="nav-customers"]', title: 'Customers', text: 'Search, import a CSV, call someone, and open any customer to see their whole journey.' },
  { selector: '[data-tour="nav-calls"]', title: 'Calls and analytics', text: 'Every call with filters and CSV export, plus when people pick up and how many become meetings.' },
  { selector: '[data-tour="nav-practice"]', title: 'Practice Room', text: 'Rehearse any kind of customer and see exactly what happens next, with no real calls.' },
  { selector: '[data-tour="nav-controls"]', title: 'Controls', text: 'Run jobs and manage the do-not-call list. Every action asks first.' },
]

function Shell({ onLogout }: { onLogout: () => void }) {
  const { data: settings } = useLoad(() => api<Settings>('/api/settings'), [], onLogout)
  const [welcome, setWelcome] = useState(() => !flag('welcomed'))
  const [tour, setTour] = useState(false)
  const navigate = useNavigate()
  const here = useLocation().pathname
  const startTour = () => { setWelcome(false); setFlag('welcomed'); if (here !== '/') navigate('/'); setTimeout(() => setTour(true), here === '/' ? 0 : 500) }
  const closeWelcome = () => { setWelcome(false); setFlag('welcomed') }
  return (
    <SettingsContext.Provider value={settings}>
      {settings?.switches.real_calls && <p className="banner" role="status">REAL CALLS ARE ON — customers will be phoned</p>}
      <header className="topbar">
        <span className="brand"><span className="dot" />{settings?.business.company ?? 'voxai'}</span>
        <nav>
          <NavLink to="/" end data-tour="nav-dashboard">Dashboard</NavLink>
          <NavLink to="/customers" data-tour="nav-customers">Customers</NavLink>
          <NavLink to="/calls" data-tour="nav-calls">Calls</NavLink>
          <NavLink to="/plan">Plan</NavLink>
          <NavLink to="/practice" data-tour="nav-practice">Practice</NavLink>
          <NavLink to="/controls" data-tour="nav-controls">Controls</NavLink>
        </nav>
        <button className="ghost" onClick={startTour} aria-label="Take the product tour">Tour</button>
        <button className="ghost" onClick={onLogout}>Sign out</button>
      </header>
      {welcome && <Welcome onTour={startTour} onClose={closeWelcome} />}
      {tour && <Tour steps={TOUR} onClose={() => setTour(false)} />}
      <Routes>
        <Route path="/" element={<Dashboard onAuthError={onLogout} />} />
        <Route path="/customers" element={<Customers onAuthError={onLogout} />} />
        <Route path="/customers/:id" element={<CustomerDetail onAuthError={onLogout} />} />
        <Route path="/calls" element={<Calls onAuthError={onLogout} />} />
        <Route path="/plan" element={<Plan onAuthError={onLogout} />} />
        <Route path="/practice" element={<Practice onAuthError={onLogout} />} />
        <Route path="/controls" element={<Controls onAuthError={onLogout} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </SettingsContext.Provider>
  )
}
