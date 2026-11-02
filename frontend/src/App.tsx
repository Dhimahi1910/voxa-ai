import { useState } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { getKey, setKey } from './api'
import Customers from './pages/Customers'
import CustomerDetail from './pages/CustomerDetail'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'

export default function App() {
  const [authed, setAuthed] = useState(() => !!getKey())
  const navigate = useNavigate()
  const logout = () => { setKey(''); setAuthed(false); navigate('/') }

  if (!authed) return <Login onLogin={() => setAuthed(true)} />
  return (
    <div className="shell">
      <header className="topbar">
        <strong>Voice Agent Console</strong>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/customers">Customers</NavLink>
        </nav>
        <button className="link" onClick={logout}>Sign out</button>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard onAuthError={logout} />} />
          <Route path="/customers" element={<Customers onAuthError={logout} />} />
          <Route path="/customers/:id" element={<CustomerDetail onAuthError={logout} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
