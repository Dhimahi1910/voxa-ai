import { useState, type FormEvent } from 'react'
import { api, setKey } from '../api'

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError(''); setKey(value.trim())
    try { await api('/api/dashboard'); onLogin() }
    catch (err) { setKey(''); setError(err instanceof Error ? err.message : 'Could not sign in') }
    finally { setBusy(false) }
  }
  return (
    <form className="login" onSubmit={submit}>
      <h1>Voice Agent Console</h1>
      <label htmlFor="key">Admin API key</label>
      <input id="key" type="password" autoComplete="off" value={value} onChange={e => setValue(e.target.value)} required />
      <button disabled={busy || !value.trim()}>{busy ? 'Checking…' : 'Sign in'}</button>
      {error && <p className="error" role="alert">{error}</p>}
      <p className="muted">The key is one of the <code>API_KEYS</code> in the server's <code>.env</code>. It is kept only for this browser tab.</p>
    </form>
  )
}
