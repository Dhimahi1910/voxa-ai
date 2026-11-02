import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, when, type Customer } from '../api'
import { Badge, Status } from '../components/ui'
import { useLoad } from '../hooks'

const PAGE = 25

export default function Customers({ onAuthError }: { onAuthError: () => void }) {
  const [input, setInput] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(0)
  useEffect(() => { const t = setTimeout(() => { setQ(input.trim()); setPage(0) }, 300); return () => clearTimeout(t) }, [input])

  const { data, error, loading } = useLoad(
    () => api<Customer[]>(`/api/customers?limit=${PAGE}&offset=${page * PAGE}${q ? `&q=${encodeURIComponent(q)}` : ''}`),
    [q, page], onAuthError)

  return (
    <>
      <h1>Customers</h1>
      <input className="search" type="search" placeholder="Search name, phone or email" aria-label="Search customers"
        value={input} onChange={e => setInput(e.target.value)} />
      <Status loading={loading && !data} error={error} />
      {data && (data.length === 0 ? <p className="muted">No customers found.</p> : (
        <table>
          <thead><tr><th>Name</th><th>Phone</th><th>Calls</th><th>Last outcome</th><th>Last call</th><th>Meeting</th></tr></thead>
          <tbody>{data.map(c => (
            <tr key={c.id}>
              <td><Link to={`/customers/${c.id}`}>{c.name || '(no name)'}</Link></td>
              <td>{c.phone}</td><td>{c.call_count}{c.exhausted && <span className="badge muted"> max</span>}</td>
              <td><Badge value={c.last_outcome} /></td><td>{when(c.last_call_at)}</td><td><Badge value={c.meeting_status} /></td>
            </tr>))}
          </tbody>
        </table>
      ))}
      <div className="pager">
        <button disabled={page === 0} onClick={() => setPage(p => p - 1)}>Previous</button>
        <span>Page {page + 1}</span>
        <button disabled={!data || data.length < PAGE} onClick={() => setPage(p => p + 1)}>Next</button>
      </div>
    </>
  )
}
