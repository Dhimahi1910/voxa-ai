import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, when, type Call, type Customer, type Dashboard as D, type PlanToday } from '../api'
import { JobButton } from '../components/Actions'
import Checklist from '../components/Checklist'
import CountUp from '../components/CountUp'
import Orb from '../components/Orb'
import Tilt from '../components/Tilt'
import { Badge, Status } from '../components/ui'
import { VeeshaTip } from '../components/Veesha'
import { fireConfetti } from '../confetti'
import { useLoad } from '../hooks'
import { MILESTONES } from '../milestones'
import { useSettings } from '../settings-context'
import { readJson, writeJson } from '../storage'
import { useToast } from '../toast-context'

const greeting = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening' }

export default function Dashboard({ onAuthError }: { onAuthError: () => void }) {
  const dash = useLoad(() => api<D>('/api/dashboard'), [], onAuthError)
  const calls = useLoad(() => api<Call[]>('/api/calls?limit=8'), [], onAuthError)
  const custs = useLoad(() => api<Customer[]>('/api/customers?limit=6'), [], onAuthError)
  const plan = useLoad(() => api<PlanToday>('/api/plan/today'), [], onAuthError)
  const settings = useSettings()
  const toast = useToast()
  const [celebrated, setCelebrated] = useState<string | null>(null)
  const d = dash.data

  // Celebrate the first newly reached milestone (once), without nagging on later visits.
  useEffect(() => {
    if (!d) return
    const reached = MILESTONES.filter(m => d.milestones[m.key] >= 1)
    const seen = readJson<string[]>('voxai:milestones', [])
    const fresh = reached.find(m => !seen.includes(m.key))
    if (fresh) { setCelebrated(fresh.title); toast('good', `${fresh.title}: ${fresh.text}`); fireConfetti() }
    if (reached.some(m => !seen.includes(m.key))) writeJson('voxai:milestones', reached.map(m => m.key))
  }, [d, toast])

  if (!d) return <main className="page"><Status loading={dash.loading} error={dash.error} /></main>

  const o = d.today.by_outcome
  const missed = (o['Not Received'] ?? 0) + (o['Not Responded'] ?? 0)
  const stats: [string, number][] = [
    ['Calls today', d.today.calls], ['Connected', o['Connected'] ?? 0], ['Missed', missed],
    ['Callbacks', o['Rescheduled'] ?? 0], ['Technical failures', d.today.technical_failures],
    ['Customers', d.totals.customers], ['Do not call', d.totals.do_not_call],
  ]
  const refresh = () => { dash.reload(); calls.reload(); custs.reload(); plan.reload() }
  const sw = d.switches
  const reasonCounts = (plan.data?.skipped ?? []).reduce<Record<string, { text: string; n: number }>>((acc, s) => {
    acc[s.reason] = { text: s.reason_text, n: (acc[s.reason]?.n ?? 0) + 1 }; return acc
  }, {})

  return (
    <main className="page">
      <section className="hero">
        <div>
          <h1>{greeting()}.<br /><span className="muted">Here's {d.company} today.</span></h1>
          <p className="sub">{d.today.calls === 0 ? 'No calls yet today.' : `${d.today.calls} call${d.today.calls === 1 ? '' : 's'} so far, ${o['Connected'] ?? 0} connected.`}</p>
          <div className="row" style={{ marginBottom: '1rem' }}>
            <span className={`badge ${sw.real_calls ? 'bad' : 'good'}`}><span className="pulse" />{sw.real_calls ? 'Real calls on' : 'Simulated calls'}</span>
            <span className={`badge ${sw.email_sending ? 'warn' : 'good'}`}>{sw.email_sending ? 'Emails on' : 'Emails off'}</span>
            <span className={`badge ${sw.sheets_dry_run ? 'good' : 'warn'}`}>{sw.sheets_dry_run ? 'Sheets read-only' : 'Sheets writing'}</span>
            <span className="badge">Scheduler {sw.scheduler ? 'on' : 'off'}</span>
          </div>
          <div className="row"><JobButton job="calling_run" primary onDone={refresh} /><JobButton job="due_tasks" onDone={refresh} /></div>
        </div>
        <Orb intensity={Math.min(1, 0.2 + d.today.calls / 12)} />
      </section>

      {celebrated && <VeeshaTip title="Milestone unlocked!">{celebrated}. {MILESTONES.find(m => m.title === celebrated)?.text}</VeeshaTip>}
      {d.totals.customers === 0 && <VeeshaTip>It's quiet here. Add a customer or import a CSV and I'll get going. You can also rehearse in the <Link to="/practice">Practice Room</Link> first.</VeeshaTip>}

      <Checklist dashboard={d} settings={settings} />

      <section className="stats" data-tour="stats">
        {stats.map(([label, n]) => <Tilt className="stat" key={label}><b><CountUp value={n} /></b><span>{label}</span></Tilt>)}
      </section>

      <section className="bento" data-tour="panels">
        <div className="glass panel">
          <header><h2>Recent calls</h2><Link to="/calls">All calls →</Link></header>
          <Status loading={calls.loading && !calls.data} error={calls.error} />
          {calls.data?.length === 0 && <p className="muted">No calls yet.</p>}
          <ul className="list">
            {calls.data?.map(c => (
              <li key={c.id}>
                <span><Link to={`/customers/${c.customer_id}`}>{c.customer_name || c.customer_phone}</Link><br /><small className="faint">{when(c.dialed_at ?? c.created_at)} · {c.duration_seconds != null ? `${c.duration_seconds}s` : '—'}</small></span>
                <Badge value={c.outcome ?? c.state} />
              </li>
            ))}
          </ul>
        </div>

        <div className="glass panel">
          <header><h2>Customers</h2><Link to="/customers">View all →</Link></header>
          <Status loading={custs.loading && !custs.data} error={custs.error} />
          {custs.data?.length === 0 && <p className="muted">No customers yet.</p>}
          <ul className="list">
            {custs.data?.map(c => (
              <li key={c.id}>
                <span><Link to={`/customers/${c.id}`}>{c.name || '(no name)'}</Link><br /><small className="faint">{c.phone} · {c.call_count} call{c.call_count === 1 ? '' : 's'}</small></span>
                <Badge value={c.last_outcome} />
              </li>
            ))}
          </ul>
        </div>

        <div className="glass panel" data-tour="settings">
          <header><h2>Settings</h2><Link to="/controls">Controls →</Link></header>
          {!settings ? <p className="muted">Loading…</p> : (
            <>
              <dl className="kv">
                <dt>Agent</dt><dd>{settings.business.agent} at {settings.business.company}</dd>
                <dt>Calling hours</dt><dd>{settings.calling.hours} {settings.calling.timezone}</dd>
                <dt>Days</dt><dd>{settings.calling.days.join(', ')}</dd>
                <dt>Daily run</dt><dd>{settings.calling.daily_run}</dd>
                <dt>Max attempts</dt><dd>{settings.calling.max_attempts} per customer</dd>
                <dt>Retry (no answer)</dt><dd>{settings.retry.not_received?.enabled ? `after ${Math.round(settings.retry.not_received.delay_minutes / 60)}h, ${settings.retry.not_received.window}` : 'off'}</dd>
                <dt>Reminders</dt><dd>{settings.meeting_reminders_minutes_before.map(m => m >= 60 ? `${m / 60}h` : `${m}m`).join(', ') || 'none'} before</dd>
              </dl>
              <h3 style={{ margin: '1rem 0 .4rem' }}>Integrations</h3>
              <div className="row">
                {Object.entries(settings.integrations).map(([k, ok]) => (
                  <span key={k} className="badge"><span className={ok ? 'dot-ok' : 'dot-off'} style={{ margin: 0 }} />{k.replace('_', ' ')}</span>
                ))}
              </div>
              <p className="faint" style={{ fontSize: '.8rem', marginBottom: 0 }}>Edit rules in <code>config/*.yaml</code>, then rebuild.</p>
            </>
          )}
        </div>
      </section>

      <section className="two">
        <div className="glass panel" data-tour="plan">
          <header><h2>Today's plan</h2><Link to="/plan">Why? →</Link></header>
          {plan.data && (
            <>
              <p style={{ margin: '0 0 .6rem' }}>
                <b>{plan.data.will_call.length}</b> to call, <b>{plan.data.skipped.length}</b> skipped.{' '}
                {!plan.data.in_calling_hours && <span className="badge warn">Outside calling hours ({plan.data.window})</span>}
              </p>
              <div className="row">{Object.values(reasonCounts).map(r => <span key={r.text} className="chip">{r.text} <b>{r.n}</b></span>)}</div>
              {plan.data.skipped.length === 0 && plan.data.will_call.length === 0 && <p className="muted">No customers yet.</p>}
            </>
          )}
        </div>
        <div className="glass panel">
          <header><h2>Upcoming calls &amp; reminders</h2></header>
          {d.upcoming_tasks.length === 0 ? <p className="muted">Nothing scheduled.</p> : (
            <table><thead><tr><th>When</th><th>Customer</th><th>Type</th></tr></thead><tbody>
              {d.upcoming_tasks.map(t => (
                <tr key={t.id}><td>{when(t.run_at)}</td>
                  <td><Link to={`/customers/${t.customer_id}`}>{t.customer_name || t.customer_phone}</Link></td>
                  <td>{t.kind === 'reminder' ? 'Meeting reminder' : t.reason === 'callback' ? 'Callback' : 'Retry'}</td></tr>
              ))}
            </tbody></table>
          )}
        </div>
      </section>

      <section className="two">
        <div className="glass panel">
          <header><h2>Upcoming meetings</h2></header>
          {d.upcoming_meetings.length === 0 ? <p className="muted">No meetings booked.</p> : (
            <table><thead><tr><th>When</th><th>Customer</th><th>Mode</th></tr></thead><tbody>
              {d.upcoming_meetings.map(m => (
                <tr key={m.id}><td>{when(m.scheduled_for)}</td>
                  <td><Link to={`/customers/${m.customer_id}`}>{m.customer_name || m.customer_phone}</Link></td>
                  <td>{m.mode || '—'}</td></tr>
              ))}
            </tbody></table>
          )}
        </div>
        <div className="glass panel">
          <header><h2>Achievements</h2><span className="badge">{MILESTONES.filter(m => d.milestones[m.key] >= 1).length}/{MILESTONES.length}</span></header>
          <ul className="list">
            {MILESTONES.map(m => {
              const got = d.milestones[m.key] >= 1
              return <li key={m.key} className={got ? '' : 'locked'}><span><b>{got ? '★ ' : '☆ '}{m.title}</b><br /><small className="faint">{m.text}</small></span>{got && <span className="badge good">{d.milestones[m.key]}</span>}</li>
            })}
          </ul>
        </div>
      </section>
    </main>
  )
}
