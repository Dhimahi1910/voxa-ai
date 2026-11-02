import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, errMsg, post, when, type Customer, type ImportResult } from '../api'
import { CallButton } from '../components/Actions'
import Modal from '../components/Modal'
import { Badge, Status } from '../components/ui'
import { useLoad } from '../hooks'
import { useToast } from '../toast-context'

const PAGE = 25

export default function Customers({ onAuthError }: { onAuthError: () => void }) {
  const [input, setInput] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(0)
  const [adding, setAdding] = useState(false)
  const [importing, setImporting] = useState(false)
  useEffect(() => { const t = setTimeout(() => { setQ(input.trim()); setPage(0) }, 300); return () => clearTimeout(t) }, [input])

  const { data, error, loading, reload } = useLoad(
    () => api<Customer[]>(`/api/customers?limit=${PAGE}&offset=${page * PAGE}${q ? `&q=${encodeURIComponent(q)}` : ''}`),
    [q, page], onAuthError)

  return (
    <main className="page">
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: '1rem' }}>
        <h1>Customers</h1>
        <div className="row"><button onClick={() => setImporting(true)}>Import CSV</button><button className="primary" onClick={() => setAdding(true)}>Add customer</button></div>
      </div>
      <input className="search" type="search" placeholder="Search name, phone or email" aria-label="Search customers"
        value={input} onChange={e => setInput(e.target.value)} style={{ marginBottom: '1rem' }} />
      <Status loading={loading && !data} error={error} />
      {data && (data.length === 0 ? <p className="muted">No customers found.</p> : (
        <div className="glass panel">
          <table>
            <thead><tr><th>Name</th><th>Phone</th><th>Calls</th><th>Last outcome</th><th>Last call</th><th>Meeting</th><th /></tr></thead>
            <tbody>{data.map(c => (
              <tr key={c.id}>
                <td><Link to={`/customers/${c.id}`}>{c.name || '(no name)'}</Link></td>
                <td>{c.phone}</td><td>{c.call_count}{c.exhausted && <span className="badge"> max</span>}</td>
                <td><Badge value={c.last_outcome} /></td><td>{when(c.last_call_at)}</td><td><Badge value={c.meeting_status} /></td>
                <td><CallButton customerId={c.id} name={c.name || c.phone} onDone={reload} /></td>
              </tr>))}
            </tbody>
          </table>
        </div>
      ))}
      <div className="pager">
        <button disabled={page === 0} onClick={() => setPage(p => p - 1)}>Previous</button>
        <span className="muted">Page {page + 1}</span>
        <button disabled={!data || data.length < PAGE} onClick={() => setPage(p => p + 1)}>Next</button>
      </div>
      {importing && <ImportCsv onClose={() => setImporting(false)} onDone={() => { setImporting(false); reload() }} />}
      {adding && <AddCustomer onClose={() => setAdding(false)} onAdded={() => { setAdding(false); reload() }} />}
    </main>
  )
}

function AddCustomer({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [f, setF] = useState({ name: '', phone: '', email: '' })
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true)
    try { await post('/api/customers', f); toast('good', `${f.name} added`); onAdded() }
    catch (err) { toast('bad', errMsg(err)) } finally { setBusy(false) }
  }
  return (
    <Modal title="Add customer" onClose={onClose}>
      <form onSubmit={submit} style={{ display: 'grid', gap: '.8rem' }}>
        <label>Name<input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required maxLength={200} /></label>
        <label>Phone<input value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} required placeholder="98765 43210 or +91…" /></label>
        <label>Email (optional)<input type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></label>
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={busy}>{busy ? 'Adding…' : 'Add'}</button>
        </div>
      </form>
    </Modal>
  )
}


const TEMPLATE = 'data:text/csv;charset=utf-8,' + encodeURIComponent('name,phone,email\nAsha Patel,98765 43210,asha@example.com\n')

function ImportCsv({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [text, setText] = useState('')
  const [res, setRes] = useState<ImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  async function send(dry: boolean) {
    setBusy(true)
    try {
      const r = await post<ImportResult>('/api/customers/import', { csv: text, dry_run: dry })
      setRes(r)
      if (!dry) { toast('good', `${r.created} customer${r.created === 1 ? '' : 's'} imported`); onDone() }
    } catch (e) { toast('bad', errMsg(e)) } finally { setBusy(false) }
  }
  async function pick(f: File | undefined) {
    if (!f) return
    if (f.size > 900_000) return toast('bad', 'That file is too large (max about 900 KB).')
    setText(await f.text()); setRes(null)
  }
  return (
    <Modal title="Import customers from CSV" onClose={onClose}>
      <p className="muted" style={{ margin: 0 }}>Needs a phone column (phone, mobile or phone_number). Name and email are optional. <a href={TEMPLATE} download="customers-template.csv">Download a template</a>.</p>
      <input type="file" accept=".csv,text/csv" onChange={e => pick(e.target.files?.[0])} aria-label="CSV file" />
      <textarea rows={6} spellCheck={false} value={text} onChange={e => { setText(e.target.value); setRes(null) }} placeholder="…or paste CSV here" aria-label="CSV text" />
      {res && (
        <div className="import-res">
          <div className="row"><span className="badge good">{res.valid} ready</span><span className="badge warn">{res.invalid_count} invalid</span>
            <span className="badge">{res.duplicates} duplicate in file</span><span className="badge">{res.existing} already customers</span></div>
          {res.invalid.length > 0 && <ul className="why">{res.invalid.slice(0, 5).map(i => <li key={i.row}>Row {i.row}: {i.reason} {i.value && `(${i.value})`}</li>)}</ul>}
          {res.preview.length > 0 && <small className="muted">First: {res.preview.map(p => p.name || p.phone).join(', ')}</small>}
        </div>
      )}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button onClick={onClose}>Cancel</button>
        <button onClick={() => send(true)} disabled={busy || !text.trim()}>Preview</button>
        <button className="primary" onClick={() => send(false)} disabled={busy || !res || res.valid === 0}>{res ? `Import ${res.valid}` : 'Import'}</button>
      </div>
    </Modal>
  )
}
