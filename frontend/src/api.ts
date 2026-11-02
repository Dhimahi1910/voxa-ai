// Thin API client. The admin key lives in sessionStorage only (cleared when the tab closes) and is sent as X-API-Key.
const KEY = 'voice-agent-api-key'

export const getKey = (): string => {
  try { return sessionStorage.getItem(KEY) ?? '' } catch { return '' }
}
export const setKey = (v: string) => {
  try {
    if (v) sessionStorage.setItem(KEY, v)
    else sessionStorage.removeItem(KEY)
  } catch { /* storage unavailable */ }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { 'X-API-Key': getKey(), 'Content-Type': 'application/json', ...init?.headers } })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.status === 204 ? (undefined as T) : (res.json() as Promise<T>)
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

const FRIENDLY: Record<string, string> = {
  outside_hours: 'Outside calling hours, so no call was placed.',
  call_in_progress: 'A call to this customer is already in progress.',
  do_not_call: 'This customer is on the do-not-call list.',
}
/** Turn API/network errors into a short message people can act on. */
export const errMsg = (e: unknown): string =>
  e instanceof Error ? FRIENDLY[e.message] ?? e.message : 'Something went wrong'

export interface Customer {
  id: number; name: string; phone: string; email: string; call_count: number
  last_outcome: string | null; last_call_at: string | null; meeting_status: string; exhausted: boolean
}
export interface Call {
  id: number; customer_id: number; reason: string; state: string; outcome: string | null
  provider_call_id: string | null; error: string | null; dialed_at: string | null
  duration_seconds: number | null; summary: string | null; recording_url: string | null
  analysis: Analysis | null; processed_at: string | null; created_at: string
  customer_name?: string; customer_phone?: string; transcript?: string | null
}
export interface Analysis {
  requirements: Record<string, string>; meeting_preference: string; preferred_meeting_time: string
  call_rescheduled_time: string; call_status: string; meeting_status: string; do_not_contact: boolean
}
export interface Switches { real_calls: boolean; email_sending: boolean; sheets_dry_run: boolean; scheduler: boolean }
export interface Dashboard {
  company: string
  milestones: Milestones
  today: { calls: number; by_outcome: Record<string, number>; technical_failures: number }
  totals: { customers: number; do_not_call: number }
  upcoming_tasks: { id: number; kind: string; reason: string; run_at: string; customer_id: number; customer_name: string; customer_phone: string }[]
  upcoming_meetings: { id: number; scheduled_for: string; mode: string; customer_id: number; customer_name: string; customer_phone: string }[]
  switches: Switches
}
export interface Settings {
  business: { company: string; agent: string; requirements: string[] }
  switches: Switches
  calling: { timezone: string; hours: string; days: string[]; daily_run: string; max_attempts: number; min_gap_minutes: number; batch_limit: number }
  retry: Record<string, { enabled: boolean; delay_minutes: number; window: string }>
  meeting_reminders_minutes_before: number[]
  integrations: { voice_provider: boolean; google_sheets: boolean; gmail: boolean; llm: boolean; webhook: boolean }
}
export interface DncEntry { phone: string; reason: string; source: string; created_at: string }

const fmt = new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' })
export const when = (iso: string | null | undefined) => (iso ? fmt.format(new Date(iso)) : '—')
export const safeUrl = (u: string | null | undefined) => (u && /^https?:\/\//i.test(u) ? u : null)

export interface Milestones { calls: number; connected: number; callbacks: number; meetings: number; emails: number }
export interface TimelineEvent { at: string; kind: 'call' | 'task' | 'email' | 'meeting' | 'dnc'; title: string; tone: string; detail: string; why: string; call_id?: number }
export interface PlanToday {
  in_calling_hours: boolean; window: string; days: string[]; batch_limit: number
  will_call: { id: number; name: string; phone: string }[]
  skipped: { id: number; name: string; phone: string; reason: string; reason_text: string }[]
}
export interface Analytics {
  days: number
  totals: { calls: number; failed: number; connect_rate: number; avg_duration: number }
  outcomes: Record<string, number>
  funnel: { label: string; value: number }[]
  by_hour: { hour: number; calls: number; connected: number }[]
  daily: { date: string; calls: number; connected: number }[]
}
export interface PersonaInfo { key: string; label: string; blurb: string }
export interface PracticeResult {
  persona: PersonaInfo; attempt: number; max_attempts: number; analysis_source: string; transcript: string
  provider: { status: string; answered: boolean; duration: number }
  analysis: Analysis
  plan: { mark_dnc: boolean; exhausted: boolean; next_call_at: string | null; next_call_reason: string; meeting_at: string | null; meeting_mode: string
    emails: { kind: string; subject: string; body: string; would_send: boolean }[] }
  reasons: string[]
}
export interface ImportResult {
  dry_run: boolean; total: number; valid: number; invalid: { row: number; reason: string; value: string }[]; invalid_count: number
  duplicates: number; existing: number; created: number; preview: { name: string; phone: string; email: string }[]
}

/** Download an authenticated file (the API key is a header, so a plain link cannot be used). */
export async function download(path: string, filename: string) {
  const res = await fetch(path, { headers: { 'X-API-Key': getKey() } })
  if (!res.ok) throw new ApiError(res.status, res.statusText)
  const url = URL.createObjectURL(await res.blob())
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
}
