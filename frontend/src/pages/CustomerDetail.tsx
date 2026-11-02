import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, when, type Call, type Customer } from '../api'
import CallPanel from '../components/CallPanel'
import { Badge, Status } from '../components/ui'
import { useLoad } from '../hooks'

export default function CustomerDetail({ onAuthError }: { onAuthError: () => void }) {
  const { id } = useParams()
  const [selected, setSelected] = useState<number | null>(null)
  const cust = useLoad(() => api<Customer>(`/api/customers/${id}`), [id], onAuthError)
  const calls = useLoad(() => api<Call[]>(`/api/calls?customer_id=${id}&limit=100`), [id], onAuthError)
  const c = cust.data
  if (!c) return <Status loading={cust.loading} error={cust.error} />
  const active = selected ?? calls.data?.[0]?.id ?? null

  return (
    <>
      <p><Link to="/customers">← Customers</Link></p>
      <h1>{c.name || '(no name)'}</h1>
      <p className="muted">{c.phone}{c.email && ` · ${c.email}`} · {c.call_count} call(s) · meeting <Badge value={c.meeting_status} /></p>
      <Status loading={calls.loading && !calls.data} error={calls.error} />
      {calls.data && (calls.data.length === 0 ? <p className="muted">No calls yet.</p> : (
        <div className="split">
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
          {active != null && <CallPanel callId={active} onAuthError={onAuthError} />}
        </div>
      ))}
    </>
  )
}
