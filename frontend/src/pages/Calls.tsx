import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, download, errMsg, when, type Analytics, type Call } from '../api'
import CallPanel from '../components/CallPanel'
import { Donut, Funnel, HourHeat, Spark } from '../components/charts'
import { Badge, Status } from '../components/ui'
import { useLoad } from '../hooks'
import { useToast } from '../toast-context'

const PAGE = 25
const OUTCOMES = ['Connected', 'Not Received', 'Not Responded', 'Rescheduled', 'Ended']

export default function Calls({ onAuthError }: { onAuthError: () => void }) {
  const [days, setDays] = useState(14)
  const [outcome, setOutcome] = useState('')
  const [input, setInput] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const toast = useToast()
  useEffect(() => { const t = setTimeout(() => { setQ(input.trim()); setPage(0) }, 300); return () => clearTimeout(t) }, [input])

  const stats = useLoad(() => api<Analytics>(`/api/analytics?days=${days}`), [days], onAuthError)
  const filter = `days=${days}${outcome ? `&outcome=${encodeURIComponent(outcome)}` : ''}${q ? `&q=${encodeURIComponent(q)}` : ''}`
  const list = useLoad(() => api<Call[]>(`/api/calls?${filter}&limit=${PAGE}&offset=${page * PAGE}`), [filter, page], onAuthError)

  const a = stats.data
  const best = a?.by_hour.filter(h => h.calls >= 2).sort((x, y) => y.connected / y.calls - x.connected / x.calls)[0]
  const active = selected ?? list.data?.[0]?.id ?? null

  return (
    <main className="page">
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: '1rem' }}>
        <h1>Calls</h1>
        <div className="seg" role="group" aria-label="Date range">
          {[7, 14, 30].map(n => <button key={n} className={days === n ? 'on' : ''} onClick={() => { setDays(n); setPage(0) }}>{n} days</button>)}
        </div>
      </div>

      <Status loading={stats.loading && !a} error={stats.error} />
      {a && (
        <>
          <section className="stats">
            <div className="glass stat"><b>{a.totals.calls}</b><span>Calls</span></div>
            <div className="glass stat"><b>{a.totals.connect_rate}%</b><span>Connect rate</span></div>
            <div className="glass stat"><b>{a.totals.avg_duration}s</b><span>Avg. talk time</span></div>
            <div className="glass stat"><b>{a.funnel[3].value}</b><span>Meetings booked</span></div>
            <div className="glass stat"><b>{a.totals.failed}</b><span>Technical failures</span></div>
          </section>
          <section className="two" style={{ marginTop: 0 }}>
            <div className="glass panel"><header><h2>Outcomes</h2></header><Donut data={a.outcomes} /></div>
            <div className="glass panel"><header><h2>From dial to meeting</h2></header><Funnel steps={a.funnel} /></div>
          </section>
          <section className="two">
            <div className="glass panel">
              <header><h2>When people pick up</h2></header>
              <HourHeat hours={a.by_hour} />
              <p className="muted" style={{ marginBottom: 0 }}>
                {best ? <>Best hour so far: <b>{String(best.hour).padStart(2, '0')}:00</b> ({Math.round(100 * best.connected / best.calls)}% connected from {best.calls} calls).</> : 'Not enough calls yet to spot a best time.'}
              </p>
            </div>
            <div className="glass panel"><header><h2>Calls per day</h2><span className="faint"><i className="key v" />calls <i className="key t" />connected</span></header><Spark points={a.daily} /></div>
          </section>
        </>
      )}

      <div className="row" style={{ margin: '1.4rem 0 .8rem' }}>
        <input className="search" type="search" placeholder="Search customer or phone" aria-label="Search calls" value={input} onChange={e => setInput(e.target.value)} />
        <select value={outcome} onChange={e => { setOutcome(e.target.value); setPage(0) }} aria-label="Filter by outcome">
          <option value="">All outcomes</option>{OUTCOMES.map(o => <option key={o}>{o}</option>)}
        </select>
        <button onClick={() => download(`/api/calls/export?${filter}`, 'calls.csv').catch(e => toast('bad', errMsg(e)))}>Export CSV</button>
      </div>
      <Status loading={list.loading && !list.data} error={list.error} />
      {list.data && (list.data.length === 0 ? <p className="muted">No calls match these filters.</p> : (
        <div className="split">
          <div className="glass panel">
            <table>
              <thead><tr><th>When</th><th>Customer</th><th>Outcome</th><th>Length</th></tr></thead>
              <tbody>{list.data.map(k => (
                <tr key={k.id} className={k.id === active ? 'sel' : ''} onClick={() => setSelected(k.id)} tabIndex={0} onKeyDown={e => e.key === 'Enter' && setSelected(k.id)}>
                  <td>{when(k.dialed_at ?? k.created_at)}</td>
                  <td><Link to={`/customers/${k.customer_id}`} onClick={e => e.stopPropagation()}>{k.customer_name || k.customer_phone}</Link></td>
                  <td><Badge value={k.outcome ?? k.state} /></td><td>{k.duration_seconds != null ? `${k.duration_seconds}s` : '—'}</td>
                </tr>))}
              </tbody>
            </table>
            <div className="pager">
              <button disabled={page === 0} onClick={() => setPage(p => p - 1)}>Previous</button>
              <span className="muted">Page {page + 1}</span>
              <button disabled={list.data.length < PAGE} onClick={() => setPage(p => p + 1)}>Next</button>
            </div>
          </div>
          {active != null && <CallPanel callId={active} onAuthError={onAuthError} />}
        </div>
      ))}
    </main>
  )
}
