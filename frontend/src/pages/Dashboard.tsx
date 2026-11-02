import { Link } from 'react-router-dom'
import { api, when, type Dashboard as D } from '../api'
import { Badge, Status } from '../components/ui'
import { useLoad } from '../hooks'

const OUTCOMES = ['Connected', 'Not Received', 'Not Responded', 'Rescheduled', 'Ended', 'Pending']

export default function Dashboard({ onAuthError }: { onAuthError: () => void }) {
  const { data: d, error, loading } = useLoad(() => api<D>('/api/dashboard'), [], onAuthError)
  if (!d) return <Status loading={loading} error={error} />
  const sw = d.switches
  return (
    <>
      <h1>{d.company} — today</h1>
      <div className="switches">
        <span className={`badge ${sw.real_calls ? 'bad' : 'good'}`}>{sw.real_calls ? 'REAL CALLS ON' : 'Dry-run calls'}</span>
        <span className={`badge ${sw.email_sending ? 'warn' : 'good'}`}>{sw.email_sending ? 'Emails ON' : 'Emails off'}</span>
        <span className={`badge ${sw.sheets_dry_run ? 'good' : 'warn'}`}>{sw.sheets_dry_run ? 'Sheets read-only' : 'Sheets writing'}</span>
        <span className="badge muted">Scheduler {sw.scheduler ? 'on' : 'off'}</span>
      </div>

      <section className="cards">
        <div className="card"><b>{d.today.calls}</b><span>Calls today</span></div>
        {OUTCOMES.filter(o => d.today.by_outcome[o]).map(o => (
          <div className="card" key={o}><b>{d.today.by_outcome[o]}</b><span><Badge value={o} /></span></div>
        ))}
        <div className="card"><b>{d.today.technical_failures}</b><span>Technical failures</span></div>
        <div className="card"><b>{d.totals.customers}</b><span>Customers</span></div>
        <div className="card"><b>{d.totals.do_not_call}</b><span>Do not call</span></div>
      </section>

      <div className="two">
        <section>
          <h2>Upcoming calls and reminders</h2>
          {d.upcoming_tasks.length === 0 ? <p className="muted">Nothing scheduled.</p> : (
            <table><thead><tr><th>When</th><th>Customer</th><th>Type</th></tr></thead><tbody>
              {d.upcoming_tasks.map(t => (
                <tr key={t.id}><td>{when(t.run_at)}</td>
                  <td><Link to={`/customers/${t.customer_id}`}>{t.customer_name || t.customer_phone}</Link></td>
                  <td>{t.kind === 'reminder' ? 'Meeting reminder' : t.reason === 'callback' ? 'Callback' : 'Retry'}</td></tr>
              ))}
            </tbody></table>
          )}
        </section>
        <section>
          <h2>Upcoming meetings</h2>
          {d.upcoming_meetings.length === 0 ? <p className="muted">No meetings booked.</p> : (
            <table><thead><tr><th>When</th><th>Customer</th><th>Mode</th></tr></thead><tbody>
              {d.upcoming_meetings.map(m => (
                <tr key={m.id}><td>{when(m.scheduled_for)}</td>
                  <td><Link to={`/customers/${m.customer_id}`}>{m.customer_name || m.customer_phone}</Link></td>
                  <td>{m.mode || '—'}</td></tr>
              ))}
            </tbody></table>
          )}
        </section>
      </div>
    </>
  )
}
