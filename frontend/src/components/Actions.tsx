import { useState } from 'react'
import { errMsg, post, type Call } from '../api'
import { useSettings } from '../settings-context'
import { useToast } from '../toast-context'
import { Confirm } from './Modal'

/** "Call now" with a confirmation that states clearly whether the call is real or simulated. */
export function CallButton({ customerId, name, onDone, small = true }: { customerId: number; name: string; onDone?: () => void; small?: boolean }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const real = useSettings()?.switches.real_calls ?? false

  async function go() {
    setBusy(true)
    try {
      const call = await post<Call>('/api/calls/start', { customer_id: customerId })
      toast('good', real ? `Call started to ${name}` : `Simulated call recorded for ${name}`)
      setOpen(false); onDone?.()
      return call
    } catch (e) { toast('bad', errMsg(e)); setOpen(false) } finally { setBusy(false) }
  }
  return (
    <>
      <button className={`primary ${small ? 'small' : ''}`} onClick={() => setOpen(true)}>Call now</button>
      {open && (
        <Confirm title={`Call ${name}?`} confirmLabel={real ? 'Place real call' : 'Run simulated call'} busy={busy} onConfirm={go} onClose={() => setOpen(false)}>
          {real
            ? <><b className="error">Real calls are ON.</b> This will phone {name} right now through the voice provider.</>
            : <>Real calls are <b>off</b>, so this is a simulation: nothing will be dialled.</>}
          {' '}Do-not-call numbers, calling hours and in-progress calls are still enforced.
        </Confirm>
      )}
    </>
  )
}

const JOBS: Record<string, { label: string; text: string }> = {
  calling_run: { label: 'Run calling job', text: 'Picks eligible customers from the sheet and database and calls them.' },
  due_tasks: { label: 'Process due tasks', text: 'Runs retries, callbacks and meeting reminders that are due now.' },
  reconcile_calls: { label: 'Reconcile calls', text: 'Checks unfinished calls with the provider and re-syncs the sheet.' },
}
export const jobInfo = (job: string) => JOBS[job]

export function JobButton({ job, primary, onDone }: { job: string; primary?: boolean; onDone?: () => void }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const real = useSettings()?.switches.real_calls ?? false
  const info = JOBS[job]

  async function go() {
    setBusy(true)
    try {
      const r = await post<{ result: Record<string, unknown> }>('/api/jobs/trigger', { job })
      toast('good', `${info.label}: ${Object.entries(r.result).map(([k, v]) => `${k} ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', ')}`)
      setOpen(false); onDone?.()
    } catch (e) { toast('bad', errMsg(e)); setOpen(false) } finally { setBusy(false) }
  }
  return (
    <>
      <button className={primary ? 'primary' : ''} onClick={() => setOpen(true)}>{info.label}</button>
      {open && (
        <Confirm title={`${info.label}?`} confirmLabel="Run now" busy={busy} onConfirm={go} onClose={() => setOpen(false)}>
          {info.text} {job === 'calling_run' && (real ? <b className="error">Real calls are ON: customers will be phoned.</b> : 'Real calls are off, so calls are simulated.')}
        </Confirm>
      )}
    </>
  )
}
