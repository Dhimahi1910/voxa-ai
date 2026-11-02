import { Link } from 'react-router-dom'
import { api, type PlanToday } from '../api'
import { Status } from '../components/ui'
import { VeeshaTip } from '../components/Veesha'
import { useLoad } from '../hooks'

export default function Plan({ onAuthError }: { onAuthError: () => void }) {
  const { data: p, error, loading } = useLoad(() => api<PlanToday>('/api/plan/today'), [], onAuthError)
  if (!p) return <main className="page"><Status loading={loading} error={error} /></main>
  const groups = p.skipped.reduce<Record<string, typeof p.skipped>>((acc, s) => { (acc[s.reason_text] ??= []).push(s); return acc }, {})
  return (
    <main className="page">
      <h1>Today's plan</h1>
      <p className="muted">Exactly who the next calling run would dial, and the reason for everyone it would skip. Nothing here is acted on.</p>
      <VeeshaTip>
        {p.in_calling_hours
          ? `It's inside calling hours (${p.window}), so a run would dial the ${p.will_call.length} people below.`
          : `It's outside calling hours (${p.window}, ${p.days.join(', ')}), so a run would place no calls right now. This is who would be eligible once the window opens.`}
      </VeeshaTip>
      <div className="two">
        <div className="glass panel">
          <header><h2>Will call</h2><span className="badge good">{p.will_call.length}</span></header>
          {p.will_call.length === 0 ? <p className="muted">Nobody is due.</p> : (
            <ul className="list">{p.will_call.map(c => <li key={c.id}><Link to={`/customers/${c.id}`}>{c.name || c.phone}</Link><small className="faint">{c.phone}</small></li>)}</ul>
          )}
        </div>
        <div className="glass panel">
          <header><h2>Skipped, and why</h2><span className="badge warn">{p.skipped.length}</span></header>
          {p.skipped.length === 0 ? <p className="muted">Nobody is skipped.</p> : Object.entries(groups).map(([text, rows]) => (
            <div key={text} style={{ marginBottom: '.9rem' }}>
              <div className="chip" style={{ marginBottom: '.3rem' }}>{text} <b>{rows.length}</b></div>
              <ul className="list">{rows.map(c => <li key={c.id}><Link to={`/customers/${c.id}`}>{c.name || c.phone}</Link><small className="faint">{c.phone}</small></li>)}</ul>
            </div>
          ))}
        </div>
      </div>
    </main>
  )
}
