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
  return res.json() as Promise<T>
}

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
export interface Dashboard {
  company: string
  today: { calls: number; by_outcome: Record<string, number>; technical_failures: number }
  totals: { customers: number; do_not_call: number }
  upcoming_tasks: { id: number; kind: string; reason: string; run_at: string; customer_id: number; customer_name: string; customer_phone: string }[]
  upcoming_meetings: { id: number; scheduled_for: string; mode: string; customer_id: number; customer_name: string; customer_phone: string }[]
  switches: { real_calls: boolean; email_sending: boolean; sheets_dry_run: boolean; scheduler: boolean }
}

const fmt = new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' })
export const when = (iso: string | null | undefined) => (iso ? fmt.format(new Date(iso)) : '—')
export const safeUrl = (u: string | null | undefined) => (u && /^https?:\/\//i.test(u) ? u : null)
