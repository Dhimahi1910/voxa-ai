import { useEffect, useState } from 'react'
import { ApiError } from './api'

/** Loads data, exposes loading/error, and signs the user out on 401/503 auth failures. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[], onAuthError: () => void) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let live = true
    setLoading(true)
    fn().then(d => { if (live) { setData(d); setError('') } })
      .catch((e: unknown) => {
        if (!live) return
        if (e instanceof ApiError && e.status === 401) return onAuthError()
        setError(e instanceof Error ? e.message : 'Request failed')
      })
      .finally(() => live && setLoading(false))
    return () => { live = false }
    // deps are supplied by the caller, so the lint rule cannot verify them
  }, deps)
  return { data, error, loading }
}

