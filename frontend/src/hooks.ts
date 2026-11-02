import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './api'

/** Loads data, exposes loading/error and a reload(); signs the user out on a 401. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[], onAuthError: () => void) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const fnRef = useRef(fn)
  fnRef.current = fn
  useEffect(() => {
    let live = true
    setLoading(true)
    fnRef.current().then(d => { if (live) { setData(d); setError('') } })
      .catch((e: unknown) => {
        if (!live) return
        if (e instanceof ApiError && e.status === 401) return onAuthError()
        setError(e instanceof Error ? e.message : 'Request failed')
      })
      .finally(() => live && setLoading(false))
    return () => { live = false }
    // deps are supplied by the caller, so the lint rule cannot verify them
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  const reload = useCallback(() => setTick(t => t + 1), [])
  return { data, error, loading, reload }
}

export const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
