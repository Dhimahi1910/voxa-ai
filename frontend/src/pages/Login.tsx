import { useState, type FormEvent } from 'react'
import { api, setKey } from '../api'
import Orb from '../components/Orb'

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError(''); setKey(value.trim())
    try { await api('/api/dashboard'); onLogin() }
    catch (err) { setKey(''); setError(err instanceof Error && err.message === 'Unauthorized' ? 'That key was not accepted.' : err instanceof Error ? err.message : 'Could not sign in') }
    finally { setBusy(false) }
  }
  return (
    <div className="login-shell">
      <form className="glass login-card" onSubmit={submit}>
        <span className="brand"><span className="dot" />voxai</span>
        <h1>Voice agent console</h1>
        <p className="muted" style={{ margin: 0 }}>Calls, conversations and follow-ups, in one calm place.</p>
        <label htmlFor="key">Admin API key
          <input id="key" type="password" autoComplete="off" value={value} onChange={e => setValue(e.target.value)} required />
        </label>
        <button className="primary" disabled={busy || !value.trim()}>{busy ? 'Checking…' : 'Sign in'}</button>
        {error && <p className="error" role="alert" style={{ margin: 0 }}>{error}</p>}
        <p className="faint" style={{ margin: 0, fontSize: '.82rem' }}>The key is one of <code>API_KEYS</code> in the server's <code>.env</code>. It is kept only for this browser tab.</p>
      </form>
      <Orb intensity={0.35} />
    </div>
  )
}
