import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Dashboard, Settings } from '../api'
import { flag } from '../storage'
import { VeeshaAvatar } from './Veesha'

interface Item { key: string; title: string; done: boolean; text: string; to?: string; cta?: string }

export function checklistItems(d: Dashboard, s: Settings | null): Item[] {
  const i = s?.integrations
  return [
    { key: 'customer', title: 'Add your first customer', done: d.totals.customers > 0, text: 'Add one by hand or import a CSV.', to: '/customers', cta: 'Open customers' },
    { key: 'sim', title: 'Place a simulated call', done: d.milestones.calls > 0, text: 'On the Customers page, press “Call now”. Nothing is dialled while calls are simulated.', to: '/customers', cta: 'Try it' },
    { key: 'practice', title: 'Rehearse in the Practice Room', done: flag('practiced'), text: 'See what happens after a busy, silent or interested customer.', to: '/practice', cta: 'Practice' },
    { key: 'voice', title: 'Connect the voice provider', done: !!i?.voice_provider, text: 'Set VOICE_API_KEY and VOICE_AGENT_ID on the server, then restart.' },
    { key: 'sheet', title: 'Connect Google Sheets', done: !!i?.google_sheets, text: 'Set GOOGLE_APPLICATION_CREDENTIALS and GOOGLE_SHEETS_SPREADSHEET_ID.' },
    { key: 'gmail', title: 'Connect email', done: !!i?.gmail, text: 'Set GMAIL_SENDER and the Google credentials file.' },
    { key: 'llm', title: 'Add the AI analysis key', done: !!i?.llm, text: 'Set LLM_API_KEY so conversations are read by the model.' },
    { key: 'live', title: 'Go live', done: !!s?.switches.real_calls, text: 'When everything above is green, turn on ENABLE_REAL_CALLS on the server. Test with your own number first.' },
  ]
}

export default function Checklist({ dashboard, settings }: { dashboard: Dashboard; settings: Settings | null }) {
  const items = checklistItems(dashboard, settings)
  const done = items.filter(x => x.done).length
  const [open, setOpen] = useState(done < items.length)
  const pct = Math.round((done / items.length) * 100)
  const R = 22, C = 2 * Math.PI * R
  const next = items.find(x => !x.done)

  return (
    <section className="glass panel checklist" data-tour="checklist">
      <header onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer', marginBottom: open ? '.8rem' : 0 }}>
        <div className="row" style={{ flexWrap: 'nowrap', gap: '.9rem' }}>
          <svg width="54" height="54" viewBox="0 0 54 54" aria-label={`${pct}% complete`}>
            <circle cx="27" cy="27" r={R} fill="none" stroke="rgba(255,255,255,.1)" strokeWidth="5" />
            <circle cx="27" cy="27" r={R} fill="none" stroke="url(#ring)" strokeWidth="5" strokeLinecap="round" strokeDasharray={`${(pct / 100) * C} ${C}`} transform="rotate(-90 27 27)" />
            <defs><linearGradient id="ring"><stop offset="0" stopColor="#2de2c9" /><stop offset="1" stopColor="#8b6cff" /></linearGradient></defs>
            <text x="27" y="31" textAnchor="middle" fontSize="12" fill="#eef0ff" fontWeight="700">{pct}%</text>
          </svg>
          <div>
            <h2>{done === items.length ? 'All set. You are ready.' : 'Getting started'}</h2>
            <small className="muted">{done === items.length ? 'Every step is done.' : `${done} of ${items.length} done. Next: ${next?.title}`}</small>
          </div>
        </div>
        <button className="ghost small" aria-expanded={open}>{open ? 'Hide' : 'Show'}</button>
      </header>
      {open && (
        <ul className="steps">
          {items.map(x => (
            <li key={x.key} className={x.done ? 'done' : ''}>
              <span className="tick" aria-hidden="true">{x.done ? '✓' : ''}</span>
              <div><b>{x.title}</b><br /><small className="muted">{x.text}</small></div>
              {!x.done && x.to && <Link to={x.to} className="chip-link">{x.cta}</Link>}
            </li>
          ))}
        </ul>
      )}
      {open && <div className="row" style={{ marginTop: '.4rem' }}><VeeshaAvatar size={22} /><small className="faint">Steps tick themselves off as your setup changes.</small></div>}
    </section>
  )
}
