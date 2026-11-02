import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, errMsg, post, when, type Call, type Customer, type DncEntry } from '../api'
import { CallButton } from '../components/Actions'
import CallPanel from '../components/CallPanel'
import { Confirm } from '../components/Modal'
import Journey from '../components/Journey'
import { Badge, Status } from '../components/ui'
import { useLoad } from '../hooks'
import { useToast } from '../toast-context'

export default function CustomerDetail({ onAuthError }: { onAuthError: () => void }) {
  const { id } = useParams()
  const [selected, setSelected] = useState<number | null>(null)
  const [tab, setTab] = useState<'calls' | 'journey'>('calls')
  const [dncOpen, setDncOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const cust = useLoad(() => api<Customer>(`/api/customers/${id}`), [id], onAuthError)
  const calls = useLoad(() => api<Call[]>(`/api/calls?customer_id=${id}&limit=100`), [id], onAuthError)
  const dnc = useLoad(() => api<DncEntry[]>('/api/dnc'), [], onAuthError)
  const c = cust.data
  if (!c) return <main className="page"><Status loading={cust.loading} error={cust.error} /></main>
  const active = selected ?? calls.data?.[0]?.id ?? null
  const onDnc = !!dnc.data?.some(d => d.phone === c.phone)

  async function addDnc() {
    setBusy(true)
    try { await post('/api/dnc', { phone: c!.phone, reason: 'added from console' }); toast('good', 'Added to do-not-call'); dnc.reload() }
    catch (e) { toast('bad', errMsg(e)) } finally { setBusy(false); setDncOpen(false) }
  }
  const refresh = () => { cust.reload(); calls.reload() }

  return (
    <main className="page">
      <p><Link to="/customers">← Customers</Link></p>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: '.4rem' }}>
        <h1>{c.name || '(no name)'}</h1>
        <div className="row">
          {onDnc ? <span className="badge bad">Do not call</span> : <button className="danger" onClick={() => setDncOpen(true)}>Add to do-not-call</button>}
          {!onDnc && <CallButton customerId={c.id} name={c.name || c.phone} onDone={refresh} small={false} />}
        </div>
      </div>
      <p className="muted">{c.phone}{c.email && ` · ${c.email}`} · {c.call_count} call(s) · meeting <Badge value={c.meeting_status} /></p>
      <div className="seg" role="tablist" aria-label="Customer views" style={{ margin: '.4rem 0 1rem' }}>
        <button role="tab" aria-selected={tab === 'calls'} className={tab === 'calls' ? 'on' : ''} onClick={() => setTab('calls')}>Calls</button>
        <button role="tab" aria-selected={tab === 'journey'} className={tab === 'journey' ? 'on' : ''} onClick={() => setTab('journey')}>Journey</button>
      </div>
      {tab === 'journey' && <div className="glass panel"><Journey customerId={c.id} onAuthError={onAuthError} /></div>}
      {tab === 'calls' && <Status loading={calls.loading && !calls.data} error={calls.error} />}
      {tab === 'calls' && calls.data && (calls.data.length === 0 ? <p className="muted">No calls yet.</p> : (
        <div className="split">
          <div className="glass panel">
            <table>
              <thead><tr><th>When</th><th>Outcome</th><th>Why</th><th>Length</th></tr></thead>
              <tbody>{calls.data.map(k => (
                <tr key={k.id} className={k.id === active ? 'sel' : ''} onClick={() => setSelected(k.id)} tabIndex={0}
                    onKeyDown={e => e.key === 'Enter' && setSelected(k.id)}>
                  <td>{when(k.dialed_at ?? k.created_at)}</td>
                  <td><Badge value={k.outcome ?? k.state} /></td><td>{k.reason}</td>
                  <td>{k.duration_seconds != null ? `${k.duration_seconds}s` : '—'}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
          {active != null && <CallPanel callId={active} onAuthError={onAuthError} />}
        </div>
      ))}
      {dncOpen && (
        <Confirm title="Add to do-not-call?" confirmLabel="Add to list" danger busy={busy} onConfirm={addDnc} onClose={() => setDncOpen(false)}>
          {c.name || c.phone} will no longer be called or emailed, and any scheduled calls will be skipped.
        </Confirm>
      )}
    </main>
  )
}
