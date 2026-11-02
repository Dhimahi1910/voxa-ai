import { useEffect, useRef, useState } from 'react'
import { api, errMsg, post, when, type PersonaInfo, type PracticeResult } from '../api'
import { Badge, Status } from '../components/ui'
import { VeeshaTip } from '../components/Veesha'
import { fireConfetti } from '../confetti'
import { prefersReducedMotion, useLoad } from '../hooks'
import { setFlag } from '../storage'
import { useToast } from '../toast-context'

interface Meta { max_attempts: number; ai_available: boolean; personas: PersonaInfo[] }
const kindLabel = (k: string) => k.replace(/_/g, ' ')

export default function Practice({ onAuthError }: { onAuthError: () => void }) {
  const meta = useLoad(() => api<Meta>('/api/practice/personas'), [], onAuthError)
  const [persona, setPersona] = useState('interested')
  const [attempt, setAttempt] = useState(1)
  const [useAi, setUseAi] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<PracticeResult | null>(null)
  const [shown, setShown] = useState(0)
  const [open, setOpen] = useState<number | null>(null)
  const toast = useToast()
  const timer = useRef<number | undefined>(undefined)

  const lines = (result?.transcript ?? '').split('\n').filter(Boolean)
  const finished = !!result && shown >= lines.length
  useEffect(() => {
    window.clearInterval(timer.current)
    if (!result) return
    if (prefersReducedMotion()) { setShown(lines.length); return }
    setShown(0)
    timer.current = window.setInterval(() => setShown(n => { if (n >= lines.length) { window.clearInterval(timer.current); return n } return n + 1 }), 750)
    return () => window.clearInterval(timer.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result])

  async function run() {
    setBusy(true); setResult(null); setOpen(null)
    try {
      const r = await post<PracticeResult>('/api/practice/run', { persona, attempt, use_ai: useAi })
      setResult(r); setFlag('practiced')
      if (r.plan.meeting_at) fireConfetti(70)
    } catch (e) { toast('bad', errMsg(e)) } finally { setBusy(false) }
  }

  const m = meta.data
  return (
    <main className="page">
      <h1>Practice Room</h1>
      <p className="muted">Pick a customer and watch what Veesha would do. This uses the real rules, but nothing is dialled, emailed or saved.</p>
      <Status loading={meta.loading && !m} error={meta.error} />
      {m && (
        <>
          <section className="personas">
            {m.personas.map(p => (
              <button key={p.key} className={`glass persona ${persona === p.key ? 'on' : ''}`} onClick={() => setPersona(p.key)} aria-pressed={persona === p.key}>
                <b>{p.label}</b><span>{p.blurb}</span>
              </button>
            ))}
          </section>
          <div className="row" style={{ margin: '1rem 0 1.4rem' }}>
            <span className="muted">This is call number</span>
            <div className="seg" role="group" aria-label="Attempt number">
              {Array.from({ length: m.max_attempts }, (_, i) => i + 1).map(n => <button key={n} className={attempt === n ? 'on' : ''} onClick={() => setAttempt(n)}>{n}</button>)}
            </div>
            <span className="faint">of {m.max_attempts} allowed</span>
            {m.ai_available && <label className="check"><input type="checkbox" checked={useAi} onChange={e => setUseAi(e.target.checked)} /> Use real AI analysis (uses tokens)</label>}
            <button className="primary" onClick={run} disabled={busy}>{busy ? 'Calling…' : 'Run practice call'}</button>
          </div>
        </>
      )}

      {result && (
        <div className="split">
          <div className="glass panel">
            <header><h2>The call</h2><Badge value={result.analysis.call_status} /></header>
            {lines.length === 0 ? (
              <div className="ringing"><span /><span /><span /><p className="muted">Ringing… no answer.</p></div>
            ) : (
              <div className="chat">
                {lines.slice(0, shown).map((l, i) => {
                  const agent = l.startsWith('Agent:')
                  return <div key={i} className={`bubble ${agent ? 'agent' : 'cust'}`}><small>{agent ? 'Veesha' : 'Customer'}</small>{l.replace(/^(Agent|Customer):\s*/, '')}</div>
                })}
                {!finished && <div className="bubble typing"><i /><i /><i /></div>}
              </div>
            )}
            <small className="faint">Analysis by {result.analysis_source === 'rules' ? 'fixed rules (no model needed)' : result.analysis_source === 'ai' ? 'the AI model' : 'a scripted example'}.</small>
          </div>

          <div className="glass panel" style={{ opacity: finished || lines.length === 0 ? 1 : 0.35, transition: 'opacity .4s' }}>
            <header><h2>What happens next</h2><span className="badge">call {result.attempt}/{result.max_attempts}</span></header>
            <ul className="why">{result.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
            <div className="outcomes">
              {result.plan.mark_dnc && <div className="out bad"><b>Do not call</b><span>Added to the list. All calls and emails stop.</span></div>}
              {result.plan.next_call_at && <div className="out info"><b>{result.plan.next_call_reason === 'callback' ? 'Callback booked' : 'Retry scheduled'}</b><span>{when(result.plan.next_call_at)}</span></div>}
              {result.plan.meeting_at && <div className="out good"><b>Meeting booked</b><span>{when(result.plan.meeting_at)}{result.plan.meeting_mode && ` · ${result.plan.meeting_mode}`}</span></div>}
              {result.plan.exhausted && <div className="out warn"><b>Attempts used up</b><span>No more automatic calls.</span></div>}
              {!result.plan.mark_dnc && !result.plan.next_call_at && !result.plan.meeting_at && !result.plan.exhausted && <div className="out"><b>No automatic follow-up</b><span>A person should take it from here.</span></div>}
            </div>
            <h3 style={{ margin: '1rem 0 .4rem' }}>Emails it would send</h3>
            {result.plan.emails.length === 0 ? <p className="muted">None.</p> : result.plan.emails.map((e, i) => (
              <div key={i} className="mail">
                <button className="ghost" onClick={() => setOpen(open === i ? null : i)} aria-expanded={open === i}>
                  <b>{e.subject}</b> <span className={`badge ${e.would_send ? 'good' : ''}`}>{e.would_send ? kindLabel(e.kind) : `${kindLabel(e.kind)} (disabled)`}</span>
                </button>
                {open === i && <pre className="transcript">{e.body}</pre>}
              </div>
            ))}
          </div>
        </div>
      )}
      {!result && !busy && <VeeshaTip>Choose a customer type above, set which attempt this is, and press Run. Try the same person on call 3 to see what happens when attempts run out.</VeeshaTip>}
    </main>
  )
}
