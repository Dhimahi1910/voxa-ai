import { useState, type FormEvent } from 'react'
import { api, errMsg, post, when, type DncEntry } from '../api'
import { JobButton, jobInfo } from '../components/Actions'
import { Confirm } from '../components/Modal'
import { Status } from '../components/ui'
import { useLoad } from '../hooks'
import { useToast } from '../toast-context'

export default function Controls({ onAuthError }: { onAuthError: () => void }) {
  const dnc = useLoad(() => api<DncEntry[]>('/api/dnc'), [], onAuthError)
  const [phone, setPhone] = useState('')
  const [reason, setReason] = useState('')
  const [removing, setRemoving] = useState<DncEntry | null>(null)
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  async function add(e: FormEvent) {
    e.preventDefault(); setBusy(true)
    try { await post('/api/dnc', { phone, reason }); toast('good', 'Added to do-not-call'); setPhone(''); setReason(''); dnc.reload() }
    catch (err) { toast('bad', errMsg(err)) } finally { setBusy(false) }
  }
  async function remove() {
    if (!removing) return
    setBusy(true)
    try { await api(`/api/dnc?phone=${encodeURIComponent(removing.phone)}`, { method: 'DELETE' }); toast('good', 'Removed from do-not-call'); dnc.reload() }
    catch (err) { toast('bad', errMsg(err)) } finally { setBusy(false); setRemoving(null) }
  }

  return (
    <main className="page">
      <h1>Controls</h1>
      <p className="muted">Every action asks for confirmation first. Real calls and emails stay off unless enabled in the server settings.</p>
      <section className="two">
        <div className="glass panel">
          <header><h2>Jobs</h2></header>
          <ul className="list">
            {['calling_run', 'due_tasks', 'reconcile_calls'].map(j => (
              <li key={j}><span><b>{jobInfo(j).label}</b><br /><small className="faint">{jobInfo(j).text}</small></span><JobButton job={j} /></li>
            ))}
          </ul>
        </div>
        <div className="glass panel">
          <header><h2>Do-not-call list</h2><span className="badge">{dnc.data?.length ?? 0}</span></header>
          <form onSubmit={add} style={{ display: 'grid', gap: '.6rem', marginBottom: '1rem' }}>
            <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="Phone number" aria-label="Phone number" required />
            <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason (optional)" aria-label="Reason" maxLength={500} />
            <button className="danger" disabled={busy || !phone.trim()}>Add to list</button>
          </form>
          <Status loading={dnc.loading && !dnc.data} error={dnc.error} />
          {dnc.data?.length === 0 && <p className="muted">No numbers on the list.</p>}
          <ul className="list">
            {dnc.data?.map(d => (
              <li key={d.phone}>
                <span>{d.phone}<br /><small className="faint">{d.source} · {when(d.created_at)}{d.reason && ` · ${d.reason}`}</small></span>
                <button className="small" onClick={() => setRemoving(d)}>Remove</button>
              </li>
            ))}
          </ul>
        </div>
      </section>
      {removing && (
        <Confirm title="Remove from do-not-call?" confirmLabel="Remove" danger busy={busy} onConfirm={remove} onClose={() => setRemoving(null)}>
          Only do this if {removing.phone} has asked to be contacted again. They may be called and emailed once more.
        </Confirm>
      )}
    </main>
  )
}
