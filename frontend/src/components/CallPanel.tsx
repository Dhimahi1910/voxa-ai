import { api, safeUrl, when, type Call } from '../api'
import { Badge, Status } from './ui'
import { useLoad } from '../hooks'

export default function CallPanel({ callId, onAuthError }: { callId: number; onAuthError: () => void }) {
  const { data: call, error, loading } = useLoad(() => api<Call>(`/api/calls/${callId}`), [callId], onAuthError)
  if (!call) return <aside className="panel"><Status loading={loading} error={error} /></aside>
  const reqs = Object.entries(call.analysis?.requirements ?? {}).filter(([, v]) => v)
  const rec = safeUrl(call.recording_url)
  return (
    <aside className="panel">
      <h3>Call #{call.id} <Badge value={call.outcome ?? call.state} /></h3>
      <dl>
        <dt>Dialed</dt><dd>{when(call.dialed_at)}</dd>
        <dt>Duration</dt><dd>{call.duration_seconds != null ? `${call.duration_seconds}s` : '—'}</dd>
        <dt>Reason</dt><dd>{call.reason}</dd>
        <dt>State</dt><dd>{call.state}</dd>
        {call.error && <><dt>Error</dt><dd className="error">{call.error}</dd></>}
        {call.analysis?.meeting_status && <><dt>Meeting</dt><dd><Badge value={call.analysis.meeting_status} /> {call.analysis.preferred_meeting_time}</dd></>}
        {call.analysis?.call_rescheduled_time && <><dt>Callback</dt><dd>{call.analysis.call_rescheduled_time}</dd></>}
        {call.analysis?.do_not_contact && <><dt>Do not contact</dt><dd><Badge value="failed" /> requested by customer</dd></>}
      </dl>
      {call.summary && <><h4>Summary</h4><p>{call.summary}</p></>}
      {reqs.length > 0 && <><h4>Requirements</h4><dl>{reqs.map(([k, v]) => <><dt key={k}>{k.replace(/_/g, ' ')}</dt><dd key={k + 'v'}>{v}</dd></>)}</dl></>}
      {rec && <p><a href={rec} target="_blank" rel="noopener noreferrer">Open recording</a></p>}
      <h4>Transcript</h4>
      <pre className="transcript">{call.transcript || 'No transcript available.'}</pre>
    </aside>
  )
}
