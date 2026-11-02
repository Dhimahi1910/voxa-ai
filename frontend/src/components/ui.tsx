const TONE: Record<string, string> = {
  Connected: 'good', Scheduled: 'good', 'Not Received': 'warn', 'Not Responded': 'warn', Ended: 'warn',
  Rescheduled: 'info', failed: 'bad', unknown: 'bad', Pending: 'muted',
}
export const Badge = ({ value }: { value: string | null | undefined }) =>
  value ? <span className={`badge ${TONE[value] ?? ''}`}>{value}</span> : <span className="badge">—</span>

export const Status = ({ loading, error }: { loading: boolean; error: string }) =>
  error ? <p className="error" role="alert">{error}</p> : loading ? <p className="muted">Loading…</p> : null
