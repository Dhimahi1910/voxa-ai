import { api, safeUrl, when, type Call } from '../api'
import { useLoad } from '../hooks'
import { Badge, Status } from './ui'

export default function CallPanel({ callId, onAuthError }: { callId: number; onAuthError: () => void }) {
  const { data: call, error, loading } = useLoad(() => api<Call>(`/api/calls/${callId}`), [callId], onAuthError)
  if (!call) return <aside className="glass panel"><Status loading={loading} error={error} /></aside>
  const reqs = Object.entries(call.analysis?.requirements ?? {}).filter(([, v]) => v)
  const rec = safeUrl(call.recording_url)
  return (
    <aside className="glass panel">
      <header><h3>Call #{call.id}</h3><Badge value={call.outcome ?? call.state} /></header>
      <dl className="kv">
        <dt>Dialed</dt><dd>{when(call.dialed_at)}</dd>
        <dt>Duration</dt><dd>{call.duration_seconds != null ? `${call.duration_seconds}s` : '—'}</dd>
        <dt>Reason</dt><dd>{call.reason}</dd>
        <dt>State</dt><dd>{call.state}</dd>
        {call.error && <><dt>Error</dt><dd className="error">{call.error}</dd></>}
        {call.analysis?.meeting_status && <><dt>Meeting</dt><dd><Badge value={call.analysis.meeting_status} /> {call.analysis.preferred_meeting_time}</dd></>}
        {call.analysis?.call_rescheduled_time && <><dt>Callback</dt><dd>{call.analysis.call_rescheduled_time}</dd></>}
        {call.analysis?.do_not_contact && <><dt>Do not contact</dt><dd><span className="badge bad">requested by customer</span></dd></>}
      </dl>
      {call.summary && <><h3 style={{ marginTop: '1rem' }}>Summary</h3><p className="muted">{call.summary}</p></>}
      {reqs.length > 0 && <><h3 style={{ marginTop: '1rem' }}>Requirements</h3>
        <dl className="kv">{reqs.map(([k, v]) => <div key={k} style={{ display: 'contents' }}><dt>{k.replace(/_/g, ' ')}</dt><dd>{v}</dd></div>)}</dl></>}
      {rec && <p><a href={rec} target="_blank" rel="noopener noreferrer">Open recording ↗</a></p>}
      <h3 style={{ marginTop: '1rem' }}>Transcript</h3>
      <pre className="transcript">{call.transcript || 'No transcript available.'}</pre>
    </aside>
  )
}
