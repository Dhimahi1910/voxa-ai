import { Link } from 'react-router-dom'
import { api, when, type TimelineEvent } from '../api'
import { useLoad } from '../hooks'
import { Status } from './ui'

const GLYPH: Record<string, string> = { call: '☎', task: '◷', email: '✉', meeting: '★', dnc: '⊘' }

export default function Journey({ customerId, onAuthError }: { customerId: number; onAuthError: () => void }) {
  const { data, error, loading } = useLoad(() => api<TimelineEvent[]>(`/api/customers/${customerId}/timeline`), [customerId], onAuthError)
  if (!data) return <Status loading={loading} error={error} />
  if (data.length === 0) return <p className="muted">Nothing has happened yet for this customer.</p>
  const now = Date.now()
  return (
    <ol className="timeline">
      {data.map((e, i) => (
        <li key={i} className={`${e.tone} ${new Date(e.at).getTime() > now ? 'future' : ''}`} style={{ animationDelay: `${Math.min(i, 12) * 60}ms` }}>
          <span className="node" aria-hidden="true">{GLYPH[e.kind] ?? '•'}</span>
          <div>
            <b>{e.kind === 'call' && e.call_id ? <Link to={`/calls`}>{e.title}</Link> : e.title}</b>
            <small className="faint"> · {when(e.at)}{new Date(e.at).getTime() > now ? ' (upcoming)' : ''}</small>
            {e.detail && <p className="muted">{e.detail}</p>}
            {e.why && <p className="why-line">Why: {e.why}</p>}
          </div>
        </li>
      ))}
    </ol>
  )
}
